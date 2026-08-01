"""SIKAEGSHOP publishes a remaining-stock count. It must reach the warehouse.

The connector read that number twice and wrote it down nowhere a query can find
it: `_availability` reduced it to the word `in_stock`, and `enrichment_rows`
filed it in the attribute bag. The PRICE row — the one column a reader can
filter, chart and compare against another shop — was never given it. Measured on
the live warehouse 2026-07-30: **0 of 252** SIKAEGSHOP observations and **0 of
87** offer_state rows carried a count.

The fixture and the census behind it are
`fixtures/live/sikaegshop_stock_counts_2026-07-30.{json,CAPTURE.md}`: all 87
live products publish an integer count, and **16 of them publish `0` while
`is_active` is true**. Those 16 are why the rule here is an explicit
`is not None` and never truthiness — a published 0 is the shop saying "none
left", and a count nobody published must stay NULL rather than default to a 0
that would read as sold out.

WHY EVERY WAREHOUSE TEST BELOW CRAWLS TWICE
-------------------------------------------
A single ingest into an empty database cannot fail. The first observation of an
offer is always appended — there is no open period to compare against — so the
count lands whatever the append gate does, and a test that stops there is green
while the value is being dropped on every crawl after the first.

The real question is the SECOND crawl: a shop whose price has not moved. That is
the path `_still_the_same_price` guards, and the path every one of those 252
observations actually took. So each test here ingests twice and asserts against
the row written by the second.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.connectors.custom_json import CustomJsonConnector, _availability
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import PRODUCT_PRICES, RowView

from tests.test_customjson import _StubFetcher, list_page, make_entry

LIVE = Path(__file__).parent / "fixtures" / "live"
CAPTURE = json.loads(
    (LIVE / "sikaegshop_stock_counts_2026-07-30.json").read_text(encoding="utf-8"))
PRODUCTS = {str(p["product_id"]): p for p in CAPTURE["data"]}

COUNTED = PRODUCTS["252"]      # stock_quantity 198, price 10
ZERO = PRODUCTS["213"]         # stock_quantity 0,   price 2280, is_active true
THOUSANDS = PRODUCTS["288"]    # stock_quantity 4000, price 650


def silent(product: dict) -> dict:
    """The same product, from a shop that publishes no count at all.

    The key is REMOVED, not nulled — that is the shape of a sibling shop in this
    family (and of sika itself before the count existed), and it is the only
    input for which an empty cell is the correct answer.
    """
    return {k: v for k, v in product.items() if k != "stock_quantity"}


def crawl_rows(*products):
    """One prices crawl over exactly these product records."""
    entry = make_entry()
    table = next(iter(CustomJsonConnector(
        _StubFetcher(payloads=list_page(*products))).fetch(entry)))
    return table, RowView(PRODUCT_PRICES, table.header)


def cell(products, pid: str, column: str = "stock_quantity") -> str:
    table, view = crawl_rows(*products)
    row = next(r for r in table.rows
               if view.get(r, "external_product_id") == pid)
    return view.get(row, column)


# ---- the connector: what the shop said, in the column it belongs in ----------

def test_the_published_count_rides_the_price_row():
    """198 and 4000 are what the API states for these two products today."""
    assert cell([COUNTED, THOUSANDS], "252") == "198"
    assert cell([COUNTED, THOUSANDS], "288") == "4000"


def test_a_published_zero_is_recorded_as_zero_not_dropped():
    """16 of 87 live products publish 0 while `is_active` is true. That is the
    shop saying "none left" — the most decision-changing thing it says about a
    count. A falsy guard would silently discard exactly those 16."""
    assert cell([ZERO], "213") == "0"
    assert _availability(ZERO) == "out_of_stock"     # and the word agrees


def test_a_count_the_shop_never_published_stays_empty():
    """The inverse error, and the worse one: a defaulted 0 would state "sold
    out" about a product the shop never discussed. Absent stays absent."""
    assert cell([silent(COUNTED)], "252") == ""
    assert cell([{**COUNTED, "stock_quantity": None}], "252") == ""


def test_a_stock_flag_is_not_a_count():
    """`isinstance(True, int)` is True in Python, and this family's sibling keys
    are flags. `stock: true` must not be written down as "1 item left"."""
    assert cell([{**silent(COUNTED), "stock": True}], "252") == ""


# ---- the round trip: row -> payload -> ingest -> warehouse -------------------

