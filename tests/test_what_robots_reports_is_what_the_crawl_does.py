"""#1413: the robots answer the owner is shown is the one the crawl acts on.

Four defects, each measured on the fetcher before this file existed:

1. An UNREADABLE robots.txt (a 503, a 500, a dropped connection) was cached as
   "no rules" and nothing was written, so every robots check stopped in silence --
   under `obey` too. Ruled: treated as if the site had no file, the tool's own
   rules apply, and the run's log says so once per host. A 404 is still "no file",
   with nothing written.
   RE-RULED FOR THE SERVER AND THE NETWORK (#1585, ES-2): RFC 9309 §2.3.1.4 makes a
   5xx or no answer at all "complete disallow", so those now PAUSE the site's run
   with `RobotsUnreachable` and no page is fetched. A 4xx (§2.3.1.3) keeps #1413's
   answer exactly: crawled under the tool's own rules, said once at WARNING.
2. The site's Crawl-delay was applied only when the tool-wide `crawl_honour_delay`
   was on, whatever the source chose. Ruled: under `obey` the source's rule wins.
3. `robots_custom.crawl_delay_s` was only a floor: the site's delay raised it, so a
   custom 2s under a 10s site ran at 10s while `GET /robots` reported 2s. Ruled:
   the owner's per-source delay is applied as set, and the override is written down
   when the site asked for more.
4. `HttpFetcher.fresh_session` dropped the robots choice, the custom rule and the
   tool default, so a source set to `obey` stopped obeying on a fresh session.

Driven through the real HttpFetcher over a stubbed transport, as
tests/test_http_fetcher.py does, because the defects lived in what the fetcher
did, not in what any function returned.
"""
from __future__ import annotations

import math

import httpx
import pytest

from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import (
    CrawlBlocked,
    HttpFetcher,
    RobotsDisallowed,
    RobotsUnreachable,
    resolve_fetcher,
)
from scrapex.robots import RobotsChoice, RobotsCustom, decide, inspect, is_unreachable
from scrapex.vocab import ExtractKind, ExtractScope

HOST = "shop.test"
PAGE = f"https://{HOST}/products/1"
PRIVATE = f"https://{HOST}/private/thing"
SLOW_SITE = "User-agent: *\nCrawl-delay: 10\nDisallow: /private/\n"
#: Far from zero for the reason tests/test_http_fetcher.py gives at FROZEN_CLOCK.
FROZEN_CLOCK = 1_000.0


def _over(robots, fetcher: HttpFetcher) -> tuple[HttpFetcher, list[str]]:
    """Point `fetcher` at a site whose robots.txt answers `robots`.

    `robots` is the file's text (served 200), an `httpx.Response`, or an
    exception the transport raises -- the three ways a robots fetch ends.
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/robots.txt"):
            if isinstance(robots, Exception):
                raise robots
            if isinstance(robots, httpx.Response):
                return robots
            return httpx.Response(200, text=robots)
        seen.append(str(request.url))
        return httpx.Response(200, text="ok")

    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler),
                                   follow_redirects=True)
    return fetcher, seen


def _fetcher(robots, **kwargs) -> tuple[HttpFetcher, list[str]]:
    kwargs.setdefault("min_interval_s", 0.0)
    kwargs.setdefault("jitter", 0.0)
    return _over(robots, HttpFetcher(**kwargs))


def _clocked(monkeypatch) -> list[float]:
    """A clock that advances only by what the pacer sleeps."""
    now = [FROZEN_CLOCK]
    slept: list[float] = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds
    monkeypatch.setattr("scrapex.connectors.base.time.monotonic", lambda: now[0])
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", sleep)
    return slept


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    """A 10s Crawl-delay is the point of these tests, not something to wait out."""
    _clocked(monkeypatch)


def entry(**over) -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="TESTSHOP", source_name="Test Shop",
        base_url=f"https://{HOST}", family="zid-html",
        currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                             scope=ExtractScope.CENSUS)],
        **over))


def _unreadable_notes(fetcher: HttpFetcher) -> list[str]:
    return [w for w in fetcher.degradations if "could not be read" in w]


# ---- 1. an unreadable robots.txt is no robots.txt, said out loud --------------

#: The 4xx answers #1413's ruling still governs (RFC 9309 §2.3.1.3). The 503, 500 and
#: dropped connection that stood here moved to UNREACHABLE below (#1585): they pause.
UNREADABLE = [
    pytest.param(httpx.Response(403), "HTTP 403", id="403"),
    pytest.param(httpx.Response(410), "HTTP 410", id="410"),
    pytest.param(httpx.Response(401), "HTTP 401", id="401"),
    pytest.param(httpx.Response(429), "HTTP 429", id="429"),
]
#: RFC 9309 §2.3.1.4: "server or network errors". The crawl pauses on every one.
UNREACHABLE = [
    pytest.param(httpx.Response(503), "HTTP 503", id="503"),
    pytest.param(httpx.Response(500), "HTTP 500", id="500"),
    pytest.param(httpx.Response(502), "HTTP 502", id="502"),
    pytest.param(httpx.Response(599), "HTTP 599", id="599"),
    pytest.param(httpx.ConnectError("connection refused"), "ConnectError", id="exception"),
    pytest.param(httpx.ReadTimeout("timed out"), "ReadTimeout", id="timeout"),
]
CHOICES = [
    pytest.param({}, id="default"),
    pytest.param({"robots_choice": "obey"}, id="obey"),
    pytest.param({"robots_choice": "custom",
                  "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 3.0}},
                 id="custom"),
    pytest.param({"obey_disallow": True}, id="default-that-obeys"),
]


@pytest.mark.parametrize("choice", CHOICES)
@pytest.mark.parametrize("robots,named", UNREADABLE)
def test_an_unreadable_file_is_written_down_once_per_host(robots, named, choice):
    fetcher, seen = _fetcher(robots, min_interval_s=0.0, **choice)

    fetcher.get(PAGE)
    fetcher.get(PAGE + "?again=1")

    notes = _unreadable_notes(fetcher)
    assert len(notes) == 1, f"one host, {len(notes)} lines: {fetcher.degradations}"
    # A WARNING, not a note: `degradations` is what the run logs at WARNING
    # (capture.py), `robots_warnings` only at INFO.
    assert not any("could not be read" in w for w in fetcher.robots_warnings), (
        fetcher.robots_warnings)
    assert named in notes[0], f"the line does not say what went wrong: {notes[0]}"
    assert HOST in notes[0], "the line does not say which site"
    assert "tool's own rules apply" in notes[0], notes[0]
    assert len(seen) == 2


@pytest.mark.parametrize("choice", CHOICES)
@pytest.mark.parametrize("robots,named", UNREADABLE)
def test_an_unreadable_file_is_treated_as_no_file_under_every_choice(robots, named,
                                                                     choice):
    """The tool's own rules apply: a path the site may well disallow is fetched,
    because there is no readable rule to refuse it with, and the pace is ours."""
    fetcher, seen = _fetcher(robots, min_interval_s=1.5, **choice)

    response = fetcher.get(PRIVATE)

    assert response.status_code == 200
    assert seen == [PRIVATE]
    assert fetcher._min_interval_s == 1.5, "an unreadable file moved the pace"


def test_the_unreadable_line_names_the_pace_the_run_used_instead():
    fetcher, _ = _fetcher(httpx.Response(403), min_interval_s=2.5)

    fetcher.get(PAGE)

    assert "2.5s" in _unreadable_notes(fetcher)[0]


@pytest.mark.parametrize("choice", CHOICES)
def test_a_404_is_still_no_file_and_still_says_nothing(choice):
    """A 404 is an answer, not a failure: the site has no file."""
    fetcher, seen = _fetcher(httpx.Response(404), min_interval_s=1.0, **choice)

    fetcher.get(PRIVATE)

    assert fetcher.robots_warnings == []
    assert fetcher.degradations == [], "a 404 was written down as unreadable"
    assert seen == [PRIVATE]
    assert fetcher._min_interval_s == 1.0


def test_a_readable_file_writes_no_unreadable_line():
    fetcher, _ = _fetcher("User-agent: *\nAllow: /\n")

    fetcher.get(PAGE)

    assert _unreadable_notes(fetcher) == []


def test_an_unreadable_file_on_one_host_does_not_speak_for_another():
    """One line per HOST, so a second host that also fails gets its own."""
    fetcher, _ = _fetcher(httpx.Response(403))

    fetcher.get(PAGE)
    fetcher.get("https://other.test/x")

    notes = _unreadable_notes(fetcher)
    assert len(notes) == 2, notes
    assert any(n.startswith(f"{HOST}:") for n in notes)
    assert any(n.startswith("other.test:") for n in notes)


# ---- 1b. an unreachable robots.txt pauses the site's run (#1585) ---------------

#: Every robots choice a source can hold, the custom one with NO rule stored included:
#: the pause comes before any choice is consulted, so that one must pause too rather
#: than raise its "no custom rule" ValueError.
EVERY_CHOICE = [
    *CHOICES,
    pytest.param({"robots_choice": "custom", "robots_custom": None},
                 id="custom-with-no-rule"),
    pytest.param({"honour_crawl_delay": False}, id="ignore-the-delay"),
]


def _counting(robots) -> tuple[HttpFetcher, list[str]]:
    """A fetcher whose site records EVERY request, robots.txt included."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if str(request.url).endswith("/robots.txt"):
            if isinstance(robots, Exception):
                raise robots
            return robots
        return httpx.Response(200, text="ok")

    fetcher = HttpFetcher(min_interval_s=0.0, jitter=0.0)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))
    return fetcher, asked


