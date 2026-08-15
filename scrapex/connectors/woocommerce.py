"""woocommerce-storeapi family connector (ENGINEERING.md A3: proven family).

WooCommerce's Store API (`/wp-json/wc/store/products`) is open JSON, paginated.
Gotcha (handled here): prices are integer strings in MINOR units with a
`currency_minor_unit` (e.g. "1050" + 2 → 10.50).

A VARIABLE product's list entry carries only the price RANGE's low end; each
variation is itself a product at /products/{id}, with its own price, sku and a
human "variation" string ("Color: أرضي"). Verified live on samehgabriel.com
2026-07-22: the parent showed 450.00 while its earth-coloured variation sells
at 2,776.66 — the product-level row was hiding the actual prices. One extra
request per variation buys the real numbers.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import SourceEntry
from ..localinbox import safe_token
from ..normalize import brand_pair, option_axes_json, option_fingerprint, strip_markup
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, DetailGroup, ExtractKind, group_for_code
from .base import CrawlBlocked, HttpFetcher, ScrapedTable, declare_frontier
from .jsonld import (
    WalkTally,
    brand_name,
    category_path,
    offer_price,
    sitemap_locs,
    walk_product_pages,
)
from .jsonld import (
    enrichment_rows as jsonld_enrichment_rows,
)
from .jsonld import (
    product_row as jsonld_product_row,
)

PER_PAGE = 100
_API_HEADERS = {"Accept": "application/json"}
_PAGE_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
_SITEMAP_HEADERS = {"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8"}
_PAGE_FALLBACK_STATUSES = frozenset({400, 401, 403, 404, 405, 406, 410, 414, 422})


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


def _price_span(product: dict) -> tuple[str, str]:
    """The Store API's own (min, max) minor-unit strings, or ("", "").

    WooCommerce populates `prices.price_range` only when the product's price is
    a span — a variable product whose variations differ, a grouped product
    summarising its children. Its absence is the shop saying "one price".
    """
    span = (product.get("prices") or {}).get("price_range") or {}
    if not isinstance(span, dict):
        return "", ""
    return str(span.get("min_amount") or ""), str(span.get("max_amount") or "")


def _is_a_range(product: dict) -> bool:
    low, high = _price_span(product)
    return bool(low) and bool(high) and low != high


def _range_text(product: dict) -> str:
    prices = product.get("prices") or {}
    low, high = _price_span(product)
    minor = int(prices.get("currency_minor_unit", 2) or 0)
    scale = 10 ** minor
    try:
        return f"{int(low) / scale:.{minor}f}..{int(high) / scale:.{minor}f}"
    except (TypeError, ValueError):
        return f"{low}..{high}"


def _money(prices: dict, key: str) -> str:
    raw = prices.get(key)
    if raw in (None, ""):
        return ""
    minor = int(prices.get("currency_minor_unit", 2))
    return f"{int(raw) / (10 ** minor):.{minor}f}"


def _positive_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _site_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".").removeprefix("www.")


def _same_site(url: str, host: str) -> bool:
    return bool(host) and _site_host(url) == host


def _is_product_sitemap(url: str) -> bool:
    name = urlsplit(url).path.rsplit("/", 1)[-1].lower()
    excluded = ("product_cat", "product-tag", "product_tag", "taxonom", "shipping", "pa_")
    return name.endswith(".xml") and "product" in name and not any(
        marker in name for marker in excluded)


def _same_site_products(urls: Iterable[str], host: str,
                        *, trusted_product_map: bool = False) -> list[str]:
    products: list[str] = []
    for url in urls:
        path = urlsplit(url).path.lower()
        if not _same_site(url, host) or path.endswith(".xml"):
            continue
        if trusted_product_map or "/product/" in path:
            products.append(url)
    return list(dict.fromkeys(products))


def _decimal_money(value) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if not amount.is_finite() or amount <= 0:
        return ""
    return format(amount.quantize(Decimal("0.01")), "f")


def _jsonld_product_id(html: str, node: dict, url: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    body_classes = soup.body.get("class", []) if soup.body else []
    for class_name in body_classes:
        found = re.fullmatch(r"postid-(\d+)", str(class_name))
        if found:
            return found.group(1)
    return str(node.get("productID") or node.get("sku")
               or str(node.get("@id") or "").removesuffix("#product") or url)


def _page_variations(html: str) -> tuple[list[dict], dict[str, tuple[str, dict[str, str]]]]:
    """Woo's embedded variations and the page's own labels for their slugs."""
    soup = BeautifulSoup(html, "lxml")
    form = soup.select_one("form.variations_form[data-product_variations]")
    if form is None:
        return [], {}
    try:
        variations = json.loads(str(form.get("data-product_variations") or ""))
    except (json.JSONDecodeError, TypeError):
        return [], {}
    if not isinstance(variations, list):
        return [], {}

    axes: dict[str, tuple[str, dict[str, str]]] = {}
    for select in form.select("select[name]"):
        name = str(select.get("name") or "")
        code = name.removeprefix("attribute_")
        label_tag = form.find("label", attrs={"for": code})
        label = label_tag.get_text(" ", strip=True) if label_tag else code
        values = {str(option.get("value") or ""): option.get_text(" ", strip=True)
                  for option in select.find_all("option")
                  if option.get("value") not in (None, "")}
        axes[name] = (label or code, values)
    return [v for v in variations if isinstance(v, dict)], axes


def _variation_axes_from_page(attributes: dict,
                              labels: dict[str, tuple[str, dict[str, str]]]
                              ) -> dict[str, str]:
    axes: dict[str, str] = {}
    for name, raw in (attributes or {}).items():
        value = str(raw or "").strip()
        if not value:
            continue
        label, choices = labels.get(str(name),
                                    (str(name).removeprefix("attribute_"), {}))
        axes[label] = choices.get(value, value)
    return axes


def _jsonld_has_unsafe_range(offers) -> bool:
    candidates = offers if isinstance(offers, list) else [offers]
    prices = [offer_price(offer)[0] for offer in candidates
              if isinstance(offer, dict)]
    stated = {price for price in prices if price}
    if len(stated) > 1:
        return True
    if isinstance(offers, dict):
        low = str(offers.get("lowPrice") or "")
        high = str(offers.get("highPrice") or "")
        return bool(low and high and low != high)
    return False


def _jsonld_price_rows(builder: RowBuilder, node: dict, html: str, url: str,
                       source: SourceEntry, vat: str,
                       notes: list[str]) -> tuple[list[list[str]], str]:
    """Rows from a Woo product page, preserving live variation ids when stated."""
    pid = _jsonld_product_id(html, node, url)
    variations, labels = _page_variations(html)
    if variations:
        _summary_price, currency, _summary_availability = offer_price(node.get("offers"))
        rows: list[list[str]] = []
        skipped = 0
        for variation in variations:
            effective = _decimal_money(variation.get("display_price"))
            if not effective or not variation.get("variation_is_active", True):
                skipped += 1
                continue
            regular = _decimal_money(variation.get("display_regular_price")) or effective
            axes = _variation_axes_from_page(
                variation.get("attributes") or {}, labels)
            option = ", ".join(f"{name}: {value}" for name, value in axes.items())
            query = urlencode(variation.get("attributes") or {})
            rows.append(builder.row(
                external_product_id=pid,
                external_variant_id=str(variation.get("variation_id") or ""),
                external_sku=str(variation.get("sku") or node.get("sku") or ""),
                product_name_ar=str(node.get("name") or ""),
                **brand_pair(brand_name(node)),
                product_link=url,
                variant_url=f"{url}{'&' if '?' in url else '?'}{query}" if query else url,
                parent_sku=str(node.get("sku") or ""),
                variant_ar=option,
                option_fingerprint=option_fingerprint(axes) if axes else "",
                variant_axes_ar=option_axes_json(axes),
                country_code_alpha2=source.default_region,
                currency=currency or source.currency or "UNKNOWN",
                tax_included=vat,
                price_before=regular,
                price_sale=effective if effective != regular else "",
                price=effective,
                availability=(Availability.IN_STOCK.value
                              if variation.get("is_in_stock")
                              else Availability.OUT_OF_STOCK.value),
                category_path_ar=category_path(node),
            ))
        if skipped:
            notes.append(
                f"{skipped} variation(s) on {node.get('name') or url} carried "
                "no active positive price in the page record and were skipped")
        return rows, pid

    if _jsonld_has_unsafe_range(node.get("offers")):
        notes.append(
            f"{node.get('name') or url}: JSON-LD publishes a price range but "
            "no individually identified offers — skipped rather than stored "
            "at the range's low end")
        return [], pid
    row = jsonld_product_row(builder, node, url, source, vat, pid)
    return ([row] if row is not None else []), pid


class WooCommerceConnector:
    connector_id = "woocommerce-storeapi"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher
        # Resume support: the job journal hands back the page tokens it holds
        # and this crawl skips exactly those (same contract GPP established).
        self.skip_tokens: set[str] = set()

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/wp-json/wc/store/products"
        vat = "1" if source.vat_mode.value == "incl" else "0"
        notes: list[str] = []
        fetched: list[dict] = []      # kept so enrichment needs no second fetch

        page = 1
        page_size: int | None = None
        # WHEN THE JSON-LD FALLBACK MAY BE ENTERED, and it is narrower than it
        # looks: only before the API has answered once (`api_started`) and only
        # on a crawl with NOTHING JOURNALLED (`not self.skip_tokens`). Every
        # fallback branch below repeats both halves.
        #
        # THE SECOND HALF IS ABOUT DOUBLE INGESTION, not about caution. The two
        # routes token their pages differently — the API journals `page-1`,
        # `page-2`, …, the fallback journals `safe_token(product_url)`. Neither
        # set can recognise the other, so a journal holding API pages plus a
        # fallback resume would carry the SAME products under two tokens and
        # ingest them twice. `_fetch_jsonld` honours `skip_tokens` for its own
        # tokens, which makes an all-fallback journal resumable — but it cannot
        # tell a `page-3` payload apart from one it has yet to fetch.
        #
        # THE COST IS REAL AND ACCEPTED: a fallback crawl that is interrupted
        # cannot resume. Its next attempt meets the same refusal, finds a
        # non-empty journal, and FAILS rather than falling back again — and it
        # will keep failing until that journal is cleared, which discards the
        # pages it had. Paying that is deliberate: a hard failure is visible and
        # repairable, while a doubled price history is neither.
        api_started = False
        while True:
            token = f"page-{page}"
            if token in self.skip_tokens:
                page += 1
                continue      # already journaled — never re-asked
            # `per_page` is an EFFICIENCY, not part of the answer, so it is named
            # optional: samehgabriel.com answers 200 to this endpoint and 403 to
            # the same endpoint with `?per_page=1` — any value at all. Twelve
            # days of that source were lost to a query string. The fetcher asks
            # again without it and RECORDS that it had to.
            try:
                response = self._fetcher.get_dropping(
                    endpoint, optional=("per_page",),
                    params={"per_page": PER_PAGE, "page": page},
                    headers=_API_HEADERS)
                products = response.json()
            except CrawlBlocked:
                raise
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if (not api_started and not self.skip_tokens
                        and status in _PAGE_FALLBACK_STATUSES):
                    yield from self._fetch_jsonld(
                        source, f"Store API answered HTTP {status} after its "
                        "optional parameters were removed")
                    return
                raise
            except ValueError as exc:
                if not api_started and not self.skip_tokens:
                    yield from self._fetch_jsonld(
                        source, f"Store API returned unreadable JSON ({exc})")
                    return
                raise

            if not isinstance(products, list):
                if not api_started and not self.skip_tokens:
                    yield from self._fetch_jsonld(
                        source, "Store API no longer returned a product array")
                    return
                raise RuntimeError(
                    f"{endpoint}?page={page} returned "
                    f"{type(products).__name__}, not a product array")
            if not products:
                if not api_started and not self.skip_tokens:
                    yield from self._fetch_jsonld(
                        source, "Store API returned an empty first page")
                    return
                break

            api_started = True
            before_notes = len(notes)
            page_rows: list[list[str]] = []
            for p in products:
                made = self._product_rows(builder, p, source, vat, endpoint, notes)
                page_rows.extend(made)
                if made:
                    # Enrichment is keyed to a product the warehouse knows, and
                    # the warehouse learns a product from its PRICE row. Details
                    # for a product we refused to price have nothing to hang on
                    # and arrive as out-of-scope rejects — noise that looks like
                    # a contract breach. What we priced is what we describe.
                    fetched.append(p)
            # One table PER PAGE so a pause keeps what it fetched: the journal
            # stores each as it arrives and the resume starts at the tail.
            yield ScrapedTable(
                source_key=source.source_key, kind=PRODUCT_PRICES.kind,
                source_url=f"{endpoint}?page={page}", header=builder.header,
                rows=page_rows, warnings=notes[before_notes:],
                page_token=token,
            )
            # Prefer the API's own frontier when it states one. The live host
            # that rejects `per_page` still answers X-WP-TotalPages: 2; reading
            # that is stronger than inferring a rule from one page. A shop that
            # omits the header falls back to the observed page size — never the
            # size we asked for, because it may have refused that request.
            announced_pages = _positive_int(
                response.headers.get("X-WP-TotalPages"))
            if announced_pages is not None and page >= announced_pages:
                break
            if page_size is None:
                page_size = len(products)
            if announced_pages is None and len(products) < page_size:
                break
            page += 1
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

    def _fetch_jsonld(self, source: SourceEntry,
                      reason: str) -> Iterable[ScrapedTable]:
        """Fallback to the public product pages when the Store API shape is gone.

        JSON-LD is the stable price summary. WooCommerce's own embedded
        variation record, when present on the SAME page, preserves the numeric
        product/variation ids and the per-colour prices the API normally gives
        us. The route is explicitly a warning: page markup carries fewer
        enrichment facts and costs one request per product.
        """
        base = source.base_url.rstrip("/")
        urls = self._product_urls(base)
        if not urls:
            raise RuntimeError(
                f"{reason}; the JSON-LD fallback could not discover any product "
                f"URLs from robots.txt or the WordPress sitemap indexes at {base}")

        remaining = [url for url in urls if safe_token(url) not in self.skip_tokens]
        declare_frontier(self._fetcher, len(remaining))
        tally = WalkTally()
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        vat = "1" if source.vat_mode.value == "incl" else "0"
        unlanded_notes: list[str] = []

        fallback_warning = (
            f"{reason}; used the site's public product pages instead. Prices "
            "came from Product JSON-LD and WooCommerce's page variation record "
            "when present. This route costs one request per product and its "
            "enrichment is narrower than the Store API.")

        for url, token, html, node in walk_product_pages(
                self._fetcher, urls, self.skip_tokens, safe_token, tally,
                request_kwargs={"headers": _PAGE_HEADERS}):
            builder = RowBuilder(PRODUCT_PRICES)
            page_notes: list[str] = []
            rows, pid = _jsonld_price_rows(
                builder, node, html, url, source, vat, page_notes)
            if not rows:
                tally.priceless += 1
                unlanded_notes.extend(page_notes)
            else:
                yield ScrapedTable(
                    source.source_key, PRODUCT_PRICES.kind, url,
                    builder.header, rows, warnings=page_notes,
                    page_token=token)

            if wants_enrichment and rows:
                extra = RowBuilder(ENRICHMENT)
                details = jsonld_enrichment_rows(extra, node, pid)
                if details:
                    yield ScrapedTable(
                        source.source_key, ENRICHMENT.kind, url,
                        extra.header, details, page_token=token)

        summary = [fallback_warning, *unlanded_notes, *tally.notes()]
        yield ScrapedTable(
            source.source_key, PRODUCT_PRICES.kind, base,
            RowBuilder(PRODUCT_PRICES).header, [], warnings=summary)

    def _product_urls(self, base: str) -> list[str]:
        """Product pages from the site's own sitemap declarations.

        robots.txt leads. WordPress core and the two common plugin filenames
        are fallbacks, tried only until one yields a product frontier.
        """
        roots: list[str] = []
        advertised = getattr(self._fetcher, "sitemap_urls", None)
        if advertised is not None:
            try:
                roots.extend(advertised(base))
            except CrawlBlocked:
                raise
            except Exception:
                pass
        roots.extend([
            f"{base}/wp-sitemap.xml",
            f"{base}/sitemap_index.xml",
            f"{base}/product-sitemap.xml",
        ])
        host = _site_host(base)
        for root in dict.fromkeys(roots):
            locs = self._sitemap_locs(root)
            direct = _same_site_products(
                locs, host, trusted_product_map=_is_product_sitemap(root))
            if direct:
                return direct
            children = [url for url in locs
                        if _same_site(url, host) and _is_product_sitemap(url)]
            for child in children:
                products = _same_site_products(
                    self._sitemap_locs(child), host, trusted_product_map=True)
                if products:
                    return products
        return []

    def _sitemap_locs(self, url: str) -> list[str]:
        try:
            return sitemap_locs(
                self._fetcher.get(url, headers=_SITEMAP_HEADERS).text)
        except CrawlBlocked:
            raise
        except httpx.HTTPStatusError as exc:
            # A missing guessed filename means try the next one. A rate limit or
            # an unhealthy server means stop; probing more paths is extra load,
            # not resilience.
            if exc.response.status_code in _PAGE_FALLBACK_STATUSES:
                return []
            raise

    def _product_rows(self, builder: RowBuilder, product: dict, source: SourceEntry,
                      vat: str, endpoint: str, notes: list[str]) -> list[list[str]]:
        """The rows one catalogue entry is worth: its variations, or itself.

        For a variable product the list entry's price is only the range's low
        end, so the variation rows REPLACE the parent row — emitting both would
        state the same offer twice at two different prices. The parent price
        survives only as a fallback when every variation fetch failed, said out
        loud, because a missing week is honest but a silently thinner catalogue
        is not (Q3)."""
        variation_ids = [str(v.get("id") or "")
                         for v in (product.get("variations") or []) if v.get("id")]
        if not variation_ids:
            # No variations to stand in for it, so this catalogue entry has to
            # answer for itself — and a `grouped` or `external` product often
            # cannot. The Store API says so itself: `prices.price_range` is
            # populated exactly when `prices.price` is the LOW END of a span
            # rather than a price (live proof on this very shop, 2026-07-25:
            # product 9803 carries {"min_amount":"208978","max_amount":"209072"}).
            # Writing 2,089.78 into price for a product that sells
            # from 2,089.78 to 2,090.72 states a price the shop does not quote.
            if _is_a_range(product):
                notes.append(
                    f"{product.get('name')}: a {product.get('type') or 'product'} "
                    f"whose price is a RANGE ({_range_text(product)}) and which "
                    "publishes no variations to price individually — skipped "
                    "rather than stored at the range's low end")
                return []
            row = self._row(builder, product, source, vat)
            return [row] if row is not None else []
        out: list[list[str]] = []
        for vid in variation_ids:
            try:
                child = self._fetcher.get(f"{endpoint}/{vid}").json()
            except CrawlBlocked:
                raise    # the site said no — hundreds more requests is not the answer
            except Exception as exc:
                notes.append(f"{product.get('name')}: variation {vid}: {exc}")
                continue
            row = self._row(builder, child if isinstance(child, dict) else {},
                            source, vat, parent=product)
            if row is not None:
                out.append(row)
        if not out:
            if _is_a_range(product):
                # The fallback was always the range's low end; when the shop
                # states that it IS a range, keeping it says "this costs X"
                # about a product that costs X..Y. A missing week is honest,
                # a wrong price is not.
                notes.append(
                    f"{product.get('name')}: no variation answered with a price "
                    f"and the product-level figure is a RANGE "
                    f"({_range_text(product)}) — skipped rather than stored at "
                    "the range's low end")
                return out
            notes.append(
                f"{product.get('name')}: no variation answered with a price — "
                "the product-level price is kept instead; the shop publishes no "
                "price_range for it, so that low end is the whole range")
            row = self._row(builder, product, source, vat)
            if row is not None:
                out.append(row)
        return out

    @staticmethod
    def _row(builder: RowBuilder, product: dict, source: SourceEntry, vat: str,
             parent: dict | None = None):
        prices = product.get("prices") or {}
        effective = _money(prices, "price")
        try:
            priced = bool(effective) and float(effective) != 0
        except ValueError:
            priced = False
        if not priced:
            # No price OR price "0" — WooCommerce represents an unpriced
            # variation both ways, and 0.00 entering the table would replace a
            # real range-low fallback, poison Min, and silently skip the
            # say-it-out-loud path (found by the adversarial review).
            return None
        regular = _money(prices, "regular_price") or effective
        sale = _money(prices, "sale_price")
        pid = str((parent or product).get("id", ""))
        # Variation payloads arrive with attributes:[] (verified live), so the
        # selling basis and the brand always come from the CARRIER of the
        # attributes — the parent when there is one.
        carrier = parent or product
        basis, unit = selling_basis(carrier)
        # "Color: أرضي" — the site's own words for which variation this is.
        option = str(product.get("variation") or "").strip()
        axes = _variation_axes(option)
        return builder.row(
            external_product_id=pid,
            external_variant_id=str(product.get("id", "")),
            external_sku=product.get("sku") or carrier.get("sku") or "",
            # This shop publishes ONE language, Arabic. It fills only the
            # marked column and leaves the English one empty — the heading
            # then says which language the reader is looking at, which is the
            # owner's rule. Moving the value to product_name would rename
            # everything and fix nothing.
            product_name_ar=product.get("name") or carrier.get("name") or "",
            **brand_pair(brand_of(carrier)),
            # The PRODUCT's page for the product column, and the VARIATION's own
            # page for the variation — they are different addresses and were
            # sharing one column, so five of every six links opened the wrong
            # colour. (This shop's colour slugs disagree with its colour names:
            # «أحمر» is slug `black`. WooCommerce selects by SLUG, so the link
            # is right and the label is right; do not reconcile them.)
            product_link=carrier.get("permalink") or product.get("permalink") or "",
            variant_url=(product.get("permalink") or "") if parent else "",
            parent_sku=str(carrier.get("sku") or ""),
            variant_ar=option,
            option_fingerprint=option_fingerprint(axes) if axes else "",
            # The SAME axes as structure. They were parsed already, for the
            # fingerprint, and then thrown away — so the warehouse kept
            # "Color: أحمر" as one string and an export could not split it into
            # the two columns it is (the owner's report, fixed at the root
            # rather than by cutting the string at the far end).
            variant_axes_ar=option_axes_json(axes),
            unit=unit,
            basis_quantity=basis,
            country_code_alpha2=source.default_region,
            currency=prices.get("currency_code") or source.currency or "UNKNOWN",
            tax_included=vat,
            price_before=regular,
            price_sale=sale if (sale and sale != regular) else "",
            price=effective,
            availability=Availability.IN_STOCK.value if product.get("is_in_stock") else Availability.OUT_OF_STOCK.value,
        )


def _variation_axes(text: str) -> dict[str, str]:
    """"Color: أرضي, Size: L" -> {"Color": "أرضي", "Size": "L"}.

    The parsed axes feed the option fingerprint so the SAME choice keeps the
    same identity across crawls even if the site reorders the string."""
    axes: dict[str, str] = {}
    for part in (text or "").split(","):
        key, _, value = part.partition(":")
        if key.strip() and value.strip():
            axes[key.strip()] = value.strip()
    return axes


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
    return strip_markup(html)


# Arabic letters, including the Supplement and the presentation forms a shop
# can emit. Used to read the LANGUAGE OF A VALUE, which is the only language
# evidence a WooCommerce Store API response carries.
_ARABIC_TEXT = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def enrichment_rows(builder: RowBuilder, product: dict) -> list[list[str]]:
    """One row per attribute, category, tag and measurement of one product."""
    pid = str(product.get("id") or "")
    if not pid:
        return []
    rows: list[list[str]] = []

    def add(code, label, value, *, url="", group="", numeric="", unit=""):
        if not value:
            return
        # THE CODE STATES THE LANGUAGE OF ITS CONTENT (0039): the unmarked name
        # is the non-Arabic one, `_ar` marks Arabic, and `lang` says the same in
        # the column the migrations read. This path used to pass lang="" and the
        # site's raw taxonomy, so 252 Arabic facts were stored under UNMARKED
        # codes — which under the convention ASSERTS they are English.
        #
        # Woo carries no store view and no locale header, which is why 0039 and
        # 0045 both deferred this. The evidence that does exist is the VALUE's
        # own script, and it is honest evidence: «مجدول» is Arabic whatever the
        # shop's headers say. Marking only what is demonstrably Arabic claims
        # nothing extra — a Latin or numeric value keeps the unmarked code,
        # which is already the right one for it.
        #
        # Language-NEUTRAL facts are excluded, the same carve-out 0045 made for
        # madar: a weight's fact is its numeric_value and "3,8 كيلوجرام" is only
        # how this shop renders it, and a file is a file. Marking those would
        # also silently break `weight`'s owner promotion, which keys on the code.
        base = code.removesuffix("_ar")
        neutral = base == "weight" or base.startswith("image")
        arabic = bool(_ARABIC_TEXT.search(str(value))) and not neutral
        if arabic and not code.endswith("_ar"):
            code = f"{code}_ar"
        # The shared map decides WHERE (vocab.group_for_code), so every
        # source files the same kind of fact in the same place. It strips the
        # language mark itself, so a marked code files exactly where its
        # unmarked twin does. The caller's `group` remains the hint for codes
        # this shop names in a way the map has not been taught yet.
        decided, recognised = group_for_code(code)
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=str(value), numeric_value=str(numeric), unit_raw=unit,
            value_url=url, lang="ar" if arabic else "",
            attribute_group=decided if recognised else (group or decided)))

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
                group=DetailGroup.SPECIFICATIONS)

    for category in product.get("categories") or []:
        add("category", "Category", category.get("name"),
            url=category.get("link") or "", group=DetailGroup.MORE_INFORMATION)
    for tag in product.get("tags") or []:
        add("tag", "Tag", tag.get("name"), url=tag.get("link") or "",
            group=DetailGroup.MORE_INFORMATION)
    for brand in product.get("brands") or []:
        add("brand", "Brand", brand.get("name"), url=brand.get("link") or "",
            group=DetailGroup.MORE_INFORMATION)

    # The product's pictures, primary first. The Store API states them in
    # `images` and the shop's own gallery order IS that list's order, so the
    # position is the site's ranking, not a number we chose — the same
    # convention magento and salla already file under (`image`, then `image_1`…).
    #
    # This costs no extra request: the `images` list is in the same payload the
    # price came from. The panel uses raw_value as the image alternative text,
    # so the shop's `alt` wins, followed by its attachment name and filename.
    # A picture without `src` is skipped rather than pointed at a guessed URL.
    #
    # Files are language-neutral by the carve-out in `add`: an Arabic caption
    # does not make the picture itself an Arabic-only fact.
    for position, image in enumerate(product.get("images") or []):
        if not isinstance(image, dict):
            continue
        href = str(image.get("src") or "").strip()
        if not href:
            continue
        add(f"image_{position}" if position else "image", "Image",
            str(image.get("alt") or "").strip()
            or str(image.get("name") or "").strip()
            or href.rsplit("/", 1)[-1],
            url=href, group=DetailGroup.MEDIA)

    # Measurements arrive both raw and formatted. The raw number is kept as the
    # numeric value and the formatted string as what the site actually printed,
    # so nothing has to guess the unit back out of "2.0 kg".
    weight = product.get("weight")
    if weight:
        add("weight", "Weight", product.get("formatted_weight") or weight,
            numeric=weight, group=DetailGroup.SPECIFICATIONS)
    dimensions = product.get("dimensions") or {}
    for axis in ("length", "width", "height"):
        if dimensions.get(axis):
            add(axis, axis.title(), dimensions[axis], numeric=dimensions[axis],
                group=DetailGroup.SPECIFICATIONS)

    add("description", "Description", _clean(product.get("short_description")),
        group=DetailGroup.DESCRIPTION)
    return rows
