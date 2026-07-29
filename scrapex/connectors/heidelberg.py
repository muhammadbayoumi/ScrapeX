"""heidelberg-price-matrix family connector (ENGINEERING.md A3: proven family).

onlinestore.heidelbergmaterials.eg is an Angular SPA served as static files from
IIS; its data comes from a bespoke ASP.NET Web API on a SECOND host, hard-coded
in the bundle as `APIUrl="https://onlinestoreapi.heidelbergmaterials.eg/api"`.
That split is the reason this reads `SourceEntry.api.base_url` rather than
`base_url` — the same reason hybris does. Everything below was established
against the live API and the live bundle on 2026-07-29.

It is NOT custom-json-api. That connector builds its endpoint as
`f"{source.base_url}/api/products"` and never looks at `source.api`, so it would
ask the STOREFRONT host for products and get the IIS 404 page; and its price
model is a number sitting on the product, while here the price lives in a
separate 2,070-row table and is a function of five things at once.

WHAT A PRICE IS HERE
--------------------
A price is (product x governorate x dispatch plant x quantity tier x customer
segment). `GET /api/ProductsPrices` publishes 2,070 rows x 12 price columns =
24,840 slots, of which **211 hold a real number** — and only **108 are prices
the storefront can actually render**. Three filters, every one of them read off
the site's own code rather than chosen by us, cut 211 to 108:

1. SEGMENT. The anonymous storefront hard-codes `segment="Y6"` (Individuals /
   أفراد) — verbatim from the bundle: `plant="Y210"; …; segment="Y6"`. Y6 holds
   201 of the 211. The other 10 are YM/YT and every one of them is for Dahab, a
   city the API itself flags `isActive: false`. No visitor can be quoted them.
2. ACTIVE. `/api/ProductsPrices` returns inactive rows; the storefront's own
   `GetProductsPricesByCityIdAndSegment` filters them. Verified: the full table
   gives 9 rows for Al Dakahleya/Y6, the storefront slice gives 8, the dropped
   one is TOURAH with `isActive: false`, and the 8 agree exactly. Applying it
   here is what keeps the two endpoints from disagreeing.
3. PLANT. Every row carries prices for all three plants; the storefront renders
   at most two. `isMultiPlant: false` shows ONLY the product's own
   `plants.plantCode` (`w(t.products.isMultiPlant?-1:1)`), and `isMultiPlant:
   true` shows a two-option `<select>` — «مصنع السويس» (Y210) and «مصنع
   القطامية» (Y220) — with NO Y410 branch anywhere in it. Taking all three
   columns would file 88 numbers no visitor can see.

THE TRAPS
---------
`0.02` and `0.0` MEAN "NOT AVAILABLE", NOT TWO PIASTRES. The storefront's own
test is `t.salePrice30Y410>.1?5:-1` for the price and `<=.1?6:-1` for
« غير متاح». All 211 real prices carry a `.02` fraction; all 24,629 non-prices
are exactly `0.02` or `0.0`. Because 0.02 is POSITIVE, the ordinary
"non-positive means no price" rule that custom_json uses lets it straight
through, which is why the floor is written out here as its own named constant.

`maxPrice` (1950) / `exWorkMaxPrice` (1700) ARE NOT THE PRICE. Both ride every
product and the bundle references them ZERO times in 719,821 bytes, against 65
references to `salePrice`. The city matrix prices that same product at 3950.02.
Recording them would publish a number no page ever printed, at roughly half the
real one.

NO DISCOUNT EXISTS TODAY. `isOnSale` is false on all 2,070 PRICE rows and all
12 `fakePrice*` columns are sentinels — 0 real values in 24,840 slots. Five of
the nine PRODUCTS carry `isOnSale: true` with no `fakePrice` behind it, so
`price_before` / `price_sale` stay empty rather than manufacture a
strike-through the site never draws.

`productLabelEn == productLabelAr` ON ALL 9 — the same Latin string ("CEMII /
A-P 42,5N SUEZ") stored twice. That is a DESIGNATION, not a name: it travels to
enrichment as `cement_type` and never into `product_name_ar`. The real
bilingual pair is `productNameEn` / `productNameAr`.

Arabic arrives HTML-ENTITY ENCODED (`&#1571;&#1587;…`) on the live API while the
prerendered HTML carries the same text as plain UTF-8, so every string is
unescaped before it is recorded; source strings also carry trailing whitespace
(`'Helwan '`, `'…السويس\\r\\n'`), which is transport noise and not part of any
word the site wrote.

THREE REQUESTS, NOT TWO
-----------------------
`/api/Products` + `/api/ProductsPrices` are the whole catalogue and the whole
price matrix, ~16 s and one 19 MB body (5.4 MB gzipped — httpx negotiates that
by default, and 19 MB uncompressed is not optional politeness).

`/api/Plants` is the third, and it costs 3 rows. A multi-plant product is
quoted from Y220, and NO product in the catalogue is assigned to Y220 — all 9
sit on Y210 or Y410 — so the name «القطامية» / "Katameya" exists nowhere in
`/api/Products`. Without the lookup the plant axis of a Y220 row could only be
left blank or transliterated by us, and inventing a name a site publishes is
exactly what the bilingual rule forbids. One request buys the site's own word
for it, in both languages, plus the company behind each plant.

Neither host serves `robots.txt` (both 404 on 2026-07-28 and again on
2026-07-29), so there is no Crawl-delay to honour and HttpFetcher's 1 req/s
default governs the pace. Nothing here needs a cookie: city and segment are
pure query parameters on the storefront's own calls, and an A->B->A probe on
one cookie jar answered each request correctly — checked deliberately, because
zid.py documents a store that pins exactly this kind of choice in a cookie.

THE SITE'S OWN CART BUG IS NOT MIRRORED. For a non-multi-plant Y210/Y220
product the add-to-cart handler passes `salePrice30Y410` as the >=30 t price
(`c.onAddCart(o.productId,s,o.salePriceY410,o.salePrice30Y410,"Y410")`). The
DISPLAY branches are correct. We record what is displayed.
"""
from __future__ import annotations

