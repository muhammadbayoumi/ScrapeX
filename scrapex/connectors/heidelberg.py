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

`Bagged` IS NOT A CATEGORY. `productTypes` is the ONLY taxonomy the store API
has, `/api/ProductTypes` holds exactly two rows — `Bagged`/«معبأ» and
`Bulk`/«سائب» — and all 9 catalogued products are `Bagged`. A column with one
value across the whole catalogue distinguishes nothing, so it was filling
`category_path` with a PACKAGING TYPE. The real taxonomy is published on a
THIRD host and is read from there; see "THE CORPORATE TAXONOMY" below. The
packaging type is not deleted — it is a true fact the store published, and it
moves to a detail row of its own.

FIVE REQUESTS
-------------
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

The fourth and fifth are the corporate category listing, ONE PER LANGUAGE, and
they are the whole of the taxonomy read — 5 families out of 2 requests, no
per-family page fetched at crawl time. The taxonomy changes rarely; what each
family's designation is was established once, from captured evidence, and the
tests assert it against those captures rather than re-asking the site every run.

Neither STORE host serves `robots.txt` (both 404 on 2026-07-28 and again on
2026-07-29). The corporate host DOES: `www.heidelbergmaterials.eg/robots.txt`
answers 200 with the Drupal default. Its `Crawl-delay: 10` is addressed ONLY to
`AhrefsBot` and `AhrefsSiteAudit` — the `User-agent: *` group carries none — so
nothing in it binds this crawler, and HttpFetcher's 1 req/s default governs all
three hosts. Verified rather than assumed: 21 recon requests on 2026-07-30
produced an empty `robots_warnings`. Its Disallow list (`/core/`, `/profiles/`,
`/admin/`, `/search/`, `/user/*`, `/media/oembed`) does not intersect either
listing path, so no informational line fires for it either.

Nothing here needs a cookie: city and segment are
pure query parameters on the storefront's own calls, and an A->B->A probe on
one cookie jar answered each request correctly — checked deliberately, because
zid.py documents a store that pins exactly this kind of choice in a cookie.

THE CORPORATE TAXONOMY
----------------------
`www.heidelbergmaterials.eg` publishes FIVE cement families, in both languages,
at `/en/our-products` and `/ar/our_products_ar` — hreflang twins, confirmed by
`<link rel="alternate">` on both. Each family page prints, directly under its
`<h1>`, the designation that family answers to:

    Suez, Helwan, Tourah      / السويس، حلوان، طره            CEMII / A-P 42,5N
    Sulphate Resistant        / المقاوم للكبريتات              CEM IV/A (P) 42.5 SR
    Suez Oasis, Helwan Oasis  / الواحة السويس، الواحة حلوان   OASIS 22.5X
    Blast Furnace Cement      / أسمنت خبث الأفران              CEM III / A 42,5N
    Bulk Cement               / أسمنت سائب                    CEMI 42.5 N

The fifth has NO store product, and that agrees with the store from the other
side: `/api/ProductTypes` carries a `Bulk`/«سائب» type that no product uses.
Two independent hosts saying bulk is not sold online.

THERE IS NO MACHINE JOIN BETWEEN THE HOSTS, and the mapping below is a RULING
rather than a match because of it. Every family page links to
`onlinestore.heidelbergmaterials.eg/#/` — the ROOT, never a `productinfo/{id}`
— and the corporate HTML contains no GUID at all. The designations agree in
meaning and disagree in TOKENS, not merely typography:

    CEMII / A-P 42,5N      ⊂ CEMII / A-P 42,5N SUEZ      clean prefix
    CEM III / A 42,5N      ≟ CEMIII / A 42.5N Suez       space, decimal mark
    CEM IV/A (P) 42.5 SR   ≟ CEM IV/A (P) 42.5N SR       an extra N
    OASIS 22.5X            ≟ OASIS MC 22.5X SUEZ         an extra MC

