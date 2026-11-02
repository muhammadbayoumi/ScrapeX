"""His ruling on the 15 MADAR codes the group map had never been taught (#1835).

They went unasked because the note naming them was dropped (#1836), and the
fallback filed all 15 under More information. He delegated the filing on
2026-10-26 («صنفهم»), so it follows his own boundary (vocab.py): a property OF the
product is Specifications, information ABOUT it is More information.
"""

from __future__ import annotations

import pytest

from scrapex.connectors.magento import _enrichment_rows
from scrapex.rowspec import ENRICHMENT, RowBuilder, RowView
from scrapex.vocab import DetailGroup, group_for_code

_SPECIFICATIONS = (
    "drilling_capacity", "max_flow_lpm", "impact_energy_j", "max_head_m", "max_torque_nm",
    "fuel_tank_l", "wire_gauge", "grit", "melamine_top", "drill_bit_length",
    "drill_bit_size", "number_of_teeth", "roll_specification", "ejf_percentage",
)


@pytest.mark.parametrize("code", _SPECIFICATIONS)
def test_a_property_of_the_product_files_under_specifications(code):
    assert group_for_code(code) == (DetailGroup.SPECIFICATIONS, True)
    assert group_for_code(f"{code}_ar") == (DetailGroup.SPECIFICATIONS, True)


def test_which_model_it_is_files_beside_the_manufacturer():
    """Information ABOUT the product, the same side as manufacturer and origin."""
    assert group_for_code("product_model") == (DetailGroup.MORE_INFORMATION, True)
    assert group_for_code("product_model_ar") == (DetailGroup.MORE_INFORMATION, True)
    assert group_for_code("manufacturer")[0] == group_for_code("product_model")[0]


def test_a_code_nobody_has_ruled_on_is_still_reported_as_new():
    """The standing rule stays armed: taught 15 codes, not a wider fallback."""
    assert group_for_code("a_code_no_shop_has_published") == (DetailGroup.MORE_INFORMATION, False)


def test_the_crawl_files_them_and_stops_asking():
    builder = RowBuilder(ENRICHMENT)
    view = RowView(ENRICHMENT, builder.header)
    asked: set[str] = set()
    product = {"uid": "p1", "custom_attributesV2": {"items": [
        {"code": "drilling_capacity", "value": "Wood 85 mm, Steel 10 mm"},
        {"code": "product_model", "value": "WBK III"}]}}

    rows = [view.as_dict(r) for r in _enrichment_rows(builder, product, {}, unknown_codes=asked)]

    assert asked == set()
    groups = {r["attribute_code"].removesuffix("_ar"): r["attribute_group"] for r in rows}
    assert groups["drilling_capacity"] == "Specifications"
    assert groups["product_model"] == "More information"