import html
from typing import Iterable

from ..config import SourceEntry
from ..normalize import option_axes_json, strip_markup
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, DetailGroup, ExtractKind, group_for_code
from .base import HttpFetcher, ScrapedTable

# The segment an anonymous visitor is quoted, verbatim from the bundle.
PUBLIC_SEGMENT = "Y6"
# The two options the multi-plant `<select>` offers. Y410 is deliberately
# absent: the multi-plant branch has no Y410 option at all.
MULTI_PLANT_CODES = ("Y210", "Y220")
ALL_PLANT_CODES = ("Y210", "Y220", "Y410")
# The storefront's own threshold for "this is a price" (`>.1` / `<=.1`).
PRICE_FLOOR = 0.1
# « / للطن » and «ج م», both printed beside every figure.
SELLING_UNIT = "tonne"
BASIS_QUANTITY = "1"
# The language the storefront renders. Every one of its 31 components is
# suffixed `-ar` and there is no language switch, so `lang` is not a guess.
PRIMARY_LANG = "ar"

# (price-field prefix, the SAP material number for that bracket, the site's own
# Arabic words for it). The merchant issues a DIFFERENT SAP code per bracket —
# 2122671 under 30 t and 2112671 at 30 t and above — so the tier is his
# distinction, not one we drew. The Arabic is lifted verbatim from the sentence
# the product card prints: «السعر من 1 الى 29 طن يختلف عن السعر من 30 طن فأكثر».
# There is no English twin anywhere on the site and the owner ruled
# (2026-07-29) that the English axis stays EMPTY rather than be authored here.
_TIERS = (
    ("salePrice", "sapCode", "من 1 الى 29 طن"),
    ("salePrice30", "sapCode30", "من 30 طن فأكثر"),
)

# The axis names. The values are the site's; these headings are ours, and they
# are the only invented strings in the row — «اختر مدينة التوصيل» and
# «مصنع السويس» are what the two dropdowns are labelled with.
_CITY_AXIS, _CITY_AXIS_AR = "City", "المدينة"
_PLANT_AXIS, _PLANT_AXIS_AR = "Plant", "المصنع"
_QUANTITY_AXIS_AR = "الكمية"


def _api_root(source: SourceEntry) -> str:
    api = source.api
    if api is None or not api.base_url:
        raise ValueError(
            f"{source.source_key}: heidelberg-price-matrix needs api.base_url "
            "(the data host) in the manifest — the storefront host serves no API")
    return f"{api.base_url.rstrip('/')}/api"


