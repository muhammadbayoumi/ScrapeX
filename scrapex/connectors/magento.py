"""magento-graphql family connector (ENGINEERING.md A3: proven family).

Madar (the flagship) runs Magento 2 with an open GraphQL endpoint. We list all
priced products paginated (`filter:{price:{from:"0"}}`) and map each configurable
variant — or each simple product — to one canonical PRODUCT_PRICES row.
Prices are VAT-exclusive on this platform (the source's vat_mode records that).
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..normalize import option_fingerprint
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import HttpFetcher, ScrapedTable

PAGE_SIZE = 100

_QUERY = """query($pageSize:Int!,$currentPage:Int!){
  products(filter:{price:{from:"0"}},pageSize:$pageSize,currentPage:$currentPage){
    page_info{current_page total_pages}
    items{
      uid sku name url_key stock_status
      price_range{minimum_price{regular_price{value} final_price{value}}}
      ... on ConfigurableProduct{
        variants{
          product{uid sku name stock_status price_range{minimum_price{regular_price{value} final_price{value}}}}
          attributes{code label}
        }
      }
    }
  }
}"""


def _availability(stock_status: str | None) -> str:
    if stock_status == "IN_STOCK":
        return Availability.IN_STOCK.value
    if stock_status == "OUT_OF_STOCK":
        return Availability.OUT_OF_STOCK.value
    return Availability.UNKNOWN.value


def _prices(node: dict) -> tuple[float | None, float | None]:
    mp = ((node.get("price_range") or {}).get("minimum_price")) or {}
    regular = (mp.get("regular_price") or {}).get("value")
    final = (mp.get("final_price") or {}).get("value")
    return regular, final


class MagentoGraphqlConnector:
    connector_id = "magento-graphql"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/graphql"
        ctx = {
            "base": base,
            "currency": source.currency or "UNKNOWN",
            "vat": "1" if source.vat_mode.value == "incl" else "0",
            "region": source.default_region,
        }
        rows: list[list[str]] = []
        page = 1
        while True:
            body = {"query": _QUERY, "variables": {"pageSize": PAGE_SIZE, "currentPage": page}}
            products = (((self._fetcher.post(endpoint, json=body).json() or {})
                         .get("data") or {}).get("products")) or {}
            items = products.get("items") or []
            if not items:
                break
            for product in items:
                rows.extend(self._product_rows(builder, product, ctx))
            total_pages = ((products.get("page_info") or {}).get("total_pages")) or page
            if page >= total_pages:
                break
            page += 1

        yield ScrapedTable(
            source_key=source.source_key, kind=PRODUCT_PRICES.kind,
            source_url=endpoint, header=builder.header, rows=rows,
        )

    @staticmethod
    def _product_rows(builder: RowBuilder, product: dict, ctx: dict) -> list[list[str]]:
        url_key = product.get("url_key") or ""
        url = f"{ctx['base']}/{url_key}.html" if url_key else ""
        variants = product.get("variants") or []
        out: list[list[str]] = []

        def row(pid, vid, sku, name, reg, fin, stock, label="", fp=""):
            effective = fin if fin is not None else reg
            if effective is None:
                return  # a product with no price — skip, don't emit an empty required field
            out.append(builder.row(
                external_product_id=pid, external_variant_id=vid, external_sku=sku or "",
                product_name=name or "", option_label=label, option_fingerprint=fp,
                product_url=url, region=ctx["region"], currency=ctx["currency"], vat_included=ctx["vat"],
                regular_price=reg if reg is not None else effective,
                sale_price=fin if (reg is not None and fin is not None and reg != fin) else "",
                effective_price=effective, availability=_availability(stock),
            ))

        if variants:
            for v in variants:
                child = v.get("product") or {}
                attrs = [a for a in (v.get("attributes") or []) if a.get("code")]
                reg, fin = _prices(child)
                row(product.get("uid"), child.get("uid"), child.get("sku"),
                    child.get("name") or product.get("name"), reg, fin, child.get("stock_status"),
                    label=", ".join(a.get("label", "") for a in attrs),
                    fp=option_fingerprint({a["code"]: a.get("label", "") for a in attrs}) if attrs else "")
        else:
            reg, fin = _prices(product)
            row(product.get("uid"), product.get("uid"), product.get("sku"),
                product.get("name"), reg, fin, product.get("stock_status"))
        return out
