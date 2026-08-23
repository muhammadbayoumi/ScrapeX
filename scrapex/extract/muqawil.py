"""Reading one contractor off muqawil.org's pages.

Step 2 of the contractor plan, and it sits BESIDE `html_table.py` rather than
replacing it: a profile page carries five real `<table>` elements — the licences
and their readiness, the two contractor lists, the SELF-BUILD PRICE SCHEDULE and
the contract counts — and those go through `detect_html_tables` exactly as any
other site's would.

CORRECTED 2026-08-22, because that sentence named the technical rating as the
fifth table for months and there is no such table. Measured over 2,419 real
profile pairs: `div#contractor-tab4`, the pane the tab button `التقييم الفني`
points at, holds ZERO tables on 2,360 of 2,360 pages. The fifth table is the
self-build price schedule, in a `section-card` of its own — see `PROFILE_CARDS`. What this file reads is everything that is NOT a table, which on a
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

import hashlib
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

#: EVERY FIELD A LISTING CARD CAN CARRY, declared rather than derived — and the
#: reason is the same one `BILINGUAL_CARD_FIELDS` above states for the `_ar` half,
#: applied to the half it did not cover.
#:
#: THE FAILURE THAT FORCED IT, measured 2026-08-21 on the first partitioned crawl:
#: 897 stored page-pairs went through the approval path and **74 were accepted and
#: 823 refused** with `ExtractionConflict`. 74 is not a round number — it is
#: `region_id=0`'s four cells, `1 + 4 + 10 + 59`. And `region_id=0` IS the 1,438
#: contractors who publish no location, so their cards carry no location box:
#:
#:     region_id=0 & company_size=big   21 fields, no card_city_region
#:     region_id=1 & company_size=big   22 fields
#:
#: Those 74 pages taught the dataset a 21-field schema and every located
#: contractor's page after them was refused for having one more column.
#:
#: THE CAUSE IS THE PARTITION, WHICH IS WHY DERIVING THE LIST CANNOT WORK. The old
#: unfiltered crawl mixed every kind of contractor onto every page, so the union of
#: a page's cards always held every field and the schema was stable across 864
#: pages. A partition **groups like with like** — that is exactly what makes a cell
#: provably complete — so the first cell is systematically unrepresentative. The
#: property that makes the crawl trustworthy makes a per-page field list wrong.
#:
#: MEASURED ACROSS PAGE 1 OF EVERY CELL: 15 fields, of which 14 appear wherever
#: there is a card at all and only `card_city_region` varies (58 of 64 pages). One
#: cell — `region_id=8 & company_size=big` — publishes no contractors whatsoever,
#: so a derived list would be EMPTY there.
#:
#: An absent value is now a NULL in a column that is always there, which is what
#: the bilingual note already says and what the owner's ~70 columns need: a column
#: count that does not depend on which twenty contractors a page happened to show.
CARD_FIELDS = (
    "contractor_id", "company_name", "membership_level", "logo_url",
    "customer_rating_score", "customer_rating_count",
    "contractor_classification", "contractor_classification_grade",
    "card_city_region", "card_city", "card_region",
    "profile_url", "profile_url_ar",
    "card_company_size", "card_main_contractor",
    "card_membership_number", "card_status", "card_sub_contractor",
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

#: Where a profile's non-table facts sit, in the same shape `_LOCATOR` names for a
#: card. A profile has no repeating row, so the locator is the page's own info block.
_PROFILE_LOCATOR = "div.info-box"

#: EVERY FIELD A PROFILE PAGE CAN CARRY, declared for the reason `CARD_FIELDS` is:
#: a page that happens to omit a box must not produce a different schema, or the
#: second profile approved is refused and the crawl stops at one.
#:
#: MEASURED on the two committed fixtures, `merge_locales` producing 20 keys: the
#: eleven labelled boxes, their five Arabic halves, the two coordinates, the decoded
#: email and the Saudi-contractor flag. `contractor_id` LEADS because it is the
#: identity and the listing already uses it as one — a profile row that could not be
#: joined to its listing row would be a second table about the same company.
#:
#: WHAT IS NOT HERE, and it is most of his 48. The profile carries **five real
#: `<table>` elements** — the licences and their readiness, the two contractor lists,
#: the technical rating, the contract counts — and those go through
#: `detect_html_tables` like any other site's tables. They are the multi-valued groups
#: `R-19` rules belong in CHILD tables, not columns, so they are deliberately absent
#: from this list rather than forgotten.
PROFILE_FIELD_ORDER = (
    "contractor_id",
    "membership_number", "membership_type", "membership_type_ar",
    "member_since", "is_saudi_contractor",
    "company_size", "company_size_ar",
    "training_credit_hours", "training_credit_hours_ar",
    "city", "city_ar", "region", "region_ar", "address",
    "activity", "activity_ar",
    "organization_mobile_number", "organization_email",
    "latitude", "longitude",
    # SIX MORE, MEASURED 2026-08-22 over 2,419 real profile pairs and NOT on the
    # info box -- which is why a count of the info box's labels said the profile
    # was fully read when three of its seven cards had no reader at all.
    #
    # `R-31` is what makes adding them safe rather than a migration: every field
    # already approved is still here, so `_retire_or_refuse` opens schema version 2
    # and the 704 rows approved under version 1 keep theirs. A field REMOVED would
    # be refused, and that is the direction that matters.
    #
    # THE PRICES LEAD THE NEW ONES because they are a price, and this is a
    # price-tracking warehouse: `self_build_price_*` is what a contractor charges
    # per square metre under the self-build programme, and nothing in this
    # repository had a column for it.
    "commercial_registration",
    "self_build_price_under_five_projects",
    "self_build_price_five_to_ten_projects",
    "self_build_price_over_ten_projects",
    "model_contract_count", "registered_contract_count",
)

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


#: A profile page carries seven `section-card` elements, sometimes eight or nine;
#: the contractors LISTING carries twenty-two. Measured over 300 real profile
#: snapshots: 7 x262, 8 x33, 9 x4, and one 22 that was the listing served in a
#: profile's place. Nothing was observed between 9 and 22, so the threshold sits
#: in an empty gap rather than on a guess.
LISTING_SHAPED = 15


class PageIsNotAProfile(ValueError):
    """The site answered a profile request with a different document.

    WHY THIS IS AN EXCEPTION AND NOT A NULL. muqawil answers an id that no longer
    resolves with **the contractors listing**, at HTTP 200 and 375 KB where a
    profile is 122 KB. Nothing downstream can tell: `read_profile` finds none of
    `PROFILE_FIELDS`' labels, emits nulls for all of them, and the membership
    number leaks through from the first card on that listing — so fourteen
    contractors ended up carrying a stranger's membership number, thirteen of
    them the SAME stranger's. The rows looked ordinary: 18.0 populated fields
    against 18.2 on healthy ones.

    A missing field is a fact about a contractor. A missing DOCUMENT is not, and
    the two must not arrive at the warehouse looking alike. `OP-64`.
    """


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
    """A key from a label, and it must not collapse two labels into one.

    `[a-z0-9]` ONLY, WHICH IS RIGHT FOR AN ENGLISH LABEL AND EMPTY FOR AN ARABIC ONE.
    That emptiness used to fall back to the constant `"unnamed"`, so every Arabic label
    produced the SAME key — measured 2026-08-21 on a real profile: **ten Arabic labels
    collapsed into two keys**, losing eight of them to a silent dict collision.

    Nothing consumes that today, because `merge_locales` pairs the two readings BY INDEX
    and never reads an Arabic label — its docstring says so and that is why the merge is
    correct. But a public attribute that silently drops eight of ten entries is a loaded
    gun for the next caller, and this repository has already paid for exactly this once:
    `DSN-05`, where `_slug` filtering every Arabic label to nothing made
    `card_city_region` absent on the Arabic side and split it into two empty strings for
    every contractor in the country.

    SO A LABEL WITH NO ASCII LEFT GETS A DIGEST OF ITSELF. Stable for the same label,
    distinct for different ones, and not pretending to be readable — a positional
    fallback would shift the moment the site adds a box.
    """
    ascii_only = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    if ascii_only:
        return ascii_only
    if not label.strip():
        return "unnamed"
    return "u" + hashlib.sha256(label.strip().encode("utf-8")).hexdigest()[:10]


def _boxes(soup: BeautifulSoup) -> list[tuple[str, str]]:
    pairs = []
    for box in soup.select(".info-box"):
        name, value = box.select_one(".info-name"), box.select_one(".info-value")
        if name is not None and value is not None:
            pairs.append((_text(name), _text(value)))
    return pairs


def _card_boxes(html: str) -> dict[str, tuple[tuple[str, str], ...]]:
    """Per contractor, that card's boxes in PAGE ORDER, as `(field_key, value)`.

    WHY THIS EXISTS, and it is the fourth leak's twin. `read_listing` keys a
    card's boxes by `card_{_slug(label)}`, and `_slug` keeps `[a-z0-9]` only —
    so on the ARABIC page every label filters down to nothing, becomes
    `unnamed`, and all seven boxes collapse into ONE key that the last of them
    wins. Merging the two languages BY KEY therefore asked the Arabic page for
    names it does not have, and `card_city_region_ar`, `card_company_size_ar`,
    `card_status_ar` and `card_training_credit_hours_ar` were empty in all
    11,059 approved rows. The test that should have caught it asserted the
    COLUMN was present rather than that a VALUE had arrived.

    So the boxes come back positional and the module's existing rule applies:
    the English label names the field, the Arabic page contributes a value at
    the same index, and no Arabic label is ever matched against anything. That
    is what `merge_locales` already does for profiles.

    MEASURED BEFORE IT WAS RELIED ON. Across 120 real page pairs, 2,360 cards
    appeared in both languages, and the box count agreed on 2,360 of them.

    The last box is dropped because it is the classification, whose LABEL is its
    data — `read_listing` takes that one by position for the same reason.
    """
    boxes: dict[str, tuple[tuple[str, str], ...]] = {}
    for card in BeautifulSoup(html, "html.parser").select("div.section-card"):
        link = card.find("a", href=_PROFILE_HREF)
        if link is None:
            continue
        found = _PROFILE_HREF.search(link["href"])
        boxes[found.group(1)] = tuple(
            (f"card_{_slug(name)}", value) for name, value in _boxes(card)[:-1])
    return boxes




@dataclass(frozen=True)
class MultiValuedGroup:
    """One of `R-19`'s repeating groups, and how to find it on a profile page.

    `R-41`: a group is named by a DECLARED map, never by position and never by its
    heading. The alternatives were measured and all three fail —

        the detector's own name    `Table 1` … `Table 5`, which is position
        the nearest heading        three of the five tables share one, and for two of
                                   them the nearest heading is a TAB BUTTON that
                                   belongs to a different section entirely
        the column signature       two tables carry the same `# / الإسم` pair

    THE SELECTOR IS THE DECLARATION, and it is chosen for stability rather than for
    brevity. Where the page gives an id, the id is used: `#contractor-tab2` and
    `#contractor-tab3` are the only thing that separates two tables with identical
    headers and no rows. Where it does not, a header the site does not translate is
    used — see `published_as` below for why that is safe here and would not be
    elsewhere.
    """

    #: Our stable name. Not the site's — the site's is `published_as`.
    key: str
    #: `table` goes through `detect_html_tables`; `tree` is a nested list and does not.
    kind: str
    #: A CSS selector locating the container, resolved with soupsieve.
    selector: str
    #: THE VOCABULARY THIS GROUP POPULATES, in both languages -- and it lives HERE,
    #: beside the group, because a measurement of 2026-08-22 says a group and its
    #: taxonomy are one fact. `ProfileReader` used to carry a single pair for the whole
    #: reader, which was true while `interests` was the only wired group and became a
    #: trap the moment a second arrived: interests publishes 211 English paths and
    #: licences 19, with ZERO exact overlap (`Civil engineering` against `Civil
    #: Engineering`), while their ARABIC ROOTS DO overlap -- and `taxonomy.ensure_path`
    #: is idempotent on the Arabic name. One scheme would have fused the two trees at
    #: the roots and let them diverge below.
    #:
    #: EMPTY MEANS NOT WIRED. A group with no scheme name is declared and unwritten,
    #: which is the state three of the five are in; `contractors.write_groups` refuses
    #: to write one rather than defaulting it.
    #: What the SITE calls it, kept for the record and for a reader comparing with the
    #: page. **Arabic even on the English profile** — measured: every table header and
    #: every contractor tab label is identical in both locales, so a selector built on
    #: this text is locale-stable. That is a property of THIS site and not a rule: the
    #: interests card IS translated (`Interests` / `الأنشطة`), which is why that one is
    #: located structurally instead.
    published_as: str
    #: THE VOCABULARY THIS GROUP POPULATES, in both languages -- and it lives HERE,
    #: beside the group, because a measurement of 2026-08-22 says a group and its
    #: taxonomy are one fact. `ProfileReader` used to carry a single pair for the whole
    #: reader, which was true while `interests` was the only wired group and became a
    #: trap the moment a second arrived: interests publishes 211 English paths and
    #: licences 19, with ZERO exact overlap (`Civil engineering` against `Civil
    #: Engineering`), while their ARABIC ROOTS DO overlap -- and `taxonomy.ensure_path`
    #: is idempotent on the Arabic name. One scheme would have fused the two trees at
    #: the roots and let them diverge below.
    #:
    #: EMPTY MEANS NOT WIRED. A group with no scheme name is declared and unwritten,
    #: which is the state three of the five are in; `contractors.write_groups` refuses
    #: to write one rather than defaulting it.
    scheme_name: str = ""
    scheme_name_ar: str = ""


#: The groups `R-19` asks for, as they are actually published. Measured against
#: `tests/fixtures/muqawil/profile-{en,ar}.html` on 2026-08-21.
MULTI_VALUED_GROUPS: tuple[MultiValuedGroup, ...] = (
    MultiValuedGroup(
        key="interests",
        kind="tree",
        # STRUCTURAL, BECAUSE THIS CARD'S TITLE *IS* TRANSLATED — `Interests` in English
        # and `الأنشطة` in Arabic, which is not even a translation of it. A title-based
        # selector read 25 nodes from one locale and 0 from the other. The card is the
        # one holding the nested list, and `read_interests` refuses if two ever do.
        selector="div.section-card:has(ul.list-numerical li.list-item)",
        published_as="Interests / الأنشطة",
        scheme_name="Interests", scheme_name_ar="الأنشطة"),
    MultiValuedGroup(
        key="licensed_activities",
        kind="table",
        selector='table:has(th:-soup-contains("الأنشطة المرخصة"))',
        published_as="الأنشطة المرخصة",
        # THE SITE PUBLISHES NO ENGLISH NAME FOR THIS VOCABULARY -- the card's title is
        # `التراخيص ومستوى الجاهزية` in both locales -- so the English one is OURS, and
        # the Arabic one is the site's own table header. `ensure_scheme` keys on the
        # Arabic name, which is the half that is not invented.
        scheme_name="Licensed Activities", scheme_name_ar="الأنشطة المرخصة"),
    MultiValuedGroup(
        key="sub_contractors",
        kind="table",
        # THE ID IS THE ONLY THING THAT WORKS HERE. This table and `main_contractors`
        # have the same two headers, `# / الإسم`, and both are EMPTY for the committed
        # contractor — so neither a signature nor a row can tell them apart. The tab
        # button naming this pane reads `المقاولين بالباطن`.
        selector="div#contractor-tab2 table",
        published_as="المقاولين بالباطن"),
    MultiValuedGroup(
        key="main_contractors",
        kind="table",
        selector="div#contractor-tab3 table",
        published_as="المقاولين الرئيسيين"),
    MultiValuedGroup(
        key="contract_counts",
        kind="table",
        selector='table:has(th:-soup-contains("عدد العقود النموذجية"))',
        published_as="عدد العقود النموذجية / عدد العقود المسجلة"),
)

#: WHAT `R-19` NAMES AND THE PROFILE DOES NOT PUBLISH, recorded rather than guessed at.
#:
#: `R-19` lists *"Interests, Licensed Activities, Qualification Programs, Balady
#: Services, contractor relations"*. Measured against the committed profile, two of
#: those five are not on the page at all, and one is two:
#:
#:   * **Qualification Programs** and **Balady Services** appear as LISTING FILTER
#:     axes — `lc_program_list_id` (13 values) and `balady_service_id` (8) — and not as
#:     profile sections. They may be a facet of the search rather than a property of a
#:     contractor, or they may render only for contractors that hold one. One profile
#:     cannot tell those apart, which is `R-19`'s own stated evidence limit.
#:   * **contractor relations** is TWO groups on the page: main contractors and sub
#:     contractors, in separate tabs.
#:   * And the **technical rating** — `contractor-tab4`, `التقييم الفني` — is a tab with
#:     **no table in it** on this profile, so there is nothing to declare a selector for.
#:
#: Kept as a declaration so that "we could not find it" is a recorded fact rather than a
#: silently shorter list, which is how a build ends up covering four of five groups and
#: reporting success.
GROUPS_NOT_LOCATED: tuple[tuple[str, str], ...] = (
    ("qualification_programs",
     "a listing filter axis (lc_program_list_id, 13 values), not a profile section on "
     "the committed contractor"),
    ("balady_services",
     "a listing filter axis (balady_service_id, 8 values), not a profile section on the "
     "committed contractor"),
    ("technical_rating",
     "NOT A GROUP AT ALL, corrected 2026-08-22. The tab button التقييم الفني names "
     "div#contractor-tab4, and that pane holds ZERO tables in its DOM subtree on "
     "2,360 of 2,360 measured pages -- it is a label over an empty pane. The earlier "
     "reading, 'carries no table for this contractor', was measured on one fixture "
     "and read as a property of that contractor; it is a property of the site. The "
     "fifth table on the page is the SELF-BUILD PRICE schedule, in its own "
     "section-card -- see PROFILE_CARDS and read_self_build_prices"),
)

#: WHAT 2,419 PAGES SAID ABOUT THE FOUR GROUPS `write_groups` DEFERRED, and it is
#: recorded here beside the declarations because `R-19` asked for measurement and one
#: fixture was all there was to measure. Counts, not impressions:
#:
#:   licensed_activities  1,685 rows over 228 pages, a CLOSED vocabulary of 22
#:                        distinct activities -> a taxonomy. Built.
#:   contract_counts      92 pages, always exactly one row of two numbers -> two
#:                        columns, which is what `write_groups` already argued.
#:   sub_contractors      2,419 pages carry the table. Rows on TWO of them.
#:   main_contractors     2,419 pages carry the table. Rows on ZERO of them.
#:
#: The last two are the ones a study cannot settle: they are contractor-to-contractor
#: RELATIONS rather than classifications, and 2 rows in 2,419 pages is not enough to
#: design a shape on. They stay declared and unbuilt, and the snapshots keep the
#: evidence, so the day the site fills them in it is a re-parse and not a re-crawl.
GROUPS_MEASURED_EMPTY: tuple[tuple[str, str], ...] = (
    ("sub_contractors", "rows on 2 of 2,419 pages measured 2026-08-22"),
    ("main_contractors", "rows on 0 of 2,419 pages measured 2026-08-22"),
)


def locate_group(html: str, key: str) -> Tag | None:
    """The element one declared group lives in, or `None` if this page has not got it.

    `None` IS AN ANSWER AND NOT A FAILURE. Three of the five declared groups are empty
    for the committed contractor and two of those render no rows at all, so a profile
    without a section is the common case rather than the exception.

    MORE THAN ONE MATCH IS REFUSED, though, because a selector that has stopped being
    unique has stopped being a declaration — and picking the first would read one
    group's values as another's, which is the failure `R-41` exists to prevent.
    """
    group = next((one for one in MULTI_VALUED_GROUPS if one.key == key), None)
    if group is None:
        raise KeyError(
            f"{key!r} is not a declared group. Declared: "
            f"{[one.key for one in MULTI_VALUED_GROUPS]}. Groups R-19 names that this "
            f"profile does not publish: {[name for name, _ in GROUPS_NOT_LOCATED]}")
    found = BeautifulSoup(html, "html.parser").select(group.selector)
    if len(found) > 1:
        raise ValueError(
            f"{key!r} matched {len(found)} elements, so its selector is no longer a "
            f"declaration: {group.selector}. The layout has changed.")
    return found[0] if found else None

#: The interests block is a nested list, and the nesting is the taxonomy. A child `<ul>`
#: is a SIBLING of the `<li>` it hangs under, not its child — so a parent is the nearest
#: preceding `<li>` at one level up, which is what `read_interests` walks.
#:
#: FOUND BY STRUCTURE AND NEVER BY ITS HEADING. The first draft matched the title text
#: `"Interests"`, and it read 25 nodes from the English profile and **0 from the
#: Arabic** — because the Arabic heading is `الأنشطة`, "Activities", not a translation
#: of the English one. Titles are content and they are not parallel between locales;
#: `DSN-05` cost a day to the same class of mistake, where `_slug` filtered every Arabic
#: label to nothing and split a column into two empty strings for every contractor in
#: the country.
#:
#: The list is the thing that identifies the card. Measured on both committed profiles:
#: exactly one `div.section-card` contains `ul.list-numerical` items — 25 of them — and
#: the other two contain none.
_INTEREST_LIST = "div.section-card:has(ul.list-numerical li.list-item)"


def read_interests(html: str) -> tuple[tuple[str, ...], ...]:
    """Every interest as a PATH from root, in document order. One tuple per node.

    WHY THIS EXISTS, AND IT CORRECTS A WRITTEN PREMISE. The plan for `R-19` says the
    five multi-valued groups *"go through `detect_html_tables` like any other site's
    tables"*. Measured against the committed profile: the page holds exactly **five
    `<table>` elements and none of them is Interests**. It is a nested `<ul
    class="list list-numerical">` inside `<div class="section-card">`, under an
    `<h3 class="card-title">Interests</h3>`.

    That matters because interests are the BIGGEST of the five — the `R-19` study
    measured 30 values in 6 groups for one contractor and priced the group at ~235 MB at
    full scale. Building on the five-tables premise would have produced four groups and
    silently missed the largest.

    THE SHAPE IS `classification_node`'S, WHICH IS WHY PATHS AND NOT NAMES. Measured on
    the fixture, three levels deep, and the leaf name is **not unique** — the study found
    `الصرف الصحي` under more than one parent, so an identity built from the leaf name
    merges two different activities. A path is the identity; the name is not.

    EVERY NODE, NOT ONLY THE LEAVES. A taxonomy needs its interior nodes to exist before
    a leaf can reference one, and `Construction of buildings` is both a level-1 node and
    a level-2 node with different children — visible in this one fixture. Returning
    leaves alone would leave the parents to be inferred, which is the guessing this
    function removes.

    IT DOES NOT WRITE ANYTHING. Which storage shape these become is `R-19`'s open
    question — a child dataset referencing `classification_node` is the study's
    recommendation and is **awaiting his ruling**. Reading is what both candidate shapes
    need, so it is what gets built ahead of the decision.
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = [card for card in soup.select("div.section-card")
             if card.select_one("ul.list-numerical li.list-item") is not None]
    if len(cards) > 1:
        # AMBIGUOUS IS NOT A GUESS. Measured today there is exactly one such card in
        # each locale; a page that grows a second numerical list would make "the one
        # with the list" mean two things, and picking the first would read one group's
        # values as another's. The layout moved, and that is a fact the caller needs.
        raise ValueError(
            f"{len(cards)} section-cards carry a numerical list, so the interests "
            "block can no longer be identified by structure. The layout has changed.")
    card = cards[0] if cards else None
    if card is None:
        # ABSENT IS NOT EMPTY, and the caller cannot tell them apart from a tuple — but
        # it can from the count, and a contractor with no interests is a real state. An
        # exception here would make a profile without the section unreadable.
        return ()

    found: list[tuple[str, ...]] = []
    for item in card.select("li.list-item"):
        path = _path_to(item, card)
        if path:
            found.append(path)
    return tuple(found)


