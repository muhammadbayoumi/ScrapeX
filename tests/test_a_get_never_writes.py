"""A GET never writes to the warehouse (#1192).

THREE READS WROTE. `GET /source/{key}` and `GET /api/fields/{key}` called
`ensure_fields` and committed — so opening the Data page or the column chooser
inserted `dataset_field` rows, without the write lock every other write in the
engine takes. The Excel export called it too, through `fields.apply_schema`; it
rolled the rows back, but had to take the database's write lock to try, so behind
any writer it waited five seconds and failed with a bare 500. Measured before the
fix on this file's own fixture: 16 rows from one GET, and the export at 5.55 s
and 500 while another connection held a write. On his warehouse, 10 of 12 price
sources carried export columns nobody had registered.

GET is a safe method: the client asks for no change (RFC 9110 §9.2.1). So a read
now shows the columns as they would be registered (`fields.fields_as_seeded`),
and the rows are written by the one write that needs them — `POST /api/fields`,
under the write lock — which registers exactly the list the read showed, in the
order it showed it.
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex import fields, outputs
from scrapex.config import MANIFEST_FILE
from scrapex.ingest import ingest_payloads
from scrapex.publish import publish_source, workbook_tables
from scrapex.reports import column_presence, column_seed, export_source_table
from scrapex.webui.app import create_app
from tests.test_ingest import make_entry, make_payload, one_row
from tests.test_outputs import FakeFunnel, FakeSink

# The approved `contractors` dataset, built the way the product builds it.
from tests.test_the_chooser_tells_the_truth_about_a_dataset import (
    PRICE_KEYS_FOUND_IN_THE_WILD,
    schema_keys,
    warehouse,
)

SOURCE = "ELSEWEDYSHOP"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest),
                      raise_server_exceptions=False)


def registered(path: Path, source_key: str) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [row[0] for row in conn.execute(
            "SELECT field_key FROM dataset_field WHERE source_key = ? "
            "ORDER BY display_order, dataset_field_id", (source_key,))]
    finally:
        conn.close()


def committed_by_others(path: Path, fn) -> bool:
    """Did anything commit to the file while `fn` ran?

    `PRAGMA data_version` changes on a connection when ANOTHER connection
    commits, which is exactly the question — and it sees a commit whatever table
    it touched, so this guard does not have to know which table a read wrote.
    """
    watcher = sqlite3.connect(path)
    try:
        before = watcher.execute("PRAGMA data_version").fetchone()[0]
        fn()
        return watcher.execute("PRAGMA data_version").fetchone()[0] != before
    finally:
        watcher.close()


# ---- 1 · the reads -----------------------------------------------------------

PRICE_READS = [
    f"/source/{SOURCE}",
    f"/api/fields/{SOURCE}",
    f"/api/table/{SOURCE}",
    f"/api/promotable/{SOURCE}",
    f"/export/{SOURCE}.xlsx",
]
DATASET_READS = [
    "/api/fields/contractors",
    "/source/contractors",
    "/api/table/contractors",
]

# What `main` offered in Choose-Columns on this fixture before the fix, captured
# by running its code (d218f6fd) — the independent answer "not writing did not
# change what he is offered" is checked against, membership AND agreed order.
OFFERED_BEFORE = [
    "product_name", "country_code_alpha2", "sku", "display_method", "price",
    "minimum_quantity", "quantity_increment", "stock_quantity", "availability",
    "tax", "brand", "category_leaf", "category_leaf_ar", "price_changed_on",
    "last_confirmed_on", "curation",
]


@pytest.mark.parametrize("path", PRICE_READS)
def test_a_price_source_read_commits_nothing(client, db_path, path):
    status = {}
    wrote = committed_by_others(
        db_path, lambda: status.update(code=client.get(path).status_code))

    assert status["code"] == 200, f"GET {path} answered {status['code']}"
    assert not wrote, f"GET {path} committed a write to the warehouse"
    assert registered(db_path, SOURCE) == [], f"GET {path} registered columns"


@pytest.mark.parametrize("path", DATASET_READS)
def test_a_dataset_read_commits_nothing(warehouse, path):
    file = warehouse.engine.path
    client = TestClient(create_app(databases=warehouse))
    status = {}
    wrote = committed_by_others(
        file, lambda: status.update(code=client.get(path).status_code))

    assert status["code"] == 200, f"GET {path} answered {status['code']}"
    assert not wrote, f"GET {path} committed a write to the warehouse"
    assert registered(file, "contractors") == [], f"GET {path} registered columns"


def test_the_watcher_sees_a_commit_when_there_is_one(client, db_path):
    """The positive control. Without it, every "commits nothing" guard above could
    pass because `PRAGMA data_version` never moves, not because nothing wrote."""
    wrote = committed_by_others(db_path, lambda: client.post(
        f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True}))

    assert wrote, "a POST that registers and hides committed, and the watcher missed it"


def test_the_chooser_still_offers_what_it_offered(client):
    """Not writing must not change the answer: every column, in the agreed order."""
    offered = [f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]]

    assert offered == OFFERED_BEFORE


def behind_a_writer(file: Path, client: TestClient, path: str):
    """GET `path` while another connection holds the database's write lock."""
    writer = sqlite3.connect(file, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    try:
        started = time.perf_counter()
        response = client.get(path)
        return response, time.perf_counter() - started
    finally:
        writer.execute("ROLLBACK")
        writer.close()


@pytest.mark.parametrize("path", PRICE_READS)
def test_a_price_source_read_does_not_wait_for_a_writer(client, db_path, path):
    """The defect a person could see: Export pressed while the engine writes.

    Before the fix the export took 5.55 s and answered 500 on this very fixture,
    because it tried to register its columns and SQLite made it wait for the
    writer's lock until `busy_timeout` ran out. Every read is held to it, not the
    export alone: a read that INSERTs without committing passes the commit guards
    above and still fails here.
    """
    response, took = behind_a_writer(db_path, client, path)

    assert response.status_code == 200, (
        f"GET {path} failed behind a writer: {response.status_code} {response.text[:120]}")
    assert took < 2.0, f"GET {path} waited {took:.2f}s for a lock it has no reason to take"


@pytest.mark.parametrize("path", DATASET_READS)
def test_a_dataset_read_does_not_wait_for_a_writer(warehouse, path):
    client = TestClient(create_app(databases=warehouse), raise_server_exceptions=False)
    response, took = behind_a_writer(warehouse.engine.path, client, path)

    assert response.status_code == 200, (
        f"GET {path} failed behind a writer: {response.status_code} {response.text[:120]}")
    assert took < 2.0, f"GET {path} waited {took:.2f}s for a lock it has no reason to take"


# ---- 2 · the one write that registers ----------------------------------------

def test_the_first_change_keeps_the_order_the_chooser_showed(client, db_path):
    """The POST registers the list the GET showed, BEFORE changing one column.

    Otherwise the column he hid first would be the first row written, and jump to
    the top of his list the next time he opened it.
    """
    shown = [f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]]
    middle = shown[len(shown) // 2]

    response = client.post(f"/api/fields/{SOURCE}",
                           json={"field_key": middle, "hidden": True})
    assert response.status_code == 200, response.text

    after = client.get(f"/api/fields/{SOURCE}").json()["fields"]
    assert [f["field_key"] for f in after] == shown, "his first change reordered the list"
    assert [f["field_key"] for f in after if f["is_hidden"]] == [middle]
    assert registered(db_path, SOURCE) == shown, "the write registered a different list"


def test_a_datasets_first_change_keeps_its_order(warehouse):
    client = TestClient(create_app(databases=warehouse))
    shown = [f["field_key"] for f in client.get("/api/fields/contractors").json()["fields"]]
    last = shown[-1]

    response = client.post("/api/fields/contractors",
                           json={"field_key": last, "hidden": True})
    assert response.status_code == 200, response.text

    after = [f["field_key"] for f in client.get("/api/fields/contractors").json()["fields"]]
    assert after == shown, "hiding one contractor column reordered his list"


def test_hiding_a_contractor_column_writes_no_price_key(warehouse):
    """The POST took the price path for every key, and `column_presence` answers
    eleven ungated price keys for a key it does not know — so one hide wrote
    `price`, `tax` and nine more against the directory."""
    client = TestClient(create_app(databases=warehouse))
    response = client.post("/api/fields/contractors",
                           json={"field_key": "membership_level", "hidden": True})
    assert response.status_code == 200, response.text

    written = set(registered(warehouse.engine.path, "contractors"))
    leaked = sorted(written & set(PRICE_KEYS_FOUND_IN_THE_WILD))
    assert not leaked, f"hiding a contractor column registered price keys: {leaked}"
    assert written == schema_keys(warehouse), (
        f"the write registered something other than the directory's own fields: "
        f"{sorted(written ^ schema_keys(warehouse))}")


def test_a_field_the_dataset_does_not_have_is_404(warehouse):
    """It used to be registered on the spot and then hidden, like any other."""
    client = TestClient(create_app(databases=warehouse))
    response = client.post("/api/fields/contractors",
                           json={"field_key": "price", "hidden": True})
    assert response.status_code == 404, response.text


def test_on_an_arranged_source_the_table_lists_new_columns_as_the_chooser_does(
        client, db_path):
    """He arranged two columns; the source publishes more that were never placed.

    Those columns stay unregistered until his next save now, so the table and
    Choose-Columns must agree on where they go meanwhile — and a save that
    changes nothing about order (a rename) must not move the table. The table's
    arranged branch used to break the tie on the key's spelling.
    """
    conn = dbmod.connect(db_path)
    try:
        fields.ensure_fields(conn, SOURCE, ["price", "product_name"])
        fields.reorder(conn, SOURCE, ["price", "product_name"])
        conn.commit()
    finally:
        conn.close()

    def table_order():
        return [c["key"] for c in client.get(f"/api/table/{SOURCE}").json()["columns"]]

    chooser = [f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]
               if not f["is_hidden"]]
    table = table_order()
    shared = [key for key in table if key in chooser]

    in_chooser_order = [key for key in chooser if key in shared]
    assert shared == in_chooser_order, (
        "the table and Choose-Columns order the unplaced columns differently: "
        f"table {shared}, chooser {in_chooser_order}")

    response = client.post(f"/api/fields/{SOURCE}",
                           json={"field_key": "price", "display_name": "Unit price"})
    assert response.status_code == 200, response.text
    assert table_order() == table, "a rename moved the columns of the table"


