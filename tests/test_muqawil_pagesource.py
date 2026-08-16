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

from pathlib import Path

import pytest

from scrapex.pagesource import (
    FetchedPage,
    PageKind,
    PageSource,
    SliceNotSupported,
    supports_slices,
)
from scrapex.sites.muqawil import (
    SELF_BUILD_SEGMENT,
    MuqawilPageSource,
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
    assert source.site_key == "muqawil.org"


# ---- how big the crawl is ----------------------------------------------------

def test_the_page_count_is_read_from_the_listing_rather_than_assumed():
    """865 was true on the day it was measured and a directory grows. A constant
    would stop crawling the tail the week it changed, and say nothing."""
    assert read_last_page(listing().html) == 865


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


def test_a_row_past_the_end_of_the_page_is_not_in_any_slice(source):
    assert source.belongs_to_slice(listing("en"), 99, "RIYADH") is False


def test_naming_no_city_refuses_rather_than_answering_no(source):
    """False would mean 'this row is not in the slice', and a site answering it
    for every row produces an EMPTY crawl that reads as a successful one."""
    with pytest.raises(SliceNotSupported):
        source.belongs_to_slice(listing("en"), 0, "  ")


def test_a_listing_that_stopped_publishing_the_city_refuses(source):
    """The same reasoning one level down: a moved marker must not read as a
    smaller city."""
    moved = FetchedPage(url=listing().url,
                        html=listing().html.replace("icon-locaion", "icon-where"),
                        kind=PageKind.LISTING)

    with pytest.raises(SliceNotSupported, match="city marker has moved"):
        source.belongs_to_slice(moved, 0, "RIYADH")


def test_the_walker_can_ask_up_front_whether_slicing_is_available(source):
    """`supports_slices` is how the walker refuses a slice scope before the
    first request instead of half way through a crawl."""
    assert supports_slices(source, base_url="https://muqawil.org") is False, (
        "asked with an EMPTY page and no city named, muqawil must refuse — "
        "which is what lets the walker offer the scope honestly")
