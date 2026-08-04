"""shopify-json family connector (ENGINEERING.md A3: proven family).

Every Shopify storefront exposes /products.json — paginated, structured
products + variants + prices. One variant -> one product_prices row, built
against the canonical RowSpec (never hardcoded column order, Q2).
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..normalize import brand_pair, option_axes_json, option_fingerprint
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, ExtractKind, group_for_code
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

PAGE_SIZE = 250  # Shopify hard max per page

# Shopify serves a translated catalogue under a locale prefix when the shop
# publishes one. elsewedyshop declares ar + en (hreflang on its own homepage)
# and /en/products.json answers with the English titles for the SAME ids —
# verified live 2026-07-23. The prefix is TRIED, never assumed: a shop with one
# language answers the same titles and this adds nothing to the rows.
ENGLISH_LOCALE = "en"


def _root_title(title: str, language: str) -> dict[str, str]:
    """The root locale's title, in the column that names its language.

    Two columns, and which one is not a detail: an unmarked column is English
    by the project's root rule and the _ar one is the site's own Arabic. Put
    the wrong one in and the AR|EN switch shows a reader English under a
    heading that says Arabic, which is worse than a blank.
    """
    return {"product_name": title} if language == "en" else {"product_name_ar": title}


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
        # The pictures ride the SAME /products.json the prices come from, so
        # capturing them costs no extra request — but only when the manifest
        # asks, because ingest refuses an enrichment payload from a source
        # that does not declare the kind.
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        detail = RowBuilder(ENRICHMENT)
        detail_rows: list[list[str]] = []

        page = 1
        while True:
            url = f"{base}/products.json?limit={PAGE_SIZE}&page={page}"
            products = self._fetcher.get(url).json().get("products", [])
            if not products:  # explicit stop: empty page ends pagination (Q4)
                break
            for product in products:
                titles[str(product.get("id") or "")] = str(product.get("title") or "")
                rows.extend(self._product_rows(builder, product, base, currency, vat_flag,
                                               source.default_region,
                                               source.default_language))
                if wants_enrichment:
                    detail_rows.extend(enrichment_rows(detail, product))
            if len(products) < PAGE_SIZE:
                break
            page += 1

        # The owner's standing rule: a site that publishes both languages is
        # captured in both. Applied to the rows already built, so a failed
        # English pass costs a note and never a price.
        # The second language is whatever the root is NOT. A shop serving
        # English at its root has no /en to fetch — that URL 404s on
        # spark-eshop — and asking for it was how an English shop ended up
        # with an empty English column.
        other_locale = "ar" if source.default_language == "en" else ENGLISH_LOCALE
        other = self._other_locale_titles(base, other_locale, titles, notes)
        if other:
            product_at = builder.header.index("external_product_id")
            other_at = builder.header.index(
                "product_name_ar" if source.default_language == "en" else "product_name")
            for row in rows:
                row[other_at] = other.get(row[product_at], "")

        yield ScrapedTable(
            source_key=source.source_key,
            kind=PRODUCT_PRICES.kind,
            source_url=f"{base}/products.json",
            header=builder.header,
            rows=rows,
            warnings=notes,
        )

        if detail_rows:
            yield ScrapedTable(
                source_key=source.source_key,
                kind=ENRICHMENT.kind,
                source_url=f"{base}/products.json",
                header=detail.header,
                rows=detail_rows,
            )

    def _other_locale_titles(self, base: str, locale: str, titles: dict[str, str],
                             notes: list[str]) -> dict[str, str]:
        """product id -> the title in the shop's OTHER locale, or {}.

        Joined by id, and kept only where it DIFFERS from the title already
        collected: a shop whose locale prefix simply re-serves its single
        language would otherwise be published as if it had been translated.
        The first page decides whether the rest is worth fetching, so a
        monolingual shop pays one request, not a second full crawl.
        """
        found: dict[str, str] = {}
        page = 1
        while True:
            url = f"{base}/{locale}/products.json?limit={PAGE_SIZE}&page={page}"
            try:
                products = self._fetcher.get(url).json().get("products", [])
            except CrawlBlocked:
                raise
            except Exception as exc:  # noqa: BLE001 — bilingual is additive
                if page == 1:
                    notes.append(
                        f"{locale} locale unavailable — every name stays in the "
                        f"{'product_name' if locale == 'ar' else 'product_name_ar'} "
                        f"column this run: {exc}")
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
    def _product_rows(builder, product, base, currency, vat_flag, region,
                      language: str = "ar") -> list[list[str]]:
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
                # The root locale's title goes in ITS OWN column, not always
                # the Arabic one. shopify had "ar" written in as an assumption,
                # and a shop serving English at its root then filed 1,789
                # English titles as Arabic while the English column — the one
                # config calls required — stayed empty on every product.
                **_root_title(product.get("title") or "", language),
                **brand_pair(product.get("vendor") or ""),
                variant_ar=variant.get("title") if options else "",
                # The axes as STRUCTURE beside the sentence built from them
                # (B11). "Color: Red" welded into one cell cannot be filtered,
                # grouped or pivoted, which is the only reason a column exists —
                # and splitting the string at the far end is the fix the owner
                # explicitly refused. Shopify names its own axes in
                # `options[].name`, so nothing is inferred.
                variant_axes_ar=option_axes_json(options) if options else "",
                option_fingerprint=option_fingerprint(options) if options else "",
                product_link=f"{base}/products/{handle}" if handle else "",
                # Each variation's OWN link. Shopify selects a variation by
                # query parameter, so all of them shared the product's URL and
                # every one but the default pointed at the wrong thing.
                variant_url=(f"{base}/products/{handle}?variant={variant.get('id')}"
                             if handle and variant.get("id") and options else ""),
                # The PRODUCT's sku, so a variation's own sku stops standing in
                # for its parent's.
                parent_sku=str(product.get("sku") or ""),
                country_code_alpha2=region,
                currency=currency,
                tax_included=vat_flag,
                price_before=compare_at or price,
                price_sale=price if compare_at else "",
                price=price,
                availability=_availability(variant),
                stock_quantity="",
            ))
        return rows


def enrichment_rows(builder: RowBuilder, product: dict) -> list[list[str]]:
    """The product's pictures, primary first, from the price payload itself.

    /products.json states `images` beside the variants the prices are read
    from — 1,442 pictures across all 932 elsewedyshop products, every one of
    them with a `src` (live census 2026-07-30). The connector kept the prices
    and read straight past the pictures, which is the whole reason this source
    published 0 images while the shop published one for every product.

    `position` is the shop's own gallery ranking and the list arrives in it, so
    the `image`, `image_1`… order is the site's and not a choice made here —
    the convention magento, salla and woocommerce already file under.

    Shopify's products.json carries NO alt text (1,442 of 1,442 are null on
    this shop), so the filename stands in as the panel's alternative text. The
    `?v=` cache-buster is dropped from that LABEL only; value_url keeps the URL
    exactly as published, because the URL is the record.
    """
    pid = str(product.get("id") or "")
    if not pid:
        return []
    rows: list[list[str]] = []
    position = 0
    for image in product.get("images") or []:
        if not isinstance(image, dict):
            continue
        href = str(image.get("src") or "").strip()
        if not href:
            continue
        # Files are language-neutral: a picture is the same fact in either
        # store language, so `lang` stays unstated (0039's carve-out).
        code = f"image_{position}" if position else "image"
        group, _recognised = group_for_code(code)
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code,
            attribute_label="Image",
            raw_value=str(image.get("alt") or "").strip()
                      or href.rsplit("/", 1)[-1].split("?")[0],
            numeric_value="", unit_raw="", value_url=href, lang="",
            attribute_group=group))
        position += 1
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
