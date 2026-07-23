"""custom-json-api family connector (ENGINEERING.md A3: proven family).

sikaegshop is a custom Next.js shop exposing an open, unauthenticated
GET /api/products. VERIFIED against the live API on 2026-07-20: 87 products
across 8 pages of 12, Arabic + English names. One product -> one PRODUCT_PRICES
row.

This connector was originally written without ever calling the real endpoint,
against a hand-authored fixture, and every structural assumption in it was wrong:

  - the envelope is {success, data[], pagination{}}, not {products[]}
  - the fields are product_id / product_arname / product_enname, not
    id / name_ar / name_en, and there is no sku, slug, brand or url at all
  - the response is PAGED: reading one page would have captured 12 of 87

The result was not an error. `data.get("products")` returned None, the loop ran
zero times, and the crawl printed "0 rows" as a success. That is why the source
looked broken while the site was up the whole time.

PRICE SEMANTICS — verified across all 87 live products, no longer assumed:
`price` is the list price (never null, never 0) AND what the storefront
charges. `specail_price` (the store's
own spelling) is the discounted price and is set on 78 of 87. `sale_price`
exists in the schema but is null on every product. `flash_sale_price` is a
nullable NUMBER, not the boolean flag this file used to assume — it is null on
all 87 today, so it is read as the effective price when present and cannot be
verified further until the store actually runs a flash sale.
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, ExtractKind
from .base import HttpFetcher, ScrapedTable

# A page is 12 products; 8 pages today. This cap is a runaway guard, not a
# limit — it sits far above the real page count so a pagination bug cannot spin.
_MAX_PAGES = 100


def _num(value) -> float | None:
    """A positive number, or None (0 / null / non-numeric all mean 'no price')."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _fmt(n: float | None) -> str:
    if n is None:
        return ""
    return str(int(n)) if float(n).is_integer() else str(n)


def _prices(product: dict) -> tuple[str, str, str]:
    """(regular, sale, effective) as strings — see PRICE SEMANTICS in the docstring.

    CORRECTED 2026-07-23 against the live storefront. `specail_price` is a
    STANDING COLUMN, not proof of a live discount: product 235 still publishes
    specail_price 939.38 while the shop's own page renders 1252.50 — the
    listing price — so honouring it invented a discount the shop does not
    offer, and no re-crawl could clear it because the field never changed.

    A flash sale IS dated and live, so `flash_sale_price` (with its sibling
    fields) remains the discount. The standing special travels to enrichment
    as what it is: a number the shop keeps, not a price it charges.
    """
    regular = _num(product.get("price"))
    flash = _num(product.get("flash_sale_price"))
    if regular is None:               # a flash price alone can still be the price
        regular = flash
    if regular is None:
        return "", "", ""
    on_sale = flash is not None and flash < regular
    effective = flash if on_sale else regular
    return _fmt(regular), _fmt(effective if on_sale else None), _fmt(effective)


def _availability(product: dict) -> str:
    """Stock first, then the active flag. `is_active` is a listing state, not a
    stock level — a live product with zero stock is out of stock, not in it."""
    qty = product.get("stock_quantity", product.get("stock", product.get("quantity")))
    if isinstance(qty, (int, float)) and not isinstance(qty, bool):
        return Availability.IN_STOCK.value if qty > 0 else Availability.OUT_OF_STOCK.value
    flag = product.get("is_active", product.get("in_stock"))
    if isinstance(flag, bool):
        return Availability.IN_STOCK.value if flag else Availability.OUT_OF_STOCK.value
    return Availability.UNKNOWN.value


