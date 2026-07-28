"""Shared JSON-LD + sitemap parsing for server-rendered product connectors.

Once TWO SSR families (salla-html, zid-html) needed the same schema.org Product
reading, the shared logic moved here rather than one connector importing another
(base.py: connectors never import each other; A3: a family base is extracted only
once it's PROVEN — now it is). Site-specific concerns (which sitemap to walk, how
to derive the product id) stay in each connector.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from bs4 import BeautifulSoup

from ..vocab import Availability
from .base import CrawlBlocked


def sitemap_locs(xml: str) -> list[str]:
    """Every <loc> URL in a sitemap or sitemap index."""
    return [loc.get_text(strip=True) for loc in BeautifulSoup(xml, "xml").find_all("loc")]


class SitemapUnreadable(RuntimeError):
    """The catalogue index itself could not be read.

    NOT the same as "this shop lists no products", and both connectors used to
    say the second when they meant the first: `except Exception: return []`. A
    blocked or cancelled sitemap fetch then published as a legitimately empty
    crawl. A run that could not read the index has failed; jobs.py isolates the
    source and the rest of the run carries on, which is where that belongs.
    """


def sitemap_products(fetcher, sitemap_url: str, keep: Callable[[str], bool],
                     *, dedupe: Callable[[list[str]], list[str]] | None = None,
                     unreadable_children: list[str] | None = None) -> list[str]:
    """Every product URL under a sitemap (or sitemap index), site rules applied.

    `keep` decides what a product URL looks like for this shop and `dedupe` how
    to collapse the ones that repeat — the two things that genuinely differ.
    A CHILD sitemap that fails is survivable and counted; the ROOT failing is
    not, because nothing else can be trusted after it.
    """
    try:
        locs = sitemap_locs(fetcher.get(sitemap_url).text)
    except CrawlBlocked:
        raise                                  # the owner's Stop, or the site's
    except Exception as exc:  # noqa: BLE001 — reported, never turned into "empty"
        raise SitemapUnreadable(
            f"the product index at {sitemap_url} could not be read ({exc}), so "
            "this run cannot tell an empty catalogue from an unreachable one"
        ) from exc

    products = [url for url in locs if keep(url)]
    for child in (url for url in locs if url.endswith(".xml")):
        try:
            products += [url for url in sitemap_locs(fetcher.get(child).text) if keep(url)]
        except CrawlBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 — one child, counted and survived
            if unreadable_children is not None:
                unreadable_children.append(f"{child}: {exc}")
    return dedupe(products) if dedupe else list(dict.fromkeys(products))


@dataclass
class WalkTally:
    """What a catalogue walk did NOT land, and why. Every count is reported.

    salla counted three of these and zid four — zid's `unreachable` being the
    honest one, since a page that never answered is not a page that published
    no price. One tally, so neither can quietly grow a blind spot the other
    already closed.
    """

    priceless: int = 0
    unparsed: int = 0
    unreachable: int = 0
    skipped: int = 0
    unreadable_children: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.unreadable_children is None:
            self.unreadable_children = []

    def notes(self) -> list[str]:
        notes: list[str] = []
        if self.priceless:
            notes.append(
                f"{self.priceless} product(s) publish no usable price in their "
                "JSON-LD (variant-priced) — skipped, never guessed; their real "
                "prices need the page's variant HTML or a session capture")
        if self.unparsed:
            notes.append(f"{self.unparsed} product page(s) carried no Product "
                         "JSON-LD at all")
        if self.unreachable:
            notes.append(f"{self.unreachable} product page(s) could not be fetched")
        if self.unreadable_children:
            notes.append(f"{len(self.unreadable_children)} child sitemap(s) could "
                         f"not be read: {'; '.join(self.unreadable_children[:3])}")
        if self.skipped:
            notes.append(f"{self.skipped} product page(s) were already journaled by "
                         "a paused run and were not fetched again")
        return notes


def walk_products(fetcher, urls: Iterable[str], skip_tokens, token_of: Callable[[str], str],
                  tally: WalkTally) -> Iterator[tuple[str, str, dict]]:
    """(url, token, product node) for every page that answered AND parsed.

    THE STOP SIGNAL PASSES THROUGH. Both SSR connectors guarded the page fetch
    with a bare `except Exception: continue`, and CrawlBlocked is a RuntimeError
    — so the site's own refusal AND the owner's Cancel (CrawlInterrupted, which
    subclasses it for exactly this reason) were swallowed, and the walk carried
    on through every remaining URL. On a 1,233-product shop behind a 10-second
    crawl delay that is hours of knocking on a door that said no, with a Cancel
    button that does nothing. One loop, one guard, both connectors.
    """
    for url in urls:
        token = token_of(url)
        if token in skip_tokens:
            # BEFORE the request: a resume that refetched would cost the hours
            # it exists to save.
            tally.skipped += 1
            continue
        try:
            html = fetcher.get(url).text
        except CrawlBlocked:
            raise
        except Exception:  # noqa: BLE001 — one dead page never kills the crawl (Q3)
            tally.unreachable += 1
            continue
        node = parse_product_jsonld(html)
        if not node:
            tally.unparsed += 1
            continue
        yield url, token, node


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


def product_row(builder, node: dict, url: str, source, vat: str, pid: str):
    """One price row from a schema.org Product node, or None when unpriced.

    This was written out twice, byte for byte, in salla and zid — with ONE line
    different between them, the product id, which is now the caller's argument.
    Both shops publish Arabic only, so the marked column is filled and the
    unmarked one stays empty rather than carrying Arabic under a name that
    asserts English.
    """
    from ..normalize import brand_pair

    price, currency, availability = offer_price(node.get("offers"))
    if not price:
        # Variant-priced with no usable price: the real ones need the page's
        # variant HTML or a session capture. Never guessed at.
        return None
    return builder.row(
        external_product_id=pid, external_variant_id=pid,
        external_sku=str(node.get("sku") or ""),
        product_name_ar=str(node.get("name") or ""),
        **brand_pair(brand_name(node)), product_link=url,
        country_code_alpha2=source.default_region,
        currency=currency or source.currency or "UNKNOWN", tax_included=vat,
        price_before=price, price_sale="", price=price,
        availability=availability_status(availability),
        # The product's own filing, stated in the SAME JSON-LD the price came
        # from — «أنظمة الإطفاء > طفايات الحريق اليدوية». No extra request.
        category_path_ar=category_path(node),
    )


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