def _path_to(item: Tag, card: Tag) -> tuple[str, ...]:
    """The ancestry of one `<li>`, root first.

    THE PARENT IS A SIBLING, NOT AN ANCESTOR. The markup nests as

        <ul><li>Civil engineering</li>
            <ul><li>Construction of roads and railways</li>
                <ul><li>…</li></ul></ul></ul>

    so the `<ul>` holding a child sits BESIDE the `<li>` it belongs to. Walking
    `parents` alone therefore finds the right depth and never the right names: it would
    report every leaf as a child of nothing. Each step up takes the enclosing `<ul>` and
    then its nearest preceding `<li>` sibling, which is the node it hangs under.
    """
    name = item.find(string=True, recursive=False)
    name = (name or "").strip()
    if not name:
        return ()
    path = [name]
    node: Tag | None = item
    while True:
        holder = node.find_parent("ul")
        if holder is None or not _within(holder, card):
            break
        parent_item = holder.find_previous_sibling("li")
        if parent_item is None:
            break
        parent_name = parent_item.find(string=True, recursive=False)
        parent_name = (parent_name or "").strip()
        if parent_name:
            path.append(parent_name)
        node = parent_item
    return tuple(reversed(path))


def _within(node: Tag, card: Tag) -> bool:
    return any(one is card for one in node.parents)

