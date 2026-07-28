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
        external_product_id="1", country_code_alpha2="EG", currency="EGP",
        tax_included="1", price="10.00",
    )
    view = RowView(PRODUCT_PRICES, builder.header)
    assert view.get(row, "external_sku") == ""       # optional -> ""
    assert view.get(row, "price") == "10.00"


def test_builder_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown fields"):
        RowBuilder(PRODUCT_PRICES).row(nonsense="x")


def test_builder_rejects_missing_required_field():
    with pytest.raises(ValueError, match="required field"):
        RowBuilder(PRODUCT_PRICES).row(external_product_id="1")  # missing region/currency/...


def test_builder_stringifies_bool_and_number():
    row = RowBuilder(PRODUCT_PRICES).row(
        external_product_id=4672, country_code_alpha2="EG", currency="EGP",
        tax_included=True, price=168.78,
    )
    view = RowView(PRODUCT_PRICES, row and RowBuilder(PRODUCT_PRICES).header)
    assert view.get(row, "external_product_id") == "4672"
    assert view.get(row, "tax_included") == "1"


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
    row = builder.row(external_product_id="1", country_code_alpha2="EG", currency="EGP",
                      tax_included="1", price="10.00")
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


# The pre-sweep header, written out. It is deliberately NOT derived from the
# current spec: a derived fixture updates itself and goes on passing while
# the claim it makes stops being true.
PRE_SWEEP_HEADER = [
    "external_product_id", "external_variant_id", "external_sku",
    "product_name", "brand_raw", "option_label", "option_fingerprint",
    "product_link", "country_code_alpha2", "currency", "tax_included", "price_before",
    "price_sale", "price", "availability", "stock_quantity",
]


def test_a_payload_captured_after_the_widening_is_still_readable():
    """The contract spans two engines and the local inbox holds rows captured
    on the day they were made. If widening the spec made those unreadable, the
    data would still be on disk and no longer usable — the worst outcome."""
    header = [c for c in PRODUCT_PRICES.columns if c not in PRODUCT_PRICES.additive]
    row = ["4672", "", "SKU-1", "Cable", "", "Elsewedy", "أحمر", "", "",
           "", "EG", "EGP", "1", "350", "", "300", "in_stock", "5", "", ""]
    row = row[:len(header)]

    view = RowView(PRODUCT_PRICES, header)

    assert view.get(row, "unit") == "", "an additive column reads as empty"


def test_a_payload_captured_before_the_language_sweep_is_REFUSED():
    """The opposite guarantee, and the sharper one.

    `product_name` kept its name and changed its meaning from Arabic to
    English. A pre-sweep row read through the new spec would land Arabic in
    the English column with nothing to reveal it — so the four _ar columns
    are NOT additive and a stale header fails on SHAPE, independently of the
    payload version number.

    Constructed directly rather than through FunnelPayload: after the bump a
    stored v1 payload dies at the version validator before RowView is ever
    built, which would test the wrong mechanism."""
    with pytest.raises(ValueError):
        RowView(PRODUCT_PRICES, PRE_SWEEP_HEADER)


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


def test_a_payload_still_carrying_brand_raw_is_refused_not_misread():
    """`brand` is non-additive on purpose, the same defence the _ar columns use.

    RowView returns "" for a missing ADDITIVE column and raises for a missing
    non-additive one. If the pair were additive, a pre-0047 payload carrying
    brand_raw would be accepted and its brand silently dropped — a whole column
    of every ALSWEED product gone, with no error anywhere. PAYLOAD_VERSION is
    the other refusal; this one is independent of the version number.
    """
    import pytest

    from scrapex.rowspec import PRODUCT_PRICES, RowView

    assert "brand" not in PRODUCT_PRICES.additive
    assert "brand_ar" not in PRODUCT_PRICES.additive

    pre_sweep = [c for c in PRODUCT_PRICES.columns if c not in ("brand", "brand_ar")]
    pre_sweep.insert(4, "brand_raw")
    with pytest.raises(ValueError):
        RowView(PRODUCT_PRICES, pre_sweep)
