"""etendering.tenderboard.gov.om — what Oman's ESNAD vendor register knows about itself.

Studied in `#1004` before a line of this was written; the vocabulary measurements are
`#1004`'s step 1. Every constant here is a measurement, and `docs/GULF-EGYPT-SOURCES.md`
`:295-353` is the record this verified and corrected.

WHY THIS SOURCE IS READ FROM ITS LISTING AND NOTHING ELSE. The register's row carries the
whole record — name, CR number, address, telephone, fax, category, expiry, company type —
so **23,502 firms cost 471 requests**, one page of fifty at a time. There is no per-firm
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
from dataclasses import dataclass

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
    name: str
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


def register_url(page: int, *, direction: str = LTR, base_url: str = BASE_URL) -> str:
    """One page of the register.

    `pageNo` IS A GET PARAMETER, which is why this reader needs no form post and no
    session: `pageNo=2` answered with S No. 51-100 and a different fifty firms. It also
    makes every URL stable and enumerable, so the repository's URL-keyed resume works here
    unchanged -- unlike Balady, whose detail URL carries a token that is re-minted on every
    response (`scrapex/sites/balady.py`).
    """
    if page < 1:
        raise ValueError(f"page must be at least 1, got {page}")
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    return (f"{base_url}{REGISTER_PATH}?CTRL_STRDIRECTION={direction}&PublicUrl=1"
            f"&eventFlag={REGISTER_EVENT}&pageNo={page}")


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
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


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
    rather than pick one to believe.
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

    printed = re.search(r"of\s+(\d+)", _text(nav))
    if printed is not None:
        readings["printed"] = int(printed.group(1))

    if not readings:
        raise RegisterShapeError(
            "the paginator publishes no total in any of its three forms -- no hidMax, no "
            "ShowPage target and no 'of N'. S No. is computed from the requested page "
            "and cannot stand in for it")
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
            continue                      # a paginator row wearing a data row's cell count
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
        if not cells[2]:
            raise RegisterShapeError(f"a data row carries no company name: {cells!r}")
        firms.append(Firm(
            short_name=short_name,
            name=cells[2],
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
    """Pair the two views of one page on the CR number.

    ON THE NUMBER, NEVER ON POSITION -- `docs/GULF-EGYPT-SOURCES.md:338`. The order did
    match on page 1, and the pairing still goes through the number, because an order that
    happens to agree today is not a contract. A firm with no CR number cannot be paired and
    is reported rather than dropped: measured, that is 1 of 102 rows.
    """
    by_cr: dict[str, Firm] = {}
    for firm in arabic:
        if firm.cr_number:
            by_cr[firm.cr_number] = firm
    paired: list[tuple[Firm, Firm]] = []
    unpaired: list[str] = []
    for firm in english:
        other = by_cr.get(firm.cr_number) if firm.cr_number else None
        if other is None:
            unpaired.append(firm.short_name)
            continue
        paired.append((firm, other))
    if unpaired:
        raise RegisterShapeError(
            f"{len(unpaired)} firm(s) on this page have no counterpart in the Arabic "
            f"view by CR number: {unpaired[:6]}. The two views are the same fifty firms; "
            "a firm present in one and not the other is news, not a row to skip.")
    return tuple(paired)