# ---- the cards, which he warned are not the same on every page ---------------

#: EVERY CARD A PROFILE PUBLISHES, and a DECLARATION rather than a comment
#: because of what he said on 2026-08-22, in the middle of this measurement:
#:
#:     «المعلومات غير ثابته ولا متفقثة بين الصفح يعنى ممكن تلاقى معلومات تانية
#:      وطريقة عرض مختلفة»
#:
#: The information is neither fixed nor consistent between pages; you may find
#: other information and a different presentation. He was right, and this file was
#: wrong in three places at once. What follows was MEASURED over 2,419 real profile
#: pairs off the running crawl, not read off the two committed fixtures.
#:
#: THE THREE CORRECTIONS, each of which was a written premise somewhere:
#:
#:   1. This module's own docstring says the five tables are "the licences and
#:      their readiness, the two contractor lists, THE TECHNICAL RATING and the
#:      contract counts". There is no technical-rating table. The tab labelled
#:      التقييم الفني -- div#contractor-tab4 -- holds ZERO tables in its DOM
#:      subtree on 2,360 of 2,360 pages, and the fifth table is the SELF-BUILD
#:      PRICE schedule, which no document in this repository named.
#:   2. GROUPS_NOT_LOCATED records the technical rating as "carries no table for
#:      this contractor" -- true of the fixture, and true of every page measured.
#:      It is not a group at all: the button is a label over an empty pane.
#:   3. The price table was mis-attributed to that pane by a REGEX that chunked
#:      from id="contractor-tab4" until the next tab id. On a page whose pane is
#:      empty, that chunk runs on into the next card -- so the price table read as
#:      "inside tab4" while its real ancestry is
#:      div.table-responsive < div.section-card < div.col-12. A PANE IS A DOM
#:      SUBTREE AND NOTHING ELSE, which is the lesson _INTEREST_LIST learned about
#:      headings, arriving from the other side.
#:
#: AND THE CARD TITLES ARE NOT ALL TRANSLATED, which is why `titles` is a tuple.
#: Interests/الأنشطة and Map/الموقع are translated; التراخيص ومستوى الجاهزية and
#: العقود سعر البناء (برنامج البناء الذاتي) print in ARABIC on the English page,
#: which is exactly what makes a title-based selector locale-stable for those two
#: -- the same property MultiValuedGroup.published_as already records.
@dataclass(frozen=True)
class ProfileCard:
    """One card the profile publishes, by every title the site prints for it."""

    #: Our stable name for it.
    key: str
    #: Every spelling seen, both locales. A title-based selector uses these.
    titles: tuple[str, ...]
    #: `table`, `list` or `text` -- what a reader has to go through to reach it.
    carries: str
    #: The measured share of pages that publish it, kept as evidence rather than
    #: as a promise: these are counts off 2,419 pairs, not a guarantee.
    on_pages: str


