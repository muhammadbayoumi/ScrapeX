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


def entry(**over) -> SourceEntry:
    base = dict(
        source_key="SHOP", source_name="متجر", base_url="https://shop.example",
        family="shopify-json", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)])
    base.update(over)
    return SourceEntry.model_validate(base)


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


# ---- per-source columns (the review's headline ask) --------------------------
#
# "The schema and data tables must be dynamic because the source websites do not
#  provide data in a consistent format... Only fields that are available and
#  relevant to the selected source should be shown."
#
# The "Manage columns" panel was fully built and worked — over a CONSTANT 14-key
# header shared by every site, and hiding a column changed nothing on the screen
# where it was clicked. The machinery existed, wired to the wrong input on both
# ends.

def test_a_source_with_no_variants_or_skus_is_not_given_those_columns(conn):
    """Direct answer to the review's key question — until now, yes, empty
    columns were still shown, filled with em-dashes."""
    from scrapex.reports import column_presence

    ingest_payloads(conn, entry(), [payload([row(unit="tonne")])])

    present = column_presence(conn, "SHOP")

    assert "option_label" not in present, "a Variant column of em-dashes"
    assert "sku" not in present, "an SKU column of em-dashes"
    assert "unit" in present and "product_name" in present and "effective_price" in present


def test_a_source_that_does_supply_them_keeps_those_columns(conn):
    from scrapex.reports import column_presence

    ingest_payloads(conn, entry(), [payload([
        row(external_sku="SKU-1", option_label="Red / Large",
            option_fingerprint="color=red|size=large")])])

    present = column_presence(conn, "SHOP")

    assert "sku" in present and "option_label" in present


def test_presence_is_per_source_not_global(conn):
    """Two sources in one warehouse must not share a column set."""
    from scrapex.reports import column_presence

    ingest_payloads(conn, entry(), [payload([row(external_sku="SKU-1")])])
    other = entry(source_key="COMMODITY")
    ingest_payloads(conn, other, [FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="COMMODITY",
        kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at="2026-07-20T10:00:00Z", source_url="https://x.example",
        header=list(PRODUCT_PRICES.columns), rows=[row(unit="liter")])])

    assert "sku" in column_presence(conn, "SHOP")
    assert "sku" not in column_presence(conn, "COMMODITY")


def test_the_identifying_columns_are_never_swept_away(conn):
    """A table with no name and no price is not a shorter table, it is not a
    price list."""
    from scrapex.reports import ESSENTIAL_COLUMNS, column_presence

    ingest_payloads(conn, entry(), [payload([row()])])

    assert ESSENTIAL_COLUMNS <= column_presence(conn, "SHOP")


# ---- the table has to be READABLE, not merely correct ------------------------
#
# Rendered and looked at: every row was three lines tall because the tax cell
# carried a sentence, the price broke across two lines, and a Status column read
# "Unknown" 721 times. Correct data laid out unreadably is not a working screen.

def test_a_column_that_says_unknown_everywhere_is_not_a_column(conn):
    """'unknown' is a non-empty string that states nothing. Counting it as
    present gave GPP a Status column reading Unknown on all 721 rows."""
    from scrapex.reports import column_presence

    ingest_payloads(conn, entry(), [payload([row(availability="unknown")])])

    assert "availability" not in column_presence(conn, "SHOP")


def test_a_source_with_real_stock_data_keeps_its_status_column(conn):
    from scrapex.reports import column_presence

    ingest_payloads(conn, entry(), [payload([row(availability="in_stock")])])

    assert "availability" in column_presence(conn, "SHOP")


def test_the_tax_cell_is_short_and_the_sentence_moves_to_the_tooltip(conn):
    """"Tax included, rate not published" wrapped to three lines and tripled the
    height of every row. The short form says the same thing in a cell."""
    from scrapex import tax

    state = tax.TaxState("general", "incl", None, "", "https://x", "*")
    assert state.short_label() == "Incl. —"
    assert state.label() == "Tax included, rate not published"
    assert len(state.short_label()) < len(state.label()) / 3


def test_the_short_label_never_implies_a_rate_it_does_not_have():
    """"Incl. —" says a rate exists nowhere. "Incl. 0%" would say tax is zero,
    which is a claim nobody made."""
    from scrapex import tax

    short = tax.TaxState("general", "incl", None, "", "u", "*").short_label()

    assert "0" not in short and "%" not in short
    assert tax.UNVERIFIED.short_label() == "Unverified"


def test_a_stated_rate_still_shows_the_number_in_the_cell():
    from scrapex import tax

    assert tax.TaxState("stated", "incl", 15, "", "u", "*").short_label() == "Incl. 15%"
    assert tax.TaxState("stated", "excl", 15, "", "u", "*").short_label() == "Excl. 15%"


def test_both_the_short_and_the_full_label_reach_the_page(conn):
    """The cell needs one and the tooltip needs the other; losing either makes
    the compact cell either unreadable or unexplained."""
    ingest_payloads(conn, entry(), [payload([row()])])

    shown = browse_observations(conn, "SHOP").rows[0]

    assert shown["tax_short"] and shown["tax_label"]
    assert shown["tax_short"] != shown["tax_label"]
