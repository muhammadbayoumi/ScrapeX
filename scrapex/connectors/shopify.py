"""shopify-json family connector (ENGINEERING.md A3: proven family).

Every Shopify storefront exposes /products.json — paginated, structured
products + variants + prices. One variant -> one product_prices row, built
against the canonical RowSpec (never hardcoded column order, Q2).
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..normalize import option_fingerprint
from ..rowspec import PRODUCT_PRICES, RowBuilder
from ..vocab import Availability
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

PAGE_SIZE = 250  # Shopify hard max per page

# Shopify serves a translated catalogue under a locale prefix when the shop
# publishes one. elsewedyshop declares ar + en (hreflang on its own homepage)
# and /en/products.json answers with the English titles for the SAME ids —
# verified live 2026-07-23. The prefix is TRIED, never assumed: a shop with one
# language answers the same titles and this adds nothing to the rows.
ENGLISH_LOCALE = "en"


class ShopifyConnector:
    connector_id = "shopify-json"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        rows: list[list[str]] = []
        base = source.base_url.rstrip("/")
        vat_flag = "1" if source.vat_mode.value == "incl" else "0"
        currency = source.currency or "UNKNOWN"
        titles: dict[str, str] = {}
        notes: list[str] = []

        page = 1
        while True:
            url = f"{base}/products.json?limit={PAGE_SIZE}&page={page}"
            products = self._fetcher.get(url).json().get("products", [])
            if not products:  # explicit stop: empty page ends pagination (Q4)
                break
            for product in products:
                titles[str(product.get("id") or "")] = str(product.get("title") or "")
                rows.extend(self._product_rows(builder, product, base, currency, vat_flag, source.default_region))
            if len(products) < PAGE_SIZE:
                break
            page += 1

        # The owner's standing rule: a site that publishes both languages is
        # captured in both. Applied to the rows already built, so a failed
        # English pass costs a note and never a price.
        english = self._english_titles(base, titles, notes)
        if english:
            product_at = builder.header.index("external_product_id")
            english_at = builder.header.index("product_name")
            for row in rows:
                row[english_at] = english.get(row[product_at], "")

        yield ScrapedTable(
            source_key=source.source_key,
            kind=PRODUCT_PRICES.kind,
            source_url=f"{base}/products.json",
            header=builder.header,
            rows=rows,
            warnings=notes,
        )

    def _english_titles(self, base: str, titles: dict[str, str],
                        notes: list[str]) -> dict[str, str]:
        """product id -> English title, or {} when the shop has only one language.

        Joined by id, and kept only where it DIFFERS from the title already
        collected: a shop whose locale prefix simply re-serves its single
        language would otherwise be published as if it had been translated.
        The first page decides whether the rest is worth fetching, so a
        monolingual shop pays one request, not a second full crawl.
        """
        found: dict[str, str] = {}
        page = 1
        while True:
            url = f"{base}/{ENGLISH_LOCALE}/products.json?limit={PAGE_SIZE}&page={page}"
            try:
                products = self._fetcher.get(url).json().get("products", [])
            except CrawlBlocked:
                raise
            except Exception as exc:  # noqa: BLE001 — bilingual is additive
                if page == 1:
                    notes.append(f"{ENGLISH_LOCALE} locale unavailable — names "
                                 f"stay single-language this run: {exc}")
                break
            if not products:
                break
            fresh = 0
            for product in products:
                pid = str(product.get("id") or "")
                title = str(product.get("title") or "")
                if pid and title and title != titles.get(pid, ""):
                    found[pid] = title
                    fresh += 1
            if not fresh:
                break   # this locale says nothing the first pass did not
            if len(products) < PAGE_SIZE:
                break
            page += 1
        return found

    @staticmethod
    def _product_rows(builder, product, base, currency, vat_flag, region) -> list[list[str]]:
        option_names = [opt.get("name", f"option{i}") for i, opt in enumerate(product.get("options", []), start=1)]
        handle = product.get("handle", "")
        rows = []
        for variant in product.get("variants", []):
            options = {}
            for i, name in enumerate(option_names, start=1):
                value = variant.get(f"option{i}")
                if value and value != "Default Title":
                    options[name] = value
            price = variant.get("price")
            compare_at = was_price(variant.get("compare_at_price"), price)
            rows.append(builder.row(
                external_product_id=product.get("id"),
                external_variant_id=variant.get("id"),
                external_sku=variant.get("sku") or "",
                # This store answers in Arabic; the English pass above fills
                # the unmarked column from the same shop's en locale.
                product_name_ar=product.get("title") or "",
                brand_raw=product.get("vendor") or "",
                variant_ar=variant.get("title") if options else "",
                option_fingerprint=option_fingerprint(options) if options else "",
                product_url=f"{base}/products/{handle}" if handle else "",
                region=region,
                currency=currency,
                vat_included=vat_flag,
                regular_price=compare_at or price,
                sale_price=price if compare_at else "",
                effective_price=price,
                availability=_availability(variant),
                stock_quantity="",
            ))
        return rows


def was_price(compare_at, price) -> str:
    """The genuine "was" price, or "" when the variant is not on sale.

    Shopify writes compare_at_price as a STRING, and a shop that has cleared a
    sale often leaves "0.00" behind rather than null. "0.00" is a non-empty
    string, so the previous `compare_at or price` selected it and the sale
    branch fired: 44 of 1034 live ELSEWEDYSHOP variants were being published as
    "on sale, was 0.00" — a price movement from zero that never happened.

    A "was" price is only real when it is strictly ABOVE what is being charged;
    equal or lower is not a discount, it is noise or a stale field.
    """
    try:
        was = float(str(compare_at).strip())
        now = float(str(price).strip())
    except (TypeError, ValueError):
        return ""
    return str(compare_at) if was > now else ""


def _availability(variant: dict) -> str:
    available = variant.get("available")
    if available is True:
        return Availability.IN_STOCK.value
    if available is False:
        return Availability.OUT_OF_STOCK.value
    return Availability.UNKNOWN.value
