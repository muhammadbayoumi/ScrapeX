"""Choose-Columns on a dataset table: it offered the wrong columns, then ignored them.

TWO DEFECTS, ONE ENDPOINT, and both were measured in the owner's live warehouse
on 2026-08-22 rather than reasoned about.

FIRST, IT OFFERED THE PRICE HEADER. `/api/fields/{key}` had no catalogue branch,
so a dataset key fell through to the price path and asked `column_presence` —
"which BROWSE columns does this source populate" — about a contractor directory.
`ensure_fields` is additive by design, so merely OPENING the panel wrote eleven
price-path keys against `contractors`:

    display_method, price, minimum_quantity, quantity_increment,
    stock_quantity, tax, category_leaf, category_leaf_ar,
    price_changed_on, last_confirmed_on, curation

Eleven rows, and not one of the directory's own 28 fields among them.

SECOND, HIDING ONE DID NOTHING AT ALL. `dataset_table_payload` built its columns
from `field_definition` and never read `dataset_field`, so the arrangement saved
and the screen did not change. That is the defect the panel's `datatable.js`
already warns about in its own comment — *"dragging a column saved, reloaded the
page, and changed nothing on screen because the grid was reading its own copy"* —
arriving from the other direction.

WHY THE PAIR MATTERS MORE THAN EITHER HALF. A chooser that offers the wrong
columns and then ignores the answer is worse than one that is simply absent: it
is a control that lies twice, and `R-45` rests on this mechanism working, because
a hidden column is not lost but MOVED — into the row's own card.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import ApprovalField, CandidateApproval, SnapshotCreate
from scrapex.extract.muqawil import listing_candidate
from scrapex.fields import set_display_name, set_visibility
from scrapex.webui.app import create_app

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")

# The eleven that were actually there. Kept verbatim so a reader can see the
# defect rather than a description of it.
PRICE_KEYS_FOUND_IN_THE_WILD = (
    "display_method", "price", "minimum_quantity", "quantity_increment",
    "stock_quantity", "tax", "category_leaf", "category_leaf_ar",
    "price_changed_on", "last_confirmed_on", "curation",
)


@pytest.fixture()
def warehouse(tmp_path: Path):
    """One approved `contractors` dataset, and the registry that holds it."""
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        snapshot = service.save_snapshot(conn, SnapshotCreate(
            source_url="https://muqawil.org/en/contractors?page=1",
            html_content=LISTING))
        candidate = listing_candidate(LISTING)
        service.approve_candidate(
            conn, int(snapshot["page_snapshot_id"]),
            CandidateApproval(
                table_index=0, site_key="muqawil_org",
                site_display_name="SCA", dataset_key="contractors",
                dataset_name="Contractors",
                fields=[ApprovalField(
                    field_key=f.field_key, display_name=f.source_name,
                    data_type="text",
                    identity=(f.field_key == "contractor_id"))
                    for f in candidate.fields]),
            candidate=candidate)
        conn.commit()
    finally:
        conn.close()
    return registry


def schema_keys(registry) -> set[str]:
    conn = registry.engine.connect()
    try:
        resolved = service.dataset_schema_fields(conn, "contractors")
        assert resolved is not None, "the fixture did not approve a dataset"
        return {row["field_key"] for row in resolved[1]}
    finally:
        conn.close()


def payload(registry, **kw):
    conn = registry.engine.connect()
    try:
        return service.dataset_table_payload(conn, "contractors", **kw)
    finally:
        conn.close()


def open_the_chooser(registry) -> dict:
    """What the owner does before he can arrange anything.

    NOT A SHORTCUT AROUND THE ENDPOINT, and the first version of this file was
    wrong to skip it: `set_visibility` is an UPDATE, so with no `dataset_field`
    row it matches nothing and silently succeeds. A column he was never offered
    is a column he cannot hide, and the seeding is `GET /api/fields`'s job.
    """
    return TestClient(create_app(databases=registry)).get(
        "/api/fields/contractors").json()


def arrange(registry, fn):
    """Open the chooser, then change one thing in it — in that order."""
    open_the_chooser(registry)
    conn = registry.engine.connect()
    try:
        fn(conn)
        conn.commit()
    finally:
        conn.close()


# ---- 1 · what the chooser is allowed to offer -------------------------------

def test_the_chooser_offers_the_datasets_own_fields(warehouse):
    """Its own schema, not the price header the price path would have supplied."""
    client = TestClient(create_app(databases=warehouse))

    body = client.get("/api/fields/contractors").json()
    offered = {field["field_key"] for field in body["fields"]}

    assert offered, "the chooser offers nothing at all for a dataset"
    assert offered <= schema_keys(warehouse), (
        f"the chooser offers columns the directory does not publish: "
        f"{sorted(offered - schema_keys(warehouse))}")
    assert "company_name" in offered, "its own identity column is not offered"


def test_no_price_key_is_ever_offered_for_a_dataset(warehouse):
    """The defect itself: opening the panel must not import the price header."""
    client = TestClient(create_app(databases=warehouse))

    body = client.get("/api/fields/contractors").json()
    offered = {field["field_key"] for field in body["fields"]}

    leaked = sorted(offered & set(PRICE_KEYS_FOUND_IN_THE_WILD))
    assert not leaked, f"price-path keys reached a contractor directory: {leaked}"


def test_price_keys_already_on_disk_are_not_listed(warehouse):
    """They cannot be un-written by seeding correctly; they must go inert.

    `ensure_fields` is additive, so the eleven rows in his warehouse would simply
    be JOINED by the 28 real ones. Deleting them is a destructive migration and
    `COMPATIBILITY.md` puts that behind a review gate that is HIS — so the panel
    stops believing them instead, and nothing on disk is destroyed.
    """
    arrange(warehouse, lambda conn: [
        conn.execute(
            "INSERT INTO dataset_field (source_key, field_key, original_name, "
            "display_order) VALUES ('contractors', ?, ?, ?)", (key, key, index))
        for index, key in enumerate(PRICE_KEYS_FOUND_IN_THE_WILD)])

    client = TestClient(create_app(databases=warehouse))
    body = client.get("/api/fields/contractors").json()
    offered = {field["field_key"] for field in body["fields"]}

    still_there = sorted(offered & set(PRICE_KEYS_FOUND_IN_THE_WILD))
    assert not still_there, (
        f"eleven rows written by the old defect are still offered: {still_there}")
    assert "company_name" in offered, "the real columns went with them"


def test_a_price_source_still_takes_the_price_path(warehouse):
    """The catalogue is asked FIRST, not INSTEAD. An unknown key must fall through."""
    conn = warehouse.engine.connect()
    try:
        assert service.dataset_schema_fields(conn, "MADAR") is None, (
            "an upper-case price key resolved as a dataset; the two key spaces "
            "were supposed to be disjoint")
    finally:
        conn.close()

    client = TestClient(create_app(databases=warehouse))
    assert client.get("/api/fields/MADAR").status_code == 200


# ---- 2 · and the answer has to reach the table ------------------------------

def test_hiding_a_dataset_column_removes_it_from_the_table(warehouse):
    before = {column["key"] for column in payload(warehouse, cap=5)["columns"]}
    assert "membership_level" in before

    arrange(warehouse, lambda conn: set_visibility(
        conn, "contractors", "membership_level", True))

    after = {column["key"] for column in payload(warehouse, cap=5)["columns"]}
    assert "membership_level" not in after, (
        "the column was hidden and the table still draws it — the arrangement "
        "saved and the screen did not change")


def test_a_hidden_dataset_column_is_moved_and_not_lost(warehouse):
    """`R-45`: hide means MOVE IT TO THE CARD, which is what this list feeds."""
    arrange(warehouse, lambda conn: set_visibility(
        conn, "contractors", "membership_level", True))

    moved = payload(warehouse, cap=5)["moved_to_details"]

    assert [column["key"] for column in moved] == ["membership_level"], (
        "a hidden column vanished instead of moving to the details")


def test_showing_it_again_moves_it_back(warehouse):
    """Reversible, because a presentation change is never destructive."""
    arrange(warehouse, lambda conn: set_visibility(
        conn, "contractors", "membership_level", True))
    arrange(warehouse, lambda conn: set_visibility(
        conn, "contractors", "membership_level", False))

    result = payload(warehouse, cap=5)

    assert "membership_level" in {c["key"] for c in result["columns"]}
    assert result["moved_to_details"] == []


def test_a_renamed_dataset_column_carries_his_label(warehouse):
    arrange(warehouse, lambda conn: set_display_name(
        conn, "contractors", "company_name", "Contractor"))

    labels = {c["key"]: c["label"] for c in payload(warehouse, cap=5)["columns"]}

    assert labels["company_name"] == "Contractor", (
        "his rename is stored and the table still prints the old heading")


def test_an_untouched_table_keeps_the_schemas_own_order(warehouse):
    """`display_order` defaults to 0 for every row, so imposing it before he has
    arranged anything would reshuffle a table nobody touched."""
    conn = warehouse.engine.connect()
    try:
        schema_order = [row["field_key"]
                        for row in service.dataset_schema_fields(
                            conn, "contractors")[1]]
    finally:
        conn.close()

    drawn = [c["key"] for c in payload(warehouse, cap=5)["columns"]]

    assert drawn[:len(schema_order)] == schema_order, (
        "the table reordered itself before the owner arranged anything")


def test_the_observed_columns_survive_an_arrangement(warehouse):
    """Ours, not the site's — they are appended after his columns and stay."""
    arrange(warehouse, lambda conn: set_visibility(
        conn, "contractors", "membership_level", True))

    drawn = [c["key"] for c in payload(warehouse, cap=5)["columns"]]

    assert any(key.startswith("observed_") or "state" in key for key in drawn), (
        "the observation columns were dropped by the presentation filter")
