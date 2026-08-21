"""The walker fetches what the scope allows and not one page more.

The scope is not paperwork. muqawil's listing is 860 pages — fourteen minutes at
the shipped pace — and its detail pages are 121,157, which is thirty-four hours.
A walker that quietly fetched a detail page under `listing_only` would turn a
fourteen-minute crawl into a day and a half, and the only way anyone would find
out is by watching it not finish.

So every test here is about a page that must NOT be fetched, or a failure that
must not end the walk. Nothing here touches the network.
"""
from __future__ import annotations

import pytest

from scrapex.crawlscope import CrawlScope, SliceRequired
from scrapex.pagesource import FetchedPage, PageKind, SliceNotSupported
from scrapex.pagewalk import PageWalker


class FakeSite:
    """Three listing pages, two rows each, and it knows its own cities."""

    site_key = "fakesite"

    def __init__(self, pages: int = 3, can_slice: bool = True) -> None:
        self._pages = pages
        self._can_slice = can_slice
        #: Whether the walker ever ASKED this site about slice membership.
        #: Under listing_only it must not — see the test that reads it.
        self.slice_questions = 0

    def listing_urls(self, base_url: str):
        for n in range(1, self._pages + 1):
            yield f"{base_url}/list?page={n}"

    def detail_urls(self, page: FetchedPage):
        n = page.url.rsplit("=", 1)[-1]
        return [f"https://fake.test/entity/{n}a", f"https://fake.test/entity/{n}b"]

    def belongs_to_slice(self, page: FetchedPage, row_index: int, slice_of: str) -> bool:
        self.slice_questions += 1
        if not self._can_slice:
            raise SliceNotSupported("this site does not publish the city on its listing")
        # The first row of every page is in Cairo, the second is not.
        return slice_of == "Cairo" and row_index == 0


class Recorder:
    """Every url the walker asked for, in order."""

    def __init__(self, fails: set[str] | None = None) -> None:
        self.asked: list[str] = []
        self._fails = fails or set()

    def __call__(self, url: str) -> str:
        self.asked.append(url)
        if url in self._fails:
            raise TimeoutError("the site did not answer")
        return f"<html>{url}</html>"


def walker(site=None, fetch=None, pace_s=1.0):
    sleeps: list[float] = []
    w = PageWalker(site or FakeSite(), fetch or Recorder(),
                   pace_s=pace_s, sleep=sleeps.append)
    return w, sleeps


def test_listing_only_never_fetches_a_detail_page():
    """THE ONE THAT PAYS FOR THIS FILE. On muqawil the difference between
    obeying this and not is fourteen minutes against thirty-four hours.

    THE FIRST VERSION OF THIS TEST DID NOT BITE, and it is worth recording why.
    It asserted only that no detail url was fetched — and with the scope check
    deleted from the walker it still passed, because this fake answers "not in
    the slice" for the empty slice `listing_only` carries. The guard was
    redundant with the fixture rather than proven by it.

    So what is asserted now is that the site is never ASKED. Under listing_only
    the depth is settled before the site is consulted at all, which is the thing
    that actually has to be true: a site whose `belongs_to_slice` happened to
    answer True would otherwise crawl for thirty-four hours under the name of
    the fourteen-minute scope.
    """
    site = FakeSite()
    fetch = Recorder()
    w, _ = walker(site=site, fetch=fetch)

    report = w.walk("https://fake.test", CrawlScope.LISTING_ONLY)

    assert report.listing_pages == 3
    assert report.detail_pages == 0
    assert all("/list?page=" in url for url in fetch.asked), (
        f"a detail page was fetched under listing_only: {fetch.asked}")
    assert site.slice_questions == 0, (
        "the walker asked the site about slice membership under listing_only — "
        "so the depth is being decided by the site's answer instead of by the "
        "scope, and a site that answered True would crawl every detail page")
    assert report.skipped == 0, (
        "detail pages were 'skipped' under a scope that never considers them; "
        "skipped means the slice ruled a row out, and listing_only rules on "
        "nothing")


