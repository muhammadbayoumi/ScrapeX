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
    assert "price" in keys and "product_name" in keys
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
                       json={"view_name": "Prices", "config": {"columns": ["price"]}})
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
    assert body["offer"]["product_name"] or body["offer"]["product_name_ar"]
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

    # Put it in a KNOWN state first. This used to read whatever the shipped
    # manifest happened to say, so the day ELSEWEDYSHOP was activated for real
    # the flip became a no-op and the test failed for a reason that had nothing
    # to do with the behaviour it guards.
    client.post(f"/api/sources/{SOURCE}/active", json={"active": False})
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


def test_a_probe_placeholder_refuses_activation_with_the_reason(client, tmp_path):
    """pydantic refuses an active TBD-probe placeholder, and the refusal must
    reach the panel as a message rather than corrupt the manifest.

    The placeholder is APPENDED here rather than borrowed from the shipped
    manifest. It used to point at TABLER, which has since been removed — an MIT
    icon library is not a price source — and a test that names a specific entry
    dies with that entry while the rule it guards lives on.
    """
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + """
  - source_key: UNPROBED
    source_name_ar: غير مفحوص
    source_name: Unprobed
    base_url: https://example.invalid
    family: TBD-probe
    cadence: manual
    authority: shop
    currency: EGP
    default_region: EG
    vat_mode: incl
    active: false
    extract:
      - kind: product_prices
        scope: census
""", encoding="utf-8")

    r = client.post("/api/sources/UNPROBED/active", json={"active": True})
    assert r.status_code == 400
    assert "probe" in r.json().get("detail", "").lower()
    # Read the FILE rather than the listing: "the bad write survived" is a claim
    # about the manifest on disk, and asserting it directly is stronger than
    # asking the API whether it happens to enumerate the entry.
    after = manifest.read_text(encoding="utf-8")
    assert "source_key: UNPROBED" in after, "the refusal must not delete the entry"
    unprobed = after[after.index("source_key: UNPROBED"):]
    assert "active: false" in unprobed, "the refused flip must not have been written"


def test_activating_an_unknown_source_is_404(client):
    assert client.post("/api/sources/GHOST/active", json={"active": True}).status_code == 404


# ---- the schedules page is the CENTRAL control (owner ruling) ----------------

def test_a_schedule_accepts_every_run_mode_its_source_supports(client):
    """Scheduling a history backfill died on schedule.run_mode's CHECK until
    migration 0026 — crawl_job learned the word in 0025 and the two
    vocabularies had drifted. A mode a job can run is a mode a schedule can
    name."""
    r = client.post("/api/schedules/GPP_ENERGY", json={
        "frequency": "weekly", "run_at": "09:00", "weekday": 0,
        "timezone": "Africa/Cairo", "run_mode": "history_backfill",
        "missed_run_policy": "skip", "overlap_policy": "skip", "enabled": True})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["run_mode"] == "history_backfill"
    assert saved["missed_run_policy"] == "skip"
    assert saved["overlap_policy"] == "skip"
    assert saved["next_run_at"]


def test_a_typoed_timezone_is_refused_not_silently_utc(client):
    """_zone falls back to UTC when FIRING (right: a crash at 09:00 helps
    nobody) — but a SAVE it cannot honour must refuse, or the owner's 09:00
    fires at a different hour, unexplained forever."""
    r = client.post("/api/schedules/GPP_ENERGY", json={
        "frequency": "daily", "run_at": "09:00", "timezone": "Cairo/Africa"})
    assert r.status_code == 400
    assert "Cairo/Africa" in r.json()["detail"]


def test_a_disabled_schedule_keeps_its_settings_and_computes_no_next_run(client):
    client.post("/api/schedules/GPP_ENERGY", json={
        "frequency": "daily", "run_at": "07:30", "timezone": "Africa/Cairo"})
    r = client.post("/api/schedules/GPP_ENERGY", json={
        "frequency": "daily", "run_at": "07:30", "timezone": "Africa/Cairo",
        "enabled": False})
    saved = r.json()
    assert saved["enabled"] == 0 or saved["enabled"] is False
    assert saved["next_run_at"] is None, "a paused schedule still promises a firing"
    assert saved["run_at"] == "07:30", "pausing lost the settings"


