"""magento-graphql family connector (ENGINEERING.md A3: proven family).

Madar (the flagship) runs Magento 2 with an open GraphQL endpoint. We list all
priced products paginated (`filter:{price:{from:"0"}}`).

WHAT A ROW IS depends on the product's SHAPE, and the shapes do not agree — the
single most expensive assumption this connector ever made. Study B1 enumerated
madar's whole live census on 2026-07-25 (760 products, 8 pages):

  SimpleProduct        399   one row; the API figure IS the price the page shows
  ConfigurableProduct  328   one row per variant, and the API figure is the
                             page's tax-EXCLUSIVE one — see _product_rows
  GroupedProduct        33   one row per MEMBER; the group itself has no price,
                             and its price_range reports max == min even when
                             the members span 55%

No BundleProduct, VirtualProduct or DownloadableProduct exists on this store
today; a price_range that really is a range is refused rather than filed at its
low end.

NOTHING HERE MULTIPLIES A PRICE. The figure the API states is the figure that
gets stored, for every shape, and what differs per shape is the tax_included
flag the row carries — the owner's ruling after a source-wide 15% uplift was
declared here and put 3,312 wrong prices in the warehouse: «سجلها كما تاخذ
البيانات من الموقع بدون تعديل ولكن عمود الضريبة يكون واضح الرقم دا شامل الضريبة
ام لا». Record it as the site gives it; make the tax column say what it is.
So a configurable row is stored at 50.4 with tax_included=0 and reads "Excl.
15%", where the old code stored 57.96 and claimed the shop had printed it.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from ..config import SourceEntry
from ..normalize import option_axes_json, option_fingerprint, selling_unit_from, strip_markup
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..units import charter_for
from ..vocab import Availability, DisplayMethod, ExtractKind, group_for_code
from .base import CrawlBlocked, HttpFetcher, ScrapedTable, declare_frontier

PAGE_SIZE = 100

# configurable_options carries the site's own NAME for each variant axis
# ("السماكة (مم)"), and each variant child carries its weight — verified live
# on madar 2026-07-22 (riyadh-cement: weight 50 + "50كجم" in the name; steel
# angles: thickness/width/length axes). The descriptions slot is filled only
# when the manifest asks for enrichment, so a prices-only crawl stays light.
#
# `__typename` and the GroupedProduct fragment ride the SAME request the prices
# already come from — they cost nothing and they are the difference between
# knowing what a row is and assuming it. Study B1 (2026-07-25) enumerated the
# whole madar census: 399 SimpleProduct, 328 ConfigurableProduct, 33
# GroupedProduct, and the three do NOT share one price rule (see _product_rows).
#
# THE QUANTITY FACTS — is_qty_decimal, min_sale_qty, qty_increments — ride the
# same request too, and their absence is what made 109 leaves unreadable. A
# madar rebar member states weight 1000, a 0.25 minimum and a 0.05 step, and
# the warehouse stored basis_quantity 1.0 with no unit and no minimum: "the
# price of one thing", for a figure that is not the price of one thing. They
# live on SimpleProduct in madar's schema (introspected 2026-07-29), so they
# are asked for at the top level AND inside both child selections — a grouped
# member and a configurable child are simple products, and that is where the
# facts actually sit.
#
# only_x_left_in_stock is the shop's own count, non-null on 297 priced leaves.
# rowspec has carried a stock_quantity column and ingest has stored it since
# before this connector existed; nothing ever asked the site for it.
_QUANTITY_FACTS = ("is_qty_decimal min_sale_qty qty_increments "
                   "only_x_left_in_stock")

_QUERY_TEMPLATE = """query($pageSize:Int!,$currentPage:Int!){{
  products(filter:{{price:{{from:"0"}}}},pageSize:$pageSize,currentPage:$currentPage){{
    page_info{{current_page total_pages}}
    items{{
      __typename uid sku name url_key stock_status
      categories{{uid name breadcrumbs{{category_name}}}}
      price_range{{minimum_price{{regular_price{{value}} final_price{{value}}}}
                  maximum_price{{final_price{{value}}}}}}
      ... on SimpleProduct{{weight {quantity}}}
      {extra}
      ... on GroupedProduct{{
        items{{qty position product{{uid sku name stock_status
          ... on PhysicalProductInterface{{weight}}
          ... on SimpleProduct{{{quantity}}}
          price_range{{minimum_price{{regular_price{{value}} final_price{{value}}}}}}}}}}
      }}
      ... on ConfigurableProduct{{
        configurable_options{{attribute_code label}}
        variants{{
          product{{uid sku name stock_status weight
            ... on SimpleProduct{{{quantity}}}
            price_range{{minimum_price{{regular_price{{value}} final_price{{value}}}}}}}}
          attributes{{code label}}
        }}
      }}
    }}
  }}
}}"""

_QUERY = _QUERY_TEMPLATE.format(extra="", quantity=_QUANTITY_FACTS)
# custom_attributesV2 IS the site's "More information" panel (verified live
# 2026-07-23: manufacturer, country_of_manufacture, origin, size, material
# type, coating, grade — the owner's list, code for code). Dropdown values
# arrive as selected_options, text values as value; both fragments cover it.
#
# `image` and `media_gallery` were READ by _enrichment_rows since the day it
# was written and never ASKED FOR here, so every madar product arrived with no
# picture and the panel's gallery was empty for the whole source. The reader
# was right; the query was the hole.
#
# THE WHOLE CATALOGUE, 2026-07-30 (761 products, 4 pages of 200), because the
# 186 madar products that look imageless get re-reported as a bug about this
# query roughly once a month:
#
#   publish an `image` url          761   — every one
#     ... of which the placeholder  185   — one shared URL, placeholder_4.png
#     ... a real file               576
#   publish a media_gallery         577
#   no gallery AND placeholder      184
#   no gallery BUT a real image       0   <- there is nothing here to fetch
#
# So the empty column is the SITE's answer, not a gap in this query: a product
# with no gallery is a product whose only image is the shop's grey box. The
# reader refuses it, and an honest blank beats a placeholder in a data column.
#
# meta_title / meta_description / meta_keyword are asked for BY NAME because
# custom_attributesV2 is filtered to is_visible_on_front:true and these are not
# visible on the front — so the "take every visible attribute" reader could
# never reach them, and the Site metadata group that exists for exactly this
# kind of fact stayed half empty. They earn their place on live evidence: the
# epoxy rebar's AR meta_title says «سابك» (SABIC) while its `name` says «من
# حديد» (Hadeed) and its image is epoxy_sabic.png. That contradiction is the
# SITE's, and under "source truth is never edited" we record it rather than
# quietly pick a winner.
_QUERY_ENRICHED = _QUERY_TEMPLATE.format(
    quantity=_QUANTITY_FACTS,
    extra="description{html} short_description{html} "
          "meta_title meta_description meta_keyword "
          "image{url label} media_gallery{url label position} "
          "custom_attributesV2(filters:{is_visible_on_front:true}){items{"
          "code ... on AttributeValue{value} "
          "... on AttributeSelectedOptions{selected_options{label}}}}")

# THE SITE'S OWN FILTERS. Magento answers `aggregations` with exactly the facets
# its category pages offer — verified live 2026-07-25: 20 of them, including
# «عدد الخطوط», «التيار المقنّن (بالأمبير)» and «سعة القطع (كيلو أمبير)». The
# owner asked to be able to filter the way the site lets him filter, and this
# is the site saying which attributes those are, in its own words. One request
# per crawl, and only when the manifest asks for enrichment.
#
# It also repairs a smaller wart: the "More information" rows were labelled with
# the raw attribute CODE (country_of_manufacture) because nothing else knew the
# human label. For every filterable attribute, this query is where that label
# comes from.
_AGGREGATIONS_QUERY = """query{products(filter:{price:{from:"0"}},pageSize:1,currentPage:1){
  aggregations{attribute_code label}}}"""

# THE UNIT THE SHOP'S OWN WEIGHTS ARE IN. Magento carries it on StoreConfig,
# and madar answers "kgs" on both store views — read live 2026-07-30, ar_SA and
# en_SA alike, one request, no session and no state change.
#
# It matters because `weight` is a bare float in the schema and the rebar's
# 1000 is about to be shown to a reader as the basis its price is quoted
# against. "kg" was, until this query existed, the one word in that sentence
# that came out of OUR mouth: normalize.selling_unit_from hardcodes it and so
# does the enrichment weight row. Now the shop says it. A store configured in
# "lbs" renders lbs with nothing here changing, and a crawl that cannot reach
# this answer publishes no basis at all rather than a number with a unit we
# assumed — the same rule selling_unit_from already applies when a name and a
# weight disagree.
#
# One request per crawl, and unlike aggregations it runs on EVERY crawl: this
# one qualifies a price, so a prices-only run needs it as much as an enriched
# one does.
_STORE_CONFIG_QUERY = "query{storeConfig{weight_unit}}"

# EVERY attribute's human label, in the store's own language — the owner's
# screenshot of madar's «المزيد من المعلومات» tab shows «المصنع», «بلد
# المنشأ», «الطول (متر)» where the panel showed manufacturer, origin,
# length_cm. The site publishes the words; only the facet subset was ever
# asked for them (aggregations covers what the shop FILTERS by, nothing
# else). An empty attributes list asks for all of them: one request per
# store view, and the answer is the whole vocabulary.
# NAMED codes, never an empty list: probed live 2026-07-27, madar's Magento
# refuses attributes:[] with 'Required parameters "attribute_code" and
# "entity_type"' — and answers perfectly for named codes («المصنع» for
# manufacturer, exactly the word the owner's screenshot shows). The codes
# are free: every product the crawl already fetched states its own.
_ATTRIBUTE_LABELS_QUERY = """query{{customAttributeMetadataV2(attributes:[{attrs}]){{
  items{{code label}}}}}}"""
_ATTRIBUTE_CODE_SAFE = re.compile(r"^[A-Za-z0-9_]+$")

# The en_SA store view returns English names for the same uids (verified
# live: "اسمنت الرياض" -> "Riyadh Cement"). uid + name ONLY — the bilingual
# table costs pages, never payloads.
#
# THE GROUPED FRAGMENT IS NOT OPTIONAL. Both English queries carried a
# ConfigurableProduct fragment and no GroupedProduct one, so `names_en` never
# learned a single member uid — and a grouped member's name IS its variant
# label, the thing that tells one member from another. The site publishes
# 161/161 English member names and 150 of them differ from the Arabic
# ("Hadeed Epoxy Rebar| Ø10mm × 12m | ASTM A775 Grade 60"); all 162 stored
# variants carried variant=''. Under the standing bilingual rule that is a
# defect, and it needed BOTH this fragment and the row() call to be fixed —
# either one alone leaves the column empty.
_ENGLISH_STORE = "en_SA"
# The language the PRIMARY pass collects in. Not a new assumption: this
# connector already asserts it every time it writes the default store's name
# into product_name_ar and reads the other half from _ENGLISH_STORE above. The
# two are one setting and a store whose default view is not Arabic would have
# to change both together.
_PRIMARY_LANG = "ar"
# Facts about the PAGE, which is why they file under Site metadata and not
# beside the product's own properties. Requested by name because
# custom_attributesV2 is filtered to is_visible_on_front:true and these are
# not visible on the front, so the "take every visible attribute" reader could
# never see them. Their human label per store comes from the same
# customAttributeMetadataV2 call every other code uses.
_META_FIELDS = ("meta_title", "meta_description", "meta_keyword")
_EN_GROUPED_FRAGMENT = "... on GroupedProduct{items{product{uid name}}}"
_EN_QUERY = """query($pageSize:Int!,$currentPage:Int!){
  products(filter:{price:{from:"0"}},pageSize:$pageSize,currentPage:$currentPage){
    page_info{current_page total_pages}
    items{uid name %(grouped)s ... on ConfigurableProduct{
      configurable_options{attribute_code label}
      variants{product{uid name} attributes{code label}}}}
  }
}""" % {"grouped": _EN_GROUPED_FRAGMENT}

# The SAME en pass when enrichment is on: descriptions and attribute values
# ride pages the names already cost, so the English half of every detail is
# free. The standing rule: a translation the site publishes and we drop is
# a defect — and madar publishes every description and attribute twice.
_EN_QUERY_ENRICHED = """query($pageSize:Int!,$currentPage:Int!){
  products(filter:{price:{from:"0"}},pageSize:$pageSize,currentPage:$currentPage){
    page_info{current_page total_pages}
    items{uid name description{html} short_description{html}
      meta_title meta_description meta_keyword
      custom_attributesV2(filters:{is_visible_on_front:true}){items{
        code ... on AttributeValue{value}
        ... on AttributeSelectedOptions{selected_options{label}}}}
      %(grouped)s
      ... on ConfigurableProduct{
      configurable_options{attribute_code label}
      variants{product{uid name} attributes{code label}}}}
  }
}""" % {"grouped": _EN_GROUPED_FRAGMENT}

# selling_unit_from (the "50كجم" in a variant's NAME agreeing with its weight)
# moved to ..normalize on 2026-07-25: sikaegshop states its pack size the same
# way, and connectors never import each other (A1). Unit parsing belongs to the
# one shared parsing module by rule anyway (Q2).


# The category TREE, to four levels — the same L1..L4 the main table offers.
# Queried once per crawl because madar's price-filtered census answers
# categories:[] on every product (verified live 2026-07-22) while the tree and
# per-category listings are fully populated: the classification exists, the
# census query just refuses to say it. Walking the tree makes the path known
# from the walk itself, so the per-leaf product query needs nothing but uids.
_TREE_QUERY = """{categoryList{
  children{uid name children{uid name children{uid name children{uid name}}}}
}}"""

_LEAF_PRODUCTS_QUERY = """query($uid:String!,$pageSize:Int!,$currentPage:Int!){
  products(filter:{category_uid:{eq:$uid}},pageSize:$pageSize,currentPage:$currentPage){
    page_info{current_page total_pages}
    items{uid}
  }
}"""


def _depth(path: str) -> int:
    """LEVELS in a path, not characters. 'Deepest wins' compared string
    lengths once, so a shallow promo bucket with a long Arabic name beat a
    genuinely deeper three-level home (found by the adversarial review,
    reproduced by execution). A filing's depth is its level count."""
    return path.count(" > ") + 1 if path else 0