def test_the_slice_fetches_only_the_rows_that_are_in_it():
    fetch = Recorder()
    w, _ = walker(fetch=fetch)

    report = w.walk("https://fake.test", CrawlScope.LISTING_PLUS_SLICE,
                    slice_of="Cairo")

    assert report.listing_pages == 3
    assert report.detail_pages == 3, "one row per page is in Cairo"
    assert report.skipped == 3, "the other row per page was ruled out, not lost"
    assert [u for u in fetch.asked if "/entity/" in u] == [
        "https://fake.test/entity/1a",
        "https://fake.test/entity/2a",
        "https://fake.test/entity/3a"], "the wrong rows were followed"


def test_a_slice_scope_with_no_slice_named_is_refused_before_the_first_request():
    """The refusal must cost nothing. Discovering it after fourteen minutes of
    listing pages is the same failure with a bill attached."""
    fetch = Recorder()
    w, _ = walker(fetch=fetch)

    with pytest.raises(SliceRequired):
        w.walk("https://fake.test", CrawlScope.LISTING_PLUS_SLICE)

    assert fetch.asked == [], "it started crawling before checking it could finish"


def test_a_site_that_cannot_slice_says_so_instead_of_crawling_nothing():
    """SliceNotSupported must reach the caller. Swallowed, it would read as
    'no row is in the slice' and produce an empty crawl wearing the clothes of
    a successful one."""
    w, _ = walker(site=FakeSite(can_slice=False))

    with pytest.raises(SliceNotSupported):
        w.walk("https://fake.test", CrawlScope.LISTING_PLUS_SLICE, slice_of="Cairo")


def test_full_then_listing_takes_every_detail_page():
    fetch = Recorder()
    w, _ = walker(fetch=fetch)

    report = w.walk("https://fake.test", CrawlScope.FULL_THEN_LISTING)

    assert report.listing_pages == 3 and report.detail_pages == 6
    assert report.skipped == 0


def test_one_dead_page_does_not_end_the_crawl():
    """A crawl that stops at the first 404 of a thirty-four hour run is a crawl
    nobody can finish. The failure is recorded and named, and the rest goes on."""
    fetch = Recorder(fails={"https://fake.test/entity/2a"})
    w, _ = walker(fetch=fetch)

    report = w.walk("https://fake.test", CrawlScope.FULL_THEN_LISTING)

    assert report.detail_pages == 5, "the other five detail pages were abandoned"
    assert [url for url, _ in report.failures] == ["https://fake.test/entity/2a"]
    assert "TimeoutError" in report.failures[0][1], (
        "the failure does not say what happened, so nobody can act on it")


def test_a_dead_listing_page_costs_only_its_own_details():
    fetch = Recorder(fails={"https://fake.test/list?page=2"})
    w, _ = walker(fetch=fetch)

    report = w.walk("https://fake.test", CrawlScope.FULL_THEN_LISTING)

    assert report.listing_pages == 2
    assert report.detail_pages == 4, "pages 1 and 3 still yielded their details"
    assert len(report.failures) == 1


def test_the_pace_is_paid_between_requests_and_never_before_the_first():
    """A crawl that sleeps before its first page delays every run for nothing,
    and one that sleeps after its last bills for a second it did not need."""
    w, sleeps = walker(pace_s=1.5)

    w.walk("https://fake.test", CrawlScope.LISTING_ONLY)

    assert sleeps == [1.5, 1.5], (
        f"three pages should cost two waits, not {len(sleeps)}")


def test_every_page_reaches_the_sink_exactly_once_and_says_which_kind_it_is():
    seen: list[FetchedPage] = []
    w, _ = walker()

    w.walk("https://fake.test", CrawlScope.FULL_THEN_LISTING, on_page=seen.append)

    assert len(seen) == 9
    assert [p.kind for p in seen[:3]] == [
        PageKind.LISTING, PageKind.DETAIL, PageKind.DETAIL], (
        "the sink cannot tell a listing from a detail, so it cannot store either")
    assert len({p.url for p in seen}) == 9, "a page was handed over twice"
    assert all(p.html for p in seen), "a page arrived with no html"


