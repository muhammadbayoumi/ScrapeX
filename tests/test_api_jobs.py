"""Spec 4/23/24: the job API the side panel drives — enqueue, poll, control, tail.

The panel NEVER executes a crawl here: POST /api/jobs only queues. Execution is
the worker's, so these tests run with start_worker=False and drive run_job_once
directly when they need a finished job.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402

REAL_SOURCE = "ELSEWEDYSHOP"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "harvest.db"
    conn = dbmod.connect(p)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    return p


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))  # no worker thread


# ---- enqueue -----------------------------------------------------------------

def test_create_job_queues_without_executing(client):
    r = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE], "run_mode": "update"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued" and body["job_ref"].startswith("job_")

    state = client.get(f"/api/jobs/{body['job_ref']}").json()
    assert state["status"] == "queued"          # queued, NOT run by the request
    assert state["progress"] == {"done": 0, "total": 1, "percent": 0}
    assert state["started_at"] is None


def test_create_job_requires_source_keys(client):
    assert client.post("/api/jobs", json={}).status_code == 400


def test_create_job_rejects_unknown_source_before_queueing(client):
    r = client.post("/api/jobs", json={"source_keys": ["NOPE"]})
    assert r.status_code == 404
    assert client.get("/api/jobs").json()["jobs"] == []   # nothing was queued


def test_create_job_rejects_bad_run_mode(client):
    r = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE], "run_mode": "sideways"})
    assert r.status_code == 400


def test_create_job_accepts_multiple_sources(client):
    r = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE, "MADAR"]})
    assert r.status_code == 200 and r.json()["source_keys"] == [REAL_SOURCE, "MADAR"]


# ---- poll --------------------------------------------------------------------

def test_get_unknown_job_is_404(client):
    assert client.get("/api/jobs/job_nope").status_code == 404


def test_list_jobs_and_active_filter(client):
    ref = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE]}).json()["job_ref"]
    assert {j["job_ref"] for j in client.get("/api/jobs").json()["jobs"]} == {ref}
    active = client.get("/api/jobs", params={"active_only": True}).json()["jobs"]
    assert [j["job_ref"] for j in active] == [ref]


# ---- control -----------------------------------------------------------------

def test_pause_and_cancel_settle_a_queued_job_immediately(client):
    """A queued job is not held by the worker, so the intent is applied at once —
    parking it in 'pausing'/'cancelling' would strand it forever."""
    ref = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE]}).json()["job_ref"]
    paused = client.post(f"/api/jobs/{ref}/control", json={"control": "pause"})
    assert paused.status_code == 200 and paused.json()["status"] == "paused"

    cancelled = client.post(f"/api/jobs/{ref}/control", json={"control": "cancel"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    # terminal now, so a further control request is a conflict
    assert client.post(f"/api/jobs/{ref}/control", json={"control": "pause"}).status_code == 409


def test_control_rejects_bad_value_and_unknown_job(client):
    ref = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE]}).json()["job_ref"]
    assert client.post(f"/api/jobs/{ref}/control", json={"control": "explode"}).status_code == 400
    assert client.post("/api/jobs/job_nope/control", json={"control": "pause"}).status_code == 404


def test_control_on_a_finished_job_is_409(client, db_path):
    from scrapex.jobs import run_job_once
    from tests.test_jobs import _FakeManifest, _capture_ok

    ref = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE]}).json()["job_ref"]
    conn = dbmod.connect(db_path)
    try:
        run_job_once(conn, ref, _FakeManifest([REAL_SOURCE]), capture=_capture_ok([]))
    finally:
        conn.close()
    assert client.get(f"/api/jobs/{ref}").json()["status"] == "completed"
    assert client.post(f"/api/jobs/{ref}/control", json={"control": "pause"}).status_code == 409


# ---- log tail ----------------------------------------------------------------

def test_job_logs_tail_is_bounded_and_404s_for_unknown(client, db_path):
    from scrapex.jobs import run_job_once
    from tests.test_jobs import _FakeManifest, _capture_ok

    ref = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE]}).json()["job_ref"]
    conn = dbmod.connect(db_path)
    try:
        run_job_once(conn, ref, _FakeManifest([REAL_SOURCE]), capture=_capture_ok([]))
    finally:
        conn.close()

    body = client.get(f"/api/jobs/{ref}/logs").json()
    assert body["job_ref"] == ref and len(body["entries"]) >= 2
    assert any("job started" in e["message"] for e in body["entries"])
    # the tail is capped even when a caller asks for more
    assert len(client.get(f"/api/jobs/{ref}/logs", params={"limit": 9999}).json()["entries"]) <= 200
    assert client.get("/api/jobs/job_nope/logs").status_code == 404


# ---- change feed (spec 15/20) -----------------------------------------------

def test_changes_endpoint_reports_summary_and_feed(client, db_path):
    from scrapex.ingest import ingest_payloads
    from tests.test_ingest import make_entry, make_payload, one_row

    conn = dbmod.connect(db_path)
    try:
        entry = make_entry()
        ingest_payloads(conn, entry, [make_payload([one_row(effective_price="100.00")])])
        ingest_payloads(conn, entry, [make_payload([one_row(effective_price="130.00")],
                                                   scraped_at="2026-07-17T10:00:00Z")])
        conn.commit()
    finally:
        conn.close()

    body = client.get("/api/changes", params={"source_key": REAL_SOURCE}).json()
    assert body["summary"]["new"] == 2 and body["summary"]["price_increase"] == 1
    assert body["changes"][0]["change_type"] == "price_increase"   # newest first


def test_changes_endpoint_is_empty_for_a_quiet_source(client):
    body = client.get("/api/changes", params={"source_key": "MADAR"}).json()
    assert body["summary"] == {} and body["changes"] == []


def test_finished_job_reports_progress_and_counters(client, db_path):
    from scrapex.jobs import run_job_once
    from tests.test_jobs import _FakeManifest, _capture_ok

    ref = client.post("/api/jobs", json={"source_keys": [REAL_SOURCE]}).json()["job_ref"]
    conn = dbmod.connect(db_path)
    try:
        run_job_once(conn, ref, _FakeManifest([REAL_SOURCE]), capture=_capture_ok([]))
    finally:
        conn.close()
    state = client.get(f"/api/jobs/{ref}").json()
    assert state["status"] == "completed"
    assert state["progress"] == {"done": 1, "total": 1, "percent": 100}
    assert state["counters"]["observations"] == 3 and state["finished_at"] is not None


# ---- records for the panel's Browse Data screen (spec 20) -------------------

def test_records_are_paginated_for_the_panel(client, db_path):
    from scrapex.ingest import ingest_payloads
    from tests.test_ingest import make_entry, make_payload, one_row

    conn = dbmod.connect(db_path)
    try:
        rows = [one_row(external_product_id=str(2000 + i), external_variant_id=str(6000 + i),
                        product_name=f"Lamp {i}") for i in range(4)]
        ingest_payloads(conn, make_entry(), [make_payload(rows)])
        conn.commit()
    finally:
        conn.close()

    first = client.get("/api/records", params={"source_key": REAL_SOURCE, "limit": 2}).json()
    assert len(first["records"]) == 2 and first["next_cursor"] == 2
    last = client.get("/api/records",
                      params={"source_key": REAL_SOURCE, "limit": 50}).json()
    assert last["next_cursor"] is None          # client stops, never guesses


def test_records_respect_search_and_are_capped(client, db_path):
    body = client.get("/api/records",
                      params={"source_key": REAL_SOURCE, "q": "nothing-matches-this"}).json()
    assert body["records"] == [] and body["next_cursor"] is None
    capped = client.get("/api/records",
                        params={"source_key": REAL_SOURCE, "limit": 99999}).json()
    assert len(capped["records"]) <= 100
