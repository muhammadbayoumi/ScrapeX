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
gets stored, for every shape, and what differs per shape is the vat_included
flag the row carries — the owner's ruling after a source-wide 15% uplift was
declared here and put 3,312 wrong prices in the warehouse: «سجلها كما تاخذ
البيانات من الموقع بدون تعديل ولكن عمود الضريبة يكون واضح الرقم دا شامل الضريبة
ام لا». Record it as the site gives it; make the tax column say what it is.
So a configurable row is stored at 50.4 with vat_included=0 and reads "Excl.
15%", where the old code stored 57.96 and claimed the shop had printed it.
"""
from __future__ import annotations

import re

from typing import Iterable

from ..config import SourceEntry
from ..normalize import option_axes_json, option_fingerprint, selling_unit_from
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, ExtractKind
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

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
_QUERY_TEMPLATE = """query($pageSize:Int!,$currentPage:Int!){{
  products(filter:{{price:{{from:"0"}}}},pageSize:$pageSize,currentPage:$currentPage){{
    page_info{{current_page total_pages}}
    items{{
      __typename uid sku name url_key stock_status
      categories{{uid name breadcrumbs{{category_name}}}}
      price_range{{minimum_price{{regular_price{{value}} final_price{{value}}}}
                  maximum_price{{final_price{{value}}}}}}
      {extra}
      ... on GroupedProduct{{
        items{{qty position product{{uid sku name stock_status
          ... on PhysicalProductInterface{{weight}}
          price_range{{minimum_price{{regular_price{{value}} final_price{{value}}}}}}}}}}
      }}
      ... on ConfigurableProduct{{
        configurable_options{{attribute_code label}}
        variants{{
          product{{uid sku name stock_status weight price_range{{minimum_price{{regular_price{{value}} final_price{{value}}}}}}}}
          attributes{{code label}}
        }}
      }}
    }}
  }}
}}"""

_QUERY = _QUERY_TEMPLATE.format(extra="")
# custom_attributesV2 IS the site's "More information" panel (verified live
# 2026-07-23: manufacturer, country_of_manufacture, origin, size, material
# type, coating, grade — the owner's list, code for code). Dropdown values
# arrive as selected_options, text values as value; both fragments cover it.
#
# `image` and `media_gallery` were READ by _enrichment_rows since the day it
# was written and never ASKED FOR here, so every madar product arrived with no
# picture and the panel's gallery was empty for the whole source. The reader
# was right; the query was the hole. Live check 2026-07-25: 11 of the first 60
# products carry a real image, the other 49 answer with the shop's own
# placeholder URL — which the reader already refuses, because a grey box where
# a product belongs is worse than an honest blank.
_QUERY_ENRICHED = _QUERY_TEMPLATE.format(
    extra="description{html} short_description{html} "
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

# The en_SA store view returns English names for the same uids (verified
# live: "اسمنت الرياض" -> "Riyadh Cement"). uid + name ONLY — the bilingual
# table costs pages, never payloads.
_ENGLISH_STORE = "en_SA"
_EN_QUERY = """query($pageSize:Int!,$currentPage:Int!){
  products(filter:{price:{from:"0"}},pageSize:$pageSize,currentPage:$currentPage){
    page_info{current_page total_pages}
    items{uid name ... on ConfigurableProduct{variants{product{uid name}}}}
  }
}"""

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
    """Tag-stripped text: scraped content is untrusted (spec 34), and the text
    carries the meaning anyway — same rationale as the woo connector.

    Entities are unescaped FIRST: madar returns its description already
    escaped (`&lt;article lang="ar"&gt;…`), so stripping tags before
    unescaping left the markup sitting in the value as literal text."""
    if not html:
        return ""
    import html as html_module

    text = html_module.unescape(html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


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


class MagentoGraphqlConnector:
    connector_id = "magento-graphql"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher
        self.skip_tokens: set[str] = set()      # resume: pages already journaled

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/graphql"
        ctx = {
            "base": base,
            "currency": source.currency or "UNKNOWN",
            # What the STOREFRONT shows, which is what a simple product's and a
            # grouped member's figure is.
            "vat": "1" if source.vat_mode.value == "incl" else "0",
            "region": source.default_region,
            # ...and what a CONFIGURABLE's figure is, which on this platform is
            # a different answer (see _product_rows). vat_included is a fact
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
        ctx["names_en"] = self._english_names(endpoint, notes)
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        query = _QUERY_ENRICHED if wants_enrichment else _QUERY
        fetched: list[dict] = []      # kept so enrichment needs no second fetch
        page = 1
        while True:
            token = f"page-{page}"
            body = {"query": query, "variables": {"pageSize": PAGE_SIZE, "currentPage": page}}
            products = (((self._fetcher.post(endpoint, json=body).json() or {})
                         .get("data") or {}).get("products")) or {}
            items = products.get("items") or []
            if not items:
                break
            if token not in self.skip_tokens:
                # Warnings raised while building THIS page must ride this page.
                # Pinning them all to page 1 (as before) silently dropped every
                # skip a later page reported — and a skip nobody hears is the
                # quiet data loss the warnings exist to prevent.
                before = len(notes)
                page_rows: list[list[str]] = []
                for product in items:
                    made = self._product_rows(builder, product, ctx)
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
                    page_token=token,
                )
            total_pages = ((products.get("page_info") or {}).get("total_pages")) or page
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
            for product in fetched:
                attribute_rows.extend(_enrichment_rows(extra, product, filterable))
            if attribute_rows:
                yield ScrapedTable(
                    source_key=source.source_key, kind=ENRICHMENT.kind,
                    source_url=endpoint, header=extra.header,
                    rows=attribute_rows,
                )

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
        except Exception as exc:  # noqa: BLE001 — the crawl does not hang on this
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

    def _english_names(self, endpoint: str, notes: list) -> dict:
        """uid -> English name from the en_SA store view (verified live:
        "اسمنت الرياض" -> "Riyadh Cement"). A LIGHT second pass — uid and name
        only — so the bilingual table costs pages, never payloads. Failure
        degrades to Arabic-only WITH a note; the prices are never at stake."""
        names: dict[str, str] = {}
        try:
            page = 1
            while True:
                body = {"query": _EN_QUERY,
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
                    for v in item.get("variants") or []:
                        child = v.get("product") or {}
                        cuid = str(child.get("uid") or "")
                        if cuid and child.get("name"):
                            names[cuid] = str(child["name"])
                total = ((products.get("page_info") or {}).get("total_pages")) or page
                if page >= total:
                    break
                page += 1
        except CrawlBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 — bilingual is additive, prices are vital
            notes.append(f"english-names pass failed — names stay "
                         f"Arabic-only this run: {exc}")
            return {}
        return names

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
        except Exception as exc:  # noqa: BLE001 — the Arabic path still stands
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
        except Exception as exc:  # noqa: BLE001 — classification is additive, prices are vital
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
        option_labels = {str(o.get("attribute_code") or ""): str(o.get("label") or "")
                         for o in product.get("configurable_options") or []}

        def row(pid, vid, sku, name, reg, fin, stock, label="", fp="",
                basis="", unit="", vat=None, axes=None):
            effective = fin if fin is not None else reg
            if effective is None:
                return  # a product with no price — skip, don't emit an empty required field
            out.append(builder.row(
                external_product_id=pid, external_variant_id=vid, external_sku=sku or "",
                product_name=name or "",
                # The PRODUCT's English name, never the child's — madar names
                # its variant children by internal SKU string in BOTH stores,
                # so asking the child first put "618097 1 GANG RJ11 SOCKET
                # WHITE ELOE LEGRAND" where the page says "Legrand Eloe
                # telephone and data sockets". Same rule as the Arabic name.
                product_name_en=names_en.get(str(pid)) or names_en.get(str(vid)) or "",
                option_label=label, option_fingerprint=fp,
                # The axes as STRUCTURE beside the sentence built from them.
                # `_option_text` composes «السماكة (مم): 2.2، العرض (مم): 24»
                # for a person to read; a spreadsheet needs one column per
                # axis, and the parts were being discarded the moment the
                # sentence existed (the owner's report, fixed at the root).
                option_axes=option_axes_json(axes or {}),
                basis_quantity=basis, unit=unit,
                product_url=url, region=ctx["region"], currency=ctx["currency"],
                # PER ROW, never per source: on this platform one crawl carries
                # both answers at once, and a source-level flag stamped on
                # every observation is how the warehouse came to assert things
                # the shop never said.
                vat_included=vat if vat is not None else ctx["vat"],
                regular_price=reg if reg is not None else effective,
                sale_price=fin if (reg is not None and fin is not None and reg != fin) else "",
                effective_price=effective, availability=_availability(stock),
                category_path=category_path, category_path_en=category_path_en,
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
                    fp=option_fingerprint({"member": str(child.get("sku") or "")})
                    if child.get("sku") else "",
                    basis=basis, unit=unit)
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
        # vat_included=0, so the Tax column reads "Excl. 15%" on this row and
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
                    basis=basis, unit=unit, vat=variant_vat)
        else:
            # A product standing alone must have ONE price, not a span. Every
            # SimpleProduct in the live census (399 of 399) answers
            # maximum_price == minimum_price, so this never fires for the shape
            # we have; it is here for the shape we do not — a BundleProduct
            # publishes a real min..max, and writing its minimum into
            # effective_price would file "from 50" as "50". A shape we have not
            # studied is not a shape we may guess at.
            if _spans_a_range(product):
                notes.append(
                    f"{product.get('name')} ({product.get('sku')}): "
                    f"{shape or 'this product'} publishes a price RANGE "
                    f"({_range_text(product)}), not a price — skipped rather "
                    "than stored at the range's low end")
                return out
            reg, fin = _prices(product)
            row(product.get("uid"), product.get("uid"), product.get("sku"),
                product.get("name"), reg, fin, product.get("stock_status"))
        return out


def _enrichment_rows(builder: RowBuilder, product: dict,
                     filterable: dict | None = None) -> list:
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

    def add(code, label, value, *, numeric="", unit="", url=""):
        if not value:
            return
        group = ("Media" if code.startswith("image")
                 else "Description" if "desc" in code
                 else "Measurements" if code == "weight"
                 else "Filters" if code in facets
                 else "More information")
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=str(value), numeric_value=str(numeric), unit_raw=unit,
            value_url=url, lang="", attribute_group=group))

    # The product's pictures, primary first. A placeholder is the site saying
    # "no image" — storing it would put a grey box where a product belongs.
    for position, media in enumerate([product.get("image") or {},
                                      *(product.get("media_gallery") or [])]):
        href = str(media.get("url") or "")
        if not href or "placeholder" in href.lower():
            continue
        add(f"image_{position}" if position else "image", "Image",
            str(media.get("label") or "") or href.rsplit("/", 1)[-1], url=href)

    add("description", "Description",
        _clean(((product.get("description") or {}).get("html")) or ""))
    add("short_description", "Summary",
        _clean(((product.get("short_description") or {}).get("html")) or ""))
    # The "More information" panel, one row per stated fact — manufacturer,
    # origin, grade, coating... — in the site's own values.
    for attribute in ((product.get("custom_attributesV2") or {}).get("items")) or []:
        code = str(attribute.get("code") or "")
        value = attribute.get("value") or ", ".join(
            str(o.get("label") or "")
            for o in attribute.get("selected_options") or [] if o.get("label"))
        if code:
            # The site's own label when it has published one (it does for every
            # attribute it filters by); the bare code otherwise, which is all
            # there was for any of them until now.
            add(code, facets.get(code) or code, value)
    for v in product.get("variants") or []:
        child = v.get("product") or {}
        weight = child.get("weight")
        if not weight:
            continue
        basis, _unit = selling_unit_from(child.get("name") or "", weight)
        if basis:
            continue      # already the selling basis on the price row
        sku = child.get("sku") or ""
        add("weight", f"Weight — {sku}", weight, numeric=weight, unit="kg")
    return rows
