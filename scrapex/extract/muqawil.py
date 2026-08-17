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
from collections.abc import Iterable
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from .html_table import InferredField, TableCandidate
from .models import MAX_TABLE_ROWS

#: Where a card sits, in the same shape `html_table.py` writes for a `<table>`
#: (`table#id::row(1)`). It is stored on every record as `source_locator`, so it
#: has to name something a person could go and look at.
_LOCATOR = "div.section-card"

#: The CARD fields muqawil publishes in both languages, and the fourth thing
#: that had to stop being decided per page. Emitting `_ar` only where an Arabic
#: value happened to be found made the column list depend on which contractors
#: that page's Arabic half showed — and the listing reorders, so 118 pages in
#: 119 were refused as a different schema. Which fields the SITE translates is a
#: fact about the site, so it is declared here beside `PROFILE_FIELDS`, and an
#: absent value is a NULL in a column that is always there.
#:
#: Measured: these differ between locales. `contractor_id`, `logo_url`, the two
#: rating numbers, the membership number, the classification grade and the two
#: contractor counts read identically, so none of them earns a second column.
BILINGUAL_CARD_FIELDS = (
    "company_name", "membership_level", "contractor_classification",
    "card_company_size", "card_status", "card_city_region",
    "card_training_credit_hours",
)

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

        boxes = _boxes(card)
        for name, value in boxes[:-1]:
            row[f"card_{_slug(name)}"] = value

        # THE CLASSIFICATION PUTS ITS DATA IN THE LABEL, which is the reverse of
        # every other box on the card: `.info-name` reads `Second Classified`
        # and `.info-value` reads `2`. Slugging the name gave a DIFFERENT field
        # key per grade — `card_second_classified`, `card_fifth_classified` — so
        # every page produced a different schema and the second page approved
        # was refused with ExtractionConflict. Found by running it over the real
        # crawl; no fixture of one page could have shown it.
        #
        # TAKEN BY POSITION, and verified over 800 real cards: the last box is a
        # classification on every one of them, whether the card carries seven
        # boxes or eight. Position is also the only key that is language-neutral
        # — the label is the data here, so it cannot be matched against.
        if boxes:
            name, value = boxes[-1]
            row["contractor_classification"] = name
            row["contractor_classification_grade"] = value
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
    return _candidate_from(read_listing(html), table_index=table_index)


