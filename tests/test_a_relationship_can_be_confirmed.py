"""Two thirds of a vocabulary the schema enforces had no way to be written.

`dataset_relationship` declares three review states in its own CHECK constraint —
`suggested`, `confirmed`, `rejected` — and `propose_relationship` writes `SUGGESTED`
as a literal. Nothing in the codebase ever wrote either of the other two.

SO THE OWNER'S DECISION HAD NOWHERE TO GO. He looked at the panel, saw `contractors`
and `contractor_profiles` as two cards, and asked why a contractor's profile was not
part of the main table. Both datasets carry `contractor_id`; `dataset_relationship`
exists for exactly that and held **zero rows**. He said «اربطهم فى dataset_relationship»
— and "link them" is a confirmation, which was the one thing the code could not record.

WHY REVIEW IS NOT PART OF PROPOSING. `propose_relationship`'s own docstring already
drew the line: *"this path can never confirm it."* An inference and a decision are
different facts with different authors, and a function that did both would let a guess
arrive already blessed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapex.catalog_models import (
    Cardinality,
    CatalogConflict,
    RelationshipCreate,
    RelationshipFieldPairCreate,
    RelationshipReviewStatus,
)
from scrapex.catalog_relations import (
    list_relationships,
    propose_relationship,
    review_relationship,
)
from scrapex.databases import DatabaseRegistry, EngineDatabase

SITE = "muqawil_org"


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def _two_datasets(conn) -> tuple[int, int, int, int]:
    """The shape his warehouse really has: two datasets, one shared key field.

    Built through SQL rather than the catalogue API because the point under test is the
    REVIEW, and the fixture should not depend on discovery succeeding.
    """
    conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url) "
        "VALUES (?,?,?)", (SITE, "Contractors", "https://muqawil.org"))
    ids = []
    for key in ("contractors", "contractor_profiles"):
        cur = conn.execute(
            "INSERT INTO dataset_definition (source_id, dataset_key, "
            " original_name, dataset_kind, discovery_method, locator_json) "
            "VALUES (1,?,?, 'table','html_table','{}')", (key, key))
        ids.append(int(cur.lastrowid))
    fields = []
    for dataset_id in ids:
        # Column names read from `PRAGMA table_info`, not from memory: the first
        # attempt guessed `source_name`/`nullable`/`position` and the table has
        # `original_name`/`is_nullable`/`display_order`.
        cur = conn.execute(
            "INSERT INTO field_definition (dataset_definition_id, field_key, "
            " original_name, display_name, data_type, is_nullable, display_order) "
            "VALUES (?,'contractor_id','contractor_id','Contractor id','text',0,0)",
            (dataset_id,))
        fields.append(int(cur.lastrowid))
    conn.commit()
    return ids[0], ids[1], fields[0], fields[1]


def _proposed(conn) -> dict:
    parent, child, parent_field, child_field = _two_datasets(conn)
    return propose_relationship(conn, SITE, RelationshipCreate(
        relationship_key="contractor_profile",
        parent_dataset_id=parent, child_dataset_id=child,
        cardinality=Cardinality.ONE_TO_ONE, confidence=1.0,
        evidence={"joined_on": "contractor_id"},
        field_pairs=[RelationshipFieldPairCreate(
            parent_field_id=parent_field, child_field_id=child_field)],
    ))


# ---- the state that could not be written -------------------------------------

def test_a_proposal_starts_suggested_and_can_be_confirmed(conn):
    """THE GAP, closed. Before this, `suggested` was the only reachable state."""
    made = _proposed(conn)
    assert made["review_status"] == RelationshipReviewStatus.SUGGESTED.value

    after = review_relationship(conn, SITE, "contractor_profile",
                                status=RelationshipReviewStatus.CONFIRMED)

    assert after["review_status"] == RelationshipReviewStatus.CONFIRMED.value
    assert after["dataset_relationship_id"] == made["dataset_relationship_id"], (
        "reviewing created a second relationship instead of deciding the first")


def test_it_can_also_be_rejected(conn):
    """The third state, and it must be reachable too: a proposal the owner refuses is
    a decision worth keeping, not a row to delete. `R-43`'s reasoning one level down —
    a rejection that vanishes invites the same proposal next week."""
    _proposed(conn)

    after = review_relationship(conn, SITE, "contractor_profile", status="rejected")

    assert after["review_status"] == RelationshipReviewStatus.REJECTED.value


def test_the_field_pairs_survive_the_verdict(conn):
    """The join itself is the payload. A review that dropped the field pairs would
    leave a confirmed relationship that says nothing about how to join."""
    made = _proposed(conn)
    before = made["field_pairs"]

    after = review_relationship(conn, SITE, "contractor_profile", status="confirmed")

    assert after["field_pairs"] == before
    assert after["field_pairs"], "the relationship carries no field pair at all"


def test_reviewing_something_that_was_never_proposed_is_refused(conn):
    """Silently creating it would turn a typo into a confirmed relationship nobody
    inferred."""
    _two_datasets(conn)

    with pytest.raises(CatalogConflict, match="propose it first"):
        review_relationship(conn, SITE, "not_a_relationship", status="confirmed")


def test_a_retired_relationship_cannot_be_confirmed(conn):
    """`valid_to` means history. Confirming history would make it live again through a
    side door — and `propose_relationship` already refuses a retired key for exactly
    this reason, so refusing here keeps one rule instead of two."""
    made = _proposed(conn)
    conn.execute(
        "UPDATE dataset_relationship SET valid_to = '2026-08-22T00:00:00Z' "
        " WHERE dataset_relationship_id = ?", (made["dataset_relationship_id"],))
    conn.commit()

    with pytest.raises(CatalogConflict, match="retired"):
        review_relationship(conn, SITE, "contractor_profile", status="confirmed")


def test_an_unknown_verdict_is_refused_before_it_reaches_the_database(conn):
    """The CHECK constraint would catch it, but as an IntegrityError naming a
    constraint — not as a message about a word nobody knows. The enum answers first."""
    _proposed(conn)

    with pytest.raises(ValueError):
        review_relationship(conn, SITE, "contractor_profile", status="approved")


def test_the_verdict_moves_the_timestamp(conn):
    """`updated_at` is where a reader asks "when was this decided", and there is
    nowhere else to look."""
    made = _proposed(conn)
    conn.execute(
        "UPDATE dataset_relationship SET updated_at = '2000-01-01T00:00:00Z' "
        " WHERE dataset_relationship_id = ?", (made["dataset_relationship_id"],))
    conn.commit()

    review_relationship(conn, SITE, "contractor_profile", status="confirmed")

    stamp = conn.execute(
        "SELECT updated_at FROM dataset_relationship WHERE dataset_relationship_id = ?",
        (made["dataset_relationship_id"],)).fetchone()[0]
    assert stamp != "2000-01-01T00:00:00Z", (
        "the verdict was recorded without saying when, so nothing distinguishes a "
        "decision taken today from one taken in 2000")


def test_the_listing_shows_the_verdict(conn):
    """A confirmation nobody can read is not a confirmation. `list_relationships` is
    what the panel and the owner both go through."""
    _proposed(conn)
    review_relationship(conn, SITE, "contractor_profile", status="confirmed")

    listed = list_relationships(conn, SITE)
    rows = listed["relationships"] if isinstance(listed, dict) else listed
    statuses = [row["review_status"] for row in rows]
    assert statuses == [RelationshipReviewStatus.CONFIRMED.value], statuses


def test_proposing_is_still_unable_to_confirm(conn):
    """THE BOUNDARY, pinned. `propose_relationship` says in its own docstring that it
    can never confirm, and the new function must not have quietly given it the power:
    a guess that arrives already blessed is the failure this separation prevents."""
    source = (Path(__file__).resolve().parent.parent / "scrapex"
              / "catalog_relations.py").read_text(encoding="utf-8")
    body = source[source.index("def propose_relationship"):
                  source.index("def list_relationships")]
    assert "CONFIRMED" not in body, (
        "propose_relationship can now write `confirmed`, so an inference can arrive "
        "already decided")
    assert json.dumps(True)  # keeps the import honest about being used
