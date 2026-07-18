"""Q1/Q2: the canonical row-spec contract — builder + view symmetry, loud drift."""
from __future__ import annotations

import pytest

from scrapex.rowspec import PRODUCT_PRICES, RowBuilder, RowView, spec_for
from scrapex.vocab import ExtractKind


def test_builder_header_is_the_spec_columns():
    builder = RowBuilder(PRODUCT_PRICES)
    assert builder.header == list(PRODUCT_PRICES.columns)


def test_builder_fills_missing_optionals_with_empty_string():
    builder = RowBuilder(PRODUCT_PRICES)
    row = builder.row(
        external_product_id="1", region="EG", currency="EGP",
        vat_included="1", effective_price="10.00",
    )
    view = RowView(PRODUCT_PRICES, builder.header)
    assert view.get(row, "external_sku") == ""       # optional -> ""
    assert view.get(row, "effective_price") == "10.00"


def test_builder_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown fields"):
        RowBuilder(PRODUCT_PRICES).row(nonsense="x")


def test_builder_rejects_missing_required_field():
    with pytest.raises(ValueError, match="required field"):
        RowBuilder(PRODUCT_PRICES).row(external_product_id="1")  # missing region/currency/...


def test_builder_stringifies_bool_and_number():
    row = RowBuilder(PRODUCT_PRICES).row(
        external_product_id=4672, region="EG", currency="EGP",
        vat_included=True, effective_price=168.78,
    )
    view = RowView(PRODUCT_PRICES, row and RowBuilder(PRODUCT_PRICES).header)
    assert view.get(row, "external_product_id") == "4672"
    assert view.get(row, "vat_included") == "1"


def test_view_rejects_header_missing_a_column():
    """Connector drift (dropped/renamed column) must fail loud at ingest (Q4)."""
    truncated = list(PRODUCT_PRICES.columns)[:-1]
    with pytest.raises(ValueError, match="missing columns"):
        RowView(PRODUCT_PRICES, truncated)


def test_view_tolerates_reordered_header():
    reordered = list(reversed(PRODUCT_PRICES.columns))
    builder = RowBuilder(PRODUCT_PRICES)
    row = builder.row(external_product_id="1", region="EG", currency="EGP",
                      vat_included="1", effective_price="10.00")
    # Build a row in reordered layout, read it back by name:
    reordered_row = [row[PRODUCT_PRICES.index(col)] for col in reordered]
    view = RowView(PRODUCT_PRICES, reordered)
    assert view.get(reordered_row, "external_product_id") == "1"
    assert view.get(reordered_row, "currency") == "EGP"


def test_spec_for_unknown_kind_fails_loud():
    with pytest.raises(ValueError, match="no row spec"):
        spec_for(ExtractKind.ENRICHMENT)  # not defined until Phase 3
