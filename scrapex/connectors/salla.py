"""salla-html family connector (ENGINEERING.md A3: proven family).

Salla stores (alsweed = «السويد», elburoj) are server-rendered with schema.org
Product JSON-LD on each product page. We enumerate product URLs from the
sitemap (numeric /p{id}), fetch each page, and read the JSON-LD.

Gotcha (handled): variant-priced products expose offers.price = 0 in JSON-LD;
we fall back to an AggregateOffer lowPrice, and skip a product with no usable
price (its real variant prices need the extension's session capture — later).
The pure parsers (`sitemap_locs`, `parse_product_jsonld`, `offer_price`) are
unit-tested against fixtures; only the fetch loop touches the network.
"""
from __future__ import annotations

import re
from typing import Iterable

from ..localinbox import safe_token
from ..normalize import brand_pair
from ..config import SourceEntry
# ENRICHMENT is imported eagerly: the enrichment branch below referenced it
# without it ever being in scope, so a salla source that declared an
# enrichment extract would have died on NameError after the whole crawl.
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import ExtractKind
from .base import HttpFetcher, ScrapedTable, declare_frontier
# Shared SSR helpers (also re-exported for salla's tests). offer_price/parse are
# generic; the /p{id} id scheme below is the salla-specific part. enrichment_rows
# moved to jsonld when zid needed the same pictures-and-prose reading — it is
# imported here rather than left behind so both families share one copy.
from .jsonld import (WalkTally, brand_name, category_path, enrichment_rows,
                     offer_price, parse_product_jsonld, product_row,
                     sitemap_locs, sitemap_products, walk_products)

_PRODUCT_ID = re.compile(r"/p(\d{5,})")


def _salla_id(url: str, node: dict) -> str:
    """Salla ids are the numeric /p{id} in the URL, else whatever the page says.

    THE one line that differed between salla's row builder and zid's — the rest
    was identical, byte for byte, which is why the row now lives in jsonld and
    this is an argument to it.
    """
    found = _PRODUCT_ID.search(url)
    return found.group(1) if found else str(node.get("sku") or url)


def one_url_per_product(urls: list[str]) -> list[str]:
    """One URL per product id, first occurrence wins.

    A Salla sitemap index lists every product ONCE PER LOCALE — /ar/…/p123 and
    /en/…/p123 are the same product. Deduplicating by URL string, as this did,
    collapses nothing: alsweed published 2466 URLs for 1233 products, so every
    crawl fetched each page twice and emitted two rows carrying the SAME
    external_product_id.

    That is worse than wasted requests. Two rows per product inflate the count,
    so min_expected_rows can never catch it — the canary only watches for rows
    going missing — and downstream every product looks like it has a duplicate
    offer. It also doubled the crawl cost against elburoj, which asks for a
    10-second delay between requests.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for url in urls:
        match = _PRODUCT_ID.search(url)
        key = match.group(1) if match else url
        if key in seen:
            continue
        seen.add(key)
        kept.append(url)
    return kept


class SallaConnector:
    connector_id = "salla-html"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher
        # Pages already journaled by a paused attempt, set by capture on resume.
        # This crawl is one REQUEST PER PRODUCT off a sitemap — there are no page
        # numbers to count — so the checkpoint is the product URL, hashed by
        # localinbox.safe_token because a raw URL does not survive being written
        # into a filename and would therefore never match on resume.
        self.skip_tokens: set[str] = set()

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        base = source.base_url.rstrip("/")
        vat = "1" if source.vat_mode.value == "incl" else "0"
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        tally = WalkTally()

        for url, token, node in walk_products(
                self._fetcher, self._product_urls(f"{base}/ar/sitemap.xml", tally),
                self.skip_tokens, safe_token, tally):
            # ONE TABLE PER PRODUCT, journaled as fetched. This connector used
            # to accumulate every row and yield a single table at the END, so a
            # crawl interrupted at hour five had written nothing at all — not
            # merely un-resumable, but a total loss, with capture's journal
            # (which exists for exactly that interruption) never given anything
            # to hold.
            builder = RowBuilder(PRODUCT_PRICES)
            row = product_row(builder, node, url, source, vat, _salla_id(url, node))
            if row is None:
                tally.priceless += 1
            else:
                yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base,
                                   builder.header, [row], page_token=token)
            if wants_enrichment:
                # The pictures and descriptions the SAME page already carried,
                # under the SAME token: one product is journaled once, so a
                # resume cannot land its price without its details.
                extra = RowBuilder(ENRICHMENT)
                attribute_rows = enrichment_rows(extra, node, _salla_id(url, node))
                if attribute_rows:
                    yield ScrapedTable(source.source_key, ENRICHMENT.kind, base,
                                       extra.header, attribute_rows,
                                       page_token=token)

        # The skips were SILENT — a crawl that quietly lands fewer products
        # than the site sells is the GPP lesson again. Verified live on
        # alsweed 2026-07-23: a variant-priced page publishes price:0 with no
        # lowPrice, no meta amount, no inline figure — there is genuinely
        # nothing to read, so the skip is right and saying it is mandatory.
        notes = tally.notes()
        if notes:
            # A summary carrying only the counts, deliberately UNTOKENIZED: the
            # counts describe this attempt, and capture.clear_untokenized drops
            # them on resume so a resumed run reports its own rather than
            # inheriting numbers from the attempt before it.
            yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base,
                               RowBuilder(PRODUCT_PRICES).header, [],
                               warnings=notes)

    def _product_urls(self, sitemap_url: str, tally: WalkTally) -> list[str]:
        """Salla's two rules: /p{id} marks a product, and one URL per product id
        (the sitemap lists every product once per locale). The walking is shared.

        THE FRONTIER IS KNOWN HERE, before a single product page is fetched, and
        this connector spends exactly one request per URL in it — the enrichment
        rows come off the same page it already fetched for the price. So the
        total is not an estimate for this family: it is a count, and declaring it
        is what lets the panel show a fraction of something real instead of a
        percentage of the number of sources.
        """
        urls = sitemap_products(
            self._fetcher, sitemap_url, lambda url: bool(_PRODUCT_ID.search(url)),
            dedupe=one_url_per_product,
            unreadable_children=tally.unreadable_children)
        # Minus the pages a paused run already journaled: a resume will not
        # re-fetch those, so counting them would leave the bar permanently short
        # of its own total by exactly the number of pages the resume saved.
        declare_frontier(
            self._fetcher,
            len([url for url in urls if safe_token(url) not in self.skip_tokens]))
        return urls
