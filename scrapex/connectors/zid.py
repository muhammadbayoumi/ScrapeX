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

THE STORE'S OWN EXCHANGE RATE (2026-07-29). A Zid storefront that sells into
more than one country prints, in every page's bootstrap JSON, the rate it
converts with: `"code": "SAR", ..., "exchange_rate": "3.754116"`. Each locale
prints ONLY its own active currency, so the Saudi pages never mention EGP and
the reverse. The connector reads the rate off pages it was fetching anyway, and
spends ONE extra request per FOREIGN COUNTRY the page itself advertises — never
a guessed path, always an `hreflang` the store published. capture stores them
under source_kind='shop'.

THE COUNTRY IS A COOKIE, NOT A PATH (measured 2026-07-29, and it matters far
beyond the rate). The store pins the country in a `locale` cookie on the first
request of a session and thereafter REDIRECTS every URL to the pinned country,
overriding the path prefix. Asked for /ar-eg/... on a session that had already
seen a Saudi page, it answered 200 from /ar-sa/... in SAR — no error, no clue.
So the prefix only decides the FIRST request of a session. Two consequences the
next reader must not have to rediscover: the foreign-rate probe runs on a
fetcher of its own (below), and this crawl's own session must never be allowed
to touch an Egyptian URL first, or every product page after it would come back
in EGP and be stored as a Saudi price.

THE PICTURES (2026-07-29). Every advancedcastle product page publishes `image`
in the SAME Product JSON-LD the price is read from, and not one was stored:
this connector had no enrichment branch at all, so a zid source that
contracted enrichment would have been served prices and silence. The reading
itself is not zid's to write (salla already had it), so it moved to jsonld and
both families now share it. What zid adds is the branch, and the choice to run
it for a PRICELESS product too — a variant-priced page publishes no usable
price and still publishes its pictures.

MEASURED, live warehouse before this fix: 168/168 ADVANCEDCASTLE products, 0
carrying an image. MEASURED, this connector run end-to-end against the live
site after the fix (168 products, one crawl): 168/168 products land at least
one image, 435 image rows total, 771 enrichment rows including description
and sku.

