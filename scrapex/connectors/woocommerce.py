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

import re

from typing import Iterable

from ..config import SourceEntry
from ..normalize import option_axes_json, option_fingerprint
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import DetailGroup, Availability, ExtractKind
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

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
        rows: list[list[str]] = []
        notes: list[str] = []
        fetched: list[dict] = []      # kept so enrichment needs no second fetch

        page = 1
        while True:
            token = f"page-{page}"
            if token in self.skip_tokens:
                page += 1
                continue      # already journaled — never re-asked
            products = self._fetcher.get(endpoint, params={"per_page": PER_PAGE, "page": page}).json()
            if not isinstance(products, list) or not products:
                break
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
            rows.extend(page_rows)
            # One table PER PAGE so a pause keeps what it fetched: the journal
            # stores each as it arrives and the resume starts at the tail.
            yield ScrapedTable(
                source_key=source.source_key, kind=PRODUCT_PRICES.kind,
                source_url=f"{endpoint}?page={page}", header=builder.header,
                rows=page_rows, warnings=notes if page == 1 else [],
                page_token=token,
            )
            if len(products) < PER_PAGE:
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
            # Writing 2,089.78 into effective_price for a product that sells
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
            except Exception as exc:  # noqa: BLE001 — isolate per variation
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
            brand_raw=brand_of(carrier),
            # The PRODUCT's page for the product column, and the VARIATION's own
            # page for the variation — they are different addresses and were
            # sharing one column, so five of every six links opened the wrong
            # colour. (This shop's colour slugs disagree with its colour names:
            # «أحمر» is slug `black`. WooCommerce selects by SLUG, so the link
            # is right and the label is right; do not reconcile them.)
            product_url=carrier.get("permalink") or product.get("permalink") or "",
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
            vat_included=vat,
            regular_price=regular,
            sale_price=sale if (sale and sale != regular) else "",
            effective_price=effective,
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