def _option_text(attrs: list[dict], option_labels: dict[str, str]) -> str:
    """"السماكة (مم): 2.2، العرض (مم): 24" — the axis NAMES ride along.

    Bare number tuples ("2.2, 24, 24, 6000") were the owner's exact report:
    unreadable without the axes. configurable_options carries the site's own
    label per code, so the meaning comes from the source, in its words."""
    parts = []
    for a in attrs:
        value = str(a.get("label") or "")
        axis = option_labels.get(str(a.get("code") or ""), "")
        parts.append(f"{axis}: {value}" if axis else value)
    return "، ".join(p for p in parts if p)


def _clean(html: str) -> str:
    """Tag-stripped text — see normalize.strip_markup for why <style> and
    <script> go content and all, and why entities are unescaped first."""
    return strip_markup(html)


def _classification(product: dict) -> tuple[str, str]:
    """(category_path, category_external_id) — the DEEPEST filing the site states.

    Madar files one product under several categories at several depths (the
    owner's report: multiple layers of classification, all of which must reach
    the main table). Magento's breadcrumbs carry the ancestors in order, so the
    deepest chain IS the levels, joined with the contract's ' > ' separator.
    Deepest rather than first: a shallow duplicate filing ("Promotions") says
    less than the real place in the tree.
    """
    best_chain: list[str] = []
    best_uid = ""
    for category in product.get("categories") or []:
        crumbs = [(b.get("category_name") or "").strip()
                  for b in (category.get("breadcrumbs") or [])]
        chain = [*[c for c in crumbs if c], (category.get("name") or "").strip()]
        chain = [c for c in chain if c]
        if len(chain) > len(best_chain):
            best_chain = chain
            best_uid = str(category.get("uid") or "")
    return " > ".join(best_chain), best_uid


def _availability(stock_status: str | None) -> str:
    if stock_status == "IN_STOCK":
        return Availability.IN_STOCK.value
    if stock_status == "OUT_OF_STOCK":
        return Availability.OUT_OF_STOCK.value
    return Availability.UNKNOWN.value


def _prices(node: dict) -> tuple[float | None, float | None]:
    """The (regular, final) figures the node states — exactly as stated.

    This function used to take a tax rate and multiply. It does not any more,
    and the parameter is gone rather than defaulted, so no caller can quietly
    re-introduce the uplift: a computed price is a number the shop never
    published, and telling the two apart afterwards is impossible. Whether the
    figure includes tax is recorded BESIDE it, on the row.
    """
    mp = ((node.get("price_range") or {}).get("minimum_price")) or {}
    return ((mp.get("regular_price") or {}).get("value"),
            (mp.get("final_price") or {}).get("value"))