@pytest.mark.parametrize("choice", EVERY_CHOICE)
@pytest.mark.parametrize("robots,named", UNREACHABLE)
def test_an_unreachable_file_pauses_the_run_under_every_choice(robots, named, choice):
    """RFC 9309 §2.3.1.4: complete disallow. No page goes out, whatever the source
    chose -- there is no rule of the site's for a choice to act on."""
    fetcher, seen = _fetcher(robots, **choice)

    with pytest.raises(RobotsUnreachable) as raised:
        fetcher.get(PAGE)

    assert seen == [], "a page went out after robots.txt could not be reached"
    assert fetcher.requests_count == 0
    said = str(raised.value)
    assert HOST in said and named in said, said
    assert "RFC 9309 §2.3.1.4" in said and "paused" in said, said


@pytest.mark.parametrize("robots,named", UNREACHABLE)
def test_the_pause_is_a_crawl_blocked_so_every_page_guard_lets_it_through(robots,
                                                                          named):
    """Every connector's per-page guard re-raises CrawlBlocked by name; a fresh
    exception type would be filed as one dead page and the walk would go on."""
    fetcher, _ = _fetcher(robots)

    with pytest.raises(CrawlBlocked):
        fetcher.get(PAGE)


@pytest.mark.parametrize("robots,named", UNREACHABLE)
def test_an_unreachable_file_is_read_once_and_every_later_page_pauses_too(robots,
                                                                          named):
    """Cached per host, as a refusal is: page two re-raises without asking the site
    for robots.txt again, and without asking for the page either. The one READ is
    its attempts -- retried like a page, so a 599 that `_request` would not retry is
    asked once -- and nothing after them."""
    fetcher, asked = _counting(robots)
    retried = (isinstance(robots, Exception)
               or robots.status_code in HttpFetcher.RETRY_STATUSES)

    for n in range(3):
        with pytest.raises(RobotsUnreachable, match=named):
            fetcher.get(f"{PAGE}?page={n}")

    attempts = fetcher._max_attempts if retried else 1
    assert asked == [f"https://{HOST}/robots.txt"] * attempts, asked


@pytest.mark.parametrize("robots,named", UNREACHABLE)
def test_an_unreachable_file_writes_no_crawled_anyway_line(robots, named):
    """The 4xx sentence says the run went on under the tool's own rules. Here it did
    not, so that line would be a false account of the run."""
    fetcher, _ = _fetcher(robots)

    with pytest.raises(RobotsUnreachable):
        fetcher.get(PAGE)

    assert fetcher.degradations == [], fetcher.degradations
    assert fetcher.robots_warnings == [], fetcher.robots_warnings