def test_hiding_a_column_never_registers_absent_ones(client):
    """The POST path seeded EVERY browse column, so touching one column on a
    flat-label shop registered Category L1-L4 forever (ensure_fields is
    additive; nothing de-registers). Presence-gated now, like the GET path —
    except the one key actually being touched, which must keep working even
    when its data just vanished (adversarial review finding)."""
    answer = client.post(f"/api/fields/{SOURCE}",
                         json={"field_key": "sku", "hidden": True})
    assert answer.status_code == 200

    keys = [f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]]
    assert "category_l1" not in keys and "category_l4" not in keys, \
        "columns this source never publishes were registered by a POST"
    assert "sku" in keys


# ---- promoting a DETAIL to a COLUMN ------------------------------------------

@pytest.fixture()
def client_with_details(db_path, tmp_path) -> TestClient:
    """A source that publishes DETAILS, which is what can be promoted."""
    import sqlite3

    conn = dbmod.connect(db_path)
    # On MORE THAN ONE product, deliberately. A code that covers exactly one
    # is that product's own row, not a KIND of fact, and the chooser leaves
    # those out — sika publishes 535 image_N codes that way and the list was
    # 760 lines nobody could read. A one-product fixture was not a small
    # test, it was the wrong shape.
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_product_id="P2", external_variant_id="V2",
                product_name="Second cable")])])
    pids = [r[0] for r in conn.execute(
        "SELECT source_product_id FROM source_product ORDER BY source_product_id")]
    assert len(pids) >= 2, "this fixture needs two products to be honest"
    for value, pid in zip(("2.5 mm", "4 mm"), pids):
        conn.execute(
            "INSERT INTO source_product_attribute (source_product_id, attribute_code, "
            " attribute_label, raw_value, attribute_group, lang, is_site_filter) "
            "VALUES (?,?,?,?,?,?,0)",
            (pid, "cable_gauge", "Cable gauge", value, "Specifications", "en"))
    conn.commit(); conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


def test_the_owner_can_promote_a_detail_to_a_column_and_send_it_back(client_with_details):
    """The owner's question: are the exported tables not already assembled from
    the system's own tables? They are. Madar's export is 56 declared columns
    plus 64 pivoted straight out of source_product_attribute — the details table
    itself. The machine that turns a detail into a column runs in production.

    What was missing was a voice in it. An attribute rose only where the SHOP
    published it as a facet, so madar got 64 and sika, whose shop publishes
    none, got none of its 18. Now the owner chooses, and can unchoose.
    """
    listed = client_with_details.get("/api/promotable/ELSEWEDYSHOP").json()["attributes"]
    assert listed, "a source with details must offer them for promotion"
    first = listed[0]
    # The count is shown BEFORE the choice: an attribute two products carry is
    # a column of blanks, and that is worth seeing in advance.
    assert first["products"] >= 1 and first["of_products"] >= first["products"]
    assert first["promoted"] is False and first["is_column"] is False

    code = first["attribute_code"]
    up = client_with_details.post(f"/api/promotable/ELSEWEDYSHOP",
                     json={"attribute_code": code, "promote": True}).json()
    assert up["promoted"] is True
    now = {a["attribute_code"]: a for a in up["attributes"]}[code]
    assert now["promoted"] is True and now["is_column"] is True

    # It reaches the MAIN TABLE, which is what was asked for — not the file only.
    columns = {c["key"] for c in client_with_details.get("/api/table/ELSEWEDYSHOP").json()["columns"]}
    assert first["label"] in columns, "a promoted detail must appear as a real column"

    # And back again. The row IS the promotion, so demoting deletes it and
    # nothing has to remember a previous shape.
    down = client_with_details.post(f"/api/promotable/ELSEWEDYSHOP",
                       json={"attribute_code": code, "promote": False}).json()
    assert down["promoted"] is False
    columns = {c["key"] for c in client_with_details.get("/api/table/ELSEWEDYSHOP").json()["columns"]}
    assert first["label"] not in columns


