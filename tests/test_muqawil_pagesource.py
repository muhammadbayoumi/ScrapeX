"""What muqawil.org knows about its own pages, proved against real HTML.

Step 3 of docs/GENERIC-FETCH-SEAM.md. `scrapex/pagewalk.py` and
`scrapex/pagesource.py` shipped tested against a `FakeSite`, which proves the
walker and says nothing about any real site. This is the first `PageSource` with
a site behind it.

THE FIXTURES ARE REAL, TRIMMED, AND COMMITTED — `tests/fixtures/muqawil/`, taken
2026-08-16. Trimmed to the pagination and four cards for the listings, and to
everything but the scripts for the profiles (the one script carrying `lat:` is
kept, because the coordinates are only there). Nothing here touches the network:
a test that needs muqawil to be up is a test that fails on a train.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scrapex.pagesource import (
    WHOLE,
    Cell,
    FetchedPage,
    PageKind,
    PageSource,
    SliceNotSupported,
    supports_slices,
)
from scrapex.sites.muqawil import (
    SELF_BUILD_SEGMENT,
    MuqawilPageSource,
    MuqawilPartition,
    cells,
    listing_url,
    read_ids,
    read_last_page,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


def listing(locale: str = "en") -> FetchedPage:
    return FetchedPage(
        url=f"https://muqawil.org/{locale}/contractors?page=1",
        html=(FIXTURES / f"listing-{locale}.html").read_text(encoding="utf-8"),
        kind=PageKind.LISTING)


@pytest.fixture()
def source() -> MuqawilPageSource:
    return MuqawilPageSource(last_page=3)


# ---- the protocol itself -----------------------------------------------------

def test_it_is_a_page_source_and_not_a_connector(source):
    """`PageSource` is runtime-checkable, so this is a real assertion and not a
    comment. A generic source written against `SiteConnector` instead would
    compile, pass its own tests, and put nothing in the generic tables."""
    assert isinstance(source, PageSource)


def test_the_site_key_is_the_catalogue_s_and_not_the_hostname(source):
    """IT READ `muqawil.org` UNTIL THE TWO HALVES WERE FIRST JOINED, and could
    never have worked. `snapshotcrawl.read_scope` looks this up in
    `site_profile`, and rows get there through `catalog.register_site`, whose
    `CatalogKey` is `^[a-z][a-z0-9_]{1,63}$` — no dots, no hyphens.

    So a hostname here means every crawl raises SiteNotRegistered while the row
    sits in the table under a name one character different. Asserted against the
    pattern itself rather than the literal, so the rule is what is pinned.
    """
    assert re.fullmatch(r"[a-z][a-z0-9_]{1,63}", source.site_key), (
        f"{source.site_key!r} cannot be registered as a site_profile row, so "
        "no crawl of it will ever find its scope")
    assert source.site_key == "muqawil_org"


# ---- how big the crawl is ----------------------------------------------------

def test_the_page_count_is_read_from_the_listing_rather_than_assumed():
    """865 was true on the day it was measured and a directory grows. A constant
    would stop crawling the tail the week it changed, and say nothing."""
    assert read_last_page(listing().html) == 865


def test_a_filtered_listing_does_not_hide_its_page_count_behind_an_entity():
    """THE LIVE FAILURE, in the shape the live page writes it.

    Unfiltered, the paginator writes `?page=2` and the old pattern matched
    because `page=` followed a `?`. Add one filter and it writes
    `?region_id=1&amp;page=322`, where the character before `page=` is a
    SEMICOLON — so nothing matched, `read_last_page` raised, and Riyadh's 322
    pages read as one page of twenty. Measured against the live site on
    2026-08-20: 322 is the real number.

    Asserted on the ESCAPED text and not on `&`, because a fixture written with
    a bare ampersand is not the page: bs4 and the browser both normalise, and it
    was exactly the escaping that broke this.
    """
    escaped = (
        '<ul class="pagination">'
        '<li><a href="https://muqawil.org/en/contractors?region_id=1&amp;page=1">'
        '«</a></li>'
        '<li><a href="https://muqawil.org/en/contractors?region_id=1&amp;page=2">'
        '2</a></li>'
        '<li><a href="https://muqawil.org/en/contractors?region_id=1&amp;page=322">'
        '»</a></li></ul>')
    assert "&amp;page=322" in escaped, "the fixture must carry the entity"
    assert read_last_page(escaped) == 322


def test_a_page_count_is_not_read_off_the_query_string_of_the_page_itself():
    """A slice's own URL is `?page=1&region_id=1`, and a caller that passed the
    URL in with the body — or a pattern loose enough to reach it — would read
    `1` and call the slice complete. The number has to come from a LINK."""
    with pytest.raises(ValueError, match="refusing to guess"):
        read_last_page("<html><body>?page=7 is not a link</body>"
                       "<p>region_id=1&amp;page=9</p></html>")


def test_a_page_with_no_pagination_refuses_rather_than_guessing():
    """Returning 1 would be the dangerous answer: a crawl of twenty contractors
    out of seventeen thousand, reported as complete."""
    with pytest.raises(ValueError, match="refusing to guess"):
        read_last_page("<html><body>no pagination here</body></html>")


def test_the_source_will_not_be_built_without_a_page_count():
    """A default would let a caller crawl page one and never learn that 864
    pages were not asked for."""
    with pytest.raises(TypeError):
        MuqawilPageSource()          # type: ignore[call-arg]


# ---- the listing frontier ----------------------------------------------------

def test_both_locales_are_walked_page_by_page_and_not_locale_by_locale(source):
    """THE ORDER IS THE POINT. A crawl stopped half way must hold BOTH languages
    for the pages it reached — the owner's columns come in pairs, and half a
    pair is not half a row, it is an unusable one."""
    urls = list(source.listing_urls("https://muqawil.org"))

    assert urls[:4] == [
        "https://muqawil.org/en/contractors?page=1",
        "https://muqawil.org/ar/contractors?page=1",
        "https://muqawil.org/en/contractors?page=2",
        "https://muqawil.org/ar/contractors?page=2",
    ]
    assert len(urls) == 6, "three pages in both locales is six requests"


def test_the_request_count_is_the_pages_times_the_locales(source):
    """FOUND BY THE FIRST LIVE RUN. The plan reported 865 requests for a crawl
    that makes 1,730, because each page is fetched in both languages — so the
    progress bar would have reached its total half way through and sat there.

    The count belongs to the SITE because only the site knows it fetches each
    page twice; a caller passing `last_page` cannot know that."""
    assert source.listing_requests == 6, "three pages in two locales"
    assert source.listing_requests == len(list(source.listing_urls("https://x")))


def test_a_trailing_slash_on_the_base_url_does_not_double(source):
    assert next(iter(source.listing_urls("https://muqawil.org/"))) == \
        "https://muqawil.org/en/contractors?page=1"


# ---- the detail frontier -----------------------------------------------------

def test_every_contractor_on_the_page_is_offered_in_both_languages(source):
    urls = list(source.detail_urls(listing()))
    ids = {url.rsplit("/", 2)[-2] for url in urls}

    assert len(ids) == 4, "the fixture holds four cards"
    assert len(urls) == 8, "each contractor is wanted in both locales"
    for contractor_id in ids:
        assert f"https://muqawil.org/en/contractors/{contractor_id}/143" in urls
        assert f"https://muqawil.org/ar/contractors/{contractor_id}/143" in urls


def test_the_self_build_segment_is_rebuilt_and_never_inherited(source):
    """`/143` is not decoration. `/881/1` and `/881/999` return the same
    contractor, but only `143` renders the self-build price section — measured
    by diffing the two, where the ONLY difference was that section appearing.
    A crawl that carried some other value would ship three of the owner's
    columns permanently empty and nothing would say so."""
    assert SELF_BUILD_SEGMENT == "143"

    strange = FetchedPage(
        url="https://muqawil.org/en/contractors?page=1",
        html=listing().html.replace("/143", "/999"),
        kind=PageKind.LISTING)

    for url in source.detail_urls(strange):
        assert url.endswith("/143"), (
            f"{url} carried the listing's own tail instead of the one that "
            "renders every section")


def test_the_impostor_card_is_not_taken_for_a_contractor(source):
    """A listing page holds twenty-one `div.section-card` and only twenty are
    contractors. Selecting by position rather than by holding a profile link
    would be off by one for every row after the impostor."""
    padded = FetchedPage(
        url=listing().url,
        html=listing().html.replace(
            "<div class='container'>",
            "<div class='container'><div class='section-card'>an advert</div>"),
        kind=PageKind.LISTING)

    assert len(list(source.detail_urls(padded))) == \
        len(list(source.detail_urls(listing())))


def test_one_contractor_listed_twice_is_asked_for_once(source):
    doubled = FetchedPage(url=listing().url,
                          html=listing().html + listing().html,
                          kind=PageKind.LISTING)

    assert len(list(doubled_ids(source, doubled))) == 4


def doubled_ids(source, page):
    return {url.rsplit("/", 2)[-2] for url in source.detail_urls(page)}


# ---- the slice, which is what makes a cheap first crawl possible -------------

def test_a_city_is_read_off_the_listing_in_either_language(source):
    """ANSWERED FROM THE LISTING, which is the whole reason the slice scope is
    affordable: one city's profiles without fetching the other sixteen
    thousand."""
    assert source.belongs_to_slice(listing("en"), 0, "RIYADH") is True
    assert source.belongs_to_slice(listing("en"), 0, "riyadh") is True, \
        "case is the reader's business, not the owner's"
    assert source.belongs_to_slice(listing("ar"), 0, "الرياض") is True


def test_a_city_that_is_not_this_row_is_a_plain_no(source):
    assert source.belongs_to_slice(listing("en"), 0, "JEDDAH") is False


def test_a_row_past_the_end_of_the_page_is_refused_not_answered(source):
    """THIS TEST USED TO ASSERT `is False`, AND THAT EXPECTATION ENCODED A DEFECT.

    Answering `False` means "this row is not in the slice", which is a claim about a row
    that does not exist. It made a real off-by-a-locale bug invisible:
    `enumerate(detail_urls(page))` handed indices up to 33 for a page with 17 cards, and
    every index past the last card was quietly dropped — seventeen contractors vanished
    from the slice and the result read as a smaller city.

    An index past the last row is a CALLER error, so it is the one thing this method must
    not have an opinion about. Same reasoning as the two tests below it: a refusal is the
    only answer that cannot be mistaken for data.
    """
    with pytest.raises(SliceNotSupported) as raised:
        source.belongs_to_slice(listing("en"), 99, "RIYADH")

    assert "does not exist" in str(raised.value)


def test_naming_no_city_refuses_rather_than_answering_no(source):
    """False would mean 'this row is not in the slice', and a site answering it
    for every row produces an EMPTY crawl that reads as a successful one."""
    with pytest.raises(SliceNotSupported):
        source.belongs_to_slice(listing("en"), 0, "  ")


def test_a_card_without_a_city_is_in_no_city_rather_than_a_refusal(source):
    """THIS TEST USED TO DEMAND A REFUSAL, AND THE BELIEF BEHIND IT WAS MEASURED FALSE.

    It read: *"a moved marker must not read as a smaller city"* — sound reasoning, and
    unable to tell a moved marker from a contractor that publishes no location. The cost
    was real: on 2026-08-21 a crawl that had closed four cells with `D = 0` ended on one
    card without a city.

    Then the rule was narrowed to "refuse only if NO card on the page has one", which
    looked like the measurable distinction. It is not. `region_id=0` is muqawil's
    no-location partition — the fact `#234` recorded when its 74 pages taught 21 fields
    against a declared 22 — and measured on stored pages: **`region_id=0` carries 17 and
    20 cards with ZERO city icons**, while `region_id=1` carries 20 of 20. A whole page
    without a city is legitimate here.

    So a cityless card is in no named city, and the moved-marker signal lives where it can
    actually be seen: `detail_frontier` reports the rows it examined against the rows it
    matched, and nothing matching anywhere is the symptom.
    """
    moved = FetchedPage(url=listing().url,
                        html=listing().html.replace("icon-locaion", "icon-where"),
                        kind=PageKind.LISTING)

    assert source.belongs_to_slice(moved, 0, "RIYADH") is False


def test_a_row_that_does_not_exist_is_still_a_refusal(source):
    """WHAT DID NOT CHANGE, and it must not: an index past the last card is a CALLER
    error, and `supports_slices` relies on that refusal to probe an empty page."""
    with pytest.raises(SliceNotSupported, match="does not exist"):
        source.belongs_to_slice(listing(), 999, "RIYADH")


def test_the_walker_can_ask_up_front_whether_slicing_is_available(source):
    """`supports_slices` is how the walker refuses a slice scope before the
    first request instead of half way through a crawl."""
    assert supports_slices(source, base_url="https://muqawil.org") is False, (
        "asked with an EMPTY page and no city named, muqawil must refuse — "
        "which is what lets the walker offer the scope honestly")


# ---- the partition: which slices exist, and how a slice's URL is built -------

def test_the_partition_is_fifty_six_cells_and_region_zero_is_one_of_them():
    """`region_id=0` IS THE WHOLE EXHAUSTIVENESS ANSWER, and leaving it out is
    the defect this asserts against.

    `Σ N` over regions 1–13 came to 15,966 against a listing of 17,403 — 1,437
    short, and those 1,437 are the contractors whose card publishes no location
    at all. `region_id=0` returns exactly them. A partition of regions 1–13 would
    read 15,966 rows, prove all 52 cells complete, and be wrong about the
    directory by 8.3%.
    """
    every = cells()
    assert len(every) == 56, "fourteen regions including zero, times four sizes"
    assert len({one.query for one in every}) == 56, "and no cell repeats another"

    regions = {dict(one.params)["region_id"] for one in every}
    assert regions == {str(n) for n in range(14)}
    assert "0" in regions, "the contractors who publish no location have a URL"

    sizes = {dict(one.params)["company_size"] for one in every}
    assert sizes == {"big", "medium", "small", "verysmall"}


def test_a_cell_url_puts_the_filter_before_the_page_as_the_site_does():
    """ONE BUILDER, BECAUSE THE URL IS AN IDENTITY. It is what gets stored in
    `generic_page_snapshot.source_url`, what `already_stored` compares on a
    resume, and what the witness re-fetches. Two builders differing by parameter
    order give a resume that re-fetches everything it already has, and neither
    copy looks wrong on its own.

    The order also matches the paginator hrefs the site itself publishes
    (`...?region_id=1&page=322`), so a stored URL can be compared with the link
    the page came from.
    """
    one = Cell(params=(("region_id", "1"), ("company_size", "big")))
    assert listing_url("https://muqawil.org", locale="en", page=322, cell=one) == \
        "https://muqawil.org/en/contractors?region_id=1&company_size=big&page=322"
    assert listing_url("https://muqawil.org/", locale="ar", page=1) == \
        "https://muqawil.org/ar/contractors?page=1"


def test_a_cell_names_its_own_pages_and_never_the_listings():
    """REGION 13 × VERYSMALL IS SEVEN PAGES where the listing is 871. Handing a
    cell the listing's page count would fetch 864 pages that all answer with the
    cell's last page over and over — and the crawl would look like it was
    working."""
    one = Cell(params=(("region_id", "13"), ("company_size", "verysmall")))
    source = MuqawilPageSource(last_page=7, locales=("en",), cell=one)
    urls = list(source.listing_urls("https://muqawil.org"))
    assert len(urls) == 7
    assert urls[0].endswith("?region_id=13&company_size=verysmall&page=1")
    assert urls[-1].endswith("&page=7")
    assert source.cell is one


def test_an_unfiltered_source_is_unchanged_by_the_partition_existing(source):
    """THE DEFAULT IS THE WHOLE LISTING. Every caller written before the
    partition existed passes no cell and must get exactly what it got."""
    assert source.cell is WHOLE
    assert next(iter(source.listing_urls("https://muqawil.org"))) == \
        "https://muqawil.org/en/contractors?page=1"


def test_a_cell_that_names_one_parameter_twice_is_refused():
    """A repeated parameter is not a narrower filter, it is an ambiguous one: the
    site decides which occurrence wins and nothing here can say which. Refused
    rather than de-duplicated, because dropping one silently gives a cell whose
    label and whose URL describe different sets."""
    with pytest.raises(ValueError, match="one parameter twice"):
        Cell(params=(("region_id", "1"), ("region_id", "2")))


def test_the_empty_cell_is_the_whole_listing_and_has_a_name():
    """Not a special case, deliberately: sizing the unfiltered listing and sizing
    a cell are then the same two requests through the same code, which is what
    lets the exhaustiveness audit compare both sides measured the same way."""
    assert WHOLE.query == ""
    assert WHOLE.label == "whole"
    assert Cell(params=(("region_id", "0"),)).label == "region_id_0"


# ---- ids off a listing page: order kept, duplicates kept ---------------------

def test_the_id_sequence_is_read_in_published_order_with_duplicates_kept():
    """THIS IS WHAT THE WITNESS COMPARES. A set would answer "the same twenty
    contractors" for two different orderings, and a rolled cache generation is
    exactly a reordering of the same population — so an unordered read would
    certify the one event the witness exists to catch.

    Duplicates are kept for the same reason: 4,556 of 11,059 contractors turned
    up on more than one page in a single pass, and a repeat inside one page is
    itself a fact about the page rather than noise to clean up.
    """
    page = listing()
    ids = read_ids(page.html)
    assert ids, "the fixture must publish contractors"
    assert isinstance(ids, tuple)

    doubled = read_ids(page.html + page.html)
    assert doubled == ids + ids, "duplicates kept, and in order"
    assert len(set(doubled)) == len(set(ids))


def test_the_ids_are_the_same_in_both_locales_because_an_href_has_no_language():
    """MEASURED: 20 of 20 identical on 845 of 864 stored pages. It is why the
    coverage arithmetic is read from ONE locale — counting both would divide by a
    population it had counted twice — and why the Arabic half is a data-pairing
    cost rather than a coverage cost."""
    assert set(read_ids(listing("en").html)) == set(read_ids(listing("ar").html))


def test_a_listing_and_its_detail_urls_agree_about_who_is_on_the_page(source):
    """`detail_urls` and `read_ids` read the same cards through the same regex, so
    a change to one cannot leave the other behind. The impostor twenty-first
    `div.section-card` is excluded by both, because both require a profile link."""
    page = listing()
    from_details = {url.split("/")[-2] for url in source.detail_urls(page)}
    assert from_details == set(read_ids(page.html))


def test_a_partition_declares_the_locales_it_reads_and_refuses_a_stray_primary():
    """The coverage arithmetic must be read off pages the crawl actually asks
    for. A primary locale outside the fetched set would compute a deficit over a
    population nothing had fetched."""
    partition = MuqawilPartition()
    assert partition.locales == ("en", "ar")
    assert partition.primary_locale == "en"
    assert partition.site_key == MuqawilPageSource.site_key
    assert len(partition.cells()) == 56

    with pytest.raises(ValueError, match="not among the locales"):
        MuqawilPartition(locales=("ar",), primary_locale="en")
