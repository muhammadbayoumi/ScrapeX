"""muqawil.org — the Saudi Contractors Authority's public contractor directory.

Step 3 of docs/GENERIC-FETCH-SEAM.md, and the first concrete `PageSource` this
project has. Everything here is about THIS SITE'S LAYOUT and nothing else: no
fetching, no pacing, no request counting, no database. All of that belongs to
`scrapex/pagewalk.py`, and it belongs there so that every site behaves the same
way about the things that are not about the site.

WHAT WAS MEASURED, 2026-08-16, and why each measurement is load-bearing. The
full record is `docs/CONTRACTOR-SOURCE.md`; these four decide the code:

  * The listing is `?page=1..865`, TWENTY rows a page, and **no page-size
    parameter is honoured** — `per_page`, `perPage`, `limit`, `size`,
    `page_size` and `take` were each tried at 60 and each answered twenty. So
    the page count is the crawl's whole bound and cannot be traded down.

  * A profile is `/{lang}/contractors/{id}/{143}`. The trailing segment plays NO
    part in identity — `/881/1` and `/881/999` return the same contractor — but
    `143` is what makes the self-build price section render at all. Diffing the
    two, the only difference was `العقود سعر البناء (برنامج البناء الذاتي)`
    appearing under `143` and vanishing under `999`. A crawl that treated the
    segment as noise would ship three of the owner's columns permanently empty
    and nothing would say so. It is a literal here, deliberately.

  * A contractor card is `div.section-card`, and there are TWENTY-ONE of them on
    a listing page. The twenty-first is not a contractor. Cards are therefore
    selected by holding a profile link, never by counting.

  * Cloudflare fronts the site and does NOT block: a plain HTTP fetch with
    ScrapeX's own user agent answers 200 with the full body and no interstitial.
    No browser is needed, which is an order of magnitude off the crawl's cost.
"""
from __future__ import annotations

import html as html_entities
import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

from ..pagesource import WHOLE, Cell, FetchedPage, PageSource, SliceNotSupported

#: The trailing path segment that makes a profile render its self-build prices.
#: A literal because it is one, and named because `143` in a URL template is the
#: kind of number a later reader deletes as noise. See the module docstring.
SELF_BUILD_SEGMENT = "143"

#: Both locales, because the `[ar]` half of every column comes from the second.
#: The owner's reason: the Data page switches language behind one toggle, so a
#: row that carries only one language cannot be shown in the other.
LOCALES = ("en", "ar")

#: A profile link, in either locale. The id is the identity; the tail is not.
_PROFILE = re.compile(r"/(?:en|ar)/contractors/(\d+)/\d+")

#: `region_id`, INCLUDING ZERO, and the zero is the whole exhaustiveness answer.
#: `Σ N` over regions 1…13 came to 15,966 against a whole listing of 17,403 —
#: 1,437 short. Those 1,437 are the contractors whose card publishes no location
#: at all, and `region_id=0` returns exactly them, every card blank. Corroborated
#: independently: 960 of the 11,059 stored records (8.7%) have a null
#: `card_city_region`, and 1,437 of 17,403 is 8.3%. So the "contractor in no
#: partition" case — the one that makes a partition method unsound — turns out to
#: have a URL. Measured 2026-08-20, `docs/BACKLOG.md` DEC-11.
REGION_IDS = (0, *range(1, 14))

#: `company_size`, and it is exhaustive too: its four values summed to 17,405
#: against a whole of 17,403, a drift of two arrivals in the minutes between the
#: two measurements. They are RADIO INPUTS and not a `<select>`, which is why an
#: earlier study of the listing's dropdowns reported this facet did not exist.
COMPANY_SIZES = ("big", "medium", "small", "verysmall")

#: The city, keyed by the ICON and never by the label beside it. The Arabic page
#: spells the membership-number label `رقم العضويه` — with `ه`, not `ة` — and a
#: label-matched selector breaks on a spelling difference no reader would ever
#: notice. The icon class is identical in both locales, which makes it the only
#: honest key. `icon-locaion` is THEIR spelling of "location"; it is matched
#: exactly, and the day they fix it this selector is what will say so.
_CITY_ICON = "icon-locaion"


