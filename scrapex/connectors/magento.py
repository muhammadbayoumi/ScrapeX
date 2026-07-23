"""magento-graphql family connector (ENGINEERING.md A3: proven family).

Madar (the flagship) runs Magento 2 with an open GraphQL endpoint. We list all
priced products paginated (`filter:{price:{from:"0"}}`) and map each configurable
variant — or each simple product — to one canonical PRODUCT_PRICES row.
Prices are VAT-exclusive on this platform (the source's vat_mode records that).
"""
from __future__ import annotations

import re

from typing import Iterable

from ..config import SourceEntry
from ..normalize import option_fingerprint
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import Availability, ExtractKind
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

PAGE_SIZE = 100

# configurable_options carries the site's own NAME for each variant axis
# ("السماكة (مم)"), and each variant child carries its weight — verified live
# on madar 2026-07-22 (riyadh-cement: weight 50 + "50كجم" in the name; steel
# angles: thickness/width/length axes). The descriptions slot is filled only
# when the manifest asks for enrichment, so a prices-only crawl stays light.
_QUERY_TEMPLATE = """query($pageSize:Int!,$currentPage:Int!){{
  products(filter:{{price:{{from:"0"}}}},pageSize:$pageSize,currentPage:$currentPage){{
    page_info{{current_page total_pages}}
    items{{
      uid sku name url_key stock_status
      categories{{uid name breadcrumbs{{category_name}}}}
      price_range{{minimum_price{{regular_price{{value}} final_price{{value}}}}}}
      {extra}
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
_QUERY_ENRICHED = _QUERY_TEMPLATE.format(
    extra="description{html} short_description{html} "
          "custom_attributesV2(filters:{is_visible_on_front:true}){items{"
          "code ... on AttributeValue{value} "
          "... on AttributeSelectedOptions{selected_options{label}}}}")

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

# "50كجم" / "50 kg" in a variant's NAME: the site stating what one price
# buys. Arabic and Latin spellings both appear on madar.
_STATED_KG = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:كجم|كغم|كغ|kg)", re.IGNORECASE)


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


def selling_unit_from(name: str, weight) -> tuple[str, str]:
    """(basis_quantity, unit) — ONLY when the site itself states the basis.

    The owner's rule: a price is never shown apart from the unit it is FOR,
    and the unit is read off the source, never guessed. Riyadh cement states
    it twice — weight=50 AND "50كجم" in the variant's name — so kg/50 is the
    basis. A steel angle carries weight=4.986, but that is the PIECE's mass:
    its name states dimensions in millimetres, no kg quantity, and its price
    is per piece — inventing "per 4.986 kg" would be exactly the guess this
    function refuses. Agreement between the stated name and the weight field
    is the test."""
    try:
        heavy = float(weight)
    except (TypeError, ValueError):
        return "", ""
    if not heavy:
        return "", ""
    found = _STATED_KG.search(name or "")
    if not found:
        return "", ""
    stated = float(found.group(1).replace(",", "."))
    if abs(stated - heavy) > 1e-6:
        return "", ""
    quantity = int(stated) if stated == int(stated) else stated
    return str(quantity), "kg"


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
    carries the meaning anyway — same rationale as the woo connector."""
    if not html:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


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
    mp = ((node.get("price_range") or {}).get("minimum_price")) or {}
    regular = (mp.get("regular_price") or {}).get("value")
    final = (mp.get("final_price") or {}).get("value")
    return regular, final


