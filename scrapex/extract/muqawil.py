"""Reading one contractor off muqawil.org's pages.

Step 2 of the contractor plan, and it sits BESIDE `html_table.py` rather than
replacing it: a profile page carries five real `<table>` elements — the licences
and their readiness, the two contractor lists, the technical rating and the
contract counts — and those go through `detect_html_tables` exactly as any other
site's would. What this file reads is everything that is NOT a table, which on a
listing page is all of it: **a listing page contains zero `<table>` elements.**

TWO FAILURES HERE ARE SILENT, AND BOTH HAVE A GUARD OF THEIR OWN.

  1. THE EMAIL IS NOT IN THE HTML. Cloudflare replaces it with the literal
     `[email protected]` and an attribute `data-cfemail` holding the address
     XOR-ed byte by byte under a key that is its own first byte. A parser that
     does not decode stores that literal for every contractor in the country,
     and a test asking "is this column populated?" passes forever.

     THE KEY ROTATES PER RENDER. The same address came back as
     `670e1327140406491406` and `f9908db98a9a98d78a98` on two fetches minutes
     apart. So nothing may pin the ciphertext — only the address it decodes to.

  2. THE COORDINATES ARE IN AN INLINE SCRIPT. Not a `data-` attribute, not a map
     iframe: `lat:` and `lng:` inside a `<script>`. The day that script changes
     there is no error to catch — only two columns that quietly become NULL.

WHY THE ENGLISH LABEL IS THE KEY, AND THE ARABIC ONE IS NEVER READ. Measured on
the two committed fixtures: a profile has ELEVEN `.info-box` pairs in BOTH
locales, in the same order, index for index. So the English page is read by its
labels — which are stable — and the Arabic value is taken from the SAME INDEX.
The Arabic labels are never matched against anything, which is the point: the
Arabic membership-number label is spelled `رقم العضويه`, with `ه` and not `ة`,
and a parser keyed on it breaks on a difference no reader would ever notice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from .html_table import InferredField, TableCandidate
from .models import MAX_TABLE_ROWS

#: Where a card sits, in the same shape `html_table.py` writes for a `<table>`
#: (`table#id::row(1)`). It is stored on every record as `source_locator`, so it
#: has to name something a person could go and look at.
_LOCATOR = "div.section-card"

#: `label -> field_key`, in the page's own order. English only, on purpose —
#: see the module docstring. A label this map does not know is KEPT, under a
#: slug of its own, rather than dropped: a field the site adds is news, and a
#: parser that silently discards what it was not told about is how it stays
#: news for a year.
PROFILE_FIELDS: dict[str, str] = {
    "Membership Number": "membership_number",
    "Membership": "membership_type",
    "Member Since": "member_since",
    "Company Size": "company_size",
    "Training credit hours": "training_credit_hours",
    "Organization Mobile Number": "organization_mobile_number",
    "Organization Email": "organization_email",
    "City": "city",
    "Region": "region",
    "Address": "address",
    "Activity": "activity",
}

#: Fields whose Arabic value is a DIFFERENT value rather than the same one
#: written twice. Everything else pairs by default; these are the exceptions
#: measured on the fixtures — a date reads `2018/08/25` in both, and the address
#: is published in Arabic on the ENGLISH page, so neither earns an `_ar`.
NOT_BILINGUAL = frozenset({"membership_number", "member_since",
                           "organization_mobile_number", "organization_email",
                           "address"})

_CFEMAIL = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')
_LATLNG = re.compile(
    r"lat:\s*(-?\d+(?:\.\d+)?).{0,80}?lng:\s*(-?\d+(?:\.\d+)?)", re.DOTALL)
_PROFILE_HREF = re.compile(r"/(?:en|ar)/contractors/(\d+)/\d+")


class CoordinatesMoved(LookupError):
    """The inline script no longer carries `lat:`/`lng:` where it did.

    RAISED, NOT ANSWERED None. None means "this contractor has no location",
    which is a real state for a page that never had one — and a parser that
    returned it for a script that MOVED would turn a layout change into
    seventeen thousand contractors quietly losing their coordinates.
    """


@dataclass(frozen=True)
class Reading:
    """One contractor, as one page in one language published it."""

    fields: dict[str, str] = field(default_factory=dict)
    #: Every label the page carried, in order, whether or not it was recognised.
    labels: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    latitude: float | None = None
    longitude: float | None = None


def decode_cfemail(encoded: str) -> str:
    """Cloudflare's email obfuscation, undone.

    The first byte is the key and every byte after it is XOR-ed with it. There
    is nothing clever here; the only thing worth writing down is that this must
    happen at all, because the alternative reads as success.
    """
    if len(encoded) < 4 or len(encoded) % 2:
        raise ValueError(f"not a data-cfemail payload: {encoded!r}")
    key = int(encoded[:2], 16)
    return "".join(chr(int(encoded[i:i + 2], 16) ^ key)
                   for i in range(2, len(encoded), 2))


def read_email(html: str) -> str:
    """The organisation's address, decoded. Empty when the page carries none."""
    found = _CFEMAIL.search(html)
    return decode_cfemail(found.group(1)) if found else ""


