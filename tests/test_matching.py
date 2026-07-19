"""Spec 14: identity, suggestion precedence, the human gate, and undo."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.changes import aliases_of
from scrapex.ingest import ingest_payloads
from scrapex.matching import (
    ConflictError, Decision, decide, pending_reviews, suggest_for_source, undo_decision,
)
from scrapex.normalize import name_similarity, normalize_name
from scrapex.vocab import CurationStatus, ReviewStatus
from tests.test_ingest import make_entry, make_payload, one_row


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def _material(conn, name_en=None, name_ar=None, gtin=None, mpn=None) -> int:
    cur = conn.execute(
        "INSERT INTO material (material_name_en, material_name_ar, gtin, manufacturer_part_number) "
        "VALUES (?,?,?,?)", (name_en, name_ar, gtin, mpn))
    return int(cur.lastrowid)


def _seed_product(conn, **over) -> None:
    ingest_payloads(conn, make_entry(), [make_payload([one_row(**over)])])


# ---- name normalization (the one shared implementation) ---------------------

def test_normalize_name_folds_arabic_digits_and_punctuation():
    assert normalize_name("Cement  50KG!!") == "cement 50kg"
    assert normalize_name("أسمنت ٥٠ كجم") == "أسمنت 50 كجم"


def test_name_similarity_is_word_order_insensitive():
    assert name_similarity("white cement 50kg", "cement 50kg white") == 1.0
    assert name_similarity("white cement", "steel rebar") == 0.0
    assert name_similarity("", "anything") == 0.0


# ---- suggestion precedence ---------------------------------------------------

def test_gtin_beats_name_and_never_auto_approves(conn):
    _seed_product(conn, external_sku="6281100000012", product_name="LED 400W")
    _material(conn, name_en="Something else entirely", gtin="6281100000012")
    assert suggest_for_source(conn, "ELSEWEDYSHOP") == 1

    queue = pending_reviews(conn)
    assert len(queue) == 1
    assert queue[0]["match_method"] == "gtin" and queue[0]["confidence"] == 0.99
    # the human gate: still PENDING despite 0.99
    status = conn.execute("SELECT review_status FROM source_product_match").fetchone()[0]
    assert status == ReviewStatus.PENDING.value


def test_name_similarity_suggestion(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    item = pending_reviews(conn)[0]
    assert item["match_method"] == "name_fuzzy" and item["confidence"] >= 0.55


def test_weak_names_are_not_suggested_at_all(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Portland Cement 50kg")
    assert suggest_for_source(conn, "ELSEWEDYSHOP") == 0
    assert pending_reviews(conn) == []


def test_no_materials_means_no_suggestions(conn):
    _seed_product(conn)
    assert suggest_for_source(conn, "ELSEWEDYSHOP") == 0


def test_review_item_lists_matched_and_conflicting_fields(conn):
    _seed_product(conn, product_name="LED Floodlight 400W", external_sku="ZZZ-1")
    _material(conn, name_en="LED Floodlight 400W", gtin="6281100000012")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    item = pending_reviews(conn)[0]
    assert "name" in item["matched_fields"] and "sku" in item["conflicting_fields"]


# ---- the owner's decisions ---------------------------------------------------

def test_approve_links_and_selects_the_product(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    material_id = _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]

    result = decide(conn, match_id, Decision.APPROVE)
    assert result["status"] == ReviewStatus.APPROVED.value
    assert result["material_id"] == material_id
    assert conn.execute("SELECT curation_status FROM source_product").fetchone()[0] \
        == CurationStatus.SELECTED.value
    assert pending_reviews(conn) == []      # left the queue


def test_new_creates_its_own_material(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]

    before = conn.execute("SELECT COUNT(*) FROM material").fetchone()[0]
    result = decide(conn, match_id, Decision.NEW)
    assert conn.execute("SELECT COUNT(*) FROM material").fetchone()[0] == before + 1
    assert result["status"] == ReviewStatus.APPROVED.value


def test_separate_is_remembered_so_the_pair_never_returns(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]

    decide(conn, match_id, Decision.SEPARATE)
    assert pending_reviews(conn) == []
    assert suggest_for_source(conn, "ELSEWEDYSHOP") == 0   # not re-offered


def test_gtin_outranks_a_perfect_name_match(conn):
    """Regression (HIGH): ranking on confidence alone let a name_fuzzy 1.0 beat an
    exact GTIN 0.99 — an identifier is categorically stronger than a word overlap."""
    _seed_product(conn, product_name="Steel Rebar 12mm", external_sku="6281100000012")
    _material(conn, name_en="Totally Different Thing", gtin="6281100000012")
    _material(conn, name_en="Steel Rebar 12mm")          # name_similarity == 1.0
    suggest_for_source(conn, "ELSEWEDYSHOP")
    assert pending_reviews(conn)[0]["match_method"] == "gtin"


def test_separate_blocks_only_that_pair_not_the_product(conn):
    """Regression (HIGH): an ignored row used to retire the whole product, exiling
    it from matching forever even against a completely different material."""
    _seed_product(conn, product_name="LED Floodlight 400W")
    wrong = _material(conn, name_en="LED Floodlight 400W Wrong")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    decide(conn, pending_reviews(conn)[0]["source_product_match_id"], Decision.SEPARATE)

    right = _material(conn, name_en="Floodlight LED 400W")   # a better, different one
    assert suggest_for_source(conn, "ELSEWEDYSHOP") == 1
    queued = pending_reviews(conn)
    assert len(queued) == 1 and queued[0]["material_id"] == right
    assert queued[0]["material_id"] != wrong                 # the rejected pair stays rejected


def test_deciding_twice_is_a_conflict_not_a_duplicate(conn):
    """Regression: a double-clicked NEW minted a second material every time."""
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]

    decide(conn, match_id, Decision.NEW)
    before = conn.execute("SELECT COUNT(*) FROM material").fetchone()[0]
    with pytest.raises(ConflictError):
        decide(conn, match_id, Decision.NEW)
    assert conn.execute("SELECT COUNT(*) FROM material").fetchone()[0] == before


def test_approving_a_retired_match_is_a_conflict(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]
    decide(conn, match_id, Decision.APPROVE)
    undo_decision(conn, match_id)
    with pytest.raises(ConflictError):
        decide(conn, match_id, Decision.APPROVE)


def test_later_leaves_it_queued(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]
    decide(conn, match_id, Decision.LATER)
    assert len(pending_reviews(conn)) == 1


def test_unknown_match_or_decision_fails_loud(conn):
    with pytest.raises(KeyError):
        decide(conn, 9999, Decision.APPROVE)
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]
    with pytest.raises(ValueError):
        decide(conn, match_id, "obliterate")


# ---- undo preserves everything ----------------------------------------------

def test_undo_retires_the_link_and_keeps_price_history(conn):
    _seed_product(conn, product_name="LED Floodlight 400W")
    _material(conn, name_en="Floodlight LED 400W")
    suggest_for_source(conn, "ELSEWEDYSHOP")
    match_id = pending_reviews(conn)[0]["source_product_match_id"]
    decide(conn, match_id, Decision.APPROVE)
    prices_before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]

    assert undo_decision(conn, match_id) is True
    assert undo_decision(conn, match_id) is False        # already retired
    # the match row still EXISTS (audit trail), just retired
    row = conn.execute("SELECT review_status, valid_to FROM source_product_match").fetchone()
    assert row["review_status"] == ReviewStatus.APPROVED.value and row["valid_to"] is not None
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == prices_before


# ---- identity aliases --------------------------------------------------------

def test_a_reslugged_url_becomes_an_alias(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(product_url="https://s.com/p/old")])])
    ingest_payloads(conn, entry, [make_payload([one_row(product_url="https://s.com/p/new")],
                                               scraped_at="2026-07-17T10:00:00Z")])
    pid = conn.execute("SELECT source_product_id FROM source_product").fetchone()[0]
    aliases = aliases_of(conn, pid)
    assert [(a["alias_type"], a["alias_value"]) for a in aliases] \
        == [("product_url", "https://s.com/p/old")]
    assert conn.execute("SELECT product_url FROM source_product").fetchone()[0] \
        == "https://s.com/p/new"


def test_a_reissued_sku_becomes_an_alias(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(external_sku="OLD-1")])])
    ingest_payloads(conn, entry, [make_payload([one_row(external_sku="NEW-1")],
                                               scraped_at="2026-07-17T10:00:00Z")])
    pid = conn.execute("SELECT source_product_id FROM source_product").fetchone()[0]
    assert ("external_sku", "OLD-1") in [(a["alias_type"], a["alias_value"])
                                         for a in aliases_of(conn, pid)]
