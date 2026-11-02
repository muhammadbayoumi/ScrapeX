"""A value of one space is the shop leaving a field empty, not stating it.

His warehouse (v26, mode=ro, 2026-10-26) held 738 MADAR attribute rows whose
raw_value is a single space, on 39 active products; 180 of them flagged as site
filters. Each flagged one became a table column whose every cell is blank: 14 of
MADAR's 36 site-named columns (#1831). His ruling of 2026-10-26: the connector
stops storing them.

STOPPING IS NOT ENOUGH, which is why ingest is in this change. A run retires a
detail only for a (product, code) it restated, so once the connector goes quiet
about a blank code nothing ever restates it, and the 738 rows would stand forever.
"""

from __future__ import annotations

from scrapex import db as dbmod
from scrapex import reports
from scrapex.connectors.magento import _enrichment_rows
from scrapex.ingest import ingest_payloads
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.rowspec import ENRICHMENT, RowBuilder, RowView
from scrapex.vocab import ExtractKind
from tests.test_ingest import make_entry, make_payload, one_row


def _codes(items: list[dict]) -> set[str]:
    builder = RowBuilder(ENRICHMENT)
    view = RowView(ENRICHMENT, builder.header)
    product = {"uid": "p1", "custom_attributesV2": {"items": items}}
    return {view.as_dict(row)["attribute_code"]
            for row in _enrichment_rows(builder, product, {})}


def test_the_connector_does_not_send_a_value_of_one_space():
    codes = _codes([{"code": "amperage", "value": " "},
                    {"code": "mounting_type", "value": "Module Insert"}])
    assert "mounting_type_ar" in codes or "mounting_type" in codes
    assert not {"amperage", "amperage_ar"} & codes


def test_a_selected_option_whose_label_is_blank_is_not_sent_either():
    """A dropdown arrives as selected_options, the other shape the API returns."""
    codes = _codes([{"code": "gangs", "selected_options": [{"label": " "}]}])
    assert not {"gangs", "gangs_ar"} & codes


def test_a_real_value_with_spaces_around_it_is_kept_as_written():
    """The record is the record: only a value with nothing in it is refused."""
    builder = RowBuilder(ENRICHMENT)
    view = RowView(ENRICHMENT, builder.header)
    product = {"uid": "p1", "custom_attributesV2": {
        "items": [{"code": "color", "value": " Yellow "}]}}
    rows = [view.as_dict(r) for r in _enrichment_rows(builder, product, {})]
    assert [r["raw_value"] for r in rows if r["attribute_code"].startswith("color")] == [" Yellow "]


def _details(product_id: str, code: str, value: str) -> FunnelPayload:
    builder = RowBuilder(ENRICHMENT)
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="ELSEWEDYSHOP",
        kind=ExtractKind.ENRICHMENT, client="cli",
        scraped_at="2026-10-26T10:00:00Z", source_url="https://elsewedyshop.com/x",
        header=builder.header,
        rows=[builder.row(external_product_id=product_id, attribute_code=code,
                          attribute_label=code, raw_value=value,
                          attribute_group="Specifications", is_site_filter="1")])


def _setup():
    entry = make_entry(extract=[{"kind": "product_prices"}, {"kind": "enrichment"}])
    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    return entry, conn


def _old_blank(conn) -> None:
    """A blank an earlier crawl stored, the way the 738 sit in his warehouse.
    Written directly: a run stating one today retires it the same run."""
    conn.execute(
        "INSERT INTO source_product_attribute (source_product_id, attribute_code, "
        " attribute_label, raw_value, attribute_group, is_site_filter) "
        "SELECT source_product_id, 'amperage', 'amperage', ' ', 'Specifications', 1 "
        "FROM source_product WHERE external_product_id = '1001'")
    conn.commit()


def _stored(conn) -> list[tuple[str, str]]:
    return sorted(tuple(r) for r in conn.execute(
        "SELECT attribute_code, raw_value FROM source_product_attribute"))


def test_a_run_that_covers_the_product_retires_the_blanks_already_stored():
    entry, conn = _setup()
    try:
        _old_blank(conn)
        assert _stored(conn) == [("amperage", " ")], "the fixture needs the blank stored"

        # The next crawl says nothing about amperage, and restates another code.
        result = ingest_payloads(conn, entry, [_details("1001", "mounting_type", "Module Insert")])

        assert _stored(conn) == [("mounting_type", "Module Insert")]
        assert any("retired 1 " in notice for notice in result.notices), result.notices
    finally:
        conn.close()


def test_the_blank_column_leaves_the_table_with_its_row():
    entry, conn = _setup()
    try:
        _old_blank(conn)
        keys = {c["key"] for c in reports.table_payload(conn, "ELSEWEDYSHOP")["columns"]}
        assert "amperage" in keys, "the fixture must reach the defect: a column of blanks"

        ingest_payloads(conn, entry, [_details("1001", "mounting_type", "Module Insert")])

        keys = {c["key"] for c in reports.table_payload(conn, "ELSEWEDYSHOP")["columns"]}
        assert "amperage" not in keys
        assert "mounting_type" in keys
    finally:
        conn.close()


def test_a_run_never_retires_a_blank_on_a_product_it_did_not_cover():
    """The guard on the guard: a partial crawl must never touch what it did not
    fetch. A run stating details for nothing leaves every stored row alone."""
    entry, conn = _setup()
    try:
        _old_blank(conn)

        ingest_payloads(conn, entry, [make_payload([one_row()])])

        assert _stored(conn) == [("amperage", " ")]
    finally:
        conn.close()


def test_a_blank_on_another_product_survives_a_run_that_covers_only_this_one():
    """The scope, per product: a crawl of one product says nothing about the next."""
    entry, conn = _setup()
    try:
        ingest_payloads(conn, entry, [make_payload([one_row(
            external_product_id="1002", external_sku="SKU-1002")])])
        _old_blank(conn)
        conn.execute(
            "INSERT INTO source_product_attribute (source_product_id, attribute_code, "
            " attribute_label, raw_value, attribute_group, is_site_filter) "
            "SELECT source_product_id, 'gangs', 'gangs', ' ', 'Specifications', 1 "
            "FROM source_product WHERE external_product_id = '1002'")
        conn.commit()

        ingest_payloads(conn, entry, [_details("1001", "mounting_type", "Module Insert")])

        assert _stored(conn) == [("gangs", " "), ("mounting_type", "Module Insert")]
    finally:
        conn.close()


def test_a_blank_from_any_other_connector_does_not_outlive_its_own_run():
    """custom_json, heidelberg, jsonld and woocommerce each guard with `if not
    value`, which a space passes. The sweep is the one place that decides for
    all of them: whatever a connector sends, a blank is gone when the run ends."""
    entry, conn = _setup()
    try:
        ingest_payloads(conn, entry, [_details("1001", "amperage", " ")])
        assert _stored(conn) == []
    finally:
        conn.close()
