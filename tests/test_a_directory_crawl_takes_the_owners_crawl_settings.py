"""A directory crawl is paced by the settings he sets, and its log says how it behaved.

ISSUE 1414. The listing crawl and the profile sweep built their fetcher as
`HttpFetcher(min_interval_s=1.0)`, every other argument at its default. So none of the
panel's crawl settings -- pace, timeout, user agent, the browser agent and its client
hints, honour-delay, obey-disallow -- reached muqawil or the Oman register, while every
price source took them all through `resolve_fetcher`. And `fetcher.robots_warnings`
filled on that path with nothing reading it, so a directory run's log carried no robots
line; the one pace it did state was the 1s constant, even when robots.txt had raised it.

STAGE 1 OF THE OWNER'S RULING: one general chain for every collector
(`connectors.base.general_fetcher`), the price path adding its per-source rules on top.
Robots for a directory is the tool default until stage 2 gives it a column.

THE REAL CHAIN, THE REAL SCHEMA, NO NETWORK. `make_fetch` is spied THROUGH, not
replaced: the fetcher under test is the one the runner built from the saved settings,
and only its transport is swapped for a `MockTransport` -- so the robots handling that
writes the log lines is the shipped code, not a stand-in for it.
"""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import httpx
import pytest

from scrapex import contractors, directoryjob, jobs, profilejob, settings, source_settings
from scrapex import db as dbmod
from scrapex.config import Manifest
from scrapex.connectors import base as connectors_base
from scrapex.connectors.base import DEFAULT_USER_AGENT, RobotsDisallowed

SITE = "muqawil_org"

#: `source_settings.save` judges a choice against the manifest (an unprobed price source
#: cannot be activated); a directory is in none, so any manifest without it will do.
_NO_PRICE_SOURCES = Manifest.model_validate({"sources": [{
    "source_key": "SOME_SHOP", "source_name": "Some Shop", "base_url": "https://shop.test",
    "family": "custom-json-api", "extract": [{"kind": "product_prices"}]}]})
HOST = "muqawil.org"
SLOW_SITE = "User-agent: *\nCrawl-delay: 10\nDisallow: /private/\n"
#: Far from zero for the reason tests/test_http_fetcher.py gives at FROZEN_CLOCK.
FROZEN_CLOCK = 1_000.0

OWNER = {
    "crawl_min_interval_s": "4.5",
    "crawl_timeout_s": "12",
    "crawl_user_agent": "OwnerTyped/7.0",
    "crawl_honour_delay": "0",
    "crawl_obey_disallow": "1",
}


@pytest.fixture()
def conn(tmp_path):
    connection = dbmod.connect(tmp_path / "engine.db")
    dbmod.migrate(connection)
    connection.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES (?, 'muqawil.org', 'https://muqawil.org', 'directory')", (SITE,))
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    """A 10s Crawl-delay is the point of some of these tests, not something to wait out.
    The clock advances only by what the pacer sleeps."""
    now = [FROZEN_CLOCK]

    def sleep(seconds):
        now[0] += seconds
    monkeypatch.setattr("scrapex.connectors.base.time.monotonic", lambda: now[0])
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", sleep)


def _spy(monkeypatch, robots: str = "", robots_status: int = 200) -> dict:
    """Let the runner build its fetcher for real, then cut only the wire.

    What the real client was built with -- its headers and timeout -- is read BEFORE the
    transport is swapped, because the swap is a new `httpx.Client` and would report its
    own defaults instead.
    """
    built: dict = {}
    real = contractors.make_fetch

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/robots.txt"):
            if robots_status != 200:
                return httpx.Response(robots_status)
            return httpx.Response(200, text=robots) if robots else httpx.Response(404)
        return httpx.Response(200, text="<html></html>")

    def spying(crawl_settings, rules):
        built["rules"] = rules
        fetcher, fetch = real(crawl_settings, rules)
        built["headers"] = dict(fetcher._client.headers)
        built["timeout"] = fetcher._client.timeout
        fetcher._client.close()
        fetcher._client = httpx.Client(transport=httpx.MockTransport(handler),
                                       follow_redirects=True)
        built["fetcher"] = fetcher
        return fetcher, fetch

    monkeypatch.setattr(contractors, "make_fetch", spying)
    return built