def test_an_unreachable_file_on_one_host_does_not_pause_another():
    """Per HOST, like every robots answer: a second site whose file reads crawls."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == HOST and request.url.path == "/robots.txt":
            return httpx.Response(503)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text="ok")

    fetcher = HttpFetcher(min_interval_s=0.0, jitter=0.0)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(RobotsUnreachable):
        fetcher.get(PAGE)
    assert fetcher.get("https://other.test/x").status_code == 200
    with pytest.raises(RobotsUnreachable):
        fetcher.get(PAGE)


def test_the_robots_read_that_failed_still_owes_the_pace(monkeypatch):
    """Unchanged by the pause (#1302): the read is paced like a request, so a site
    that answered 503 is not asked again sooner than the pace allows. Its retries
    back off as a page's do -- 2x and 4x the pace -- and the pace is owed after the
    last of them."""
    slept = _clocked(monkeypatch)
    fetcher, _ = _fetcher(httpx.Response(503), min_interval_s=3.0)

    with pytest.raises(RobotsUnreachable):
        fetcher.get(PAGE)
    fetcher._throttle()

    assert slept == [6.0, 12.0, 3.0], slept


@pytest.mark.parametrize("status,pauses", [
    (500, True), (503, True), (599, True),
    (400, False), (403, False), (404, False), (410, False), (429, False),
    (499, False), (200, False), (301, False), (600, False),
])
def test_only_the_server_counts_among_statuses(status, pauses):
    """The boundary, at both edges: §2.3.1.4 is 5xx; §2.3.1.3 is 4xx."""
    assert is_unreachable(status) is pauses


@pytest.mark.parametrize("error,pauses", [
    pytest.param(httpx.ConnectError("refused"), True, id="ConnectError"),
    pytest.param(httpx.ReadTimeout("slow"), True, id="ReadTimeout"),
    pytest.param(httpx.ProxyError("403 Forbidden"), True, id="ProxyError"),
    pytest.param(httpx.RemoteProtocolError("hung up"), True, id="RemoteProtocolError"),
    pytest.param(httpx.TooManyRedirects("loop"), False, id="TooManyRedirects"),
    pytest.param(httpx.DecodingError("bad gzip"), False, id="DecodingError"),
    pytest.param(httpx.InvalidURL("no host"), False, id="InvalidURL"),
    pytest.param(UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"), False,
                 id="UnicodeDecodeError"),
    pytest.param(ValueError("anything else"), False, id="ValueError"),
])
def test_only_the_network_counts_among_exceptions(error, pauses):
    """§2.3.1.4 names "network errors": `httpx.TransportError` and nothing else. Too
    many redirects is §2.3.1.2's "unavailable", and a file that would not decode was
    answered -- neither is the network failing."""
    assert is_unreachable(error) is pauses


# ---- the read is retried like a page before it pauses (#1585) -------------------

def _scripted(*answers) -> tuple[HttpFetcher, list[str]]:
    """A fetcher whose robots.txt gives `answers` in turn: a response or an exception
    per attempt, the last repeated. Every request is recorded."""
    asked: list[str] = []
    queue = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        if request.url.path == "/robots.txt":
            answer = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return httpx.Response(200, text="ok")

    fetcher = HttpFetcher(min_interval_s=1.0, jitter=0.0)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))
    return fetcher, asked


@pytest.mark.parametrize("first", [
    pytest.param(httpx.ConnectError("dropped"), id="ConnectError"),
    pytest.param(httpx.ReadTimeout("slow"), id="ReadTimeout"),
    pytest.param(httpx.Response(503), id="503"),
    pytest.param(httpx.Response(502), id="502"),
])
def test_one_failed_attempt_then_an_answer_crawls(first):
    """THE OWNER'S RULING: one dropped connection does not pause a site for the day.
    The second attempt's 404 is the answer -- no file -- and the page goes out."""
    fetcher, asked = _scripted(first, httpx.Response(404))

    assert fetcher.get(PAGE).status_code == 200

    assert asked == ["/robots.txt", "/robots.txt", "/products/1"], asked
    assert fetcher.retry_count == 1, "the retry was not counted"
    assert fetcher.degradations == [], fetcher.degradations


def test_a_retried_read_that_then_serves_the_file_applies_its_rules():
    fetcher, asked = _scripted(httpx.Response(503),
                               httpx.Response(200, text=SLOW_SITE))
    fetcher._obey_disallow = True

    with pytest.raises(RobotsDisallowed):
        fetcher.get(PRIVATE)

    assert asked == ["/robots.txt", "/robots.txt"], asked
    assert fetcher._min_interval_s == 10.0, "the file read on the retry was not used"


@pytest.mark.parametrize("attempts", [1, 2, 3, 5])
def test_every_attempt_fails_and_then_it_pauses(attempts):
    """N attempts, the fetcher's own `max_attempts`, and no page: the pause comes only
    after the last one."""
    fetcher, asked = _scripted(httpx.ConnectError("refused"))
    fetcher._max_attempts = attempts

    with pytest.raises(RobotsUnreachable, match="ConnectError"):
        fetcher.get(PAGE)

    assert asked == ["/robots.txt"] * attempts, asked
    assert fetcher.retry_count == attempts - 1
    assert fetcher.requests_count == 0, "a robots read was counted as a crawl request"


def test_the_last_attempts_answer_decides():
    """A 503 then a 403: the read ended in a 4xx, so the crawl goes on and says so."""
    fetcher, asked = _scripted(httpx.Response(503), httpx.Response(403))

    assert fetcher.get(PAGE).status_code == 200

    assert asked == ["/robots.txt", "/robots.txt", "/products/1"], asked
    assert any("could not be read (HTTP 403)" in w for w in fetcher.degradations)


def test_a_429_is_retried_like_a_page_and_then_read_as_a_4xx():
    """`_request` retries a 429, so the read does; ending on one is §2.3.1.3."""
    fetcher, asked = _scripted(httpx.Response(429))

    assert fetcher.get(PAGE).status_code == 200

    assert asked.count("/robots.txt") == fetcher._max_attempts, asked
    assert any("could not be read (HTTP 429)" in w for w in fetcher.degradations)


@pytest.mark.parametrize("status", [404, 403, 410, 401, 400])
def test_a_status_a_page_is_not_retried_on_is_read_once(status):
    """Only `RETRY_STATUSES` are asked again, as on a page."""
    fetcher, asked = _scripted(httpx.Response(status))

    fetcher.get(PAGE)

    assert asked.count("/robots.txt") == 1, asked


@pytest.mark.parametrize("error", [
    pytest.param(httpx.TooManyRedirects("loop"), id="TooManyRedirects"),
    pytest.param(httpx.DecodingError("bad gzip"), id="DecodingError"),
])
def test_a_failure_that_is_not_the_networks_is_not_retried_and_crawls(error):
    """`_request` lets these through unretried; so does the read. Neither is a network
    error, so §2.3.1.3 applies: the crawl goes on and the run's log says why."""
    fetcher, asked = _scripted(error)

    assert fetcher.get(PAGE).status_code == 200

    assert asked == ["/robots.txt", "/products/1"], asked
    [line] = _unreadable_notes(fetcher)
    assert type(error).__name__ in line, line


def test_the_retry_backs_off_as_a_page_does_and_honours_retry_after(monkeypatch):
    """The same `_sleep_backoff`: a named Retry-After is waited, then the pace."""
    slept = _clocked(monkeypatch)
    fetcher, _ = _scripted(httpx.Response(503, headers={"Retry-After": "7"}),
                           httpx.Response(404))

    fetcher.get(PAGE)

    assert slept[0] == 7.0, slept


def test_the_retried_read_happens_once_per_host_under_the_lock():
    """The cache is filled after the LAST attempt: a second page asks nothing."""
    fetcher, asked = _scripted(httpx.Response(503), httpx.Response(404))

    fetcher.get(PAGE)
    fetcher.get(PAGE + "?again=1")

    assert asked.count("/robots.txt") == 2, asked


@pytest.mark.parametrize("choice", list(RobotsChoice))
def test_decide_pauses_an_unreachable_report_under_every_choice(choice):
    """What `GET /robots` reports comes from `decide()`, so it must say "not fetched"
    where the fetcher raises -- before the custom-rule refusal, as the fetcher does."""
    report = inspect(PAGE, None, unreadable="HTTP 503", unreachable=True)

    verdict = decide(report, choice, custom=None, tool_default_obeys=False,
                     url_disallowed=False)

    assert verdict.may_fetch is False
    assert "RFC 9309" in verdict.reason and "paused" in verdict.reason, verdict.reason
    assert "could not be reached" in report.summary(), report.summary()
    assert "pauses" in report.summary(), report.summary()


def test_decide_still_crawls_past_a_4xx_report():
    report = inspect(PAGE, None, unreadable="HTTP 403")

    verdict = decide(report, RobotsChoice.OBEY, url_disallowed=True)

    assert verdict.may_fetch is True
    assert report.unreachable is False
    assert "could not be read (HTTP 403)" in report.summary()


# ---- 2. under `obey`, the source's rule wins over the tool-wide switch --------

def test_obey_applies_the_sites_delay_when_the_switch_is_off():
    fetcher, _ = _fetcher(SLOW_SITE, robots_choice="obey", honour_crawl_delay=False)

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == 10.0, "obey did not apply the site's delay"
    [line] = [w for w in fetcher.robots_warnings if "crawl delay" in w]
    assert "set to obey" in line and "switch" in line, line
    assert "IGNORED" not in line, line
    assert not line.endswith("— honoured"), (
        "the line reads like the switch is on; it must say why the run is slow")


def test_obey_waits_the_sites_delay_before_page_one_with_the_switch_off(monkeypatch):
    slept = _clocked(monkeypatch)
    fetcher, _ = _fetcher(SLOW_SITE, robots_choice="obey", honour_crawl_delay=False)

    fetcher.get(PAGE)

    assert slept == [10.0], slept


def test_obey_with_the_switch_on_says_the_plain_honoured_line():
    fetcher, _ = _fetcher(SLOW_SITE, robots_choice="obey", honour_crawl_delay=True)

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == 10.0
    assert f"{HOST}: robots.txt asks for a 10s crawl delay — honoured" \
        in fetcher.robots_warnings


def test_the_default_still_follows_the_switch_when_it_is_off():
    """Unchanged for a source that said nothing: the owner's per-run choice."""
    fetcher, _ = _fetcher(SLOW_SITE, min_interval_s=1.0, honour_crawl_delay=False)

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == 1.0
    assert any("IGNORED at your request" in w for w in fetcher.robots_warnings)


# ---- 3. the owner's custom delay is applied as set ----------------------------

def test_a_custom_delay_below_the_sites_is_applied_as_set():
    source = entry(robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": 2.0})
    fetcher, _ = _over(SLOW_SITE, resolve_fetcher(source, {"min_interval_s": 1.0}))

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == 2.0, (
        "the site's 10s raised the owner's custom 2s again")
    [line] = [w for w in fetcher.robots_warnings if "crawl delay" in w]
    assert "10s" in line and "2s" in line, f"the line must name both numbers: {line}"
    assert "custom rule" in line, line


def test_page_one_waits_the_custom_delay_not_the_sites(monkeypatch):
    slept = _clocked(monkeypatch)
    source = entry(robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": 2.0})
    fetcher, _ = _over(SLOW_SITE, resolve_fetcher(source, {"min_interval_s": 1.0}))
    fetcher._jitter = 0.0

    fetcher.get(PAGE)

    assert slept == [2.0], slept


def test_a_custom_delay_above_the_sites_is_applied_and_needs_no_warning():
    source = entry(robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": 12.0})
    fetcher, _ = _over(SLOW_SITE, resolve_fetcher(source, {"min_interval_s": 1.0}))

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == 12.0
    assert not any("crawl delay" in w for w in fetcher.robots_warnings), (
        fetcher.robots_warnings)


def test_a_custom_delay_reaches_a_fetcher_built_without_resolve_fetcher():
    """`decide()`'s delay is applied by the fetcher itself, not only folded in by
    `resolve_fetcher`: the agreement holds for any caller."""
    fetcher, _ = _fetcher(SLOW_SITE, robots_choice="custom",
                          robots_custom={"enforce_disallow": False, "crawl_delay_s": 4.0})

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == 4.0


def test_a_custom_rule_with_a_null_delay_still_takes_the_sites():
    source = entry(robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": None})
    fetcher, _ = _over(SLOW_SITE, resolve_fetcher(source, {"min_interval_s": 1.0}))

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == 10.0


@pytest.mark.parametrize("pace", [10.0, 15.0], ids=["equal", "slower"])
def test_a_site_delay_no_longer_than_the_pace_changes_nothing_and_says_nothing(pace):
    """The site asks for 10s; the pace in force is already that or slower. Nothing
    moves, so no line may claim the site's delay was honoured."""
    fetcher, _ = _fetcher(SLOW_SITE, min_interval_s=pace)

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == pace
    assert not any("crawl delay" in w for w in fetcher.robots_warnings), (
        fetcher.robots_warnings)


@pytest.mark.parametrize("custom_delay", [10.0, 12.0], ids=["equal", "above"])
def test_a_custom_delay_at_or_above_the_sites_needs_no_line_on_a_bare_fetcher(
        custom_delay):
    """Built WITHOUT `resolve_fetcher`, so the pace starts at 0 and only the custom
    branch of `_apply_site_delay` can keep the log quiet."""
    fetcher, _ = _fetcher(SLOW_SITE, robots_choice="custom",
                          robots_custom={"enforce_disallow": False,
                                         "crawl_delay_s": custom_delay})

    fetcher.get(PAGE)

    assert fetcher._min_interval_s == custom_delay
    assert not any("crawl delay" in w for w in fetcher.robots_warnings), (
        fetcher.robots_warnings)


def test_custom_with_no_rule_stored_is_still_refused_on_a_site_with_a_delay():
    """Refused, as `decide()` refuses it -- never a pace picked in its place.
    And refused every time: the host is cached only after the decision."""
    fetcher, seen = _fetcher(SLOW_SITE, robots_choice="custom", robots_custom=None)

    for _ in range(2):
        with pytest.raises(ValueError, match="custom robots rule"):
            fetcher.get(PAGE)
    assert seen == [], "a page went out under a rule that does not exist"


def test_custom_with_no_rule_stored_reads_robots_txt_once_not_per_page():
    """The refusal is remembered per host. Uncached, every page fetched robots.txt
    again -- unpaced, since the pace never got set -- and collected nothing."""
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        if str(request.url).endswith("/robots.txt"):
            return httpx.Response(200, text=SLOW_SITE)
        return httpx.Response(200, text="ok")

    fetcher = HttpFetcher(min_interval_s=0.0, jitter=0.0, robots_choice="custom",
                          robots_custom=None)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))

    for n in range(3):
        with pytest.raises(ValueError, match="custom robots rule"):
            fetcher.get(f"{PAGE}?page={n}")
    assert fetched == [f"https://{HOST}/robots.txt"], fetched


def test_custom_with_no_rule_stored_crawls_a_site_that_asks_for_no_delay():
    """Unchanged: on a site with no Crawl-delay the only question the rule answers
    is a disallowed path, and that is where the refusal stays."""
    fetcher, seen = _fetcher("User-agent: *\nAllow: /\n", robots_choice="custom",
                             robots_custom=None)

    assert fetcher.get(PAGE).status_code == 200
    assert seen == [PAGE]


# ---- what `decide()` reports is what the fetcher applies ----------------------

AGREEMENT = [
    pytest.param("default", None, True, id="default"),
    pytest.param("default", None, False, id="ignore"),
    pytest.param("obey", None, True, id="obey"),
    pytest.param("obey", None, False, id="obey-switch-off"),
    pytest.param("custom", {"enforce_disallow": False, "crawl_delay_s": 2.0}, True,
                 id="custom-below-site"),
    pytest.param("custom", {"enforce_disallow": False, "crawl_delay_s": 12.0}, False,
                 id="custom-above-site"),
    pytest.param("custom", {"enforce_disallow": True, "crawl_delay_s": None}, True,
                 id="custom-null"),
    pytest.param("custom", {"enforce_disallow": True, "crawl_delay_s": None}, False,
                 id="custom-null-switch-off"),
]


@pytest.mark.parametrize("choice,custom,honour", AGREEMENT)
def test_the_pace_applied_is_the_pace_decide_reports(choice, custom, honour):
    """THE AGREEMENT #1413 ASKED FOR. `decide()` is what `GET /robots` shows; the
    crawl's pace must be the slower of the owner's own pace and that delay --
    never the site's delay behind the report's back."""
    source = entry(robots=choice, robots_custom=custom)
    settings = {"min_interval_s": 1.0, "honour_crawl_delay": honour}
    fetcher = resolve_fetcher(source, settings)
    owners_pace = fetcher._min_interval_s
    fetcher, _ = _over(SLOW_SITE, fetcher)

    fetcher.get(PAGE)

    report = inspect(PAGE, SLOW_SITE, user_agent=fetcher._user_agent)
    verdict = decide(report, RobotsChoice(choice),
                     custom=RobotsCustom(**custom) if custom else None,
                     honour_site_delay=honour, url_disallowed=True)
    assert fetcher._min_interval_s == max(owners_pace, verdict.delay_s or 0.0), (
        f"{choice}: decide() reports {verdict.delay_s}s, the fetcher runs at "
        f"{fetcher._min_interval_s}s")


# ---- 4. a fresh session carries the source's robots answer --------------------

ROBOTS_ANSWERS = [
    pytest.param({"robots_choice": "obey"}, id="obey"),
    pytest.param({"obey_disallow": True}, id="tool-default-obeys"),
    pytest.param({"robots_choice": "custom",
                  "robots_custom": {"enforce_disallow": True, "crawl_delay_s": None}},
                 id="custom-enforces"),
]


@pytest.mark.parametrize("answer", ROBOTS_ANSWERS)
def test_a_fresh_session_still_refuses_what_the_source_refuses(answer):
    crawl, _ = _fetcher(SLOW_SITE, honour_crawl_delay=False, **answer)
    fresh, seen = _over(SLOW_SITE, crawl.fresh_session())

    with pytest.raises(RobotsDisallowed):
        fresh.get(PRIVATE)
    assert seen == [], "the fresh session fetched a path its source refuses"


def test_a_fresh_session_carries_every_robots_setting():
    custom = {"enforce_disallow": True, "crawl_delay_s": 4.0}
    crawl = HttpFetcher(robots_choice="custom", robots_custom=custom,
                        obey_disallow=True, honour_crawl_delay=False)

    fresh = crawl.fresh_session()

    assert fresh._robots_choice == "custom"
    assert fresh._robots_custom == custom
    assert fresh._obey_disallow is True
    assert fresh._honour_crawl_delay is False


def test_a_fresh_session_under_obey_still_takes_the_sites_delay():
    crawl, _ = _fetcher("User-agent: *\nAllow: /\n", robots_choice="obey",
                        honour_crawl_delay=False)
    fresh, _ = _over(SLOW_SITE, crawl.fresh_session())

    fresh.get(PAGE)

    assert fresh._min_interval_s == 10.0


def test_a_fresh_session_still_shares_none_of_the_crawls_state():
    """The half of fresh_session's contract that did not change."""
    crawl, _ = _fetcher(SLOW_SITE, robots_choice="obey")
    crawl.get(PAGE)

    fresh = crawl.fresh_session()

    assert fresh._robots == {} and fresh._robots_reports == {}
    assert fresh.robots_warnings == [] and fresh.requests_count == 0


# ---- the route the panel reads says what the crawl does -----------------------

ROUTE_SOURCES = {
    "DEF": ("default", None),
    "OBEY": ("obey", None),
    "CUST": ("custom", {"enforce_disallow": False, "crawl_delay_s": 2.0}),
}


@pytest.fixture(scope="module")
def panel(tmp_path_factory):
    """One warehouse and one manifest for every source the route is asked about:
    standing a warehouse up is the slow part, and nothing here writes to it."""
    import os
    import subprocess
    import sys

    import yaml
    from fastapi.testclient import TestClient

    root = tmp_path_factory.mktemp("route")
    sources = []
    for key, (choice, custom) in ROUTE_SOURCES.items():
        block = {"source_key": key, "source_name": key, "base_url": f"https://{HOST}",
                 "family": "custom-json-api", "cadence": "daily", "authority": "shop",
                 "active": False, "currency": "SAR", "default_region": "SA",
                 "vat_mode": "incl", "robots": choice,
                 "extract": [{"kind": "product_prices", "scope": "census"}]}
        if custom:
            block["robots_custom"] = custom
        sources.append(block)
    manifest = root / "sources.yaml"
    manifest.write_text(yaml.safe_dump({"sources": sources}), encoding="utf-8")
    database = root / "engine.db"
    made = subprocess.run([sys.executable, "-m", "scrapex.cli", "init-db",
                           "--db", str(database)],
                          env=dict(os.environ, SCRAPEX_SOURCES=str(manifest)),
                          capture_output=True, text=True, timeout=300)
    assert made.returncode == 0, made.stderr

    from scrapex.webui.app import create_app

    return TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))


@pytest.mark.parametrize("honour", [True, False], ids=["switch-on", "switch-off"])
@pytest.mark.parametrize("key", list(ROUTE_SOURCES))
def test_the_route_reports_the_delay_the_crawl_applies(panel, monkeypatch, key, honour):
    """`GET /robots` is what the owner reads before choosing. A delay it reports
    and the crawl does not use -- or the reverse -- is the #1413 defect."""
    from scrapex.capture import crawl_settings as real_crawl_settings

    def settings(conn):
        return {**real_crawl_settings(conn), "min_interval_s": 1.0,
                "honour_crawl_delay": honour}
    monkeypatch.setattr("scrapex.webui.app.crawl_settings", settings)

    # The route reads robots.txt through its own httpx.Client; this one is the
    # stubbed site. Patched after the TestClient exists, so only the route's
    # client is stubbed.
    real_client = httpx.Client

    def stubbed_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(200, text=SLOW_SITE))
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", stubbed_client)

    answer = panel.get(f"/api/sources/{key}/robots")
    monkeypatch.setattr(httpx, "Client", real_client)

    assert answer.status_code == 200, answer.text
    reported = answer.json()["on_a_disallowed_path"]["delay_s"]

    choice, custom = ROUTE_SOURCES[key]
    fetcher = resolve_fetcher(entry(robots=choice, robots_custom=custom),
                              {"min_interval_s": 1.0, "honour_crawl_delay": honour})
    owners_pace = fetcher._min_interval_s
    fetcher, _ = _over(SLOW_SITE, fetcher)
    fetcher.get(PAGE)

    assert fetcher._min_interval_s == max(owners_pace, reported or 0.0), (
        f"{key}: the route reports {reported}s, the crawl runs at "
        f"{fetcher._min_interval_s}s")


