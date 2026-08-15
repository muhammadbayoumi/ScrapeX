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

from ..vocab import Availability, DetailGroup, group_for_code
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
    except Exception as exc:
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
        except Exception as exc:
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
    english_lost: int = 0
    # The fuller picture route (below): pages whose OWN picture record was
    # readable, and pages that published pictures in their JSON-LD while that
    # record could not be found. The second is the number that matters — it is
    # how a theme update announces itself instead of silently halving the
    # images a source lands.
    pictures_read: int = 0
    pictures_route_lost: int = 0
    unreadable_children: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.unreadable_children is None:
            self.unreadable_children = []

    def picture_route_defects(self) -> list[str]:
        """Stated as a DEFECT, not a warning, when the route stops matching.

        A CSS class or a bootstrap variable is a contract the shop's theme can
        end without telling anyone, and the failure mode is silence: the reader
        matches nothing, every product keeps the one picture its JSON-LD names,
        and the run reports plain success while the catalogue quietly loses the
        rest. base.py draws the line — a warning says something went wrong and
        was contained, a defect says the data this run produced is KNOWN to be
        degraded, and only a defect reaches crawl_run.errors_count.

        The rule is deliberately blunt: the route failing on MORE pages than it
        worked on is not a handful of odd products, it is the shape having
        changed. That covers the total case (`pictures_read == 0`) without
        needing a second threshold for it.
        """
        if self.pictures_route_lost and self.pictures_route_lost > self.pictures_read:
            return [
                f"the page's own picture list could not be read on "
                f"{self.pictures_route_lost} product page(s) that publish images, "
                f"against {self.pictures_read} where it could — the shop's theme "
                "has almost certainly changed and this run stored only the "
                "pictures the JSON-LD summary names. The images are NOT gone "
                "from the site; the reader stopped matching and needs updating."
            ]
        return []

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
        if self.english_lost:
            notes.append(
                f"{self.english_lost} product(s) advertise an English page whose "
                "product JSON-LD could not be read (unreachable, unparsable, or "
                "a different product) — their English columns are empty and "
                "were never translated or guessed")
        if self.pictures_route_lost:
            notes.append(
                f"{self.pictures_route_lost} product page(s) publish images in "
                "their JSON-LD but carry no readable picture list of their own — "
                "those products kept only the pictures the summary names, and "
                "none were guessed at")
        return notes


