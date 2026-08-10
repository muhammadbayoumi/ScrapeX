"""salla-html family connector (ENGINEERING.md A3: proven family).

Salla stores (alsweed = «السويد», elburoj) are server-rendered with schema.org
Product JSON-LD on each product page. We enumerate product URLs from the
sitemap (numeric /p{id}), fetch each page, and read the JSON-LD.

Gotcha (handled): variant-priced products expose offers.price = 0 in JSON-LD;
we fall back to an AggregateOffer lowPrice, and skip a product with no usable
price (its real variant prices need the extension's session capture — later).
The pure parsers (`sitemap_locs`, `parse_product_jsonld`, `offer_price`) are
unit-tested against fixtures; only the fetch loop touches the network.

THE PICTURES (2026-07-30). This shop's JSON-LD names ONE picture per product
while the page's slider names the set, and the picture the JSON-LD names is
often not even the first slide. MEASURED over the whole alsweed catalogue,
1,231 of 1,233 products fetched once each (2 pages did not answer; the site
never objected): JSON-LD names 1,170 pictures, the sliders name 3,322 — a gap
of 2,162 across 749 products. 61 products publish no picture at all and stay
honestly blank.

So the slider leads and the summary is merged in behind it (page_pictures
below, merge_pictures in jsonld). It costs no request: the slider is in the
SAME response the price is read from, which this connector previously
discarded by walking with `walk_products` instead of `walk_product_pages`.

The merge is keyed on the URL here, and that is checked rather than assumed:
1,160 of the 1,170 JSON-LD image URLs are byte-identical to a slide href. The
10 that are not are YouTube thumbnails the JSON-LD lists as product images and
the slider files as `data-type="youtube"` slides; they are kept, because a run
must never store less than the one before it.

That reader is markup, and markup is a contract a theme update can end without
telling anyone — silently, since the prices would still land and every product
would keep the one picture its JSON-LD names. WalkTally counts the pages where
it stops matching and raises a DEFECT, not a note, when it fails on more pages
than it works on.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

from ..config import SourceEntry
from ..localinbox import safe_token

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
from .jsonld import (
    Picture,
    WalkTally,
    brand_name,
    category_path,
    enrichment_rows,
    jsonld_pictures,
    merge_pictures,
    offer_price,
    parse_product_jsonld,
    product_row,
    sitemap_locs,
    sitemap_products,
    walk_product_pages,
)

# THE RE-EXPORTS, SAID OUT LOUD. The comment above has always claimed these are
# re-exported for salla's tests; a comment could not stop `ruff --fix` deleting
# four of them as unused, and it did -- tests/test_salla.py stopped importing.
# __all__ is the same claim in a form the tooling reads.
__all__ = [
    "Picture", "SallaConnector", "WalkTally", "brand_name", "category_path",
    "enrichment_rows", "jsonld_pictures", "merge_pictures", "offer_price",
    "one_url_per_product", "page_pictures", "parse_product_jsonld",
    "product_row", "sitemap_locs", "sitemap_products", "walk_product_pages",
]

_PRODUCT_ID = re.compile(r"/p(\d{5,})")


def _salla_id(url: str, node: dict) -> str:
    """Salla ids are the numeric /p{id} in the URL, else whatever the page says.

    THE one line that differed between salla's row builder and zid's — the rest
    was identical, byte for byte, which is why the row now lives in jsonld and
    this is an argument to it.
    """
    found = _PRODUCT_ID.search(url)
    return found.group(1) if found else str(node.get("sku") or url)


def _product_key(url: str) -> str:
    """The numeric /p{id} the slider keys its slides on, "" when the URL has none.

    Deliberately NOT _salla_id: that falls back to the sku or the whole URL so
    a price row always has an id, and neither of those is what
    `data-fslightbox="product_…"` is built from. A URL with no numeric id has
    no slider to find, and "" says exactly that.
    """
    found = _PRODUCT_ID.search(url)
    return found.group(1) if found else ""


def page_pictures(html: str, pid: str) -> list[Picture]:
    """The pictures the product's own slider lists, in the shop's order.

    THE ANCHOR, not the `<img>`, and not a CSS class. Each slide is
    `<a data-fslightbox="product_{id}" data-img-id=… data-slid-index=… href=…>`,
    and every part of that earns its place:

    * `data-fslightbox="product_{id}"` ties the slide to THIS product, so a
      page carrying a related-products carousel cannot leak its pictures in.
    * `href` is the full-size URL and is always present. The `<img>` inside is
      lazy-loaded — MEASURED on alsweed, only the first slide has a real `src`
      and the rest carry `cdn.salla.network/images/s-empty.png` — so reading
      `<img src>` would have stored the same placeholder as several pictures.
    * the anchors appear ONCE per picture while the `<img>`s appear twice (the
      slider renders a thumbnail strip as well), so this route is free of the
      duplication a container-wide `img` sweep would have to undo.

    `swiper-slide` and `magnify-wrapper` are on the same element and are the
    theme's and a JS library's; they are deliberately not what this matches.

    VIDEOS ARE NOT PICTURES. 7 of 787 slides on the alsweed sample are
    `data-type="youtube"`, whose href is a video, so only `image` slides are
    read here. The store's JSON-LD separately names some YouTube *thumbnails*
    as product images; those rows already exist and the merge keeps them
    rather than quietly dropping what this source already stored.
    """
    if not pid:
        return []
    soup = BeautifulSoup(html or "", "lxml")
    pictures: list[Picture] = []
    for slide in soup.select(f'a[data-fslightbox="product_{pid}"]'):
        if str(slide.get("data-type") or "").strip().lower() != "image":
            continue
        href = str(slide.get("href") or "").strip()
        if not href.startswith("http"):
            continue
        # Identity is the URL, and it is checked rather than assumed: on the
        # alsweed census every JSON-LD image URL that names a picture (270 of
        # 270) is byte-identical to a slide href, and no product repeats an
        # href. Unlike zid, this shop publishes one picture at one address, so
        # the URL tells two pictures apart correctly. `data-img-id` is a
        # stronger identity if that ever stops being true — but it is not on
        # the JSON-LD side, and an identity only one route can compute would
        # store the overlap twice.
        pictures.append(Picture(
            identity=href, url=href,
            label=str(slide.get("data-caption") or "").strip()))
    return pictures


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

        # walk_product_pages rather than walk_products: the page's own slider
        # is the only place this shop states its whole picture set, so the HTML
        # the price was read from has to stay in hand. It costs no request —
        # it is the SAME response, which the previous view simply discarded.
        for url, token, html, node in walk_product_pages(
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
                #
                # The JSON-LD names ONE picture per product on this shop while
                # the slider names the set — MEASURED on the alsweed catalogue,
                # a roughly threefold difference — so the slider leads and the
                # summary is merged in behind it, by identity, never twice.
                summary = jsonld_pictures(node)
                record = page_pictures(html, _product_key(url))
                if record:
                    tally.pictures_read += 1
                elif summary:
                    tally.pictures_route_lost += 1
                extra = RowBuilder(ENRICHMENT)
                attribute_rows = enrichment_rows(
                    extra, node, _salla_id(url, node),
                    pictures=merge_pictures(record, summary))
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
        # The slider is markup, and markup is a contract a theme update can end
        # without notice. If it stops matching, every price still lands and
        # every product keeps the one picture its JSON-LD names, so the run
        # would look clean while the catalogue lost two thirds of its images.
        # A defect, not a note, because only a defect is counted as an error.
        defects = tally.picture_route_defects()
        if notes or defects:
            # A summary carrying only the counts, deliberately UNTOKENIZED: the
            # counts describe this attempt, and capture.clear_untokenized drops
            # them on resume so a resumed run reports its own rather than
            # inheriting numbers from the attempt before it.
            yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base,
                               RowBuilder(PRODUCT_PRICES).header, [],
                               warnings=notes, defects=defects)

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