def _range_ends(product: dict) -> tuple[float | None, float | None]:
    """(lowest, highest) final price the node's price_range states."""
    span = product.get("price_range") or {}
    low = ((span.get("minimum_price") or {}).get("final_price") or {}).get("value")
    high = ((span.get("maximum_price") or {}).get("final_price") or {}).get("value")
    return low, high


def _spans_a_range(product: dict) -> bool:
    low, high = _range_ends(product)
    return low is not None and high is not None and high != low


def _range_text(product: dict) -> str:
    low, high = _range_ends(product)
    return f"{low}..{high}"


def _display_method(product: dict) -> str:
    """HOW THIS PAGE PRESENTS ITS PRODUCT — one of vocab.DisplayMethod, or "".

    Read off `__typename` plus the min/max test, both of which are already in
    the census response: this costs NO extra request. Measured on madar
    2026-07-29 — 400 single, 36 options_one_price, 292 options_priced, 33
    member_list over 161 leaves.

    The min/max test is what separates the two configurable cases, and it is
    the difference between a page that shows one price and a page that shows
    "from X". Note it is only trustworthy for CONFIGURABLE: Magento answers
    max == min on all 33 grouped products even though 20 of them really span,
    which is exactly why a grouped product's own price_range is refused
    elsewhere in this file — so the grouped answer is taken from the typename
    alone and never from the range.

    An unstudied shape (a BundleProduct, a VirtualProduct — neither exists on
    this store today) returns "". A shape we have not studied is not a shape we
    may guess at, and the column's whole value is that it never bluffs.
    """
    shape = str(product.get("__typename") or "")
    if shape == "GroupedProduct":
        return DisplayMethod.MEMBER_LIST.value
    if shape == "ConfigurableProduct":
        return (DisplayMethod.OPTIONS_PRICED.value if _spans_a_range(product)
                else DisplayMethod.OPTIONS_ONE_PRICE.value)
    if shape == "SimpleProduct":
        return DisplayMethod.SINGLE.value
    return ""


def _quantity_facts(child: dict) -> tuple[str, str, str]:
    """(minimum_quantity, quantity_increment, quantity_is_decimal) as the site
    states them — and "" wherever it states nothing.

    NOTHING IS DERIVED HERE. madar's rebar publishes weight 1000 with a 0.25
    minimum in 0.05 steps and never writes «طن» anywhere a crawl can reach
    (verified exhaustively 2026-07-29: member and parent attributes,
    description, short_description, every meta field, both category
    descriptions, both store views, and the full rendered page). The owner
    ruled «الحقائق الخام فقط» — raw facts only — so this returns the numbers
    and lets the display layer say "per 1,000 kg". Turning them into a unit
    would put a word on the row that the shop has never printed.

    Magento's default for a product nobody configured is min_sale_qty 1 /
    qty_increments 1, which says nothing; it is stored anyway rather than
    filtered, because "the site says 1" and "the site says nothing" are
    different facts and only the site gets to tell them apart.
    """
    minimum = child.get("min_sale_qty")
    increment = child.get("qty_increments")
    decimal = child.get("is_qty_decimal")
    return ("" if minimum is None else str(minimum),
            "" if increment is None else str(increment),
            "" if decimal is None else ("1" if decimal else "0"))


def _spec_size(product: dict | None) -> str:
    """The `size` the shop states in a product's Specifications panel.

    «إسمنت السعودية» carries no size on its variants at all — its option value
    is «Cement Type: Sulphate Resistant» — and states «المقاس: 50 Kg» in its
    specifications, which is the shop saying what one bag is. 48 madar products
    state a mass or volume this way.

    Read from the response the price row is already built from: when a source
    declares enrichment, this crawl asks _QUERY_ENRICHED and custom_attributesV2
    arrives with the price. It costs no request.
    """
    if not product:
        return ""
    for item in ((product.get("custom_attributesV2") or {}).get("items")) or []:
        if str(item.get("code") or "") not in ("size", "size_ar"):
            continue
        selected = item.get("selected_options") or []
        if selected:
            return str(selected[0].get("label") or "")
        return str(item.get("value") or "")
    return ""


def _apply_charter(row: list[str], charter, product: dict | None = None) -> None:
    """Let a declared charter decide the unit, from the row this crawl built.

    Applied AFTER the row exists rather than inside the three call sites of
    normalize.selling_unit_from, because that function serves other families
    and its agreement rule is right for them: a name stating a kg quantity that
    matches the weight field. What it cannot do is read a unit the shop states
    in two fields, or a container it names in an option value — and those are
    the two ways madar speaks. Measured over its 3,537 offers: the old rule
    reaches 92, this reaches 3,532.

    A source with no charter is untouched, so nothing outside madar moves.
    """
    if not charter:
        return
    columns = PRODUCT_PRICES.columns
    at = columns.index
    resolution = charter.resolve({
        "weight": row[at("weight")],
        "weight_unit": row[at("weight_unit")],
        "variant_axes": row[at("variant_axes")],
        "variant_axes_ar": row[at("variant_axes_ar")],
        "product_name": row[at("product_name")],
        "product_name_ar": row[at("product_name_ar")],
        # Not a row column: the shop's Specifications value, handed straight to
        # the charter. It describes the FAMILY, so any charter that reads it
        # must rank it below the variant's own axes — a product-level size
        # printed on every variant is how a family's figure becomes each
        # member's, which is the mistake reports.py already names in writing.
        "spec_size": _spec_size(product),
    })
    if resolution is None:
        return
    row[at("unit")] = resolution.unit
    row[at("basis_quantity")] = resolution.basis
    row[at("selling_unit_raw")] = resolution.raw
    row[at("selling_unit_raw_lang")] = resolution.raw_lang
    row[at("content_quantity")] = ("" if resolution.content_quantity is None
                                   else f"{resolution.content_quantity:g}")
    row[at("content_unit")] = resolution.content_unit
    row[at("unit_basis_provenance")] = resolution.provenance
    row[at("unit_basis_witness")] = resolution.witness