def read_last_page(html: str) -> int:
    """The highest page number the listing's own pagination links to.

    READ, NEVER ASSUMED. 865 was true on 2026-08-16 and a directory grows; a
    constant here would quietly stop crawling the tail the week it changed. The
    caller reads page one, calls this, and only then builds the source — which
    is why `MuqawilPageSource` demands the number instead of defaulting it.

    ENTITIES ARE UNESCAPED FIRST, and the reason is a measured failure rather
    than tidiness. An UNFILTERED listing writes `?page=2`, so `page=` follows a
    `?` and the old pattern matched. A FILTERED one — `?region_id=1` — writes
    `href="...?region_id=1&amp;page=322"`, where the character before `page=` is
    a SEMICOLON. The pattern matched nothing, this function raised, and every
    caller that guarded the raise read a 322-page region as a single page of
    twenty. That is not a parse quirk: the whole partition-and-witness method in
    `DEC-11` reads its slice sizes from a filtered listing, so a slice would
    have reported itself complete after one page while 6,420 contractors sat
    behind pagination nobody followed.

    AND ONLY INSIDE AN `href`, because unescaping WIDENS what matches: after it,
    the string `region_id=1&page=9` sitting in ordinary body text counts as a
    page link where the semicolon used to hide it. The number a crawl trusts has
    to come from a link the site published, not from prose that happens to look
    like a query string.
    """
    pages = [int(found)
             for href in re.findall(r"""href=["']([^"']+)["']""", html)
             for found in re.findall(r"[?&]page=(\d+)",
                                     html_entities.unescape(href))]
    if not pages:
        raise ValueError(
            "no pagination on this listing page, so the crawl's size is "
            "unknown — refusing to guess it. Check the page really is a "
            "contractor listing before treating this as a layout change.")
    return max(pages)


def listing_url(base_url: str, *, locale: str, page: int,
                cell: Cell = WHOLE) -> str:
    """One listing page's URL, filtered or not. THE ONLY PLACE ONE IS BUILT.

    IT IS ONE FUNCTION BECAUSE THE URL IS AN IDENTITY. Three callers need this
    string and they must agree to the character: the crawl that STORES the page
    (`generic_page_snapshot.source_url`), the resume that decides the page is
    already stored (`snapshotcrawl.already_stored` compares that column), and the
    witness that re-fetches page 1 after the slice to prove the generation never
    rolled. Two builders that differ by the order of two query parameters would
    give a resume that re-fetches everything it already has, and neither copy
    would look wrong on its own.

    THE FILTER GOES BEFORE `page`, matching the site's own paginator hrefs
    (`...?region_id=1&amp;page=322`). It has no effect on what the site returns,
    and it means a stored URL can be pasted into a browser and compared with the
    link the page itself published.
    """
    query = f"{cell.query}&page={page}" if cell.query else f"page={page}"
    return f"{base_url.rstrip('/')}/{locale}/contractors?{query}"


def cells(*, region_ids: Iterable[int] = REGION_IDS,
          company_sizes: Iterable[str] = COMPANY_SIZES) -> tuple[Cell, ...]:
    """The exhaustive `region_id` × `company_size` partition — 56 cells.

    EXHAUSTIVE TO THE UNIT, measured 2026-08-20 over 152 requests: 15,966 across
    regions 1–13 plus 1,437 under `region_id=0` sums to 17,403, which is exactly
    what `(L−1)·S + c` says the unfiltered listing holds. Both axes are
    independently exhaustive, which is what makes their product exhaustive.

    IT COSTS 3% MORE PAGES THAN THE UNFILTERED LISTING, not less: `Σ` pages over
    the cells is 897 against 871, the per-cell rounding of a 20-row page. That
    overhead is the price of a crawl that can say "complete" instead of
    "probably" — 1,065 requests and about 1.7 hours against 18.4 hours for a
    thirteen-pass blind sweep that can still only report an expected number of
    contractors it never saw.

    THE ARGUMENTS EXIST FOR TESTS AND FOR A PARTIAL RUN, never to narrow the
    partition quietly: `crawl_partition` audits `Σ N_cell` against the whole
    listing and reports the shortfall, so a narrowed partition shows up as a
    deficit rather than as a smaller directory.
    """
    return tuple(
        Cell(params=(("region_id", str(region)), ("company_size", size)))
        for region in region_ids
        for size in company_sizes)


