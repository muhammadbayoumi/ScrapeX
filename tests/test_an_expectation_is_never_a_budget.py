"""The number on the progress bar must never become a limit on the crawl.

MADAR's full rebuild made exactly 80 requests, and so had the three runs before
it. The owner asked the right question: was 80 written into the code as a cap,
when it was only ever an estimate that each run recomputes?

It was not, and the warehouse proves it — ALSWEED went from 415 requests to 808
on its next run, 393 past the number seeded from its predecessor. MADAR sits at
80 because 869 products over 51 category paths genuinely cost 80 pages, and the
loop stops on the store's own page_info.total_pages, not on a constant.

But NOTHING TESTED THAT. Not one test in this suite referenced expect_requests,
declare_frontier or expected_requests. The rule that keeps a display figure from
becoming a budget lived only in a docstring — and "it is not a budget and
nothing here enforces it" is a sentence, not a mechanism. The obvious future
edit is someone adding `if self.requests_count >= self.expected_requests:
return` as an optimisation, and every crawl would then silently stop at
whatever its last run happened to cost, reporting success.

That failure would be invisible: the count would equal the expectation exactly,
which is what a healthy finished crawl looks like.
"""

from __future__ import annotations

import httpx
import pytest

from scrapex.connectors.base import HttpFetcher, declare_frontier


@pytest.fixture()
def fetcher():
    """A real HttpFetcher whose socket is a stub. The class under test is the
    one crawls actually use — a fake fetcher here would test the fake."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="ok")

    f = HttpFetcher(min_interval_s=0.0, jitter=0.0)
    f._client = httpx.Client(transport=httpx.MockTransport(handler))
    return f


def test_a_crawl_may_fetch_more_pages_than_it_expected(fetcher):
    """THE ONE THAT MATTERS. Declare three pages, then ask for seven, and all
    seven must be answered. A crawl that stopped here would stop at exactly its
    expectation — indistinguishable from having finished."""
    declare_frontier(fetcher, 3)
    assert fetcher.expected_requests == 3

    for i in range(7):
        assert fetcher.get(f"https://example.test/p{i}").status_code == 200

    assert fetcher.requests_count == 7, (
        "the crawl stopped at its own progress estimate; the estimate is a "
        "display figure and may never bound what is fetched")
    assert fetcher.requests_count > fetcher.expected_requests


def test_the_expectation_only_ever_rises(fetcher):
    """A connector that enumerates a second frontier is adding to what it will
    fetch, not replacing it. A bar that shrank mid-crawl is the same lie in the
    other direction."""
    declare_frontier(fetcher, 10)
    declare_frontier(fetcher, 2)

    assert fetcher.expected_requests == 10


def test_the_expectation_is_counted_from_the_requests_already_spent(fetcher):
    """"Three more pages" after four spent is seven, not three. Reading a
    sitemap index costs real requests before the frontier is known, and an
    expectation that ignored them would arrive at 100% early."""
    for i in range(4):
        fetcher.get(f"https://example.test/seed{i}")
    declare_frontier(fetcher, 3)

    assert fetcher.expected_requests == 7


def test_a_fetcher_that_cannot_hear_a_frontier_is_not_broken_by_one():
    """declare_frontier is the one guard so no connector grows its own. Reaching
    straight for expect_requests once turned a progress-display improvement into
    an AttributeError that failed real magento and salla crawls."""
    class Minimal:
        pass

    declare_frontier(Minimal(), 5)          # must not raise
