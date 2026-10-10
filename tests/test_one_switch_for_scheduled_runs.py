"""One Active switch for a source's scheduled runs (#1596, his ruling D1: option 2).

`source_setting.active` stays the stored truth. These hold the engine half:

  * migration 0024 folds every paused schedule (`enabled = 0`) into `active = 0` for its
    source and re-enables the schedule, on a warehouse with mixed rows, and a schedule
    fires after it exactly as it fired before;
  * `POST /api/schedules/{key}` writes `active` and the schedule in one transaction,
    refuses a TBD-probe activation with the checker's sentence, and answers `active`.

Integration tests run the real `db/engine/schema.sql` plus the shipped migrations.
"""
from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex import source_settings
from scrapex.config import MANIFEST_FILE, load_manifest
from scrapex.databases.domain import EngineDatabase
from scrapex.ingest import get_source_id
from scrapex.scheduler import compute_next_run, fire_due, upsert_schedule
from scrapex.vocab import ConnectorFamily
from scrapex.webui.app import create_app

MIGRATION = "0024_one_switch_for_scheduled_runs.sql"
MANIFEST = load_manifest(MANIFEST_FILE)
#: Price sources that ship active and have a collector, so only the rows decide firing.
ACTIVE = [e for e in MANIFEST.sources
          if e.active and e.family != ConnectorFamily.TBD_PROBE][:6]
UNPROBED = next(e for e in MANIFEST.sources if e.family == ConnectorFamily.TBD_PROBE)
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
PAST = "2026-10-10T11:59:30Z"


def _at_0023(path, monkeypatch):
    """A warehouse built the way the engine builds one, stopped short of 0024."""
    db = EngineDatabase(path)
    whole = db._migrations
    at = [one.name for one in whole].index(MIGRATION)
    monkeypatch.setattr(db, "_migrations", whole[:at])
    db.initialize()
    return db, whole, at


#: Every `source_setting` column he decides, each away from its default.
HIS_CHOICES = {"active": True, "robots": "custom",
               "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 4.5},
               "user_agent": "ScrapeX-Test/1.0 (+https://example.com)",
               "crawl_pace_s": 2.5}


def _setting_rows(path) -> dict[str, dict]:
    """The whole stored `source_setting` row per source, every column but `updated_at`."""
    conn = dbmod.connect(path)
    try:
        return {r["source_key"]: {k: r[k] for k in r.keys()  # noqa: SIM118 -- a Row, not a dict
                                  if k not in ("source_key", "updated_at")}
                for r in conn.execute(
                    "SELECT ss.source_key, st.* FROM source_setting st"
                    " JOIN source_site ss ON ss.source_id = st.source_id")}
    finally:
        conn.close()


def _mixed_rows(path) -> dict[str, str]:
    """Every kind of row the fold meets, each due now. Returns role -> source_key."""
    a, b, c, d, orphan, manual = (e.source_key for e in ACTIVE)
    conn = dbmod.connect(path)
    for entry in ACTIVE[:4] + ACTIVE[5:]:
        get_source_id(conn, entry, entry.currency)          # registered, as a crawl does
    # b: EVERY choice he can store, set, so a fold that rewrites any column but `active`
    # (#1630 review: `user_agent = NULL`, a custom rule nulled) is caught.
    source_settings.save(conn, b, ACTIVE[1], HIS_CHOICES)
    # d: switched off by him, schedule enabled.
    source_settings.save(conn, d, ACTIVE[3], {"active": False})
    for key, enabled, frequency in ((a, 0, "daily"), (b, 0, "weekly"), (c, 1, "daily"),
                                    (d, 1, "daily"), (orphan, 0, "daily"),
                                    (manual, 0, "manual")):
        # A paused schedule holds no slot, as `upsert_schedule` stores it; an enabled
        # one is due now.
        upsert_schedule(conn, key, frequency=frequency, weekday=2, enabled=bool(enabled))
        if enabled:
            conn.execute("UPDATE schedule SET next_run_at = ? WHERE source_key = ?",
                         (PAST, key))
    conn.commit()
    conn.close()
    return {"paused": a, "paused_with_choices": b, "on": c, "off": d,
            "orphan": orphan, "manual": manual}


