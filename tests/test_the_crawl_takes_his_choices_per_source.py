"""Every consumer acts on his per-source choices from the warehouse (#1584, PR 2 of 3).

PR 1 put `source_setting` in the warehouse and `source_settings.effective` over it: his
choice for a source, else what `sources.yaml` ships, else no per-source opinion. This
holds each place that DECIDES something from those five fields to that one answer, on
the real schema and the real migrations:

    the price crawl's fetcher     capture.capture_source -> build_connector -> resolve_fetcher
    the schedule                  scheduler.fire_due (active)
    the warehouse's own record    storage.reconcile_active -> source_site.lifecycle
    the Run menu                  dryrun.dry_payload -> passes.price_passes (active)
    the robots screen             GET /api/sources/{key}/robots
    the command line's crawl      cli `crawl`, which opens no warehouse: the shipped layer

The directory jobs (listing and profiles) are held in
`tests/test_a_directory_crawl_takes_the_owners_crawl_settings.py`, beside the general
settings they already take.

A choice is written with `source_settings.save`, exactly as the panel will (PR 3), so a
test here fails if the reader and the writer stop agreeing.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import timedelta

import httpx
import pytest

from scrapex import capture, cli, directories, dryrun, jobs, source_settings, storage
from scrapex.config import Manifest
from scrapex.connectors.base import resolve_fetcher
from scrapex.databases.domain import EngineDatabase
from scrapex.jobs import list_jobs
from scrapex.robots import RobotsChoice
from scrapex.scheduler import fire_due, upsert_schedule, utcnow

#: Ships an opinion on every field, so whose answer reached the consumer is visible.
SHOP = "SHOP_A"
#: Ships `active: false`.
QUIET = "QUIET_B"
#: In `source_site` and not in the manifest.
DIRECTORY = "muqawil_org"


def _entry(key: str, **fields) -> dict:
    return {"source_key": key, "source_name": key.title(), "base_url": "https://shop.test",
            "family": "custom-json-api", "extract": [{"kind": "product_prices"}],
            **fields}


MANIFEST = Manifest.model_validate({"sources": [
    _entry(SHOP, active=True, robots="obey", user_agent="Shipped/1.0", crawl_pace_s=3.0),
    _entry(QUIET, active=False),
]})


@pytest.fixture()
def conn(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    for key in (SHOP, QUIET, DIRECTORY):
        connection.execute(
            "INSERT INTO source_site (source_key, source_name, lifecycle) "
            "VALUES (?, ?, 'active')", (key, key))
    connection.commit()
    yield connection
    connection.close()


class _Built(Exception):
    """Stops a crawl once its fetcher exists: what it was built with is the subject."""


def _fetcher_capture_builds(conn, monkeypatch, entry):
    """Run the real `capture_source` up to the fetcher, through the real factory."""
    built = {}
    real = capture.build_connector

    def spying(source, rules, crawl_settings=None):
        connector, fetcher = real(source, rules, crawl_settings)
        built["rules"], built["fetcher"] = rules, fetcher
        raise _Built

    monkeypatch.setattr(capture, "build_connector", spying)
    with pytest.raises(_Built):
        capture.capture_source(conn, entry)
    return built


# ---- the price crawl's fetcher -------------------------------------------------------

def test_a_price_crawl_is_fetched_as_he_chose(conn, monkeypatch):
    source_settings.save(conn, SHOP, source_settings.shipped_with(MANIFEST, SHOP), {
        "user_agent": "His/2.0", "crawl_pace_s": 7.0, "robots": "custom",
        "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 2.0}})
    conn.commit()

    built = _fetcher_capture_builds(conn, monkeypatch, MANIFEST.get(SHOP))
    fetcher = built["fetcher"]

    try:
        assert fetcher._user_agent == "His/2.0"
        assert fetcher._min_interval_s == 7.0, "his pace is the slowest opinion here"
        assert fetcher._robots_choice == RobotsChoice.CUSTOM
        assert fetcher._robots_custom == {"enforce_disallow": True, "crawl_delay_s": 2.0}
    finally:
        fetcher.close()


def test_a_price_crawl_he_never_touched_is_fetched_as_it_shipped(conn, monkeypatch):
    built = _fetcher_capture_builds(conn, monkeypatch, MANIFEST.get(SHOP))
    fetcher = built["fetcher"]

    try:
        assert fetcher._user_agent == "Shipped/1.0"
        assert fetcher._min_interval_s == 3.0
        assert fetcher._robots_choice == RobotsChoice.OBEY
    finally:
        fetcher.close()


def test_a_cleared_choice_crawls_as_shipped_again(conn, monkeypatch):
    """His ruling: clearing returns a field to the source's SHIPPED value."""
    source_settings.save(conn, SHOP, source_settings.shipped_with(MANIFEST, SHOP), {"user_agent": "His/2.0"})
    source_settings.save(conn, SHOP, source_settings.shipped_with(MANIFEST, SHOP), {"user_agent": None})
    conn.commit()

    fetcher = _fetcher_capture_builds(conn, monkeypatch, MANIFEST.get(SHOP))["fetcher"]

    try:
        assert fetcher._user_agent == "Shipped/1.0"
    finally:
        fetcher.close()