# ---- 3 · a publish is a write, and registers what it exported ----------------

def expected_registration(db_path: Path) -> list[str]:
    """What the first registration of a source must write, in order: the seed
    Choose-Columns shows, then every other exported column."""
    conn = dbmod.connect(db_path)
    try:
        seed = column_seed(column_presence(conn, SOURCE))
        header, _ = export_source_table(conn, SOURCE)
    finally:
        conn.close()
    return seed + [key for key in header if key not in seed]


def publish(db_path: Path, schema: str = fields.ORIGINAL_SCHEMA) -> None:
    conn = dbmod.connect(db_path)
    try:
        publish_source(conn, SOURCE, FakeSink(), "folder", "book", schema=schema)
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("schema", [fields.ORIGINAL_SCHEMA, fields.CURRENT_VIEW])
def test_a_publish_registers_what_it_exported_so_he_can_hide_it(client, db_path, schema):
    """Registering export-only columns is what puts them in Choose-Columns.

    The first version of this fix took registration out of `apply_schema` for
    every caller, the committing publish included, so no path registered a
    column that is not a browse column: the chooser never offered `country`, a
    hide answered 404, and the current-view export kept it. A publish holds the
    write lock and commits, so it registers again; a download does not. Both
    schemas the panel's "Columns to export" setting offers are held to it.
    """
    publish(db_path, schema)

    assert registered(db_path, SOURCE) == expected_registration(db_path), (
        "a publish registered something other than the seed, then the rest of the export")

    offered = {f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]}
    assert "country" in offered, "an exported column is still not offered after a publish"

    response = client.post(f"/api/fields/{SOURCE}",
                           json={"field_key": "country", "hidden": True})
    assert response.status_code == 200, response.text

    conn = dbmod.connect(db_path)
    try:
        header, rows = export_source_table(conn, SOURCE)
        shown, _ = fields.apply_schema(conn, SOURCE, header, rows, fields.CURRENT_VIEW)
    finally:
        conn.close()
    assert "country" not in shown, "he hid the column and the current-view export kept it"


