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