PROFILE_CARDS: tuple[ProfileCard, ...] = (
    ProfileCard(key="contractor_relations", titles=("(no card-title)",),
                carries="table",
                on_pages="2,419 of 2,419 -- the two tab tables, rows on 2"),
    ProfileCard(key="contract_request", titles=("Contract Request", "طلب تعاقد"),
                carries="text", on_pages="2,419 of 2,419"),
    ProfileCard(key="licensed_activities", titles=("التراخيص ومستوى الجاهزية",),
                carries="table", on_pages="2,419 of 2,419, rows on 228"),
    ProfileCard(key="self_build_prices",
                titles=("العقود سعر البناء (برنامج البناء الذاتي)",),
                carries="table", on_pages="713 of 2,419, rows on 163"),
    ProfileCard(key="contract_counts",
                titles=("Previous Projects", "المشاريع السابقة"),
                carries="table", on_pages="92 of 2,419, always exactly one row"),
    ProfileCard(key="interests", titles=("Interests", "الأنشطة"),
                carries="list", on_pages="2,419 of 2,419"),
    ProfileCard(key="map", titles=("Map", "الموقع"),
                carries="text", on_pages="2,419 of 2,419"),
)

#: THE HEADING LEVEL IS NOT FIXED, and asking for the wrong one hides a card. The
#: first census of card titles asked for `h3.card-title` and `h2.card-title`,
#: reported two titles per page and MISSED the price card entirely -- its heading
#: is an `h4`. So every level is asked for, and the level is never named.
_CARD_TITLE_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def _card_title(card: Tag) -> str:
    """What the page calls this card, or `(no card-title)` for the one with none."""
    head = card.find(_CARD_TITLE_TAGS, class_="card-title")
    return _text(head) if head is not None else "(no card-title)"