def _text(value) -> str:
    """One published string, as the site wrote it and readable.

    Unescaped because the live API returns Arabic entity-encoded and the same
    payload embedded in the prerendered HTML returns it plain — file the raw
    string and `&#1571;…` becomes the product name. Stripped because
    `'Helwan '` and `'…السويس\\r\\n'` carry transport noise around words that
    are themselves untouched.
    """
    return html.unescape(str(value or "")).strip()


def _rich(value) -> str:
    """An HTML fragment as TEXT — the four technical blocks and the descriptions.

    The site renders these through `innerHTML`, so the markup is a rendering
    instruction and the sentences are the fact. `separator="\\n"` keeps each
    `<p>`/`<li>` on its own line, which is what makes "Initial setting time
    (min) >=60" readable in a cell instead of one run-on paragraph. Entities are
    unescaped inside strip_markup, before any tag is removed.
    """
    return strip_markup(str(value or ""), separator="\n")


def _money(value: float) -> str:
    """The figure the page prints, minus its thousands separator.

    The API states money to two decimals and every real price here ends `.02`,
    so `:.2f` reproduces it exactly; the trailing-zero trim only ever fires on
    a whole-pound price, and stops at the point so 4800.00 cannot become 48.
    """
    return f"{round(float(value), 2):.2f}".rstrip("0").rstrip(".")


def _price(row: dict, field: str) -> float | None:
    """A price the storefront would print, or None for its «غير متاح» sentinel."""
    try:
        number = float(row.get(field))
    except (TypeError, ValueError):
        return None
    return number if number > PRICE_FLOOR else None


def _plants_for(product: dict) -> tuple[str, ...]:
    """The plant columns the storefront renders for this product, and only those."""
    if product.get("isMultiPlant"):
        return MULTI_PLANT_CODES
    own = str((product.get("plants") or {}).get("plantCode") or "")
    return (own,) if own else ()


