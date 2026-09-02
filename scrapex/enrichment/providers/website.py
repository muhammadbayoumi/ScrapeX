"""Cautious enrichment from a candidate organization website."""
from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from ..matching import (
    email_domain,
    host_of,
    name_similarity,
    normalized_phone,
    registrable_domain,
)
from ..models import FieldFact, OrganizationIdentity, ProviderResult

_ISO = re.compile(r"\bISO\s*[-:]?\s*(\d{4,5}(?::\d{4})?)\b", re.IGNORECASE)
_CERTIFICATION_CONTEXT = re.compile(
    r"certif|accredit|اعتماد|معتمد|شهاد|حاصل", re.IGNORECASE
)
_NEGATED_CERTIFICATION = re.compile(
    r"\b(?:not|never|without|formerly|expired|lapsed)\b|"
    r"غير\s+معتمد|غير\s+حاصل|لا\s+(?:نحمل|نملك|توجد)",
    re.IGNORECASE,
)
_CAREERS = re.compile(
    r"career|careers|vacanc|recruit|jobs?|employment|وظائف|توظيف", re.IGNORECASE
)
_CONTACT = re.compile(r"contact|about|company|من نحن|اتصل|تواصل", re.IGNORECASE)
_CONTACT_PAGE = re.compile(r"contact|اتصل|تواصل", re.IGNORECASE)
_HR_MAIL = re.compile(
    r"^(?:hr|career|careers|jobs|recruit|recruitment)[._+-]?", re.IGNORECASE
)
_EMAIL_ADDRESS = re.compile(
    r"^(?!.*\.\.)[^@\s]{1,64}@[a-z0-9](?=[a-z0-9.-]*\.)"
    r"(?:[a-z0-9.-]{0,251}[a-z0-9])?$",
    re.IGNORECASE,
)
_PACE_LOCK = threading.Lock()
_HOST_NEXT_REQUEST: dict[str, float] = {}
_HOST_ROBOTS_DELAY: dict[str, float] = {}
_DNS_SLOTS = threading.BoundedSemaphore(16)


def _pace_host(host: str) -> None:
    try:
        configured_ms = float(
            os.environ.get("SCRAPEX_WEBSITE_MIN_INTERVAL_MS", "250") or 250
        )
    except ValueError:
        configured_ms = 250.0
    if not math.isfinite(configured_ms):
        configured_ms = 250.0
    interval = max(configured_ms / 1000.0, _HOST_ROBOTS_DELAY.get(host, 0.0), 0.0)
    with _PACE_LOCK:
        now = time.monotonic()
        due = _HOST_NEXT_REQUEST.get(host, now)
        wait = max(0.0, due - now)
        _HOST_NEXT_REQUEST[host] = max(now, due) + interval
    if wait:
        time.sleep(wait)


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str
    status_code: int = 200


def _public_addresses(host: str, port: int = 443) -> tuple[str, ...]:
    """Resolve once and return only a completely public address set.

    Returning the addresses, rather than a boolean, lets the HTTP request pin
    the connection to the exact result that was checked.  A second DNS lookup
    between validation and connect is the classic rebinding gap.
    """
    if not host or host == "localhost":
        return ()
    if not _DNS_SLOTS.acquire(blocking=False):
        return ()
    addresses: set[str] = set()
    failed = []

    def resolve() -> None:
        try:
            addresses.update(
                item[4][0] for item in socket.getaddrinfo(
                    host, port, type=socket.SOCK_STREAM
                )
            )
        except (OSError, UnicodeError) as exc:
            failed.append(exc)
        finally:
            _DNS_SLOTS.release()

    thread = threading.Thread(
        target=resolve, name="scrapex-enrichment-dns", daemon=True
    )
    thread.start()
    try:
        configured_timeout = float(
            os.environ.get("SCRAPEX_DNS_TIMEOUT_SECONDS", "3") or 3
        )
    except ValueError:
        configured_timeout = 3.0
    if not math.isfinite(configured_timeout):
        configured_timeout = 3.0
    thread.join(timeout=min(max(configured_timeout, 0.1), 15.0))
    if thread.is_alive() or failed:
        return ()
    if not addresses:
        return ()
    parsed = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return ()
        if not address.is_global:
            return ()
        parsed.append(address)
    return tuple(str(item) for item in sorted(parsed, key=lambda item: (item.version, str(item))))