def _carries_data(card: Tag) -> bool:
    """Whether this card holds something a parser can read out of it."""
    return (bool(card.select("table"))
            or bool(card.select("ul.list-numerical li.list-item")))


def read_cards(html: str) -> tuple[tuple[str, bool], ...]:
    """Every card on the page as `(title, carries data)`, in document order."""
    return tuple(
        (_card_title(card), _carries_data(card))
        for card in BeautifulSoup(html, "html.parser").select("div.section-card"))


def undeclared_cards(html: str) -> tuple[str, ...]:
    """Cards this page publishes, carrying data, that `PROFILE_CARDS` does not name.

    HIS WARNING, MADE MECHANICAL. A parser reads the cards it knows and cannot tell
    a card that is absent from a card nobody declared -- which is how a site grows a
    section and it stays unnoticed for a year. This is the question two fixtures
    could not answer and 2,419 pages can.

    "CARRYING DATA" IS THE FILTER, AND IT BEAT THE OBVIOUS ONE ON MEASUREMENT. The
    contractor's own name is a card too, and its title is different on every page,
    so it must be excluded or the guard reports thousands of unknown cards on its
    first run. Two rules were available:

        by POSITION -- the name card is card 0        wrong on 40 of 5,668 pages
        by CONTENT  -- the name card carries no table wrong on 0 of 5,668 pages

    Measured across both locales: the name card is first on 5,666 of 5,668 pages,
    and on 40 pages an undeclared text-only card appears after the first. Every one
    of those 40 carried neither a table nor a list. So content wins, and position is
    not used at all.

    THE COST OF THAT CHOICE, stated rather than hidden: a NEW TEXT card would not be
    reported, because nothing distinguishes it from the contractor's name. Map and
    Contract Request are text cards, so that is a real blind spot -- it is the
    narrower one, and it is the one with no false positives.

    Not an exception: a new card is news for a person, and raising here would let
    one page's novelty stop the approval of the other 34,833.
    """
    known = {title for card in PROFILE_CARDS for title in card.titles}
    return tuple(title for title, carries in read_cards(html)
                 if carries and title not in known)


def _card(html: str, key: str) -> Tag | None:
    """The card one declared key names, or `None` when this page has not got it.

    MORE THAN ONE IS REFUSED, for the reason `locate_group` states: a title that has
    stopped being unique has stopped being a declaration, and taking the first would
    read one card's values as another's.
    """
    card = next((one for one in PROFILE_CARDS if one.key == key), None)
    if card is None:
        raise KeyError(f"{key!r} is not a declared card. Declared: "
                       f"{[one.key for one in PROFILE_CARDS]}")
    found = [node
             for node in BeautifulSoup(html, "html.parser").select("div.section-card")
             if _card_title(node) in card.titles]
    if len(found) > 1:
        raise ValueError(
            f"{key!r} matched {len(found)} cards, so its title is no longer a "
            f"declaration: {card.titles}. The layout has changed.")
    return found[0] if found else None


# ---- the commercial registration, which was believed to be unavailable -------

#: WHERE THE CONTRACT-REQUEST FORM POSTS. One endpoint, site-wide, identical on all
#: 2,479 pages measured -- and that is the honest answer to `contract_request_url`
#: in CONTRACTOR-SOURCE.md. The plan for this step says that field "has no known URL
#: pattern and is not on the card"; the truth is narrower and more useful. The card
#: IS on every page, and the URL is a CONSTANT rather than a per-contractor value,
#: so it earns no column. What earns a column is what the form carries.
_CONTRACT_FORM = 'form[action*="init_econtract_draft"]'


def read_commercial_registration(html: str) -> str:
    """The contractor's Commercial Registration number, or `""`.

    FOUND IN A PLACE NOBODY LOOKED. `Commercial Registration` appears four times in
    his column study and no extractor had it, because it is not in the info box and
    not on the listing card -- it is the pre-filled `cr` input of the contract
    request form, which every profile publishes.

    MEASURED over 2,543 profile pairs: present on 2,542, always TEN DIGITS, and
    2,542 DISTINCT VALUES OVER 2,542 CONTRACTORS -- no two share one. So it is a
    second natural key for this directory, and the first that is a national
    identifier rather than muqawil's own numbering: it is what a row here could be
    joined to Balady, or to a commercial register, on.

    THE SAME FORM'S `second_party_phone` IS NOT A SECOND PHONE, and it was worth
    measuring rather than assuming. Over 900 pages it is filled on 434, and on every
    one of those it equals `organization_mobile_number` exactly -- 0 differ, 0 carry
    a number the info box lacks. A column for it would hold no new fact.
    """
    form = BeautifulSoup(html, "html.parser").select_one(_CONTRACT_FORM)
    if form is None:
        return ""
    node = form.select_one('input[name="cr"]')
    return (node.get("value") or "").strip() if node is not None else ""


# ---- the self-build prices, which are a PRICE in a price warehouse -----------

#: `label -> field_key` for the three tiers the self-build price card publishes.
#: ARABIC LABELS ON THE ENGLISH PAGE, like every other table header here, so one map
#: serves both locales.
#:
#: MEASURED over 2,419 pairs: exactly these three labels and no fourth, on
#: 161/160/160 pages. The values are numerals with no currency, no thousands
#: separator and no unit -- 466 of 466 parsed as numbers -- and the schedule is NOT
#: always non-increasing across the tiers: 122 contractors quote a non-increasing
#: one and 33 do not. Nothing here may assume a bigger award is cheaper.
SELF_BUILD_PRICE_TIERS: dict[str, str] = {
    "سعر المتر المربع في حال الحصول على أقل من خمسة مشاريع":
        "self_build_price_under_five_projects",
    "سعر المتر المربع في حال الحصول على خمسة حتى عشرة مشاريع":
        "self_build_price_five_to_ten_projects",
    "سعر المتر المربع في حال الحصول على أكثر من عشرة مشاريع":
        "self_build_price_over_ten_projects",
}


