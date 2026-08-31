"""Deterministic identity checks shared by enrichment providers."""
from __future__ import annotations

import ipaddress
import math
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlsplit

GENERIC_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com",
    "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com", "aol.com",
    "proton.me", "protonmail.com", "mail.com", "gmx.com", "gmx.net",
})

_NON_WORD = re.compile(r"[^\w\u0600-\u06ff]+", re.UNICODE)
_PHONE = re.compile(r"\D+")
_LEGAL_WORDS = {
    "company", "co", "corp", "corporation", "limited", "ltd", "llc",
    "establishment", "شركة", "مؤسسة", "المحدودة",
}
_MULTI_LABEL_PUBLIC_SUFFIXES = frozenset({
    "co.uk", "org.uk", "com.sa", "net.sa", "org.sa", "com.eg", "com.ae",
    "co.za", "com.au", "com.kw", "com.qa", "com.bh", "com.om", "com.jo",
})


def normalized_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    folded = "".join(
        character for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).casefold()
    folded = folded.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ـ": "",
    }))
    words = [word for word in _NON_WORD.sub(" ", folded).split()
             if word not in _LEGAL_WORDS]
    return " ".join(words)


def name_similarity(left: str, right: str) -> float:
    a, b = normalized_name(left), normalized_name(right)
    if not a or not b:
        return 0.0
    containment = (
        min(len(a), len(b)) / max(len(a), len(b)) if a in b or b in a else 0.0
    )
    a_words, b_words = set(a.split()), set(b.split())
    union = a_words | b_words
    jaccard = len(a_words & b_words) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    return round(max(containment, jaccard, sequence), 4)


def normalized_phone(value: str) -> str:
    digits = _PHONE.sub("", value or "")
    return digits[-9:] if len(digits) >= 9 else digits


def host_of(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").casefold().strip(".")
    return host.removeprefix("www.")


def registrable_domain(value: str) -> str:
    """Return a conservative eTLD+1 for common contractor-market domains.

    This deliberately avoids pretending to be a complete Public Suffix List.
    Unknown suffixes use the ordinary final two labels; known country-code
    second-level suffixes retain three.  URL safety still uses `host_of`, never
    this coarser identity helper.
    """
    host = host_of(value)
    labels = host.split(".")
    if len(labels) < 2:
        return host
    suffix = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if suffix in _MULTI_LABEL_PUBLIC_SUFFIXES \
        and len(labels) >= 3 else suffix


def email_domain(value: str) -> str:
    raw = (value or "").strip().casefold()
    if raw.count("@") != 1:
        return ""
    local, raw_domain = raw.rsplit("@", 1)
    if (
        not local
        or any(character.isspace() for character in local + raw_domain)
        or any(character in raw_domain for character in "/:?#[]")
    ):
        return ""
    domain = raw_domain.rstrip(".")
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    labels = ascii_domain.split(".")
    if (
        len(ascii_domain) > 253
        or len(labels) < 2
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or re.fullmatch(r"[a-z0-9-]+", label) is None
            for label in labels
        )
    ):
        return ""
    try:
        ipaddress.ip_address(ascii_domain)
        return ""
    except ValueError:
        pass
    core = registrable_domain(ascii_domain)
    if ascii_domain in GENERIC_EMAIL_DOMAINS or core in GENERIC_EMAIL_DOMAINS:
        return ""
    return core


def haversine_metres(
    latitude: float, longitude: float, other_latitude: float, other_longitude: float
) -> float:
    radius = 6_371_000.0
    lat1, lat2 = math.radians(latitude), math.radians(other_latitude)
    dlat = lat2 - lat1
    dlon = math.radians(other_longitude - longitude)
    part = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * \
        math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(part), math.sqrt(1 - part))


def status_for_score(score: float) -> str:
    if score >= 0.88:
        return "verified"
    if score >= 0.72:
        return "probable"
    return "manual_review"
