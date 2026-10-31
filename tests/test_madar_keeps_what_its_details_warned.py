"""A warning raised while reading details must reach the run (#1836).

The Magento connector reads the details AFTER the last price page has been
yielded, and every note it raised there went into a list nothing read again. So
the sentence that puts his standing rule in front of him, «اى معلومة نلاقيها عن
منتج فى المستقبل اسالنى نحطها فى انهو جروب», never left the connector: 15 MADAR
codes were filed under More information by the fallback, job_log_entry holds 0
rows of it, and MADAR's last four runs record warning_count 0. A failed facet or
label query, which turns every label into a raw code, vanished the same way.
"""

from __future__ import annotations

from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.magento import MagentoGraphqlConnector
from scrapex.ingest import ingest_payloads
from scrapex.payload import new_payload
from scrapex.vocab import ExtractKind, ExtractScope

_PRODUCT = {
    "__typename": "SimpleProduct", "uid": "QU5H", "sku": "51116-TSB", "url_key": "drill",
    "name": "مثقاب", "stock_status": "IN_STOCK", "categories": [], "weight": 2,
    "is_qty_decimal": False, "min_sale_qty": 1, "qty_increments": 1,
    "only_x_left_in_stock": None,
    "custom_attributesV2": {"items": [{"code": "drilling_capacity", "value": "85 mm"}]},
    "price_range": {"minimum_price": {"regular_price": {"value": 100.0},
                                      "final_price": {"value": 100.0}},
                    "maximum_price": {"final_price": {"value": 100.0}}},
}


class _Response:
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


class _Fetcher:
    def __init__(self, items=None, broken=()):
        self.items = [_PRODUCT] if items is None else items
        self.broken = broken

    def post(self, url, json=None, **kwargs):
        query = (json or {}).get("query", "")
        page = (json or {}).get("variables", {}).get("currentPage", 1)
        for marker in self.broken:
            if marker in query:
                raise OSError(f"{marker} refused")
        if "storeConfig" in query:
            return _Response({"data": {"storeConfig": {"weight_unit": "kgs"}}})
        if "categoryList" in query:
            return _Response({"data": {"categoryList": [{"children": []}]}})
        if "aggregations" in query:
            return _Response({"data": {"products": {"aggregations": []}}})
        if "customAttributeMetadataV2" in query:
            return _Response({"data": {"customAttributeMetadataV2": {"items": [
                {"code": "drilling_capacity", "label": "قدرة الثقب"}]}}})
        empty = {"data": {"products": {
            "items": [], "page_info": {"current_page": 1, "total_pages": 1}}}}
        if (kwargs.get("headers") or {}).get("Store") or "category_uid" in query or page != 1:
            return _Response(empty)
        return _Response({"data": {"products": {
            "page_info": {"current_page": 1, "total_pages": 1}, "items": self.items}}})

    def close(self): pass


def _entry() -> SourceEntry:
    return SourceEntry.model_validate({
        "source_key": "MADAR", "source_name": "المدار", "base_url": "https://www.madar.com",
        "family": "magento-graphql", "currency": "SAR", "default_region": "SA",
        "vat_mode": "incl",
        "extract": [ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS),
                    ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS)]})


def _tables(fetcher):
    return list(MagentoGraphqlConnector(fetcher).fetch(_entry()))


def _warnings(tables) -> list[str]:
    return [w for t in tables for w in t.warnings]


def test_a_new_detail_code_reaches_the_run():
    """The standing rule's own question, and the reason this file exists."""
    warned = _warnings(_tables(_Fetcher()))
    assert any("detail codes are new" in w and "drilling_capacity" in w for w in warned), warned


def test_a_failed_facet_query_reaches_the_run():
    warned = _warnings(_tables(_Fetcher(broken=("aggregations",))))
    assert any("aggregations unavailable" in w for w in warned), warned


def test_a_failed_label_query_reaches_the_run():
    warned = _warnings(_tables(_Fetcher(broken=("customAttributeMetadataV2",))))
    assert any("attribute labels unavailable" in w for w in warned), warned


def test_a_warning_rides_the_details_table_once():
    """Not on a price page as well: capture lists every table's warnings, and a
    question asked twice is how a rule stops being read."""
    tables = _tables(_Fetcher())
    prices = [t for t in tables if t.kind == ExtractKind.PRODUCT_PRICES]
    details = [t for t in tables if t.kind == ExtractKind.ENRICHMENT]
    assert not any("detail codes are new" in w for t in prices for w in t.warnings)
    assert sum("detail codes are new" in w for t in details for w in t.warnings) == 1


def test_a_note_raised_before_the_prices_is_not_repeated_on_the_details_table():
    """Page 1 carries everything raised up to it; the details table carries only
    what was raised after it."""
    tables = _tables(_Fetcher())
    details = [t for t in tables if t.kind == ExtractKind.ENRICHMENT]
    prices = [t for t in tables if t.kind == ExtractKind.PRODUCT_PRICES]
    assert not set(prices[0].warnings) & set(details[0].warnings)


def test_a_warning_survives_when_no_details_table_had_rows():
    """No priced product, so no detail rows at all, and a facet query that failed.
    With nothing to carry them the notes used to vanish with the table."""
    tables = _tables(_Fetcher(items=[], broken=("aggregations",)))
    assert any("aggregations unavailable" in w for w in _warnings(tables))


def test_a_details_table_with_no_rows_ingests_as_nothing(tmp_path):
    """A table that exists only to carry a warning must not disturb the run."""
    from scrapex import db as dbmod
    tables = [t for t in _tables(_Fetcher(items=[], broken=("aggregations",)))
              if t.kind == ExtractKind.ENRICHMENT]
    assert tables and tables[0].rows == []
    conn = dbmod.connect(tmp_path / "empty.db")
    dbmod.migrate(conn)
    result = ingest_payloads(conn, _entry(), [new_payload(
        source_key="MADAR", kind=ExtractKind.ENRICHMENT, client="cli",
        scraped_at="2026-10-31T10:00:00Z", source_url=tables[0].source_url,
        header=tables[0].header, rows=tables[0].rows)])
    assert result.errors == []
    assert conn.execute("SELECT COUNT(*) FROM source_product_attribute").fetchone()[0] == 0