class UnknownPriceTier(LookupError):
    """The price card published a row this map does not know.

    RAISED, AND DELIBERATELY, for the reason `CoordinatesMoved` is raised: the
    alternative is a price the site publishes and this warehouse silently does not
    store. A fourth tier is exactly the kind of change worth stopping for, and a
    price-tracking warehouse that drops a price without a word has the one failure
    mode it cannot afford.
    """


def read_self_build_prices(html: str) -> dict[str, str]:
    """The self-build price schedule, `field_key -> value`. `{}` when absent.

    THE ROWS ARE NOT IN A STABLE ORDER -- measured, the same three labels arrive in
    different sequences on different pages -- so this reads them BY LABEL. Position
    would have put the over-ten price in the under-five column on some pages and not
    others, which is the class of defect that never looks wrong in a column count.

    EMPTY IS NOT ABSENT. The card is published on 713 of 2,419 pages and carries
    rows on 163, so a contractor in the self-build programme who has not priced it
    has the card and no rows. Both are real states and neither is an error.
    """
    card = _card(html, "self_build_prices")
    if card is None:
        return {}
    found: dict[str, str] = {}
    for row in card.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
        label, value = _text(cells[0]), _text(cells[1])
        key = SELF_BUILD_PRICE_TIERS.get(label)
        if key is None:
            raise UnknownPriceTier(
                f"the self-build price card published {label!r}, which is not one of "
                f"the three declared tiers. A price this warehouse cannot store is "
                f"worth stopping for: {sorted(SELF_BUILD_PRICE_TIERS)}")
        found[key] = value
    return found


# ---- the contract counts, under a card named for something else --------------

#: `header -> field_key`. THE CARD IS NAMED FOR SOMETHING ELSE, which is why this is
#: keyed on the table's headers and not on the card's title: the card prints
#: `Previous Projects` / `المشاريع السابقة` and its table holds two contract counts.
#: Measured on 92 of 2,419 pages, always exactly one row.
CONTRACT_COUNT_COLUMNS: dict[str, str] = {
    "عدد العقود النموذجية": "model_contract_count",
    "عدد العقود المسجلة": "registered_contract_count",
}


def read_contract_counts(html: str) -> dict[str, str]:
    """The two contract counts, `field_key -> value`. `{}` when the card is absent.

    TWO SCALARS, WHICH IS WHY THEY ARE COLUMNS AND NOT A GROUP. `write_groups`
    already recorded that reasoning -- "putting them in a link table would make a
    membership out of a count" -- and the corpus agrees: one row, two numbers, on
    every page that publishes the card at all.
    """
    card = _card(html, "contract_counts")
    if card is None:
        return {}
    table = card.select_one("table")
    if table is None:
        return {}
    keys = [CONTRACT_COUNT_COLUMNS.get(_text(cell)) for cell in table.select("th")]
    found: dict[str, str] = {}
    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) != len(keys):
            continue
        for key, cell in zip(keys, cells, strict=True):
            if key is not None:
                found[key] = _text(cell)
    return found


# ---- the licences, and the split rule that was never provable before ---------

#: THE LANGUAGE BOUNDARY IS THE FIRST LATIN LETTER, not a separator. Measured over
#: 1,500 rows: the script-run signature of every activity cell is `AL` and nothing
#: else -- 1,500 of 1,500, one transition, Arabic then Latin.
_FIRST_LATIN = re.compile(r"[A-Za-z]")

#: THE DASH IS THE HIERARCHY SEPARATOR, which is what makes it dangerous.
#: `write_groups` records the activity cell as carrying "BOTH languages in one
#: string with no separator" and concludes that splitting "needs a script-boundary
#: rule". The script-boundary half is right; the "no separator" half hid the real
#: trap. There ARE dashes in the cell, they sit INSIDE each language, and they
#: separate LEVELS: تشييد المباني - تشييد المباني - جميع الأنواع is a three-level
#: path. A parser that split the cell on the dash would have cut a path into pieces
#: and called each piece a language.
#:
#: BOTH DASHES, because the site mixes them inside one cell:
#: `Construction of Buildings - Construction of Buildings – All Types` uses a
#: hyphen and then an en dash.
_PATH_SEPARATOR = re.compile(r"\s+[-–—]\s+")

#: The readiness cell, when there is one: `أساسي | Basic` -- both languages, one
#: pipe. Measured EMPTY on 1,490 of 1,500 rows, with five distinct values across the
#: other ten: Gold, Silver, Dimond (the site's spelling) and Basic.
_READINESS_SEPARATOR = " | "


@dataclass(frozen=True)
class LicensedActivity:
    """One licensed activity, as a path in each language, plus its readiness."""

    #: The path, root first, off the Arabic half. THE IDENTITY, always present.
    arabic: tuple[str, ...]
    #: The same path off the English half -- or `()` when the site's own two halves
    #: disagree about how many levels there are. See `read_licensed_activities`.
    english: tuple[str, ...]
    readiness_ar: str = ""
    readiness_en: str = ""
    #: WHAT THE SITE CALLS THE READINESS COLUMN, read off the table's own header
    #: rather than declared as a constant. `R-45`: «ما يقوله الموقع هو مصدر الحقيقة
    #: الوحيد لا نعدل عليه» -- so if muqawil renames that column, the warehouse
    #: carries the new name instead of asserting the old one. Measured today:
    #: `مستوى الجاهزية`, identical on both locales.
    readiness_label: str = ""
    #: The cell exactly as published, kept so a disagreement can be looked at.
    published_as: str = ""

    @property
    def paired(self) -> bool:
        """Whether the two halves agreed. `False` is the SITE's defect, not ours."""
        return bool(self.english)