def _public_host(host: str) -> bool:
    """Compatibility predicate used by tests and callers that need no pin."""
    return bool(_public_addresses(host))


def _public_peer(response: httpx.Response) -> bool:
    """Verify the connected peer too, closing the DNS-rebinding gap."""
    stream = response.extensions.get("network_stream")
    if stream is None:
        return False
    server = stream.get_extra_info("server_addr")
    if not server:
        return False
    try:
        return ipaddress.ip_address(server[0]).is_global
    except (ValueError, TypeError):
        return False


def _peer_matches(response: httpx.Response, address: str) -> bool:
    stream = response.extensions.get("network_stream")
    server = stream.get_extra_info("server_addr") if stream is not None else None
    if not server:
        return False
    try:
        return ipaddress.ip_address(server[0]) == ipaddress.ip_address(address)
    except (ValueError, TypeError):
        return False


def _new_client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(12.0, connect=6.0),
        # The pool keys connections by the pinned IP URL. Two unrelated hosts
        # may share a CDN address, so reusing that TLS connection would cross
        # logical origins even though each request carries its own Host/SNI.
        limits=httpx.Limits(max_keepalive_connections=0),
        headers={"User-Agent": "ScrapeX/organization-enrichment"},
    )


def _fetch_with_client(
    client: httpx.Client, url: str, *, require_html: bool = True,
    max_bytes: int = 2_000_000,
    policy: Callable[[str], bool] | None = None,
) -> FetchedPage:
    current = url
    original_domain = registrable_domain(url)
    for _ in range(6):
        if policy is not None and not policy(current):
            raise PermissionError("robots.txt disallows organization enrichment")
        parsed = urlsplit(current)
        host = parsed.hostname or ""
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("website candidate has an invalid internationalized host") \
                from exc
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            raise ValueError("website candidate must be an unauthenticated HTTP(S) URL")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("website candidate has an invalid port") from exc
        if port != (443 if parsed.scheme == "https" else 80):
            raise ValueError("website candidate uses a non-standard network port")
        addresses = _public_addresses(host, port)
        if not addresses:
            raise ValueError(f"website candidate {host!r} does not resolve publicly")
        last_error: Exception | None = None
        redirected = False
        for address in addresses:
            pinned_host = f"[{address}]" if ":" in address else address
            pinned = urlunsplit((parsed.scheme, pinned_host, parsed.path or "/",
                                 parsed.query, ""))
            request = client.build_request("GET", pinned, headers={"Host": host})
            request.extensions["sni_hostname"] = host
            try:
                _pace_host(host)
                response = client.send(request, stream=True)
                try:
                    if not _public_peer(response) or not _peer_matches(response, address):
                        raise ValueError("website candidate connected to an unexpected peer")
                    if response.is_redirect:
                        location = response.headers.get("location", "")
                        if not location:
                            raise ValueError("website candidate returned an empty redirect")
                        redirected_url = urljoin(current, location)
                        redirect_parts = urlsplit(redirected_url)
                        if parsed.scheme == "https" and redirect_parts.scheme != "https":
                            raise ValueError("website candidate attempted an HTTPS downgrade")
                        if not original_domain or \
                                registrable_domain(redirected_url) != original_domain:
                            raise ValueError(
                                "website candidate redirected outside its organization domain"
                            )
                        current = redirected_url
                        redirected = True
                        break
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").casefold()
                    if require_html and "html" not in content_type \
                            and "xhtml" not in content_type:
                        raise ValueError(
                            f"website candidate returned {content_type or 'unknown content'}"
                        )
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise ValueError(
                                f"website candidate returned more than {max_bytes} bytes"
                            )
                    encoding = response.encoding or "utf-8"
                    html = bytes(content).decode(encoding, errors="replace")
                    return FetchedPage(current, html, response.status_code)
                finally:
                    response.close()
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
        if redirected:
            continue
        if last_error is not None:
            raise last_error
        raise ValueError("website candidate could not be fetched safely")
    raise ValueError("website candidate redirected more than five times")


