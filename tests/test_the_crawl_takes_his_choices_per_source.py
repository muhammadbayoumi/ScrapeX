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

from scrapex import capture, cli, dryrun, source_settings, storage
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
    source_settings.save(conn, MANIFEST, SHOP, {
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
    source_settings.save(conn, MANIFEST, SHOP, {"user_agent": "His/2.0"})
    source_settings.save(conn, MANIFEST, SHOP, {"user_agent": None})
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
    entry = Manifest.model_validate({"sources": [_entry(
        SHOP, robots="obey", robots_custom={"enforce_disallow": False,
                                            "crawl_delay_s": 30})]}).get(SHOP)

    fetcher = resolve_fetcher(entry, source_settings.layered({}, SHOP, entry),
                              {"min_interval_s": 1.0})

    try:
        assert fetcher._min_interval_s == 1.0
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

def _due(conn, key: str) -> None:
    upsert_schedule(conn, key, frequency="daily", run_at="00:00")
    conn.execute("UPDATE schedule SET next_run_at = ? WHERE source_key = ?",
                 ((utcnow() - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"), key))
    conn.commit()


def test_a_source_he_switched_on_fires_although_it_ships_off(conn):
    source_settings.save(conn, MANIFEST, QUIET, {"active": True})
    _due(conn, QUIET)

    assert len(fire_due(conn, manifest=MANIFEST)) == 1


def test_a_source_he_switched_off_does_not_fire_although_it_ships_on(conn):
    source_settings.save(conn, MANIFEST, SHOP, {"active": False})
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
    source_settings.save(conn, MANIFEST, SHOP, {"active": False})
    conn.commit()

    changed = storage.reconcile_active(conn)

    assert _lifecycle(conn, SHOP) == "paused"
    assert changed == {SHOP: False, QUIET: False}


def test_a_directory_follows_his_active_only_when_he_chose(conn, reconciling):
    storage.reconcile_active(conn)
    assert _lifecycle(conn, DIRECTORY) == "active", (
        "a source the manifest does not name was switched off with no choice of his")

    source_settings.save(conn, MANIFEST, DIRECTORY, {"active": False})
    conn.commit()
    assert storage.reconcile_active(conn) == {DIRECTORY: False}
    assert _lifecycle(conn, DIRECTORY) == "paused"


def test_a_malformed_shipped_rule_leaves_that_source_alone_and_the_rest_reconciled(
        conn, monkeypatch, tmp_path):
    """One source's broken manifest entry must not stop the others' record from being
    put right -- and its own `active` is not guessed at."""
    import yaml

    import scrapex.config as config

    broken = {"sources": [
        _entry(SHOP, active=False, robots="custom", robots_custom={"crawl_delay_s": 5}),
        _entry(QUIET, active=False)]}
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(broken), encoding="utf-8")
    monkeypatch.setattr(config, "MANIFEST_FILE", path)

    assert storage.reconcile_active(conn) == {QUIET: False}
    assert _lifecycle(conn, SHOP) == "active"


def test_the_run_menu_blocks_a_source_he_switched_off(conn):
    source_settings.save(conn, MANIFEST, SHOP, {"active": False})
    conn.commit()

    body = dryrun.dry_payload(SHOP, general=conn, price=conn, manifest=MANIFEST)

    assert all(one["blocked_by"] and "switched off" in one["blocked_by"]
               for one in body["passes"])


def test_the_run_menu_opens_a_source_he_switched_on(conn):
    source_settings.save(conn, MANIFEST, QUIET, {"active": True})
    conn.commit()

    body = dryrun.dry_payload(QUIET, general=conn, price=conn, manifest=MANIFEST)

    assert not any("switched off" in (one["blocked_by"] or "") for one in body["passes"])


# ---- the robots screen says what the crawl will do -------------------------------------

def test_the_robots_screen_shows_his_choice_not_the_manifests(tmp_path, monkeypatch):
    """`GET /robots` is read before he chooses; showing the manifest's `obey` while the
    crawl runs his custom rule is the #1413 defect over again."""
    import yaml
    from fastapi.testclient import TestClient

    from scrapex.webui.app import create_app

    database = tmp_path / "scrapex-engine.db"
    EngineDatabase(database).initialize()
    manifest_path = tmp_path / "sources.yaml"
    manifest_path.write_text(
        yaml.safe_dump(MANIFEST.model_dump(mode="json", exclude_none=True)),
        encoding="utf-8")
    with sqlite3.connect(database) as setup:
        setup.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                      (SHOP, SHOP))
        source_settings.save(setup, MANIFEST, SHOP, {
            "user_agent": "His/2.0", "robots": "custom",
            "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 0.0}})
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
    body = answer.json()
    assert body["choice"] == "custom"
    assert body["custom"] == {"enforce_disallow": True, "crawl_delay_s": 0.0}
    assert body["user_agent"] == "His/2.0"
    assert body["on_a_disallowed_path"]["may_fetch"] is False
    assert body["on_a_disallowed_path"]["delay_s"] == 0.0