def read_licensed_activities(html: str) -> tuple[LicensedActivity, ...]:
    """Every licensed activity on the page, in document order.

    THIS IS THE GROUP `write_groups` DEFERRED, and its stated reason has expired:
    "Six samples, one malformed, is not enough to declare that rule on." Correct at
    the time. Measured now over 1,685 rows on 2,419 real pages, and the vocabulary
    is CLOSED AT 22 DISTINCT ACTIVITIES -- a taxonomy, which is what `R-38` is for.

    THE SITE'S ENGLISH IS WRONG ON 100 ROWS, AND A COUNT CATCHES ALL THREE CASES.
    Splitting each half on the path separator and comparing the number of levels:

        1,585 of 1,685 rows  the two halves agree, level for level
           70 rows           Arabic says أعمال تركيبات السباكة والحرارة والتكييف
                             and English says "Construction of Buildings - Medium &
                             Low Rise". A DIFFERENT ACTIVITY, not a translation.
           30 rows           English truncated by the site to "Civil Engineering -",
                             and TWO different Arabic activities truncate to that
                             same string, so it does not even distinguish them.

    So the English half is not trustworthy and the Arabic half is. The load-bearing
    property is luck worth writing down: EVERY ONE OF THE THREE DEFECTS CHANGES THE
    LEVEL COUNT, so nothing has to recognise an activity to detect them, and no row
    can be stored carrying an English name that belongs to a different activity.

    THE ARABIC PATH STANDS ALONE WHERE THEY DISAGREE, rather than the row being
    dropped or the halves zipped to the shorter. Both alternatives were available
    and both are worse: zipping is what `merge_locales` refuses in its own words --
    "a wrong value is worse than a missing one in a table whose whole purpose is to
    be believed" -- and dropping would discard 100 rows of intact Arabic because the
    site cannot spell its own English. `paired` says which happened, so the 100 are
    countable rather than invisible.
    """
    card = _card(html, "licensed_activities")
    if card is None:
        return ()
    # THE LAST HEADER IS THE READINESS COLUMN'S NAME, taken from the page. Two
    # headers are measured on every page -- `الأنشطة المرخصة` and `مستوى الجاهزية`
    # -- and the readiness is the second, which is why the value cells are read
    # from the END of the row too. A table that grows a column keeps both aligned.
    headers = [_text(cell) for cell in card.select("th")]
    label = headers[-1] if len(headers) >= 2 else ""
    found: list[LicensedActivity] = []
    for row in card.select("tr"):
        cells = row.select("td")
        if len(cells) < 2:
            continue
        published, readiness = _text(cells[-2]), _text(cells[-1])
        boundary = _FIRST_LATIN.search(published)
        if boundary is None:
            # NO LATIN HALF AT ALL. Measured zero times in 1,500 rows, so this is
            # the shape changing rather than one contractor's data -- and the Arabic
            # path is still the identity, so the row is kept rather than refused.
            arabic, english = published.strip(), ""
        else:
            arabic = published[:boundary.start()].strip()
            english = published[boundary.start():].strip()
        arabic_path = tuple(part for part in _PATH_SEPARATOR.split(arabic) if part)
        english_path = tuple(part for part in _PATH_SEPARATOR.split(english) if part)
        ready_ar, _, ready_en = readiness.partition(_READINESS_SEPARATOR)
        found.append(LicensedActivity(
            arabic=arabic_path,
            english=english_path if len(english_path) == len(arabic_path) else (),
            readiness_ar=ready_ar.strip(), readiness_en=ready_en.strip(),
            readiness_label=label if readiness else "",
            published_as=published))
    return tuple(found)


def read_profile(html: str) -> Reading:
    """One profile page, in whichever language it was fetched.

    The labels are returned alongside the mapped fields so the Arabic page can
    be paired to the English one BY INDEX — which is the only pairing that does
    not depend on reading an Arabic label correctly.
    """
    soup = BeautifulSoup(html, "html.parser")

    # THE SHAPE, BEFORE THE FIELDS. See `PageIsNotAProfile`: reading the fields of
    # the wrong document produces a row rather than an error, and a row is what
    # reaches the warehouse.
    cards = len(soup.select("div.section-card"))
    if cards >= LISTING_SHAPED:
        raise PageIsNotAProfile(
            f"this page carries {cards} section-cards, which is the contractors "
            f"listing and not one contractor's profile — the id it was fetched "
            f"for no longer resolves, and the site answers that with 200")

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

    # THE INFO BOX IS ONE CARD OF SEVEN. Everything above reads `div.info-box` and
    # the inline map script; these three read the cards beside them. They are here
    # rather than in `merge_locales` because none of them is bilingual -- the site
    # prints these labels in Arabic on the English page, so there is no second value
    # to attach, and `merge_locales` pairs by INDEX over `labels`, which these never
    # enter.
    registration = read_commercial_registration(html)
    if registration:
        fields["commercial_registration"] = registration
    fields.update(read_self_build_prices(html))
    fields.update(read_contract_counts(html))

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

        # DSN-05 · ONE CELL HOLDS TWO FACTS, and his request to separate them was
        # not met while a column count called it done. The card publishes city and
        # region together — `"RIYADH - Riyadh"`, and in Arabic `"الرياض - الرياض"`
        # where the two happen to be the same word.
        #
        # THE PUBLISHED VALUE IS KEPT. `card_city_region` stays exactly as the site
        # wrote it, and the two halves are ADDED beside it, because source truth is
        # never edited — the first rule this project has. A reader who wants to check
        # the split against what the page said still can.
        city, region = _split_city_region(row.get("card_city_region", ""))
        row["card_city"] = city
        row["card_region"] = region

        # DSN-04 · THE PROFILE URL, AND IT IS TAKEN FROM THE CARD RATHER THAN BUILT.
        # The design marks it `u` — "built from the id" — as `/{lang}/contractors/
        # {id}/143`. Measured on the fixture AND on a stored live page: the site
        # writes the href ABSOLUTE, `https://muqawil.org/en/contractors/881/143`. So
        # the host does not have to be invented here, and this parser stays free of a
        # hostname it would otherwise duplicate from `sites/muqawil.py`.
        #
        # THE TAIL IS REBUILT AS `143` AND NOT CARRIED OVER, the same rule
        # `MuqawilPageSource.detail_urls` states: `143` is what makes the self-build
        # price section render at all, and a page that ever links some other value
        # would otherwise store a URL that renders three of his columns empty.
        href = str(link["href"])
        row["profile_url"] = _profile_url(href, "en")
        row["profile_url_ar"] = _profile_url(href, "ar")
        rows.append(row)
    return rows


#: The trailing path segment that makes a profile render its self-build prices.
#: The same literal `sites/muqawil.py` documents, and for the same measured reason:
#: `/881/1` and `/881/999` return the same contractor, but the section
#: `العقود سعر البناء (برنامج البناء الذاتي)` appears only under `143`.
_SELF_BUILD_SEGMENT = "143"


def _profile_url(href: str, locale: str) -> str:
    """This contractor's profile in the named locale, from the card's own href.

    `contract_request_url` IS NOT BUILT HERE, and its absence is deliberate rather
    than an omission. The design marks it `u` as well, but its pattern column in
    `docs/CONTRACTOR-SOURCE.md` is **empty** — no URL pattern is known and the card
    does not carry one. A column filled with a guessed URL is worse than a column
    that is not there: it looks answered.
    """
    found = _PROFILE_HREF.search(href)
    if found is None:
        return ""
    contractor = found.group(1)
    scheme, _, rest = href.partition("://")
    host = rest.split("/", 1)[0] if rest else ""
    if not host:
        # A relative href, which this site does not write today. Kept relative
        # rather than given a host this function has no business choosing.
        return f"/{locale}/contractors/{contractor}/{_SELF_BUILD_SEGMENT}"
    return (f"{scheme}://{host}/{locale}/contractors/"
            f"{contractor}/{_SELF_BUILD_SEGMENT}")