def _cards(html: str) -> list:
    """Every contractor card on a listing page, in the order it is published.

    SELECTED BY HOLDING A PROFILE LINK. `div.section-card` matches twenty-one
    elements and only twenty are contractors, so a slice keyed on position would
    be off by one for every row after the impostor.
    """
    soup = BeautifulSoup(html, "html.parser")
    return [card for card in soup.select("div.section-card")
            if card.find("a", href=_PROFILE)]


def read_ids(html: str) -> tuple[str, ...]:
    """Every contractor id this listing page publishes, IN PUBLISHED ORDER.

    THE ORDER IS THE POINT, and so is keeping the duplicates. This is what the
    partition crawl's witness compares: re-fetch a slice's page 1 after reading
    the slice, and if the id SEQUENCE is unchanged the listing's cache generation
    never rolled, so the pages just read were one true partition. A set would
    answer "the same twenty contractors" for two different orderings, which is
    exactly the case the witness exists to detect.

    AND NEVER THE BYTES. `docs/BACKLOG.md` DEC-11 measured a re-fetched page 1
    whose id order was IDENTICAL and whose body was NOT byte-identical — the
    response carries per-render noise, and the email address alone is XOR-ed under
    a key that rotates per render. A byte comparison would therefore have failed
    every witness, so the method would have certified nothing, ever, while looking
    like it was working.

    Read off the href, so it is language-independent: `/en/contractors/1301/143`
    and `/ar/contractors/1301/143` are the same contractor and yield the same id.
    """
    found: list[str] = []
    for card in _cards(html):
        link = card.find("a", href=_PROFILE)
        match = _PROFILE.search(link["href"])
        if match is not None:
            found.append(match.group(1))
    return tuple(found)


