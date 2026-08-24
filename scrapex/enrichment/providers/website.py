"""Cautious enrichment from a candidate organization website."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..matching import email_domain, host_of, name_similarity, normalized_phone
from ..models import FieldFact, OrganizationIdentity, ProviderResult

_ISO = re.compile(r"\bISO\s*[-:]?\s*(\d{4,5}(?::\d{4})?)\b", re.IGNORECASE)
_CAREERS = re.compile(
    r"career|careers|vacanc|recruit|jobs?|employment|وظائف|توظيف", re.IGNORECASE
)
_CONTACT = re.compile(r"contact|about|company|من نحن|اتصل|تواصل", re.IGNORECASE)
_HR_MAIL = re.compile(
    r"^(?:hr|career|careers|jobs|recruit|recruitment)[._+-]?", re.IGNORECASE
)


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str
    status_code: int = 200


def _public_host(host: str) -> bool:
    """Reject literal or resolved private addresses before an outbound request."""
    if not host or host == "localhost":
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, 443)}
    except OSError:
        return False
    if not addresses:
        return False
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return False
        if not address.is_global:
            return False
    return True


def _default_fetch(url: str) -> FetchedPage:
    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(12.0, connect=6.0),
        headers={"User-Agent": "ScrapeX/organization-enrichment"},
    ) as client:
        current = url
        for _ in range(6):
            host = urlsplit(current).hostname or ""
            if not _public_host(host):
                raise ValueError(f"website candidate {host!r} does not resolve publicly")
            with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    if not location:
                        raise ValueError("website candidate returned an empty redirect")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").casefold()
                if "html" not in content_type and "xhtml" not in content_type:
                    raise ValueError(
                        f"website candidate returned {content_type or 'unknown content'}"
                    )
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise ValueError("website candidate returned more than 2 MB")
                encoding = response.encoding or "utf-8"
                html = bytes(content).decode(encoding, errors="replace")
                return FetchedPage(str(response.url), html, response.status_code)
    raise ValueError("website candidate redirected more than five times")


class WebsiteProvider:
    name = "website"

    def __init__(self, fetch: Callable[[str], FetchedPage] | None = None):
        self._fetch = fetch or _default_fetch

    def run(self, identity: OrganizationIdentity) -> ProviderResult:
        mapped_host = host_of(identity.website)
        mail_host = email_domain(identity.email)
        candidate_host = mapped_host or mail_host
        if not candidate_host:
            return ProviderResult(self.name, (
                FieldFact(
                    "website_match_status", "not_found", self.name,
                    source_url=identity.source_url, confidence=0.0,
                    verification_status="not_found",
                    evidence={"reason": "no mapped website or non-generic email domain"},
                ),
            ))

        first_error = ""
        root = None
        candidates = []
        if identity.website:
            candidates.append(identity.website if "://" in identity.website
                              else f"https://{identity.website}")
        candidates.extend((f"https://{candidate_host}", f"https://www.{candidate_host}"))
        for url in dict.fromkeys(candidates):
            try:
                root = self._fetch(url)
                break
            except Exception as exc:
                if not first_error:
                    first_error = str(exc)
        if root is None:
            return ProviderResult(self.name, (
                FieldFact(
                    "website_match_status", "not_found", self.name,
                    source_url=f"https://{candidate_host}", confidence=0.0,
                    verification_status="not_found",
                    evidence={"reason": first_error or "website did not answer"},
                ),
            ), error=first_error)

        soup = BeautifulSoup(root.html, "lxml")
        published_names = _published_names(soup)
        score = max((
            name_similarity(expected, published)
            for expected in (identity.company_name, identity.company_name_ar)
            for published in published_names
        ), default=0.0)
        # A domain explains why this page is a candidate; it does not override
        # a contradictory published name. Extra facts are extracted only after
        # the page identifies the organization with at least a plausible name.
        if score >= 0.45 and mapped_host and host_of(root.url) == mapped_host:
            score = max(score, 0.78)
        elif score >= 0.45 and mail_host and host_of(root.url) == mail_host:
            score = max(score, 0.68)
        status = "verified" if score >= 0.82 else (
            "probable" if score >= 0.62 else "manual_review"
        )
        common = {
            "provider": self.name,
            "source_url": root.url,
            "confidence": round(score, 4),
            "verification_status": status,
        }
        facts = [
            FieldFact("website_url", root.url, **common),
            FieldFact("company_domain", host_of(root.url), **common),
            FieldFact("website_match_status", status, **common),
            FieldFact("website_match_score", round(score, 4), **common),
        ]
        if status == "manual_review":
            return ProviderResult(self.name, tuple(facts))

        pages = [root]
        links = _useful_links(soup, root.url)
        for link in links[:4]:
            try:
                pages.append(self._fetch(link))
            except Exception:
                continue
        facts.extend(_facts_from_pages(pages, identity, status, score))
        return ProviderResult(self.name, tuple(facts))


def _meta(soup: BeautifulSoup, name: str) -> str:
    node = soup.find(
        "meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.IGNORECASE)}
    )
    if node is None:
        node = soup.find(
            "meta", attrs={"property": re.compile(f"^og:{name}$", re.IGNORECASE)}
        )
    return str(node.get("content") or "").strip() if node else ""


def _useful_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    base_host = host_of(base_url)
    scored: list[tuple[int, str]] = []
    for link in soup.find_all("a", href=True):
        raw = str(link.get("href") or "").strip()
        absolute = urljoin(base_url, raw)
        if urlsplit(absolute).scheme not in ("http", "https") or host_of(absolute) != base_host:
            continue
        label = f"{link.get_text(' ', strip=True)} {raw}"
        score = 2 if _CAREERS.search(label) else 1 if _CONTACT.search(label) else 0
        if score:
            scored.append((score, absolute.split("#", 1)[0]))
    return list(dict.fromkeys(url for _, url in sorted(scored, reverse=True)))


def _json_ld_values(soup: BeautifulSoup) -> list[str]:
    values: list[str] = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(node.string or node.get_text() or "null")
        except json.JSONDecodeError:
            continue
        queue = payload if isinstance(payload, list) else [payload]
        for item in queue:
            if not isinstance(item, dict):
                continue
            for key in ("knowsAbout", "serviceType"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
                elif isinstance(value, list):
                    values.extend(str(one).strip() for one in value if str(one).strip())
    return list(dict.fromkeys(values))


def _published_names(soup: BeautifulSoup) -> list[str]:
    """Small name-bearing elements, not a whole page that dilutes an exact name."""
    values = []
    if soup.title:
        values.append(soup.title.get_text(" ", strip=True))
    for node in soup.find_all("h1", limit=4):
        values.append(node.get_text(" ", strip=True))
    for property_name in ("og:site_name", "og:title"):
        node = soup.find("meta", attrs={"property": property_name})
        if node and node.get("content"):
            values.append(str(node["content"]).strip())
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(node.string or node.get_text() or "null")
        except json.JSONDecodeError:
            continue
        queue = payload if isinstance(payload, list) else [payload]
        for item in queue:
            if not isinstance(item, dict):
                continue
            for key in ("name", "alternateName", "legalName"):
                if item.get(key):
                    values.append(str(item[key]).strip())
    return list(dict.fromkeys(value for value in values if value))


def _facts_from_pages(
    pages: list[FetchedPage], identity: OrganizationIdentity, status: str, score: float
) -> list[FieldFact]:
    facts: list[FieldFact] = []
    descriptions: list[tuple[str, str]] = []
    certifications: list[str] = []
    specialties: list[str] = []
    career_urls: list[str] = []
    emails: list[tuple[str, str]] = []
    phones: list[tuple[str, str]] = []
    for page in pages:
        soup = BeautifulSoup(page.html, "lxml")
        description = _meta(soup, "description")
        if description:
            descriptions.append((description, page.url))
        text = soup.get_text(" ", strip=True)
        certifications.extend(f"ISO {match}" for match in _ISO.findall(text))
        specialties.extend(_json_ld_values(soup))
        for link in soup.find_all("a", href=True):
            href = str(link.get("href") or "").strip()
            label = f"{link.get_text(' ', strip=True)} {href}"
            absolute = urljoin(page.url, href)
            if _CAREERS.search(label) and urlsplit(absolute).scheme in ("http", "https"):
                career_urls.append(absolute)
            if href.casefold().startswith("mailto:"):
                address = href[7:].split("?", 1)[0].strip()
                if _HR_MAIL.search(address.split("@", 1)[0]):
                    emails.append((address, page.url))
            if href.casefold().startswith("tel:"):
                phone = href[4:].strip()
                if normalized_phone(phone) and normalized_phone(phone) != normalized_phone(
                    identity.phone
                ):
                    phones.append((phone, page.url))
    common = {"provider": "website", "confidence": round(score, 4),
              "verification_status": status}
    if descriptions:
        facts.append(FieldFact("website_description", descriptions[0][0],
                               source_url=descriptions[0][1], **common))
    if certifications:
        facts.append(FieldFact("iso_certifications", sorted(set(certifications)),
                               source_url=pages[0].url, **common))
    if specialties:
        facts.append(FieldFact("core_specialties", specialties,
                               source_url=pages[0].url, **common))
    if career_urls:
        facts.append(FieldFact("careers_url", career_urls[0],
                               source_url=career_urls[0], **common))
    if emails:
        facts.append(FieldFact("careers_email", emails[0][0],
                               source_url=emails[0][1], **common))
        facts.append(FieldFact("careers_contact", emails[0][0],
                               source_url=emails[0][1], **common))
    elif career_urls:
        facts.append(FieldFact("careers_contact", career_urls[0],
                               source_url=career_urls[0], **common))
    if phones:
        facts.append(FieldFact("verified_phone_secondary", phones[0][0],
                               source_url=phones[0][1], **common))
    return facts
