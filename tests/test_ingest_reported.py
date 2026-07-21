"""Reported rows: the source's dated claims, kept apart from what WE watched.

A reported row says "the publisher states this price held on that date". It is
real data worth keeping — ten years of it, in GPP's case — and it is not an
observation of ours. Everything here proves the separation holds end to end:
the date it lands under, the change stream it must never enter, the derived
timeline it must never rewrite, and the absence bookkeeping it must not touch.

The bug this file exists to prevent: before the pass-through, the ingest
adapter dropped provenance and as_of_date, so every history anchor landed as a
TODAY observation — three "months ago" prices stamped with the crawl date,
colliding with the current price, confirming or contradicting it at random.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex import pricehistory
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import ScrapedTable
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope


def _entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="GPP_ENERGY", source_name="أسعار الطاقة العالمية",
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        cadence="weekly", authority="aggregator", currency="USD",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE,
                             scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["*"])],
    ))


def _payload(rows_kv: list[dict]):
    builder = RowBuilder(COMMODITY_PRICE)
    rows = []
    for kv in rows_kv:
        base = dict(material_key="DIESEL", region="EG", currency="EGP",
                    unit="liter", vat_included="1", price_basis="original")
        base.update(kv)
        rows.append(builder.row(**base))
    table = ScrapedTable("GPP_ENERGY", ExtractKind.COMMODITY_PRICE,
                         "https://www.globalpetrolprices.com",
                         builder.header, rows)
    return table.to_payload()


@pytest.fixture()
def conn():
    c: sqlite3.Connection = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def _observations(conn):
    return conn.execute(
        "SELECT business_date, effective_price, provenance FROM price_observation "
        "ORDER BY price_observation_id").fetchall()


def _changes(conn):
    return conn.execute(
        "SELECT change_type, previous_value, new_value FROM change_event "
        "WHERE field_key = 'effective_price'").fetchall()


CURRENT = dict(effective_price="20.50")
ANCHOR_1M = dict(effective_price="20.50", provenance="reported", as_of_date="2026-06-21")
ANCHOR_1Y = dict(effective_price="15.50", provenance="reported", as_of_date="2025-07-21")


def test_a_reported_row_lands_under_the_date_the_source_names(conn):
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M, ANCHOR_1Y])])

    rows = _observations(conn)
    assert [(r["provenance"], r["business_date"]) for r in rows] == [
        ("observed", rows[0]["business_date"]),   # ours, dated by the crawl
        ("reported", "2026-06-21"),
        ("reported", "2025-07-21"),
    ]
    # And the crawl date is NOT the anchor's date — the whole point.
    assert rows[0]["business_date"] not in ("2026-06-21", "2025-07-21")


def test_a_backfilled_anchor_never_fires_a_change_event(conn):
    """15.50-a-year-ago arriving after today's 20.50 is history, not a crash.
    Before the split it produced a 'price_decrease' dated this morning."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1Y])])

    assert _changes(conn) == []


def test_next_weeks_price_is_compared_to_our_last_observation_not_the_anchor(conn):
    """The previous-read orders by insertion; the freshest row after week 1 is
    the year-ago anchor at 15.50. Comparing 21.00 against IT would report a
    +35% jump when the real move is 20.50 -> 21.00."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1Y])])
    ingest_payloads(conn, _entry(), [_payload([dict(effective_price="21.00")])])

    moves = _changes(conn)
    assert len(moves) == 1
    # change_event stores values as text; the numbers are what matters.
    assert (float(moves[0]["previous_value"]), float(moves[0]["new_value"])) == (20.5, 21.0)


def test_reported_rows_do_not_open_or_close_derived_periods(conn):
    """The derived timeline records what ScrapeX watched (owner rule: real
    changes only). A publisher's anchors must not write it."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M, ANCHOR_1Y])])
    offer_id = conn.execute("SELECT offer_id FROM source_offer").fetchone()[0]
    pricehistory.rebuild_offer(conn, offer_id)

    periods = conn.execute(
        "SELECT COUNT(*) FROM price_period WHERE offer_id = ?", (offer_id,)).fetchone()[0]
    assert periods == 1, "anchors opened periods — publisher dating wrote our history"


def test_a_reported_row_without_a_date_is_rejected_not_guessed(conn):
    result = ingest_payloads(conn, _entry(), [_payload([
        dict(effective_price="19.00", provenance="reported"),   # no as_of_date
    ])])

    assert result.rejected_out_of_scope == 1
    assert _observations(conn) == []


def test_recrawling_the_same_anchor_is_idempotent(conn):
    """Week 2 re-reads the same country page; the same (date, price) anchor must
    not duplicate. The dedupe key includes business_date, so it cannot."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M])])
    result = ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M])])

    rows = _observations(conn)
    assert len([r for r in rows if r["provenance"] == "reported"]) == 1
    assert result.duplicates >= 1


def test_two_anchors_same_price_different_dates_both_persist(conn):
    """20.50 a month ago and 20.50 today-per-the-source are two claims, not one.
    A dedupe that ignored the date would silently drop half the history."""
    ingest_payloads(conn, _entry(), [_payload([
        ANCHOR_1M, dict(effective_price="20.50", provenance="reported",
                        as_of_date="2026-07-13"),
    ])])

    dates = [r["business_date"] for r in _observations(conn)]
    assert sorted(dates) == ["2026-06-21", "2026-07-13"]


def test_an_anchor_alone_does_not_mark_the_offer_as_seen(conn):
    """`seen` drives absence bookkeeping: it asserts the offer is on the site
    TODAY. A ten-year-old anchor asserts no such thing."""
    result = ingest_payloads(conn, _entry(), [_payload([ANCHOR_1Y])])

    assert result.seen == {}
