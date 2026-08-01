"""The shop's remaining-stock count, all the way to the warehouse.

MADAR publishes `only_x_left_in_stock` on 297 priced leaves. 55ae064 added it to
the census query and carried it to the row, and it still never landed: measured
on the live warehouse 2026-07-30, 0 of 6,146 MADAR observations held a stock
figure.

The connector was not the gap. `_still_the_same_price` is BOTH the price-period
gate and the gate on whether an observation is appended at all, and it decides
on the price key alone — which deliberately excludes stock, so that a stock
movement never reads as a price change. An offer whose price had not moved was
therefore CONFIRMED, nothing was appended, and the column stayed NULL on the row
that already existed. The identical defect had already been found and fixed one
column over, for `price_trade`, in the same function.

WHY THE EXISTING ROUND-TRIP TEST DID NOT CATCH IT: it ingests once, into an
empty database. A first-ever ingest has no open price period, so the gate short-
circuits before it can drop anything and the value lands. The defect only exists
on the SECOND crawl of an unmoved price — which is every crawl in production.
So every test below crawls twice.

All values are the bytes madar returned on 2026-07-30; see
`fixtures/live/madar_stock_counts_2026-07-30.CAPTURE.md`.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex import pricehistory
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.magento import MagentoGraphqlConnector
from scrapex.ingest import ingest_payloads
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.vocab import ExtractKind, ExtractScope

_FIXTURE = Path(__file__).parent / "fixtures/live/madar_stock_counts_2026-07-30.json"

# The two counts the defect report named, and the nine nulls beside them.
_PEGASO = "530458705"    # only_x_left_in_stock: 1
_DADCO = "71205003"      # only_x_left_in_stock: 8
_REBAR_MEMBERS = ("101150812", "101151012", "101151212", "101151412", "101151612",
                  "101151812", "101152012", "101152512", "101153212")


def _census() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _without_counts(census: dict) -> dict:
    """The same capture as every MADAR crawl before 55ae064 sent it.

    Not a hypothetical: the query did not ask for the field, so it was absent
    from the response rather than null. This is what the 6,146 existing
    observations were built from.
    """
    stripped = copy.deepcopy(census)

    def walk(node):
        if isinstance(node, dict):
            node.pop("only_x_left_in_stock", None)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(stripped)
    return stripped


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Fetcher:
    """Serves one census page from the capture, and nothing it did not capture.

    The en_SA store answers with no items on purpose: this fixture is a
    `sku:{in:...}` capture of the default store only, so an English name here
    would be invented. product_name is not a required column, and no assertion
    below reads it.
    """

    def __init__(self, census: dict):
        self._census = census
        self.requests_count = 0

    def post(self, url, json=None, **kwargs):
        self.requests_count += 1
        query = (json or {}).get("query", "")
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        empty = _Response({"data": {"products": {
            "items": [], "page_info": {"current_page": 1, "total_pages": 1}}}})
        if (kwargs.get("headers") or {}).get("Store"):
            if "categoryList" in query:
                return _Response({"data": {"categoryList": [{"children": []}]}})
            return empty
        if "storeConfig" in query:
            # Read live the same day, on both store views.
            return _Response({"data": {"storeConfig": {"weight_unit": "kgs"}}})
        if "categoryList" in query:
            return _Response({"data": {"categoryList": [{"children": []}]}})
        if "category_uid" in query:
            return empty
        return _Response(self._census) if page == 1 else empty

    def close(self):
        pass


def _entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="MADAR", source_name="المدار", base_url="https://www.madar.com",
        family="magento-graphql", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def _crawl(conn, census: dict, scraped_at: str):
    """One full round trip: connector -> rows -> payload -> ingest -> warehouse."""
    tables = [t for t in MagentoGraphqlConnector(_Fetcher(census)).fetch(_entry())
              if t.kind == ExtractKind.PRODUCT_PRICES]
    payloads = [FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="MADAR",
        kind=ExtractKind.PRODUCT_PRICES, client="cli", scraped_at=scraped_at,
        source_url=t.source_url, header=t.header, rows=t.rows) for t in tables]
    assert payloads, "the capture produced no price payload"
    return ingest_payloads(conn, _entry(), payloads)


@pytest.fixture
def warehouse(tmp_path):
    """Two crawls of the same unmoved prices: yesterday without the counts,
    today with them. This is the production history, in miniature."""
    conn = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(conn)
    first = _crawl(conn, _without_counts(_census()), "2026-07-29T10:00:00Z")
    second = _crawl(conn, _census(), "2026-07-30T10:15:00Z")
    try:
        yield conn, first, second
    finally:
        conn.close()


def _observations(conn, sku: str) -> list:
    return conn.execute(
        "SELECT p.observed_at, p.stock_quantity, p.price FROM price_observation p "
        "JOIN source_offer o USING (offer_id) "
        "JOIN source_variant v USING (source_variant_id) "
        "WHERE v.external_sku = ? ORDER BY p.observed_at, p.price_observation_id",
        (sku,)).fetchall()


def _latest_stock(conn, sku: str):
    rows = _observations(conn, sku)
    assert rows, f"no observation at all for {sku}"
    return rows[-1]["stock_quantity"]


# ---- the defect ---------------------------------------------------------------

def test_the_first_crawl_leaves_the_count_null_because_it_never_asked(warehouse):
    """The starting state, asserted rather than assumed: the 6,146 rows that
    already exist are NULL truthfully. Nothing here backfills them."""
    conn, first, _ = warehouse
    assert first.observations > 0, "the first crawl must have appended something"
    assert _observations(conn, _PEGASO)[0]["stock_quantity"] is None
    assert _observations(conn, _DADCO)[0]["stock_quantity"] is None


def test_a_published_count_lands_even_though_the_price_did_not_move(warehouse):
    """THE REGRESSION. Both prices are byte-identical across the two crawls, so
    the price key is unchanged and the old gate confirmed the row and appended
    nothing. The count is a new fact about the offer and must be recorded."""
    conn, _, second = warehouse
    assert _latest_stock(conn, _PEGASO) == 1.0
    assert _latest_stock(conn, _DADCO) == 8.0
    assert second.observations >= 2, (
        "the second crawl must append the two leaves whose count is new")


def test_a_count_of_one_is_not_mistaken_for_nothing(warehouse):
    """`530458705` publishes exactly 1 — the smallest count madar states, and the
    value a falsy guard destroys while a null check keeps. The gate tests
    `is not None` for this reason, and this is the test that says so."""
    conn, _, _ = warehouse
    assert _latest_stock(conn, _PEGASO) == 1.0


def test_the_price_history_is_untouched_by_a_stock_movement(warehouse):
    """The other half of the fix: the count lands INSIDE the open period. A
    stock movement is not a price change and must open no second period, or
    every one of these offers would report a price move that never happened."""
    conn, _, _ = warehouse
    for sku in (_PEGASO, _DADCO):
        periods = conn.execute(
            "SELECT COUNT(*), SUM(closed_at IS NULL) FROM price_period p "
            "JOIN source_offer o USING (offer_id) "
            "JOIN source_variant v USING (source_variant_id) "
            "WHERE v.external_sku = ?", (sku,)).fetchone()
        assert periods[0] == 1, f"{sku}: a stock move opened a second price period"
        assert periods[1] == 1, f"{sku}: the one period must still be open"
        prices = {r["price"] for r in _observations(conn, sku)}
        assert len(prices) == 1, f"{sku}: the price itself must not have moved"


def test_the_earlier_null_is_preserved_not_rewritten(warehouse):
    """price_observation is append-only (trg_price_obs_no_update). The row that
    was taken before the site was asked keeps its NULL: we genuinely did not
    know the count then, and inventing one retroactively would be a claim about
    a day nobody measured."""
    conn, _, _ = warehouse
    for sku in (_PEGASO, _DADCO):
        rows = _observations(conn, sku)
        assert len(rows) == 2, f"{sku}: expected the old row plus one new one"
        assert rows[0]["stock_quantity"] is None
        assert rows[0]["observed_at"] < rows[1]["observed_at"]


# ---- the rule that must NOT be broken to achieve the above -------------------

def test_a_product_the_site_says_nothing_about_stays_null(warehouse):
    """DO NOT INVENT A ZERO. All nine epoxy-rebar members answer null: madar
    publishes no remaining count for any of them. "We do not know how many are
    left" and "none are left" are different facts, and on a price warehouse the
    second is a claim about whether the shop can sell at all.

    Asserted as `is None` per member rather than as an aggregate, so a 0 leaking
    into one of the nine cannot hide behind the other eight.
    """
    conn, _, _ = warehouse
    for sku in _REBAR_MEMBERS:
        rows = _observations(conn, sku)
        assert rows, f"{sku}: the member did not reach the warehouse at all"
        for row in rows:
            assert row["stock_quantity"] is None, (
                f"{sku}: the site published no count; "
                f"the warehouse invented {row['stock_quantity']!r}")


def test_a_silent_product_appends_no_second_observation(warehouse):
    """The same rule from the other side, and the guard on the fix's cost. The
    nine silent members have an unmoved price and no count, so the second crawl
    must confirm them and write nothing — a new observation per crawl per
    unchanged row would turn an append-only table into a daily copy of itself.
    """
    conn, _, _ = warehouse
    for sku in _REBAR_MEMBERS:
        assert len(_observations(conn, sku)) == 1, (
            f"{sku}: a product the site says nothing about gained a second row")


# ---- the second-order defect the same gate caused ----------------------------

def test_the_count_survives_a_rebuild(warehouse):
    """offer_state.stock_quantity is DERIVED: pricehistory.rebuild_offer reads it
    off the latest observation. So while the append was being skipped, the live
    warehouse's 297 offer_state counts were only ever the value _confirm_seen
    stamped on its way out — and _confirm_seen runs for a SUCCESS only. A
    rebuild, or any run that did not finish, dropped all 297 back to NULL.

    Measured before the fix: offer_state 8.0, then rebuild_offer -> None.
    """
    conn, _, _ = warehouse
    offer_id = conn.execute(
        "SELECT o.offer_id FROM source_offer o "
        "JOIN source_variant v USING (source_variant_id) "
        "WHERE v.external_sku = ?", (_DADCO,)).fetchone()["offer_id"]
    state = "SELECT stock_quantity FROM offer_state WHERE offer_id = ?"
    assert conn.execute(state, (offer_id,)).fetchone()["stock_quantity"] == 8.0
    pricehistory.rebuild_offer(conn, offer_id)
    assert conn.execute(state, (offer_id,)).fetchone()["stock_quantity"] == 8.0, (
        "the count did not survive being re-derived from the observations")


def test_a_third_crawl_with_an_unchanged_count_appends_nothing(warehouse):
    """The count is recorded when it MOVES, not on every crawl that sees it.
    Without this the 297 would grow a row a day each and the append-only table
    would stop meaning "something changed"."""
    conn, _, _ = warehouse
    before = len(_observations(conn, _DADCO))
    third = _crawl(conn, _census(), "2026-07-31T10:15:00Z")
    assert len(_observations(conn, _DADCO)) == before
    assert third.observations == 0
    assert third.confirmed > 0
