"""Spec 22 through the API + a real export: hiding a column never loses data."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.fields import CURRENT_VIEW, ORIGINAL_SCHEMA  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.publish import publish_source  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402

SOURCE = "ELSEWEDYSHOP"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "harvest.db"
    conn = dbmod.connect(p)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.commit()
    conn.close()
    return p


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


class _MemorySink:
    """Captures what a real publish would have written."""
    def __init__(self): self.tabs = {}
    def ensure_workbook(self, folder, workbook): return "wb"
    def write_tab(self, handle, tab, header, rows): self.tabs[tab] = (header, rows)
    def location(self, handle): return "memory://wb"


def test_fields_are_discovered_from_the_real_export(client):
    body = client.get(f"/api/fields/{SOURCE}").json()
    keys = [f["field_key"] for f in body["fields"]]
    assert "effective_price" in keys and "currency" in keys
    assert all(f["display_name"] is None and not f["is_hidden"] for f in body["fields"])


def test_rename_and_hide_through_the_api(client):
    client.get(f"/api/fields/{SOURCE}")
    r = client.post(f"/api/fields/{SOURCE}",
                    json={"field_key": "currency", "display_name": "Currency code"})
    assert r.status_code == 200
    field = next(f for f in r.json()["fields"] if f["field_key"] == "currency")
    assert field["label"] == "Currency code" and field["original_name"] == "currency"

    r = client.post(f"/api/fields/{SOURCE}", json={"field_key": "currency", "hidden": True})
    field = next(f for f in r.json()["fields"] if f["field_key"] == "currency")
    assert field["is_hidden"] is True     # still listed — hidden, not gone


def test_unknown_field_is_404(client):
    client.get(f"/api/fields/{SOURCE}")
    assert client.post(f"/api/fields/{SOURCE}",
                       json={"field_key": "ghost", "hidden": True}).status_code == 404


def test_reset_restores_everything(client):
    client.get(f"/api/fields/{SOURCE}")
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "currency", "hidden": True})
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "currency", "display_name": "X"})
    fields = client.post(f"/api/fields/{SOURCE}", json={"reset": True}).json()["fields"]
    assert all(f["display_name"] is None and not f["is_hidden"] for f in fields)


def test_saved_views_crud(client):
    client.get(f"/api/fields/{SOURCE}")
    made = client.post(f"/api/views/{SOURCE}",
                       json={"view_name": "Prices", "config": {"columns": ["effective_price"]}})
    assert made.status_code == 200
    view_id = made.json()["saved_view_id"]
    assert client.get(f"/api/fields/{SOURCE}").json()["views"][0]["view_name"] == "Prices"
    assert client.delete(f"/api/views/{view_id}").status_code == 200
    assert client.delete(f"/api/views/{view_id}").status_code == 404


def test_view_name_is_required(client):
    assert client.post(f"/api/views/{SOURCE}", json={}).status_code == 400


# ---- the invariant that matters: hidden != deleted --------------------------

def test_hidden_column_is_dropped_from_the_view_but_kept_in_the_original(client, db_path):
    client.get(f"/api/fields/{SOURCE}")
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "currency", "hidden": True})

    conn = dbmod.connect(db_path)
    try:
        view_sink, orig_sink = _MemorySink(), _MemorySink()
        publish_source(conn, SOURCE, view_sink, "f", "wb", schema=CURRENT_VIEW)
        publish_source(conn, SOURCE, orig_sink, "f", "wb", schema=ORIGINAL_SCHEMA)
    finally:
        conn.close()

    view_header, view_rows = view_sink.tabs[SOURCE]
    orig_header, orig_rows = orig_sink.tabs[SOURCE]
    assert "currency" not in view_header          # the owner's arrangement
    assert "currency" in orig_header              # the raw contract is intact
    assert len(orig_rows[0]) == len(view_rows[0]) + 1   # no value was destroyed


def test_unhiding_brings_the_column_back_with_its_data(client, db_path):
    client.get(f"/api/fields/{SOURCE}")
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "currency", "hidden": True})
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "currency", "hidden": False})

    conn = dbmod.connect(db_path)
    try:
        sink = _MemorySink()
        publish_source(conn, SOURCE, sink, "f", "wb", schema=CURRENT_VIEW)
    finally:
        conn.close()
    header, rows = sink.tabs[SOURCE]
    assert "currency" in header and rows[0][header.index("currency")] == "EGP"
