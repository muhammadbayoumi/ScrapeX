"""Each answer the Data page reads is one function, and its route is that function.

THE LIGHT FILE STORES THESE BODIES (#1199). A reader with no engine opens a record
card, an activity tree and the dataset list from a copy the engine wrote, so the copy
must be the route's own answer rather than a second build of it. Three of them lived
inside `create_app` closures, where a second caller could only copy them:

    GET /api/offer/{source}/{id}     ->  reports.offer_card
    GET /api/taxonomy/{dataset}      ->  taxonomy.dataset_taxonomy
    the datasets the listing shows   ->  extract_service.listed_datasets / dataset_folds

Each test holds the route's bytes to the function's, as FastAPI serialises a route
with no response model, which is how the light file will write them.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

pytest.importorskip("fastapi")
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex import features, taxonomy
from scrapex.config import MANIFEST_FILE
from scrapex.extract import service
from scrapex.features import FeatureKey, FeatureState
from scrapex.ingest import ingest_payloads
from scrapex.reports import offer_card
from scrapex.webui.app import create_app
from tests.test_an_activity_filter_reads_what_is_stored import (
    _dataset,
    _hold,
    _record,
    _tree,
)
from tests.test_ingest import make_entry, make_payload, one_row

SOURCE = "ELSEWEDYSHOP"


def _as_served(payload) -> bytes:
    """A route with no response model: `jsonable_encoder`, then `JSONResponse`."""
    return JSONResponse(content=jsonable_encoder(payload)).body


@pytest.fixture()
def db_path(tmp_path):
    """One offer, ingested twice at two prices, so its story has a change in it."""
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload(
        [one_row()], scraped_at="2026-07-16T10:00:00Z")])
    ingest_payloads(conn, make_entry(), [make_payload(
        [one_row(price="1,100.00", price_before="1,100.00")],
        scraped_at="2026-07-20T10:00:00Z")])
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path):
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


def _offer_id(db_path) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT offer_id FROM source_offer").fetchone()[0]


# ---- the record card ---------------------------------------------------------

def test_the_offer_route_serves_the_card_byte_for_byte(client, db_path):
    """If this fails, the card a reader opens offline is not the card the engine shows."""
    offer_id = _offer_id(db_path)
    conn = dbmod.connect(db_path)
    try:
        card = offer_card(conn, SOURCE, offer_id)
    finally:
        conn.close()

    response = client.get(f"/api/offer/{SOURCE}/{offer_id}")

    assert response.status_code == 200
    assert response.content == _as_served(card)
    assert list(card) == ["offer", "periods", "observations", "changes", "details"]
    # NOT VACUOUS: two prices, so the story has a history and a change to compare.
    assert len(card["observations"]) == 2 and card["changes"], card


def test_another_sources_offer_is_no_card_and_a_404(client, db_path):
    """The ownership rule moved with the card: it never confirms another source's id."""
    offer_id = _offer_id(db_path)
    conn = dbmod.connect(db_path)
    try:
        assert offer_card(conn, "GPP_ENERGY", offer_id) is None
        assert offer_card(conn, SOURCE, offer_id + 1000) is None
    finally:
        conn.close()

    assert client.get(f"/api/offer/GPP_ENERGY/{offer_id}").status_code == 404
    assert client.get(f"/api/offer/{SOURCE}/{offer_id + 1000}").status_code == 404


# ---- the activity tree -------------------------------------------------------

@pytest.fixture()
def directory(tmp_path):
    """muqawil's profile dataset, with the interests tree held by one record."""
    path = tmp_path / "directory.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    definition, version = _dataset(conn)
    nodes = _tree(conn)
    record = _record(conn, definition, version, "6001")
    _hold(conn, record, nodes["leaf"])
    conn.close()
    return path


def test_the_taxonomy_route_serves_the_function_byte_for_byte(directory, tmp_path):
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    client = TestClient(create_app(directory, manifest_path=manifest))
    conn = dbmod.connect(directory)
    try:
        answer = taxonomy.dataset_taxonomy(conn, "contractor_profiles")
        tree = taxonomy.group_tree(conn, "interests")
    finally:
        conn.close()

    response = client.get("/api/taxonomy/contractor_profiles")

    assert response.status_code == 200
    assert response.content == _as_served(answer)
    # Only the group declared as a tree, and it is the stored one.
    assert answer == {"dataset_key": "contractor_profiles", "groups": [tree]}
    assert tree["scheme"] is not None


def test_a_declared_tree_that_stores_nothing_is_left_out(tmp_path):
    """`interests` is declared as a tree, and an empty warehouse holds no scheme for it.
    A group with no scheme would draw an empty filter control."""
    conn = dbmod.connect(tmp_path / "empty.db")
    dbmod.migrate(conn)
    try:
        assert taxonomy.dataset_taxonomy(conn, "contractor_profiles") == {
            "dataset_key": "contractor_profiles", "groups": []}
    finally:
        conn.close()