class MagentoGraphqlConnector:
    connector_id = "magento-graphql"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(PRODUCT_PRICES)
        base = source.base_url.rstrip("/")
        endpoint = f"{base}/graphql"
        ctx = {
            "base": base,
            "currency": source.currency or "UNKNOWN",
            "vat": "1" if source.vat_mode.value == "incl" else "0",
            "region": source.default_region,
        }
        notes: list[str] = []
        ctx["paths"] = self._category_map(endpoint, source, notes)
        ctx["names_en"] = self._english_names(endpoint, notes)
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        query = _QUERY_ENRICHED if wants_enrichment else _QUERY
        rows: list[list[str]] = []
        fetched: list[dict] = []      # kept so enrichment needs no second fetch
        page = 1
        while True:
            body = {"query": query, "variables": {"pageSize": PAGE_SIZE, "currentPage": page}}
            products = (((self._fetcher.post(endpoint, json=body).json() or {})
                         .get("data") or {}).get("products")) or {}
            items = products.get("items") or []
            if not items:
                break
            if wants_enrichment:
                fetched.extend(items)
            for product in items:
                rows.extend(self._product_rows(builder, product, ctx))
            total_pages = ((products.get("page_info") or {}).get("total_pages")) or page
            if page >= total_pages:
                break
            page += 1

        yield ScrapedTable(
            source_key=source.source_key, kind=PRODUCT_PRICES.kind,
            source_url=endpoint, header=builder.header, rows=rows,
            warnings=notes,
        )
        # The details the same responses already carried — descriptions and
        # per-variant weights — cost no extra request. Only when the manifest
        # asks (same gate as the woo connector).
        if wants_enrichment:
            extra = RowBuilder(ENRICHMENT)
            attribute_rows: list[list[str]] = []
            for product in fetched:
                attribute_rows.extend(_enrichment_rows(extra, product))
            if attribute_rows:
                yield ScrapedTable(
                    source_key=source.source_key, kind=ENRICHMENT.kind,
                    source_url=endpoint, header=extra.header,
                    rows=attribute_rows,
                )

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
        out: list[list[str]] = []

        names_en = ctx.get("names_en") or {}
        option_labels = {str(o.get("attribute_code") or ""): str(o.get("label") or "")
                         for o in product.get("configurable_options") or []}

        def row(pid, vid, sku, name, reg, fin, stock, label="", fp="",
                basis="", unit=""):
            effective = fin if fin is not None else reg
            if effective is None:
                return  # a product with no price — skip, don't emit an empty required field
            out.append(builder.row(
                external_product_id=pid, external_variant_id=vid, external_sku=sku or "",
                product_name=name or "",
                product_name_en=names_en.get(str(vid)) or names_en.get(str(pid)) or "",
                option_label=label, option_fingerprint=fp,
                basis_quantity=basis, unit=unit,
                product_url=url, region=ctx["region"], currency=ctx["currency"], vat_included=ctx["vat"],
                regular_price=reg if reg is not None else effective,
                sale_price=fin if (reg is not None and fin is not None and reg != fin) else "",
                effective_price=effective, availability=_availability(stock),
                category_path=category_path, category_external_id=category_id,
            ))

        if variants:
            for v in variants:
                child = v.get("product") or {}
                attrs = [a for a in (v.get("attributes") or []) if a.get("code")]
                reg, fin = _prices(child)
                # The basis the site itself states (weight + "50كجم" in the
                # name agreeing) rides the row; a piece's mass does not.
                basis, unit = selling_unit_from(child.get("name") or "",
                                                child.get("weight"))
                row(product.get("uid"), child.get("uid"), child.get("sku"),
                    child.get("name") or product.get("name"), reg, fin, child.get("stock_status"),
                    label=_option_text(attrs, option_labels),
                    fp=option_fingerprint({a["code"]: a.get("label", "") for a in attrs}) if attrs else "",
                    basis=basis, unit=unit)
        else:
            reg, fin = _prices(product)
            row(product.get("uid"), product.get("uid"), product.get("sku"),
                product.get("name"), reg, fin, product.get("stock_status"))
        return out


def _enrichment_rows(builder: RowBuilder, product: dict) -> list:
    """Descriptions and per-variant weights the census already carried.

    The weight lands here ONLY when it is not the selling basis: cement's 50
    lives on the price row as "per 50 kg", while a steel angle's 4.986 kg is
    a property of the piece — information, not the unit."""
    pid = str(product.get("uid") or "")
    if not pid:
        return []
    rows: list = []

    def add(code, label, value, *, numeric="", unit=""):
        if not value:
            return
        group = ("Description" if "desc" in code
                 else "Measurements" if code == "weight"
                 else "More information")
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=str(value), numeric_value=str(numeric), unit_raw=unit,
            value_url="", lang="", attribute_group=group))

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
            add(code, code, value)
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
