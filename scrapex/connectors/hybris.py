"""hybris-occ family connector (ENGINEERING.md A3: proven family).

SAP Commerce (Hybris) exposes the OCC v2 REST API. Its data host DIFFERS from the
storefront base_url (masdar: api.masdaronline.com vs www.masdaronline.com), so this
is the first connector to read SourceEntry.api (the OCC host + baseSite id). Product
search is paginated 0-indexed; one product -> one PRODUCT_PRICES row (v1 is
product-level; baseProduct->variant expansion via the product-detail call is a later
enhancement).

VAT (masdar) — CORRECTED 2026-07-20 by reading the live API. This file used to
claim the search price was VAT-exclusive and that priceWithTax needed a separate
detail call. Both are false: a FULL search response carries price, priceWithTax
and priceWithoutTax together, and price.value equals priceWithTax.value on every
live product (206.99999999999997 inclusive against 180.00 exclusive — exactly
15%). The manifest said excl, so every MASDAR row would have been published with
its VAT flag inverted. The basis is now read FROM THE PAYLOAD rather than taken
on the manifest's word, because the payload cannot be wrong about itself.
"""
from __future__ import annotations

import re
from typing import Iterable

from ..normalize import brand_pair
from ..config import SourceEntry
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, ExtractKind, group_for_code
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

PAGE_SIZE = 100

# OCC states ONE picture several times over, once per rendering size, and says
# which size each is in its own `format` field. Live census 2026-07-30: 560 of
# masdar's 640 priced products carry exactly one PRIMARY picture published as
# thumbnail + product + zoom (1,680 entries, 560 pictures), and the remaining
# 80 publish no image at all.
#
# Storing all three would assert the product has three pictures, which is a
# claim the site never made — so one picture becomes one row, at the largest
# rendering the site offers. The preference is the site's OWN format names, not
# a size parsed out of the URL; a format this list does not know keeps whatever
# was seen first rather than being dropped.
_FORMAT_PREFERENCE = ("zoom", "product", "thumbnail")

# The size the rendering is named after prefixes the filename
# ("96Wx96H-1000061922-1200Wx1200H-0.jpg"). Stripping it is what identifies the
# three renderings as ONE picture; a name that does not match is left whole, so
# an unrecognised shape degrades into separate rows rather than a wrong merge.
_SIZE_PREFIX = re.compile(r"^\d+Wx\d+H-")

# The language the price rows are collected in, and the one the bilingual rule
# asks for beside it. OCC takes `lang` per request and masdar's own
# /languages endpoint lists both as active (read live 2026-07-23), so the
# English pass is attempted only when the STORE says it publishes English —
# never as a standing assumption about SAP Commerce.
PRIMARY_LANG = "ar"
ENGLISH_LANG = "en"

# OCC stockLevelStatus -> our vocabulary. lowStock is still purchasable (in_stock).
_STOCK = {
    "inStock": Availability.IN_STOCK.value,
    "lowStock": Availability.IN_STOCK.value,
    "outOfStock": Availability.OUT_OF_STOCK.value,
}


def _vat_basis(product: dict, default: str) -> str:
    """'1' when the price we take includes tax, '0' when it does not.

    Decided from the payload wherever the API states both figures, and only
    falling back to the manifest's claim when it does not. The manifest declared
    masdar exclusive while its API returns price == priceWithTax on every
    product — a flag inverted on ~1,354 products, and nothing in the pipeline
    could have noticed, because a VAT flag is carried, never checked.
    """
    value = (product.get("price") or {}).get("value")
    with_tax = (product.get("priceWithTax") or {}).get("value")
    without_tax = (product.get("priceWithoutTax") or {}).get("value")
    try:
        if value is not None and with_tax is not None and float(value) == float(with_tax):
            return "1"
        if value is not None and without_tax is not None and float(value) == float(without_tax):
            return "0"
    except (TypeError, ValueError):
        pass
    return default