def _split_city_region(value: str) -> tuple[str, str]:
    """`"RIYADH - Riyadh"` into its two halves, whitespace collapsed first.

    THE SEPARATOR IS ONLY RECOGNISABLE ONCE THE WHITESPACE IS GONE. The card writes
    it across lines with a great deal of padding:

        RIYADH
                                    - Riyadh

    SPLIT ON THE FIRST DASH, which assumes no Saudi city name carries one. That held
    for every city seen — RIYADH, JEDDAH, DAMMAM, AL KHOBAR — and `sites/muqawil.py`
    makes the same assumption in `_city_of` for the slice scope, so if a city ever
    does, these are the two lines that will be wrong together.

    A VALUE WITH NO DASH IS ALL CITY AND NO REGION, not a failure: 1,438 contractors
    publish no location at all and arrive here as an empty string, which must give
    two empty strings rather than raise.
    """
    text = " ".join(value.split())
    if not text:
        return "", ""
    city, _, region = text.partition("-")
    return city.strip(), region.strip()


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
                    table_index: int = 0,
                    declared: tuple[str, ...] = CARD_FIELDS,
                    name: str = "contractors",
                    locator: str = _LOCATOR,
                    empty_warning: str = "No contractor cards on this page."
                    ) -> TableCandidate:
    """Rows already read, in the shape the approval path speaks.

    `declared` IS A PARAMETER AND WAS A CONSTANT, and that was a real defect rather
    than a tidiness point. It always led with `CARD_FIELDS` — the LISTING's columns —
    so a profile row put through this came out carrying **17 empty listing columns**:
    measured on the committed fixture, 39 fields where the profile has 20. Every page
    kind has its own declared list, for the reason `CARD_FIELDS` itself exists.
    """
    if not rows:
        return TableCandidate(
            table_index=table_index, name=name, locator=locator,
            fields=(), rows=(), confidence=0.0,
            warnings=(empty_warning,),
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
    # DECLARED, NOT DERIVED. `CARD_FIELDS` is the list and its note carries the
    # measurement that forced it: deriving `present` from this page's own cards made
    # the schema depend on which twenty contractors the page showed, and a partition
    # groups like with like — so 823 of 897 pages were refused. A field the site
    # ADDS is still kept, appended after the declared ones, because a new column is
    # news and a parser that silently drops it is how it stays news for a year.
    present = {key for row in rows for key in row}
    names = list(declared)
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
        table_index=table_index, name=name, locator=locator,
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

    # A ZERO IN EITHER HALF IS THE SITE'S "NO PIN", NOT A PLACE. Measured 2026-08-21 on
    # two of 712 Dammam profiles, the page itself publishes
    # `var latlang = { lat: 24.4493518, lng: 0 }` — and both carried the SAME latitude,
    # which is what an unset default looks like. `read_coordinates` is right to report it
    # faithfully; promoting it to a coordinate column is not, because latitude 24.45 with
    # longitude 0 is a point in the Atlantic about 4,000 km from Dammam.
    #
    # ABSENT RATHER THAN CORRECTED, because there is nothing to correct it to. A missing
    # coordinate says "this contractor never placed a pin"; a zero says "this contractor
    # is in the Gulf of Guinea", and a table whose purpose is to be believed cannot say
    # the second.
    if english.latitude is not None and english.latitude and english.longitude:
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

    CONTRACTORS ARE MATCHED BY ID, NEVER BY POSITION ON THE PAGE. `en?page=5`
    and `ar?page=5` are two separate requests against a listing that reorders
    every thirty seconds — measured: 4,556 of 11,059 contractors turned up on
    more than one page in a single pass. Zipping the two pages row by row would
    therefore attach one company's Arabic name to another company's English one,
    and the result would look perfectly reasonable. A contractor the Arabic page
    did not happen to show simply keeps its English half.

    ONE CARD'S BOXES ARE THEN PAIRED BY POSITION WITHIN THAT MATCH, which is a
    different question and the opposite answer — see `_card_boxes`. The order of
    boxes inside a card is the site's template, not its data, and the Arabic
    labels cannot be read as keys at all.

    AND A PAIR IS ONLY KEPT WHEN THE TWO DIFFER, which is the same rule
    `merge_locales` applies to profiles. `contractor_id`, the rating counts and
    the membership number read identically in both, and a second column holding
    the same string costs a cell in every row of eleven thousand and says
    nothing.
    """
    english_rows = read_listing(english)
    arabic_rows = {row["contractor_id"]: row for row in read_listing(arabic)}
    english_boxes, arabic_boxes = _card_boxes(english), _card_boxes(arabic)

    merged: list[dict[str, str]] = []
    for row in english_rows:
        both = dict(row)
        contractor = row["contractor_id"]
        other = arabic_rows.get(contractor, {})
        mine = english_boxes.get(contractor, ())
        theirs = arabic_boxes.get(contractor, ())
        # ONLY WHEN BOTH LANGUAGES PUBLISHED THE SAME NUMBER OF BOXES. A
        # positional pair drawn from lists of different lengths is a value on
        # the wrong field, which is worse than no value; a card that fails this
        # keeps its English half, exactly as an unpaired contractor does.
        aligned = ({key: theirs[index][1] for index, (key, _) in enumerate(mine)}
                   if len(mine) == len(theirs) else {})
        # EVERY declared pair, every row — present or not. See
        # BILINGUAL_CARD_FIELDS: a column that appears only when a value was
        # found is a column that appears only on some pages.
        for key in BILINGUAL_CARD_FIELDS:
            # `aligned` answers for the card's boxes. `other` answers for the
            # three fields read from fixed places in the markup, which never
            # needed a label: the title, the membership badge, the grade.
            value = aligned.get(key) or other.get(key) or ""
            both[f"{key}_ar"] = value if value != row.get(key) else ""

        # DSN-05's ARABIC HALF IS DERIVED FROM THE ALIGNED VALUE, NEVER FROM THE
        # ARABIC ROW, and the difference is the fourth leak all over again.
        # `read_listing` keys a card's boxes by `card_{_slug(label)}`, and `_slug`
        # keeps `[a-z0-9]` only — so on the ARABIC page every label filters down to
        # nothing and `card_city_region` is simply absent from that row. Measured on
        # the committed fixture: `None`. So splitting the Arabic ROW gives two empty
        # strings for every contractor in the country, silently.
        #
        # `both["card_city_region_ar"]` is the value paired BY POSITION just above,
        # which is the only honest source for it — and it is the same reasoning
        # `_card_boxes` was written for.
        city_ar, region_ar = _split_city_region(both.get("card_city_region_ar", ""))
        both["card_city_ar"] = city_ar
        both["card_region_ar"] = region_ar
        merged.append(both)
    return _candidate_from(merged, table_index=table_index)


def bilingual_profile_candidate(english: str, arabic: str, *,
                                contractor_id: str,
                                table_index: int = 0) -> TableCandidate:
    """One contractor's profile, both locales, in the shape the approval path speaks.

    THE MISSING ADAPTER, and it was the only thing missing. `read_profile`,
    `read_email`, `read_coordinates` and `merge_locales` were all built and tested —
    the plan said "nothing extracts a profile page today" and that was wrong. What did
    not exist was the step from a merged reading to a `TableCandidate`, which is what
    puts the 48 columns on the approval path at all.

    `contractor_id` IS PASSED IN, not parsed out. A profile page is reached BY id — the
    crawl builds `/{lang}/contractors/{id}/143` — so the id is what the caller already
    knows, and a page that failed to repeat it in its own body would otherwise produce
    a row with no identity and be refused at approval. The listing's `contractor_id` is
    the same key, which is what lets a profile row join its listing row instead of
    becoming a second table about one company.

    ONE ROW, NOT TWENTY. A listing page holds twenty cards; a profile holds one
    contractor. The approval path does not care — a candidate is rows with named
    columns — but the locator says `div.info-box` rather than `div.section-card`
    because that is where a person would go to look.
    """
    merged = merge_locales(read_profile(english), read_profile(arabic))
    merged["contractor_id"] = str(contractor_id)
    return _candidate_from(
        [merged], table_index=table_index, declared=PROFILE_FIELD_ORDER,
        name="contractor_profiles", locator=_PROFILE_LOCATOR,
        empty_warning="No profile fields on this page.")
