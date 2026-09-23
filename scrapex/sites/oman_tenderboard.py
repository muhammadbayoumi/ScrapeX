"""etendering.tenderboard.gov.om — what Oman's ESNAD vendor register knows about itself.

Studied in `#1004` before a line of this was written; the vocabulary measurements are
`#1004`'s step 1. Every constant here is a measurement, and `docs/GULF-EGYPT-SOURCES.md`
`:295-353` is the record this verified and corrected.

WHY THIS SOURCE IS READ FROM ITS LISTING AND NOTHING ELSE. The register's row carries the
whole record — name, CR number, address, telephone, fax, category, expiry, company type —
so **23,502 firms cost 942 requests -- 471 pages in each of two languages**, one page of fifty at a time. There is no per-firm
fetch in this reader: the three per-firm surfaces (profile, certificate, procurement
activities) all answered a *Security Page* asking for a sign-in, and `#1004` records them
as existing and gated rather than reached.

THE IDENTIFIER IS INSIDE AN HTML COMMENT, and this is the trap that would cost the most.
The register renders eleven cells and labels ten; the second one is

    <!-- <td>0000</td> -->

with its header commented out the same way. `Company Short Name` is fetched, written into
the response, and hidden from every browser -- 50 values a page, 23,502 in the register.
**An HTML parser that strips comments loses the record key**, so `read_rows` uncomments
deliberately and asserts the shape it expects while doing it. The same value appears again,
uncommented, as the argument to the row's own `getProcActivities('0000')`, and the two are
checked against each other.

`S No.` IS NOT A COUNT AND CANNOT BE TRUSTED. Asked for `pageNo=65536` the server answered
**200 with 51 rows** and `S No.` from 3,276,751 to 3,276,800 -- it clamps the rows to the
real last page and computes the label from whatever page was requested. So the only honest
total is the paginator's own `of 471` / `ShowPage(471)`, which `read_last_page` reads twice
and requires to agree. It also means **an out-of-range page is not an empty page**, and a
crawl that stops on "no rows" never stops.

THE CATEGORY CELL HAS NO SEPARATOR. A firm holding several categories gets them
concatenated with nothing between:

    Construction and Maintenance Information Technology Services Pipeline Network
    Construction and Drilling Wells

`docs/GULF-EGYPT-SOURCES.md:353` warned against one comma-separated field; there is no
comma. The cell is decomposed by longest-match against the vocabulary the page publishes
in its own `<select>` -- measured in `#1004` step 1 at **102 of 102 cells decomposing with
zero remainder**, and **22 of 102 firms (21.6%) holding more than one category**. The
vocabulary is read from the page rather than hard-coded here, so a category the site adds
is data and not a code change.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .. import normalize
from ..pagesource import WHOLE, Cell, SliceNotSupported

#: Matches `source_site.source_key`, as `directories.Directory.key` requires.
SITE_KEY = "oman_tenderboard"

BASE_URL = "https://etendering.tenderboard.gov.om"

REGISTER_PATH = "/product/ReportAction"

#: The register, and the taxonomy, are two `eventFlag` values on one route.
REGISTER_EVENT = "RegVendorPublic"
SUBCATEGORY_EVENT = "getSubCategory"

#: The site's own language switch is a query parameter, not a header or a cookie: its
#: `switchLangauge()` rewrites `LTR`<->`RTL` in the current query. Both views return the
#: same fifty firms in the same order, joinable on the CR number -- 50 of 50 on page 1.
LTR = "LTR"
RTL = "RTL"
DIRECTIONS = (LTR, RTL)

#: MEASURED. Every full page held exactly fifty firms, and page 471 held two. No page-size
#: parameter was found, so this is the site's number and not a request of ours.
ROWS_PER_PAGE = 50

#: The eleven cells a data row renders, in order. `sno` is parsed and deliberately
#: discarded -- see the module docstring on why it is not a count.
_CELL_COUNT = 11


class RegisterShapeError(RuntimeError):
    """The register page is not the shape this reader was written against.

    Raises rather than skipping, because a row this reader cannot read is a firm missing
    from a register whose total is known: `#1004` measured 23,502, so a short read is
    detectable and must be reported rather than absorbed.
    """


@dataclass(frozen=True)
class Firm:
    """One register row, carried as it arrived.

    `short_name` is the record key. Measured over the 102 rows held: **unique, and present
    on 102 of 102**, which is why it and not the CR number is the identity -- the CR was
    blank on 1 of 102.

    `cr_number` is the join key between the two language views, and nothing else. The
    record's own instruction (`docs/GULF-EGYPT-SOURCES.md:338`) is to join on it and never
    on row position; the order did match on page 1, which makes that prudence rather than
    a defect observed, and the join is still on the number.

    `address` IS ARABIC IN THE ENGLISH VIEW, for every row on page 1. So `R-12`'s base
    column stays NULL for it and the `_ar` column carries the value -- as a rule here, not
    an exception.
    """

    short_name: str
    #: BLANK FOR AN `عالمية` REGISTRANT, and measured rather than assumed: four
    #: Arabic pages of the owner's first crawl carry a row whose full-name cell is
    #: empty while the English page names it. It is not the record key --
    #: `short_name` is -- so a blank one is a field, like `address`. Issue 1037.
    name: str | None
    cr_number: str | None
    address: str | None
    telephone: str | None
    fax: str | None
    #: The cell exactly as printed, several category names run together. Kept verbatim
    #: because `SR-1` makes the published string the source of truth and the decomposition
    #: ours; `decompose_categories` derives the list beside it, never instead of it.
    category_raw: str
    #: `dd-MM-yyyy` as printed, and blank on 44 of 102 rows. ONE cell serves all of a
    #: firm's categories, so the per-category expiry `docs/GULF-EGYPT-SOURCES.md:353` asks
    #: for is not in the public list at all.
    expiry_raw: str | None
    company_type: str | None


@dataclass(frozen=True)
class CategorySplit:
    """What a category cell decomposed into, and what it could not.

    `remainder` IS THE MEASUREMENT, not an error path to hide. `#1004` step 1 measured 102
    of 102 cells with an empty remainder, on 0.43% of the register; the full rate arrives
    with the crawl, and a non-zero count is what tells anyone the vocabulary drifted.
    """

    names: tuple[str, ...]
    remainder: str


def listing_url(base_url: str = BASE_URL, *, locale: str = LTR, page: int = 1,
                cell: Cell = WHOLE) -> str:
    """One page of the register.

    `pageNo` IS A GET PARAMETER, which is why this reader needs no form post and no
    session: `pageNo=2` answered with S No. 51-100 and a different fifty firms. It also
    makes every URL stable and enumerable, so the repository's URL-keyed resume works here
    unchanged -- unlike Balady, whose detail URL carries a token that is re-minted on every
    response (`scrapex/sites/balady.py`).
    """
    if page < 1:
        raise ValueError(f"page must be at least 1, got {page}")
    if locale not in DIRECTIONS:
        raise ValueError(f"locale must be one of {DIRECTIONS}, got {locale!r}")
    url = (f"{base_url}{REGISTER_PATH}?CTRL_STRDIRECTION={locale}&PublicUrl=1"
           f"&eventFlag={REGISTER_EVENT}&pageNo={page}")
    # A CELL'S PARAMS GO IN ORDER, because the URL is the identity a resume matches on:
    # `snapshotcrawl.already_stored` compares `generic_page_snapshot.source_url`, so two
    # orderings of the same filter would re-fetch every page. `WHOLE` adds nothing.
    for name, value in cell.params:
        url += f"&{name}={value}"
    return url


def subcategory_url(category_code: str, *, direction: str = LTR,
                    base_url: str = BASE_URL) -> str:
    """The subcategories of one category, as XML.

    Measured: it honours `CTRL_STRDIRECTION`, and the two language lists matched in length
    for all twelve categories -- 194 subcategories a language. Twenty-four requests are the
    whole official taxonomy, which is why `docs/GULF-EGYPT-SOURCES.md:368`'s 2021 PDF is
    not the reference any more.
    """
    if not category_code:
        raise ValueError("category_code must not be empty")
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    return (f"{base_url}{REGISTER_PATH}?eventFlag={SUBCATEGORY_EVENT}&PublicUrl=1"
            f"&category={category_code}&CTRL_STRDIRECTION={direction}")


def _text(fragment: str) -> str:
    """A fragment's visible text, through the one module that owns markup.

    `normalize.strip_markup` UNESCAPES ENTITIES, and the hand-rolled version here did
    not: `AL HASSAN ENGINEERING &amp; CO LLC` reached the warehouse with the `&amp;`
    intact, `&quot;` and `&#1593;` likewise, and a `&nbsp;`-only cell read as the
    four-character string `&nbsp;` rather than as empty -- which defeated the
    empty-short-name guard below and stored `&nbsp;` as a firm's record key.

    CLAUDE.md: parsing lives in one `normalize` module. This was the fourth copy of
    tag-stripping in `scrapex/` and the only wrong one; `aramco`, `heidelberg`,
    `magento` and `woocommerce` all import the shared one.
    """
    return normalize.strip_markup(fragment)


def read_categories(html: str) -> dict[str, str]:
    """`{code: name}` from the page's own category `<select>`.

    READ, NOT HARD-CODED. The twelve measured on 2026-09-18 were `C1` `T1` `C2` `I1`
    (suffixed "(Old)" -- a legacy scheme still carrying live rows) and `Z1`..`Z8`; a
    thirteenth is the site's business, not a code change here. `-1` is its `--Select--`
    placeholder and is dropped.
    """
    block = re.search(r'<select[^>]*name="category"[^>]*>(.*?)</select>', html, re.DOTALL)
    if block is None:
        raise RegisterShapeError(
            "the page carries no category select, and it is the only published "
            "vocabulary the category cell can be decomposed against")
    found = {}
    for code, label in re.findall(
            r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', block.group(1), re.DOTALL):
        name = _text(label)
        if code and code != "-1" and name:
            found[code] = name
    if not found:
        raise RegisterShapeError(
            "the category select holds no options besides its placeholder")
    return found


def read_company_types(html: str) -> dict[str, str]:
    """`{code: name}` from the `vendType` select.

    Measured: `0` Local, `1` International, `2` SME, `3` Omani Real Estate Agent,
    `6` Vehicle Contractor, `7` Freelancer. **`4` and `5` are absent**, so the code space
    has holes and nothing here may assume it is dense.
    """
    block = re.search(r'<select[^>]*name="vendType"[^>]*>(.*?)</select>', html, re.DOTALL)
    if block is None:
        raise RegisterShapeError("the page carries no vendType select")
    found = {}
    for code, label in re.findall(
            r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', block.group(1), re.DOTALL):
        name = _text(label)
        if code and code != "-1" and name:
            found[code] = name
    return found


def read_subcategories(xml: str) -> tuple[tuple[str, str], ...]:
    """`((code, name), ...)` from one `getSubCategory` response.

    The endpoint answers `text/xml` with the values and the names as two flat sequences of
    sibling elements rather than nested pairs, so they are zipped by position -- and a
    length mismatch is a shape failure rather than something to truncate past.
    """
    codes = [c.strip() for c in re.findall(
        r"<subCategoryValue>(.*?)</subCategoryValue>", xml, re.DOTALL)]
    names = [_text(n) for n in re.findall(
        r"<subCategoryName>(.*?)</subCategoryName>", xml, re.DOTALL)]
    if len(codes) != len(names):
        raise RegisterShapeError(
            f"the subcategory response carries {len(codes)} value(s) and {len(names)} "
            "name(s); they are paired by position and cannot be")
    return tuple(zip(codes, names, strict=True))


def read_last_page(html: str) -> int:
    """The register's last page, read three independent ways and required to agree.

    THREE READINGS, because this number is the only honest end of the register and
    `S No.` actively lies past it. The paginator carries all three:

      * `<input type='hidden' name='hidMax' value='471'>` -- the site's OWN validation
        source: its `ShowPage()` refuses a page above `hidMax` and says so.
      * `ShowPage(471)` on the Last link.
      * the printed text `of 471`, which is split across two table cells, so the tags
        are stripped before it is read rather than matched through them.

    If the three ever disagree the paginator has changed shape and a crawl must stop
    rather than pick one to believe -- AND AT LEAST TWO MUST BE PRESENT TO AGREE. This
    used to accept whichever readings it happened to find, so one sufficed: with
    `hidMax` and the `ShowPage` link gone, the printed text alone was believed without
    comment. A paginator redesign that printed `Showing 1 of 50` would then have set the
    last page to 50 against a register of 471 and lost some 21,050 firms, silently --
    which is the exact failure the three readings exist to prevent.
    """
    block = re.search(r"<table[^>]*class='Pagination_table'.*?</table>", html, re.DOTALL)
    if block is None:
        raise RegisterShapeError(
            "the page carries no Pagination_table, which is where this register prints "
            "its own total")
    nav = block.group(0)
    readings: dict[str, int] = {}

    hidden = re.search(r"name='hidMax'[^>]*value='(\d+)'", nav) or re.search(
        r'name="hidMax"[^>]*value="(\d+)"', nav)
    if hidden is not None:
        readings["hidMax"] = int(hidden.group(1))

    targets = [int(n) for n in re.findall(r"ShowPage\((\d+)\)", nav)]
    if targets:
        readings["ShowPage"] = max(targets)

    # THE LAST `of N`, NOT THE FIRST. The nav prints more than one `of` when the site
    # shows both a window and a total -- `Showing 1 of 50 of 471` -- and taking the
    # first reads the window as the register.
    printed_totals = re.findall(r"of\s+(\d+)", _text(nav))
    if printed_totals:
        readings["printed"] = int(printed_totals[-1])

    if not readings:
        raise RegisterShapeError(
            "the paginator publishes no total in any of its three forms -- no hidMax, no "
            "ShowPage target and no 'of N'. S No. is computed from the requested page "
            "and cannot stand in for it")
    if len(readings) < 2:
        raise RegisterShapeError(
            f"the paginator publishes its total only once, as {readings}. Three "
            "independent readings are what make this number trustworthy and one cannot "
            "be checked against anything; the paginator has changed shape")
    distinct = set(readings.values())
    if len(distinct) != 1:
        raise RegisterShapeError(
            f"the paginator's readings of the total disagree: {readings}. They must "
            "agree before a crawl trusts any of them")
    total = distinct.pop()
    if total < 1:
        raise RegisterShapeError(f"the paginator declares {total} pages")
    return total


def read_rows(html: str) -> tuple[Firm, ...]:
    """Every firm on one register page, with the commented-out identifier recovered.

    THE UNCOMMENTING IS THE POINT. The record key is inside `<!-- <td>0000</td> -->`, so
    the comment markers are stripped from each row before its cells are split -- and the
    shape is asserted while doing it: exactly one comment per data row, holding exactly one
    cell, and its value equal to the `getProcActivities(...)` argument in the same row.
    Anything else and the assumption behind the uncommenting has stopped being true.
    """
    firms: list[Firm] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        # A DATA ROW IS ONE THAT CARRIES `getProcActivities(`, and the alternative was
        # measured wrong: filtering on a cell count keeps the paginator, which is a `<tr
        # class="rownohover">` wrapping a nested `Pagination_table` and renders NINE cells
        # of its own. On page 1 that is 51 rows passing a cell-count filter and 50 firms.
        # The call is in every one of the 50 in both languages and on page 471, and it is
        # meaningful rather than incidental: it is the firm's own actions cell.
        if "getProcActivities(" not in row:
            continue
        comments = re.findall(r"<!--(.*?)-->", row, re.DOTALL)
        if len(comments) != 1:
            raise RegisterShapeError(
                f"a data row carries {len(comments)} comment(s); the reader recovers the "
                "record key from exactly one, holding the Company Short Name cell")
        if comments[0].count("<td") != 1:
            raise RegisterShapeError(
                "the commented block in a data row does not hold exactly one cell: "
                f"{comments[0].strip()[:120]!r}")
        flat = row.replace("<!--", "").replace("-->", "")
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", flat, re.DOTALL)]
        if len(cells) != _CELL_COUNT:
            raise RegisterShapeError(
                f"a data row has {len(cells)} cells, not the {_CELL_COUNT} this register "
                f"renders: {cells!r}")
        if not cells[0].isdigit():
            # A ROW THAT GOT THIS FAR IS A DATA ROW, so this raises rather than skipping.
            # The comment here used to say "a paginator row wearing a data row's cell
            # count", and that row cannot reach this line: it carries no
            # `getProcActivities(`, which `:315` already requires, and it has nine cells
            # against the eleven `:328` requires. Measured on both shipped fixtures.
            #
            # What the skip actually did was drop real firms in silence. The site
            # printing `1.` instead of `1` emptied the register -- 4 firms to 0, no
            # error -- and the completeness proof cannot see it, because `declared` and
            # `ids` are both computed by THIS reader: zero against zero is "provably
            # complete", and `contractors.mark_departures` then marks every stored Oman
            # row absent on the strength of it.
            raise RegisterShapeError(
                f"a data row's first cell is {cells[0]!r}, which is not the plain "
                f"integer S No. this reader was written against. S No. is discarded, "
                f"but its shape is how a data row is recognised; a row this reader "
                f"cannot read is a firm missing from a register whose total is known. "
                f"Row: {row[:200]!r}")
        short_name = cells[1]
        if not short_name:
            raise RegisterShapeError(
                "a data row carries no Company Short Name, and it is the record key; "
                f"measured present on 102 of 102 rows. Row: {cells!r}")
        # CASE-INSENSITIVELY, AND THAT IS MEASURED RATHER THAN LENIENT. Over 152 rows
        # across four pages and both languages the two copies were identical on 150 and
        # differed only in case on 2 -- `ZYPHARSPH` printed against `zypharsph` in the
        # call, and `ZZZZZZZ` against `zzzzzzz`. Both are the alphabetic keys; a
        # zero-padded numeric one is unaffected. None differed in any other way, so a
        # genuine disagreement still raises.
        echoed = re.search(r"getProcActivities\('([^']*)'\)", row)
        if echoed is not None and echoed.group(1).lower() != short_name.lower():
            raise RegisterShapeError(
                f"the row's commented key {short_name!r} and its activities argument "
                f"{echoed.group(1)!r} disagree beyond case; one of the two has stopped "
                "being the record key")
        # A BLANK FULL NAME IS DATA, NOT A BROKEN PAGE, and refusing it cost 200 firms.
        #
        # This line used to raise. Measured 2026-09-23 over all 942 stored pages of the
        # owner's first crawl: four Arabic pages -- 254, 274, 388, 443 -- carry one row
        # each whose full-name cell is empty, and every one of them is an `عالمية`
        # (international) registrant whose ENGLISH page names it perfectly. The refusal
        # discarded the whole page, and a page is fifty firms.
        #
        # AND A PAGE REFUSED IN ONE LOCALE COSTS BOTH: of the 23,240 records interpreted
        # from that crawl, ZERO lack an Arabic name, because a record is written only
        # when both halves parse. So `CARITOR`, `ECONOMICS`, `PETROLINVEST` and the
        # firms beside them were absent from the warehouse entirely, in a register whose
        # total is known -- 23,520 ids sighted against 23,240 records. Issue 1037.
        #
        # IT IS NOT THE RECORD KEY, which is what makes this safe: `IDENTITY_FIELD` is
        # `short_name` (`extract/oman_tenderboard.py`), `cells[1]`, and the guard above
        # already refuses a row without one. `firm_name` is a payload field beside
        # `address`, which this source's extract already stores NULL by measurement.
        #
        # THE OTHER REFUSALS ABOVE STAY, and that is the whole point of separating them:
        # a first cell that is not an integer, a missing short name, a cell count that
        # is not eleven, and an activities argument that disagrees with the commented
        # key are all evidence that this reader's understanding of the page has broken.
        # A field the site leaves blank for one class of registrant is not.
        firms.append(Firm(
            short_name=short_name,
            name=cells[2] or None,
            cr_number=cells[3] or None,
            address=cells[4] or None,
            telephone=cells[5] or None,
            fax=cells[6] or None,
            category_raw=cells[7],
            expiry_raw=cells[8] or None,
            company_type=cells[9] or None,
        ))
    return tuple(firms)


def decompose_categories(cell: str, vocabulary: dict[str, str]) -> CategorySplit:
    """Split a category cell against the published names, longest first.

    LONGEST FIRST IS NOT A STYLE CHOICE. `Construction and Maintenance` is a prefix of
    nothing, but `Construction of Ports Roads Bridges Railways Dams and Maintenance` shares
    its first word, and `Supply` is a prefix of `Supply and Services (Old)`. Matching
    shortest-first would consume `Supply` out of the longer name and leave a remainder that
    looks like a vocabulary drift when it is only a greedy bug.
    """
    remaining = (cell or "").strip()
    names = sorted(vocabulary.values(), key=len, reverse=True)
    found: list[str] = []
    while remaining:
        for name in names:
            if remaining.startswith(name):
                found.append(name)
                remaining = remaining[len(name):].strip()
                break
        else:
            break
    return CategorySplit(names=tuple(found), remainder=remaining)


def codes_for(split: CategorySplit, vocabulary: dict[str, str]) -> tuple[str, ...]:
    """The category codes behind a decomposition, in the order the cell printed them.

    The codes and not the names, because the names are what the site renders in the
    requested language while the code is the same in both -- so a code is what a stored
    row can be joined on and a name is not.
    """
    by_name = {name: code for code, name in vocabulary.items()}
    return tuple(by_name[name] for name in split.names)


def join_languages(english: tuple[Firm, ...],
                   arabic: tuple[Firm, ...]) -> tuple[tuple[Firm, Firm], ...]:
    """Pair the two views of one page: on the CR number, then on the record key.

    ON THE NUMBER FIRST -- `docs/GULF-EGYPT-SOURCES.md:338` -- AND NEVER ON POSITION. The
    real orders agree, and an order that happens to agree is not a contract.

    THE FALLBACK IS THE RECORD KEY, AND A PROOF RUN OVER 40 REAL PAGES IS WHY. Pairing on
    the CR number alone refused 3 of those 40 pages outright, losing 150 firms to protect
    three. Diagnosed on all three: the firm carries **no CR number in EITHER view** --
    `ATI PROJECT SRL`, `TEN DESIGN FZ LLC`, `VOLTAS OMAN LLC` -- while its counterpart is
    sitting in the Arabic view under the same `Company Short Name`. Every CR present in
    English was present in Arabic on all three pages; nothing was actually unmatched.

    So the fallback is not a weakened guard, it is the identity this module already
    declares: the short name is unique and present on **1,850 of 1,850** firms measured,
    where the CR number is blank on about 2%. A firm neither key can pair is still
    reported rather than dropped -- that is the case worth raising on, and it did not
    occur in 1,850 firms.
    """
    # A REPEATED KEY IN THE ARABIC VIEW IS NEWS, NOT A LAST-WRITE. Built as plain
    # dicts, two Arabic firms sharing a CR number silently kept the later one and the
    # English firm it displaced was paired with the WRONG twin -- carrying another
    # firm's name into its row. `read_ids` keeps duplicates deliberately for this
    # reason; discarding them here was where that news was lost.
    for label, values in (("CR number", [f.cr_number for f in arabic if f.cr_number]),
                          ("record key", [f.short_name for f in arabic])):
        repeated = sorted({v for v in values if values.count(v) > 1})
        if repeated:
            raise RegisterShapeError(
                f"the Arabic view repeats a {label}: {repeated[:6]}. Pairing on it would "
                f"attach one firm's Arabic row to another firm's English row, which is a "
                f"wrong row rather than a missing one")

    by_cr = {firm.cr_number: firm for firm in arabic if firm.cr_number}
    by_key = {firm.short_name: firm for firm in arabic}
    paired: list[tuple[Firm, Firm]] = []
    unpaired: list[str] = []
    for firm in english:
        other = by_cr.get(firm.cr_number) if firm.cr_number else None
        if other is None:
            other = by_key.get(firm.short_name)
        if other is None:
            unpaired.append(firm.short_name)
            continue
        paired.append((firm, other))
    # BOTH DIRECTIONS, because "present in one and not the other" has two of them.
    # Only the English side was checked, so an Arabic firm with no English twin was
    # dropped in silence -- and the two views are two separate requests, so drift
    # between them is the expected case rather than an exotic one.
    matched = {id(other) for _, other in paired}
    orphaned = [firm.short_name for firm in arabic if id(firm) not in matched]
    if orphaned:
        unpaired.extend(orphaned)
    if unpaired:
        raise RegisterShapeError(
            f"{len(unpaired)} firm(s) on this page have no counterpart in the other "
            f"view by CR number or by record key: {unpaired[:6]}. The two views are the "
            "same fifty firms; a firm present in one and not the other is news, not a "
            "row to skip.")
    return tuple(paired)


def read_ids(html: str) -> tuple[str, ...]:
    """Every firm's record key on this page, in published order, keeping duplicates.

    KEEPING DUPLICATES is the protocol's word and it is load-bearing: the sizing
    arithmetic counts what the page published, and de-duplicating here would hide a
    register that repeated a firm rather than report it. Measured over 102 rows there were
    none, which is a reason to watch for one rather than to assume it away.
    """
    return tuple(firm.short_name for firm in read_rows(html))


class OmanPageSource:
    """The pages one cell of this register covers.

    `PageSource` (`scrapex/pagesource.py`), implemented for a listing that is the whole
    record.
    """

    site_key = SITE_KEY

    def __init__(self, *, last_page: int, locales: Iterable[str] = DIRECTIONS,
                 cell: Cell = WHOLE) -> None:
        if last_page < 1:
            raise ValueError(f"last_page must be at least 1, got {last_page}")
        self._last_page = last_page
        self._locales = tuple(locales)
        if not self._locales:
            raise ValueError("a page source with no locale fetches nothing")
        self._cell = cell

    def listing_urls(self, base_url: str) -> Iterable[str]:
        """Every page, in both languages, PAGE BY PAGE rather than language by language.

        THE ORDER IS DELIBERATE, and the reason is muqawil's own
        (`scrapex/sites/muqawil.py`): `LTR p1`, `RTL p1`, `LTR p2`, ... so a run stopped
        half way holds BOTH halves of the pages it reached. Here it is stronger than
        there -- the two views are joined on the CR number to make one row, so an English
        page whose Arabic twin was never fetched yields no rows at all, not half-rows.
        """
        for page in range(1, self._last_page + 1):
            for locale in self._locales:
                yield listing_url(base_url, locale=locale, page=page, cell=self._cell)

    def detail_urls(self, page: Any) -> Iterable[str]:
        """None, and that is this source's shape rather than an omission.

        The listing row carries the whole record -- name, CR number, address, telephone,
        fax, category, expiry and company type -- so 23,502 firms cost 942 requests -- 471 pages in each of two languages and
        no per-firm fetch. The three per-firm surfaces the page does link (the profile,
        the certificate and the procurement activities) all answered a *Security Page*
        asking for a sign-in, so there is no detail URL this crawl may fetch. `#1004` §4.
        """
        return ()

    def belongs_to_slice(self, page: Any, row_index: int, slice_of: str) -> bool:
        """Refused, because no slice scope is offered for this source.

        NOT answered False, which is the distinction `SliceNotSupported` exists for: False
        for every row is an empty crawl that looks like a successful one. The register
        does publish category and company type on the row, so a slice COULD be built here
        later -- but nothing asks for one today, and inventing the mapping from a
        `slice_of` string onto those columns with no caller is the abstraction this
        repository refuses until a second case proves it.
        """
        raise SliceNotSupported(
            f"{SITE_KEY} offers no slice scope; the register is crawled whole in "
            f"{ROWS_PER_PAGE}-row pages (asked for {slice_of!r})")


class OmanPartition:
    """`PartitionedListing` for a register that needs no partition.

    ONE CELL, AND THE MEASUREMENT IS WHY. `Cell` exists because muqawil's listing order
    is a cached random permutation that rolls every 157-282 s, so a page set has to be
    small enough to read inside one generation. This register does not shuffle: page 1
    fetched twice returned the same fifty firms in the same order, with the same record
    keys. So `WHOLE` is the only cell, the exhaustiveness audit has nothing to sum, and
    the empty cell removes the special case rather than adding one.
    """

    site_key = SITE_KEY
    locales = DIRECTIONS
    primary_locale = LTR

    def cells(self) -> tuple[Cell, ...]:
        return (WHOLE,)

    def listing_url(self, base_url: str, *, locale: str, page: int,
                    cell: Cell = WHOLE) -> str:
        return listing_url(base_url, locale=locale, page=page, cell=cell)

    def read_last_page(self, html: str) -> int:
        return read_last_page(html)

    def read_ids(self, html: str) -> tuple[str, ...]:
        return read_ids(html)

    def in_cell(self, cell: Cell, *, last_page: int) -> OmanPageSource:
        return OmanPageSource(last_page=last_page, locales=self.locales, cell=cell)