# ---- the route says the crawl pauses where the fetcher pauses (#1585) ---------

ROUTE_ROBOTS = [
    pytest.param(httpx.Response(503), True, id="503"),
    pytest.param(httpx.Response(500), True, id="500"),
    pytest.param(httpx.ConnectError("connection refused"), True, id="exception"),
    pytest.param(httpx.Response(403), False, id="403"),
    pytest.param(httpx.Response(429), False, id="429"),
    pytest.param(httpx.Response(404), False, id="404"),
]


def _ask_the_route(panel, monkeypatch, key: str, robots) -> dict:
    """`GET /robots` over a site whose robots.txt answers `robots`."""
    real_client = httpx.Client

    def answer(request: httpx.Request) -> httpx.Response:
        if isinstance(robots, Exception):
            raise robots
        return robots

    def stubbed_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(answer)
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", stubbed_client)
    try:
        response = panel.get(f"/api/sources/{key}/robots")
    finally:
        monkeypatch.setattr(httpx, "Client", real_client)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("key", list(ROUTE_SOURCES))
@pytest.mark.parametrize("robots,pauses", ROUTE_ROBOTS)
def test_the_route_reports_the_pause_the_crawl_takes(panel, monkeypatch, key, robots,
                                                     pauses):
    """THE #1413 AGREEMENT, FOR THE NEW ANSWER. Where the fetcher raises
    `RobotsUnreachable` the route says the crawl will not fetch, and why; where it
    crawls on, the route says so. Asked of the route and of the real fetcher alike."""
    shown = _ask_the_route(panel, monkeypatch, key, robots)

    choice, custom = ROUTE_SOURCES[key]
    fetcher, seen = _over(robots, resolve_fetcher(entry(robots=choice,
                                                        robots_custom=custom),
                                                  {"min_interval_s": 0.0}))
    try:
        fetcher.get(PAGE)
        crawl_paused = False
    except RobotsUnreachable:
        crawl_paused = True

    assert crawl_paused is pauses, f"the fetcher's answer moved: {seen}"
    assert shown["unreachable"] is pauses, shown
    assert shown["on_a_disallowed_path"]["may_fetch"] is (not pauses), shown
    if pauses:
        reason = shown["on_a_disallowed_path"]["reason"]
        assert "RFC 9309 §2.3.1.4" in reason and "paused" in reason, reason
        assert "press Resume" in reason, reason
        assert shown["on_a_disallowed_path"]["delay_s"] is None, shown
        assert "pauses" in shown["summary"], shown["summary"]
        assert "RFC 9309" in shown["summary"] and "Resume" in shown["summary"], shown


