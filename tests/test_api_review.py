"""Spec 14: the review-queue API — suggest, decide, undo. Nothing auto-approves."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "harvest.db"
    conn = dbmod.connect(p)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row(product_name="LED Floodlight 400W")])])
    conn.execute("INSERT INTO material (material_name_en) VALUES ('Floodlight LED 400W')")
    conn.commit()
    conn.close()
    return p


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


def _queue(client):
    r = client.post("/api/review/suggest", json={"source_key": "ELSEWEDYSHOP"})
    assert r.status_code == 200
    return client.get("/api/review").json()["pending"]


def test_suggest_then_queue_is_pending_not_approved(client):
    pending = _queue(client)
    assert len(pending) == 1
    item = pending[0]
    assert item["incoming_name"] == "LED Floodlight 400W"
    assert item["material_name"] == "Floodlight LED 400W"
    assert item["confidence"] >= 0.55 and "name" in item["matched_fields"]


def test_suggest_requires_a_source_key(client):
    assert client.post("/api/review/suggest", json={}).status_code == 400


def test_approve_then_queue_is_empty(client):
    match_id = _queue(client)[0]["source_product_match_id"]
    r = client.post(f"/api/review/{match_id}", json={"decision": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert client.get("/api/review").json()["pending"] == []


def test_separate_keeps_them_apart_permanently(client):
    match_id = _queue(client)[0]["source_product_match_id"]
    client.post(f"/api/review/{match_id}", json={"decision": "separate"})
    assert client.get("/api/review").json()["pending"] == []
    # re-running the suggester must not resurface the same pair
    again = client.post("/api/review/suggest", json={"source_key": "ELSEWEDYSHOP"}).json()
    assert again["suggested"] == 0


def test_bad_decision_and_unknown_match(client):
    match_id = _queue(client)[0]["source_product_match_id"]
    assert client.post(f"/api/review/{match_id}", json={"decision": "nuke"}).status_code == 400
    assert client.post("/api/review/424242", json={"decision": "approve"}).status_code == 404


def test_undo_restores_and_is_idempotent(client):
    match_id = _queue(client)[0]["source_product_match_id"]
    client.post(f"/api/review/{match_id}", json={"decision": "approve"})
    assert client.post(f"/api/review/{match_id}/undo").status_code == 200
    assert client.post(f"/api/review/{match_id}/undo").status_code == 409   # nothing active left


def test_new_creates_a_material(client, db_path):
    match_id = _queue(client)[0]["source_product_match_id"]
    r = client.post(f"/api/review/{match_id}", json={"decision": "new"})
    assert r.status_code == 200
    conn = dbmod.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM material").fetchone()[0] == 2
    finally:
        conn.close()