def test_a_custom_delay_left_beside_another_choice_is_not_a_pace():
    """#1591: `resolve_fetcher` read `robots_custom.crawl_delay_s` whatever the choice,
    so a rule left beside `obey` slowed the crawl and nothing said why. The rules it
    takes now carry a rule only under custom."""
    # `SourceEntry` now refuses such a rule; `model_copy` does not validate, so this is
    # the entry that got one past it anyway.
    entry = MANIFEST.get(SHOP).model_copy(update={
        "robots_custom": {"enforce_disallow": False, "crawl_delay_s": 30}})

    fetcher = resolve_fetcher(entry, source_settings.layered({}, SHOP, entry),
                              {"min_interval_s": 1.0})

    try:
        assert fetcher._min_interval_s == 3.0, "its own shipped pace, not the leftover 30"
        assert fetcher._robots_custom is None
    finally:
        fetcher.close()


def test_a_custom_delay_under_custom_is_still_a_pace():
    entry = Manifest.model_validate({"sources": [_entry(
        SHOP, robots="custom", robots_custom={"enforce_disallow": False,
                                              "crawl_delay_s": 30})]}).get(SHOP)

    fetcher = resolve_fetcher(entry, source_settings.layered({}, SHOP, entry),
                              {"min_interval_s": 1.0})

    try:
        assert fetcher._min_interval_s == 30.0
    finally:
        fetcher.close()


def test_the_command_line_crawl_runs_a_source_as_it_shipped(monkeypatch):
    """`scrapex crawl` writes to the local inbox and opens no warehouse, so there is no
    choice of his to read: it gets the shipped layer, not nothing."""
    seen = {}

    def spying(source, rules, crawl_settings=None):
        seen["rules"] = rules
        raise _Built

    monkeypatch.setattr(cli, "load_manifest", lambda *a, **k: MANIFEST)
    monkeypatch.setattr(cli, "build_connector", spying)
    with pytest.raises(_Built):
        # The command's own function: `cli.main` turns any exception into an exit code.
        cli._cmd_crawl(argparse.Namespace(source=SHOP, inbox=None, history=False))

    assert seen["rules"] == source_settings.layered({}, SHOP, MANIFEST.get(SHOP))
    assert seen["rules"].user_agent == "Shipped/1.0"


# ---- active: the schedule, the record, the Run menu ---------------------------------

def _due(conn, key: str, run_mode: str = "update") -> None:
    upsert_schedule(conn, key, frequency="daily", run_at="00:00", run_mode=run_mode)
    conn.execute("UPDATE schedule SET next_run_at = ? WHERE source_key = ?",
                 ((utcnow() - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), key))
    conn.commit()


def test_a_source_he_switched_on_fires_although_it_ships_off(conn):
    source_settings.save(conn, QUIET, source_settings.shipped_with(MANIFEST, QUIET), {"active": True})
    _due(conn, QUIET)

    assert len(fire_due(conn, manifest=MANIFEST)) == 1


def test_a_source_he_switched_off_does_not_fire_although_it_ships_on(conn):
    source_settings.save(conn, SHOP, source_settings.shipped_with(MANIFEST, SHOP), {"active": False})
    _due(conn, SHOP)

    assert fire_due(conn, manifest=MANIFEST) == []
    assert list_jobs(conn) == []


def test_with_no_choice_the_schedule_follows_the_manifest(conn):
    _due(conn, SHOP)
    _due(conn, QUIET)

    fired = fire_due(conn, manifest=MANIFEST)

    assert len(fired) == 1
    assert [job["source_keys"] for job in list_jobs(conn)] == [[SHOP]]