def _candidate_from(rows: list[dict[str, str]], *,
                    table_index: int = 0) -> TableCandidate:
    """Rows already read, in the shape the approval path speaks."""
    if not rows:
        return TableCandidate(
            table_index=table_index, name="contractors", locator=_LOCATOR,
            fields=(), rows=(), confidence=0.0,
            warnings=("No contractor cards on this page.",),
            approvable=False, truncated=False)

    # THE UNION, NOT THE FIRST ROW'S KEYS. A contractor with no rating carries
    # no rating keys at all, so keying the schema off row one would drop a
    # column for every contractor after it that happened to have one.
    #
    # AND ORDERED DETERMINISTICALLY, which cost 105 pages of 120 before it was
    # done. First-seen order depends on which card came first, and 55 cards in
    # 800 carry seven boxes rather than eight — so a page whose thin card led
    # produced the SAME FIELDS IN A DIFFERENT ORDER. `_schema_payload` puts
    # `position` in the hash, so that is a different schema, and every page
    # after the first was refused with ExtractionConflict. The fields were
    # identical; only their order was not.
    #
    # A fixed lead for the ones a reader looks for first, then sorted. Column
    # order on screen is `display_order`'s business and the owner's to set;
    # this only has to be the SAME every time.
    lead = ["contractor_id", "company_name", "membership_level", "logo_url",
            "customer_rating_score", "customer_rating_count",
            "contractor_classification", "contractor_classification_grade"]
    present = {key for row in rows for key in row}
    names = [key for key in lead if key in present]
    names += sorted(present - set(names))

    fields = tuple(
        InferredField(
            field_key=name, source_name=name, data_type="text",
            # ALWAYS TRUE, NEVER MEASURED, and this was the third and last
            # page-property that leaked into a dataset-wide schema. Computed
            # per page it read False where that page happened to be complete
            # and True where it was not — and `_schema_payload` puts it in the
            # hash, so 50 pages in 60 were refused as "a different schema" with
            # identical fields in identical order. Nullability is a fact about
            # the DATASET: any page may carry a contractor with a gap, so the
            # only answer one page can honestly give is yes.
            nullable=True,
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

@dataclass(frozen=True)
class Uniqueness:
    """What a run of contractors says about a field that ought to be unique."""

    field_key: str
    checked: int
    #: contractor ids whose value is missing entirely.
    blank: tuple[str, ...] = ()
    #: value -> the contractor ids sharing it. Empty when the rule holds.
    repeated: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def holds(self) -> bool:
        return not self.repeated and not self.blank

    def summary(self) -> str:
        if self.holds:
            return (f"{self.field_key}: unique across {self.checked:,} "
                    "contractors, none blank")
        parts = [f"{self.field_key}: {self.checked:,} checked"]
        if self.blank:
            parts.append(f"{len(self.blank):,} blank")
        if self.repeated:
            worst = max(self.repeated.items(), key=lambda kv: len(kv[1]))
            parts.append(f"{len(self.repeated):,} value(s) shared by more than "
                         f"one contractor, worst {worst[0]!r} on "
                         f"{len(worst[1])} of them")
        return " · ".join(parts)


def check_unique(rows: Iterable[dict[str, str]], *,
                 field_key: str = "card_membership_number",
                 identity: str = "contractor_id") -> Uniqueness:
    """Count what shares a value that the owner says nothing should share.

    THE OWNER SUPPLIED THE RULE AND THE DATA PROVED IT, in that order. He said
    the membership number does not repeat; measured over the 11,059 contractors
    of the first full crawl it was unique with none blank. Without his sentence
    a repeat would have looked like ordinary data — which is exactly why this
    exists: the rule is not discoverable from the rows.

    IT COUNTS AND REPORTS. IT DOES NOT RAISE. A duplicate is not necessarily
    ScrapeX's fault — the site may publish one, or a page may have shifted under
    a crawl that took three hours — and refusing an eleven-thousand-row dataset
    over one repeat would throw away a good crawl to punish a bad row. This
    belongs beside the data, not in front of it.

    ACROSS PAGES, WHICH IS THE ONLY LEVEL IT MEANS ANYTHING AT. A listing page
    holds twenty rows; a repeat inside one is almost impossible and a repeat
    across 865 of them is the case worth catching. So it takes rows, not a page.
    """
    seen: dict[str, list[str]] = {}
    blank: list[str] = []
    checked = 0
    for row in rows:
        checked += 1
        who = str(row.get(identity) or "")
        value = str(row.get(field_key) or "").strip()
        if not value:
            blank.append(who)
            continue
        seen.setdefault(value, []).append(who)
    return Uniqueness(
        field_key=field_key, checked=checked, blank=tuple(blank),
        # A value on the SAME contractor twice is a page read twice, not a
        # collision — the rule is about two contractors, so the ids are deduped
        # before the count.
        repeated={value: tuple(sorted(set(ids)))
                  for value, ids in seen.items() if len(set(ids)) > 1})


@dataclass(frozen=True)
class Drift:
    """How much a paginated crawl showed itself the same row twice."""

    pages: int
    rows: int
    distinct: int
    #: contractor id -> how many different pages it turned up on.
    repeated: dict[str, int] = field(default_factory=dict)

    @property
    def reshown(self) -> int:
        """Slots spent on a row that had already been seen."""
        return self.rows - self.distinct

    @property
    def steady(self) -> bool:
        return not self.repeated

    def summary(self) -> str:
        if self.steady:
            return (f"{self.pages:,} pages, {self.rows:,} rows, every one a "
                    "different contractor")
        worst_id, worst_n = max(self.repeated.items(), key=lambda kv: kv[1])
        return (f"{self.pages:,} pages, {self.rows:,} rows, only "
                f"{self.distinct:,} contractors — {self.reshown:,} slots were "
                f"re-showings, {len(self.repeated):,} contractors seen twice or "
                f"more, worst {worst_id} on {worst_n} pages. The listing moved "
                "under the crawl, so an unknown number of contractors were "
                "never shown at all.")


def check_drift(paged_rows: Iterable[tuple[int, dict[str, str]]], *,
                identity: str = "contractor_id") -> Drift:
    """How often the same contractor turned up on more than one page.

    THIS IS ABOUT THE CRAWL, NOT THE DATA, and the two must not be reported
    together. `check_unique` deliberately treats one contractor read twice as
    one contractor — which is right, and was proved right: over the first full
    crawl, 4,556 contractors appeared more than once and EVERY COPY WAS
    BYTE-IDENTICAL. Not one differing field, not one membership number shared by
    two companies, not one company carrying two numbers. So the repeats are not
    bad data at all; they are one row read from two places.

    WHICH IS THE WORSE FINDING. A listing that reorders under a crawl does not
    only repeat — it also SKIPS. A contractor that slid from page 42 to 41 is
    read twice; the one that slid from 41 to 42 is never read at all. Measured
    on 2026-08-16: 865 pages of twenty offered 17,300 slots, 6,241 of them went
    to a row already seen, and 11,059 contractors came back. How many were
    missed is not knowable from the crawl itself.

    So this counts what CAN be seen — the repeats — because they are the visible
    half of an invisible loss, and a crawl that reported 17,275 rows with no
    further comment would read as a complete one.
    """
    pages: set[int] = set()
    seen: dict[str, set[int]] = {}
    rows = 0
    for page, row in paged_rows:
        rows += 1
        pages.add(page)
        who = str(row.get(identity) or "")
        if who:
            seen.setdefault(who, set()).add(page)
    return Drift(
        pages=len(pages), rows=rows, distinct=len(seen),
        repeated={who: len(where) for who, where in seen.items()
                  if len(where) > 1})


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


def bilingual_listing_candidate(english: str, arabic: str, *,
                                table_index: int = 0) -> TableCandidate:
    """One listing page in both languages, as one candidate with `_ar` columns.

    THIS IS WHAT LIGHTS THE TOGGLE. `dataset_table_payload` derives
    `payload.bilingual` from any field ending `_ar` that has a partner without
    it, and `grid.js` flips exactly those. Until a row carries both halves the
    toggle has nothing to flip, which is why an English-only approval produces a
    table with no language switch at all.

    MERGED BY CONTRACTOR ID, NEVER BY POSITION. `en?page=5` and `ar?page=5` are
    two separate requests against a listing that reorders every thirty seconds —
    measured: 4,556 of 11,059 contractors turned up on more than one page in a
    single pass. Zipping the two pages row by row would therefore attach one
    company's Arabic name to another company's English one, and the result would
    look perfectly reasonable. A contractor the Arabic page did not happen to
    show simply keeps its English half.

    AND A PAIR IS ONLY KEPT WHEN THE TWO DIFFER, which is the same rule
    `merge_locales` applies to profiles. `contractor_id`, the rating counts and
    the membership number read identically in both, and a second column holding
    the same string costs a cell in every row of eleven thousand and says
    nothing.
    """
    english_rows = read_listing(english)
    arabic_rows = {row["contractor_id"]: row for row in read_listing(arabic)}

    merged: list[dict[str, str]] = []
    for row in english_rows:
        both = dict(row)
        other = arabic_rows.get(row["contractor_id"], {})
        # EVERY declared pair, every row — present or not. See
        # BILINGUAL_CARD_FIELDS: a column that appears only when a value was
        # found is a column that appears only on some pages.
        for key in BILINGUAL_CARD_FIELDS:
            value = other.get(key) or ""
            both[f"{key}_ar"] = value if value != row.get(key) else ""
        merged.append(both)
    return _candidate_from(merged, table_index=table_index)
