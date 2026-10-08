"""#1413: the robots answer the owner is shown is the one the crawl acts on.

Four defects, each measured on the fetcher before this file existed:

1. An UNREADABLE robots.txt (a 503, a 500, a dropped connection) was cached as
   "no rules" and nothing was written, so every robots check stopped in silence --
   under `obey` too. Ruled: treated as if the site had no file, the tool's own
   rules apply, and the run's log says so once per host. A 404 is still "no file",
   with nothing written.
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

from scrapex import source_settings
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import HttpFetcher, RobotsDisallowed, resolve_fetcher
from scrapex.robots import RobotsChoice, RobotsCustom, decide, inspect
from scrapex.vocab import ExtractKind, ExtractScope


def _shipped_fetcher(source, crawl_settings=None):
    """`resolve_fetcher` for a source as it SHIPPED -- no warehouse, so no choice of his
    (#1584) -- which is the layer every test in this file is about."""
    return resolve_fetcher(source, source_settings.layered({}, source.source_key, source),
                           crawl_settings)


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

UNREADABLE = [
    pytest.param(httpx.Response(503), "HTTP 503", id="503"),
    pytest.param(httpx.Response(500), "HTTP 500", id="500"),
    pytest.param(httpx.Response(403), "HTTP 403", id="403"),
    pytest.param(httpx.ConnectError("connection refused"), "ConnectError", id="exception"),
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
    fetcher, _ = _fetcher(httpx.Response(503), min_interval_s=2.5)

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
    fetcher, _ = _fetcher(httpx.Response(503))

    fetcher.get(PAGE)
    fetcher.get("https://other.test/x")

    notes = _unreadable_notes(fetcher)
    assert len(notes) == 2, notes
    assert any(n.startswith(f"{HOST}:") for n in notes)
    assert any(n.startswith("other.test:") for n in notes)


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
    fetcher, _ = _over(SLOW_SITE, _shipped_fetcher(source, {"min_interval_s": 1.0}))

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
    fetcher, _ = _over(SLOW_SITE, _shipped_fetcher(source, {"min_interval_s": 1.0}))
    fetcher._jitter = 0.0

    fetcher.get(PAGE)

    assert slept == [2.0], slept


def test_a_custom_delay_above_the_sites_is_applied_and_needs_no_warning():
    source = entry(robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": 12.0})
    fetcher, _ = _over(SLOW_SITE, _shipped_fetcher(source, {"min_interval_s": 1.0}))

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
    fetcher, _ = _over(SLOW_SITE, _shipped_fetcher(source, {"min_interval_s": 1.0}))

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
    fetcher = _shipped_fetcher(source, settings)
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
    fetcher = _shipped_fetcher(entry(robots=choice, robots_custom=custom),
                              {"min_interval_s": 1.0, "honour_crawl_delay": honour})
    owners_pace = fetcher._min_interval_s
    fetcher, _ = _over(SLOW_SITE, fetcher)
    fetcher.get(PAGE)

    assert fetcher._min_interval_s == max(owners_pace, reported or 0.0), (
        f"{key}: the route reports {reported}s, the crawl runs at "
        f"{fetcher._min_interval_s}s")