def read_coordinates(html: str) -> tuple[float, float] | None:
    """`(latitude, longitude)` from the inline script, or None if this page has
    no map at all.

    The difference between "no map" and "the map moved" is the whole guard: a
    page with a map section but no readable pair raises `CoordinatesMoved`.
    """
    found = _LATLNG.search(html)
    if found is not None:
        return float(found.group(1)), float(found.group(2))
    if re.search(r"\blat\s*:|initMap|new\s+google\.maps", html):
        raise CoordinatesMoved(
            "this page has map machinery but no readable lat/lng pair — the "
            "inline script's shape has changed, and every contractor would "
            "otherwise lose its coordinates without an error")
    return None


def _text(node: Tag | None) -> str:
    """Collapsed text. muqawil pads its cells with newlines and long runs of
    spaces, so nothing may be compared before this has run."""
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "unnamed"


def _boxes(soup: BeautifulSoup) -> list[tuple[str, str]]:
    pairs = []
    for box in soup.select(".info-box"):
        name, value = box.select_one(".info-name"), box.select_one(".info-value")
        if name is not None and value is not None:
            pairs.append((_text(name), _text(value)))
    return pairs


def read_profile(html: str) -> Reading:
    """One profile page, in whichever language it was fetched.

    The labels are returned alongside the mapped fields so the Arabic page can
    be paired to the English one BY INDEX — which is the only pairing that does
    not depend on reading an Arabic label correctly.
    """
    soup = BeautifulSoup(html, "html.parser")
    pairs = _boxes(soup)

    fields: dict[str, str] = {}
    for label, value in pairs:
        key = PROFILE_FIELDS.get(label)
        fields[key or f"x_{_slug(label)}"] = value

    email = read_email(html)
    if email:
        fields["organization_email"] = email

    latitude = longitude = None
    coordinates = read_coordinates(html)
    if coordinates is not None:
        latitude, longitude = coordinates

    return Reading(fields=fields,
                   labels=tuple(label for label, _ in pairs),
                   values=tuple(value for _, value in pairs),
                   latitude=latitude, longitude=longitude)