class HeidelbergPriceMatrixConnector:
    connector_id = "heidelberg-price-matrix"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        api = _api_root(source)
        products = self._table(api, "Products")
        plants = {str(p.get("plantCode") or ""): p for p in self._table(api, "Plants")}
        prices = self._table(api, "ProductsPrices")

        by_id = {str(p.get("id") or ""): p for p in products if p.get("id")}
        builder = RowBuilder(PRODUCT_PRICES)
        rows: list[list[str]] = []
        notes: list[str] = []
        dropped = {"segment": 0, "inactive": 0, "plant": 0, "unknown_product": 0}

        for row in prices:
            product = by_id.get(str(row.get("productId") or ""))
            available = [(plant, field) for plant in ALL_PLANT_CODES
                         for field, _sku, _label in _TIERS
                         if _price(row, f"{field}{plant}") is not None]
            if str((row.get("companyTypes") or {}).get("sapCode") or "") != PUBLIC_SEGMENT:
                dropped["segment"] += len(available)
                continue
            if product is None:
                dropped["unknown_product"] += len(available)
                continue
            if not row.get("isActive"):
                dropped["inactive"] += len(available)
                continue
            shown = _plants_for(product)
            dropped["plant"] += sum(1 for plant, _f in available if plant not in shown)
            for plant in shown:
                for field, sku_field, tier_ar in _TIERS:
                    amount = _price(row, f"{field}{plant}")
                    if amount is None:
                        continue
                    rows.append(self._row(builder, source, row, product,
                                          plants.get(plant), plant, sku_field,
                                          tier_ar, amount))

        # Every number the site holds and does not publish, said out loud. A
        # crawl that files 108 of 211 has to name the 103 it refused and why,
        # or a later reader reads the gap as a broken connector.
        if dropped["segment"]:
            notes.append(
                f"{dropped['segment']} price(s) belong to a customer segment other "
                f"than {PUBLIC_SEGMENT} — not quotable to an anonymous visitor, "
                "so not recorded")
        if dropped["inactive"]:
            notes.append(
                f"{dropped['inactive']} price(s) sit on rows the API flags "
                "isActive=false; the storefront's own endpoint filters them out")
        if dropped["plant"]:
            notes.append(
                f"{dropped['plant']} price(s) are for a plant column the product's "
                "own page never renders (isMultiPlant decides which two of three)")
        if dropped["unknown_product"]:
            notes.append(
                f"{dropped['unknown_product']} price(s) name a productId absent from "
                "/api/Products — recorded nowhere rather than guessed at")

        # Details are keyed to a product the WAREHOUSE knows, and it learns a
        # product from its PRICE row: ingest refuses an attribute whose product
        # it never registered rather than mint a ghost. So a product no city
        # prices states its details to nobody. That is a fact about the SOURCE
        # and it is said here, rather than papered over with rows that would be
        # rejected on every crawl for as long as the product stays unpriced.
        priced = {row[builder.header.index("external_product_id")] for row in rows}
        silent = sorted(_text(p.get("productNameEn")) or _text(p.get("id"))
                        for p in products if _text(p.get("id")) not in priced)
        if silent:
            notes.append(
                f"{len(silent)} product(s) are catalogued with no price in any "
                f"city ({', '.join(silent)}) — no row, and no details either")

        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind,
                           f"{api}/ProductsPrices", builder.header, rows,
                           warnings=notes)

        # The SAME /api/Products response the prices were joined against, so
        # this costs no request at all — and it is the only technical data this
        # source has: there is no datasheet container and no document endpoint.
        if any(spec.kind == ExtractKind.ENRICHMENT for spec in source.extract):
            extra = RowBuilder(ENRICHMENT)
            unrecognised: set[str] = set()
            detail = [r for product in products
                      if _text(product.get("id")) in priced
                      for r in enrichment_rows(extra, product, unrecognised)]
            if detail:
                yield ScrapedTable(
                    source.source_key, ENRICHMENT.kind, f"{api}/Products",
                    extra.header, detail,
                    # The owner's standing ASK rule (vocab.DetailGroup): a NEW
                    # kind of fact is never filed by a developer's judgement.
                    # Saying which codes the map did not know is how the
                    # question gets asked instead of the fallback absorbing it.
                    warnings=([f"attribute code(s) the detail-group map does not "
                               f"recognise, filed under the fallback until the "
                               f"owner rules: {', '.join(sorted(unrecognised))}"]
                              if unrecognised else []))

    def _table(self, api: str, name: str) -> list:
        """One lookup table. A shape this connector cannot read fails LOUD.

        The whole point: `data.get("products")` returning None once made a
        sibling connector print "0 rows" as a success while the site was up.
        """
        body = self._fetcher.get(f"{api}/{name}").json()
        if not isinstance(body, list):
            keys = sorted(body)[:6] if isinstance(body, dict) else type(body).__name__
            raise ValueError(
                f"{api}/{name} did not answer a JSON array — the API's shape has "
                f"changed (top level: {keys})")
        return body

    @staticmethod
    def _row(builder: RowBuilder, source: SourceEntry, price: dict, product: dict,
             plant: dict | None, plant_code: str, sku_field: str,
             tier_ar: str, amount: float) -> list[str]:
        city = price.get("cities") or {}
        city_en, city_ar = _text(city.get("cityNameEn")), _text(city.get("cityNameAr"))
        # The product's OWN plant object names only its own plant, and a
        # multi-plant product is quoted from a plant no product is assigned to,
        # so the name comes from the /api/Plants lookup and falls back to the
        # code the site itself uses — never to a transliteration of ours.
        plant_en = _text((plant or {}).get("plantNameEn")) or plant_code
        plant_ar = _text((plant or {}).get("plantNameAr")) or plant_code
        sku = _text(product.get(sku_field))
        types = product.get("productTypes") or {}
        name_en, name_ar = _text(product.get("productNameEn")), _text(product.get("productNameAr"))
        axes_en = {_CITY_AXIS: city_en, _PLANT_AXIS: plant_en}
        axes_ar = {_CITY_AXIS_AR: city_ar, _PLANT_AXIS_AR: plant_ar,
                   _QUANTITY_AXIS_AR: tier_ar}
        return builder.row(
            external_product_id=_text(product.get("id")),
            # Three identifiers the SITE publishes and nothing invented: the
            # governorate it prices for, the plant it dispatches from, and the
            # merchant's own material number for that quantity bracket. Distinct
            # here means a distinct variant, a distinct offer and therefore an
            # independent price timeline — which is what stops 108 prices for
            # 8 products from reading as one offer changing price 108 times.
            external_variant_id=f"{_text(price.get('cityId'))}|{plant_code}|{sku}",
            external_sku=sku,
            product_name=name_en,
            product_name_ar=name_ar,
            variant=", ".join(f"{axis}: {value}" for axis, value in axes_en.items() if value),
            variant_ar=", ".join(f"{axis}: {value}" for axis, value in axes_ar.items() if value),
            variant_axes=option_axes_json(axes_en),
            variant_axes_ar=option_axes_json(axes_ar),
            lang=PRIMARY_LANG,
            # A CLIENT-SIDE route. There is no SPA fallback rewrite, so a direct
            # GET of this 404s at IIS — it is recorded for a human to open in a
            # browser and must never be followed by a crawl.
            product_link=f"{source.base_url.rstrip('/')}/productinfo/{_text(product.get('id'))}",
            country_code_alpha2=source.default_region,
            currency=source.currency or "UNKNOWN",
            tax_included="1" if source.vat_mode.value == "incl" else "0",
            # Deliberately empty: `isOnSale` is false on every price row and
            # every fakePrice column is the sentinel, so there is no
            # strike-through to record and nothing to compute one from.
            price_before="", price_sale="",
            price=_money(amount),
            # The API has no stock concept at all. A tier the storefront prints
            # a price for is one it will sell; a tier it prints «غير متاح» for
            # never reaches this line.
            availability=Availability.IN_STOCK.value,
            unit=SELLING_UNIT, basis_quantity=BASIS_QUANTITY,
            category_path=_text(types.get("productTypeNameEn")),
            category_path_ar=_text(types.get("productTypeNameAr")),
            category_external_id=_text(product.get("productTypeId")),
        )