# ---- the route reads robots.txt the way the crawl does (#1585 review) ----------

def _route_and_crawl_against(panel, monkeypatch, key: str, handler, settings: dict):
    """Ask the route and the crawl's own fetcher the same site, with the same saved
    settings. Returns (route's JSON, whether the crawl paused, what the site saw)."""
    from scrapex.capture import crawl_settings as real_crawl_settings

    def saved(conn):
        return {**real_crawl_settings(conn), "min_interval_s": 0.0, **settings}
    monkeypatch.setattr("scrapex.webui.app.crawl_settings", saved)
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real_client = httpx.Client

    def stubbed_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(recording)
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", stubbed_client)
    try:
        response = panel.get(f"/api/sources/{key}/robots")
        choice, custom = ROUTE_SOURCES[key]
        fetcher = resolve_fetcher(entry(robots=choice, robots_custom=custom),
                                  {"min_interval_s": 0.0, **settings})
        try:
            fetcher.get(PAGE)
            paused = False
        except RobotsUnreachable:
            paused = True
        finally:
            fetcher.close()
    finally:
        monkeypatch.setattr(httpx, "Client", real_client)
    assert response.status_code == 200, response.text
    return response.json(), paused, seen


def test_a_site_slower_than_15s_reads_the_same_on_the_route_and_in_the_crawl(
        panel, monkeypatch):
    """The route's own client timed out at 15s; the crawl waits `crawl_timeout_s`
    (30s shipped). A site answering in 20s was reported unreachable -- "the crawl
    pauses" -- while the crawl read it and went on."""
    def twenty_seconds(request: httpx.Request) -> httpx.Response:
        if request.extensions["timeout"]["read"] < 20:
            raise httpx.ReadTimeout("no answer within the timeout")
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text="ok")

    shown, paused, _ = _route_and_crawl_against(panel, monkeypatch, "DEF",
                                                twenty_seconds, {"timeout_s": 30.0})

    assert paused is False
    assert shown["unreachable"] is False, shown
    assert shown["found"] is True, shown