def read_listing(html: str) -> list[dict[str, str]]:
    """Every contractor a listing page names, with what the card publishes.

    Cards are those `div.section-card` that hold a profile link — a page has
    twenty-one and twenty contractors, and the twenty-first is not one.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for card in soup.select("div.section-card"):
        link = card.find("a", href=_PROFILE_HREF)
        if link is None:
            continue
        found = _PROFILE_HREF.search(link["href"])
        row: dict[str, str] = {"contractor_id": found.group(1)}

        title = card.select_one("h2.card-title a")
        row["company_name"] = _text(title)
        row["membership_level"] = " ".join(
            str(card.get("data-membership-text", "")).split())

        logo = card.select_one("img.card-img")
        source = (logo.get("src") or "") if logo else ""
        # THE PLACEHOLDER IS NOT A LOGO. The site's own `onerror` names
        # `default.jpg`; a card already showing it has no logo, and storing the
        # placeholder URL would make every logo-less contractor look like one
        # that has a picture nobody can tell apart from the others.
        row["logo_url"] = "" if source.endswith("companies/default.jpg") else source

        rater = card.select_one(".rater")
        row["customer_rating_score"] = (rater.get("data-rate-value") or "") if rater else ""
        votes = _text(card.select_one(".votes-num"))
        count = re.search(r"(\d+)", votes)
        row["customer_rating_count"] = count.group(1) if count else ""

        for name, value in _boxes(card):
            row[f"card_{_slug(name)}"] = value
        rows.append(row)
    return rows


def listing_candidate(html: str, *, table_index: int = 0) -> TableCandidate:
    """The cards on one listing page, in the shape the approval path already speaks.

    THE MISSING LINK, AND IT IS AN ADAPTER RATHER THAN A SECOND PIPELINE.
    `approve_candidate` and everything under it — `_validated_rows`,
    `_schema_payload`, `_ensure_schema`, the upsert, the revision, the
    idempotent replay — are written against `TableCandidate`. They have nothing
    to do with `<table>`; only the DETECTION does. A muqawil listing page holds
    ZERO `<table>` elements, so detection finds nothing — but the cards are rows
    with named columns, which is all a candidate has ever been.

    So this converts, and not one line of the storage half changes. The
    alternative — a parallel path from cards to `generic_record` — would be a
    second copy of the atomicity, the idempotency and the revision history, and
    the two would drift on the first bug fixed in only one of them.

    WHAT IS NOT CLAIMED HERE. Every field is typed `text`, and deliberately:
    `html_table.py` infers types from a table's own values, and inference over
    twenty rows of one page would guess `integer` for a rating that is `4.5` on
    page two. The owner types the schema at approval, which is the step this
    whole design exists to keep. Confidence is 1.0 because nothing was guessed.
    """
    rows = read_listing(html)
    if not rows:
        return TableCandidate(
            table_index=table_index, name="contractors", locator=_LOCATOR,
            fields=(), rows=(), confidence=0.0,
            warnings=("No contractor cards on this page.",),
            approvable=False, truncated=False)

    # THE UNION, NOT THE FIRST ROW'S KEYS. A contractor with no rating carries
    # no rating keys at all, so keying the schema off row one would drop a
    # column for every contractor after it that happened to have one.
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)

    fields = tuple(
        InferredField(
            field_key=name, source_name=name, data_type="text",
            nullable=any(not row.get(name) for row in rows),
            position=position, confidence=1.0,
            uniqueness=_uniqueness(rows, name),
            null_fraction=sum(1 for row in rows if not row.get(name)) / len(rows),
            identity_candidate=(name == "contractor_id"),
        )
        for position, name in enumerate(names)
    )
    return TableCandidate(
        table_index=table_index, name="contractors", locator=_LOCATOR,
        fields=fields,
        # EVERY FIELD ON EVERY ROW, with absent ones as None rather than
        # missing: `_validated_rows` walks the FIELD list, and a row that
        # simply lacks a key would raise rather than record an empty cell.
        rows=tuple({name: (row.get(name) or None) for name in names}
                   for row in rows),
        confidence=1.0, warnings=(), approvable=True,
        truncated=len(rows) >= MAX_TABLE_ROWS)


def _uniqueness(rows: list[dict[str, str]], name: str) -> float:
    seen = {row.get(name) for row in rows if row.get(name)}
    return len(seen) / len(rows) if rows else 0.0


def merge_locales(english: Reading, arabic: Reading) -> dict[str, str]:
    """One contractor from its two pages, with the `_ar` half attached.

    PAIRED BY INDEX, NEVER BY LABEL. Both locales publish the same eleven boxes
    in the same order, so the English label names the field and the Arabic page
    supplies the value sitting at the same position. Nothing here ever reads an
    Arabic label, which is exactly why a spelling difference in one cannot break
    it.

    A page whose box count differs from its sibling's is REFUSED rather than
    zipped to the shorter of the two: zipping would silently attach the wrong
    Arabic value to every field after the divergence, and a wrong value is worse
    than a missing one in a table whose whole purpose is to be believed.
    """
    if len(english.labels) != len(arabic.labels):
        raise ValueError(
            f"the English page published {len(english.labels)} fields and the "
            f"Arabic one {len(arabic.labels)}; pairing them by position would "
            "attach the wrong Arabic value to every field after the difference")

    merged = dict(english.fields)
    for index, label in enumerate(english.labels):
        key = PROFILE_FIELDS.get(label) or f"x_{_slug(label)}"
        if key in NOT_BILINGUAL:
            continue
        arabic_value = arabic.values[index]
        if arabic_value and arabic_value != merged.get(key):
            merged[f"{key}_ar"] = arabic_value

    # DERIVED, never read twice. `Is Saudi Contractor` is the same fact as
    # `Membership Type` and the owner asked for both; computing it here means
    # the two can never disagree.
    membership = merged.get("membership_type", "")
    if membership:
        merged["is_saudi_contractor"] = str(
            "non" not in membership.lower()).lower()

    if english.latitude is not None:
        merged["latitude"] = str(english.latitude)
        merged["longitude"] = str(english.longitude)
    return merged