MEASURED LIMIT, stated rather than papered over: on a 42-product sample of the
live catalogue, the page's own gallery markup (`#product-images
img.carousel-img`) carries 124 images against JSON-LD's 109 for the same
products, and every JSON-LD image is among them. On 10 of the 42, JSON-LD
names fewer pictures than the gallery shows. Every product still gets at least
one image from JSON-LD, so nothing is left blank; reading the gallery as well
would recover the remaining ones and is a separate, owner-visible enhancement,
not part of restoring what was being dropped.

Two things this deliberately does NOT do. It does not convert anything: the
crawled price stays the price the store printed. And it does not reconcile the
rate with the prices — on 2026-07-29 the store published 3.754116 SAR and
50.5485 EGP per USD (a ratio of 13.46) while its Egyptian pages priced at a
ratio of 11.768. That mismatch is the store's, and recording what it publishes
is the only way anyone can ever see it.
"""
from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urljoin

from ..localinbox import safe_token
from ..config import SourceEntry
from ..rowspec import ENRICHMENT, PRODUCT_PRICES, RowBuilder
from ..vocab import ExtractKind
from .base import CrawlBlocked, HttpFetcher, ScrapedTable
from .jsonld import (WalkTally, alternate_links, english_alternate,
                     enrichment_rows, offer_price, parse_product_jsonld,
                     product_row, sitemap_products, walk_product_pages)

_PRODUCT_PATH = "/products/"

# One currency block of the store bootstrap. The lookahead keeps the pair
# INSIDE a single block: without it a store listing several currencies would
# marry the first code to some later block's rate — a wrong number that looks
# exactly like a right one.
_STORE_RATE = re.compile(
    r'"code"\s*:\s*"([A-Za-z]{3})"'
    r'(?:(?!"code"\s*:).)*?'
    r'"exchange_rate"\s*:\s*"?([0-9]*\.?[0-9]+)"?',
    re.S)

# 1 USD buying more than a million units is a parse gone wrong, not a rate.
# Same ceiling rates.py applies to Google Finance, restated at this door
# because a bad number refused here never reaches the database at all.
_MAX_PER_USD = 1e6


def _bootstrap_rates(html: str) -> dict[str, float]:
    """{ISO code: units per USD} the page's own bootstrap publishes.

    Foreign content, so every number is bounded and anything unfit is dropped
    rather than stored: a rate of zero would divide, and an absurd one would
    quietly rank this store's prices above or below every other source.
    """
    out: dict[str, float] = {}
    for code, raw in _STORE_RATE.findall(html):
        try:
            value = float(raw)
        except ValueError:
            continue
        if 0 < value <= _MAX_PER_USD:
            out.setdefault(code.upper(), value)
    return out


def _foreign_country_links(links: dict[str, str], home_region: str) -> dict[str, str]:
    """{region: one page} for every country BUT ours, from the page's own
    alternates. `en` (no region) and `x-default` name no country and are
    skipped; two locales of the same country collapse to one request."""
    home = (home_region or "").strip().lower()
    out: dict[str, str] = {}
    for code, href in links.items():
        parts = code.split("-")
        if len(parts) != 2 or len(parts[1]) != 2:
            continue                      # "en", "x-default": no country named
        region = parts[1]
        if region == home:
            continue
        out.setdefault(region, href)
    return out


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
        wants_enrichment = any(spec.kind == ExtractKind.ENRICHMENT
                               for spec in source.extract)
        tally = WalkTally()
        rates: dict[str, float] = {}
        rate_notes: list[str] = []
        asked_abroad = False

        for url, token, html, node in walk_product_pages(
                self._fetcher, self._product_urls(f"{base}/sitemap.xml", tally),
                self.skip_tokens, safe_token, tally):
            # Decided BEFORE the English request, so a variant-priced product we
            # are going to skip anyway never costs a second fetch.
            # This page was fetched for its price; its bootstrap carries the
            # store's rate for the currency IT prices in, so reading it costs
            # nothing. Done before the price check: a product with no price
            # still published the store's rate.
            rates.update(_bootstrap_rates(html))
            if not asked_abroad:
                # ONCE per crawl, and only for countries this page itself
                # advertises. Each locale prints only its active currency, so
                # without this the Egyptian rate the store converts with would
                # never be seen — and it is the one the owner asked for.
                asked_abroad = True
                abroad, notes = self._rates_abroad(html, url, source)
                rates.update(abroad)
                rate_notes.extend(notes)
            pid = _product_id(url, node)
            if offer_price(node.get("offers"))[0]:
                # The SAME product, in the store's other language. Fetched only
                # when THIS page advertises one, so an Arabic-only Zid store
                # still costs exactly one request per product and reaches none
                # of this.
                english, lost = self._english_node(html, node, url, source)
                tally.english_lost += lost
                # One table per product, journaled as fetched: accumulating the
                # whole catalogue and yielding once at the end meant an
                # interrupted crawl had written nothing at all.
                builder = RowBuilder(PRODUCT_PRICES)
                row = product_row(builder, node, url, source, vat, pid,
                                  english=english)
                if row is None:  # unreachable today; the price was checked above
                    tally.priceless += 1
                else:
                    yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind,
                                       base, builder.header, [row],
                                       page_token=token)
            else:
                tally.priceless += 1
            if wants_enrichment:
                # The pictures and prose the SAME page already carried, under
                # the SAME token: one product is journaled once, so a resume
                # cannot land its price without its details. Outside the price
                # branch on purpose — a variant-priced product publishes no
                # usable price and still publishes its images, and dropping
                # those with the price is how this connector came to store no
                # image at all.
                extra = RowBuilder(ENRICHMENT)
                attribute_rows = enrichment_rows(extra, node, pid)
                if attribute_rows:
                    yield ScrapedTable(source.source_key, ENRICHMENT.kind, base,
                                       extra.header, attribute_rows,
                                       page_token=token)

        # Every skip above used to be silent, so a crawl that landed half the
        # catalogue reported plain success — the GPP lesson, and the one salla
        # already learned. Carrying on is right; not saying so is not.
        notes = tally.notes() + rate_notes
        if notes or rates:
            # Untokenized on purpose: the counts describe THIS attempt, and
            # capture drops them on resume so a resumed run reports its own.
            # The rates ride here for the same reason — they are what THIS
            # crawl read, and a resume reads them again off its first page.
            yield ScrapedTable(source.source_key, PRODUCT_PRICES.kind, base,
                               RowBuilder(PRODUCT_PRICES).header, [],
                               warnings=notes, published_rates=rates)

    def _rates_abroad(self, html: str, url: str,
                      source: SourceEntry) -> tuple[dict[str, float], list[str]]:
        """({ISO: per USD}, warnings) for every country but ours.

        One request per foreign country the PAGE advertises, once per crawl. A
        single-country store advertises none and pays nothing.

        ON A SESSION OF ITS OWN, and that is the whole difficulty (measured
        2026-07-29). This store pins the country in a `locale` cookie on the
        first request and then REDIRECTS every later URL to the pinned country,
        path prefix and all: asked for /ar-eg/... on a session that had already
        seen a Saudi page, it answered from /ar-sa/... in SAR, status 200, no
        error anywhere. Reusing the crawl's fetcher would therefore have filed
        the Saudi rate under Egypt — a wrong number that looks exactly like a
        right one. A fresh session starts fresh, and on a fresh session the
        prefix wins. The session comes from the TRANSPORT (fresh_session), not
        built here: politeness lives in one place, and a transport that offers
        none — every test stub — makes this ask nothing and say why.

        It must not run the other way either: the crawl's own session is left
        untouched, because had the probe pinned it to Egypt every remaining
        product page would have come back in EGP and been stored as a Saudi
        price. The catalogue is the thing being protected here, not the rate.

        VERIFIED, NOT TRUSTED. Whatever the mechanism, a foreign page that
        answers in the store's HOME currency is not the foreign page, so that
        answer is refused and said out loud. A missing rate must never cost the
        catalogue (Q3) — and must never vanish quietly either, which is how a
        USD column goes on quoting last month's number with nothing saying why.
        """
        rates: dict[str, float] = {}
        notes: list[str] = []
        countries = _foreign_country_links(alternate_links(html),
                                           source.default_region)
        if not countries:
            return rates, notes
        new_session = getattr(self._fetcher, "fresh_session", None)
        if new_session is None:
            # The transport cannot give us a second session, so the question
            # cannot be asked SAFELY. Asking on the crawl's own session is the
            # one thing that must never happen — it would file this store's
            # Saudi rate under Egypt. Saying nothing would be worse than saying
            # this, so it is said.
            return rates, [
                f"{', '.join(sorted(r.upper() for r in countries))}: this "
                "transport offers no separate session, so the store's foreign "
                "exchange rate was not read. It is NOT read on the crawl's own "
                "session — that returns the home country's rate under the "
                "foreign country's name."]
        home = (source.currency or "").strip().upper()
        for region, href in countries.items():
            target = urljoin(url, href)
            probe = new_session()               # its own session; see above
            try:
                found = _bootstrap_rates(probe.get(target).text)
            except CrawlBlocked:
                raise                    # the site said stop — stop
            except Exception as exc:  # noqa: BLE001 — one page never kills a crawl
                notes.append(f"{region.upper()}: the store's exchange rate was "
                             f"not read from {target} — {exc}")
                continue
            finally:
                probe.close()
            foreign = {c: v for c, v in found.items() if c != home}
            if not foreign:
                notes.append(
                    f"{region.upper()}: {target} answered in "
                    f"{', '.join(sorted(found)) or 'no currency at all'} — not a "
                    f"foreign currency, so the country switch did not happen and "
                    f"no rate was recorded for {region.upper()}. Re-verify how "
                    "this store selects its country.")
                continue
            rates.update(foreign)
        return rates, notes

    def _product_urls(self, sitemap_url: str, tally: WalkTally) -> list[str]:
        """Zid's rule for what a product URL is; the walking is shared.

        NO expect_requests HERE, deliberately, and salla's identical-looking
        method does declare one. The frontier is equally known; the COST of it
        is not. A zid product page may advertise an English alternate, and
        _english_node then spends a second request on it — per product, decided
        by that product's own head. A bilingual store costs up to twice this
        list and an Arabic-only one costs exactly it, and nothing here can tell
        which until the pages arrive.

        Declaring the list anyway would put a denominator on screen that the
        numerator sails past halfway through every bilingual crawl. The panel's
        estimate — this source's last successful run, which DID pay for those
        English pages — is the better number, and it says it is an estimate.
        """
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