Casefolding, stripping whitespace and reading `,` as `.` joins 4 of the 9
products. Dropping `MC`, or deciding `42.5N` is `42.5`, would be a
cement-engineering judgement about when two designations name the same cement,
and NEITHER site states it. So it is not computed. The owner ruled the
correspondence on 2026-07-30, keyed on the store's own `productLabelEn` and
valued by the corporate site's own URL paths — both sides site-published
strings — and the family NAMES are read live every crawl, so no translation is
ever frozen into this file.

WHERE THE DESIGNATION LIVES, AND WHY IT IS NOT DUPLICATED. `cement_type` under
SPECIFICATIONS is the RECORD: it is per-product, it is the string the store
publishes, and it carries the plant inside it ("…SUEZ" / "…HELWAN"), which is
what makes it a specification of one product rather than a name or a grouping.
`category_path` is DERIVED from it — the family that designation was ruled to
belong to — and holds a DIFFERENT string in each language, read from the
corporate site. So "CEMII / A-P 42,5N SUEZ" appears once, in `cement_type`, and
"Suez, Helwan, Tourah" / «السويس، حلوان، طره» appears once, in the category. No
column repeats another, and neither language column repeats a Latin string as
though it were a translation.

THE SITE'S OWN CART BUG IS NOT MIRRORED. For a non-multi-plant Y210/Y220
product the add-to-cart handler passes `salePrice30Y410` as the >=30 t price
(`c.onAddCart(o.productId,s,o.salePriceY410,o.salePrice30Y410,"Y410")`). The
DISPLAY branches are correct. We record what is displayed.
"""
from __future__ import annotations

import html
from typing import Iterable
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ..config import SourceEntry, TaxonomyConfig
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

# ---- the corporate taxonomy: where a cement family is published --------------
#
# THE OWNER'S RULING, 2026-07-30. Store designation (`productLabelEn`, as
# `_text` normalises it) -> the corporate page for its family, one path per
# language. Asked and answered because neither host publishes the join: see
# "THE CORPORATE TAXONOMY" in the module docstring for the four designation
# pairs and exactly which token stops each from matching.
#
# The paths are keys, NOT names. Every label shown to a reader is fetched from
# the live listing each crawl, so a rename on the site arrives on its own and
# nothing in this file has to be translated or kept in step by hand.
#
# The Arabic path is stated rather than derived: `/en/suez-opc` against
# `/ar/suez-42.5-n` share no stem, and «أسمنت خبث الأفران» has no clean alias at
# all — the site's own Arabic link for it is a raw Drupal node id. Each pair
# below is the pair the family page's own `<link rel="alternate" hreflang>`
# declares, asserted against the captured fixtures in test_heidelberg.py.
_FAMILY_BY_DESIGNATION: dict[str, tuple[str, str]] = {
    # CEMII / A-P 42,5N — the corporate designation is a clean prefix of all
    # three, which differ from it only by the plant the store appends.
    "CEMII / A-P 42,5N SUEZ": ("/en/suez-opc", "/ar/suez-42.5-n"),
    "CEMII / A-P 42,5N HELWAN": ("/en/suez-opc", "/ar/suez-42.5-n"),
    "CEMII / A-P 42,5N TOURAH": ("/en/suez-opc", "/ar/suez-42.5-n"),
    # CEM IV/A (P) 42.5 SR corporate vs 42.5N SR in the store: an extra
    # strength-class N. `/ Super` is a second store product on the same family.
    "CEM IV/A (P) 42.5N SR": ("/en/sulphate-resistant", "/ar/sulphate-resistant"),
    "CEM IV/A (P) 42.5N SR / Super": ("/en/sulphate-resistant", "/ar/sulphate-resistant"),
    # OASIS 22.5X corporate vs OASIS MC 22.5X in the store: an extra MC.
    "OASIS MC 22.5X SUEZ": ("/en/helwan-oasis", "/ar/helwan-oasis"),
    "OASIS MC 22.5X HELWAN": ("/en/helwan-oasis", "/ar/helwan-oasis"),
    # CEM III / A 42,5N corporate vs CEMIII / A 42.5N in the store: the space
    # after CEM and the decimal mark. The Arabic side has no alias, only a node.
    "CEMIII / A 42.5N Suez": ("/en/cem-iii", "/ar/node/50677"),
}

# WHERE THE FAMILY NAMES ARE READ FROM, owner's choice 2026-07-30: the
# NAVIGATION labels. Two lists carry them and they disagree, so which one wins
# is a decision and it is written down here.
#
# `nav.hc-contentmenu` is the Products section's own sub-navigation and carries
# 4 of the 5 — it omits Blast Furnace Cement entirely. The teaser's button-list
# in the page body carries all 5. So the menu is read first and the teaser fills
# the gap, which is the only reason two selectors appear here.
#
# They also disagree on wording, and only in Arabic: the menu says «المقاوم
# للكبريتات» where the teaser says «المقاوم». The menu's is the one that agrees
# with the family page's own <h1>, which is why the menu wins rather than
# whichever list happens to be parsed last.
#
# Deliberately NOT the family page <h1>: it carries a sub-brand prefix the site
# spells two ways on two pages — "evoBuild - " on Oasis, "evoBUILD - " on Blast
# Furnace — and a category label should not inherit that inconsistency.
_MENU_SELECTOR = "nav.hc-contentmenu a[href]"
_TEASER_SELECTOR = "div.hc-teaser ul.button-list a[href]"


class CementFamilies:
    """The corporate taxonomy as read from the live listing, both languages.

    Holds path -> label per language and answers with a (label, label_ar) pair
    for one store designation. Keeping the two languages in separate maps is
    what makes a missing Arabic label a MISSING label rather than an English
    one silently standing in for it.
    """

    def __init__(self, en: dict[str, str], ar: dict[str, str]) -> None:
        self.en = en
        self.ar = ar

    def __len__(self) -> int:
        return len(self.en)

    def names_families(self) -> bool:
        """True only when BOTH listings were read and actually named families.

        The question "did the taxonomy read work" must be asked of the RESULT,
        not of the absence of an error: a listing can answer 200 and name
        nothing, which is what a site redesign looks like from here.
        """
        return bool(self.en) and bool(self.ar)

    def for_designation(self, designation: str) -> tuple[str, str, str]:
        """(name, name_ar, family_id) for one store designation.

        family_id is the family's English path — the corporate site's own
        canonical identifier for the page, as its `<link rel="canonical">`
        publishes it. Empty strings when the designation was never ruled on;
        the caller is what reports that, because only it knows the product.
        """
        paths = _FAMILY_BY_DESIGNATION.get(designation)
        if paths is None:
            return "", "", ""
        en_path, ar_path = paths
        return self.en.get(en_path, ""), self.ar.get(ar_path, ""), en_path


def _listing_labels(markup: str, page_url: str) -> dict[str, str]:
    """path -> label for every family the listing page names.

    The teaser is parsed first and the content menu second, so the menu
    OVERWRITES it where both name the same path — the owner's choice, written
    as the order of two lines rather than as a comment nobody can test.
    """
    soup = BeautifulSoup(markup, "lxml")
    host = urlsplit(page_url).netloc
    found: dict[str, str] = {}
    for selector in (_TEASER_SELECTOR, _MENU_SELECTOR):
        for anchor in soup.select(selector):
            label = " ".join(anchor.get_text(" ", strip=True).split())
            if not label:
                continue
            target = urlsplit(urljoin(page_url, anchor["href"]))
            # An off-site link in either list is not a family of this site. The
            # teaser's own "Online Store" button is exactly that.
            if target.netloc and target.netloc != host:
                continue
            if target.path:
                found[target.path] = label
    return found


def read_families(fetcher: HttpFetcher, taxonomy: TaxonomyConfig,
                  ) -> tuple[CementFamilies, list[str]]:
    """The five families, from two requests. (families, defects).

    A DEFECT rather than a warning when the corporate host cannot be read: the
    category is a fact this source does publish, so failing to fetch it degrades
    the run's data and must be reported as such. It never falls back to the
    packaging type — filing "Bagged" as a category is the confusion this whole
    reader exists to end, and doing it silently on a bad day would put it back.
    """
    root = (taxonomy.base_url or "").rstrip("/")
    if not root or not taxonomy.listing_path or not taxonomy.listing_path_ar:
        return CementFamilies({}, {}), [
            "taxonomy.base_url / listing_path / listing_path_ar are not all set "
            "in the manifest — the cement family cannot be read and no category "
            "is recorded"]

    pages: dict[str, dict[str, str]] = {}
    defects: list[str] = []
    for lang, path in (("en", taxonomy.listing_path), ("ar", taxonomy.listing_path_ar)):
        url = f"{root}{path}"
        try:
            pages[lang] = _listing_labels(fetcher.get(url).text, url)
        except Exception as exc:  # noqa: BLE001 — a second host is allowed to be down
            pages[lang] = {}
            defects.append(
                f"the {lang} cement-family listing ({url}) could not be read "
                f"({type(exc).__name__}) — no {lang} category is recorded for "
                "any product on this run")
            continue
        # A 200 THAT NAMED NOTHING IS ALSO A DEFECT, and it is the one that
        # would otherwise pass for success. The exception arm above only covers
        # a host that refuses; a Drupal theme release that renames
        # `hc-contentmenu`/`hc-teaser` answers 200 with a perfectly good page
        # this parser cannot see, and both selectors return nothing. Reported
        # here because a warning is not enough: ingest counts defects into
        # crawl_run.errors_count and warnings into nothing, so without this the
        # run that silently lost every category reports SUCCESS with 0 errors —
        # exactly what ScrapedTable.defects exists to prevent (base.py).
        if not pages[lang]:
            defects.append(
                f"the {lang} cement-family listing ({url}) answered but named no "
                "cement family — neither the content menu nor the teaser "
                "button-list matched, which is what a site redesign looks like "
                f"from here. No {lang} category is recorded for any product on "
                "this run")
    # A family the listing no longer names is reported per PRODUCT, by the
    # caller, because only there is it known which cement lost its category.
    return CementFamilies(pages.get("en", {}), pages.get("ar", {})), defects


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
        # Requests 4 and 5, and the last of them: the taxonomy is read ONCE per
        # crawl for the whole source, not once per product. Read before the
        # price loop because every row needs it, and read from a THIRD host.
        families, defects = ((CementFamilies({}, {}), []) if source.taxonomy is None
                             else read_families(self._fetcher, source.taxonomy))
        read_taxonomy = families.names_families()

        by_id = {str(p.get("id") or ""): p for p in products if p.get("id")}
        builder = RowBuilder(PRODUCT_PRICES)
        rows: list[list[str]] = []
        notes: list[str] = []
        unruled: set[str] = set()
        renamed: set[str] = set()
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
            designation = _text(product.get("productLabelEn"))
            family = families.for_designation(designation)
            if designation and designation not in _FAMILY_BY_DESIGNATION:
                unruled.add(designation)
            elif read_taxonomy and family[2] and not (family[0] and family[1]):
                # Gated on the listing having been READ AND NAMED FAMILIES, not
                # on the absence of a defect. A rename is only meaningful when
                # the page arrived, parsed, and simply did not contain this
                # path. Every other way of getting here is already reported once,
                # about the host, and would otherwise be repeated per product:
                #   - no taxonomy block  -> nothing was fetched, so nothing was
                #     renamed; the source simply declares no taxonomy host, and
                #     saying "the listing no longer names it" about a page never
                #     requested sends a reader hunting for a change on the site.
                #   - host down / 200-but-empty -> read_families raised a defect
                #     naming the URL; 8 rename lines under it are one fact said
                #     nine ways.
                renamed.add(designation)
            for plant in shown:
                for field, sku_field, tier_ar in _TIERS:
                    amount = _price(row, f"{field}{plant}")
                    if amount is None:
                        continue
                    rows.append(self._row(builder, source, row, product,
                                          plants.get(plant), plant, sku_field,
                                          tier_ar, amount, family))

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

        # A cement the owner has never been asked about. Same shape as the
        # unrecognised-attribute-code report and for the same reason: a NEW
        # designation gets the question asked, not a family picked for it by
        # whoever notices first.
        if unruled:
            notes.append(
                f"cement designation(s) with no ruled family, so no category was "
                f"recorded for them: {', '.join(sorted(unruled))} — ask the owner "
                "which corporate family each belongs to")
        # The ruling still names a page the listing has stopped naming. Either
        # the family was renamed, or its path moved. Never silently blank.
        if renamed:
            notes.append(
                f"the corporate listing no longer names the family page ruled for "
                f"{', '.join(sorted(renamed))} — the category is empty for it until "
                "the ruled path is corrected")

        yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind,
                           f"{api}/ProductsPrices", builder.header, rows,
                           warnings=notes, defects=defects)

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
             tier_ar: str, amount: float,
             family: tuple[str, str, str] = ("", "", "")) -> list[str]:
        city = price.get("cities") or {}
        city_en, city_ar = _text(city.get("cityNameEn")), _text(city.get("cityNameAr"))
        # The product's OWN plant object names only its own plant, and a
        # multi-plant product is quoted from a plant no product is assigned to,
        # so the name comes from the /api/Plants lookup and falls back to the
        # code the site itself uses — never to a transliteration of ours.
        plant_en = _text((plant or {}).get("plantNameEn")) or plant_code
        plant_ar = _text((plant or {}).get("plantNameAr")) or plant_code
        sku = _text(product.get(sku_field))
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
            # THE CEMENT FAMILY, from the corporate site, in the site's own two
            # sets of words. NOT `productTypes` — that is `Bagged`/«معبأ» on all
            # 9 products, a packaging type masquerading as a taxonomy, and it now
            # travels as a detail of its own instead. Empty rather than
            # substituted when the family could not be read: a blank category
            # says "not established", and "Bagged" said something false.
            category_path=family[0],
            category_path_ar=family[1],
            # The corporate site's own canonical path for that family page —
            # its identifier, published in `<link rel="canonical">`. The store's
            # productTypeId is deliberately gone from here: it identified the
            # packaging type, so keeping it beside a family name would point the
            # id and the name at two different things.
            category_external_id=family[2],
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
    # THE PACKAGING TYPE, which used to sit in category_path and is not a
    # category: `Bagged`/«معبأ» on all 9 products, one of the two values
    # /api/ProductTypes holds. It is still a true thing the store published, so
    # it is kept rather than dropped — the owner's rule that nothing a site
    # states is silently discarded — and it is BILINGUAL here because the store
    # publishes it in both languages, unlike the designation above.
    #
    # Owner ruling 2026-07-30, asked under the standing ASK rule because
    # `packaging_type` was in no group, and answered only after he called for two
    # studies: STORE. By his own boundary this is how THIS store supplies the
    # product, not a property of the cement — the corporate site publishes the
    # SAME CEM II as available in bags AND in bulk, and packaging carries no
    # price signal here at all (0 bulk prices in 24,840 slots; the price row has
    # no packaging field). It is in _DETAIL_GROUP_BY_CODE now, so group_for_code
    # answers for it and the hint below never fires.
    types = product.get("productTypes") or {}
    add("packaging_type", "Packaging type", _text(types.get("productTypeNameEn")),
        lang="en", group=DetailGroup.STORE)
    add("packaging_type_ar", "Packaging type (AR)", _text(types.get("productTypeNameAr")),
        lang="ar", group=DetailGroup.STORE)
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
