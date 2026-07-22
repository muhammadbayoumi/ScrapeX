"""The polite transport, under the conditions a large crawl actually meets.

globalpetrolprices needs ~845 country pages to get original local-currency
prices instead of the site's own USD conversion. The fetcher's docstring
promised "retrying" and contained no retry code at all: a single 429 raised and
killed the whole run.

These tests drive the real HttpFetcher against a stubbed transport, so the
retry, backoff, conditional-request and circuit-breaker behaviour is exercised
rather than asserted about.
"""
from __future__ import annotations

import httpx
import pytest

from scrapex.connectors.base import CrawlBlocked, HttpFetcher

URL = "https://example.test/diesel_prices/"


def fetcher_over(responses, **kwargs) -> tuple[HttpFetcher, list[httpx.Request]]:
    """An HttpFetcher whose transport replays `responses` in order."""
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = queue.pop(0) if queue else httpx.Response(200, text="last")
        if isinstance(item, Exception):
            raise item
        return item

    # No real sleeping: these tests are about the decisions, not the clock.
    kwargs.setdefault("min_interval_s", 0.0)
    kwargs.setdefault("jitter", 0.0)
    fetcher = HttpFetcher(**kwargs)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler),
                                   follow_redirects=True)
    return fetcher, seen


# ---- retrying, which did not exist --------------------------------------------

def test_a_rate_limit_is_retried_instead_of_killing_the_crawl():
    fetcher, seen = fetcher_over([
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, text="ok"),
    ])

    response = fetcher.get(URL)

    assert response.status_code == 200 and response.text == "ok"
    assert len(seen) == 2
    assert fetcher.retry_count == 1


def test_a_server_error_is_retried():
    fetcher, seen = fetcher_over([httpx.Response(503), httpx.Response(200, text="ok")])
    assert fetcher.get(URL).status_code == 200
    assert len(seen) == 2


def test_a_dropped_connection_is_retried():
    fetcher, seen = fetcher_over([
        httpx.ConnectError("connection reset"),
        httpx.Response(200, text="ok"),
    ])
    assert fetcher.get(URL).text == "ok"
    assert len(seen) == 2


def test_a_client_error_is_not_retried():
    """404 means the page is not there. Asking four more times is rude and
    changes nothing."""
    fetcher, seen = fetcher_over([httpx.Response(404)] * 4)

    with pytest.raises(httpx.HTTPStatusError):
        fetcher.get(URL)

    assert len(seen) == 1


def test_retry_after_is_honoured_over_our_own_backoff(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", slept.append)
    fetcher, _ = fetcher_over([
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200),
    ], min_interval_s=1.0)

    fetcher.get(URL)

    assert 7.0 in slept, f"the server named a delay and we ignored it: {slept}"


