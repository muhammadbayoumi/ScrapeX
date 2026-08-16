"""The wiring that turns a walk into stored evidence.

Step 4 of docs/GENERIC-FETCH-SEAM.md. `scrapex/pagewalk.py` shipped in July with
ZERO production callers, and `save_snapshot` had only ever been reached by a
human pressing a button. Nothing joined them, so nothing could crawl a generic
site automatically — which is the sentence that document opens with.

WHAT THESE TESTS ARE FOR. Three things that only this join can get wrong:

  * the scope must come from `site_profile` and from nowhere else, or it is
    enforced in two places and therefore in neither;
  * every page must reach `generic_page_snapshot` UNPARSED, because a parse
    re-run against stored evidence re-fetches nothing and that is the whole
    economics of a thirty-five-thousand-request source;
  * a page that cannot be stored must not discard the eight hundred already
    stored.

No network: the fetch is a dict lookup.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.crawlscope import CrawlScope, SliceRequired
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.pagesource import FetchedPage
from scrapex.snapshotcrawl import (
    SiteNotRegistered,
    crawl_to_snapshots,
    read_scope,
)

BASE = "https://site.test"


class TwoPageSite:
    """Two listing pages, one detail link each, and a city on every row."""

    site_key = "site.test"

    def listing_urls(self, base_url: str):
        for page in (1, 2):
            yield f"{base_url}/list?page={page}"

    def detail_urls(self, page: FetchedPage):
        number = page.url.rsplit("=", 1)[-1]
        return [f"{BASE}/entity/{number}"]

    def belongs_to_slice(self, page: FetchedPage, row_index: int, slice_of: str):
        return slice_of in page.html


PAGES = {
    f"{BASE}/list?page=1": "<html>RIYADH one</html>",
    f"{BASE}/list?page=2": "<html>JEDDAH two</html>",
    f"{BASE}/entity/1": "<html>detail one</html>",
    f"{BASE}/entity/2": "<html>detail two</html>",
}


def fetch(url: str) -> str:
    return PAGES[url]


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def register(conn, scope: str = "listing_only", slice_of: str | None = None):
    conn.execute(
        "INSERT INTO site_profile (site_key, display_name, base_url, "
        "crawl_scope, crawl_slice) VALUES (?,?,?,?,?)",
        ("site.test", "A site", BASE, scope, slice_of))
    conn.commit()


def stored_urls(conn) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT source_url FROM generic_page_snapshot ORDER BY page_snapshot_id")]


def crawl(conn, **kwargs):
    return crawl_to_snapshots(conn, TwoPageSite(), BASE, fetch=fetch,
                              listing_pages=2, detail_pages=2, slice_pages=1,
                              pace_s=0, **kwargs)


# ---- the scope, which had no reader in Python until this file ----------------

def test_the_scope_is_read_from_the_site_and_not_from_the_caller(conn):
    """M6a added `crawl_scope` and `crawl_slice` and NOTHING read them. There is
    deliberately no parameter to pass one: a scope the caller could also supply
    is enforced in two places, and therefore in neither."""
    register(conn, "listing_plus_slice", "RIYADH")

    assert read_scope(conn, "site.test") == (CrawlScope.LISTING_PLUS_SLICE, "RIYADH")


def test_a_site_nobody_registered_is_refused_rather_than_defaulted(conn):
    """The column's default is the SAFE scope, which is exactly why defaulting
    here would be wrong: a site with no row has not been ASKED, and crawling it
    cheaply still answers a question that was the owner's."""
    with pytest.raises(SiteNotRegistered, match="never been decided"):
        crawl(conn)


def test_a_slice_scope_with_no_slice_is_refused_before_the_first_request(conn):
    """`crawlscope.plan` raises it and this calls `plan` rather than re-checking
    — two copies of a rule disagree eventually. Refusing now costs nothing;
    refusing after fourteen minutes of listing pages costs fourteen minutes."""
    register(conn, "listing_plus_slice", None)

    with pytest.raises(SliceRequired):
        crawl(conn)
    assert stored_urls(conn) == [], "a refused crawl stored something"


# ---- one page in, one snapshot out -------------------------------------------

def test_every_page_reaches_storage_unparsed(conn):
    register(conn, "listing_only")

    outcome = crawl(conn)

    assert stored_urls(conn) == [f"{BASE}/list?page=1", f"{BASE}/list?page=2"]
    assert outcome.stored == 2
    assert outcome.report.listing_pages == 2
    assert outcome.report.detail_pages == 0, "listing_only fetched a detail page"

    kept = conn.execute(
        "SELECT html_content FROM generic_page_snapshot ORDER BY page_snapshot_id"
    ).fetchone()[0]
    assert kept == "<html>RIYADH one</html>", (
        "the HTML was altered on the way in — evidence that has been touched "
        "cannot settle what the page said")


