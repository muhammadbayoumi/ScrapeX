"""Shared JSON-LD + sitemap parsing for server-rendered product connectors.

Once TWO SSR families (salla-html, zid-html) needed the same schema.org Product
reading, the shared logic moved here rather than one connector importing another
(base.py: connectors never import each other; A3: a family base is extracted only
once it's PROVEN — now it is). Site-specific concerns (which sitemap to walk, how
to derive the product id) stay in each connector.
"""
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from ..vocab import Availability


def sitemap_locs(xml: str) -> list[str]:
    """Every <loc> URL in a sitemap or sitemap index."""
    return [loc.get_text(strip=True) for loc in BeautifulSoup(xml, "xml").find_all("loc")]


def _product_node(data) -> dict | None:
    candidates = data if isinstance(data, list) else (
        data.get("@graph") if isinstance(data, dict) and isinstance(data.get("@graph"), list) else [data])
    for node in candidates:
        if isinstance(node, dict):
            types = node.get("@type")
            if "Product" in (types if isinstance(types, list) else [types]):
                return node
    return None


def parse_product_jsonld(html: str) -> dict | None:
    """First schema.org Product node in any ld+json script (handles @graph / list)."""
    for script in BeautifulSoup(html, "lxml").find_all("script", type="application/ld+json"):
        try:
            node = _product_node(json.loads(script.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue
        if node:
            return node
    return None


def offer_price(offers) -> tuple[str, str, str]:
    """(price, currency, availability) from an Offer / AggregateOffer.

    Variant-priced products expose offers.price = 0 in JSON-LD; fall back to the
    AggregateOffer lowPrice. Empty price -> caller skips (real variant prices need
    a session capture, later)."""
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return "", "", ""
    currency = offers.get("priceCurrency", "") or ""
    availability = str(offers.get("availability", ""))
    price = offers.get("price")
    if price in (None, "", 0, "0", "0.0", 0.0):     # variant-priced -> AggregateOffer
        price = offers.get("lowPrice")
    return (str(price) if price not in (None, "") else ""), currency, availability


def brand_name(node: dict) -> str:
    """schema.org brand may be a string or a {@type:Brand,name}."""
    brand = node.get("brand")
    return brand.get("name", "") if isinstance(brand, dict) else str(brand or "")


# schema.org availability -> our vocabulary. Only what a site actually STATES
# is translated; anything else stays unknown rather than being guessed.
_SOLD_OUT = ("OutOfStock", "SoldOut", "Discontinued")


def availability_status(availability: str) -> str:
    """'in_stock' | 'out_of_stock' | 'unknown' from a schema.org availability URL.

    Both SSR connectors used to read `"InStock" in availability` and send
    EVERYTHING else — including an explicit https://schema.org/OutOfStock — to
    `unknown`. Verified live on alsweed 2026-07-23: p1754450923 publishes
    OutOfStock and was recorded as unknown, so a product the shop says it does
    not have read exactly like a product it says nothing about. The vocabulary
    has always had out_of_stock; nothing was writing it.
    """
    text = str(availability or "")
    if "InStock" in text:
        return Availability.IN_STOCK.value
    if any(word in text for word in _SOLD_OUT):
        return Availability.OUT_OF_STOCK.value
    return Availability.UNKNOWN.value


def category_path(node: dict) -> str:
    """The product's own filing, as the page states it: "A > B".

    schema.org allows a string, a Thing with a name, or a list of either. Zid
    publishes the string form («أنظمة الإطفاء > طفايات الحريق اليدوية»),
    already in the separator our category_path column uses, and it was being
    dropped on the floor. Nothing here re-shapes the path — an unfamiliar form
    yields "" rather than an invented one.
    """
    value = node.get("category")
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("name")
    return str(value).strip() if isinstance(value, str) else ""