def _visiting(monkeypatch, urls: list[str]) -> None:
    """Both collectors' crawl, replaced by one that asks for exactly `urls`.

    POSITIONAL, as the runners call them: `crawl(conn, directory, beating, fetcher, ...)`
    and `details(conn, directory, fetch, fetcher, ...)` -- the fetch is the third
    argument either way, and on the listing path it is `beating`, the wrapper the
    runner's heartbeat and stop check live in.
    """
    def crawl(*args, **kwargs):
        for url in urls:
            args[2](url)

    monkeypatch.setattr(contractors, "crawl", crawl)
    monkeypatch.setattr(contractors, "details", crawl)


def _run_directory(conn) -> str:
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    directoryjob.run_directory_crawl_job_once(conn, ref)
    return ref


def _run_profile(conn) -> str:
    # NAMED IDS, because they need no sighting ledger and are not subject to the scope
    # (`contractors.details`), so the job reaches its fetch with nothing else set up.
    ref = jobs.create_job(conn, [SITE], checkpoint={"ids": ["7101"]},
                          job_kind=profilejob.JOB_KIND)
    conn.commit()
    profilejob.run_profile_crawl_job_once(conn, ref)
    return ref


RUNNERS = pytest.mark.parametrize("run", [_run_directory, _run_profile],
                                  ids=["listing", "profiles"])


def _lines(conn, ref: str) -> list[dict]:
    return jobs.job_logs(conn, ref)


# ---- the settings reach the fetcher --------------------------------------------------

@RUNNERS
def test_the_owners_crawl_settings_reach_the_directory_fetcher(conn, monkeypatch, run):
    """Every setting the price path reads, read here too, from the store the panel
    writes. Each was at its default on this path before #1414, whatever he set."""
    settings.save(conn, OWNER)
    conn.commit()
    built = _spy(monkeypatch)
    _visiting(monkeypatch, [])

    run(conn)

    fetcher = built["fetcher"]
    assert fetcher._min_interval_s == 4.5, "the panel's pace did not reach the crawl"
    assert built["timeout"].read == 12.0, "the panel's timeout did not reach the crawl"
    assert fetcher._user_agent == "OwnerTyped/7.0"
    assert built["headers"]["user-agent"] == "OwnerTyped/7.0"
    assert fetcher._honour_crawl_delay is False
    assert fetcher._obey_disallow is True
    # He chose nothing for this directory, so its robots answer is the tool's. What he
    # chooses for it is held by `test_his_choices_for_this_directory_reach_its_fetcher`.
    assert fetcher._robots_choice == "default"


@RUNNERS
def test_the_panels_own_browser_agent_and_its_hints_reach_the_directory_fetcher(
        conn, monkeypatch, run):
    """Level 3 of `resolve_user_agent`: nothing typed, so the panel's Chrome -- and the
    client hints that must travel with it, or the headers contradict the agent."""
    agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
    hints = '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"'
    settings.save(conn, {"crawl_browser_user_agent": agent,
                         "crawl_browser_client_hints": hints})
    conn.commit()
    built = _spy(monkeypatch)
    _visiting(monkeypatch, [])

    run(conn)

    assert built["fetcher"]._user_agent == agent
    expected = connectors_base.browser_headers(agent, hints)
    assert expected["Sec-CH-UA"] == hints, "the fixture's hints were never sent"
    for name, value in expected.items():
        assert built["headers"][name.lower()] == value, name


