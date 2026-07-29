"""zid-html family connector (ENGINEERING.md A3: proven family).

Zid stores (advancedcastle) are server-rendered with schema.org Product JSON-LD,
enumerated from the sitemap — the SAME shape as Salla, so both share
connectors/jsonld.py. Two Zid-specifics: the store 403s non-browser clients, so
the source carries a Chrome `user_agent` the fetcher honors; and product ids are
slugs/UUIDs in /products/ URLs (no numeric /p{id}). v1 takes the product-level
JSON-LD price; per-variant prices live in the page HTML (a later enhancement).

BILINGUAL (2026-07-28): advancedcastle serves Arabic AND English, and each page
declares its own alternates — `hreflang="en"` beside `hreflang="ar-sa"`. Every
row was going out Arabic-only, which the standing bilingual rule makes a defect,
so a product whose page advertises an English twin is read in both and the pair
of columns is filled from the page that published each. The English fetch is
conditional on that advertisement, so an Arabic-only Zid store pays nothing.

The connector follows only the English alternate for the configured region and
uses it for text fields. Price, currency, availability, identity and country
remain anchored to the original page selected by the source configuration.
"""
from __future__ import annotations

from typing import Iterable
from urllib.parse import urljoin

from ..localinbox import safe_token
from ..config import SourceEntry
from ..rowspec import PRODUCT_PRICES, RowBuilder
from .base import CrawlBlocked, HttpFetcher, ScrapedTable
from .jsonld import (WalkTally, alternate_links, english_alternate, offer_price,
                     parse_product_jsonld, product_row, sitemap_products,
                     walk_product_pages)

_PRODUCT_PATH = "/products/"


def _product_id(url: str, node: dict) -> str:
    """Zid ids are the JSON-LD sku/productID when present, else the URL slug."""
    sku = str(node.get("sku") or node.get("productID") or "").strip()
    return sku or url.rstrip("/").rsplit("/", 1)[-1]


class ZidConnector:
    connector_id = "zid-html"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher
        # Same sitemap shape as salla, so the same checkpoint: the product URL,
        # hashed because a raw URL does not survive being written into a
        # journal filename and would never match on resume.
        self.skip_tokens: set[str] = set()

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        base = source.base_url.rstrip("/")
        vat = "1" if source.vat_mode.value == "incl" else "0"
        tally = WalkTally()

        for url, token, html, node in walk_product_pages(
                self._fetcher, self._product_urls(f"{base}/sitemap.xml", tally),
                self.skip_tokens, safe_token, tally):
            # Decided BEFORE the English request, so a variant-priced product we
            # are going to skip anyway never costs a second fetch.
            if not offer_price(node.get("offers"))[0]:
                tally.priceless += 1
                continue
            # The SAME product, in the store's other language. Fetched only when
            # THIS page advertises one, so an Arabic-only Zid store still costs
            # exactly one request per product and reaches none of this.
            english, lost = self._english_node(html, node, url, source)
            tally.english_lost += lost
            # One table per product, journaled as fetched: accumulating the
            # whole catalogue and yielding once at the end meant an interrupted
            # crawl had written nothing at all.
            builder = RowBuilder(PRODUCT_PRICES)
            row = product_row(builder, node, url, source, vat,
                              _product_id(url, node), english=english)
            if row is None:  # unreachable today; the price was checked above
                tally.priceless += 1
                continue
            yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base,
                               builder.header, [row], page_token=token)

        # Every skip above used to be silent, so a crawl that landed half the
        # catalogue reported plain success — the GPP lesson, and the one salla
        # already learned. Carrying on is right; not saying so is not.
        notes = tally.notes()
        if notes:
            # Untokenized on purpose: the counts describe THIS attempt, and
            # capture drops them on resume so a resumed run reports its own.
            yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base,
                               RowBuilder(PRODUCT_PRICES).header, [],
                               warnings=notes)

    def _product_urls(self, sitemap_url: str, tally: WalkTally) -> list[str]:
        """Zid's rule for what a product URL is; the walking is shared."""
        return sitemap_products(
            self._fetcher, sitemap_url, lambda url: _PRODUCT_PATH in url,
            unreadable_children=tally.unreadable_children)

    def _english_node(self, html: str, node: dict, url: str,
                      source: SourceEntry) -> tuple[dict, int]:
        """(the same product's English JSON-LD, how many were LOST).

        Lost means the page said there is an English version and we could not
        read it. That is worth a warning; a store with no English page at all is
        not, and returns ({}, 0) without a request.
        """
        alt = english_alternate(alternate_links(html), source.default_region)
        alt = urljoin(url, alt) if alt else ""
        if not alt or alt.rstrip("/") == url.rstrip("/"):
            return {}, 0
        try:
            other = parse_product_jsonld(self._fetcher.get(alt).text)
        except CrawlBlocked:
            raise
        except Exception:  # noqa: BLE001 — one dead page never kills the crawl (Q3)
            return {}, 1
        if not other:
            return {}, 1
        # The alternate must be the SAME product. Without this a mis-wired
        # hreflang (or a store that points every alternate at its homepage)
        # writes some other product's English name onto this row — a silent
        # corruption that reads like a successful bilingual capture.
        if _product_id(alt, other) != _product_id(url, node):
            return {}, 1
        return other, 0