def test_the_route_uses_the_owners_timeout_too(panel, monkeypatch):
    """And the other way: his 10s timeout makes the 20s site unreachable in both."""
    def twenty_seconds(request: httpx.Request) -> httpx.Response:
        if request.extensions["timeout"]["read"] < 20:
            raise httpx.ReadTimeout("no answer within the timeout")
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    shown, paused, _ = _route_and_crawl_against(panel, monkeypatch, "DEF",
                                                twenty_seconds, {"timeout_s": 10.0})

    assert paused is True
    assert shown["unreachable"] is True, shown


def test_a_site_that_answers_only_a_browser_reads_the_same_on_both(panel, monkeypatch):
    """The route sent a bare User-Agent and no client hints; the crawl sends the
    panel's Chrome and its hints. A site that 503s anything without them was shown
    as pausing while the crawl was let in."""
    agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
    hints = '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"'

    def browsers_only(request: httpx.Request) -> httpx.Response:
        if (request.headers.get("user-agent") != agent
                or request.headers.get("sec-ch-ua") != hints):
            return httpx.Response(503)
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    shown, paused, seen = _route_and_crawl_against(
        panel, monkeypatch, "DEF", browsers_only,
        {"browser_user_agent": agent, "client_hints": hints, "user_agent": ""})

    assert paused is False
    assert shown["unreachable"] is False, shown
    assert shown["found"] is True, shown
    assert all(r.headers.get("sec-ch-ua") == hints for r in seen), "a bare request"


def test_the_route_retries_like_the_crawl(panel, monkeypatch):
    """One dropped connection then the file: the crawl reads it on its retry, so the
    route must not report a pause the crawl would not take."""
    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if request.url.path == "/robots.txt" and len(calls) % 2 == 1:
            raise httpx.ConnectError("dropped")
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    shown, paused, _ = _route_and_crawl_against(panel, monkeypatch, "OBEY", flaky, {})

    assert paused is False
    assert shown["unreachable"] is False, shown


