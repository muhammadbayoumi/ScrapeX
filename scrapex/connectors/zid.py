"""zid-html family connector (ENGINEERING.md A3: proven family).

Zid stores (advancedcastle) are server-rendered with schema.org Product JSON-LD,
enumerated from the sitemap — the SAME shape as Salla, so both share
connectors/jsonld.py. Two Zid-specifics: the store 403s non-browser clients, so
the source carries a Chrome `user_agent` the fetcher honors; and product ids are
slugs/UUIDs in /products/ URLs (no numeric /p{id}). v1 takes the product-level
JSON-LD price; per-variant prices live in the page HTML (a later enhancement).
"""
from __future__ import annotations

from typing import Iterable

from ..localinbox import safe_token
from ..config import SourceEntry
from ..rowspec import PRODUCT_PRICES, RowBuilder
from .base import HttpFetcher, ScrapedTable
from .jsonld import (WalkTally, product_row, sitemap_products, walk_products)

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

        for url, token, node in walk_products(
                self._fetcher, self._product_urls(f"{base}/sitemap.xml", tally),
                self.skip_tokens, safe_token, tally):
            # One table per product, journaled as fetched: accumulating the
            # whole catalogue and yielding once at the end meant an interrupted
            # crawl had written nothing at all.
            builder = RowBuilder(PRODUCT_PRICES)
            row = product_row(builder, node, url, source, vat, _product_id(url, node))
            if row is None:
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
