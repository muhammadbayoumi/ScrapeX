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
from scrapex import fields
from scrapex.config import MANIFEST_FILE
from scrapex.ingest import ingest_payloads
from scrapex.webui.app import create_app
from tests.test_ingest import make_entry, make_payload, one_row

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

@pytest.mark.parametrize("path", [
    f"/source/{SOURCE}",
    f"/api/fields/{SOURCE}",
    f"/api/table/{SOURCE}",
    f"/api/promotable/{SOURCE}",
    f"/export/{SOURCE}.xlsx",
])
def test_a_price_source_read_commits_nothing(client, db_path, path):
    status = {}
    wrote = committed_by_others(
        db_path, lambda: status.update(code=client.get(path).status_code))

    assert status["code"] == 200, f"GET {path} answered {status['code']}"
    assert not wrote, f"GET {path} committed a write to the warehouse"
    assert registered(db_path, SOURCE) == [], f"GET {path} registered columns"


@pytest.mark.parametrize("path", [
    "/api/fields/contractors",
    "/source/contractors",
    "/api/table/contractors",
])
def test_a_dataset_read_commits_nothing(warehouse, path):
    file = warehouse.engine.path
    client = TestClient(create_app(databases=warehouse))
    status = {}
    wrote = committed_by_others(
        file, lambda: status.update(code=client.get(path).status_code))

    assert status["code"] == 200, f"GET {path} answered {status['code']}"
    assert not wrote, f"GET {path} committed a write to the warehouse"
    assert registered(file, "contractors") == [], f"GET {path} registered columns"


def test_the_chooser_still_offers_what_it_offered(client):
    """Not writing must not change the answer: the seed, in the agreed order."""
    offered = [f["field_key"] for f in client.get(f"/api/fields/{SOURCE}").json()["fields"]]

    assert "price" in offered and "product_name" in offered
    ranked = sorted(offered, key=lambda key: fields_rank(key))
    assert offered == ranked, "the chooser no longer lists in the agreed order"


def fields_rank(key: str) -> int:
    from scrapex.reports import COLUMN_RANK
    return COLUMN_RANK[key]


def test_the_excel_export_does_not_wait_for_a_writer(client, db_path):
    """The defect a person could see: Export pressed while the engine writes.

    Before the fix this took 5.55 s and answered 500 on this very fixture,
    because the export tried to register its columns and SQLite made it wait for
    the writer's lock until `busy_timeout` ran out.
    """
    writer = sqlite3.connect(db_path, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    try:
        started = time.perf_counter()
        response = client.get(f"/export/{SOURCE}.xlsx")
        took = time.perf_counter() - started
    finally:
        writer.execute("ROLLBACK")
        writer.close()

    assert response.status_code == 200, (
        f"the export failed behind a writer: {response.status_code} {response.text[:120]}")
    assert took < 2.0, f"the export waited {took:.2f}s for a lock it has no reason to take"


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


# ---- 3 · the rule that lets a read answer as if it had written ---------------

def test_a_read_answers_exactly_what_registering_would_have_left(tmp_path):
    """`fields_as_seeded` and `ensure_fields` + `list_fields`, compared on one state
    that has everything: registered, hidden, renamed, reordered, and unseen."""
    def prepare(path):
        conn = dbmod.connect(path)
        dbmod.migrate(conn)
        fields.ensure_fields(conn, "SHOP", ["a", "b", "c"])
        fields.set_visibility(conn, "SHOP", "b", True)
        fields.set_display_name(conn, "SHOP", "c", "Sea")
        fields.reorder(conn, "SHOP", ["c", "a"])
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