class MagentoGraphqlConnector:
    connector_id = "magento-graphql"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher
        self.skip_tokens: set[str] = set()      # resume: pages already journaled

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        charter = charter_for(source)
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/graphql"
        ctx = {
            "base": base,
            "currency": source.currency or "UNKNOWN",
            # What the STOREFRONT shows, which is what a simple product's and a
            # grouped member's figure is.
            "vat": "1" if source.vat_mode.value == "incl" else "0",
            "country_code_alpha2": source.default_region,
            # ...and what a CONFIGURABLE's figure is, which on this platform is
            # a different answer (see _product_rows). tax_included is a fact
            # about the number in the row, not about the source, so the two
            # travel separately and every row states its own.
            "configurable_excl": bool(source.api
                                      and source.api.configurable_prices_exclude_tax),
            "vat_configurable": (
                "0" if (source.api and source.api.configurable_prices_exclude_tax)
                else ("1" if source.vat_mode.value == "incl" else "0")),
        }
        notes: list[str] = []
        ctx["notes"] = notes
        ctx["paths"] = self._category_map(endpoint, source, notes)
        # The SAME tree, read in English: leaf uids are store-independent, so
        # one extra categoryList query relabels every path the walk already
        # found — no second product listing, no second crawl (owner's standing
        # bilingual rule).
        ctx["paths_en"] = self._category_labels(endpoint, notes)
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        english = self._english_names(endpoint, notes,
                                      enriched=wants_enrichment)
        ctx["names_en"] = english["names"]
        # The English attribute values, for the brand on the price row. They
        # were already fetched for the enrichment pass; the price row simply
        # had no way to reach them.
        ctx["details_en"] = english.get("details", {})
        # The brand is HALF this store's, and the other half is in the price key.
        # So a failed English pass may not be allowed to publish the Arabic half
        # alone: that keeps the field set identical while the digest changes,
        # which the history layer can only read as a price change — on prices
        # that never moved, into an append-only table. Suppressing BOTH halves
        # drops `brand` out of the key's field set instead, and the run is then
        # told apart as fields_changed, which is what actually happened.
        #
        # Only when enrichment was asked for: without it details_en is empty by
        # design every run, the pair is Arabic-only every run, and suppressing it
        # would invent the very instability this prevents.
        ctx["brand_pair_unreliable"] = wants_enrichment and not english.get("ok", True)
        # A defect, not a warning: the rows this run is about to write are known
        # to carry less than the source publishes, and a run that writes them
        # may not report clean (Q3/S8).
        defects: list[str] = []
        if ctx["brand_pair_unreliable"]:
            defects.append(
                "the English store did not answer, so the brand pair was left "
                "out of every row this run rather than published half — the "
                "prices are correct, the brand column is empty, and re-running "
                "when the store answers restores it")
        ctx["axis_labels_en"] = english["axis_labels"]
        ctx["axis_values_en"] = english["axis_values"]
        # The unit the shop states its weights in, read once and stamped on
        # every row that carries a weight — the qualifier travels with the
        # number it qualifies, same rule as `currency`.
        ctx["weight_unit"] = self._weight_unit(endpoint, notes)
        query = _QUERY_ENRICHED if wants_enrichment else _QUERY
        fetched: list[dict] = []      # kept so enrichment needs no second fetch
        page = 1
        while True:
            token = f"page-{page}"
            if token in self.skip_tokens:
                # BEFORE the request, which is the whole point. This check used
                # to sit below the POST, so a resumed crawl re-issued every
                # request and saved only the parsing — and because `if not
                # items: break` was below it too, the loop's TERMINATION was
                # driven by freshly fetched responses as well. A resumed crawl
                # was network-identical to a cold one: resume in name only.
                page += 1
                continue
            body = {"query": query, "variables": {"pageSize": PAGE_SIZE, "currentPage": page}}
            products = (((self._fetcher.post(endpoint, json=body).json() or {})
                         .get("data") or {}).get("products")) or {}
            items = products.get("items") or []
            if not items:
                break
            # Warnings raised while building THIS page must ride this page.
            # Pinning them all to page 1 (as before) silently dropped every
            # skip a later page reported — and a skip nobody hears is the
            # quiet data loss the warnings exist to prevent.
            before = len(notes)
            page_rows: list[list[str]] = []
            for product in items:
                made = self._product_rows(builder, product, ctx)
                for built in made:
                    _apply_charter(built, charter, product)
                page_rows.extend(made)
                if made and wants_enrichment:
                    # Details hang off the PRICE row's product, so the
                    # enrichment set follows the priced set. A product this
                    # page refused (a real price RANGE, a grouped product
                    # whose members carry no figure) that still shipped its
                    # attributes would send details for something the
                    # warehouse has never heard of — rejected out of scope,
                    # and looking for all the world like a contract breach.
                    fetched.append(product)
            # One table per page: a pause keeps every page already fetched
            # and the resume asks only for the rest.
            yield ScrapedTable(
                source_key=source.source_key, kind=PRODUCT_PRICES.kind,
                source_url=f"{endpoint}#page={page}", header=builder.header,
                rows=page_rows,
                warnings=list(notes) if page == 1 else notes[before:],
                defects=list(defects),
                page_token=token,
            )
            total_pages = ((products.get("page_info") or {}).get("total_pages")) or page
            # The store has just told us how many listing pages there are, so
            # from here the crawl's size is known rather than guessed. Declared
            # every page (expect_requests only ever raises the number) because
            # total_pages can grow under us on a live catalogue, and minus the
            # pages a resume already holds, which cost no request.
            declare_frontier(self._fetcher,
                             len([p for p in range(page + 1, int(total_pages) + 1)
                                  if f"page-{p}" not in self.skip_tokens]))
            if page >= total_pages:
                break
            page += 1
        # The details the same responses already carried — descriptions and
        # per-variant weights — cost no extra request. Only when the manifest
        # asks (same gate as the woo connector).
        if wants_enrichment:
            extra = RowBuilder(ENRICHMENT)
            attribute_rows: list[list[str]] = []
            filterable = self._filterable(endpoint, notes)
            # The human label for EVERY attribute, in each store's own
            # words — «المصنع» beside "Manufacturer" — where the facet list
            # only ever labelled what the shop filters by.
            codes = ({str(a.get("code") or "")
                      for product in fetched
                      for a in ((product.get("custom_attributesV2") or {})
                                .get("items")) or []}
                     # The meta codes are asked for by name rather than taken
                     # from the visible-attribute bag, so they would otherwise
                     # never reach the label query and would print as raw codes.
                     | set(_META_FIELDS)) - {""}
            labels_ar = self._attribute_labels(endpoint, None, notes, codes)
            labels_en = self._attribute_labels(endpoint, _ENGLISH_STORE, notes, codes)
            unknown_codes: set[str] = set()
            for product in fetched:
                attribute_rows.extend(_enrichment_rows(
                    extra, product, filterable,
                    labels_ar=labels_ar, labels_en=labels_en,
                    english=english.get("details", {}),
                    unknown_codes=unknown_codes))
            if unknown_codes:
                # ONE line, not one per row: the owner is asked where a new
                # kind of fact belongs, and a hundred repetitions of the
                # same question is how a rule stops being read.
                notes.append(
                    "these detail codes are new and were filed under More "
                    "information by default — decide where they belong and "
                    "add them to vocab._DETAIL_GROUP_BY_CODE: "
                    + ", ".join(sorted(unknown_codes)[:20]))
            if attribute_rows:
                yield ScrapedTable(
                    source_key=source.source_key, kind=ENRICHMENT.kind,
                    source_url=endpoint, header=extra.header,
                    rows=attribute_rows,
                )

    def _attribute_labels(self, endpoint: str, store: str | None,
                          notes: list, codes: set[str] | None = None) -> dict:
        """attribute code -> the store's own human label, for EVERY attribute.

        The owner's report, with a screenshot: the site prints «المصنع»,
        «بلد المنشأ», «الطول (متر)» — and the panel showed manufacturer,
        origin, length_cm, because only the facet subset had ever been asked
        for its words. Failure costs the labels and nothing else: the codes
        still identify the facts, exactly as before.
        """
        safe = sorted(c for c in (codes or set()) if _ATTRIBUTE_CODE_SAFE.match(c))
        if not safe:
            return {}
        query = _ATTRIBUTE_LABELS_QUERY.format(attrs=",".join(
            '{attribute_code:"%s",entity_type:"catalog_product"}' % c
            for c in safe))
        try:
            headers = {"Store": store} if store else None
            answer = (self._fetcher.post(endpoint, json={"query": query},
                                         headers=headers)
                      if headers else
                      self._fetcher.post(endpoint, json={"query": query})
                      ).json() or {}
            items = (((answer.get("data") or {})
                      .get("customAttributeMetadataV2")) or {}).get("items") or []
            found = {str(i.get("code") or ""): str(i.get("label") or "")
                     for i in items if i.get("code") and i.get("label")}
            # SAY when the shop declines to name an attribute. Until now only a
            # request that RAISED was reported, so a code that came back with no
            # label at all was silent — the panel simply printed the bare code
            # and it read as a bug nobody had fixed. 420 rows sat like that
            # across two "fixed" crawls precisely because nothing said anything.
            #
            # It is not an error and not a failure: madar publishes no word for
            # these, and inventing one would put text on the page that the site
            # never wrote (the owner's rule). Naming them is the whole fix — the
            # owner can then see it is the shop's silence, not ours.
            declined = sorted(set(safe) - set(found))
            if declined:
                notes.append(
                    f"{store or 'the default store'} states no label for "
                    f"{len(declined)} attribute(s); the code stands in: "
                    + ", ".join(declined[:12])
                    + (f" (+{len(declined) - 12} more)" if len(declined) > 12 else ""))
            return found
        except CrawlBlocked:
            raise
        except Exception as exc:
            notes.append(f"attribute labels unavailable for "
                         f"{store or 'the default store'} — codes stand in: {exc}")
            return {}

    def _filterable(self, endpoint: str, notes: list) -> dict:
        """attribute_code -> the site's own label, for every attribute it FILTERS by.

        The owner: «وجدت ان الموقع يتيح الفلاتر فى بعض صفحات المنتجات اريد
        اضافة اعمدة خاصة بهذه الفلاتر» — the site offers filters on some listing
        pages, and he wants columns for them so he can filter his own way.
        `aggregations` is the site answering exactly that question about itself,
        so the set is the shop's, never a list we curated. One request.

        A failure here costs the LABELS and the Filters grouping, nothing else:
        the attributes still travel as "More information" rows, which is what
        they were before this existed.
        """
        try:
            answer = (self._fetcher.post(endpoint, json={"query": _AGGREGATIONS_QUERY})
                      .json() or {})
        except CrawlBlocked:
            raise
        except Exception as exc:
            notes.append(f"filters: aggregations unavailable ({exc}) — the site's "
                         "filterable attributes stay under More information")
            return {}
        aggregations = (((answer.get("data") or {}).get("products")) or {}).get("aggregations") or []
        found: dict[str, str] = {}
        for aggregation in aggregations:
            code = str(aggregation.get("attribute_code") or "")
            # `price` and `category_id` are facets over columns the table
            # already has; repeating them as attributes would file the same
            # fact twice under two names.
            if not code or code in {"price", "category_id", "category_uid"}:
                continue
            found[code] = str(aggregation.get("label") or "") or code
        return found

    def _weight_unit(self, endpoint: str, notes: list) -> str:
        """The unit this store states its `weight` values in — or "" if it won't say.

        One request per crawl, on every crawl. The answer qualifies a NUMBER
        that ends up beside a price, so silence here has to cost the whole
        basis rather than be papered over: without a unit from the shop, the
        display layer shows no basis at all, and the price cell reads exactly
        as it does today. That is the same refusal selling_unit_from makes when
        a name and a weight disagree — publishing 1000 with a unit nobody
        stated is the one outcome this whole change exists to avoid.
        """
        try:
            answer = (self._fetcher.post(endpoint, json={"query": _STORE_CONFIG_QUERY})
                      .json() or {})
        except CrawlBlocked:
            raise
        except Exception as exc:
            notes.append(f"the store did not state the unit of its weights ({exc}) "
                         "— prices quoted against a weight show no basis this run")
            return ""
        stated = str((((answer.get("data") or {}).get("storeConfig")) or {})
                     .get("weight_unit") or "")
        if not stated:
            notes.append("storeConfig published no weight_unit — prices quoted "
                         "against a weight show no basis this run")
        return stated

    def _english_names(self, endpoint: str, notes: list,
                       enriched: bool = False) -> dict:
        """The en_SA store view, read once, for everything it says in English.

        Returns {"names": {uid: name}, "axis_labels": {code: label},
                 "axis_values": {child_uid: {code: label}},
                 "details": {uid: {"description": str, "short_description": str,
                                   "attributes": {code: value}}}}.

        `enriched` swaps in the query that also carries descriptions and
        attribute values — the same pages the names already cost, so the
        English half of every detail is free.

        Verified live: "اسمنت الرياض" -> "Riyadh Cement", and «العرض (ملم)» ->
        "Width (mm)". The axes ride the SAME pages the names already cost, so
        the second language of a variation is free — which matters, because the
        owner's rule is that a translation the site publishes and we drop is a
        defect, and this store publishes every axis twice.

        Failure degrades to Arabic-only WITH a note. That used to end "prices are
        never at stake", and it stopped being true the day the brand entered the
        price key: half a pair («السويدي» without "SWEDY") hashes to a different
        digest under an UNCHANGED field set, which reads as every offer's price
        moving. `ok` is therefore part of the answer, and the caller suppresses
        the pair rather than publishing half of it — see _manufacturer.
        """
        names: dict[str, str] = {}
        axis_labels: dict[str, str] = {}
        axis_values: dict[str, dict[str, str]] = {}
        details: dict[str, dict] = {}
        try:
            page = 1
            while True:
                body = {"query": _EN_QUERY_ENRICHED if enriched else _EN_QUERY,
                        "variables": {"pageSize": PAGE_SIZE, "currentPage": page}}
                answer = (self._fetcher.post(endpoint, json=body,
                                             headers={"Store": _ENGLISH_STORE})
                          .json() or {})
                products = ((answer.get("data") or {}).get("products")) or {}
                items = products.get("items") or []
                if not items:
                    break
                for item in items:
                    uid = str(item.get("uid") or "")
                    if uid and item.get("name"):
                        names[uid] = str(item["name"])
                    if enriched and uid:
                        # Empty values are dropped here and not in the shared
                        # reader: an attribute the store answers as blank is
                        # "the en store says nothing", and carrying it would
                        # overwrite the Arabic half with nothing downstream.
                        attributes = {code: value for code, value
                                      in _attribute_values(item).items() if value}
                        details[uid] = {
                            "description": _clean(((item.get("description") or {})
                                                   .get("html")) or ""),
                            "short_description": _clean(
                                ((item.get("short_description") or {})
                                 .get("html")) or ""),
                            "attributes": attributes,
                            # About the PAGE, not the product — see
                            # _META_FIELDS. Bilingual like everything else: the
                            # two stores write their own.
                            "meta": {code: str(item.get(code) or "")
                                     for code in _META_FIELDS},
                        }
                    # The axis NAME is per attribute and shared by every product
                    # that varies by it, so one map serves the whole crawl.
                    for option in item.get("configurable_options") or []:
                        code = str(option.get("attribute_code") or "")
                        if code and option.get("label"):
                            axis_labels[code] = str(option["label"])
                    # A GROUPED member's English name. It is not decoration:
                    # the member name is what the page prints beside each
                    # member's price, so it IS this row's variant label, and
                    # the English half of it was being dropped for all 161
                    # members on the source. `items` is the grouped selection;
                    # `variants` below is the configurable one.
                    for member in item.get("items") or []:
                        child = member.get("product") or {}
                        cuid = str(child.get("uid") or "")
                        if cuid and child.get("name"):
                            names[cuid] = str(child["name"])
                    for v in item.get("variants") or []:
                        child = v.get("product") or {}
                        cuid = str(child.get("uid") or "")
                        if cuid and child.get("name"):
                            names[cuid] = str(child["name"])
                        # The axis VALUE is per variant: a width reads 610 in
                        # both stores, a colour does not.
                        if cuid:
                            for attribute in v.get("attributes") or []:
                                code = str(attribute.get("code") or "")
                                if code and attribute.get("label"):
                                    axis_values.setdefault(cuid, {})[code] = str(attribute["label"])
                total = ((products.get("page_info") or {}).get("total_pages")) or page
                if page >= total:
                    break
                page += 1
        except CrawlBlocked:
            raise
        except Exception as exc:
            notes.append(f"english-names pass failed — names and variations stay "
                         f"Arabic-only this run: {exc}")
            return {"names": {}, "axis_labels": {}, "axis_values": {},
                    "details": {}, "ok": False}
        return {"names": names, "axis_labels": axis_labels,
                "axis_values": axis_values, "details": details, "ok": True}

    def _category_labels(self, endpoint: str, notes: list) -> dict:
        """leaf uid -> English path, from the en_SA tree. {} when unavailable."""
        labels: dict[str, str] = {}
        try:
            answer = (self._fetcher.post(endpoint, json={"query": _TREE_QUERY},
                                         headers={"Store": _ENGLISH_STORE})
                      .json() or {})
            roots = (((answer.get("data") or {}).get("categoryList") or [{}])[0]
                     .get("children")) or []

            def walk(node: dict, trail: list) -> None:
                name = str(node.get("name") or "").strip()
                uid = str(node.get("uid") or "")
                if not name or not uid:
                    return
                here = [*trail, name]
                labels[uid] = " > ".join(here)
                for child in node.get("children") or []:
                    walk(child, here)

            for root in roots:
                walk(root, [])
        except CrawlBlocked:
            raise
        except Exception as exc:
            notes.append(f"english category tree unavailable — classification "
                         f"stays Arabic-only this run: {exc}")
        return labels

    def _category_map(self, endpoint: str, source: SourceEntry,
                      notes: list[str]) -> dict[str, tuple[str, str]]:
        """product uid -> (category_path, leaf uid), from walking the tree.

        The walk KNOWS each leaf's full path, so the per-leaf query fetches
        nothing but product uids. A product filed in several places keeps its
        DEEPEST home. When the manifest targets categories (spec.categories),
        only those subtrees are walked — the owner's targeted mode for free.
        Any failure here degrades to no classification WITH a note, never to a
        lost price crawl.
        """
        wanted: set[str] = set()
        for spec in source.extract:
            wanted.update(spec.categories or [])
        paths: dict[str, tuple[str, str]] = {}
        try:
            answer = (self._fetcher.post(endpoint, json={"query": _TREE_QUERY}).json()
                      or {})
            roots = (((answer.get("data") or {}).get("categoryList") or [{}])[0]
                     .get("children")) or []

            def walk(node: dict, trail: list[str]) -> None:
                name = str(node.get("name") or "").strip()
                uid = str(node.get("uid") or "")
                if not name or not uid:
                    return
                here = [*trail, name]
                children = node.get("children") or []
                for child in children:
                    walk(child, here)
                if children:
                    return              # only LEAVES list products; parents repeat them
                # WHY PARENTS STILL DO NOT LIST, measured rather than assumed
                # (live A/B, 2026-07-29). 90 of madar's 761 products carry no
                # classification, and the obvious theory — "they are filed on a
                # branch node, and only leaves are listed here" — is wrong.
                # Listing all 17 branch nodes as well as the 56 leaves reaches
                # 671 products instead of 669: it finds TWO, for a 30% larger
                # category walk on a source that crawls daily.
                #
                # The other 88 are the shop's own silence. Asked directly, they
                # answer `categories: []` (71231005, 70402032, 70601014 all
                # verified), and no listing anywhere in the tree returns them.
                # They are not mis-filed by this walk; they are unfiled by
                # madar. That is a fact to record, not a bug to fix here, and
                # no amount of extra listing will reach them.
                if wanted and uid not in wanted and not (set(here) & wanted):
                    return
                path = " > ".join(here)
                page = 1
                while True:
                    body = {"query": _LEAF_PRODUCTS_QUERY,
                            "variables": {"uid": uid, "pageSize": PAGE_SIZE,
                                          "currentPage": page}}
                    listing = (((self._fetcher.post(endpoint, json=body).json() or {})
                                .get("data") or {}).get("products")) or {}
                    for item in listing.get("items") or []:
                        puid = str(item.get("uid") or "")
                        if puid and _depth(path) > _depth(paths.get(puid, ("", ""))[0]):
                            paths[puid] = (path, uid)
                    total = ((listing.get("page_info") or {}).get("total_pages")) or page
                    if page >= total:
                        break
                    page += 1

            for root in roots:
                walk(root, [])
        except CrawlBlocked:
            raise
        except Exception as exc:
            notes.append(f"category tree walk failed — rows carry no "
                         f"classification this run: {exc}")
            return {}
        if not paths:
            notes.append("category tree walk found no products — rows carry "
                         "no classification this run")
        return paths

    @staticmethod
    def _product_rows(builder: RowBuilder, product: dict, ctx: dict) -> list[list[str]]:
        url_key = product.get("url_key") or ""
        # THE BRAND. madar states it as the `manufacturer` attribute — on 536
        # of its 763 products, in both stores — and this connector emitted no
        # brand at all, so the column sat empty on the largest source in the
        # warehouse while the answer was sitting in the details panel.
        # Read per language from the store that published it, never split by
        # script: the two stores ARE the two languages, so there is nothing to
        # guess at.
        brand_ar, brand_en = _manufacturer(product, ctx.get("details_en") or {},
                                           unreliable=bool(ctx.get("brand_pair_unreliable")))
        url = f"{ctx['base']}/{url_key}.html" if url_key else ""
        variants = product.get("variants") or []
        # Classification belongs to the PRODUCT: every variant of it files in
        # the same place, so it is read once and rides every row. Two sources
        # of truth, deepest wins: what the product payload states (fully
        # populated on stock Magento) and what the tree walk found (madar's
        # census answers categories:[] while its tree knows the real home).
        stated_path, stated_id = _classification(product)
        walked_path, walked_id = (ctx.get("paths") or {}).get(
            str(product.get("uid") or ""), ("", ""))
        if _depth(walked_path) > _depth(stated_path):
            category_path, category_id = walked_path, walked_id
        else:
            category_path, category_id = stated_path, stated_id
        # The leaf's uid is the join: the same filing, said in English.
        category_path_en = (ctx.get("paths_en") or {}).get(category_id, "")
        if category_path_en == category_path:
            category_path_en = ""      # a monolingual tree repeats itself
        out: list[list[str]] = []

        names_en = ctx.get("names_en") or {}
        axis_labels_en = ctx.get("axis_labels_en") or {}
        axis_values_en = ctx.get("axis_values_en") or {}
        option_labels = {str(o.get("attribute_code") or ""): str(o.get("label") or "")
                         for o in product.get("configurable_options") or []}

        # The CONFIGURABLE's own sku, so a child's sku stops standing in for its
        # parent's (B11). Magento children carry their own skus and nothing else
        # recorded which product they belonged to.
        parent_sku = str(product.get("sku") or "")

        # HOW THE PAGE PRESENTS THIS PRODUCT — read once, because it is a
        # property of the PRODUCT and identical on every row it emits. What one
        # unit of the price BUYS is the other question, and it is answered per
        # row below, because it genuinely differs per member.
        display = _display_method(product)

        def row(pid, vid, sku, name, reg, fin, stock, label="", fp="",
                basis="", unit="", vat=None, axes=None, axes_en=None,
                variant_en="", quantity=("", "", ""), stock_qty=None,
                weight=None):
            effective = fin if fin is not None else reg
            if effective is None:
                return  # a product with no price — skip, don't emit an empty required field
            minimum, increment, is_decimal = quantity
            out.append(builder.row(
                external_product_id=pid, external_variant_id=vid, external_sku=sku or "",
                # The PRODUCT's English name, never the child's — madar names
                # its variant children by internal SKU string in BOTH stores,
                # so asking the child first put "618097 1 GANG RJ11 SOCKET
                # WHITE ELOE LEGRAND" where the page says "Legrand Eloe
                # telephone and data sockets". Same rule as the Arabic name.
                product_name=names_en.get(str(pid)) or names_en.get(str(vid)) or "",
                product_name_ar=name or "",
                brand=brand_en, brand_ar=brand_ar,
                # Only on a real child: a simple product is its own parent, and
                # writing its sku here would invent a hierarchy it does not have.
                parent_sku=parent_sku if str(vid) != str(pid) else "",
                # NOT variant_url. Magento selects a configurable's child by
                # option rather than by address, and the variants{} selection
                # asks for no url_key because the child has no page of its own to
                # link to. An empty column here is the truth; inventing
                # `?option=` would be a link that answers with the parent.
                variant_url="",
                variant_ar=label, option_fingerprint=fp,
                # The axes as STRUCTURE beside the sentence built from them.
                # `_option_text` composes «السماكة (مم): 2.2، العرض (مم): 24»
                # for a person to read; a spreadsheet needs one column per
                # axis, and the parts were being discarded the moment the
                # sentence existed (the owner's report, fixed at the root).
                variant_axes_ar=option_axes_json(axes or {}),
                # The same variation in English, when the en_SA store publishes
                # it. Composed with the SAME rule as the Arabic label so the two
                # read alike — «العرض (ملم): 610» / "Width (mm): 610" — instead
                # of one being a sentence and the other a list.
                #
                # `variant_en` overrides it for a GROUPED member, whose label is
                # not built from axes at all: the member has no axes, its NAME
                # is its label, and building this column only from axes_en is
                # why all 162 grouped variants stored variant='' while the site
                # published 161 English member names.
                variant=variant_en or ", ".join(
                    f"{axis}: {value}" for axis, value in (axes_en or {}).items()),
                variant_axes=option_axes_json(axes_en or {}),
                basis_quantity=basis, unit=unit,
                # WHAT THE SITE SAYS ABOUT THE QUANTITY, and only what it says.
                minimum_quantity=minimum, quantity_increment=increment,
                quantity_is_decimal=is_decimal,
                # THE WEIGHT THE SITE PUBLISHES FOR THIS LEAF, beside the unit
                # the STORE says its weights are in. Asked for since 0056 and
                # until now delivered only to selling_unit_from, which throws
                # it away unless the product's NAME corroborates it — so the
                # rebar's 1000 was fetched and dropped on every crawl.
                #
                # NOT interpreted here. This connector does not decide whether
                # 1000 is a basis or a mass; it records that the shop said
                # 1000 kgs, next to the shop saying the quantity is decimal,
                # and the display layer reads the two together. The unit is
                # dropped when there is no weight to qualify — a store-wide
                # constant on a row that carries no number is noise.
                weight="" if weight in (None, "") else str(weight),
                weight_unit=("" if weight in (None, "")
                             else (ctx.get("weight_unit") or "")),
                # HOW THE PAGE PRESENTS THE PRODUCT — constant across its rows.
                display_method=display,
                # The shop's own count when it publishes one. rowspec and ingest
                # have both handled this column since before this connector
                # existed; the query simply never asked for it.
                stock_quantity="" if stock_qty is None else str(stock_qty),
                # The language of THIS pass. The connector already asserts it by
                # writing the default store's name into product_name_ar and
                # reading English from _ENGLISH_STORE; naming it here just stops
                # the claim being implicit.
                lang=_PRIMARY_LANG,
                product_link=url, country_code_alpha2=ctx["country_code_alpha2"], currency=ctx["currency"],
                # PER ROW, never per source: on this platform one crawl carries
                # both answers at once, and a source-level flag stamped on
                # every observation is how the warehouse came to assert things
                # the shop never said.
                tax_included=vat if vat is not None else ctx["vat"],
                price_before=reg if reg is not None else effective,
                price_sale=fin if (reg is not None and fin is not None and reg != fin) else "",
                price=effective, availability=_availability(stock),
                category_path=category_path_en, category_path_ar=category_path,
                category_external_id=category_id,
            ))

        shape = str(product.get("__typename") or "")
        notes = ctx.setdefault("notes", [])

        # ---- GROUPED: the page has no product price, only its members' -------
        #
        # Study B1 (2026-07-25), read off the live storefront: a GroupedProduct
        # page prints NO single figure. It prints «المقاسات/الأنواع المتوفرة»
        # and then one price per member, and those member prices equal the
        # API's member prices exactly (swedish-redwood: 28 of 28, 1,449.00 ..
        # 2,233.88). The GROUP's own price_range is not a range at all —
        # Magento answers maximum_price == minimum_price on every one of the 33
        # groups even when the members really do span 55%, so the group figure
        # is the CHEAPEST member wearing the group's identity. Emitting it as
        # "the price of الخشب الأحمر السويدي" states a number the page never
        # presents as that product's price, which is precisely the range-as-a-
        # single-price defect. One row per member instead: each carries a price
        # the visitor can actually read, beside the member name printed next
        # to it.
        if shape == "GroupedProduct":
            members = product.get("items") or []
            for member in members:
                child = member.get("product") or {}
                # A member is a simple product with a group for a parent: its
                # own price matched the page 28/28 on swedish-redwood, so it
                # carries the storefront's vat state like any simple row.
                reg, fin = _prices(child)
                basis, unit = selling_unit_from(child.get("name") or "",
                                                child.get("weight"))
                row(product.get("uid"), child.get("uid"), child.get("sku"),
                    product.get("name") or child.get("name"), reg, fin,
                    child.get("stock_status"),
                    # The member's own name is what the page prints beside its
                    # price — it IS the label that tells the two apart.
                    label=str(child.get("name") or ""),
                    # ...and the en_SA store publishes that same label in
                    # English for 161 of 161 members, 150 of them genuinely
                    # different from the Arabic. Keyed by the member's uid,
                    # which `names_en` only learns now that _EN_QUERY carries a
                    # GroupedProduct fragment — both halves of this fix are
                    # needed, either alone leaves the column empty.
                    variant_en=names_en.get(str(child.get("uid") or "")) or "",
                    fp=option_fingerprint({"member": str(child.get("sku") or "")})
                    if child.get("sku") else "",
                    basis=basis, unit=unit,
                    quantity=_quantity_facts(child),
                    # The member's OWN weight — the group publishes none. This
                    # is the 1000 the rebar has been stating all along, and the
                    # `... on PhysicalProductInterface` fragment in the query
                    # is what reaches it: `weight` is not on ProductInterface,
                    # so a member selection without that fragment is refused by
                    # the schema outright.
                    weight=child.get("weight"),
                    stock_qty=child.get("only_x_left_in_stock"))
            if not out:
                # Never fall back to the group figure: it is the cheapest
                # member's price under the group's name, and saying nothing is
                # honest where saying that is not.
                notes.append(
                    f"{product.get('name')} ({product.get('sku')}): grouped product "
                    "whose members carry no readable price — skipped rather than "
                    "stored at the group's minimum, which is one member's price "
                    "wearing the group's name")
            return out

        # ---- CONFIGURABLE: the API's figure is the page's EXCL-of-tax one ----
        #
        # The storefront LABELS its own price fields — «finalPriceExclTaxKey =
        # 'basePrice'», «finalPriceInclTaxKey = 'finalPrice'» — and then, for
        # 12512-TSP, publishes
        #   "prices":{"basePrice":{"amount":50.4},"finalPrice":{"amount":57.96}}
        # with initialFinalPrice: 57.96. GraphQL answers 50.4. Re-verified live
        # 2026-07-25 by a second pass that fetched the page itself; the same
        # page carries «الأسعار تشمل ضريبة القيمة المضافة 15%», and the same
        # check on SimpleProduct 71231005 gave API 65.21 / page 65.205 — no gap
        # at all. This is also what the Legrand floor box (60402-LPF, a
        # CONFIGURABLE) was saying on 2026-07-23 at 194.9 vs 224.14, and why
        # commit 53b2407's counter-examples (putty-1-kg-sab,
        # uib-oxidized-bitumen — both SIMPLE) were equally true. Every reading
        # was right; only generalising one shape's rule to the source was not.
        #
        # What we do about it is NOT arithmetic. The row keeps 50.4 and says
        # tax_included=0, so the Tax column reads "Excl. 15%" on this row and
        # "Incl. 15%" on the simple one beside it. Both numbers then exist on
        # the site, which is the only test a stored price has to pass.
        if variants:
            variant_vat = (ctx.get("vat_configurable") or ctx["vat"]
                           if shape == "ConfigurableProduct" else ctx["vat"])
            # An undeclared source is recorded at its storefront's vat_mode —
            # never silently converted — but madar taught us that this shape is
            # where the two answers diverge, so a run says so once instead of
            # letting a future store repeat the 3,312-row mistake in silence.
            if shape == "ConfigurableProduct" and not ctx.get("configurable_excl"):
                marker = "configurable prices recorded at the source's declared vat_mode"
                if not any(marker in n for n in notes):
                    notes.append(
                        f"{marker} — on madar this shape's GraphQL figure is the "
                        "storefront's tax-EXCLUSIVE one (its own basePrice field) "
                        "while a SimpleProduct's is the printed price. If this "
                        "store does the same, declare "
                        "api.configurable_prices_exclude_tax so these rows say "
                        f"so. First: {product.get('name')} ({product.get('sku')})")
            for v in variants:
                child = v.get("product") or {}
                attrs = [a for a in (v.get("attributes") or []) if a.get("code")]
                reg, fin = _prices(child)
                # The basis the site itself states (weight + "50كجم" in the
                # name agreeing) rides the row; a piece's mass does not.
                basis, unit = selling_unit_from(child.get("name") or "",
                                                child.get("weight"))
                # The PRODUCT's name, never the child's: madar's child name is
                # its internal SKU string ("054010 FLOOR BACK BOX POPUP ALU
                # 3MOD LEGRAND", identical in both stores) while the product
                # carries the real localized name — «علب أرضية منبثقة من
                # ليجراند» / "Legrand Pop-up Floor Box Kit". Storing the SKU
                # string put an English code where the page shows Arabic and
                # contradicted the row's own variant label (owner-reported).
                row(product.get("uid"), child.get("uid"), child.get("sku"),
                    product.get("name") or child.get("name"), reg, fin, child.get("stock_status"),
                    label=_option_text(attrs, option_labels),
                    fp=option_fingerprint({a["code"]: a.get("label", "") for a in attrs}) if attrs else "",
                    # Keyed by the site's own axis LABEL, not its internal code:
                    # a column headed «السماكة (مم)» is readable, one headed
                    # `thickness_mm` is our vocabulary imposed on the shop's.
                    # The code stays the fingerprint's key, where stability
                    # matters more than legibility.
                    axes={option_labels.get(str(a.get("code") or ""), str(a.get("code") or "")):
                          str(a.get("label") or "") for a in attrs},
                    # English axis NAME from the store-wide map, English VALUE
                    # from this child's own attributes — a width reads 610 in
                    # both stores, a colour does not. Falls back to the Arabic
                    # value rather than dropping the axis: a half-translated
                    # variation still says which variation it is.
                    axes_en={axis_labels_en[code]: (axis_values_en.get(str(child.get("uid") or ""), {}).get(code)
                                                    or str(a.get("label") or ""))
                             for a in attrs
                             for code in [str(a.get("code") or "")]
                             if code in axis_labels_en},
                    basis=basis, unit=unit, vat=variant_vat,
                    quantity=_quantity_facts(child),
                    # Per CHILD, never the parent's: madar's steel mesh states
                    # 6.74 .. 66.02 kg across its thirteen children, so one
                    # figure for the family would be wrong twelve times.
                    weight=child.get("weight"),
                    stock_qty=child.get("only_x_left_in_stock"))
        else:
            # A product standing alone must have ONE price, not a span. Every
            # SimpleProduct in the live census (399 of 399) answers
            # maximum_price == minimum_price, so this never fires for the shape
            # we have; it is here for the shape we do not — a BundleProduct
            # publishes a real min..max, and writing its minimum into
            # price would file "from 50" as "50". A shape we have not
            # studied is not a shape we may guess at.
            if _spans_a_range(product):
                notes.append(
                    f"{product.get('name')} ({product.get('sku')}): "
                    f"{shape or 'this product'} publishes a price RANGE "
                    f"({_range_text(product)}), not a price — skipped rather "
                    "than stored at the range's low end")
                return out
            reg, fin = _prices(product)
            # A simple product IS its own leaf, so its quantity facts and its
            # stock count sit on the product node itself.
            row(product.get("uid"), product.get("uid"), product.get("sku"),
                product.get("name"), reg, fin, product.get("stock_status"),
                quantity=_quantity_facts(product),
                weight=product.get("weight"),
                stock_qty=product.get("only_x_left_in_stock"))
        return out