class MuqawilPageSource:
    """What muqawil.org knows about its own pages."""

    #: THE CATALOGUE'S KEY, NOT THE HOSTNAME, and the difference is not
    #: cosmetic. `PageSource.site_key` is what `snapshotcrawl.read_scope` looks
    #: up in `site_profile`, and rows get there through `catalog.register_site`,
    #: whose `CatalogKey` is `^[a-z][a-z0-9_]{1,63}$` — no dots, no hyphens. A
    #: `site_key` of "muqawil.org" can therefore never match a row that was
    #: registered properly, and every crawl of it would raise SiteNotRegistered
    #: while the row sat there under a name one character different.
    site_key = "muqawil_org"

    def __init__(self, *, last_page: int, locales: Iterable[str] = LOCALES,
                 cell: Cell = WHOLE) -> None:
        """`last_page` is REQUIRED, and that is the point.

        A default would let a caller crawl page one, get twenty contractors out
        of seventeen thousand, and have nothing tell them the other 864 pages
        were never asked for. `read_last_page` is how the number is obtained.

        `cell` NARROWS THE LISTING AND NOTHING ELSE. It changes which listing
        pages this source names; it does not change what a page means, so nothing
        downstream of the fetch has to know a cell exists. Its default is the
        whole listing, which is what every caller before the partition crawl
        wanted and still gets.

        AND `last_page` IS THE CELL'S OWN, not the listing's. Region 13 ×
        verysmall is 7 pages where the unfiltered listing is 871; passing the
        listing's number would fetch 864 pages of the cell that answer with the
        cell's last page over and over. Each cell publishes its size in its own
        paginator — `read_last_page` reads a FILTERED listing correctly, which it
        did not until #229.
        """
        if last_page < 1:
            raise ValueError(f"last_page must be at least 1, got {last_page}")
        self._last_page = last_page
        self._locales = tuple(locales)
        self._cell = cell

    @property
    def cell(self) -> Cell:
        """Which slice of the listing this source names. `WHOLE` if unfiltered."""
        return self._cell

    @property
    def listing_requests(self) -> int:
        """How many requests `listing_urls` will actually make.

        NOT the page count, and the difference cost a wrong progress bar on the
        first live run: 865 pages in two locales is 1,730 requests, and a caller
        that passed the page count to `crawlscope.plan` declared a frontier of
        half the crawl. The bar would have reached its total at the half-way
        point and sat there for fifteen minutes.

        It lives here because only the site knows it fetches each page twice.
        """
        return self._last_page * len(self._locales)

    def listing_urls(self, base_url: str) -> Iterable[str]:
        """Every listing page, in both locales, page by page rather than locale
        by locale.

        THE ORDER IS DELIBERATE: `en?page=1`, `ar?page=1`, `en?page=2`, … so a
        crawl stopped half way holds BOTH languages for the pages it reached,
        rather than every English page and no Arabic one. The owner's columns
        come in pairs; half a pair is not half a row, it is an unusable one.
        """
        for page in range(1, self._last_page + 1):
            for locale in self._locales:
                yield listing_url(base_url, locale=locale, page=page,
                                  cell=self._cell)

    def detail_urls(self, page: FetchedPage) -> Iterable[str]:
        """The profile of every contractor this listing page names, in both
        locales, deduplicated by contractor id.

        The id is taken from the href and the tail is REBUILT as
        `SELF_BUILD_SEGMENT` rather than carried over — the site's own links use
        it today, and rebuilding means a page that ever links some other value
        still gets crawled at the one that renders every section.
        """
        for _, url in self.detail_rows(page):
            yield url

    def detail_rows(self, page: FetchedPage) -> Iterable[tuple[int, str]]:
        """`(card_index, url)`, and it is `detail_urls`' authority rather than a
        parallel enumeration of the same thing.

        THE INDEX IS THE CARD'S, NOT THE URL'S, and that distinction is the whole point.
        This yields one URL PER LOCALE, so there are twice as many URLs as cards —
        measured on a stored page, 17 cards and 34 URLs. `enumerate(detail_urls(page))`
        therefore handed `belongs_to_slice` an index that pointed at a different
        contractor for every URL but the first, and dropped the 17 that indexed past
        the last card.

        THE INDEX IS TAKEN BEFORE DEDUPLICATION, deliberately. `read_ids` is in card
        order and `_cards` is the same order, so position IS the card. Numbering the
        deduplicated list instead would shift every index after the first repeated id —
        and a page that lists one contractor twice is exactly the case nobody would
        think to test.
        """
        base = _origin(page.url)
        emitted: set[str] = set()
        for row_index, contractor_id in enumerate(read_ids(page.html)):
            if contractor_id in emitted:
                continue
            emitted.add(contractor_id)
            for url in self.profile_urls(base, contractor_id):
                yield row_index, url

    def profile_urls(self, base_url: str, contractor_id: str) -> Iterable[str]:
        """The profile pages of ONE contractor, one per locale.

        THE ONE PLACE THAT KNOWS THE SHAPE. A frontier can be built two ways — off the
        listing pages on disk, or off the ids in `dataset_sighting` — and both need this
        URL. Two copies of the pattern is two places to forget `SELF_BUILD_SEGMENT`,
        which is the segment that makes the self-build price section render at all.
        """
        for locale in self._locales:
            yield (f"{base_url.rstrip('/')}/{locale}/contractors/"
                   f"{contractor_id}/{SELF_BUILD_SEGMENT}")

    def belongs_to_slice(self, page: FetchedPage, row_index: int,
                         slice_of: str) -> bool:
        """Whether one row of this listing is in the named city.

        ANSWERED FROM THE LISTING, which is what makes the slice scope worth
        having: muqawil publishes the city on the card, so one city's profiles
        can be crawled without fetching the other sixteen thousand.

        The slice must be named in the SAME LANGUAGE as the page — `RIYADH` for
        an English listing, `الرياض` for an Arabic one. Translating here would
        mean shipping a city gazetteer and getting it wrong for the first city
        nobody thought of.
        """
        if not slice_of.strip():
            raise SliceNotSupported(
                "a slice of muqawil is a city and no city was named")

        cards = _cards(page.html)
        if row_index >= len(cards):
            # REFUSED, NOT `False`. This used to answer False, and that made the
            # off-by-a-locale pairing invisible: `enumerate(detail_urls(page))` handed
            # this method indices up to 33 for a page with 17 cards, and every one past
            # the last card was quietly dropped. Seventeen contractors vanished from the
            # slice and the result read as a smaller city.
            #
            # An index past the last row is a CALLER error — there is no row to answer
            # about — so it is the one thing this method must not have an opinion on.
            raise SliceNotSupported(
                f"row {row_index} of {page.url} does not exist: the page has "
                f"{len(cards)} card(s). A caller pairing URLs to rows by position must "
                "use `detail_rows`, because this listing yields one URL per locale.")

        icon = cards[row_index].select_one(f".info-icon span.{_CITY_ICON}")
        if icon is None:
            # The card carries no city. NOT an answer of False, which would
            # quietly drop a contractor from every slice and read as a smaller
            # city rather than as a layout that moved.
            raise SliceNotSupported(
                f"no {_CITY_ICON} on card {row_index} of {page.url} — the "
                "listing's city marker has moved, and a slice cannot be "
                "chosen from a page that no longer publishes one")

        box = icon.find_parent(class_="info-box")
        value = box.select_one(".info-value") if box else None
        return _city_of(value) == slice_of.strip().casefold()