@pytest.mark.parametrize("error", [
    pytest.param(httpx.TooManyRedirects("loop"), id="TooManyRedirects"),
    pytest.param(httpx.ConnectError("refused"), id="ConnectError"),
])
def test_the_route_classifies_an_exception_as_the_crawl_does(panel, monkeypatch, error):
    def raising(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            raise error
        return httpx.Response(200, text="ok")

    shown, paused, _ = _route_and_crawl_against(panel, monkeypatch, "DEF", raising, {})

    assert shown["unreachable"] is paused, (shown, paused)
    assert paused is isinstance(error, httpx.TransportError)


def test_the_route_says_which_robots_txt_it_read(panel, monkeypatch):
    """A source whose crawl reads a second host (heidelberg's API and corporate
    hosts) is reported for its `base_url` host only, and the answer says so."""
    shown, _, _ = _route_and_crawl_against(
        panel, monkeypatch, "DEF",
        lambda request: httpx.Response(404 if request.url.path == "/robots.txt" else 200),
        {})

    assert shown["robots_url"] == f"https://{HOST}/robots.txt", shown


# ---- the route answers promptly; the crawl keeps the full wait (#1588 ruling) ----

def _sleeps(monkeypatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", slept.append)
    return slept


def _route_only(panel, monkeypatch, handler) -> dict:
    """The route alone, so every recorded wait is the route's own."""
    monkeypatch.setattr("scrapex.webui.app.crawl_settings",
                        lambda conn: {"min_interval_s": 0.0, "timeout_s": 30.0})
    real_client = httpx.Client

    def stubbed_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", stubbed_client)
    try:
        response = panel.get("/api/sources/DEF/robots")
    finally:
        monkeypatch.setattr(httpx, "Client", real_client)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_route_does_not_wait_a_long_retry_after_and_says_so(panel, monkeypatch):
    """A 503 asking Retry-After 900: the route answers at once, says the site asked
    for 900s, and keeps the pause as the answer it has -- the crawl would wait it."""
    slept = _sleeps(monkeypatch)
    asked: list[str] = []

    def busy(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return httpx.Response(503, headers={"Retry-After": "900"})

    shown = _route_only(panel, monkeypatch, busy)

    assert asked == ["/robots.txt"], "the route asked again instead of answering"
    assert slept == [], f"the route waited: {slept}"
    assert shown["retry_after_s"] == 900.0, shown
    assert shown["unreachable"] is True, shown
    assert "retried after 900s" in shown["summary"], shown["summary"]


def test_the_route_waits_a_short_retry_after_and_retries(panel, monkeypatch):
    """Within the cap the route waits as the crawl does, and reads the file."""
    slept = _sleeps(monkeypatch)
    calls: list[int] = []

    def once_busy(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/robots.txt":
            return httpx.Response(200, text="ok")
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, headers={"Retry-After": "5"})
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    shown = _route_only(panel, monkeypatch, once_busy)

    assert len(calls) == 2, calls
    assert 5.0 in slept, slept
    assert shown["found"] is True and shown["retry_after_s"] is None, shown


def _clocked_sleeps(monkeypatch) -> tuple[list[float], list[float]]:
    """A clock that moves only by what is slept, or by `now[0] += n` in a handler."""
    now = [FROZEN_CLOCK]
    slept: list[float] = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds
    monkeypatch.setattr("scrapex.connectors.base.time.monotonic", lambda: now[0])
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", sleep)
    return now, slept


def _prompt_fetcher(handler, *, timeout_s=10.0, pace=0.0, attempts=3) -> HttpFetcher:
    fetcher = HttpFetcher(min_interval_s=pace, jitter=0.0, timeout_s=timeout_s,
                          max_attempts=attempts)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler),
                                   timeout=timeout_s)
    return fetcher


def test_a_prompt_read_never_starts_a_wait_it_has_no_time_for(monkeypatch):
    """A 100s pace backs off 200s: past a 10s budget, so the route does not wait it.
    It answers on what it has and says the crawl would have kept going."""
    _, slept = _clocked_sleeps(monkeypatch)
    asked: list[int] = []

    def refused(request):
        asked.append(1)
        raise httpx.ConnectError("refused")

    read = _prompt_fetcher(refused, pace=100.0).read_robots(PAGE, answer_promptly=True)

    assert read.unreachable is True and read.cut_short is True, read
    assert asked == [1] and slept == [], (asked, slept)


def test_the_prompt_reads_whole_time_is_bounded(monkeypatch):
    """THE TOTAL, NOT ONLY EACH WAIT. A host that times out every attempt: each takes
    the whole timeout it is given, so a retry gets only what is left of the budget and
    none starts once it is spent. Without the deadline it was ~96-150s against the
    panel's open request."""
    now, _ = _clocked_sleeps(monkeypatch)

    def times_out(request):
        # Each attempt spends the whole timeout it was GIVEN, as a dead host does.
        now[0] += request.extensions["timeout"]["read"]
        raise httpx.ReadTimeout("no answer")

    fetcher = _prompt_fetcher(times_out, timeout_s=10.0, pace=1.0, attempts=5)
    started = now[0]

    read = fetcher.read_robots(PAGE, answer_promptly=True)

    # One attempt (10s) plus at most the budget (10s) for the retries.
    assert now[0] - started <= 20.0, now[0] - started
    assert read.unreachable is True and read.cut_short is True, read


def test_a_prompt_read_with_time_to_spare_retries_like_the_crawl(monkeypatch):
    _, slept = _clocked_sleeps(monkeypatch)
    calls: list[int] = []

    def once_down(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("dropped")
        return httpx.Response(404)

    read = _prompt_fetcher(once_down, pace=1.0).read_robots(PAGE, answer_promptly=True)

    assert len(calls) == 2 and read.cut_short is False and read.unreachable is False
    assert slept[0] == 2.0, slept                        # the crawl's own backoff


def test_the_crawls_read_has_no_deadline(monkeypatch):
    """The same timing-out host under the CRAWL: every attempt is made."""
    now, _ = _clocked_sleeps(monkeypatch)
    asked: list[int] = []

    def times_out(request):
        asked.append(1)
        now[0] += 10.0
        raise httpx.ReadTimeout("no answer")

    read = _prompt_fetcher(times_out, pace=1.0, attempts=5).read_robots(PAGE)

    assert len(asked) == 5 and read.cut_short is False


def test_the_route_says_when_its_time_ran_out(panel, monkeypatch):
    now, _ = _clocked_sleeps(monkeypatch)

    def times_out(request):
        now[0] += request.extensions["timeout"]["read"]
        raise httpx.ReadTimeout("no answer")

    shown = _route_only(panel, monkeypatch, times_out)

    assert shown["cut_short"] is True, shown
    assert shown["unreachable"] is True, shown
    assert "stopped retrying at its time limit" in shown["summary"], shown["summary"]


def test_the_crawl_still_waits_the_full_retry_after(monkeypatch):
    """The crawl is not the route: Retry-After 900 is waited, then retried."""
    slept = _sleeps(monkeypatch)
    fetcher, asked = _scripted(httpx.Response(503, headers={"Retry-After": "900"}),
                               httpx.Response(404))

    assert fetcher.get(PAGE).status_code == 200

    assert 900.0 in slept, slept
    assert asked == ["/robots.txt", "/robots.txt", "/products/1"], asked


def test_the_crawls_read_never_reports_a_retry_after(monkeypatch):
    _sleeps(monkeypatch)
    fetcher, _ = _scripted(httpx.Response(503, headers={"Retry-After": "900"}))

    read = fetcher.read_robots(PAGE)

    assert read.retry_after_s is None and read.unreachable is True


# ---- a Retry-After that is not a wait (#1588 re-review) -------------------------

NOT_A_WAIT = [pytest.param(v, id=v) for v in ("inf", "nan", "1e999", "-5", "-inf")]


@pytest.mark.parametrize("named", NOT_A_WAIT)
def test_the_route_survives_a_retry_after_that_is_not_a_number_of_seconds(
        panel, monkeypatch, named):
    """`inf` reached the JSON and crashed the route with a 500: a scraped header must
    never take the panel down. Read as no Retry-After at all."""
    _sleeps(monkeypatch)
    shown = _route_only(panel, monkeypatch, lambda request: httpx.Response(
        503, headers={"Retry-After": named}))

    assert shown["retry_after_s"] is None, shown
    assert shown["unreachable"] is True, shown


@pytest.mark.parametrize("named", NOT_A_WAIT)
def test_a_page_backs_off_by_default_on_a_retry_after_that_is_not_a_wait(
        monkeypatch, named):
    """On a page, `nan` slipped through `min` and `max` into `sleep(0)`: a retry with
    no wait at all. The default backoff -- twice the pace -- stands instead."""
    slept = _sleeps(monkeypatch)
    calls: list[int] = []

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, headers={"Retry-After": named})
        return httpx.Response(200, text="ok")

    fetcher = HttpFetcher(min_interval_s=3.0, jitter=0.0)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))

    assert fetcher.get(PAGE).status_code == 200

    assert 6.0 in slept, slept
    assert all(math.isfinite(wait) and wait >= 0 for wait in slept), slept
    assert not any("ceiling" in w for w in fetcher.robots_warnings)


@pytest.mark.parametrize("named,expected", [("0", 0.0), ("12.5", 12.5), ("", None),
                                            ("Wed, 21 Oct 2026 07:28:00 GMT", None)])
def test_a_retry_after_that_is_a_wait_is_still_read(named, expected):
    assert HttpFetcher._retry_after_s(
        httpx.Response(503, headers={"Retry-After": named})) == expected


def test_a_robots_retry_still_waits_the_pace_when_the_backoff_is_shorter(monkeypatch):
    """Retry-After: 0 is a backoff of nothing; the 5s pace is still owed before the
    retry, as `_request` owes it."""
    now, slept = _clocked_sleeps(monkeypatch)
    seen_at: list[float] = []

    def handler(request):
        seen_at.append(now[0])
        if len(seen_at) == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(404)

    fetcher = HttpFetcher(min_interval_s=5.0, jitter=0.0)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))

    fetcher.read_robots(PAGE)

    assert seen_at[1] - seen_at[0] >= 5.0, (seen_at, slept)


# ---- the route and a browser source (#1588 re-review) --------------------------

@pytest.fixture(scope="module")
def browser_panel(tmp_path_factory):
    import os
    import subprocess
    import sys

    import yaml
    from fastapi.testclient import TestClient

    root = tmp_path_factory.mktemp("route-browser")
    manifest = root / "sources.yaml"
    manifest.write_text(yaml.safe_dump({"sources": [{
        "source_key": "BROWSED", "source_name": "BROWSED",
        "base_url": f"https://{HOST}", "family": "custom-json-api",
        "cadence": "daily", "authority": "shop", "active": False, "currency": "SAR",
        "default_region": "SA", "vat_mode": "incl", "robots": "obey",
        "fetcher": "browser",
        "extract": [{"kind": "product_prices", "scope": "census"}]}]}),
        encoding="utf-8")
    database = root / "engine.db"
    made = subprocess.run([sys.executable, "-m", "scrapex.cli", "init-db",
                           "--db", str(database)],
                          env=dict(os.environ, SCRAPEX_SOURCES=str(manifest)),
                          capture_output=True, text=True, timeout=300)
    assert made.returncode == 0, made.stderr

    from scrapex.webui.app import create_app

    return TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))


def test_a_browser_source_is_told_its_crawl_reads_no_robots_txt(browser_panel,
                                                                monkeypatch):
    """The browser transport reads no robots.txt, so "the crawl pauses" would be a
    claim about a crawl that never asks. The file is shown; no pause is claimed."""
    _sleeps(monkeypatch)
    real_client = httpx.Client

    def stubbed_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda request: httpx.Response(503))
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", stubbed_client)
    try:
        shown = browser_panel.get("/api/sources/BROWSED/robots").json()
    finally:
        monkeypatch.setattr(httpx, "Client", real_client)

    assert shown["crawl_reads_robots"] is False, shown
    assert shown["unreachable"] is False, shown
    assert shown["unreadable"] == "HTTP 503", shown
    assert shown["on_a_disallowed_path"]["may_fetch"] is True, shown
    assert "reads no robots.txt" in shown["on_a_disallowed_path"]["reason"]
    assert "pauses" not in shown["summary"], shown["summary"]
    assert "reads no robots.txt" in shown["summary"], shown["summary"]


