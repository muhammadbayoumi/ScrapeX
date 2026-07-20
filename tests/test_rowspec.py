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
    """Connector drift (dropped/renamed column) must fail loud at ingest (Q4).

    Dropping an ADDITIVE column is tolerated by design, so this has to drop a
    core one to prove drift detection still works.
    """
    dropped = [c for c in PRODUCT_PRICES.columns
               if c not in PRODUCT_PRICES.additive][:-1]
    with pytest.raises(ValueError, match="missing columns"):
        RowView(PRODUCT_PRICES, dropped)


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
    """ENRICHMENT is defined now, so the guard needs a kind that genuinely has
    no spec. A string is not an ExtractKind and must not resolve to one."""
    with pytest.raises(ValueError, match="no row spec"):
        spec_for("not_a_kind")


# ---- the widened contract ----------------------------------------------------

def test_enrichment_is_a_long_format_bag_not_more_fixed_columns():
    """One ROW per attribute, so a site with nine attributes and a site with
    forty both fit without the contract changing again."""
    from scrapex.rowspec import ENRICHMENT

    builder = RowBuilder(ENRICHMENT)
    row = builder.row(external_product_id="501", attribute_code="length",
                      attribute_label="Length", raw_value="100 meters",
                      numeric_value="100", unit_raw="meters", lang="en",
                      value_url="https://shop.example/attr/length-100")
    view = RowView(ENRICHMENT, builder.header)

    assert view.get(row, "numeric_value") == "100"
    assert view.get(row, "unit_raw") == "meters"
    # Attribute values are frequently links on these sites; losing the link
    # means re-scraping every product to get it back.
    assert view.get(row, "value_url") == "https://shop.example/attr/length-100"


def test_an_attribute_with_no_code_or_value_is_refused():
    from scrapex.rowspec import ENRICHMENT

    with pytest.raises(ValueError, match="required field"):
        RowBuilder(ENRICHMENT).row(external_product_id="501", attribute_code="length")


def test_a_payload_captured_before_the_widening_is_still_readable():
    """The contract spans two engines and the local inbox holds rows captured
    on the day they were made. If widening the spec made those unreadable, the
    data would still be on disk and no longer usable — the worst outcome."""
    old_header = [c for c in PRODUCT_PRICES.columns if c not in PRODUCT_PRICES.additive]
    old_row = ["4672", "", "SKU-1", "Cable", "Elsewedy", "", "", "",
               "EG", "EGP", "1", "350", "", "300", "in_stock", "5"]
    assert len(old_row) == len(old_header)

    view = RowView(PRODUCT_PRICES, old_header)

    assert view.get(old_row, "effective_price") == "300"
    assert view.get(old_row, "unit") == "", "a column that did not exist reads as empty"
    assert view.as_dict(old_row)["category_path"] == ""


def test_a_truncated_row_reads_empty_rather_than_raising():
    """A payload cut short mid-write must not surface as an IndexError that
    nothing upstream recognises."""
    view = RowView(PRODUCT_PRICES, list(PRODUCT_PRICES.columns))
    assert view.get(["4672", "", "SKU-1"], "availability") == ""


def test_a_column_cannot_be_both_additive_and_required():
    from scrapex.rowspec import RowSpec

    with pytest.raises(ValueError, match="both additive and required"):
        RowSpec(kind=ExtractKind.PRODUCT_PRICES, columns=("a", "b"),
                required=frozenset({"a"}), additive=frozenset({"a"}))