def _items(payload) -> list:
    """The product list, whatever this shop calls it.

    `data` is what sikaegshop actually returns; the alternatives stay because
    this is a FAMILY connector and a sibling shop may differ. An unrecognised
    shape returns [] here and the caller refuses, rather than reporting an
    empty success.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "products", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _total_pages(payload) -> int:
    if not isinstance(payload, dict):
        return 1
    pagination = payload.get("pagination")
    if not isinstance(pagination, dict):
        return 1
    try:
        return max(1, int(pagination.get("totalPages") or 1))
    except (TypeError, ValueError):
        return 1


class CustomJsonConnector:
    connector_id = "custom-json-api"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/api/products"
        vat = "1" if source.vat_mode.value == "incl" else "0"
        currency = source.currency or "UNKNOWN"

        first = self._fetcher.get(endpoint).json()
        # COPY: _items returns the list inside the parsed response, so `+=` below
        # would extend the caller's own payload in place. Each page would then be
        # appended to the list the next page is read from, doubling it every
        # iteration until memory runs out.
        products = list(_items(first))
        if not products:
            # The whole point of this rewrite: an unreadable response has to be a
            # visible failure, never a quiet zero-row success.
            keys = sorted(first)[:6] if isinstance(first, dict) else type(first).__name__
            raise ValueError(
                f"{endpoint} returned no product list — the response shape has "
                f"changed (top level: {keys})")

        pages = min(_total_pages(first), _MAX_PAGES)
        for page in range(2, pages + 1):
            products += _items(self._fetcher.get(f"{endpoint}?page={page}").json())

        rows: list[list[str]] = []
        seen: set[str] = set()
        id_at = builder.header.index("external_product_id")
        for product in products:
            row = self._row(builder, product, base, currency, vat, source.default_region)
            if row is None:
                continue
            key = row[id_at]
            if key in seen:
                continue   # the catalogue shifting mid-crawl can repeat one across a page edge
            seen.add(key)
            rows.append(row)

        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, endpoint, builder.header, rows)
        # A SECOND table from the SAME responses: descriptions, keywords,
        # weights and image attachments were all read already, so emitting
        # them costs nothing. Only when the manifest declares enrichment.
        if any(spec.kind == ExtractKind.ENRICHMENT for spec in source.extract):
            extra = RowBuilder(ENRICHMENT)
            attribute_rows: list[list[str]] = []
            for product in products:
                attribute_rows.extend(enrichment_rows(extra, product, base))
            if attribute_rows:
                yield ScrapedTable(source.source_key, ENRICHMENT.kind, endpoint,
                                   extra.header, attribute_rows)

    @staticmethod
    def _row(builder: RowBuilder, product: dict, base: str, currency: str, vat: str, region: str):
        regular, sale, effective = _prices(product)
        pid = str(product.get("product_id") or product.get("id") or product.get("sku") or "")
        if not effective or not pid:
            return None  # unpriced or unidentifiable — skip, don't emit empty required
        # /products/{id} verified live on 2026-07-20; /product/{id} returns 404.
        url = str(product.get("url") or "") or f"{base}/products/{pid}"
        if not url.startswith("http"):
            url = f"{base}/{url.lstrip('/')}"
        arabic = str(product.get("product_arname") or product.get("name_ar") or "").strip()
        english = str(product.get("product_enname") or product.get("name_en") or "").strip()
        name = arabic or english or str(product.get("name") or "").strip()
        # The API states the classification per product — both languages and
        # the site's own id (verified live 2026-07-23: product_categories is
        # one object; the arname arrives with stray whitespace). Arabic label
        # first, same preference as the name.
        categories = product.get("product_categories") or {}
        if isinstance(categories, list):
            categories = categories[0] if categories else {}
        category = str(categories.get("category_arname")
                       or categories.get("category_enname") or "").strip()
        category_en = str(categories.get("category_enname") or "").strip()
        category_id = str(categories.get("category_id")
                          or product.get("category_id") or "")
        return builder.row(
            external_product_id=pid, external_variant_id=pid,
            external_sku=str(product.get("sku") or ""), product_name=name,
            product_name_en=english if english != name else "",
            lang="ar" if arabic and name == arabic else ("en" if name == english else ""),
            category_path=category,
            category_path_en=category_en if category_en != category else "",
            category_external_id=category_id if category else "",
            brand_raw=str(product.get("brand") or ""), product_url=url,
            region=region, currency=currency, vat_included=vat,
            regular_price=regular, sale_price=sale, effective_price=effective,
            availability=_availability(product),
        )


# ---- enrichment: the details the same responses already carried --------------
#
# Verified live 2026-07-23: every product carries short_description_ar/_en,
# keywords in both languages, a weight, its category in both languages and an
# attachments list whose entries are the product's images. The owner asked for
# description, specs, attachments and images; this is all of it, and none of it
# costs a request the price crawl did not already make.

def enrichment_rows(builder: RowBuilder, product: dict, base: str) -> list[list[str]]:
    """One row per stated fact about one product, both languages kept apart."""
    pid = str(product.get("product_id") or product.get("id") or "")
    if not pid:
        return []
    rows: list[list[str]] = []

    def add(code, label, value, *, lang="", url="", group="", numeric="", unit=""):
        if not value:
            return
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=str(value).strip(), numeric_value=str(numeric),
            unit_raw=unit, value_url=url, lang=lang, attribute_group=group))

    add("description", "Description", product.get("short_description_ar"),
        lang="ar", group="Description")
    add("description_en", "Description (EN)", product.get("short_description_en"),
        lang="en", group="Description")
    add("keywords", "Keywords", product.get("keywords_ar"), lang="ar",
        group="Description")
    add("keywords_en", "Keywords (EN)", product.get("keywords_en"), lang="en",
        group="Description")
    add("sku", "SKU", product.get("sku"), group="Specs")
    add("weight", "Weight", product.get("weight"), numeric=product.get("weight"),
        unit="kg", group="Specs")
    add("stock_quantity", "Stock quantity", product.get("stock_quantity"),
        numeric=product.get("stock_quantity"), group="Specs")
    # The shop keeps a standing "special price" column its storefront does not
    # charge (proven live). Recorded as the fact it is — a number the shop
    # holds — so nothing is lost and no row calls it a discount.
    add("standing_special_price", "Standing special price (not charged)",
        product.get("specail_price"), numeric=product.get("specail_price"),
        group="Specs")

    for attachment in product.get("attachments") or product.get("product_attachments") or []:
        href = str(attachment.get("file_url") or "")
        if href and not href.startswith("http"):
            href = base.rstrip("/") + "/" + href.lstrip("/")
        kind = str(attachment.get("file_type") or "")
        add("image" if kind.startswith("image/") else "attachment",
            "Image" if kind.startswith("image/") else "Attachment",
            attachment.get("file_name"), url=href, group="Media")
    return rows
