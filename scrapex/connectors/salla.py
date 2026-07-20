"""salla-html family connector (ENGINEERING.md A3: proven family).

Salla stores (alsweed = «السويد», elburoj) are server-rendered with schema.org
Product JSON-LD on each product page. We enumerate product URLs from the
sitemap (numeric /p{id}), fetch each page, and read the JSON-LD.

Gotcha (handled): variant-priced products expose offers.price = 0 in JSON-LD;
we fall back to an AggregateOffer lowPrice, and skip a product with no usable
price (its real variant prices need the extension's session capture — later).
The pure parsers (`sitemap_locs`, `parse_product_jsonld`, `offer_price`) are
unit-tested against fixtures; only the fetch loop touches the network.
"""
from __future__ import annotations

import re
from typing import Iterable

from ..config import SourceEntry
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import HttpFetcher, ScrapedTable
# Shared SSR helpers (also re-exported for salla's tests). offer_price/parse are
# generic; the /p{id} id scheme below is the salla-specific part.
from .jsonld import brand_name, offer_price, parse_product_jsonld, sitemap_locs

_PRODUCT_ID = re.compile(r"/p(\d{5,})")


def one_url_per_product(urls: list[str]) -> list[str]:
    """One URL per product id, first occurrence wins.

    A Salla sitemap index lists every product ONCE PER LOCALE — /ar/…/p123 and
    /en/…/p123 are the same product. Deduplicating by URL string, as this did,
    collapses nothing: alsweed published 2466 URLs for 1233 products, so every
    crawl fetched each page twice and emitted two rows carrying the SAME
    external_product_id.

    That is worse than wasted requests. Two rows per product inflate the count,
    so min_expected_rows can never catch it — the canary only watches for rows
    going missing — and downstream every product looks like it has a duplicate
    offer. It also doubled the crawl cost against elburoj, which asks for a
    10-second delay between requests.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for url in urls:
        match = _PRODUCT_ID.search(url)
        key = match.group(1) if match else url
        if key in seen:
            continue
        seen.add(key)
        kept.append(url)
    return kept


class SallaConnector:
    connector_id = "salla-html"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        vat = "1" if source.vat_mode.value == "incl" else "0"
        rows: list[list[str]] = []

        for url in self._product_urls(f"{base}/ar/sitemap.xml"):
            try:
                html = self._fetcher.get(url).text
            except Exception:  # noqa: BLE001 — one dead product page never kills the crawl (Q3)
                continue
            node = parse_product_jsonld(html)
            if not node:
                continue
            row = self._row(builder, node, url, source, vat)
            if row is not None:
                rows.append(row)

        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base, builder.header, rows)

    def _product_urls(self, sitemap_url: str) -> list[str]:
        try:
            locs = sitemap_locs(self._fetcher.get(sitemap_url).text)
        except Exception:  # noqa: BLE001
            return []
        products = [u for u in locs if _PRODUCT_ID.search(u)]
        for sub in (u for u in locs if u.endswith(".xml")):
            try:
                products += [u for u in sitemap_locs(self._fetcher.get(sub).text) if _PRODUCT_ID.search(u)]
            except Exception:  # noqa: BLE001
                continue
        return one_url_per_product(products)

    @staticmethod
    def _row(builder: RowBuilder, node: dict, url: str, source: SourceEntry, vat: str):
        price, currency, availability = offer_price(node.get("offers"))
        if not price:
            return None  # variant-priced with no usable price — needs session capture (later)
        m = _PRODUCT_ID.search(url)
        pid = m.group(1) if m else str(node.get("sku") or url)
        in_stock = "InStock" in availability
        return builder.row(
            external_product_id=pid, external_variant_id=pid,
            external_sku=str(node.get("sku") or ""), product_name=str(node.get("name") or ""),
            brand_raw=brand_name(node), product_url=url,
            region=source.default_region, currency=currency or source.currency or "UNKNOWN", vat_included=vat,
            regular_price=price, sale_price="", effective_price=price,
            availability=Availability.IN_STOCK.value if in_stock else Availability.UNKNOWN.value,
        )