@pytest.fixture()
def reconciling(monkeypatch, tmp_path):
    """`reconcile_active` reads the manifest file itself; point it at this one."""
    import yaml

    import scrapex.config as config

    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(MANIFEST.model_dump(mode="json", exclude_none=True)),
                    encoding="utf-8")
    monkeypatch.setattr(config, "MANIFEST_FILE", path)
    return path


def _lifecycle(conn, key: str) -> str:
    return conn.execute("SELECT lifecycle FROM source_site WHERE source_key = ?",
                        (key,)).fetchone()[0]


def test_the_warehouse_record_follows_his_active(conn, reconciling):
    """`lifecycle` must say what the schedule acts on: his switch, over the manifest."""
    source_settings.save(conn, SHOP, source_settings.shipped_with(MANIFEST, SHOP), {"active": False})
    conn.commit()

    changed = storage.reconcile_active(conn)

    assert _lifecycle(conn, SHOP) == "paused"
    assert changed == {SHOP: False, QUIET: False}


@pytest.mark.parametrize(("change", "lifecycle", "active"), [
    pytest.param(None, "active", True, id="never-chosen-is-what-it-ships"),
    pytest.param([False], "paused", False, id="choose-off"),
    pytest.param([False, None], "active", True, id="choose-off-then-clear"),
    pytest.param([True], "active", True, id="choose-on"),
    pytest.param([True, None], "active", True, id="choose-on-then-clear"),
])
def test_a_directorys_record_and_its_answer_agree_at_every_step(
        conn, reconciling, change, lifecycle, active):
    """A built directory SHIPS ON (`directories.Directory.active`). Clearing his choice
    returns it there (his ruling), so `lifecycle` and `effective` say the same thing
    after every step -- before, a cleared choice left the record 'paused' while the
    answer had moved."""
    directory = directories.get(DIRECTORY)
    for value in change or ():
        source_settings.save(conn, DIRECTORY, directory, {"active": value})
        conn.commit()
        storage.reconcile_active(conn)

    storage.reconcile_active(conn)

    assert _lifecycle(conn, DIRECTORY) == lifecycle
    assert source_settings.effective(conn, DIRECTORY, directory).active is active


def test_a_source_the_release_does_not_name_is_left_alone_unless_he_chose(conn, reconciling):
    """An orphan -- in `source_site`, in neither the manifest nor the directory
    registry -- is `undeclared_sources`' business; switching it off would hide it."""
    conn.execute("INSERT INTO source_site (source_key, source_name, lifecycle) "
                 "VALUES ('GONE_SHOP', 'Gone', 'active')")
    conn.commit()
    storage.reconcile_active(conn)
    assert _lifecycle(conn, "GONE_SHOP") == "active"

    source_settings.save(conn, "GONE_SHOP", None, {"active": False})
    conn.commit()
    assert storage.reconcile_active(conn) == {"GONE_SHOP": False}


def test_a_manifest_with_a_rule_that_cannot_be_obeyed_never_loads(
        conn, monkeypatch, tmp_path):
    """THE REFUSAL HAPPENS AT THE DOOR, so `reconcile_active` never meets one: the
    manifest does not load, and an unloadable manifest reconciles nothing rather than
    reading as "every source is off"."""
    import yaml

    import scrapex.config as config

    broken = {"sources": [
        _entry(SHOP, active=False, robots="custom", robots_custom={"crawl_delay_s": 5}),
        _entry(QUIET, active=False)]}
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(broken), encoding="utf-8")
    monkeypatch.setattr(config, "MANIFEST_FILE", path)

    # 'paused' while the broken entry ships `active: false` and QUIET ships off too: a
    # reconcile that guessed `on` for the broken one, or read the rest anyway, moves it.
    conn.execute("UPDATE source_site SET lifecycle = 'paused' WHERE source_key = ?", (SHOP,))
    conn.commit()

    with pytest.raises(ValueError, match="a custom robots rule is"):
        config.load_manifest(path)
    assert storage.reconcile_active(conn) == {}
    assert _lifecycle(conn, SHOP) == "paused"
    assert _lifecycle(conn, QUIET) == "active", "an unloadable manifest reconciled anyway"


def test_the_run_menu_blocks_a_source_he_switched_off(conn):
    source_settings.save(conn, SHOP, source_settings.shipped_with(MANIFEST, SHOP), {"active": False})
    conn.commit()

    body = dryrun.dry_payload(SHOP, general=conn, price=conn, manifest=MANIFEST)

    assert all(one["blocked_by"] and "switched off" in one["blocked_by"]
               for one in body["passes"])