def test_the_ceiling_stops_the_walk_and_says_the_crawl_is_partial():
    """A walk that stopped at some built-in number and said nothing would report
    a partial crawl as a complete one — which is how a warehouse quietly stops
    growing."""
    fetch = Recorder()
    w, _ = walker(fetch=fetch)

    report = w.walk("https://fake.test", CrawlScope.FULL_THEN_LISTING,
                    max_requests=4)

    assert report.requests <= 4
    assert "PARTIAL" in report.stopped_early
    assert len(fetch.asked) <= 4


def test_a_walk_that_finished_does_not_claim_to_have_stopped_early():
    w, _ = walker()

    report = w.walk("https://fake.test", CrawlScope.LISTING_ONLY, max_requests=99)

    assert report.stopped_early == ""


# ---- a site whose listing yields more than one URL per row -------------------
#
# THE CASE `FakeSite` ABOVE CANNOT REACH, and the reason the real defect survived here.
# `FakeSite.detail_urls` returns two URLs for a page and `belongs_to_slice` is asked
# about `row_index` 0 and 1 — so `enumerate(detail_urls(page))` is correct for it, and
# every slice test above passed under a pairing that was wrong for muqawil. Measured
# there: 17 rows, 34 URLs, and every URL after the first asked about the wrong row.

class BilingualSite:
    """One row, two URLs — the shape muqawil has and every fake here did not.

    `detail_rows` is what says which row a URL came from. Without it the walker's
    `enumerate` would pair url index 1 (row 0's second locale) with ROW 1.
    """

    site_key = "bilingual"

    #: Two rows per page, each with an English and an Arabic detail page.
    ROWS = ("first", "second")

    def __init__(self) -> None:
        self.asked_about: list[int] = []

    def listing_urls(self, base_url: str):
        yield f"{base_url}/list?page=1"

    def detail_rows(self, page: FetchedPage):
        for row_index, name in enumerate(self.ROWS):
            for locale in ("en", "ar"):
                yield row_index, f"https://fake.test/{locale}/{name}"

    def detail_urls(self, page: FetchedPage):
        return [url for _, url in self.detail_rows(page)]

    def belongs_to_slice(self, page: FetchedPage, row_index: int, slice_of: str) -> bool:
        if row_index >= len(self.ROWS):
            raise SliceNotSupported(
                f"row {row_index} does not exist: the page has {len(self.ROWS)}")
        self.asked_about.append(row_index)
        return row_index == 0


def test_a_slice_asks_the_row_each_url_came_from_not_its_position():
    """THE TEST THE WALKER DID NOT HAVE, and a mutation proved it: reverting this line
    to `enumerate(self._source.detail_urls(page))` broke nothing at all.

    With two rows and four URLs, `enumerate` asks about rows 0,1,2,3 — and rows 2 and 3
    do not exist. Here it must ask about 0,0,1,1: each URL's own row.
    """
    site = BilingualSite()
    fetch = Recorder()
    walk, _ = walker(site, fetch)

    walk.walk("https://fake.test", CrawlScope.LISTING_PLUS_SLICE, slice_of="Cairo")

    assert site.asked_about == [0, 0, 1, 1]
    # Row 0 is in the slice, so BOTH of its locales are fetched and neither of row 1's.
    fetched = [url for url in fetch.asked if "/entity/" not in url and "list?" not in url]
    assert fetched == ["https://fake.test/en/first", "https://fake.test/ar/first"]


def test_the_position_pairing_would_have_asked_about_rows_that_do_not_exist():
    """PINS WHY, so the fix cannot be undone as a simplification. This is the walker's
    old expression, run directly against the same site."""
    site = BilingualSite()
    page = FetchedPage(url="https://fake.test/list?page=1", html="",
                       kind=PageKind.LISTING)

    overshooting = [index for index, _ in enumerate(site.detail_urls(page))
                    if index >= len(site.ROWS)]

    assert overshooting == [2, 3]
    with pytest.raises(SliceNotSupported):
        site.belongs_to_slice(page, 2, "Cairo")
