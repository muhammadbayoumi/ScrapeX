"""Spec 15: field-level change events — classification rules + what ingest emits."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.changes import (
    change_summary, classify_availability, classify_price, product_field_diffs, recent_changes,
)
from scrapex.ingest import ingest_payloads
from scrapex.vocab import ChangeType
from tests.test_ingest import make_entry, make_payload, one_row


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def _types(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT change_type FROM change_event ORDER BY change_event_id")]


# ---- pure classification ----------------------------------------------------

def test_classify_price_movement():
    assert classify_price(100, 130) is ChangeType.PRICE_INCREASE
    assert classify_price(130, 100) is ChangeType.PRICE_DECREASE
    assert classify_price(100, 100) is None
    assert classify_price(None, 100) is None      # no baseline is not a change


def test_classify_price_ignores_scale_noise():
    assert classify_price(0.62, 0.620) is None


def test_classify_availability_transitions():
    assert classify_availability("in_stock", "out_of_stock") is ChangeType.UNAVAILABLE
    assert classify_availability("out_of_stock", "in_stock") is ChangeType.RETURNED
    assert classify_availability("in_stock", "in_stock") is None


def test_classify_availability_ignores_unknown():
    """A connector that briefly cannot read stock must not fake a disappearance."""
    assert classify_availability("in_stock", "unknown") is None
    assert classify_availability("unknown", "in_stock") is None


def test_product_field_diffs_detects_and_protects():
    stored = {"source_name": "Old name", "product_url": "u", "brand_raw": "B"}
    assert product_field_diffs(stored, {"product_name": "New name", "product_url": "u",
                                        "brand_raw": "B"}) == [("source_name", "Old name", "New name")]
    # an EMPTY incoming value means "not reported", never "cleared"
    assert product_field_diffs(stored, {"product_name": "", "product_url": "", "brand_raw": ""}) == []


# ---- what ingest actually emits ---------------------------------------------

def test_first_ingest_emits_new_for_product_and_variant(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    assert _types(conn) == [ChangeType.NEW.value, ChangeType.NEW.value]
    row = conn.execute("SELECT field_key, previous_value FROM change_event "
                       "ORDER BY change_event_id").fetchone()
    assert row["field_key"] == "source_product" and row["previous_value"] is None


def test_price_rise_and_fall_are_recorded(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="100.00")])])
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="130.00")],
                                               scraped_at="2026-07-17T10:00:00Z")])
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="90.00")],
                                               scraped_at="2026-07-18T10:00:00Z")])
    assert _types(conn)[-2:] == [ChangeType.PRICE_INCREASE.value, ChangeType.PRICE_DECREASE.value]
    ev = conn.execute("SELECT previous_value, new_value FROM change_event "
                      "WHERE change_type = 'price_increase'").fetchone()
    assert ev["previous_value"] == "100.0" and ev["new_value"] == "130.0"


def test_unchanged_price_emits_nothing_new(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    before = len(_types(conn))
    ingest_payloads(conn, entry, [make_payload([one_row()], scraped_at="2026-07-17T10:00:00Z")])
    assert len(_types(conn)) == before


def test_going_out_of_stock_and_returning(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(availability="in_stock")])])
    ingest_payloads(conn, entry, [make_payload(
        [one_row(availability="out_of_stock", effective_price="1,201.00")],
        scraped_at="2026-07-17T10:00:00Z")])
    ingest_payloads(conn, entry, [make_payload(
        [one_row(availability="in_stock", effective_price="1,202.00")],
        scraped_at="2026-07-18T10:00:00Z")])
    types = _types(conn)
    assert ChangeType.UNAVAILABLE.value in types and ChangeType.RETURNED.value in types


def test_rename_is_recorded_AND_applied(conn):
    """The old behaviour kept the first-seen name forever — neither history nor truth."""
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(product_name="LED 400W")])])
    ingest_payloads(conn, entry, [make_payload([one_row(product_name="LED Floodlight 400W Pro")],
                                               scraped_at="2026-07-17T10:00:00Z")])
    ev = conn.execute("SELECT * FROM change_event WHERE change_type = 'field_updated'").fetchone()
    assert ev["field_key"] == "source_name"
    assert ev["previous_value"] == "LED 400W" and ev["new_value"] == "LED Floodlight 400W Pro"
    # current state now reflects reality:
    assert conn.execute("SELECT source_name FROM source_product").fetchone()[0] \
        == "LED Floodlight 400W Pro"


def test_changes_are_linked_to_their_run_and_job(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])], job_id=None)
    ev = conn.execute("SELECT run_id FROM change_event LIMIT 1").fetchone()
    run_id = conn.execute("SELECT run_id FROM crawl_run").fetchone()[0]
    assert ev["run_id"] == run_id


# ---- reporting helpers -------------------------------------------------------

def test_change_summary_counts_by_type(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="1,300.00")],
                                               scraped_at="2026-07-17T10:00:00Z")])
    summary = change_summary(conn, "ELSEWEDYSHOP")
    assert summary[ChangeType.NEW.value] == 2
    assert summary[ChangeType.PRICE_INCREASE.value] == 1


def test_recent_changes_is_newest_first_and_bounded(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    feed = recent_changes(conn, "ELSEWEDYSHOP", limit=1)
    assert len(feed) == 1 and feed[0]["change_type"] == ChangeType.NEW.value
    assert recent_changes(conn, "ELSEWEDYSHOP", limit=10_000)  # clamped, not an error
