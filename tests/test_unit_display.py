"""A price is shown with what it is a price OF, everywhere it is shown.

The unit became real in the warehouse one commit ago — stored, part of offer
identity, part of the price key. None of that is worth anything while every
screen still renders a bare number: 325 per tonne and 325 per bag look identical
in a column, and a reader compares them.

The owner's note is explicit: "The unit of measurement must be clearly identified
for every product and price."
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.ingest import ingest_payloads
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.reports import (
    EXPORT_HEADER, browse_observations, export_source_table, price_unit,
    recent_observations,
)
from scrapex.rowspec import PRODUCT_PRICES, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="SHOP", source_name="متجر", base_url="https://shop.example",
        family="shopify-json", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    ))


def payload(rows) -> FunnelPayload:
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="SHOP",
        kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at="2026-07-20T10:00:00Z", source_url="https://shop.example",
        header=list(PRODUCT_PRICES.columns), rows=rows)


def row(**over) -> list[str]:
    fields = dict(external_product_id="P1", product_name="أسمنت", region="SA",
                  currency="SAR", vat_included="1", effective_price="325")
    fields.update(over)
    return RowBuilder(PRODUCT_PRICES).row(**fields)


# ---- the pure formatter ------------------------------------------------------

def test_a_plain_unit_reads_as_itself():
    assert price_unit("tonne", 1) == "tonne"
    assert price_unit("liter", 1.0) == "liter"


def test_a_quantity_travels_WITH_its_unit():
    """One string, so a screen cannot render the number and drop the unit — the
    pair only means anything together."""
    assert price_unit("m", 100) == "100 m"
    assert price_unit("kg", 2.5) == "2.5 kg"


def test_an_unstated_unit_is_empty_not_invented():
    """Defaulting to 'each' would assert something the source never said."""
    assert price_unit(None, 1) == ""
    assert price_unit("", 100) == ""


def test_a_broken_basis_quantity_does_not_break_the_page():
    assert price_unit("kg", None) == "kg"
    assert price_unit("kg", "not a number") == "kg"


# ---- every read path ---------------------------------------------------------

def test_the_data_table_carries_the_unit(conn):
    ingest_payloads(conn, entry(), [payload([row(unit="tonne")])])

    page = browse_observations(conn, "SHOP")

    assert page.rows[0]["unit"] == "tonne"


def test_a_roll_shows_its_quantity_in_the_table(conn):
    ingest_payloads(conn, entry(), [payload([row(unit="m", basis_quantity="100")])])

    assert browse_observations(conn, "SHOP").rows[0]["unit"] == "100 m"


def test_a_source_without_units_still_lists_its_prices(conn):
    """The unit join must never suppress a row — most shops publish no unit."""
    ingest_payloads(conn, entry(), [payload([row()])])

    page = browse_observations(conn, "SHOP")

    assert len(page.rows) == 1, "a unit-less price vanished from the table"
    assert page.rows[0]["unit"] == ""
    assert page.rows[0]["effective_price"] == 325


def test_the_export_has_a_unit_column_beside_the_price(conn):
    ingest_payloads(conn, entry(), [payload([row(unit="tonne")])])

    header, table = export_source_table(conn, "SHOP")

    assert "unit" in header, "exported workbooks had prices with no unit at all"
    assert header.index("unit") == header.index("effective_price") + 1, \
        "the unit must sit beside the number it qualifies, not at the far end"
    assert table[0][header.index("unit")] == "tonne"


def test_the_export_header_and_row_widths_agree(conn):
    ingest_payloads(conn, entry(), [payload([row(unit="tonne")])])
    header, table = export_source_table(conn, "SHOP")
    assert all(len(r) == len(header) for r in table), \
        "adding a column shifted every value one cell to the right"


def test_the_panel_sample_carries_the_unit(conn):
    ingest_payloads(conn, entry(), [payload([row(unit="tonne")])])

    assert recent_observations(conn, "SHOP")[0]["unit"] == "tonne"


def test_the_change_feed_says_per_what(conn):
    """"325 -> 300" without a unit invites the reader to assume the unit held
    still, which is exactly what may have moved."""
    from scrapex.changes import recent_changes

    ingest_payloads(conn, entry(), [payload([row(unit="tonne")])])
    ingest_payloads(conn, entry(), [FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="SHOP",
        kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at="2026-07-27T10:00:00Z", source_url="https://shop.example",
        header=list(PRODUCT_PRICES.columns),
        rows=[row(unit="tonne", effective_price="300")])])

    feed = recent_changes(conn, "SHOP")

    assert feed, "no change was recorded for a real price move"
    assert feed[0]["unit"] == "tonne"