def _state(path):
    conn = dbmod.connect(path)
    try:
        schedules = {r["source_key"]: (r["enabled"], r["next_run_at"], r["frequency"])
                     for r in conn.execute("SELECT * FROM schedule")}
        settings = {r[0]: tuple(r[1:]) for r in conn.execute(
            "SELECT ss.source_key, st.active, st.robots_choice FROM source_setting st"
            " JOIN source_site ss ON ss.source_id = st.source_id")}
        return schedules, settings
    finally:
        conn.close()


def test_the_fold_turns_every_paused_schedule_into_active_off(tmp_path, monkeypatch):
    path = tmp_path / "w.db"
    db, whole, at = _at_0023(path, monkeypatch)
    keys = _mixed_rows(path)
    before_schedules, before_settings = _state(path)
    before_rows = _setting_rows(path)

    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    assert db.initialize() == [whole[at].number]
    schedules, settings = _state(path)
    rows = _setting_rows(path)

    for role in ("paused", "paused_with_choices", "manual"):
        key = keys[role]
        assert schedules[key][0] == 1, (role, schedules[key])
        assert settings[key][0] == 0, (role, settings.get(key))
    assert settings[keys["paused"]] == (0, None), "a row was inserted with more than active"
    # HIS WHOLE ROW SURVIVES, apart from `active`: robots, its custom rule, his agent
    # and his pace, column by column, as `source_settings.read` would serve them.
    chosen = keys["paused_with_choices"]
    assert before_rows[chosen]["active"] == 1
    assert rows[chosen] == {**before_rows[chosen], "active": 0}, "his other choices were lost"
    assert (rows[chosen]["robots_choice"], rows[chosen]["robots_enforce_disallow"],
            rows[chosen]["robots_crawl_delay_s"], rows[chosen]["user_agent"],
            rows[chosen]["crawl_pace_s"]) == (
        "custom", 1, 4.5, HIS_CHOICES["user_agent"], 2.5), rows[chosen]
    with dbmod.connect(path) as conn:
        assert source_settings.read(conn, chosen) == {
            **{k: v for k, v in HIS_CHOICES.items() if k != "robots"},
            "robots": source_settings.RobotsChoice.CUSTOM, "active": False}
    # Untouched: an enabled schedule, his own off, and the source never registered.
    assert schedules[keys["on"]] == before_schedules[keys["on"]]
    assert keys["on"] not in settings
    assert settings[keys["off"]] == before_settings[keys["off"]] == (0, None)
    assert schedules[keys["orphan"]] == before_schedules[keys["orphan"]]
    assert schedules[keys["orphan"]][0] == 0
    # The slots are not touched: the fold changes who may fire, never when.
    assert {k: v[1] for k, v in schedules.items()} \
        == {k: v[1] for k, v in before_schedules.items()}
    with dbmod.connect(path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_a_schedule_fires_after_the_fold_exactly_as_before(tmp_path, monkeypatch):
    """FIRING IS IDENTICAL: the same sources start, and every slot re-arms the same."""
    old = tmp_path / "old.db"
    db, whole, at = _at_0023(old, monkeypatch)
    keys = _mixed_rows(old)
    new = tmp_path / "new.db"
    shutil.copy(old, new)
    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    assert EngineDatabase(new).initialize() == [whole[at].number]

    fired = {}
    for name, path in (("old", old), ("new", new)):
        conn = dbmod.connect(path)
        refs = fire_due(conn, NOW, manifest=MANIFEST)
        fired[name] = (
            sorted(k for r in refs for k in conn.execute(
                "SELECT source_keys FROM crawl_job WHERE job_ref = ?", (r,)).fetchone()),
            {r["source_key"]: r["next_run_at"] for r in conn.execute("SELECT * FROM schedule")})
        conn.close()

    assert fired["new"] == fired["old"]
    assert fired["old"][0] == [f'["{keys["on"]}"]'], fired["old"][0]

    # AND A FOLDED SCHEDULE STAYS QUIET ONCE ARMED: `active = 0` alone now holds it.
    conn = dbmod.connect(new)
    conn.execute("UPDATE schedule SET next_run_at = ? WHERE source_key IN (?, ?)",
                 (PAST, keys["paused"], keys["paused_with_choices"]))
    conn.commit()
    assert fire_due(conn, NOW, manifest=MANIFEST) == []
    conn.close()


# ---- the route ----------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    db = tmp_path / "harvest.db"
    conn = dbmod.connect(db)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    test_client = TestClient(create_app(db, manifest_path=manifest))
    test_client.db = db
    return test_client


def _stored(client, key):
    conn = dbmod.connect(client.db)
    try:
        return (source_settings.read(conn, key).get("active"),
                conn.execute("SELECT enabled, frequency FROM schedule WHERE source_key = ?",
                             (key,)).fetchone())
    finally:
        conn.close()


def test_the_switch_saves_active_and_the_schedule_together(client):
    key = ACTIVE[0].source_key
    body = client.post(f"/api/schedules/{key}", json={
        "frequency": "daily", "run_at": "09:00", "active": False}).json()

    assert body["active"] is False, "the answer must say the slot will not fire"
    assert body["enabled"] == 1 and body["frequency"] == "daily"
    active, row = _stored(client, key)
    assert active is False and tuple(row) == (1, "daily")

    again = client.post(f"/api/schedules/{key}", json={
        "frequency": "daily", "run_at": "09:00", "active": True}).json()
    assert again["active"] is True and again["next_run_at"]
    assert _stored(client, key)[0] is True


def test_a_save_that_fails_stores_neither_half(client):
    """ONE TRANSACTION: a schedule the warehouse refuses leaves `active` as it was."""
    key = ACTIVE[0].source_key
    r = client.post(f"/api/schedules/{key}", json={
        "frequency": "daily", "run_mode": "sometimes", "active": False})

    assert r.status_code == 400, r.text
    assert _stored(client, key) == (None, None)


def test_a_source_still_awaiting_its_probe_cannot_be_switched_on(client):
    key = UNPROBED.source_key
    r = client.post(f"/api/schedules/{key}", json={"frequency": "daily", "active": True})

    assert r.status_code == 400
    assert key in r.json()["detail"] and "TBD-probe" in r.json()["detail"], r.json()
    assert _stored(client, key) == (None, None), "the schedule was saved without its switch"
    # The registration `_store_choices` made before the refusal is rolled back with it.
    conn = dbmod.connect(client.db)
    try:
        assert conn.execute("SELECT 1 FROM source_site WHERE source_key = ?",
                            (key,)).fetchone() is None, "the refusal left a source behind"
        assert conn.execute("SELECT COUNT(*) FROM source_setting").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("active", ["false", 0, None])
def test_active_must_be_a_boolean(client, active):
    key = ACTIVE[0].source_key
    r = client.post(f"/api/schedules/{key}", json={"frequency": "daily", "active": active})
    assert r.status_code == 400 and "active must be true or false" in r.json()["detail"]


def test_a_save_with_the_switch_always_enables_the_schedule(client):
    """`active` is the one switch: a schedule saved with it is never left paused by an
    `enabled` sent beside it, so it holds a slot to fire when the switch is on."""
    key = ACTIVE[0].source_key
    body = client.post(f"/api/schedules/{key}", json={
        "frequency": "daily", "enabled": False, "active": True}).json()
    assert body["enabled"] == 1 and body["next_run_at"], body


def test_without_active_the_route_saves_as_it_did(client):
    """An older panel sends `enabled` and no `active`: nothing of his choice is written."""
    key = ACTIVE[0].source_key
    body = client.post(f"/api/schedules/{key}",
                       json={"frequency": "daily", "enabled": False}).json()
    assert body["enabled"] == 0 and body["next_run_at"] is None
    assert body["active"] is True, "the effective switch, as the source ships it"
    assert _stored(client, key)[0] is None


def test_a_save_without_the_switch_records_no_choice(client):
    """A time-only save is not a decision about `active` (#1630 review E1): his choice
    stays unmade, the source keeps what it ships, and nothing is registered for it."""
    key = ACTIVE[0].source_key
    body = client.post(f"/api/schedules/{key}",
                       json={"frequency": "daily", "run_at": "07:15", "enabled": True}).json()
    assert body["run_at"] == "07:15" and body["active"] is True
    assert _stored(client, key)[0] is None
    assert client.get(f"/api/sources/{key}/rules").json()["fields"]["active"]["origin"] \
        == "source"
    conn = dbmod.connect(client.db)
    assert conn.execute("SELECT 1 FROM source_site WHERE source_key = ?",
                        (key,)).fetchone() is None
    conn.close()


def _folded_client(tmp_path, monkeypatch, *, registered=True, **schedule):
    """A paused schedule on a warehouse at 0023, migrated by the engine's own path, with
    an app over it: the state 0024 leaves -- enabled, not manual, no slot, `active = 0`.

    `registered=False` is the ORPHAN 0024 leaves alone: no `source_site` row, so the
    schedule keeps `enabled = 0`. `schedule` overrides the daily 09:00 UTC it stores."""
    path = tmp_path / "folded.db"
    db, whole, at = _at_0023(path, monkeypatch)
    entry = ACTIVE[0]
    conn = dbmod.connect(path)
    if registered:
        get_source_id(conn, entry, entry.currency)
    upsert_schedule(conn, entry.source_key,
                    **{"frequency": "daily", "run_at": "09:00", **schedule}, enabled=False)
    conn.commit()
    conn.close()
    monkeypatch.setattr(db, "_migrations", whole)
    assert db.initialize() == [whole[at].number]
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    test_client = TestClient(create_app(path, manifest_path=manifest))
    test_client.db = path
    return test_client, entry.source_key


def _fires(client, key) -> bool:
    conn = dbmod.connect(client.db)
    try:
        sched = conn.execute("SELECT next_run_at FROM schedule WHERE source_key = ?",
                             (key,)).fetchone()
        assert sched["next_run_at"], "the schedule holds no slot, so it can never fire"
        after = datetime.strptime(sched["next_run_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC) + timedelta(seconds=30)
        return len(fire_due(conn, after, manifest=MANIFEST)) == 1
    finally:
        conn.close()


@pytest.mark.parametrize("route,body", [
    ("/api/sources/{key}/active", {"active": True}),
    ("/api/sources/{key}/rules", {"active": True}),
    # Clearing his off where the source ships on is an activation too.
    ("/api/sources/{key}/rules", {"active": None}),
])
def test_a_folded_schedule_switched_on_from_any_route_fires(tmp_path, monkeypatch,
                                                            route, body):
    """#1630 review E2: on, and read as on, must mean it fires."""
    client, key = _folded_client(tmp_path, monkeypatch)
    assert _stored(client, key)[0] is False
    r = client.post(route.format(key=key), json=body)
    assert r.status_code == 200, r.text
    assert _fires(client, key)


def _schedule_row(client, key) -> dict:
    conn = dbmod.connect(client.db)
    try:
        return dict(conn.execute("SELECT * FROM schedule WHERE source_key = ?",
                                 (key,)).fetchone())
    finally:
        conn.close()


@pytest.mark.parametrize("route", ["/api/sources/{key}/active", "/api/sources/{key}/rules"])
def test_the_re_arm_keeps_his_day_time_and_zone(tmp_path, monkeypatch, route):
    """#1630 review: the re-arm must arm the slot HE stored -- weekly, Thursday, 17:45
    in Tokyo -- not the defaults (daily, 09:00, UTC, Monday) `upsert_schedule` falls to.
    17:45 Tokyo is 08:45 UTC, so no default lands on the same instant."""
    client, key = _folded_client(tmp_path, monkeypatch, frequency="weekly",
                                 run_at="17:45", tz_name="Asia/Tokyo", weekday=3,
                                 run_mode="initial_crawl", overlap_policy="skip")
    before = _schedule_row(client, key)
    assert (before["enabled"], before["next_run_at"]) == (1, None), before

    start = datetime.now(UTC)
    r = client.post(route.format(key=key), json={"active": True})
    end = datetime.now(UTC)
    assert r.status_code == 200, r.text

    after = _schedule_row(client, key)
    slots = {compute_next_run("weekly", "17:45", "Asia/Tokyo", 3, moment).strftime(
        "%Y-%m-%dT%H:%M:%SZ") for moment in (start, end)}
    assert after["next_run_at"] in slots, (after["next_run_at"], slots)
    armed = datetime.strptime(after["next_run_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC)
    assert (armed.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%a %H:%M")) == "Thu 17:45"
    # Everything else he stored is stored still.
    assert {k: v for k, v in after.items() if k != "next_run_at"} \
        == {k: v for k, v in before.items() if k != "next_run_at"}
    assert _fires(client, key)


def _paused_by_an_older_panel(tmp_path):
    """A registered source whose schedule an older panel paused with `enabled = false`
    and no `active` -- after 0024 ran, so nothing folded it."""
    db = tmp_path / "harvest.db"
    conn = dbmod.connect(db)
    dbmod.migrate(conn)
    get_source_id(conn, ACTIVE[0], ACTIVE[0].currency)
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    client = TestClient(create_app(db, manifest_path=manifest))
    client.db = db
    key = ACTIVE[0].source_key
    body = client.post(f"/api/schedules/{key}",
                       json={"frequency": "daily", "enabled": False}).json()
    assert (body["enabled"], body["next_run_at"]) == (0, None), body
    return client, key


@pytest.mark.parametrize("route,body", [
    ("/api/sources/{key}/active", {"active": True}),
    ("/api/sources/{key}/rules", {"active": True}),
    ("/api/sources/{key}/rules", {"active": None}),
])
@pytest.mark.parametrize("paused", ["orphan_0024_left", "older_panel"])
def test_switching_a_source_on_never_re_enables_a_paused_schedule(
        tmp_path, monkeypatch, route, body, paused):
    """#1630 review: the re-arm wakes only a schedule that is `enabled`. One stored with
    `enabled = 0` -- the orphan 0024 left, or one an older panel paused -- is a pause the
    switch on /active or /rules did not make, so it stays paused and holds no slot."""
    if paused == "orphan_0024_left":
        client, key = _folded_client(tmp_path, monkeypatch, registered=False)
    else:
        client, key = _paused_by_an_older_panel(tmp_path)
    before = _schedule_row(client, key)
    assert (before["enabled"], before["next_run_at"]) == (0, None), before

    r = client.post(route.format(key=key), json=body)
    assert r.status_code == 200, r.text

    assert _schedule_row(client, key) == before
    conn = dbmod.connect(client.db)
    try:
        assert source_settings.effective(conn, key, ACTIVE[0]).active is True
        assert fire_due(conn, datetime.now(UTC) + timedelta(days=8),
                        manifest=MANIFEST) == []
    finally:
        conn.close()


def test_an_orphan_switched_on_from_its_row_is_registered_armed_and_fires(
        tmp_path, monkeypatch):
    """End to end: the orphan 0024 left (`enabled = 0`, no `source_site`), switched on
    from its Schedules row, is registered, enabled, armed -- and fires."""
    client, key = _folded_client(tmp_path, monkeypatch, registered=False)
    assert _schedule_row(client, key)["enabled"] == 0
    conn = dbmod.connect(client.db)
    assert conn.execute("SELECT 1 FROM source_site WHERE source_key = ?",
                        (key,)).fetchone() is None
    conn.close()

    r = client.post(f"/api/schedules/{key}", json={
        "frequency": "daily", "run_at": "09:00", "active": True})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True and r.json()["enabled"] == 1

    conn = dbmod.connect(client.db)
    assert conn.execute("SELECT 1 FROM source_site WHERE source_key = ?",
                        (key,)).fetchone() is not None
    conn.close()
    assert _stored(client, key)[0] is True
    row = _schedule_row(client, key)
    assert row["enabled"] == 1 and row["next_run_at"], row
    assert _fires(client, key)


def test_a_switch_turned_off_arms_nothing(tmp_path, monkeypatch):
    client, key = _folded_client(tmp_path, monkeypatch)
    client.post(f"/api/sources/{key}/active", json={"active": False})
    conn = dbmod.connect(client.db)
    assert conn.execute("SELECT next_run_at FROM schedule WHERE source_key = ?",
                        (key,)).fetchone()[0] is None
    conn.close()


def test_the_web_page_points_at_the_panels_switch_not_auto(client):
    """The panel no longer says "Auto" anywhere (#1630 review P1)."""
    off = next(e for e in MANIFEST.sources
               if not e.active and e.family != ConnectorFamily.TBD_PROBE)
    client.post(f"/api/schedules/{off.source_key}", json={"frequency": "daily"})
    page = client.get("/schedules").text
    assert "Scheduled runs are off for this source." in page
    assert "under Settings, Jobs and scheduling" in page
    assert "until Auto is enabled" not in page


def test_the_panel_harness_compiles_without_a_warning():
    """Its routes are JavaScript inside a Python f-string, so a `\\/` written once where
    `\\\\/` was meant is a SyntaxWarning on every import (#1630 review) -- and a regex
    that only works because Python passes an unknown escape through."""
    import warnings
    from pathlib import Path

    harness = Path(__file__).resolve().parents[1] / "tools" / "panel_harness.py"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compile(harness.read_text(encoding="utf-8"), str(harness), "exec")