def _attribute_values(product: dict) -> dict[str, str]:
    """code -> value for one product's custom attributes, in ONE reading rule.

    Magento answers an attribute as either a plain `value` or a set of
    `selected_options` labels, so every reader must cover both — and this rule
    was written out three times: the English pass, the brand, and the enrichment
    rows. It stays HERE and not in normalize: this is the shape of a GraphQL
    union in one platform's API, not a normalization rule shared across sources,
    and moving it up would be the premature abstraction A3/P3 forbid.
    """
    values: dict[str, str] = {}
    for attribute in ((product.get("custom_attributesV2") or {}).get("items")) or []:
        code = str(attribute.get("code") or "")
        if not code:
            continue
        value = attribute.get("value") or ", ".join(
            str(option.get("label") or "")
            for option in attribute.get("selected_options") or [] if option.get("label"))
        values[code] = str(value or "")
    return values


def _manufacturer(product: dict, details_en: dict,
                  *, unreliable: bool = False) -> tuple[str, str]:
    """madar's brand, per language, from the store that published it.

    `unreliable` is the English store having been asked and having failed. The
    pair is then suppressed WHOLE. Publishing the Arabic half alone would keep
    the price key's field set identical while changing its digest, and the only
    reading of that is "the price moved" — recorded once, in an append-only
    table, for every offer the source publishes. An absent brand is a smaller,
    truthful, reversible loss: the next run that reaches the store restores it.

    The same `manufacturer` attribute the "More information" panel prints. It
    stays a detail as well as becoming a column: the shop prints it on the page,
    and removing it from the panel would hide something the page says.

    Whatever the shop wrote is what travels — a country typed into the field,
    «مصنع حديد» where a name belongs, `Gaint` for Giant. The owner's rule is
    that the site's text is the record, because the shop will correct it and a
    cleaning rule here would hide the day it did.
    """
    if unreliable:
        return "", ""
    arabic = _attribute_values(product).get("manufacturer", "")
    english = str((details_en.get(str(product.get("uid") or "")) or {})
                  .get("attributes", {}).get("manufacturer", "") or "")
    return arabic.strip(), english.strip()