def _ingest(conn, entry, *products):
    """One crawl of these records, all the way into the warehouse."""
    table = next(iter(CustomJsonConnector(
        _StubFetcher(payloads=list_page(*products))).fetch(entry)))
    payload = table.to_payload()
    # The payload is the wire format between crawl and ingest; assert the count
    # is still on it here, so a failure downstream cannot be blamed on transport.
    view = RowView(PRODUCT_PRICES, payload.header)
    carried = {view.get(r, "external_product_id"): view.get(r, "stock_quantity")
               for r in payload.rows}
    return ingest_payloads(conn, entry, [payload]), carried


def _stored(conn, pid: str) -> list[sqlite3.Row]:
    """Every observation for one product, oldest first."""
    return conn.execute(
        "SELECT po.price_observation_id, po.price, po.availability, "
        "       po.stock_quantity "
        "FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.external_product_id = ? "
        "ORDER BY po.price_observation_id", (pid,)).fetchall()


def _state(conn, pid: str) -> sqlite3.Row:
    return conn.execute(
        "SELECT os.availability, os.stock_quantity FROM offer_state os "
        "JOIN source_offer so ON so.offer_id = os.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.external_product_id = ?", (pid,)).fetchone()


@pytest.fixture()
def conn():
    c = dbmod.connect(":memory:")
    c.row_factory = sqlite3.Row
    dbmod.migrate(c)
    try:
        yield c
    finally:
        c.close()


def test_a_count_that_arrives_on_a_later_crawl_reaches_the_warehouse(conn):
    """THE regression. Crawl once from a shop publishing no count, then again
    once it publishes 198 — at a price that has not moved.

    This is the shape of every SIKAEGSHOP offer in the live warehouse: already
    present, priced the same as yesterday, and the count arriving for the first
    time. A single ingest into an empty database would report `observations=1`
    with 198 on it and prove nothing about this path.
    """
    entry = make_entry()

    first, carried = _ingest(conn, entry, silent(COUNTED))
    assert not first.errors
    assert carried["252"] == "", "a shop that published no count must send none"
    assert _stored(conn, "252")[0]["stock_quantity"] is None, (
        "no count was published, so NULL — never a defaulted 0")

    second, carried = _ingest(conn, entry, COUNTED)
    assert not second.errors
    assert carried["252"] == "198", "the count must be on the payload"

    rows = _stored(conn, "252")
    assert len(rows) == 2, (
        f"the second crawl appended no observation ({second.confirmed} confirmed, "
        f"{second.observations} appended) — the price had not moved, so the "
        f"append gate treated a NEW stock figure as nothing to record")
    assert rows[-1]["stock_quantity"] == 198
    assert rows[-1]["price"] == 10.0, "the price itself did not move"
    assert _state(conn, "252")["stock_quantity"] == 198


def test_a_zero_that_arrives_on_a_later_crawl_reaches_the_warehouse(conn):
    """The same path for the value most easily lost. `0` must survive both the
    connector's cell and the ingest gate's `is not None` test, and land as 0 —
    not as NULL, and not as "no change to record"."""
    entry = make_entry()

    _ingest(conn, entry, silent(ZERO))
    assert _stored(conn, "213")[0]["stock_quantity"] is None

    second, carried = _ingest(conn, entry, ZERO)
    assert carried["213"] == "0"

    rows = _stored(conn, "213")
    assert len(rows) == 2, "a published 0 is a fact, and it was not appended"
    assert rows[-1]["stock_quantity"] == 0
    assert rows[-1]["availability"] == "out_of_stock"
    assert _state(conn, "213")["stock_quantity"] == 0


def test_a_count_that_moves_between_crawls_records_both_figures(conn):
    """Stock is the fast-moving number on this shop. Two crawls at one price
    must leave a readable history of the count, not one row overwritten."""
    entry = make_entry()

    _ingest(conn, entry, COUNTED)
    _ingest(conn, entry, {**COUNTED, "stock_quantity": 7})

    rows = _stored(conn, "252")
    assert [r["stock_quantity"] for r in rows] == [198, 7]
    assert {r["price"] for r in rows} == {10.0}, "no price moved; only the count"
    assert _state(conn, "252")["stock_quantity"] == 7


def test_a_shop_that_goes_quiet_does_not_have_a_zero_invented_for_it(conn):
    """The count is published today and gone tomorrow — a field the shop stopped
    sending, not a shelf that emptied. The new observation must not claim 0."""
    entry = make_entry()

    _ingest(conn, entry, COUNTED)
    _ingest(conn, entry, {**silent(COUNTED), "price": 12})   # price moved, count gone

    rows = _stored(conn, "252")
    assert len(rows) == 2
    assert rows[0]["stock_quantity"] == 198
    assert rows[-1]["stock_quantity"] is None, (
        "the shop stopped stating a count; that is not a count of zero")