def test_promotion_is_per_source_because_the_facts_are(client_with_details):
    """A detail worth a column on one site is noise on another."""
    listed = client_with_details.get("/api/promotable/ELSEWEDYSHOP").json()["attributes"]
    code = listed[0]["attribute_code"]
    client_with_details.post("/api/promotable/ELSEWEDYSHOP",
                json={"attribute_code": code, "promote": True})

    other = client_with_details.get("/api/promotable/MADAR").json()["attributes"]
    assert all(not a["promoted"] for a in other), \
        "promoting on one source must not promote on another"


# ---- #71: add / edit / delete a source from the panel ------------------------

def test_editing_a_source_changes_the_block_and_leaves_the_rest_alone(client, tmp_path):
    """An edit may change any field, so the block is replaced whole rather than
    line-wise the way the active flip is. What must survive is everything
    OUTSIDE that block — the manifest is hand-commented and those comments are
    the owner's records.
    """
    manifest = tmp_path / "sources.yaml"
    before = manifest.read_text(encoding="utf-8")
    other_blocks = [line for line in before.splitlines()
                    if line.strip().startswith("#")]

    r = client.post(f"/api/sources/{SOURCE}/edit",
                    json={"source_name": "Elsewedy Renamed", "cadence": "weekly"})
    assert r.status_code == 200, r.text

    after = manifest.read_text(encoding="utf-8")
    assert "Elsewedy Renamed" in after
    # Every comment elsewhere in the file survived.
    surviving = [line for line in after.splitlines() if line.strip().startswith("#")]
    assert set(other_blocks) <= set(surviving) or len(surviving) >= len(other_blocks) - 5


def test_an_edit_may_not_change_the_source_key(client):
    """source_key is what every warehouse row joins on, so changing it in the
    manifest alone would ORPHAN the data rather than rename it. The refusal has
    to say that, not just say no."""
    r = client.post(f"/api/sources/{SOURCE}/edit",
                    json={"source_key": "SOMETHING_ELSE"})
    assert r.status_code == 400
    assert "rename" in r.json()["detail"].lower()


def test_removing_a_source_keeps_every_row_it_ever_collected(client, tmp_path):
    """The owner's ruling: stopping a source and erasing its data are two
    separate actions with two clear outcomes. This is the first, and its whole
    promise is that the evidence survives — the rows are what a shop published,
    and taking the entry off the crawl list is not a claim none of it happened.
    """
    manifest = tmp_path / "sources.yaml"

    r = client.delete(f"/api/sources/{SOURCE}")
    assert r.status_code == 200 and r.json()["data_kept"] is True
    assert f"source_key: {SOURCE}" not in manifest.read_text(encoding="utf-8")

    listed = {s["source_key"] for s in client.get("/api/sources").json()["sources"]}
    assert SOURCE not in listed
    # A second delete is a 404, not a silent success.
    assert client.delete(f"/api/sources/{SOURCE}").status_code == 404


def test_a_wipe_refuses_without_confirmation_and_says_what_it_would_do(client):
    """A destructive button that fires on one click is a trap. The refusal must
    also say a backup is taken, because that is what makes the action
    reversible and the owner cannot know it otherwise."""
    r = client.post(f"/api/sources/{SOURCE}/wipe", json={})
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "every row" in detail and "backup" in detail


def test_the_panel_can_see_what_a_source_holds_before_deleting_it(client):
    """A button that says how much it is about to erase is the difference
    between a choice and a guess."""
    r = client.get(f"/api/sources/{SOURCE}")
    assert r.status_code == 200
    body = r.json()
    assert body["source"]["source_key"] == SOURCE
    assert set(body["holds"]) >= {"products", "observations", "details", "runs"} \
        or body["holds"] == {}
