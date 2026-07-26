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

PRICE SEMANTICS — SETTLED 2026-07-23 from the storefront's OWN source, no
longer inferred. `specail_price` (the store's own spelling) is not a dormant
discount and not a dated promotion: it is a CUSTOMER-GROUP (trade/B2B) price,
shown only to a logged-in customer whose `customerTypeId` is 2. See `_prices`
for the rule verbatim and the evidence that pins it.

Field census over all 87 live products (2026-07-23):
  price                87/87 non-null   list price, what the public is charged
  specail_price        78/87 non-null   trade-tier price, always 15-40% below
                                        `price`, never equal, never above
  sale_price            0/87            null on every product
  flash_sale_price      0/87            null today; a live flash sale fills it
  flash_sale_discount   0/87            null today; percent off, badge only
  flash_sale_info       0/87            null today; carries `min_quantity`
  flash_sale_products   0/87            empty list on every product

ScrapeX crawls anonymously, so the trade tier is unreachable BY CONSTRUCTION —
not "until some date". The public price is `price`, unless a flash sale is live.

TWO ENDPOINTS, NOT ONE — 2026-07-25
-----------------------------------
The owner reported the details panel showing a trade price, a weight and two
short descriptions for a product page that prints a Specifications card, two
PDF datasheets, a three-part description and nine photographs. The connector
was not dropping any of that: it never asked for it.

`GET /api/products?page=N` (the list) is a SUMMARY. `GET /api/products/{id}`
(the detail, equally open and unauthenticated) states, in addition:

  full_description_ar / _en        the long DESCRIPTION / USES / CHARACTERISTICS
  product_attribute_assignments    the "Technical Specifications" card, bilingual
  product_attachments              ALL of them — the list publishes only ONE
  sku                              absent from the list endpoint entirely
  dimensions, inventory_balance, min_/max_stock_level, status_id
  product_related_..._idToproducts related products (not captured — see below)

Census over all 87 live products (2026-07-25): the list published 87
attachments, the details publish 737 (535 images + 202 datasheets); 394
attribute assignments over 6 distinct attributes; a full description in both
languages on 87/87; a sku on 87/87. So the panel's gallery held one picture of
nine and no datasheets at all, and `external_sku` was empty for every row.

NOT captured, deliberately: `product_related_..._idToproducts` embeds a FULL
copy of each related product, price included. Those products have their own
rows in this same table — filing a second, instantly-stale copy of a price
inside another product's attribute bag would state the same offer twice.
`status_id` is an internal state id with no published lookup, so its number
means nothing we could write down honestly.

THE SKU, AND THE OWNER'S EXCEPTION — 2026-07-25
-----------------------------------------------
The owner ruled: «موقع سيكا غير مسجل به sku يمكننا اخذ product id كاستثناء» —
sikaegshop registers no SKU, so take the product id instead. That is true of
the endpoint the owner could see, and only that one. Censused over all 87 live
products, both endpoints, before applying it:

  /api/products (list)      sku field ABSENT ENTIRELY  —  0/87
  /api/products/{id}        sku non-empty              — 87/87  ("SK1049")

So the shop does register SKUs; the list simply does not publish them. The rule
that follows is the owner's, narrowed to where it applies:

  - where the shop publishes a real sku, THAT is `external_sku`. We record what
    the source states, and today that is every one of the 87 products.
  - where it publishes none, `external_product_id` stands in — the approved
    exception. It is written in ONE visible place (`_row`) and named as a
    fallback there, so nobody later reads "252" as a SKU the shop printed.

Because the sku lives on the detail endpoint, a prices-only crawl (no
`enrichment` in the manifest) makes no detail request and every row carries the
fallback. That is the deliberate trade: the price table must never depend on an
enrichment declaration to be complete.
"""
from __future__ import annotations

from typing import Iterable

from ..config import SourceEntry
from ..normalize import selling_unit_from
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, ExtractKind
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

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
    """(regular, sale, effective) as strings — the storefront's OWN pricing rule.

    SETTLED 2026-07-23 by reading the shop's client bundle and confirming both
    branches in a live browser. The rule below is transcribed from
    /_next/static/chunks/905ebab0162dcb89.js (and appears byte-identically in
    7f1bf18251165d5e.js and da86854718ac79a7.js — product page, grid card and
    home card, at every price site: headline, strikethrough, "you save",
    add-to-cart and cart total):

        if (flash_sale_price != null && Number(flash_sale_price) > 0)
            return flash_sale_price;                 # (1) a live flash sale
        if (2 === Number(user?.customerTypeId) && Number(specail_price) > 0)
            return specail_price;                    # (2) TRADE TIER ONLY
        return Number(price || 0);                   # (3) everyone else

    `specail_price` is therefore a CUSTOMER-GROUP price, not a dormant discount.
    Branch (2) is gated on the logged-in customer's type, which the shop reads
    from localStorage['sika-user'] (populated by POST /api/auth/login).
    Self-registration assigns customerTypeId 1; type 2 is staff-assigned.

    Proven live on product 235 (API: price 1252.5, specail_price 939.38):
      - anonymous          -> "1252.50 جنيه", no badge, no strikethrough
      - customerTypeId 1   -> "1252.50 جنيه", no badge          (so it is not
                                                                 "any login")
      - customerTypeId 2   -> "سعر خاص" badge, "939.38 جنيه", 1252.50 struck
                              through, "توفر 313.12 جنيه" (= 1252.5 - 939.38)

    There is no date window and no is_active flag anywhere in this: the API has
    no such field (created_at/updated_at are empty objects `{}`), and there is
    no settings/config/flash-sale endpoint (/api/settings, /api/config,
    /api/flash-sale, /api/home all 404; only /api/categories, /api/banners and
    /api/products{,/id} exist). The day the owner "saw discounts" was a session
    holding a type-2 identity, not a promotion that has since expired.

    ScrapeX crawls anonymously and MUST stay on branch (3)/(1): we record what
    the public is charged. `specail_price` travels to enrichment as the
    trade-tier fact it is, so nothing is lost and no row calls it a discount.
    """
    regular = _num(product.get("price"))
    flash = _num(product.get("flash_sale_price"))
    if regular is None:               # a flash price alone can still be the price
        regular = flash
    if regular is None:
        return "", "", ""
    # Branch (1): the shop honours ANY positive flash_sale_price — it does not
    # check that the flash price is lower. We charge what it charges; we only
    # call it a `sale_price` when it genuinely undercuts the list price, so a
    # mispriced flash can never be reported as a discount it is not.
    effective = flash if flash is not None else regular
    # Branch (2) is deliberately absent: unreachable for an anonymous crawl.
    return _fmt(regular), _fmt(effective if effective < regular else None), _fmt(effective)


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


def _detail(payload) -> dict | None:
    """The ONE product object in a detail response, or None if there isn't one.

    sikaegshop answers /api/products/{id} with the bare object — no {success,
    data} envelope, unlike its own list endpoint (verified live 2026-07-25).
    `data` is still unwrapped because this is a FAMILY connector and the list
    endpoint proves the envelope exists in this codebase's world; a shape
    neither branch recognises returns None and the caller records a warning
    rather than treating an unreadable answer as a product with no details.
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("product_id") or payload.get("id"):
        return payload
    inner = payload.get("data")
    if isinstance(inner, dict) and (inner.get("product_id") or inner.get("id")):
        return inner
    return None


def _shape(payload) -> str:
    """What a response looked like, for a warning that has to be actionable."""
    if isinstance(payload, dict):
        return ", ".join(sorted(payload)[:6]) or "{}"
    return type(payload).__name__


def _skipped(product: dict, why: str) -> str:
    """One warning line naming the product AND what is now missing from it.

    "detail failed" alone would leave the owner to work out what a detail even
    carries; a run that quietly thinned one product's record has to say so in
    the terms the record is read in.
    """
    pid = str(product.get("product_id") or product.get("id") or "?")
    name = str(product.get("product_arname") or product.get("product_enname")
               or product.get("name") or "").strip()
    return (f"product {pid}" + (f" ({name})" if name else "") + f": {why} — the "
            "list facts are kept, but its specifications, full description, "
            "extra images, datasheets and sku are missing from this run")


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
        sku_at = builder.header.index("external_sku")
        by_id: dict[str, list[str]] = {}
        for product in products:
            row = self._row(builder, product, base, currency, vat, source.default_region)
            if row is None:
                continue
            key = row[id_at]
            if key in seen:
                continue   # the catalogue shifting mid-crawl can repeat one across a page edge
            seen.add(key)
            rows.append(row)
            by_id[key] = row

        notes: list[str] = []
        extra = RowBuilder(ENRICHMENT)
        detail_rows: list[list[str]] = []

        def price_table() -> ScrapedTable:
            return ScrapedTable(source.source_key, PRODUCT_PRICES.kind, endpoint,
                                builder.header, rows, warnings=notes)

        # A SECOND table, and the only thing that costs extra requests: the
        # per-product detail pass. Only when the manifest declares enrichment,
        # so a source that wants prices alone pays nothing for details.
        if any(spec.kind == ExtractKind.ENRICHMENT for spec in source.extract):
            try:
                detail_rows = self._detail_rows(extra, products, endpoint, base,
                                                by_id, sku_at, notes)
            except CrawlBlocked:
                # Stopping mid-detail must not ALSO throw away the prices we
                # already read. capture.py journals a table the moment it is
                # yielded, so handing the price table over before the stop
                # propagates is the difference between a paused crawl keeping
                # 87 products and losing them to a pause at product 40.
                yield price_table()
                raise
        yield price_table()
        if detail_rows:
            yield ScrapedTable(source.source_key, ENRICHMENT.kind, endpoint,
                               extra.header, detail_rows)

    def _detail_rows(self, builder: RowBuilder, products: list, endpoint: str,
                     base: str, price_rows: dict[str, list[str]], sku_at: int,
                     notes: list[str]) -> list[list[str]]:
        """One GET per product: the enrichment the LIST endpoint does not carry.

        87 products = 87 extra requests through the shared HttpFetcher (rate
        limited, retrying, robots-aware), roughly a minute and a half at its
        1 req/s. That is the honest cost of the data and it is acceptable for a
        daily crawl of an 87-product shop: the list publishes one attachment of
        eleven, no attributes, no full description and no sku, so there is no
        cheaper way to have any of them. A shop an order of magnitude larger
        would need this pass reconsidered — it scales with the catalogue.

        A detail that fails is isolated to its own product: the crawl carries
        on, the LIST facts for that product are still emitted, and a warning
        names what was lost (Q3 — carrying on is right, hiding it is not).
        CrawlBlocked is re-raised untouched: it carries both the site's own
        refusal and the owner's Pause/Cancel (CrawlInterrupted), and neither of
        those is answered by making 86 more requests.
        """
        rows: list[list[str]] = []
        asked: set[str] = set()
        for product in products:
            pid = str(product.get("product_id") or product.get("id") or "")
            # Details are keyed to a product the WAREHOUSE knows, and it learns
            # a product from its price row. One we refused to price — unpriced,
            # or unidentifiable — has nothing to hang its details on: they would
            # cost a request and then arrive at ingest as out-of-scope rejects
            # (the rule the woo connector already follows). `asked` drops the
            # same page-edge repeat the price loop drops, so a catalogue
            # shifting mid-crawl cannot buy the same record twice.
            if pid not in price_rows or pid in asked:
                continue
            asked.add(pid)
            detail = None
            try:
                body = self._fetcher.get(f"{endpoint}/{pid}").json()
            except CrawlBlocked:
                raise
            except Exception as exc:  # noqa: BLE001 — isolate per product
                body = None
                notes.append(_skipped(product, f"the request failed: {exc}"))
            if body is not None:
                detail = _detail(body)
                if detail is None:
                    notes.append(_skipped(
                        product, "the response carried no product object "
                                 f"(top level: {_shape(body)})"))
            # A product whose detail failed still has everything the LIST
            # stated. Emitting that is better than emitting nothing for it, and
            # the warning above says precisely which facts are absent.
            rows.extend(enrichment_rows(builder, detail or product, base))
            sku = str((detail or {}).get("sku") or "")
            if sku:
                # The ONLY place a REAL sku can come from: the list endpoint has
                # no such field (0/87 live), the detail has one on 87/87. It
                # replaces the product-id fallback `_row` wrote. A detail that
                # failed, or a product the shop gives no sku, keeps the fallback
                # — the owner's approved exception, never a silent blank.
                price_rows[pid][sku_at] = sku
        return rows

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
        # What one price BUYS, when the shop STATES it: sika prints the pack
        # size beside the price — product 206 is `Sika Zinc Rich® -1 "5 KG"` at
        # EGP 5300 with weight 5. The shared rule requires the name and the
        # `weight` field to agree, which earns its keep here: 60 of the 87 live
        # names state a kg quantity and 4 of those contradict the weight
        # (product 218 is "Sika Latex®- 20 kg" with weight 5). A contradiction
        # states nothing, so we record nothing.
        #
        # The ENGLISH name is what we read. All 60 state it there; the Arabic
        # names spell it «كيلو», which the shared rule does not recognise, and
        # 0 of the 87 state a pack size in Arabic that the English name omits
        # (checked live 2026-07-25). Teaching the shared rule that spelling
        # would change another family's output to buy nothing here.
        basis, unit = selling_unit_from(english, product.get("weight"))
        # THE SKU FALLBACK (owner ruling 2026-07-25), applied here so no row can
        # leave without one. The list entry states no sku — this shop's list
        # endpoint has no such field at all — so `pid` is what stands in, and
        # the detail pass replaces it with the shop's real sku for every product
        # it manages to read (_detail_rows). A row still carrying the product id
        # therefore says one of two things, and only two: the manifest declared
        # no enrichment so no detail was ever asked for, or the shop published
        # no sku for that product. It never means "the shop printed 252 as its
        # SKU". See the module docstring for the census behind the rule.
        return builder.row(
            external_product_id=pid, external_variant_id=pid,
            external_sku=str(product.get("sku") or "") or pid,
            # The unmarked column is English; the Arabic name is marked. This
            # shop publishes both, so both are filled — and where it repeats
            # itself the English column stays empty rather than faking a
            # translation.
            product_name=english if english != name else "",
            product_name_ar=name,
            lang="ar" if arabic and name == arabic else ("en" if name == english else ""),
            category_path=category_en if category_en != category else "",
            category_path_ar=category,
            category_external_id=category_id if category else "",
            brand_raw=str(product.get("brand") or ""), product_url=url,
            country_code_alpha2=region, currency=currency, vat_included=vat,
            regular_price=regular, sale_price=sale, effective_price=effective,
            availability=_availability(product),
            unit=unit, basis_quantity=basis,
        )


# ---- enrichment: everything the shop states about one product ----------------
#
# ONE function for both endpoints, on purpose. The detail response is a superset
# of the list entry for every field read here, and the detail-only keys are
# simply absent from a list entry — `add` skips an absent value, so the same
# code emits the full record from a detail and the summary record from a list
# entry whose detail could not be fetched. A second "detail_enrichment_rows"
# would be the same rules written twice and drifting from the day after (Q1).

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

    # The code states the language of its content (0039): the unmarked name
    # is English, `_ar` is Arabic, and `lang` beside it says the same thing
    # in the column the migration reads.
    add("description_ar", "Description (AR)", product.get("short_description_ar"),
        lang="ar", group="Description")
    add("description", "Description", product.get("short_description_en"),
        lang="en", group="Description")
    add("keywords_ar", "Keywords (AR)", product.get("keywords_ar"), lang="ar",
        group="Description")
    add("keywords", "Keywords", product.get("keywords_en"), lang="en",
        group="Description")
    # The LONG description — the DESCRIPTION / USES / CHARACTERISTICS body of
    # the product page, newline-separated — is detail-only. The `_en` suffix is
    # not decoration: the panel pairs `code` with `code + "_ar"` to print one
    # bilingual entry, the same convention description/description_ar set.
    add("full_description_ar", "Full description (AR)",
        product.get("full_description_ar"), lang="ar", group="Description")
    add("full_description", "Full description",
        product.get("full_description_en"), lang="en", group="Description")
    add("sku", "SKU", product.get("sku"), group="Specs")
    add("weight", "Weight", product.get("weight"), numeric=product.get("weight"),
        unit="kg", group="Specs")
    # `add` skips a falsy value, so a stock_quantity of 0 emits no row. That is
    # a real omission and it is left standing: the fact is NOT lost, because
    # _availability reads the same number and the price row states
    # `out_of_stock` for it — which is what a zero means to a reader. Lifting
    # the guard to let this 0 through would also start writing "Maximum stock
    # level: 0" on 85 of 87 products (below), which would be a lie.
    add("stock_quantity", "Stock quantity", product.get("stock_quantity"),
        numeric=product.get("stock_quantity"), group="Specs")
    # The shop's own reorder thresholds, detail-only. Emitted only when
    # populated, and the falsy guard is the RIGHT rule for both rather than an
    # accident: across all 87 live products (2026-07-25) min_stock_level is
    # never 0 and never null, while max_stock_level is 0 on 85 and null on 2.
    # A max of 0 is the field left unset, not a ceiling of zero units — writing
    # it down would state a limit the shop does not impose.
    add("min_stock_level", "Minimum stock level", product.get("min_stock_level"),
        numeric=product.get("min_stock_level"), group="Specs")
    add("max_stock_level", "Maximum stock level", product.get("max_stock_level"),
        numeric=product.get("max_stock_level"), group="Specs")
    # `specail_price` is the TRADE-TIER price: the storefront charges it only to
    # a logged-in customer whose customerTypeId is 2 (rule + live proof in
    # _prices). Recorded as exactly that fact — a price for a group we are not —
    # so nothing is lost and no row calls it a public discount.
    add("trade_tier_price", "Trade-tier price (customer type 2 only)",
        product.get("specail_price"), numeric=product.get("specail_price"),
        group="Specs")

    # The site's own "Technical Specifications" card (colour, consumption rate,
    # product attributes, suitable applications...), detail-only, in BOTH
    # languages — the standing bilingual rule: a translation the shop publishes
    # and we drop is a defect, not a tidy-up. Codes are keyed on the shop's own
    # attribute_id, never on position: a code derived from the order would
    # rename every attribute the day the shop reorders one list.
    for assignment in product.get("product_attribute_assignments") or []:
        if not isinstance(assignment, dict):
            continue
        attribute = assignment.get("product_attributes") or {}
        code = str(assignment.get("attribute_id")
                   or attribute.get("attribute_id") or "")
        if not code:
            continue
        # This shop's data carries trailing whitespace in both the labels and
        # the values ("Product Attributes ", "1 Meter "). `add` strips the
        # value; the label is stripped here.
        add(f"attr_{code}_ar", str(attribute.get("name_ar") or "").strip(),
            assignment.get("value_ar"), lang="ar", group="Specifications")
        add(f"attr_{code}", str(attribute.get("name_en") or "").strip(),
            assignment.get("value_en"), lang="en", group="Specifications")

    # EVERY attachment the response states. Images lead the panel as the
    # gallery ("Media"); datasheets, videos and anything else are files to
    # open, so they get the shop's own second card, "Attachments". Only
    # `image/*` may reach the gallery: it renders each Media row as an <img>,
    # and this shop files YouTube links as `video/url` attachments, which would
    # arrive there as broken pictures.
    #
    # The size is the API's `file_size`. The storefront itself renders "0
    # Bytes" beside every download — its own defect, not the data's: the API
    # states 265089 for the English TDS of product 252. We record what the API
    # states, and the panel formats it. A `video/url` states no size at all, so
    # it carries no number and no unit rather than a zero it never claimed.
    #
    # The code carries the shop's OWN attachment_id, not a position and not the
    # file name. Ingest keys an attribute on (product, attribute_code,
    # raw_value): 13 of the 87 live products file TWO attachments both named
    # "Video" (two different YouTube links, verified 2026-07-25), so a shared
    # code made the second silently overwrite the first — one video of two
    # gone, with nothing anywhere to show it had been there. An id also
    # survives the shop reordering a list, which a position would not.
    for attachment in product.get("attachments") or product.get("product_attachments") or []:
        href = str(attachment.get("file_url") or "")
        if href and not href.startswith("http"):
            href = base.rstrip("/") + "/" + href.lstrip("/")
        kind = str(attachment.get("file_type") or "")
        ident = str(attachment.get("attachment_id") or "")
        if kind.startswith("image/"):
            add(f"image_{ident}" if ident else "image", "Image",
                attachment.get("file_name"), url=href, group="Media")
        else:
            size = attachment.get("file_size") or ""
            add(f"attachment_{ident}" if ident else "attachment", "Attachment",
                attachment.get("file_name"), url=href, group="Attachments",
                numeric=size, unit="bytes" if size else "")
    return rows