class WebsiteProvider:
    name = "website"
    version = "4-official-contact-evidence"
    ttl_seconds = 7 * 24 * 60 * 60
    estimated_requests_per_entity = 8

    def __init__(self, fetch: Callable[[str], FetchedPage] | None = None):
        self._client = None
        self._cache: dict[str, FetchedPage] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self.requests_made = 0
        self._robots_fetch: Callable[[str], FetchedPage] | None = None
        if fetch is not None:
            raw_fetch = fetch
        else:
            self._client = _new_client()
            def raw_fetch(url: str) -> FetchedPage:
                return _fetch_with_client(
                    self._client, url, policy=self._robots_allows
                )
            self._robots_fetch = lambda url: _fetch_with_client(
                self._client, url, require_html=False, max_bytes=512_000
            )

        def cached_fetch(url: str) -> FetchedPage:
            if url not in self._cache:
                self.requests_made += 1
                self._cache[url] = raw_fetch(url)
            return self._cache[url]

        self._fetch = cached_fetch

    def _robots_allows(self, url: str) -> bool:
        if self._robots_fetch is None:
            return True
        parsed = urlsplit(url)
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            try:
                self.requests_made += 1
                page = self._robots_fetch(robots_url)
            except Exception:
                # An absent or unreadable file states no enforceable rule. The
                # fetch still remains visible through request metrics.
                self._robots[origin] = None
            else:
                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(page.html.splitlines())
                delay = parser.crawl_delay("ScrapeX") or parser.crawl_delay("*")
                if delay:
                    _HOST_ROBOTS_DELAY[parsed.hostname or ""] = max(float(delay), 0.0)
                self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch("ScrapeX", url)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

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
            if not self._robots_allows(url):
                if not first_error:
                    first_error = "robots.txt disallows organization enrichment"
                continue
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
            "entity_match_confidence": round(score, 4),
            "extraction_confidence": 1.0,
            "source_authority": 0.9,
            "evidence": {
                "candidate_basis": "mapped_website" if mapped_host else "email_domain",
                "published_names": published_names[:10],
            },
        }
        facts = [
            FieldFact("website_url", root.url, **common),
            FieldFact("company_domain", registrable_domain(root.url), **common),
            FieldFact("website_match_status", status, **common),
            FieldFact("website_match_score", round(score, 4), **common),
        ]
        if status == "manual_review":
            return ProviderResult(self.name, tuple(facts))

        pages = [root]
        links = _useful_links(soup, root.url)
        for link in links[:4]:
            if not self._robots_allows(link):
                continue
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
        score = 3 if _CONTACT_PAGE.search(label) else (
            2 if _CAREERS.search(label) else 1 if _CONTACT.search(label) else 0
        )
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


def _linkedin_company_url(value: str) -> str:
    """Canonicalize only direct LinkedIn organization pages.

    A link from the verified official website is evidence that the URL belongs to
    the organization.  It is not evidence about LinkedIn page contents, so this
    function never fetches LinkedIn and rejects profiles, sharing links and lookalike
    hosts.
    """
    parsed = urlsplit((value or "").strip())
    if parsed.scheme not in ("http", "https") or registrable_domain(value) != "linkedin.com":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].casefold() != "company":
        return ""
    slug = parts[1]
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", slug) is None:
        return ""
    return f"https://www.linkedin.com/company/{slug}/"


def _whatsapp_contact_url(value: str) -> str:
    """Return a stable wa.me URL without carrying pre-filled message text."""
    parsed = urlsplit((value or "").strip())
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if parsed.scheme not in ("http", "https"):
        return ""
    if host == "wa.me":
        number = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"api.whatsapp.com", "web.whatsapp.com"} \
            and parsed.path.rstrip("/").casefold() == "/send":
        number = parse_qs(parsed.query).get("phone", [""])[0]
    else:
        return ""
    digits = re.sub(r"\D", "", number)
    return f"https://wa.me/{digits}" if 7 <= len(digits) <= 15 else ""