def _money(value) -> str:
    """A price as the site means it, not as binary floating point renders it.

    OCC serves 206.99999999999997 for a 207.00 price. Passing that straight
    through publishes a number no human sees on the site, and it defeats the
    price-key's scale-invariance, which folds 0.620 and 0.62 but not this.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    # Minimal representation: 206.99999999999997 -> "207", 25.5 -> "25.5",
    # 320.2865 -> "320.29". Trailing zeros are not added, because the shape of
    # the string is not ours to invent — only the binary artefact is ours to remove.
    return f"{round(number, 2):.2f}".rstrip("0").rstrip(".")


def _availability(stock: dict) -> str:
    return _STOCK.get(stock.get("stockLevelStatus"), Availability.UNKNOWN.value)


def _occ_root(source: SourceEntry) -> str:
    api = source.api
    if api is None or not api.base_url or not api.base_site:
        raise ValueError(
            f"{source.source_key}: hybris-occ needs api.base_url + api.base_site "
            "(the OCC host and baseSite id) in the manifest"
        )
    return f"{api.base_url.rstrip('/')}/rest/v2/{api.base_site}"


def _endpoint(source: SourceEntry) -> str:
    return f"{_occ_root(source)}/products/search"


def _storefront_url(product: dict, display_base: str, lang: str, currency: str) -> str:
    """The page a human can actually open — not the API's bare path.

    The OCC payload states the tail only
    (`/electrical-…/switches-and-sockets/sockets/…/p/1000035833`), and joining
    that straight onto the storefront host returns 404 on EVERY masdar
    product: the storefront files each product under
    /{lang}/{currency}/{sales-unit}/. Verified 2026-07-23 against
    masdaronline's own Product sitemap — the composed URL matched the site's
    canonical URL for all 639 priced products, 0 mismatches, and the composed
    page answers 200 showing the same price the row carries.

    Every part is READ from the payload (the sales unit and the price's own
    currency) or from the language we asked for, so nothing here is invented.
    A product that states no sales unit keeps the plain join rather than a
    guessed prefix.
    """
    url = str(product.get("url") or "")
    if not url:
        return ""
    if url.startswith("http"):
        return url
    unit = str((product.get("salesUnit") or {}).get("unit") or "").strip().lower()
    money = str((product.get("price") or {}).get("currencyIso") or currency).strip().lower()
    prefix = "/".join(part for part in (lang, money, unit) if part) if unit else ""
    tail = url.lstrip("/")
    return f"{display_base}/{prefix}/{tail}" if prefix else f"{display_base}/{tail}"


def _picture_id(url: str) -> str:
    """The identity of the PICTURE, independent of which size is being served."""
    name = url.split("?", 1)[0].rsplit("/", 1)[-1]
    return _SIZE_PREFIX.sub("", name)


def _format_rank(image: dict) -> int:
    fmt = str(image.get("format") or "").strip().lower()
    return _FORMAT_PREFERENCE.index(fmt) if fmt in _FORMAT_PREFERENCE \
        else len(_FORMAT_PREFERENCE)


def enrichment_rows(builder: RowBuilder, product: dict,
                    media_base: str) -> list[list[str]]:
    """The product's pictures, from the search payload the price came from.

    The OCC search response has carried `images` all along and this connector
    only ever built PRODUCT_PRICES rows, so MASDAR published 0 pictures for a
    catalogue that publishes 560.

    The URLs are stated RELATIVE ("/medias/…"), and they resolve on the OCC API
    host, not the storefront: HEAD on api.masdaronline.com answers 200
    image/jpeg where www.masdaronline.com answers 404 (checked 2026-07-30).
    Making them absolute against the host that actually serves them is the only
    rewriting done here — the path, filename and `?context=` token are the
    site's and are passed through untouched.
    """
    code = str(product.get("code") or "")
    if not code:
        return []

    # One entry per picture, keeping the largest rendering of each.
    best: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for image in product.get("images") or []:
        if not isinstance(image, dict):
            continue
        href = str(image.get("url") or "").strip()
        if not href:
            continue
        key = (str(image.get("imageType") or ""), _picture_id(href))
        if key not in best:
            best[key] = image
            order.append(key)
        elif _format_rank(image) < _format_rank(best[key]):
            best[key] = image

    rows: list[list[str]] = []
    for position, key in enumerate(order):
        image = best[key]
        href = str(image.get("url") or "").strip()
        absolute = href if href.startswith("http") else f"{media_base}{href}"
        # Files are language-neutral, so `lang` stays unstated even though the
        # payload was asked for in Arabic. OCC states no alt text, so the
        # filename stands in as the panel's alternative text.
        attribute_code = f"image_{position}" if position else "image"
        group, _recognised = group_for_code(attribute_code)
        rows.append(builder.row(
            external_product_id=code, attribute_code=attribute_code,
            attribute_label="Image",
            raw_value=href.split("?", 1)[0].rsplit("/", 1)[-1],
            numeric_value="", unit_raw="", value_url=absolute, lang="",
            attribute_group=group))
    return rows


class HybrisOccConnector:
    connector_id = "hybris-occ"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher
        # Pages already journaled by a paused attempt (capture sets this).
        self.skip_tokens: set[str] = set()

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        endpoint = _endpoint(source)
        display_base = source.base_url.rstrip("/")
        vat = "1" if source.vat_mode.value == "incl" else "0"
        currency = source.currency or "UNKNOWN"
        rows: list[list[str]] = []
        notes: list[str] = []
        unpriced = 0
        # The pictures ride the SAME search response the prices come from, so
        # they cost no extra request — but only when the manifest asks, because
        # ingest refuses an enrichment payload from a source that does not
        # declare the kind.
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        media_base = (source.api.base_url.rstrip("/")
                      if source.api and source.api.base_url else display_base)

        # The owner's standing rule: what a source publishes in both languages
        # is captured in both. Done FIRST so the price pass can build complete
        # rows, and best-effort throughout — an English pass that fails costs a
        # note, never the prices.
        names_en = self._english_names(source, endpoint, notes)

        page = 0
        skipped = 0
        while True:
            token = f"page-{page}"
            if token in self.skip_tokens:
                # BEFORE the request. The English names were already fetched
                # above the loop, so a page can be yielded on its own — which
                # is what makes this connector resumable at all.
                skipped += 1
                page += 1
                continue
            body = self._search(endpoint, page, PRIMARY_LANG)
            products = body.get("products") or []
            page_builder = RowBuilder(PRODUCT_PRICES)
            page_rows: list[list[str]] = []
            page_detail = RowBuilder(ENRICHMENT)
            page_detail_rows: list[list[str]] = []
            for product in products:
                row = self._row(page_builder, product, display_base, currency, vat,
                                source.default_region,
                                names_en.get(str(product.get("code") or "")) or "")
                if row is None:
                    unpriced += 1
                    continue
                page_rows.append(row)
                if wants_enrichment:
                    # Only for a product that earned a price row: an unpriced
                    # product is skipped entirely, and filing its picture would
                    # put an attribute in the warehouse for a product the price
                    # pass never landed.
                    page_detail_rows.extend(
                        enrichment_rows(page_detail, product, media_base))
            if page_rows:
                # Journaled as fetched: this used to accumulate the whole
                # catalogue and yield once, so an interrupted crawl wrote
                # nothing at all.
                yield ScrapedTable(
                    source_key=source.source_key, kind=PRODUCT_PRICES.kind,
                    source_url=endpoint, header=page_builder.header,
                    rows=page_rows, page_token=token)
            if page_detail_rows:
                # The SAME token as the prices above: one page is journaled
                # once, so a resume cannot land a page's prices without its
                # pictures — the rule salla already follows per product.
                yield ScrapedTable(
                    source_key=source.source_key, kind=ENRICHMENT.kind,
                    source_url=endpoint, header=page_detail.header,
                    rows=page_detail_rows, page_token=token)
            total_pages = (body.get("pagination") or {}).get("totalPages")
            page += 1
            if not products:
                break
            if total_pages is not None:
                if page >= int(total_pages):
                    break
            elif len(products) < PAGE_SIZE:  # safety net if pagination block is absent
                break

        # 714 of masdar's 1353 products answer price: null (verified live
        # 2026-07-23 — they are also absent from the storefront's own sitemap,
        # so they really are off sale). Skipping them is right; skipping them
        # in silence made a half-catalogue crawl look like a whole one.
        if unpriced:
            notes.append(
                f"{unpriced} product(s) publish no price at all (inactive or "
                "login-gated) — skipped, never guessed")
        if skipped:
            notes.append(f"{skipped} page(s) were already journaled by a paused "
                         "run and were not fetched again")

        if notes:
            # Untokenized: the counts describe THIS attempt, so capture drops
            # them on resume and a resumed run reports its own.
            yield ScrapedTable(
                source_key=source.source_key, kind=PRODUCT_PRICES.kind,
                source_url=endpoint, header=builder.header, rows=[],
                warnings=notes,
            )

    def _search(self, endpoint: str, page: int, lang: str) -> dict:
        return self._fetcher.get(endpoint, params={
            "fields": "FULL", "pageSize": PAGE_SIZE, "currentPage": page,
            "query": ":relevance", "lang": lang,
        }).json() or {}

    def _english_names(self, source: SourceEntry, endpoint: str,
                       notes: list[str]) -> dict[str, str]:
        """product code -> English name, or {} when the store has no English.

        Joined by CODE, never by position: two `:relevance` searches are not
        guaranteed to order the catalogue identically, so pairing page N of one
        pass with page N of the other would attach the wrong name to a product.
        """
        if ENGLISH_LANG not in self._languages(source, notes):
            return {}
        names: dict[str, str] = {}
        try:
            page = 0
            while True:
                body = self._search(endpoint, page, ENGLISH_LANG)
                products = body.get("products") or []
                for product in products:
                    code = str(product.get("code") or "")
                    if code and product.get("name"):
                        names[code] = str(product["name"])
                total_pages = (body.get("pagination") or {}).get("totalPages")
                page += 1
                if not products:
                    break
                if total_pages is not None:
                    if page >= int(total_pages):
                        break
                elif len(products) < PAGE_SIZE:
                    break
        except CrawlBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 — bilingual is additive, prices are vital
            notes.append("english-names pass failed — names stay "
                         f"{PRIMARY_LANG}-only this run: {exc}")
            return {}
        return names

    def _languages(self, source: SourceEntry, notes: list[str]) -> set[str]:
        """The isocodes the STORE says it publishes, from OCC's own endpoint.

        Asking costs one request and keeps the second pass evidence-driven: a
        single-language OCC store is never crawled twice on a guess.
        """
        try:
            body = self._fetcher.get(f"{_occ_root(source)}/languages").json() or {}
        except CrawlBlocked:
            raise
        except Exception as exc:  # noqa: BLE001
            notes.append("could not read the store's language list — names "
                         f"stay {PRIMARY_LANG}-only this run: {exc}")
            return set()
        return {str(item.get("isocode") or "").lower()
                for item in body.get("languages") or [] if item.get("active")}

    @staticmethod
    def _row(builder: RowBuilder, product: dict, display_base: str, currency: str,
             vat: str, region: str, name_en: str = ""):
        price = product.get("price") or {}
        value = price.get("value")
        code = str(product.get("code") or "")
        if value in (None, "") or not code:
            return None  # login-gated / unpriced product — skip, don't emit empty required
        # The payload knows whether its own price includes tax; the manifest only
        # claims to. Where the API states both, believe the API — the manifest
        # said 'excl' for a price that equals priceWithTax exactly.
        vat_flag = _vat_basis(product, default=vat)
        stock = product.get("stock") or {}
        level = stock.get("stockLevel")
        name = str(product.get("name") or "")
        return builder.row(
            external_product_id=code,
            external_variant_id=code,  # v1 product-level; baseProduct->variants later
            external_sku=code,
            # The unmarked column is English. `name` is what the store answers
            # in PRIMARY_LANG; the English twin is filled only when the SAME
            # API says something different — a monolingual store repeats
            # itself and repeating it here would fake a translation.
            product_name=name_en if name_en and name_en != name else "",
            product_name_ar=name,
            lang=PRIMARY_LANG,   # not a guess: this is the lang we asked for
            **brand_pair(product.get("manufacturer") or ""),
            product_link=_storefront_url(product, display_base, PRIMARY_LANG, currency),
            country_code_alpha2=region,
            currency=price.get("currencyIso") or currency,
            tax_included=vat_flag,
            price_before=_money(value),
            price_sale="",
            price=_money(value),
            availability=_availability(stock),
            stock_quantity=level if level is not None else "",
        )
