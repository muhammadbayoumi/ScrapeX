"""The seam a generic source fits, before any site is written to it.

Step 1 of docs/GENERIC-FETCH-SEAM.md. No network here and none in the module —
that is deliberate, and it is where the risk lives. The parsing that comes later
is the half that looks like progress; this is the half that decides whether the
parsing ends up anywhere.

The fake below is not a stand-in for muqawil. It is what the walker will be
built against in step 2, so that all three crawl scopes, the frontier
declaration and the refusals can be tested without a site being up, unchanged,
or willing.
"""

from __future__ import annotations

import pytest

from scrapex.pagesource import (
    FetchedPage, PageKind, PageSource, SliceNotSupported, supports_slices,
)


class FakeSite:
    """Three listing pages, two rows each, half of them in Riyadh."""

    site_key = "fake"

    def listing_urls(self, base_url: str):
        for page in range(1, 4):
            yield f"{base_url}?page={page}"

    def detail_urls(self, page: FetchedPage):
        number = page.url.rsplit("=", 1)[-1]
        return [f"https://fake.test/entity/{number}a",
                f"https://fake.test/entity/{number}b"]

    def belongs_to_slice(self, page: FetchedPage, row_index: int, slice_of: str):
        return f"row{row_index}:{slice_of}" in page.html


class SiteThatCannotSlice:
    """A listing that shows only names — city and grade are on the detail page."""

    site_key = "opaque"

    def listing_urls(self, base_url: str):
        yield base_url

    def detail_urls(self, page: FetchedPage):
        return []

    def belongs_to_slice(self, page: FetchedPage, row_index: int, slice_of: str):
        raise SliceNotSupported(
            "this listing does not publish the city, so a slice cannot be "
            "chosen without fetching every detail page — which is the whole "
            "crawl")


def test_a_fake_site_satisfies_the_protocol():
    """A Protocol nothing can implement is a design, not a seam."""
    assert isinstance(FakeSite(), PageSource)
    assert isinstance(SiteThatCannotSlice(), PageSource)


def test_a_page_carries_its_html_unparsed_and_says_where_it_came_from():
    """The walker stores exactly this. Interpretation happens later, against
    the stored copy — which is what makes a wrong parse re-runnable without
    re-fetching 860 pages."""
    page = FetchedPage(url="https://fake.test/?page=2", html="<html>…</html>",
                       kind=PageKind.LISTING)

    assert page.html == "<html>…</html>"
    assert page.url.endswith("page=2")


def test_a_page_with_no_url_is_refused_at_construction():
    """save_snapshot needs the url to record where evidence came from. A page
    without one cannot be stored, and finding that out at the moment of storing
    means the fetch has already been paid for."""
    with pytest.raises(ValueError, match="no url"):
        FetchedPage(url="", html="<html></html>", kind=PageKind.LISTING)


def test_the_two_kinds_of_page_are_not_free_text():
    """The walker gates listing and detail differently. As strings, `"listings"`
    would compare unequal to `"listing"` for ever and the crawl would fetch
    nothing while reporting success."""
    assert PageKind.LISTING == "listing"
    assert PageKind.DETAIL == "detail"
    with pytest.raises(ValueError):
        PageKind("listings")


def test_a_page_cannot_be_edited_after_it_is_fetched():
    """Frozen because the snapshot is evidence. `generic_page_snapshot` is
    immutable in the database by trigger; a mutable page on the way there would
    be a hole in the same guarantee."""
    page = FetchedPage(url="https://fake.test/", html="<html/>",
                       kind=PageKind.LISTING)
    with pytest.raises(Exception):
        page.html = "<html>edited</html>"      # type: ignore[misc]


# ---- the slice, which is what makes the middle scope affordable --------------

def test_a_slice_is_decided_from_the_listing_page():
    """THE REASON LISTING_PLUS_SLICE COSTS MINUTES INSTEAD OF HOURS. muqawil
    publishes city and grade on the listing itself, so the rows in a slice are
    known before a single detail page is fetched."""
    site = FakeSite()
    page = FetchedPage(url="https://fake.test/?page=1",
                       html="row0:Riyadh row1:Jeddah", kind=PageKind.LISTING)

    assert site.belongs_to_slice(page, 0, "Riyadh")
    assert not site.belongs_to_slice(page, 1, "Riyadh")


def test_a_site_that_cannot_slice_refuses_rather_than_answering_no():
    """THE DISTINCTION THAT MATTERS MOST IN THIS FILE.

    False means "this row is not in the slice". A site that cannot tell would
    return False for every row, and the crawl would finish quickly, report
    success, and store nothing — a failure indistinguishable from a slice that
    genuinely had no members.
    """
    site = SiteThatCannotSlice()
    page = FetchedPage(url="https://opaque.test/", html="<html/>",
                       kind=PageKind.LISTING)

    with pytest.raises(SliceNotSupported, match="does not publish the city"):
        site.belongs_to_slice(page, 0, "Riyadh")


def test_whether_a_site_can_slice_is_answerable_before_a_crawl_starts():
    """So the walker refuses the scope up front rather than half-way through.
    Asked by TRYING, not by inspecting the class: a site can implement the
    method and still be unable to answer, because the inability lives in its
    HTML."""
    assert supports_slices(FakeSite())
    assert not supports_slices(SiteThatCannotSlice())


def test_a_listing_is_walked_in_order_and_yields_its_details():
    """The shape the walker consumes. Order matters: a listing that arrives
    shuffled makes 'stop after N pages' mean a different N every run."""
    site = FakeSite()

    urls = list(site.listing_urls("https://fake.test/"))
    assert urls == ["https://fake.test/?page=1",
                    "https://fake.test/?page=2",
                    "https://fake.test/?page=3"]

    first = FetchedPage(url=urls[0], html="", kind=PageKind.LISTING)
    assert list(site.detail_urls(first)) == [
        "https://fake.test/entity/1a", "https://fake.test/entity/1b"]


def test_the_listing_is_a_generator_so_a_site_need_not_know_its_length():
    """muqawil's 860 is discoverable only by reading page one. A site forced to
    return a list would have to guess the count before it had looked."""
    import types

    assert isinstance(FakeSite().listing_urls("https://fake.test/"),
                      types.GeneratorType)