def _unique_pairs(
    values: list[tuple[str, str]], key: Callable[[str], str]
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value, source_url in values:
        normalized = key(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append((value, source_url))
    return result


def _facts_from_pages(
    pages: list[FetchedPage], identity: OrganizationIdentity, status: str, score: float
) -> list[FieldFact]:
    facts: list[FieldFact] = []
    descriptions: list[tuple[str, str]] = []
    certifications: list[str] = []
    specialties: list[str] = []
    career_urls: list[str] = []
    contact_urls: list[str] = []
    emails: list[tuple[str, str]] = []
    phones: list[tuple[str, str]] = []
    linkedin_urls: list[tuple[str, str]] = []
    whatsapp_urls: list[tuple[str, str]] = []
    organization_domain = registrable_domain(pages[0].url)
    source_email = (identity.email or "").strip().casefold()
    for page in pages:
        soup = BeautifulSoup(page.html, "lxml")
        if _CONTACT_PAGE.search(urlsplit(page.url).path):
            contact_urls.append(page.url.split("#", 1)[0])
        description = _meta(soup, "description")
        if description:
            descriptions.append((description, page.url))
        text = soup.get_text(" ", strip=True)
        certifications.extend(_certifications(text))
        specialties.extend(_json_ld_values(soup))
        for link in soup.find_all("a", href=True):
            href = str(link.get("href") or "").strip()
            label = f"{link.get_text(' ', strip=True)} {href}"
            absolute = urljoin(page.url, href)
            if _CAREERS.search(label) and urlsplit(absolute).scheme in ("http", "https"):
                career_urls.append(absolute)
            if _CONTACT_PAGE.search(label) and urlsplit(absolute).scheme in ("http", "https") \
                    and host_of(absolute) == host_of(page.url):
                contact_urls.append(absolute.split("#", 1)[0])
            if href.casefold().startswith("mailto:"):
                address = href[7:].split("?", 1)[0].strip().casefold()
                address_domain = registrable_domain(address.rsplit("@", 1)[-1])
                if _EMAIL_ADDRESS.fullmatch(address) and (
                    address == source_email or address_domain == organization_domain
                ):
                    emails.append((address, page.url))
            if href.casefold().startswith("tel:"):
                phone = href[4:].strip()
                if len(normalized_phone(phone)) >= 7:
                    phones.append((phone, page.url))
            linkedin_url = _linkedin_company_url(absolute)
            if linkedin_url:
                linkedin_urls.append((linkedin_url, page.url))
            whatsapp_url = _whatsapp_contact_url(absolute)
            if whatsapp_url:
                whatsapp_urls.append((whatsapp_url, page.url))
    emails = _unique_pairs(emails, str.casefold)
    phones = _unique_pairs(phones, normalized_phone)
    linkedin_urls = _unique_pairs(linkedin_urls, str.casefold)
    whatsapp_urls = _unique_pairs(whatsapp_urls, str.casefold)
    career_urls = list(dict.fromkeys(career_urls))
    contact_urls = list(dict.fromkeys(contact_urls))
    common = {"provider": "website", "confidence": round(score, 4),
              "verification_status": status,
              "entity_match_confidence": round(score, 4),
              "source_authority": 0.9}
    if descriptions:
        facts.append(FieldFact("website_description", descriptions[0][0],
                               source_url=descriptions[0][1],
                               extraction_confidence=0.95, **common))
    if certifications:
        facts.append(FieldFact("iso_certifications", sorted(set(certifications)),
                               source_url=pages[0].url,
                               extraction_confidence=0.65,
                               **{
                                   **common,
                                   "verification_status": "probable",
                                   "evidence": {
                                       "claim_type": "official_website_self_claim",
                                       "certificate_validity_verified": False,
                                   },
                               }))
    if specialties:
        facts.append(FieldFact("core_specialties", list(dict.fromkeys(specialties)),
                               source_url=pages[0].url,
                               extraction_confidence=0.75, **common))
    if career_urls:
        facts.append(FieldFact("careers_url", career_urls[0],
                               source_url=career_urls[0],
                               extraction_confidence=0.85, **common))
    career_emails = [item for item in emails if _HR_MAIL.search(
        item[0].split("@", 1)[0]
    )]
    if career_emails:
        facts.append(FieldFact("careers_email", career_emails[0][0],
                               source_url=career_emails[0][1],
                               extraction_confidence=0.9, **common))
        facts.append(FieldFact("careers_contact", career_emails[0][0],
                               source_url=career_emails[0][1],
                               extraction_confidence=0.9, **common))
    elif career_urls:
        facts.append(FieldFact("careers_contact", career_urls[0],
                               source_url=career_urls[0],
                               extraction_confidence=0.85, **common))
    if contact_urls:
        facts.append(FieldFact("contact_page_url", contact_urls[0],
                               source_url=contact_urls[0],
                               extraction_confidence=0.95, **common))
    if emails:
        facts.append(FieldFact(
            "contact_emails", [item[0] for item in emails],
            source_url=emails[0][1], extraction_confidence=0.95,
            evidence={"method": "same_domain_mailto_links", "items": [
                {"value": value, "source_url": source_url}
                for value, source_url in emails
            ]}, **common,
        ))
    if phones:
        facts.append(FieldFact(
            "contact_phones", [item[0] for item in phones],
            source_url=phones[0][1], extraction_confidence=0.9,
            evidence={"method": "tel_links", "items": [
                {"value": value, "source_url": source_url}
                for value, source_url in phones
            ]}, **common,
        ))
    secondary_phones = [item for item in phones if normalized_phone(item[0]) !=
                        normalized_phone(identity.phone)]
    if secondary_phones:
        facts.append(FieldFact("verified_phone_secondary", secondary_phones[0][0],
                               source_url=secondary_phones[0][1],
                               extraction_confidence=0.85, **common))
    if whatsapp_urls:
        facts.append(FieldFact(
            "whatsapp_url", whatsapp_urls[0][0], source_url=whatsapp_urls[0][1],
            extraction_confidence=0.95,
            evidence={"relationship": "official_website_outbound_link"}, **common,
        ))
    if len(linkedin_urls) == 1:
        linkedin_url, source_url = linkedin_urls[0]
        linkedin_evidence = {
            "relationship": "official_website_outbound_link",
            "linkedin_page_fetched": False,
        }
        facts.extend((
            FieldFact(
                "linkedin_company_url", linkedin_url, source_url=source_url,
                extraction_confidence=0.98, evidence=linkedin_evidence, **common,
            ),
            FieldFact(
                "linkedin_match_status", status, source_url=source_url,
                extraction_confidence=0.98, evidence=linkedin_evidence, **common,
            ),
            FieldFact(
                "linkedin_match_score", round(score, 4), source_url=source_url,
                extraction_confidence=0.98, evidence=linkedin_evidence, **common,
            ),
        ))
    elif len(linkedin_urls) > 1:
        facts.append(FieldFact(
            "linkedin_match_status", "manual_review", provider="website",
            source_url=linkedin_urls[0][1], confidence=round(score, 4),
            verification_status="manual_review",
            entity_match_confidence=round(score, 4), extraction_confidence=0.98,
            source_authority=0.9,
            evidence={"reason": "multiple official website LinkedIn company links",
                      "candidates": [item[0] for item in linkedin_urls]},
        ))
    return facts


def _certifications(text: str) -> list[str]:
    """Return ISO numbers only when the page positively claims certification."""
    values = []
    for match in _ISO.finditer(text):
        context = text[max(0, match.start() - 80):match.end() + 80]
        if (
            _CERTIFICATION_CONTEXT.search(context)
            and not _NEGATED_CERTIFICATION.search(context)
        ):
            values.append(f"ISO {match.group(1)}")
    return values
