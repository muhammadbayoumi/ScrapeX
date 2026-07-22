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


# Attributes that are NOT details (owner's correction, 2026-07-22): the single
# length term is what one price BUYS — "100 متر" is the selling basis — and the
# brand attribute is the brand, arriving here because the shop fills the
# attribute instead of the Store API's own (empty) brands list. Both are mapped
# to their first-class fields and skipped by enrichment. Multi-term or
# variation-bearing attributes stay details: a length the buyer CHOOSES is a
# variant axis, not one basis.
_LENGTH_ATTRS = {"pa_الطول", "الطول", "pa_length", "length"}
_BRAND_ATTRS = {"pa_الماركة", "الماركة", "pa_الماركه", "pa_brand", "brand"}
_BASIS = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(\S.*)$")


def _single_term(product: dict, wanted: set) -> str:
    """The one term of a non-variation attribute named in `wanted`, or ""."""
    for attribute in product.get("attributes") or []:
        code = str(attribute.get("taxonomy") or "").strip().lower()
        name = str(attribute.get("name") or "").strip().lower()
        if code not in wanted and name not in wanted:
            continue
        terms = attribute.get("terms") or []
        if len(terms) == 1 and not attribute.get("has_variations"):
            return str(terms[0].get("name") or "").strip()
    return ""


def selling_basis(product: dict) -> tuple[str, str]:
    """(basis_quantity, unit) from the single length attribute — else ("", "")."""
    value = _single_term(product, _LENGTH_ATTRS)
    found = _BASIS.match(value) if value else None
    if not found:
        return "", ""
    return found.group(1).replace(",", "."), found.group(2).strip()


def brand_of(product: dict) -> str:
    """The Store API's brands list first; the shop's brand ATTRIBUTE second."""
    for brand in product.get("brands") or []:
        name = str(brand.get("name") or "").strip()
        if name:
            return name
    return _single_term(product, _BRAND_ATTRS)


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
        basis, unit = selling_basis(product)
        return builder.row(
            external_product_id=pid,
            external_variant_id=pid,  # v1: product-level; per-variation prices later
            external_sku=product.get("sku") or "",
            product_name=product.get("name") or "",
            brand_raw=brand_of(product),
            product_url=product.get("permalink") or "",
            unit=unit,
            basis_quantity=basis,
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

    basis, _unit = selling_basis(product)
    for attribute in product.get("attributes") or []:
        # `taxonomy` is the stable machine key ("pa_color"); `name` is what the
        # shop prints and can be renamed at any time. Keying on the label would
        # make a rename look like a new attribute.
        code = str(attribute.get("taxonomy") or attribute.get("name") or "").strip()
        label = str(attribute.get("name") or code)
        lowered = code.lower()
        named = str(attribute.get("name") or "").strip().lower()
        # Mapped to first-class fields (owner's correction): the single length
        # term is the selling BASIS and rides the price row's unit; the brand
        # attribute rides brand_raw. Repeating them here would be the same fact
        # filed twice under two names.
        if basis and (lowered in _LENGTH_ATTRS or named in _LENGTH_ATTRS):
            continue
        if (lowered in _BRAND_ATTRS or named in _BRAND_ATTRS) and                 len(attribute.get("terms") or []) == 1:
            continue
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