def test_a_publish_keeps_the_order_the_chooser_showed(client, db_path):
    """Reads no longer register, so a publish may be the first write a source
    sees. Registering the export header as written reordered 15 of 16 columns in
    Choose-Columns (gate pass 2): the list must be the one he was just shown,
    with the exported extras after it."""
    before = [f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]]
    publish(db_path)
    after = [f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]]

    assert after[:len(before)] == before, "a publish reordered the columns he was shown"


def test_a_publish_does_not_move_an_arranged_table(client, db_path):
    conn = dbmod.connect(db_path)
    try:
        fields.ensure_fields(conn, SOURCE, ["price", "product_name"])
        fields.reorder(conn, SOURCE, ["price", "product_name"])
        conn.commit()
    finally:
        conn.close()

    def table_order():
        return [c["key"] for c in client.get(f"/api/table/{SOURCE}").json()["columns"]]

    before = table_order()
    publish(db_path)
    assert table_order() == before, "a publish moved the columns of an arranged table"


def test_a_current_view_publish_registers_no_label_as_a_column(client, db_path):
    """Registration happens before the schema projects the header. After it, the
    current view's header holds his LABELS — registering that would write
    `Unit price` as a new field key, and registration only ever adds."""
    response = client.post(f"/api/fields/{SOURCE}",
                           json={"field_key": "price", "display_name": "Unit price"})
    assert response.status_code == 200, response.text

    publish(db_path, fields.CURRENT_VIEW)

    assert "Unit price" not in registered(db_path, SOURCE), (
        "his renamed label was registered as a column of its own")