class MuqawilPartition:
    """How muqawil's listing is cut into slices a crawl can prove it read whole.

    A SEPARATE CLASS FROM `MuqawilPageSource`, AND NOT A CONVENIENCE. That class
    requires `last_page` in its constructor, deliberately — see its docstring —
    and a partition does not have one: the 56 cells have 56 different page counts,
    each read from the cell's own paginator at the moment the crawl reaches it. A
    partition that had to be handed a page count before it had looked would have
    to invent one, which is the failure `last_page` being required exists to
    prevent.

    IT IS WHAT `scrapex/partitioncrawl.py` SPEAKS TO, so that module holds the
    method — size, read, witness, deficit — and knows nothing about regions,
    company sizes or query parameters. The same split as `pagesource.py` and
    `pagewalk.py`, for the same reason: two sites must not differ in the things
    that are not about the site.
    """

    site_key = MuqawilPageSource.site_key

    def __init__(self, *, locales: Iterable[str] = LOCALES,
                 primary_locale: str = "en") -> None:
        """`primary_locale` is the locale the COVERAGE arithmetic is read from.

        ONE LOCALE, AND COUNTING BOTH WOULD BE A MEASUREMENT ERROR RATHER THAN
        extra rigour. Arabic page N returns the SAME twenty ids as English page N
        — measured 20 of 20 identical on 845 of 864 stored pages — because the id
        comes from the href and an href has no language. So the Arabic half buys
        129 new ids for 865 requests: it is a data-pairing cost, not a coverage
        cost, and a deficit computed over both locales would divide by a
        population it had counted twice.

        BOTH LOCALES ARE STILL FETCHED, because the seven bilingual card columns
        exist only if both halves are on disk, and because a listing approved
        from English alone produces a schema without the `_ar` fields — a
        different `schema_hash`, which the approval path refuses against a
        dataset that already has them.
        """
        self._locales = tuple(locales)
        if primary_locale not in self._locales:
            raise ValueError(
                f"the primary locale {primary_locale!r} is not among the locales "
                f"being fetched {self._locales} — the coverage arithmetic would "
                "then be read from pages the crawl never asked for")
        self._primary = primary_locale

    @property
    def locales(self) -> tuple[str, ...]:
        return self._locales

    @property
    def primary_locale(self) -> str:
        return self._primary

    def cells(self) -> tuple[Cell, ...]:
        return cells()

    def listing_url(self, base_url: str, *, locale: str, page: int,
                    cell: Cell = WHOLE) -> str:
        return listing_url(base_url, locale=locale, page=page, cell=cell)

    def read_last_page(self, html: str) -> int:
        return read_last_page(html)

    def read_ids(self, html: str) -> tuple[str, ...]:
        return read_ids(html)

    def in_cell(self, cell: Cell, *, last_page: int) -> PageSource:
        """A `PageSource` naming exactly this cell's pages, in both locales."""
        return MuqawilPageSource(last_page=last_page, locales=self._locales,
                                 cell=cell)


def _city_of(value) -> str:
    """The city out of the card's location cell, folded for comparison.

    ONE CELL HOLDS TWO FACTS. The card publishes city and region together,
    separated by a dash and a great deal of whitespace:

        RIYADH
                                    - Riyadh

    and in Arabic `الرياض - الرياض`, where the two happen to be the same word.
    So the cell is not the city — the head of it is. Whitespace is collapsed
    first, because the separator is only recognisable once it is.

    The split is on the FIRST dash, which assumes no Saudi city name carries
    one. That held for every city seen (RIYADH, JEDDAH, DAMMAM, AL KHOBAR); if
    one ever does, this is the line that will be wrong, and it is written here
    rather than left as an accident of a regex.
    """
    if value is None:
        return ""
    text = " ".join(value.get_text(" ", strip=True).split())
    return text.split("-", 1)[0].strip().casefold()


def _origin(url: str) -> str:
    """`https://host` from any URL on it, without importing urllib for one job."""
    parts = url.split("/", 3)
    return "/".join(parts[:3]) if len(parts) >= 3 else url.rstrip("/")
