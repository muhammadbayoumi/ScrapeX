"""woocommerce-storeapi family connector (ENGINEERING.md A3: proven family).

WooCommerce's Store API (`/wp-json/wc/store/products`) is open JSON, paginated.
Gotcha (handled here): prices are integer strings in MINOR units with a
`currency_minor_unit` (e.g. "1050" + 2 → 10.50). v1 emits one row per product
(product-level price); per-variation prices need extra calls — a later enhancement.
"""
from __future__ import annotations

import re

from typing import Iterable

from ..config import SourceEntry
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, ExtractKind
from .base import HttpFetcher, ScrapedTable

PER_PAGE = 100


def _money(prices: dict, key: str) -> str:
    raw = prices.get(key)
    if raw in (None, ""):
        return ""
    minor = int(prices.get("currency_minor_unit", 2))
    return f"{int(raw) / (10 ** minor):.{minor}f}"


class WooCommerceConnector:
    connector_id = "woocommerce-storeapi"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/wp-json/wc/store/products"
        vat = "1" if source.vat_mode.value == "incl" else "0"
        rows: list[list[str]] = []
        fetched: list[dict] = []      # kept so enrichment needs no second fetch

        page = 1
        while True:
            products = self._fetcher.get(endpoint, params={"per_page": PER_PAGE, "page": page}).json()
            if not isinstance(products, list) or not products:
                break
            fetched.extend(products)
            for p in products:
                row = self._row(builder, p, source, vat)
                if row is not None:
                    rows.append(row)
            if len(products) < PER_PAGE:
                break
            page += 1

        yield ScrapedTable(
            source_key=source.source_key, kind=PRODUCT_PRICES.kind,
            source_url=endpoint, header=builder.header, rows=rows,
        )
        # A SECOND table from the SAME fetch. The attributes, categories, tags,
        # description and measurements were all in the responses already read;
        # emitting them costs no extra request. Only when the manifest asks for
        # them, so a source that wants prices alone is not made to carry them.
        if any(spec.kind == ExtractKind.ENRICHMENT for spec in source.extract):
            extra = RowBuilder(ENRICHMENT)
            attribute_rows: list[list[str]] = []
            for product in fetched:
                attribute_rows.extend(enrichment_rows(extra, product))
            if attribute_rows:
                yield ScrapedTable(
                    source_key=source.source_key, kind=ENRICHMENT.kind,
                    source_url=endpoint, header=extra.header, rows=attribute_rows,
                )

    @staticmethod
    def _row(builder: RowBuilder, product: dict, source: SourceEntry, vat: str):
        prices = product.get("prices") or {}
        effective = _money(prices, "price")
        if not effective:
            return None  # no price — skip
        regular = _money(prices, "regular_price") or effective
        sale = _money(prices, "sale_price")
        pid = str(product.get("id", ""))
        return builder.row(
            external_product_id=pid,
            external_variant_id=pid,  # v1: product-level; per-variation prices later
            external_sku=product.get("sku") or "",
            product_name=product.get("name") or "",
            product_url=product.get("permalink") or "",
            region=source.default_region,
            currency=prices.get("currency_code") or source.currency or "UNKNOWN",
            vat_included=vat,
            regular_price=regular,
            sale_price=sale if (sale and sale != regular) else "",
            effective_price=effective,
            availability=Availability.IN_STOCK.value if product.get("is_in_stock") else Availability.OUT_OF_STOCK.value,
        )


# ---- enrichment: the attributes the same response already carries ------------
#
# Every one of these arrives in the SAME product payload the price comes from —
# attributes with their terms, categories, tags, the description, the weight —
# and the connector was reading past all of it to take four numbers. Emitting
# them costs ZERO additional requests. The owner asked for weight, colours,
# cable type, length, brand, size, application, voltage type and warranty; on
# this platform those are WooCommerce attributes, so they arrive as a set rather
# than as nine hardcoded fields.

def _clean(html: str) -> str:
    """Strip tags from a WooCommerce description without importing a parser.

    Descriptions are attacker-controlled text (spec 34: scraped content is
    untrusted). Storing the raw HTML and letting a template render it later is
    how that becomes an injection; the text is what carries the meaning anyway.
    """
    if not html:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def enrichment_rows(builder: RowBuilder, product: dict) -> list[list[str]]:
    """One row per attribute, category, tag and measurement of one product."""
    pid = str(product.get("id") or "")
    if not pid:
        return []
    rows: list[list[str]] = []

    def add(code, label, value, *, url="", group="", numeric="", unit=""):
        if not value:
            return
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=str(value), numeric_value=str(numeric), unit_raw=unit,
            value_url=url, lang="", attribute_group=group))

    for attribute in product.get("attributes") or []:
        # `taxonomy` is the stable machine key ("pa_color"); `name` is what the
        # shop prints and can be renamed at any time. Keying on the label would
        # make a rename look like a new attribute.
        code = str(attribute.get("taxonomy") or attribute.get("name") or "").strip()
        label = str(attribute.get("name") or code)
        for term in attribute.get("terms") or []:
            add(code, label, term.get("name"), url=term.get("link") or "",
                group="Attributes")

    for category in product.get("categories") or []:
        add("category", "Category", category.get("name"),
            url=category.get("link") or "", group="Classification")
    for tag in product.get("tags") or []:
        add("tag", "Tag", tag.get("name"), url=tag.get("link") or "",
            group="Classification")
    for brand in product.get("brands") or []:
        add("brand", "Brand", brand.get("name"), url=brand.get("link") or "",
            group="Classification")

    # Measurements arrive both raw and formatted. The raw number is kept as the
    # numeric value and the formatted string as what the site actually printed,
    # so nothing has to guess the unit back out of "2.0 kg".
    weight = product.get("weight")
    if weight:
        add("weight", "Weight", product.get("formatted_weight") or weight,
            numeric=weight, group="Measurements")
    dimensions = product.get("dimensions") or {}
    for axis in ("length", "width", "height"):
        if dimensions.get(axis):
            add(axis, axis.title(), dimensions[axis], numeric=dimensions[axis],
                group="Measurements")

    add("description", "Description", _clean(product.get("short_description")),
        group="Description")
    return rows