def test_the_sheet_send_registers_what_it_sent(db_path):
    funnel = FakeFunnel()
    conn = dbmod.connect(db_path)
    try:
        outputs.apps_script_send(conn, SOURCE, client=funnel)
        conn.commit()
    finally:
        conn.close()
    assert funnel.sent, "the send sent nothing"
    assert registered(db_path, SOURCE) == expected_registration(db_path), (
        "the Apps Script send registered something other than the seed, then the "
        "rest of what it exported")


def test_only_a_caller_that_commits_asks_the_workbook_to_register(db_path):
    """The flag is the whole difference between the download and the publish."""
    conn = dbmod.connect(db_path)
    try:
        workbook_tables(conn, SOURCE)
        assert fields.list_fields(conn, SOURCE) == [], "a download registered columns"

        workbook_tables(conn, SOURCE, register=True)
        written = [f["field_key"] for f in fields.list_fields(conn, SOURCE)]
    finally:
        conn.close()
    assert written == expected_registration(db_path)


# ---- 4 · the rule that lets a read answer as if it had written ---------------

def arranged_by_hand(conn):
    fields.ensure_fields(conn, "SHOP", ["a", "b", "c"])
    fields.set_visibility(conn, "SHOP", "b", True)
    fields.set_display_name(conn, "SHOP", "c", "Sea")
    fields.reorder(conn, "SHOP", ["c", "a"])


def reset_after_another_source(conn):
    """display_order with GAPS, the state 6 of his 14 source keys are in.

    `reset_view` sets display_order = dataset_field_id, and another source
    registered first pushes those ids up, so MAX(display_order) + 1 is far from
    COUNT(*). A next-position rule that counted rows would pass the contiguous
    state and fail this one."""
    fields.ensure_fields(conn, "OTHER", ["x", "y", "z", "w"])
    fields.ensure_fields(conn, "SHOP", ["a", "b", "c"])
    fields.reset_view(conn, "SHOP")
    fields.set_visibility(conn, "SHOP", "a", True)


@pytest.mark.parametrize("state", [arranged_by_hand, reset_after_another_source],
                         ids=["contiguous", "gaps"])
def test_a_read_answers_exactly_what_registering_would_have_left(tmp_path, state):
    """`fields_as_seeded` and `ensure_fields` + `list_fields`, compared on states
    that between them have everything: registered, hidden, renamed, reordered,
    reset, gaps in display_order, and unseen."""
    def prepare(path):
        conn = dbmod.connect(path)
        dbmod.migrate(conn)
        state(conn)
        conn.commit()
        return conn

    seed = ["a", "d", "b", "e", "d"]          # a known, a repeat and two unseen
    read = prepare(tmp_path / "read.db")
    wrote = prepare(tmp_path / "wrote.db")
    try:
        before = read.total_changes
        as_read = fields.fields_as_seeded(read, "SHOP", seed)
        assert read.total_changes == before, "fields_as_seeded wrote"

        fields.ensure_fields(wrote, "SHOP", seed)
        as_written = fields.list_fields(wrote, "SHOP")

        assert as_read == as_written
        assert fields.visible_columns(read, "SHOP", seed) == [
            f["field_key"] for f in as_written if not f["is_hidden"]]
    finally:
        read.close()
        wrote.close()


def test_an_unregistered_field_has_the_schemas_default_type(tmp_path):
    """`UNREGISTERED_TYPE` restates `dataset_field.data_type`'s DEFAULT; this keeps
    the two from drifting apart."""
    conn = dbmod.connect(tmp_path / "type.db")
    dbmod.migrate(conn)
    try:
        default = next(row["dflt_value"] for row in conn.execute(
            "PRAGMA table_info(dataset_field)") if row["name"] == "data_type")
    finally:
        conn.close()
    assert default == repr(fields.UNREGISTERED_TYPE), (
        f"the schema defaults data_type to {default}, the read says "
        f"{fields.UNREGISTERED_TYPE!r}")
