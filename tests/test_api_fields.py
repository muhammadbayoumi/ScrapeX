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
    # GET /api/fields seeds from THIS SOURCE's present browse columns now, not
    # from export_source_table's constant header — merely opening the panel used
    # to register columns the source does not publish, and ensure_fields is
    # additive, so they stayed in the list forever.
    assert "effective_price" in keys and "product_name" in keys
    assert all(f["display_name"] is None and not f["is_hidden"] for f in body["fields"])


def test_rename_and_hide_through_the_api(client):
    client.get(f"/api/fields/{SOURCE}")
    r = client.post(f"/api/fields/{SOURCE}",
                    json={"field_key": "sku", "display_name": "Product code"})
    assert r.status_code == 200
    field = next(f for f in r.json()["fields"] if f["field_key"] == "sku")
    assert field["label"] == "Product code" and field["original_name"] == "sku"

    r = client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})
    field = next(f for f in r.json()["fields"] if f["field_key"] == "sku")
    assert field["is_hidden"] is True     # still listed — hidden, not gone


def test_unknown_field_is_404(client):
    client.get(f"/api/fields/{SOURCE}")
    assert client.post(f"/api/fields/{SOURCE}",
                       json={"field_key": "ghost", "hidden": True}).status_code == 404


def test_reset_restores_everything(client):
    client.get(f"/api/fields/{SOURCE}")
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "display_name": "X"})
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
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})

    conn = dbmod.connect(db_path)
    try:
        view_sink, orig_sink = _MemorySink(), _MemorySink()
        publish_source(conn, SOURCE, view_sink, "f", "wb", schema=CURRENT_VIEW)
        publish_source(conn, SOURCE, orig_sink, "f", "wb", schema=ORIGINAL_SCHEMA)
    finally:
        conn.close()

    view_header, view_rows = view_sink.tabs[SOURCE]
    orig_header, orig_rows = orig_sink.tabs[SOURCE]
    assert "sku" not in view_header               # the owner's arrangement
    assert "currency" in orig_header              # the raw contract is intact
    assert len(orig_rows[0]) == len(view_rows[0]) + 1   # no value was destroyed


def test_unhiding_brings_the_column_back_with_its_data(client, db_path):
    client.get(f"/api/fields/{SOURCE}")
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": False})

    conn = dbmod.connect(db_path)
    try:
        sink = _MemorySink()
        publish_source(conn, SOURCE, sink, "f", "wb", schema=CURRENT_VIEW)
    finally:
        conn.close()
    header, rows = sink.tabs[SOURCE]
    assert "currency" in header and rows[0][header.index("currency")] == "EGP"


def test_hiding_a_column_actually_removes_it_from_the_grid(client):
    """The defect the owner hit: Hide this column did nothing at all.

    Three breaks in one chain, and no test crossed the layers to see any of them.
    The grid's menu names a column the side panel may never have registered, so
    the UPDATE matched zero rows and answered 404; the grid reloaded past it; and
    /api/table built its column list from `column_presence` alone and would have
    ignored the choice even if it had been stored. Hiding is only real when the
    payload the grid actually reads stops carrying the column.
    """
    before = client.get(f"/api/table/{SOURCE}").json()
    keys = [c["key"] for c in before["columns"]]
    assert "sku" in keys, "fixture no longer publishes the column this test hides"

    hidden = client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})
    assert hidden.status_code == 200, hidden.text

    after = client.get(f"/api/table/{SOURCE}").json()
    assert "sku" not in [c["key"] for c in after["columns"]]
    # The DATA is untouched: hiding is a view, never a delete.
    assert after["rows"][0]["sku"] == before["rows"][0]["sku"]


def test_showing_every_column_brings_a_hidden_one_back(client):
    """The recovery path. A hidden column that no control can restore is the
    failure the owner called catastrophic, and it is only closed if the reverse
    of the operation is proven, not assumed."""
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})
    assert "sku" not in [c["key"] for c in client.get(f"/api/table/{SOURCE}").json()["columns"]]

    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": False})
    assert "sku" in [c["key"] for c in client.get(f"/api/table/{SOURCE}").json()["columns"]]


def test_resetting_the_view_restores_every_hidden_column(client):
    """Reset the layout is the last resort in the column menu; it has to work
    without the owner knowing which columns they hid."""
    start = [c["key"] for c in client.get(f"/api/table/{SOURCE}").json()["columns"]]
    for key in start:
        client.post(f"/api/fields/{SOURCE}", json={"field_key": key, "hidden": True})
    # Every column hidden is the worst case and the one that matters: the owner
    # reaches for Reset precisely when the table has gone blank.
    assert client.get(f"/api/table/{SOURCE}").json()["columns"] == []

    client.post(f"/api/fields/{SOURCE}", json={"reset": True})
    assert [c["key"] for c in client.get(f"/api/table/{SOURCE}").json()["columns"]] == start