# ---- enrichment: everything /api/Products states about one product -----------
#
# Rides the response the prices were joined against, so it costs no request.
# Deliberately NOT here: brand, images, datasheets, GTIN, stock, weight, pack
# size, country of origin. The source publishes none of them — the image blob's
# SAS token expired 2026-02-24 and 403s for a browser too — and an empty cell is
# the honest record of a fact the site does not state.

def enrichment_rows(builder: RowBuilder, product: dict,
                    unrecognised: set[str] | None = None) -> list[list[str]]:
    """One row per stated fact about one product, both languages kept apart."""
    pid = _text(product.get("id"))
    if not pid:
        return []
    rows: list[list[str]] = []

    def add(code: str, label: str, value: str, *, lang: str, group: DetailGroup):
        if not value:
            return
        decided, known = group_for_code(code)
        if not known and unrecognised is not None:
            unrecognised.add(code)
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=value, lang=lang,
            attribute_group=decided if known else group))

    add("description", "Description", _rich(product.get("productShortDescriptionEn")),
        lang="en", group=DetailGroup.DESCRIPTION)
    add("description_ar", "Description (AR)", _rich(product.get("productShortDescriptionAr")),
        lang="ar", group=DetailGroup.DESCRIPTION)
    # The DESIGNATION — "CEMII / A-P 42,5N SUEZ" — which is what the standard
    # calls this cement, not what the shop calls the product. Stored once: the
    # site holds the same Latin string in productLabelAr on all 9, and copying
    # it into an `_ar` row would dress a repetition up as a translation.
    add("cement_type", "Cement type", _text(product.get("productLabelEn")),
        lang="en", group=DetailGroup.SPECIFICATIONS)
    companies = (product.get("plants") or {}).get("companies") or {}
    add("manufacturer", "Manufacturer", _text(companies.get("companyNameEn")),
        lang="en", group=DetailGroup.MORE_INFORMATION)
    add("manufacturer_ar", "Manufacturer (AR)", _text(companies.get("companyNameAr")),
        lang="ar", group=DetailGroup.MORE_INFORMATION)
    # The four technical blocks, in both languages. Owner ruling 2026-07-29,
    # asked under the standing rule because none of these codes was in
    # _DETAIL_GROUP_BY_CODE: all four file under Specifications, because all
    # four state properties of the cement itself. They are now IN that map, so
    # group_for_code answers for them and the hint below never fires.
    for code, label, key in (
        ("physical_characteristics", "Physical characteristics", "physicalCharacteristics"),
        ("chemical_characteristics", "Chemical characteristics", "chemicalCharacteristics"),
        ("characteristics", "Characteristics", "characteristics"),
        ("applications", "Applications", "applications"),
    ):
        add(code, label, _rich(product.get(f"{key}En")),
            lang="en", group=DetailGroup.SPECIFICATIONS)
        add(f"{code}_ar", f"{label} (AR)", _rich(product.get(f"{key}Ar")),
            lang="ar", group=DetailGroup.SPECIFICATIONS)
    return rows