def test_an_absurd_retry_after_is_capped(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", slept.append)
    fetcher, _ = fetcher_over([
        httpx.Response(429, headers={"Retry-After": "86400"}),
        httpx.Response(200),
    ])

    fetcher.get(URL)

    assert max(slept) <= HttpFetcher.MAX_BACKOFF_S, "a day-long sleep hangs the crawl"


# ---- the circuit breaker ------------------------------------------------------

def test_repeated_refusals_stop_the_run_instead_of_hammering():
    """After enough refusals the answer is no. Continuing is what turns a
    temporary rate limit into a lasting ban."""
    fetcher, seen = fetcher_over([httpx.Response(403)] * 40, max_attempts=1)

    with pytest.raises(CrawlBlocked, match="refusals in a row"):
        for _ in range(HttpFetcher.BLOCK_LIMIT + 3):
            try:
                fetcher.get(URL)
            except httpx.HTTPStatusError:
                pass

    assert len(seen) <= HttpFetcher.BLOCK_LIMIT, \
        "we kept knocking after the site said no"


def test_a_success_clears_the_refusal_streak():
    """One 403 on a page that needs auth must not arm the breaker for the rest
    of an otherwise healthy crawl."""
    fetcher, _ = fetcher_over(
        [httpx.Response(403), httpx.Response(200)] * 10, max_attempts=1)

    for _ in range(8):
        try:
            fetcher.get(URL)
        except httpx.HTTPStatusError:
            pass   # the 403s; the breaker must not trip on an alternating pattern


# ---- conditional requests: why a weekly 845-page crawl stays cheap -----------

def test_a_second_visit_sends_the_stored_validators():
    fetcher, seen = fetcher_over([
        httpx.Response(200, text="body", headers={"ETag": 'W/"abc"',
                                                  "Last-Modified": "Mon, 13 Jul 2026 00:00:00 GMT"}),
        httpx.Response(304),
    ])

    fetcher.get(URL)
    fetcher.get(URL)

    assert seen[0].headers.get("If-None-Match") is None, "nothing to send on a first visit"
    assert seen[1].headers["If-None-Match"] == 'W/"abc"'
    assert seen[1].headers["If-Modified-Since"] == "Mon, 13 Jul 2026 00:00:00 GMT"


def test_an_unchanged_page_answers_304_and_is_counted():
    fetcher, _ = fetcher_over([
        httpx.Response(200, text="body", headers={"ETag": '"v1"'}),
        httpx.Response(304),
    ])

    fetcher.get(URL)
    second = fetcher.get(URL)

    assert second.status_code == 304
    assert second.text == "", "a 304 carries no body — that is the saving"
    assert fetcher.not_modified_count == 1


def test_a_304_is_not_treated_as_a_refusal():
    """It is the friendliest answer a server can give; arming the breaker on it
    would stop a crawl precisely when it is going well."""
    fetcher, _ = fetcher_over(
        [httpx.Response(200, headers={"ETag": '"v1"'})] + [httpx.Response(304)] * 30)

    fetcher.get(URL)
    for _ in range(20):
        assert fetcher.get(URL).status_code == 304


def test_validators_survive_between_crawls():
    """The point of keeping them: a NEW fetcher next week starts able to ask
    'has this changed?' rather than downloading all 845 pages again."""
    first, _ = fetcher_over([httpx.Response(200, headers={"ETag": '"v1"'})])
    first.get(URL)
    kept = first.validators()
    assert kept[URL]["ETag"] == '"v1"'

    later, seen = fetcher_over([httpx.Response(304)])
    later.remember_validators(kept)
    later.get(URL)

    assert seen[0].headers["If-None-Match"] == '"v1"'


# ---- pacing -------------------------------------------------------------------

def test_the_interval_is_jittered_not_metronomic(monkeypatch):
    """Identical gaps are a machine signature and sit in phase with whatever
    window a rate limiter counts in."""
    slept: list[float] = []
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", slept.append)
    fetcher, _ = fetcher_over([httpx.Response(200)] * 12,
                              min_interval_s=1.0, jitter=0.3)

    for _ in range(10):
        fetcher.get(URL)

    waits = [s for s in slept if s > 0]
    assert len(set(waits)) > 1, f"every gap identical: {waits}"
    assert all(0.7 <= w <= 1.3 for w in waits), f"jitter left the band: {waits}"


def test_politeness_can_be_widened_for_a_large_crawl(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", slept.append)
    fetcher, _ = fetcher_over([httpx.Response(200)] * 3, min_interval_s=5.0, jitter=0.0)

    fetcher.get(URL)
    fetcher.get(URL)

    assert any(w >= 4.9 for w in slept), "the configured interval was not applied"


# ---- the live-progress hook --------------------------------------------------
#
# A 450-page country crawl used to be a quarter hour of total silence: the job
# showed 0/1 sources, zero requests and a start-time heartbeat while everything
# was in fact fine — indistinguishable from a hang. The hook is how the job row
# gets a pulse. Its contract: fires per COMPLETED request with (count, url),
# and its failure is the display's problem, never the crawl's.

def test_the_progress_hook_fires_per_completed_request():
    fetcher, _ = fetcher_over([httpx.Response(200, text="a"),
                               httpx.Response(200, text="b")])
    ticks: list[tuple[int, str]] = []
    fetcher.on_request = lambda count, url: ticks.append((count, url))

    fetcher.get(URL)
    fetcher.get(URL)

    assert ticks == [(1, URL), (2, URL)]


def test_a_retried_request_ticks_per_wire_attempt_like_the_counter_it_mirrors():
    """Three wire attempts for one page tick three times, because the hook
    mirrors requests_count — the F5 wire-request accounting, where a retried
    request DID cost the server two extra hits. For liveness this is also the
    right pulse: each attempt proves the crawl is alive, and a backoff between
    them is precisely when a watcher most wants a recent heartbeat."""
    fetcher, _ = fetcher_over([httpx.Response(503), httpx.Response(503),
                               httpx.Response(200, text="finally")])
    ticks: list[int] = []
    fetcher.on_request = lambda count, url: ticks.append(count)

    fetcher.get(URL)

    assert ticks == [1, 2, 3]
    assert fetcher.requests_count == 3


def test_a_broken_hook_never_breaks_the_crawl():
    fetcher, _ = fetcher_over([httpx.Response(200, text="fine")])
    fetcher.on_request = lambda count, url: 1 / 0

    response = fetcher.get(URL)

    assert response.status_code == 200, "a progress display took the crawl down"