def test_a_browser_source_does_not_start_a_browser_to_read_robots(browser_panel,
                                                                 monkeypatch):
    """`resolve_fetcher` would build a BrowserFetcher -- Playwright -- for it."""
    import scrapex.connectors.base as base

    def no_browser(*args, **kwargs):
        raise AssertionError("the route started a browser to read robots.txt")
    monkeypatch.setattr(base.BrowserFetcher, "__init__", no_browser)
    real_client = httpx.Client

    def stubbed_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda request: httpx.Response(404))
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", stubbed_client)
    try:
        response = browser_panel.get("/api/sources/BROWSED/robots")
    finally:
        monkeypatch.setattr(httpx, "Client", real_client)

    assert response.status_code == 200, response.text


def test_the_route_closes_the_fetcher_it_read_with(panel, monkeypatch):
    closed: list[int] = []
    real_close = HttpFetcher.close

    def spy(self):
        closed.append(1)
        real_close(self)
    monkeypatch.setattr(HttpFetcher, "close", spy)

    _route_only(panel, monkeypatch, lambda request: httpx.Response(404))

    assert closed == [1], closed


# ---- a cached host never waits behind another host's read (#1588 re-review) ----

def _recorded(outcomes: dict, name: str, call):
    """A thread target that keeps `call`'s result -- or its exception -- in
    `outcomes[name]`, so nothing a worker raises escapes the thread unasserted."""
    def run():
        try:
            outcomes[name] = call()
        except Exception as exc:
            outcomes[name] = exc
    return run


def test_a_cached_host_does_not_wait_behind_another_hosts_robots_read():
    """One lock serves every host, and a read can back off for minutes: a page of a
    host whose answer is cached must not queue behind it."""
    import threading

    reading_b = threading.Event()
    release_b = threading.Event()

    def handler(request):
        if request.url.host == "b.test" and request.url.path == "/robots.txt":
            reading_b.set()
            release_b.wait(10)
            return httpx.Response(404)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="ok")

    fetcher = HttpFetcher(min_interval_s=0.0, jitter=0.0)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher.get(f"https://{HOST}/first")                 # HOST's answer is cached
    outcomes: dict[str, object] = {}
    other = threading.Thread(target=_recorded(
        outcomes, "b", lambda: fetcher.get("https://b.test/x").status_code))
    other.start()
    assert reading_b.wait(5), "the second host's read never started"

    second = threading.Thread(target=_recorded(
        outcomes, "second", lambda: fetcher.get(f"https://{HOST}/second").status_code))
    second.start()
    second.join(2)
    finished = not second.is_alive()
    release_b.set()
    other.join(5)
    second.join(5)

    assert finished, "a cached host's page waited behind another host's robots read"
    assert outcomes == {"b": 200, "second": 200}, outcomes


def test_a_host_not_yet_read_still_reads_once_under_the_lock():
    """The other half: the fast path is for answered hosts only."""
    import threading

    asked: list[str] = []
    guard = threading.Lock()

    def handler(request):
        with guard:
            asked.append(request.url.path)
        if request.url.path == "/robots.txt":
            threading.Event().wait(0.1)
            return httpx.Response(404)
        return httpx.Response(200, text="ok")

    fetcher = HttpFetcher(min_interval_s=0.0, jitter=0.0)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))
    outcomes: dict[str, object] = {}
    threads = [threading.Thread(target=_recorded(
                   outcomes, str(n), lambda n=n: fetcher.get(f"{PAGE}?n={n}").status_code))
               for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert asked.count("/robots.txt") == 1, asked
    assert outcomes == {str(n): 200 for n in range(4)}, outcomes


# ---- #1588 third review ---------------------------------------------------------

def test_a_wait_that_fits_but_not_with_the_pace_after_it_is_not_started(monkeypatch):
    """The backoff (2 x a 4s pace = 8s) fits the 10s left; the pace owed after it
    does not. Starting the wait would start an attempt past the deadline."""
    _, slept = _clocked_sleeps(monkeypatch)
    asked: list[int] = []

    def busy(request):
        asked.append(1)
        return httpx.Response(503)

    read = _prompt_fetcher(busy, timeout_s=10.0, pace=4.0).read_robots(
        PAGE, answer_promptly=True)

    assert asked == [1], "a second request went out past the deadline"
    assert read.cut_short is True and slept == [], (read, slept)


def test_a_retry_after_within_the_budget_but_past_the_time_left_is_still_said(
        monkeypatch):
    """Retry-After 8 is within a 10s budget; 3s of it are gone to a slow first
    answer. The read is cut short, and the site's number still reaches the panel."""
    now, _ = _clocked_sleeps(monkeypatch)

    def slow_busy(request):
        now[0] += 3.0
        return httpx.Response(503, headers={"Retry-After": "8"})

    read = _prompt_fetcher(slow_busy, timeout_s=10.0, pace=0.5).read_robots(
        PAGE, answer_promptly=True)

    assert read.cut_short is True and read.retry_after_s == 8.0, read


def test_a_browser_source_is_never_told_obeying_blocks_everything(browser_panel,
                                                                 monkeypatch):
    """`Disallow: /` would make `obey` collect nothing -- for a crawl that reads
    robots.txt. The browser's does not, and its Crawl-delay is not kept either."""
    _sleeps(monkeypatch)
    real_client = httpx.Client

    def stubbed_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda request: httpx.Response(
            200, text="User-agent: *\nDisallow: /\nCrawl-delay: 10\n"))
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", stubbed_client)
    try:
        shown = browser_panel.get("/api/sources/BROWSED/robots").json()
    finally:
        monkeypatch.setattr(httpx, "Client", real_client)

    assert shown["found"] is True, shown
    assert shown["would_block_everything"] is False, shown
    assert shown["crawl_delay_s"] is None, shown
    assert shown["on_a_disallowed_path"]["may_fetch"] is True, shown


@pytest.mark.parametrize("kind", ["unreachable", "refused"])
def test_a_host_already_refused_or_paused_answers_without_the_lock(kind):
    """The fast path covers every cache, not only the readable one: a host whose
    answer is a pause or a refusal is answered while another host is being read."""
    import threading

    reading_b = threading.Event()
    release_b = threading.Event()

    def handler(request):
        if request.url.host == "b.test":
            if request.url.path != "/robots.txt":
                return httpx.Response(200, text="ok")
            reading_b.set()
            release_b.wait(10)
            return httpx.Response(404)
        if kind == "unreachable":
            return httpx.Response(503)
        return httpx.Response(200, text=SLOW_SITE)

    #: Every thread's outcome, collected rather than left to escape the thread.
    outcomes: dict[str, object] = {}

    choice = ({} if kind == "unreachable"
              else {"robots_choice": "custom", "robots_custom": None})
    fetcher = HttpFetcher(min_interval_s=0.0, jitter=0.0, max_attempts=1, **choice)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler))
    expected = RobotsUnreachable if kind == "unreachable" else ValueError
    with pytest.raises(expected):
        fetcher.get(PAGE)                                # the answer is cached
    other = threading.Thread(target=_recorded(
        outcomes, "b", lambda: fetcher.get("https://b.test/x").status_code))
    other.start()
    assert reading_b.wait(5), "the second host's read never started"

    again = threading.Thread(target=_recorded(outcomes, "again",
                                              lambda: fetcher.get(PAGE)))
    again.start()
    again.join(2)
    finished = not again.is_alive()
    release_b.set()
    other.join(5)
    again.join(5)

    assert finished, f"a {kind} host waited behind another host's robots read"
    assert isinstance(outcomes["again"], expected), outcomes
    assert outcomes["b"] == 200, outcomes