def test_the_run_menu_opens_a_source_he_switched_on(conn):
    source_settings.save(conn, QUIET, source_settings.shipped_with(MANIFEST, QUIET), {"active": True})
    conn.commit()

    body = dryrun.dry_payload(QUIET, general=conn, price=conn, manifest=MANIFEST)

    assert not any("switched off" in (one["blocked_by"] or "") for one in body["passes"])


# ---- the robots screen says what the crawl will do -------------------------------------

def _robots_screen(tmp_path, monkeypatch, manifest: Manifest, choices: dict) -> dict:
    """`GET /robots` for SHOP, his `choices` saved first, against a site whose robots.txt
    asks for a 10s delay."""
    import yaml
    from fastapi.testclient import TestClient

    from scrapex.webui.app import create_app

    database = tmp_path / "scrapex-engine.db"
    EngineDatabase(database).initialize()
    manifest_path = tmp_path / "sources.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True)),
        encoding="utf-8")
    with sqlite3.connect(database) as setup:
        setup.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                      (SHOP, SHOP))
        source_settings.save(setup, SHOP, source_settings.shipped_with(manifest, SHOP),
                             choices)
    client = TestClient(create_app(db_path=str(database), manifest_path=str(manifest_path)))

    real_client = httpx.Client

    def site(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(200, text="User-agent: *\nCrawl-delay: 10\n"))
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", site)
    answer = client.get(f"/api/sources/{SHOP}/robots")
    monkeypatch.setattr(httpx, "Client", real_client)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_robots_screen_shows_his_choice_not_the_manifests(tmp_path, monkeypatch):
    """`GET /robots` is read before he chooses; showing the manifest's `obey` while the
    crawl runs his custom rule is the #1413 defect over again."""
    body = _robots_screen(tmp_path, monkeypatch, MANIFEST, {
        "user_agent": "His/2.0", "robots": "custom",
        "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 0.0}})

    assert body["choice"] == "custom"
    assert body["custom"] == {"enforce_disallow": True, "crawl_delay_s": 0.0}
    assert body["user_agent"] == "His/2.0"
    assert body["on_a_disallowed_path"]["may_fetch"] is False
    assert body["on_a_disallowed_path"]["delay_s"] == 0.0


def test_his_rule_that_discloses_disallow_lets_the_path_be_fetched(tmp_path, monkeypatch):
    """The rule's `enforce_disallow` is his, carried as he set it: False fetches a
    disallowed path and says so."""
    body = _robots_screen(tmp_path, monkeypatch, MANIFEST, {
        "robots": "custom", "robots_custom": {"enforce_disallow": False,
                                              "crawl_delay_s": 4.0}})

    assert body["on_a_disallowed_path"]["may_fetch"] is True
    assert body["on_a_disallowed_path"]["delay_s"] == 4.0


SHIPS_CUSTOM = Manifest.model_validate({"sources": [_entry(
    SHOP, robots="custom", robots_custom={"enforce_disallow": False, "crawl_delay_s": 30})]})


def test_his_custom_rule_replaces_a_shipped_one_on_the_screen(tmp_path, monkeypatch):
    body = _robots_screen(tmp_path, monkeypatch, SHIPS_CUSTOM, {
        "robots": "custom", "robots_custom": {"enforce_disallow": True,
                                              "crawl_delay_s": 2.0}})

    assert body["custom"] == {"enforce_disallow": True, "crawl_delay_s": 2.0}


def test_his_obey_shows_no_shipped_custom_rule(tmp_path, monkeypatch):
    body = _robots_screen(tmp_path, monkeypatch, SHIPS_CUSTOM, {"robots": "obey"})

    assert (body["choice"], body["custom"]) == ("obey", None)


# ---- one broken source never stops the rest --------------------------------------------

def _bypassed(**broken):
    """A shipped entry carrying rules `SourceEntry` refuses. `model_copy` does not
    validate, which is how one would get past the manifest's checks: the second layer
    is what these tests hold."""
    return MANIFEST.get(SHOP).model_copy(update=broken)


BROKEN = [
    pytest.param({"robots": "Obey"}, "robots must be one of", id="misspelt-choice"),
    pytest.param({"robots": "custom",
                  "robots_custom": {"enforce_disallow": True, "crawl_delay_s": -1}},
                 "0 or more", id="negative-custom-delay"),
    pytest.param({"robots": "custom", "robots_custom": {"crawl_delay_s": 5}},
                 "a custom robots rule is", id="rule-without-enforce"),
]


@pytest.mark.parametrize(("broken", "says"), BROKEN)
def test_a_broken_source_does_not_stop_the_healthy_one_from_firing(conn, broken, says):
    """The worker calls `fire_due` before `_dispatch` (`jobs.JobRunner`), so a refusal
    raised out of it stopped EVERY job on every tick. Now the broken slot is spent, the
    reason is a failed job of that source's, and the healthy one is queued."""
    manifest = Manifest(sources=[_bypassed(**broken), MANIFEST.get(QUIET)
                                 .model_copy(update={"active": True})])
    _due(conn, SHOP, run_mode="full_rebuild")
    _due(conn, QUIET)

    queued = fire_due(conn, manifest=manifest)

    assert len(queued) == 1
    by_source = {job["source_keys"][0]: job for job in list_jobs(conn)}
    assert by_source[QUIET]["status"] == "queued"
    assert by_source[SHOP]["status"] == "failed"
    assert says in by_source[SHOP]["error_summary"]
    lines = jobs.job_logs(conn, by_source[SHOP]["job_ref"])
    assert any(line["level"] == "error" and says in line["message"]
               and line["source_key"] == SHOP for line in lines), (
        "the refusal's log line does not carry the source it is about")
    assert by_source[SHOP]["run_mode"] == "full_rebuild", (
        "the failed run is not the run the schedule asked for")
    assert SHOP in by_source[SHOP]["error_summary"], "the refusal does not name its source"

    # THE SLOT IS SPENT: the next tick neither queues it nor records it again.
    assert fire_due(conn, manifest=manifest) == []
    assert len([job for job in list_jobs(conn) if job["source_keys"] == [SHOP]]) == 1, (
        "the broken schedule was not re-armed, so every tick records it again")


@pytest.fixture()
def panel(tmp_path):
    import yaml
    from fastapi.testclient import TestClient

    from scrapex.webui.app import create_app

    database = tmp_path / "scrapex-engine.db"
    EngineDatabase(database).initialize()
    manifest_path = tmp_path / "sources.yaml"
    manifest_path.write_text(
        yaml.safe_dump(MANIFEST.model_dump(mode="json", exclude_none=True)),
        encoding="utf-8")
    return TestClient(create_app(db_path=str(database), manifest_path=str(manifest_path)),
                      raise_server_exceptions=False)


@pytest.mark.parametrize(("broken", "says"), BROKEN)
def test_the_routes_say_a_broken_rule_rather_than_answer_500(panel, monkeypatch,
                                                             broken, says):
    panel.app.state.manifest = Manifest(sources=[_bypassed(**broken), MANIFEST.get(QUIET)])
    monkeypatch.setattr(httpx, "Client", _no_network)

    for route in (f"/api/sources/{SHOP}/robots", f"/api/dry/{SHOP}"):
        answer = panel.get(route)
        assert answer.status_code == 400, (route, answer.status_code, answer.text)
        assert says in answer.json()["detail"], route


def _no_network(*args, **kwargs):
    raise AssertionError("the route reached the network before refusing")


@pytest.mark.parametrize(("broken", "says"), [
    pytest.param({"robots": "Obey"}, "robots must be one of", id="misspelt-choice"),
    pytest.param({"robots": "custom",
                  "robots_custom": {"enforce_disallow": True, "crawl_delay_s": -1}},
                 "0 or more", id="negative-custom-delay"),
    pytest.param({"robots": "custom", "robots_custom": {"crawl_delay_s": 5}},
                 "a custom robots rule is", id="rule-without-enforce"),
    pytest.param({"robots": "custom"}, "needs its rule", id="custom-without-a-rule"),
    pytest.param({"user_agent": "\u0645\u062a\u0635\u0641\u062d/1"}, "printable ASCII",
                 id="agent-not-ascii"),
    pytest.param({"crawl_pace_s": -1}, "crawl_pace_s must be more than 0",
                 id="negative-pace"),
    pytest.param({"crawl_pace_s": True}, "crawl_pace_s must be a number of seconds",
                 id="a-boolean-pace"),
    pytest.param({"crawl_pace_s": "5"}, "crawl_pace_s must be a number of seconds",
                 id="a-numeric-string-pace"),
])
def test_the_panel_refuses_rules_the_crawl_could_not_obey(panel, broken, says):
    """The broken rules came in by `/edit`, which wrote `robots: Obey` with a 200. They
    are saved by `/rules` now (#1584), which answers 400 with the checker's sentence --
    the one `SourceEntry` gives -- and stores nothing, not even the registry row."""
    before = panel.app.state.manifest.get(SHOP)

    answer = panel.post(f"/api/sources/{SHOP}/rules", json=broken)

    assert answer.status_code == 400, answer.text
    assert says in answer.json()["detail"]
    assert panel.app.state.manifest.get(SHOP) == before
    assert panel.get(f"/api/sources/{SHOP}/rules").json()["fields"]["robots"]["origin"] \
        == "source"


@pytest.mark.parametrize("start", ["paused", "draft"])
def test_a_directory_he_never_chose_for_is_recorded_as_it_ships(conn, reconciling, start):
    """A built directory ships ON, so with no choice of his its record becomes 'active'
    from whatever it held -- a start that a reconcile leaving it alone, or guessing off,
    would leave where it was."""
    conn.execute("UPDATE source_site SET lifecycle = ? WHERE source_key = ?",
                 (start, DIRECTORY))
    conn.commit()

    assert storage.reconcile_active(conn)[DIRECTORY] is True
    assert _lifecycle(conn, DIRECTORY) == "active"


@pytest.mark.parametrize("start", ["paused", "draft"])
def test_an_orphan_he_never_chose_for_keeps_whatever_it_held(conn, reconciling, start):
    conn.execute("INSERT INTO source_site (source_key, source_name, lifecycle) "
                 "VALUES ('GONE_SHOP', 'Gone', ?)", (start,))
    conn.commit()

    assert "GONE_SHOP" not in storage.reconcile_active(conn)
    assert _lifecycle(conn, "GONE_SHOP") == start


def test_a_source_whose_family_went_back_to_tbd_probe_does_not_fire(conn):
    """His stored `active` predates a release that put the family back to TBD-probe:
    there is no collector, so the schedule must not queue a run."""
    source_settings.save(conn, SHOP, MANIFEST.get(SHOP), {"active": True})
    reverted = Manifest(sources=[MANIFEST.get(SHOP).model_copy(
        update={"family": "TBD-probe", "active": False})])
    _due(conn, SHOP)

    assert fire_due(conn, manifest=reverted) == []
    assert list_jobs(conn) == []


def test_the_run_menu_reads_his_switch_from_the_warehouse_it_lives_in(conn, tmp_path):
    """`dry_payload` takes two connections; his switch is in the price-side one. Read
    from the other -- here an empty engine database -- it would be missed."""
    empty = EngineDatabase(tmp_path / "other.db")
    empty.initialize()
    source_settings.save(conn, SHOP, MANIFEST.get(SHOP), {"active": False})
    conn.commit()
    general = empty.connect()
    try:
        body = dryrun.dry_payload(SHOP, general=general, price=conn, manifest=MANIFEST)
    finally:
        general.close()

    reasons = [one["blocked_by"] or "" for one in body["passes"]]
    assert all("switched off" in reason for reason in reasons)
    assert not any("sources.yaml" in reason for reason in reasons), (
        "the switch he flipped is his own, in the warehouse, not the manifest's")


def test_a_schedule_no_registry_knows_is_spent_and_the_rest_still_fire(conn, tmp_path):
    """#1609. The engine hands `fire_due` a `SourceResolver`, whose `UnknownSource` is a
    `LookupError` and not a `KeyError`. A schedule for a key that neither the manifest
    nor `source_site` names -- a scheduled source removed from `sources.yaml` before its
    first crawl -- raised out of `fire_due` on every tick, and the worker then skipped
    `_dispatch`: no job started at all. Now the slot is re-armed without firing, and
    every other due schedule fires on the same tick."""
    from scrapex.sourceresolver import SourceResolver

    gone = "GONE_C"
    resolver = SourceResolver(
        MANIFEST, lambda: EngineDatabase(tmp_path / "scrapex-engine.db").connect())
    _due(conn, gone)
    _due(conn, SHOP)

    queued = fire_due(conn, manifest=resolver)

    assert [job["source_keys"] for job in list_jobs(conn)] == [[SHOP]]
    assert len(queued) == 1
    row = conn.execute("SELECT next_run_at FROM schedule WHERE source_key = ?",
                       (gone,)).fetchone()
    assert row[0] > utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), (
        "the unknown source's slot was not spent, so every tick meets it again")
    assert fire_due(conn, manifest=resolver) == []