@RUNNERS
def test_his_choices_for_this_directory_reach_its_fetcher(conn, monkeypatch, run):
    """#1414 STAGE 2 (#1584): a directory takes his per-source choices from the
    warehouse, by the function a price source's take them -- over his general settings,
    as a price source's own rules are. Before this it had nowhere to keep one."""
    settings.save(conn, OWNER)
    source_settings.save(conn, _NO_PRICE_SOURCES, SITE, {
        "user_agent": "HisDirectory/1.0", "crawl_pace_s": 6.0, "robots": "custom",
        "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 0.0}})
    conn.commit()
    built = _spy(monkeypatch)
    _visiting(monkeypatch, [])

    run(conn)

    fetcher = built["fetcher"]
    assert built["rules"] == source_settings.effective(conn, SITE, None)
    assert fetcher._user_agent == "HisDirectory/1.0", "his agent for it beats the typed one"
    assert fetcher._min_interval_s == 6.0, "the slowest of his pace and the general one"
    assert fetcher._robots_choice == "custom"
    assert fetcher._robots_custom == {"enforce_disallow": True, "crawl_delay_s": 0.0}


@RUNNERS
def test_a_directory_choice_he_cleared_falls_back_to_his_general_settings(
        conn, monkeypatch, run):
    """A directory ships nothing, so clearing a choice leaves the general rule alone."""
    settings.save(conn, OWNER)
    source_settings.save(conn, _NO_PRICE_SOURCES, SITE, {"user_agent": "HisDirectory/1.0"})
    source_settings.save(conn, _NO_PRICE_SOURCES, SITE, {"user_agent": None})
    conn.commit()
    built = _spy(monkeypatch)
    _visiting(monkeypatch, [])

    run(conn)

    assert built["fetcher"]._user_agent == "OwnerTyped/7.0"
    assert built["fetcher"]._min_interval_s == 4.5


@RUNNERS
def test_with_nothing_saved_the_directory_fetcher_is_what_it_always_was(
        conn, monkeypatch, run):
    """THE SHIPPED DEFAULTS ARE THE OLD `HttpFetcher(min_interval_s=1.0)`, field for
    field, so a machine whose owner never opened Settings crawls exactly as before."""
    built = _spy(monkeypatch)
    _visiting(monkeypatch, [])

    run(conn)

    fetcher = built["fetcher"]
    assert fetcher._min_interval_s == 1.0
    assert built["timeout"].read == 30.0
    assert fetcher._user_agent == DEFAULT_USER_AGENT
    assert fetcher._honour_crawl_delay is True
    assert fetcher._obey_disallow is False
    assert fetcher._robots_choice == "default"


def test_the_command_lines_pace_is_still_the_only_thing_it_sets():
    """`--pace` alone, through the same chain: everything else at the shipped default,
    which is what `HttpFetcher(min_interval_s=pace)` built before."""
    fetcher, _ = contractors.make_fetch({"min_interval_s": 2.5}, source_settings.NO_OPINION)
    try:
        old = connectors_base.HttpFetcher(min_interval_s=2.5)
        try:
            for name in ("_min_interval_s", "_user_agent", "_honour_crawl_delay",
                         "_obey_disallow", "_robots_choice", "_robots_custom"):
                assert getattr(fetcher, name) == getattr(old, name), name
            assert fetcher._client.timeout == old._client.timeout
            assert dict(fetcher._client.headers) == dict(old._client.headers)
        finally:
            old.close()
    finally:
        fetcher.close()


def test_a_price_source_with_no_rules_of_its_own_gets_the_same_general_fetcher():
    """ONE READING OF THE SETTINGS. `resolve_fetcher` adds per-source rules to
    `general_fetcher`; a source that has none must come out identical, or the two
    collectors are being polite to different degrees from one panel."""
    from scrapex.config import ExtractKind, ExtractScope, ExtractSpec, SourceEntry

    entry = SourceEntry.model_validate({
        "source_key": "TESTSHOP", "source_name": "Test Shop",
        "base_url": "https://shop.test", "family": "zid-html", "currency": "SAR",
        "default_region": "SA", "vat_mode": "incl",
        "extract": [ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                                scope=ExtractScope.CENSUS)]})
    chosen = {"min_interval_s": 3.0, "timeout_s": 9.0, "user_agent": "",
              "browser_user_agent": "Chrome-ish/1", "client_hints": '"X";v="1"',
              "honour_crawl_delay": False, "obey_disallow": True}
    price = connectors_base.resolve_fetcher(
        entry, source_settings.layered({}, entry.source_key, entry), chosen)
    general = connectors_base.general_fetcher(chosen)
    try:
        for name in ("_min_interval_s", "_user_agent", "_honour_crawl_delay",
                     "_obey_disallow", "_robots_choice", "_robots_custom"):
            assert getattr(price, name) == getattr(general, name), name
        assert price._client.timeout == general._client.timeout
        assert dict(price._client.headers) == dict(general._client.headers)
    finally:
        price.close()
        general.close()


# ---- the log says how the run behaved toward the site ---------------------------------

@RUNNERS
def test_robots_lines_reach_the_job_log_once_each_at_info(conn, monkeypatch, run):
    """A Crawl-delay honoured and a Disallow crawled past (the tool default discloses),
    each said ONCE however many pages it touched, at INFO as the price path says them."""
    _spy(monkeypatch, robots=SLOW_SITE)
    _visiting(monkeypatch, [f"https://{HOST}/en/a", f"https://{HOST}/private/1",
                            f"https://{HOST}/private/2", f"https://{HOST}/en/b"])

    ref = run(conn)

    lines = _lines(conn, ref)
    delay = [line for line in lines
             if line["message"] == f"{HOST}: robots.txt asks for a 10s crawl delay — "
                                   "honoured"]
    disallow = [line for line in lines
                if line["message"].startswith(f"{HOST}: robots.txt disallows")]
    assert len(delay) == 1, [line["message"] for line in lines]
    assert len(disallow) == 1, [line["message"] for line in lines]
    assert {line["level"] for line in delay + disallow} == {"info"}


@RUNNERS
def test_an_unreadable_robots_txt_reaches_the_job_log_once_as_a_warning(
        conn, monkeypatch, run):
    """A 503 on robots.txt: the run goes on under the tool's own rules (#1413), and
    the directory run's log says so ONCE, at WARNING, as the price path does."""
    _spy(monkeypatch, robots_status=503)
    _visiting(monkeypatch, [f"https://{HOST}/en/a", f"https://{HOST}/en/b"])

    ref = run(conn)

    unreadable = [line for line in _lines(conn, ref)
                  if "robots.txt could not be read (HTTP 503)" in line["message"]]
    assert len(unreadable) == 1, [line["message"] for line in _lines(conn, ref)]
    assert unreadable[0]["level"] == "warning"


@RUNNERS
def test_the_log_states_the_pace_the_crawl_actually_ran_at(conn, monkeypatch, run):
    """The setting says 1s; the site's Crawl-delay raised it to 10s. The log says 10s,
    once, and NO line claims the 1s constant -- the listing crawl's pool line did."""
    settings.save(conn, {"directory_crawl_workers": "3"})
    conn.commit()
    _spy(monkeypatch, robots=SLOW_SITE)
    _visiting(monkeypatch, [f"https://{HOST}/en/a", f"https://{HOST}/en/b"])

    ref = run(conn)

    messages = [line["message"] for line in _lines(conn, ref)]
    paced = [m for m in messages if m.startswith("paced at one request per")]
    assert paced == [paced[0]] and paced[0].startswith(
        "paced at one request per 10s at most"), messages
    assert not any("per 1s" in m for m in messages), messages


def test_the_pace_line_follows_the_owners_setting_when_robots_asks_nothing(
        conn, monkeypatch):
    """No Crawl-delay: the pace in force is his setting, and that is what is said."""
    settings.save(conn, {"crawl_min_interval_s": "4.5"})
    conn.commit()
    _spy(monkeypatch)
    _visiting(monkeypatch, [f"https://{HOST}/en/a"])

    ref = _run_directory(conn)

    messages = [line["message"] for line in _lines(conn, ref)]
    assert any(m.startswith("paced at one request per 4.5s at most") for m in messages), \
        messages


def test_a_run_that_asked_nothing_states_no_pace(conn, monkeypatch):
    """A run that made no request paced nothing, so it claims no pace."""
    _spy(monkeypatch)
    _visiting(monkeypatch, [])

    ref = _run_directory(conn)

    assert not any(line["message"].startswith("paced at")
                   for line in _lines(conn, ref))


def test_a_disallow_obeyed_by_the_owners_switch_fails_the_listing_and_says_why(
        conn, monkeypatch):
    """THE ERROR PATH. With `crawl_obey_disallow` on, a disallowed page stops the
    listing crawl -- and the robots line still reaches the log, because the disclosure
    is written on the way out of every exit, not only a clean one."""
    run = _run_directory
    settings.save(conn, {"crawl_obey_disallow": "1"})
    conn.commit()
    _spy(monkeypatch, robots=SLOW_SITE)
    _visiting(monkeypatch, [f"https://{HOST}/en/a", f"https://{HOST}/private/1"])

    with pytest.raises(RobotsDisallowed):
        run(conn)

    ref = conn.execute("SELECT job_ref FROM crawl_job").fetchone()[0]
    assert jobs.get_job(conn, ref)["status"] == "failed"
    messages = [line["message"] for line in _lines(conn, ref)]
    disallow = [m for m in messages if m.startswith(f"{HOST}: robots.txt disallows")]
    assert len(disallow) == 1, messages


def test_a_disallow_obeyed_by_the_owners_switch_refuses_each_profile_and_says_why(
        conn, monkeypatch):
    """THE PROFILE SWEEP DOES NOT STOP. The REAL `contractors.details` contains each
    page's failure, so under `obey` with every path disallowed no profile page goes
    out, each is refused on its own, the sweep ends `completed` with nothing stored,
    and the robots line is said once. Whether that should read as `completed` is
    the owner's question, filed rather than decided here."""
    settings.save(conn, {"crawl_obey_disallow": "1"})
    conn.commit()
    built = _spy(monkeypatch, robots="User-agent: *\nDisallow: /\n")

    ref = _run_profile(conn)

    assert jobs.get_job(conn, ref)["status"] == "completed"
    assert built["fetcher"].requests_count == 0
    messages = [line["message"] for line in _lines(conn, ref)]
    assert any("RobotsDisallowed" in m for m in messages), messages
    disallow = [m for m in messages if m.startswith(f"{HOST}: robots.txt disallows")]
    assert len(disallow) == 1, messages


@RUNNERS
def test_a_stopped_run_still_says_how_it_behaved(conn, monkeypatch, run):
    """THE STOP EXIT. A pause or cancel unwinds as `CrawlStopped` after a page was read:
    the robots line and the pace line are still written, on that exit as on the others."""
    _spy(monkeypatch, robots=SLOW_SITE)

    def crawl_then_stop(*args, **kwargs):
        args[2](f"https://{HOST}/en/a")
        raise contractors.CrawlStopped

    monkeypatch.setattr(contractors, "crawl", crawl_then_stop)
    monkeypatch.setattr(contractors, "details", crawl_then_stop)

    ref = run(conn)

    messages = [line["message"] for line in _lines(conn, ref)]
    assert f"{HOST}: robots.txt asks for a 10s crawl delay — honoured" in messages, \
        messages
    assert any(m.startswith("paced at one request per 10s") for m in messages), messages


def test_a_degradation_said_twice_is_written_once_at_warning(conn):
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    job_id = jobs.get_job(conn, ref)["job_id"]

    directoryjob.log_politeness(
        conn, job_id, SITE,
        SimpleNamespace(degradations=["x refused it", "x refused it"],
                        robots_warnings=[]))

    lines = [line for line in _lines(conn, ref) if line["message"] == "warning: x refused it"]
    assert len(lines) == 1, _lines(conn, ref)
    assert lines[0]["level"] == "warning"


@pytest.mark.parametrize("flag", ["--plan", "--crawl", "--details"])
def test_every_command_line_door_passes_its_pace_and_nothing_else(monkeypatch, flag):
    """`contractors.run` builds its fetcher in three places; each passes `--pace` alone,
    so the command line behaves exactly as it did before the owner's settings existed.

    HIS PER-SOURCE CHOICES are a different question and do reach `--crawl` and
    `--details`, which open the warehouse; `--plan` opens none and sizes the directory
    as a source that said nothing."""
    asked: list[dict] = []
    handed: list = []
    real = contractors.make_fetch
    his = source_settings.SourceRules(
        active=False, robots=source_settings.RobotsChoice.OBEY, robots_custom=None,
        user_agent="HisDirectory/1.0", crawl_pace_s=6.0)

    def spying(crawl_settings, rules):
        asked.append(crawl_settings)
        handed.append(rules)
        return real(crawl_settings, rules)

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(contractors, "make_fetch", spying)
    monkeypatch.setattr(contractors, "validate", lambda args: None)
    monkeypatch.setattr(contractors, "get_directory", lambda key: SimpleNamespace(key=key))
    monkeypatch.setattr(contractors, "open_engine", _Conn)
    # The fake connection has no warehouse to ask, so his answer is handed in here.
    monkeypatch.setattr(contractors.source_settings, "effective",
                        lambda conn, key, shipped: his)
    for name in ("plan", "crawl", "details"):
        monkeypatch.setattr(contractors, name, lambda *a, **k: None)
    parser = argparse.ArgumentParser()
    contractors.add_arguments(parser)

    assert contractors.run(parser.parse_args([flag, "--pace", "2.5"])) == 0

    assert asked == [{"min_interval_s": 2.5}]
    assert handed == [source_settings.NO_OPINION if flag == "--plan" else his]


def test_log_politeness_tolerates_a_stand_in_with_nothing_to_say(conn):
    """The runners' own tests hand in `None` or a minimal fake. A display fact must not
    raise, and must not invent a pace the stand-in never had."""
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    job_id = jobs.get_job(conn, ref)["job_id"]

    directoryjob.log_politeness(conn, job_id, SITE, None)
    directoryjob.log_politeness(conn, job_id, SITE, object())

    assert _lines(conn, ref) == []


def test_the_settings_store_is_the_one_the_panel_writes(conn):
    """`capture.crawl_settings` is the reader both collectors now take; a value saved
    through `settings.save` -- the route the panel's form posts to -- is what it reads."""
    from scrapex import capture

    settings.save(conn, OWNER)
    chosen = capture.crawl_settings(conn)

    assert chosen["min_interval_s"] == 4.5
    assert chosen["timeout_s"] == 12.0
    assert chosen["user_agent"] == "OwnerTyped/7.0"
    assert chosen["honour_crawl_delay"] is False
    assert chosen["obey_disallow"] is True
