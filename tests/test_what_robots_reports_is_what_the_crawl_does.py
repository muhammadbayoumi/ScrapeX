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
    for robots.txt again, and without asking for the page either."""
    fetcher, asked = _counting(robots)

    for n in range(3):
        with pytest.raises(RobotsUnreachable, match=named):
            fetcher.get(f"{PAGE}?page={n}")

    assert asked == [f"https://{HOST}/robots.txt"], asked


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
    that answered 503 is not asked again sooner than the pace allows."""
    slept = _clocked(monkeypatch)
    fetcher, _ = _fetcher(httpx.Response(503), min_interval_s=3.0)

    with pytest.raises(RobotsUnreachable):
        fetcher.get(PAGE)
    fetcher._throttle()

    assert slept == [3.0], slept


@pytest.mark.parametrize("status,pauses", [
    (None, True), (500, True), (503, True), (599, True),
    (400, False), (403, False), (404, False), (410, False), (429, False),
    (499, False), (200, False), (301, False),
])
def test_only_the_server_or_the_network_counts_as_unreachable(status, pauses):
    """The boundary, at both edges: §2.3.1.4 is 5xx and no answer; §2.3.1.3 is 4xx."""
    assert is_unreachable(status) is pauses


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
        assert "pauses" in shown["summary"], shown["summary"]