# ---- the Start fresh endpoint (this file already builds a seeded app) --------

def test_start_fresh_requires_the_typed_phrase(client):
    response = client.post("/api/storage/start-fresh", json={"confirm": "yes"})
    assert response.status_code == 400
    assert "start fresh" in response.json()["detail"]


def test_start_fresh_is_refused_while_a_crawl_runs(client, db_path):
    """Resetting under a live run would tear it in half: fetched pages ingest
    into a database that no longer exists. The refusal must come BEFORE any
    file is touched."""
    import sqlite3

    from scrapex.jobs import create_job

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    ref = create_job(conn, ["ELSEWEDYSHOP"])
    conn.execute("UPDATE crawl_job SET status='running' WHERE job_ref=?", (ref,))
    conn.commit(); conn.close()

    response = client.post("/api/storage/start-fresh", json={"confirm": "start fresh"})
    assert response.status_code == 409

    check = sqlite3.connect(db_path)
    assert check.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] > 0
    check.close()


def test_start_fresh_resets_and_the_old_rows_survive_on_disk(client, db_path):
    before = client.get(f"/api/table/{SOURCE}").json()
    assert before["total"] > 0

    response = client.post("/api/storage/start-fresh", json={"confirm": "start fresh"})
    assert response.status_code == 200, response.text
    assert "intact" in response.json()["detail"]

    after = client.get(f"/api/table/{SOURCE}").json()
    assert after["total"] == 0, "the new database still shows old rows"

    import sqlite3
    sealed = list(db_path.parent.glob("*.reset-backup-*.db"))
    assert len(sealed) == 1
    kept = sqlite3.connect(sealed[0])
    assert kept.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] > 0
    kept.close()


# ---- /api/offer: the inline History panel's data ----------------------------

def test_the_offer_api_serves_identity_periods_observations_and_changes(client, db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    offer_id = conn.execute("SELECT offer_id FROM source_offer").fetchone()[0]
    conn.close()

    body = client.get(f"/api/offer/{SOURCE}/{offer_id}").json()
    assert body["offer"]["offer_id"] == offer_id
    assert body["offer"]["name"]
    assert isinstance(body["periods"], list)
    assert isinstance(body["observations"], list) and body["observations"]
    assert isinstance(body["changes"], list)
    for c in body["changes"]:
        assert "field_label" in c and "display_change" in c, \
            "the panel would render schema vocabulary raw"


def test_the_offer_api_refuses_an_offer_belonging_to_another_source(client, db_path):
    """Same boundary as the HTML page: /source/A/offer/<id> must not render
    source B's offer to anyone who can count."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    offer_id = conn.execute("SELECT offer_id FROM source_offer").fetchone()[0]
    conn.close()

    assert client.get(f"/api/offer/GPP_ENERGY/{offer_id}").status_code == 404


# ---- activation from the interface -------------------------------------------

def test_flipping_active_changes_one_line_and_keeps_every_comment(client, tmp_path):
    """The manifest is hand-commented and those comments are the owner's
    records. The flip must be surgical: one line changes, every other byte
    survives."""
    manifest = tmp_path / "sources.yaml"
    before = manifest.read_text(encoding="utf-8")

    r = client.post(f"/api/sources/{SOURCE}/active", json={"active": True})
    assert r.status_code == 200 and r.json()["active"] is True

    after = manifest.read_text(encoding="utf-8")
    diff = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert len(diff) == 1, f"more than one line changed: {diff[:3]}"
    assert diff[0][0].strip() == "active: false"
    assert diff[0][1].strip() == "active: true"
    # And the engine's own view reloaded: the API now reports it active.
    listed = {s["source_key"]: s for s in client.get("/api/sources").json()["sources"]}
    assert listed[SOURCE]["active"] is True


def test_a_probe_placeholder_refuses_activation_with_the_reason(client):
    """ARAMCO is family TBD-probe: pydantic refuses an active placeholder, and
    the refusal must reach the panel as a message, not corrupt the manifest."""
    r = client.post("/api/sources/ARAMCO_FUEL_SA/active", json={"active": True})
    assert r.status_code == 400
    listed = {s["source_key"]: s for s in client.get("/api/sources").json()["sources"]}
    assert listed["ARAMCO_FUEL_SA"]["active"] is False, "the bad write survived"


def test_activating_an_unknown_source_is_404(client):
    assert client.post("/api/sources/GHOST/active", json={"active": True}).status_code == 404