def _enrichment_rows(builder: RowBuilder, product: dict, filterable: dict,
                     *, labels_ar: dict | None = None,
                     labels_en: dict | None = None,
                     english: dict | None = None,
                     unknown_codes: set | None = None) -> list:
    """Descriptions and per-variant weights the census already carried.

    The weight lands here ONLY when it is not the selling basis: cement's 50
    lives on the price row as "per 50 kg", while a steel angle's 4.986 kg is
    a property of the piece — information, not the unit.

    `filterable` is the site's own facet list (attribute_code -> its label, from
    `aggregations`). An attribute the shop filters by is grouped "Filters" and
    carries the shop's HUMAN label; everything else stays "More information".
    Empty when the aggregations query failed, which costs the grouping and the
    labels and nothing else.
    """
    pid = str(product.get("uid") or "")
    if not pid:
        return []
    rows: list = []

    facets = filterable or {}
    # Codes the shared map did not recognise. The owner's standing rule is
    # that a NEW kind of fact is never filed by judgement — he is asked. A
    # fallback that absorbed them silently would make that rule
    # unenforceable, so the run reports them once.
    unrecognised = unknown_codes if unknown_codes is not None else set()
    labels_ar = labels_ar or {}
    labels_en = labels_en or {}
    mine = (english or {}).get(pid, {})

    def add(code, label, value, *, numeric="", unit="", url="", lang=""):
        if not value:
            return
        # WHERE a reader looks comes from ONE shared map (vocab), never from
        # a connector's own guess. Being a site FACET no longer decides it:
        # that says the shop filters by the fact, which is a property of
        # the fact and now rides is_site_filter, not a place to file it.
        base = code.removesuffix("_ar")
        group, recognised = group_for_code(code)
        if not recognised:
            unrecognised.add(base)
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=str(value), numeric_value=str(numeric), unit_raw=unit,
            value_url=url, lang=lang, attribute_group=group,
            # SEPARATE from the group: this says something about the FACT
            # (the shop offers it as a facet, so a column for it lets the
            # owner slice the table the way the shop slices its listing),
            # not about where a person should look for it.
            is_site_filter="1" if base in facets else ""))

    # The product's pictures, primary first. A placeholder is the site saying
    # "no image" — storing it would put a grey box where a product belongs.
    # Language-neutral: a file is a file, so lang stays unstated.
    #
    # `image` IS the gallery's chosen main on this store: it repeats
    # media_gallery[0] on 575 of the 577 products that publish a gallery (live
    # census 2026-07-30, 761 products). Filing it under both `image` and
    # `image_1` stored ONE picture twice for 576 products and made the panel
    # show every product's main shot as a duplicate, so the URL is
    # de-duplicated — first code wins, which keeps the main image at `image`.
    #
    # The position is counted over what is KEPT, not over what was offered. It
    # used to come from enumerate() BEFORE the placeholder skip, so the one
    # product whose main image is the placeholder while its gallery is real
    # published `image_1` with no `image` at all.
    seen: set[str] = set()
    for media in [product.get("image") or {},
                  *(product.get("media_gallery") or [])]:
        href = str(media.get("url") or "")
        if not href or "placeholder" in href.lower() or href in seen:
            continue
        position = len(seen)
        seen.add(href)
        add(f"image_{position}" if position else "image", "Image",
            str(media.get("label") or "") or href.rsplit("/", 1)[-1], url=href)

    # The code states the language of its content (0039): the unmarked name is
    # English, `_ar` is Arabic, and `lang` beside it says the same thing in the
    # column the migrations read. This crawl reads the DEFAULT (Arabic) store;
    # the English half arrives from the en_SA pass, on pages the names already
    # paid for.
    add("description_ar", "Description (AR)",
        _clean(((product.get("description") or {}).get("html")) or ""),
        lang="ar")
    add("description", "Description", mine.get("description", ""), lang="en")
    add("short_description_ar", "Summary (AR)",
        _clean(((product.get("short_description") or {}).get("html")) or ""),
        lang="ar")
    add("short_description", "Summary", mine.get("short_description", ""),
        lang="en")

    # WHAT THE PAGE SAYS ABOUT ITSELF. Recorded, not reconciled: madar's epoxy
    # rebar reads «سابك» (SABIC) in the AR meta_title while its `name` says «من
    # حديد» (Hadeed) and its image is epoxy_sabic.png. Under "source truth is
    # never edited" the disagreement IS the fact, and the Site metadata group
    # exists so it can be kept without crowding out a product fact.
    meta_en = dict(mine.get("meta", {}))
    for code in _META_FIELDS:
        add(f"{code}_ar", labels_ar.get(code) or facets.get(code) or code,
            str(product.get(code) or ""), lang="ar")
        add(code, labels_en.get(code) or facets.get(code) or code,
            meta_en.get(code, ""), lang="en")

    # The "More information" panel, one row per stated fact — manufacturer,
    # origin, grade, coating... — in the site's own values, labelled in the
    # site's own words per store: «المصنع» beside "Manufacturer" where the
    # panel used to print the raw code (the owner's report, with the page's
    # own tab as evidence).
    english_attributes = dict(mine.get("attributes", {}))
    for code, value in _attribute_values(product).items():
        if code:
            add(f"{code}_ar", labels_ar.get(code) or facets.get(code) or code,
                value, lang="ar")
            en_value = english_attributes.pop(code, "")
            add(code, labels_en.get(code) or facets.get(code) or code,
                en_value, lang="en")
    # An attribute the en store states and the ar store does not — rare, but
    # dropping it would violate the standing rule from the other side.
    for code, value in english_attributes.items():
        add(code, labels_en.get(code) or facets.get(code) or code, value,
            lang="en")

    for v in product.get("variants") or []:
        child = v.get("product") or {}
        weight = child.get("weight")
        if not weight:
            continue
        basis, _unit = selling_unit_from(child.get("name") or "", weight)
        if basis:
            continue      # already the selling basis on the price row
        sku = child.get("sku") or ""
        # A number with an English label of ours: lang says so.
        add("weight", f"Weight — {sku}", weight, numeric=weight, unit="kg",
            lang="en")
    return rows
