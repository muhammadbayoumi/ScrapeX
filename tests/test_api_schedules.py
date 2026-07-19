"""Spec 26 through the API — including that we state the honest limitation."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402

SOURCE = "ELSEWEDYSHOP"


@pytest.fixture()
def client(tmp_path) -> TestClient:
    db = tmp_path / "harvest.db"
    conn = dbmod.connect(db)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db, manifest_path=manifest))


def test_setting_a_daily_schedule_arms_a_next_run(client):
    r = client.post(f"/api/schedules/{SOURCE}", json={
        "frequency": "daily", "run_at": "09:00", "timezone": "Asia/Riyadh"})
    assert r.status_code == 200
    body = r.json()
    assert body["frequency"] == "daily" and body["timezone"] == "Asia/Riyadh"
    assert body["next_run_at"] is not None and body["next_run_at"].endswith("Z")


def test_schedules_are_listed_with_the_honest_limitation(client):
    client.post(f"/api/schedules/{SOURCE}", json={"frequency": "daily"})
    body = client.get("/api/schedules").json()
    assert len(body["schedules"]) == 1
    # The API itself refuses to imply background magic.
    assert "sleeping or powered-off" in body["note"]


def test_manual_schedule_has_no_next_run(client):
    body = client.post(f"/api/schedules/{SOURCE}", json={"frequency": "manual"}).json()
    assert body["next_run_at"] is None


def test_disabling_disarms_it(client):
    client.post(f"/api/schedules/{SOURCE}", json={"frequency": "daily"})
    body = client.post(f"/api/schedules/{SOURCE}",
                       json={"frequency": "daily", "enabled": False}).json()
    assert body["enabled"] == 0 and body["next_run_at"] is None


def test_unknown_source_and_bad_frequency_are_rejected(client):
    assert client.post("/api/schedules/NOPE", json={"frequency": "daily"}).status_code == 404
    assert client.post(f"/api/schedules/{SOURCE}",
                       json={"frequency": "hourly"}).status_code == 400


def test_policies_round_trip(client):
    body = client.post(f"/api/schedules/{SOURCE}", json={
        "frequency": "weekly", "weekday": 2, "run_at": "06:30",
        "missed_run_policy": "skip", "overlap_policy": "skip",
        "run_mode": "initial_crawl"}).json()
    assert body["missed_run_policy"] == "skip" and body["overlap_policy"] == "skip"
    assert body["weekday"] == 2 and body["run_mode"] == "initial_crawl"