def test_the_full_scope_stores_the_detail_pages_too(conn):
    register(conn, "full_then_listing")

    outcome = crawl(conn)

    assert outcome.stored == 4
    assert f"{BASE}/entity/1" in stored_urls(conn)


def test_a_slice_fetches_only_the_rows_it_named(conn):
    """The whole reason the slice scope is worth having: one city's detail pages
    without the rest."""
    register(conn, "listing_plus_slice", "RIYADH")

    outcome = crawl(conn)

    assert outcome.report.detail_pages == 1
    assert f"{BASE}/entity/1" in stored_urls(conn)
    assert f"{BASE}/entity/2" not in stored_urls(conn)


def test_the_plan_is_reported_so_the_cost_can_be_seen(conn):
    register(conn, "listing_only")

    outcome = crawl(conn)

    assert outcome.plan.scope is CrawlScope.LISTING_ONLY
    assert outcome.plan.requests == 2


# ---- what must not be lost ---------------------------------------------------

def test_a_page_that_cannot_be_stored_does_not_discard_the_rest(conn):
    """One page too large, or one URL the model refuses, must not throw away the
    eight hundred already kept — the same reasoning the walker applies to a dead
    page, one level down."""
    register(conn, "listing_only")
    broken = dict(PAGES, **{f"{BASE}/list?page=2": ""})   # min_length=1 refuses

    outcome = crawl_to_snapshots(conn, TwoPageSite(), BASE,
                                 fetch=broken.__getitem__,
                                 listing_pages=2, detail_pages=0, pace_s=0)

    assert outcome.stored == 1, "the good page was lost with the bad one"
    assert len(outcome.unstored) == 1
    assert outcome.unstored[0][0] == f"{BASE}/list?page=2"


def test_a_dead_page_is_recorded_and_the_crawl_goes_on(conn):
    register(conn, "listing_only")

    def flaky(url: str) -> str:
        if url.endswith("page=1"):
            raise TimeoutError("the site did not answer")
        return PAGES[url]

    outcome = crawl_to_snapshots(conn, TwoPageSite(), BASE, fetch=flaky,
                                 listing_pages=2, detail_pages=0, pace_s=0)

    assert outcome.stored == 1
    assert outcome.report.failures, "a dead page vanished without a record"


def test_a_ceiling_stops_the_crawl_and_says_so(conn):
    register(conn, "full_then_listing")

    outcome = crawl(conn, max_requests=1)

    assert outcome.stored == 1
    assert outcome.report.requests <= 2


# ---- the frontier ------------------------------------------------------------

def test_the_frontier_is_declared_before_anything_is_fetched(conn):
    """So the Activity panel's denominator is a count and not a guess. Unlike
    GPP — whose frontier grows material by material, and which declines to
    declare one for that reason — this site's size is known up front."""
    register(conn, "listing_only")
    told: list[int] = []

    class Fetcher:
        def expect_requests(self, pages: int) -> None:
            told.append(pages)

    crawl(conn, fetcher=Fetcher())

    assert told == [2]


def test_a_slice_declares_the_slice_s_size_and_not_the_whole_site_s(conn):
    """WHY `crawlscope.plan` IS CALLED AND NOT RE-IMPLEMENTED, made observable.

    The walker checks the scope again for itself, so skipping `plan` here still
    refuses a slice with no slice named — that duplication is deliberate. What
    it does NOT protect is the number: only `plan` knows that a slice crawl
    costs `listing + slice`, not `listing + every detail page`. Get it from
    anywhere else and the progress bar counts to a total the crawl will never
    reach, which is the bar running backwards that GPP refuses to ship at all.
    """
    register(conn, "listing_plus_slice", "RIYADH")
    told: list[int] = []

    class Fetcher:
        def expect_requests(self, pages: int) -> None:
            told.append(pages)

    outcome = crawl(conn, fetcher=Fetcher())

    assert told == [3], "2 listing pages + 1 sliced detail page, not 2 + 2"
    assert outcome.plan.requests == 3


def test_a_fetcher_that_cannot_hear_the_frontier_is_not_an_error(conn):
    """`declare_frontier` exists because reaching for `expect_requests` directly
    once turned a progress display into an AttributeError that failed real
    crawls. A display fact must never be able to do that."""
    register(conn, "listing_only")

    assert crawl(conn, fetcher=object()).stored == 2