def test_a_dataset_with_no_vocabulary_answers_no_groups(directory):
    conn = dbmod.connect(directory)
    try:
        assert taxonomy.dataset_taxonomy(conn, "contractors") == {
            "dataset_key": "contractors", "groups": []}
    finally:
        conn.close()


# ---- the dataset list and its folds ------------------------------------------

def _two_datasets_and_a_link(conn, *, status="confirmed", cardinality="one_to_one"):
    definition, _version = _dataset(conn)  # contractor_profiles, on muqawil_org
    source = conn.execute(
        "SELECT source_id FROM dataset_definition WHERE dataset_definition_id = ?",
        (definition,)).fetchone()[0]
    parent = conn.execute(
        "INSERT INTO dataset_definition "
        "  (source_id, dataset_key, original_name, dataset_kind, discovery_method) "
        "VALUES (?, 'contractors', 'Contractors', 'table', 'repeating_dom') "
        "RETURNING dataset_definition_id", (source,)).fetchone()[0]
    conn.execute(
        "INSERT INTO dataset_relationship (source_id, relationship_key, "
        "  parent_dataset_id, child_dataset_id, cardinality, review_status) "
        "VALUES (?, 'profile_of', ?, ?, ?, ?)",
        (source, parent, definition, cardinality, status))
    conn.commit()


def test_the_list_names_every_live_dataset_with_its_site(tmp_path):
    conn = dbmod.connect(tmp_path / "list.db")
    dbmod.migrate(conn)
    try:
        _two_datasets_and_a_link(conn)
        listed = service.listed_datasets(conn)
    finally:
        conn.close()

    assert sorted((row["site_key"], row["dataset_key"]) for row in listed) == [
        ("muqawil_org", "contractor_profiles"), ("muqawil_org", "contractors")]


def test_the_list_is_empty_when_the_catalogue_is_switched_off(tmp_path, monkeypatch):
    """The flag gates the advertisement, and this list is it."""
    monkeypatch.setattr(features, "_FEATURES", tuple(
        FeatureState(one.key, False, one.stage, one.detail)
        if one.key == FeatureKey.GENERIC_DATASET_CATALOG else one
        for one in features._FEATURES))
    assert features.is_enabled(FeatureKey.GENERIC_DATASET_CATALOG) is False
    conn = dbmod.connect(tmp_path / "off.db")
    dbmod.migrate(conn)
    try:
        _two_datasets_and_a_link(conn)
        assert service.listed_datasets(conn) == []
    finally:
        conn.close()


@pytest.mark.parametrize(("status", "cardinality", "folds"), [
    ("confirmed", "one_to_one", {"contractor_profiles": "contractors"}),
    ("suggested", "one_to_one", {}),
    ("confirmed", "one_to_many", {}),
])
def test_only_a_confirmed_one_to_one_link_folds_a_card(tmp_path, status, cardinality, folds):
    conn = dbmod.connect(tmp_path / "folds.db")
    dbmod.migrate(conn)
    try:
        _two_datasets_and_a_link(conn, status=status, cardinality=cardinality)
        keys = [row["dataset_key"] for row in service.listed_datasets(conn)]
        assert service.dataset_folds(conn, keys) == folds
    finally:
        conn.close()


def test_a_child_that_is_itself_a_parent_keeps_its_card(tmp_path):
    conn = dbmod.connect(tmp_path / "deep.db")
    dbmod.migrate(conn)
    try:
        _two_datasets_and_a_link(conn)
        # contractors is now a child as well as a parent.
        source = conn.execute("SELECT source_id FROM source_site").fetchone()[0]
        top = conn.execute(
            "INSERT INTO dataset_definition "
            "  (source_id, dataset_key, original_name, dataset_kind, discovery_method) "
            "VALUES (?, 'firms', 'Firms', 'table', 'repeating_dom') "
            "RETURNING dataset_definition_id", (source,)).fetchone()[0]
        middle = conn.execute(
            "SELECT dataset_definition_id FROM dataset_definition "
            "WHERE dataset_key = 'contractors'").fetchone()[0]
        conn.execute(
            "INSERT INTO dataset_relationship (source_id, relationship_key, "
            "  parent_dataset_id, child_dataset_id, cardinality, review_status) "
            "VALUES (?, 'listing_of', ?, ?, 'one_to_one', 'confirmed')",
            (source, top, middle))
        conn.commit()
        keys = [row["dataset_key"] for row in service.listed_datasets(conn)]
        folds = service.dataset_folds(conn, keys)
    finally:
        conn.close()

    assert folds == {"contractor_profiles": "contractors"}


def test_a_link_to_a_dataset_that_is_not_listed_folds_nothing(tmp_path):
    conn = dbmod.connect(tmp_path / "unlisted.db")
    dbmod.migrate(conn)
    try:
        _two_datasets_and_a_link(conn)
        assert service.dataset_folds(conn, ["contractor_profiles"]) == {}
    finally:
        conn.close()