def walk_product_pages(
        fetcher, urls: Iterable[str], skip_tokens,
        token_of: Callable[[str], str], tally: WalkTally,
        *, request_kwargs: dict | None = None,
) -> Iterator[tuple[str, str, str, dict]]:
    """(url, token, html, product node) for every page that answered and parsed.

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
            html = fetcher.get(url, **(request_kwargs or {})).text
        except CrawlBlocked:
            raise
        except Exception:
            tally.unreachable += 1
            continue
        node = parse_product_jsonld(html)
        if not node:
            tally.unparsed += 1
            continue
        yield url, token, html, node


def walk_products(fetcher, urls: Iterable[str], skip_tokens,
                  token_of: Callable[[str], str],
                  tally: WalkTally) -> Iterator[tuple[str, str, dict]]:
    """Compatibility view for connectors that do not need the source HTML."""
    for url, token, _html, node in walk_product_pages(
            fetcher, urls, skip_tokens, token_of, tally):
        yield url, token, node


def alternate_links(html: str) -> dict[str, str]:
    """The page's own `<link rel="alternate" hreflang="...">` map: code -> href.

    A store that serves more than one language SAYS SO here, in its own head,
    and the codes are the store's — not a path convention we guessed. Reading
    them is what lets a connector find the other language without hardcoding
    "/en/": a store that publishes nothing else yields {} and costs no request.

    Codes are lowercased (hreflang is case-insensitive per RFC 5646) and
    `x-default` is kept, because a store whose default is a real locale points
    it at one.
    """
    out: dict[str, str] = {}
    for tag in BeautifulSoup(html, "lxml").find_all("link", rel="alternate"):
        code = str(tag.get("hreflang") or "").strip().lower()
        href = str(tag.get("href") or "").strip()
        if code and href:
            out.setdefault(code, href)   # first wins: document order is the site's
    return out


def english_alternate(links: dict[str, str], region: str = "") -> str:
    """The English page for OUR region, from the page's own alternates.

    Region-matched FIRST and deliberately: when a page publishes `en` plus a
    regional English alternate, taking whichever came first could borrow text
    from a different storefront. "" when the store has no English page, which
    is the honest answer for an Arabic-only shop.
    """
    region = (region or "").strip().lower()
    if region and f"en-{region}" in links:
        return links[f"en-{region}"]
    if "en" in links:
        return links["en"]
    for code, href in links.items():
        if code.startswith("en-"):
            return href
    return ""


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
    # WooCommerce's current schema output puts the actual amount only inside a
    # UnitPriceSpecification. Measured on samehgabriel.com 2026-08-15: the
    # enclosing Offer has no `price` and carries a one-item priceSpecification
    # list. Treating that as priceless would discard a price the page states in
    # machine-readable form.
    specifications = offers.get("priceSpecification")
    if isinstance(specifications, dict):
        specifications = [specifications]
    if price in (None, ""):
        for spec in specifications or []:
            if not isinstance(spec, dict) or spec.get("price") in (None, ""):
                continue
            price = spec["price"]
            currency = currency or spec.get("priceCurrency", "") or ""
            break
    if price in (None, "", 0, "0", "0.0", 0.0):     # variant-priced -> AggregateOffer
        price = offers.get("lowPrice")
    return (str(price) if price not in (None, "") else ""), currency, availability


def product_row(builder, node: dict, url: str, source, vat: str, pid: str,
                english: dict | None = None):
    """One price row from a schema.org Product node, or None when unpriced.

    This was written out twice, byte for byte, in salla and zid — with ONE line
    different between them, the product id, which is now the caller's argument.
    The marked Arabic column always comes from the crawled page. When that page
    advertises a verified English twin, the caller may pass its Product node;
    otherwise the unmarked columns stay empty rather than carrying Arabic under
    headings that assert English.
    """
    from ..normalize import brand_pair

    price, currency, availability = offer_price(node.get("offers"))
    if not price:
        # Variant-priced with no usable price: the real ones need the page's
        # variant HTML or a session capture. Never guessed at.
        return None
    english = english or {}
    return builder.row(
        external_product_id=pid, external_variant_id=pid,
        external_sku=str(node.get("sku") or ""),
        product_name_ar=str(node.get("name") or ""),
        product_name=str(english.get("name") or ""),
        **brand_pair(brand_name(node)), product_link=url,
        country_code_alpha2=source.default_region,
        currency=currency or source.currency or "UNKNOWN", tax_included=vat,
        price_before=price, price_sale="", price=price,
        availability=availability_status(availability),
        # The product's own filing, stated in the SAME JSON-LD the price came
        # from — «أنظمة الإطفاء > طفايات الحريق اليدوية». No extra request.
        category_path_ar=category_path(node),
        category_path=category_path(english) if english else "",
    )


@dataclass(frozen=True)
class Picture:
    """One picture a product page publishes.

    `identity` is how the SITE tells two pictures apart, and it is deliberately
    NOT the URL. A shop publishes the same picture at several sizes, and
    advancedcastle names it at `.../thumbs/<uuid>-thumbnail-1000x1000-70.jpg`
    in its JSON-LD while its own gallery renders `.../<uuid>.jpg`. MEASURED on
    the full 168-product catalogue: of 435 JSON-LD image URLs, exactly 0 appear
    as a gallery `<img src>` string, and yet 0 name a picture the gallery does
    not have. Deduplicating on the URL would therefore have stored one picture
    twice, under two attribute codes, on every product that has one — the
    "two codes holding one URL" defect, arrived at from the other direction.

    So the connector says what identity means for ITS shop: a media id where
    the platform states one (zid publishes an image uuid), the URL itself where
    the shop publishes each picture at exactly one address (salla does).

    `label` is the alternative text the SITE wrote, empty when it wrote none.
    Never invented and never translated: advancedcastle publishes ONE alt_text
    per picture and serves the SAME Arabic string on its English locale, so
    there is no second language to capture and no `_ar` pair to make.
    """

    identity: str
    url: str
    label: str = ""


def merge_pictures(record: Iterable[Picture],
                   summary: Iterable[Picture]) -> list[Picture]:
    """Every picture the page publishes, the shop's own order, each one once.

    `record` is the page's own picture list — the fuller truth — and `summary`
    is what the machine-readable summary named. The record LEADS because its
    order is the order the shop displays: schema.org allows `image` to name one
    representative picture, and on 44 of advancedcastle's 168 products the
    picture it names is not the gallery's first. Taking the summary's order
    would put a middle picture where the main one belongs.

    The summary is still merged in rather than replaced by, because it is not
    always a subset: on 4 of those 168 products the page's own list and the
    JSON-LD disagree about which pictures the product has, and 6 pictures exist
    only in the JSON-LD. Dropping them would be a regression wearing the
    clothes of an improvement — this run must never store less than the last.
    """
    out: list[Picture] = []
    seen: set[str] = set()
    for picture in [*record, *summary]:
        if not picture.url or not picture.identity or picture.identity in seen:
            continue
        seen.add(picture.identity)
        out.append(picture)
    return out


def jsonld_pictures(node: dict,
                    identity: Callable[[str], str] | None = None) -> list[Picture]:
    """The pictures schema.org `image` names.

    Allowed to be a single URL or a list of them, and advancedcastle publishes
    both forms (a string on single-image products, a list otherwise), so both
    are read and neither is guessed at. `identity` is how the caller's shop
    tells two pictures apart; without one the URL stands in, which is the right
    answer for a shop that publishes each picture at exactly one address.
    """
    images = node.get("image")
    if isinstance(images, str):
        images = [images]
    pictures: list[Picture] = []
    for href in images or []:
        if isinstance(href, str) and href.startswith("http"):
            pictures.append(Picture(
                identity=(identity(href) if identity else href), url=href))
    return pictures


def enrichment_rows(builder, node: dict, pid: str,
                    pictures: Iterable[Picture] | None = None) -> list[list[str]]:
    """The pictures and prose the product page's JSON-LD already carried.

    Written for salla and left in salla, so the SECOND SSR family to want
    details had nothing to reach for — and zid, which publishes `image` on
    every product page it was already fetching, stored none of it. That is the
    move product_row already made for the same reason: the product id is the
    one thing that genuinely differs between the two families, so it is the
    caller's argument rather than a connector importing another connector
    (base.py). Nothing else here is site-specific.

    `pictures` is the merged list the CALLER assembled from its shop's own
    picture record and the JSON-LD summary (merge_pictures). Passing none keeps
    the original behaviour — the JSON-LD's `image` alone — which is the honest
    answer for a family whose pages publish nothing richer.
    """
    rows: list[list[str]] = []

    def add(code, label, value, *, url_value="", group=""):
        if not value:
            return
        # The shared map decides WHERE (vocab.group_for_code), so every
        # source files the same kind of fact in the same place. The
        # caller's `group` remains the hint for codes this shop names in
        # a way the map has not been taught yet.
        decided, recognised = group_for_code(code)
        rows.append(builder.row(
            external_product_id=pid, attribute_code=code, attribute_label=label,
            raw_value=str(value)[:2000], numeric_value="", unit_raw="",
            value_url=url_value, lang="",
            attribute_group=decided if recognised else (group or decided)))

    if pictures is None:
        pictures = jsonld_pictures(node)
    for position, picture in enumerate(pictures):
        # The shop's own alternative text when it wrote one, the file name when
        # it did not — the same standing-in woocommerce and shopify already do,
        # so the panel always has something to render an <img> alt with. The
        # URL in value_url is the record and is never touched.
        add(f"image_{position}" if position else "image", "Image",
            picture.label or picture.url.rsplit("/", 1)[-1],
            url_value=picture.url, group=DetailGroup.MEDIA)

    add("description", "Description", node.get("description"), group="Description")
    add("sku", "SKU", node.get("sku"), group="Specs")
    return rows


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
