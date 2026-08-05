"""The pictures a page publishes in its markup but not in its machine-readable
summary — and, above all, the run saying so when it stops being able to read them.

WHY THIS FILE EXISTS. schema.org `image` is a summary: it is allowed to name one
representative picture, and on both server-rendered families it does exactly
that while the page itself publishes the whole set. Measured on the FULL
catalogues, 2026-07-30:

    ADVANCEDCASTLE (zid)   168 products   JSON-LD 435   page's own list 493
    ALSWEED        (salla) 1,233 products JSON-LD 1 per product, slider ~3x

The reader that closes that gap is markup, and markup is a contract a theme
update can end without telling anyone. Its failure mode is SILENCE — it matches
nothing, every product keeps the one picture its JSON-LD names, the prices still
land and the run reports plain success. So the tests that matter most here are
not the ones counting the extra pictures; they are the ones that FAIL IF A DRIFT
GOES UNANNOUNCED.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.jsonld import (Picture, WalkTally, jsonld_pictures,
                                       merge_pictures, parse_product_jsonld)
from scrapex.connectors.salla import SallaConnector
from scrapex.connectors.salla import page_pictures as salla_pictures
from scrapex.rowspec import ENRICHMENT, RowView
from scrapex.vocab import DetailGroup, ExtractKind, ExtractScope

LIVE = Path(__file__).parent / "fixtures" / "live"
SALLA_PAGE = (LIVE / "alsweed_product_pictures_2026-07-30.trimmed.html"
              ).read_text(encoding="utf-8")

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36"
SALLA_PID = "448819456"


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------
class _Resp:
    def __init__(self, text): self.text = text


class _SallaSite:
    SITEMAP = ("<?xml version='1.0' encoding='UTF-8'?><urlset>"
               f"<url><loc>https://alsweed.sa/ar/seat/p{SALLA_PID}</loc></url>"
               "</urlset>")

    def __init__(self, page: str = SALLA_PAGE):
        self.page = page
        self.requests_count = 0

    def get(self, url, **kwargs):
        self.requests_count += 1
        if url.endswith("sitemap.xml"):
            return _Resp(self.SITEMAP)
        if re.search(r"/p\d{5,}", url):
            return _Resp(self.page)
        raise RuntimeError("404 " + url)

    def close(self): pass


def _entry(key, base, family, ua=None) -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key=key, source_name=key, base_url=base, family=family,
        currency="SAR", default_region="SA", vat_mode="incl", user_agent=ua,
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.CENSUS)],
    ))


def salla_entry(): return _entry("ALSWEED", "https://alsweed.sa", "salla-html")


def run(connector, entry):
    """(image rows as dicts, warnings, defects) across every table yielded."""
    images, warnings, defects = [], [], []
    for table in connector.fetch(entry):
        warnings.extend(table.warnings)
        defects.extend(table.defects)
        if str(table.kind) != "enrichment":
            continue
        view = RowView(ENRICHMENT, table.header)
        for row in table.rows:
            if str(view.get(row, "attribute_code")).startswith("image"):
                images.append({k: view.get(row, k) for k in
                               ("attribute_code", "raw_value", "value_url",
                                "attribute_group")})
    return images, warnings, defects


def drifted(html: str, pattern: str) -> str:
    """The same page after a theme update that renamed what we read."""
    out = re.sub(pattern, "THEME-CHANGED", html, count=0)
    assert out != html, "the drift fixture changed nothing — the test is vacuous"
    return out


# --------------------------------------------------------------------------
# 1. THE GUARD THAT MATTERS: a drift must never pass silently
# --------------------------------------------------------------------------
def test_a_salla_theme_that_renames_its_slides_is_announced():
    site = _SallaSite(drifted(SALLA_PAGE, r"data-fslightbox"))
    images, warnings, defects = run(SallaConnector(site), salla_entry())

    assert defects, (
        "the slide anchors matched nothing and the run reported no defect — "
        "this source would drop from 8 pictures to 1 in silence")
    assert len(images) == 1, "the JSON-LD picture must still land"


def test_the_defect_fires_only_when_the_route_fails_more_than_it_works():
    """A handful of odd products is not a theme change, and must not cry wolf.

    The rule is stated once, in WalkTally, so both families share it: the route
    failing on MORE pages than it worked on is a shape change; failing on fewer
    is the ordinary raggedness of a real catalogue.
    """
    assert WalkTally(pictures_read=100, pictures_route_lost=3).picture_route_defects() == []
    assert WalkTally(pictures_read=0, pictures_route_lost=1).picture_route_defects()
    assert WalkTally(pictures_read=10, pictures_route_lost=11).picture_route_defects()
    # Nothing read and nothing lost is a source with no pictures at all, not a drift.
    assert WalkTally().picture_route_defects() == []


# --------------------------------------------------------------------------
# 2. no duplicates — the defect this design exists to avoid
# --------------------------------------------------------------------------
def test_salla_reads_the_whole_slider_not_the_one_picture_the_summary_names():
    images, _w, _d = run(SallaConnector(_SallaSite()), salla_entry())
    assert len(images) == 8, "JSON-LD named 1; the slider names 8"


def test_salla_lazy_placeholders_are_never_stored_as_pictures():
    """Every slide but the first carries s-empty.png in its <img src>.

    Reading `<img src>` would have stored one placeholder as several different
    pictures. The anchor's href is always the real one, which is why the reader
    takes it.
    """
    assert "s-empty.png" in SALLA_PAGE, "the fixture must still contain the trap"
    images, _w, _d = run(SallaConnector(_SallaSite()), salla_entry())
    assert not any("s-empty" in i["value_url"] for i in images)


def test_a_video_slide_is_not_a_picture():
    """7 of 787 alsweed slides are data-type="youtube"; a video is not a photo."""
    page = SALLA_PAGE.replace('data-type="image"', 'data-type="youtube"', 1)
    pictures = salla_pictures(page, SALLA_PID)
    assert len(pictures) == len(salla_pictures(SALLA_PAGE, SALLA_PID)) - 1


def test_nothing_is_fetched_beyond_the_pages_the_prices_already_cost():
    """No extra request. The pictures ride the response the price came from."""
    site = _SallaSite()
    list(SallaConnector(site).fetch(salla_entry()))
    assert site.requests_count == 2, (
        f"one sitemap and one product page, not {site.requests_count} — a "
        "second fetch per product would multiply every crawl")


def test_the_slider_of_another_product_is_never_read():
    """`data-fslightbox="product_{id}"` is why a related-products carousel on
    the same page cannot leak its pictures into this product's rows."""
    assert salla_pictures(SALLA_PAGE, "999999999") == []
    assert salla_pictures(SALLA_PAGE, "") == []


# --------------------------------------------------------------------------
# salvaged from the tests that covered BOTH readers before the zid half was
# split out — the behaviour is salla's too, and dropping the file would have
# dropped the cover with it
# --------------------------------------------------------------------------

def test_a_healthy_run_raises_no_picture_defect():
    """The guard has to be quiet when nothing is wrong, or it is noise."""
    _images, _warnings, defects = run(SallaConnector(_SallaSite()), salla_entry())

    assert defects == [], f"a healthy page raised {defects}"


def test_no_two_image_rows_share_a_url_or_a_code():
    images, _w, _d = run(SallaConnector(_SallaSite()), salla_entry())

    assert len(images) == 8
    urls = [i["value_url"] for i in images]
    codes = [i["attribute_code"] for i in images]
    assert len(set(urls)) == len(urls), f"one picture stored twice: {urls}"
    assert len(set(codes)) == len(codes), f"one code used twice: {codes}"


def test_a_picture_only_the_summary_names_is_never_dropped():
    """The merge must never store less than the route it replaces. A reader
    that simply swapped one route for the other would lose whatever only the
    summary knows about."""
    only_in_summary = Picture(identity="https://example.com/ghost.jpg",
                              url="https://example.com/ghost.jpg")
    record = list(salla_pictures(SALLA_PAGE, SALLA_PID))

    merged = merge_pictures(record, [only_in_summary])

    assert merged[-1].url == "https://example.com/ghost.jpg"
    assert len(merged) == len(record) + 1


def test_a_page_with_no_pictures_at_all_yields_no_image_rows():
    """A page with none gets none, and nothing is substituted for it."""
    # The reader selects a[data-fslightbox="product_<pid>"]; renaming that
    # attribute is how a page with no readable slides looks to it.
    bare = SALLA_PAGE.replace(f'data-fslightbox="product_{SALLA_PID}"',
                              'data-nothing-here="1"')
    bare = re.sub(r'"image":\s*(\[[^\]]*\]|"[^"]*")', '"image": []', bare)

    images, _w, defects = run(SallaConnector(_SallaSite(bare)), salla_entry())

    assert images == []
    assert defects == [], "no pictures published is not a drift"


# --------------------------------------------------------------------------
# the two the review asked for
# --------------------------------------------------------------------------

def test_the_merge_keys_on_identity_and_not_on_the_url():
    """THE SEAM THE WHOLE `Picture.identity` FIELD EXISTS FOR, and until now
    nothing exercised it.

    For salla, identity IS the url — the shop publishes each picture at exactly
    one address — so every shipping caller has the two agreeing, and swapping
    identity-keyed dedup for url-keyed dedup passed the entire suite. That is a
    field with a docstring and no test.

    A platform that names a picture once and serves it at several sizes is why
    the field is there. Driven directly here rather than through a connector,
    because no shipping connector produces the disagreement."""
    one_picture_two_addresses = [
        Picture(identity="media-7", url="https://example.com/big/7.jpg"),
        Picture(identity="media-7", url="https://example.com/thumb/7.jpg"),
    ]

    merged = merge_pictures(one_picture_two_addresses, [])

    assert len(merged) == 1, "one picture at two sizes was stored twice"
    assert merged[0].url == "https://example.com/big/7.jpg", (
        "the record's own first address is the one the shop leads with")


def test_the_label_is_the_shops_own_caption_not_the_file_name():
    """A BEHAVIOUR CHANGE THIS BRANCH MAKES, pinned because nothing pinned it.

    Before this reader, an ALSWEED image row's `raw_value` was the file name.
    It is now the slide's own `data-caption` — the merchant's words, in the
    merchant's language. That is better, and it is not free: the ingest upsert
    key is (source_product_id, attribute_code, raw_value), so every existing
    ALSWEED image row inserts anew and the old one retires on the next crawl.

    Deleting the caption and falling back to the file name passed the whole
    suite, so the improvement was undefended."""
    images, _w, _d = run(SallaConnector(_SallaSite()), salla_entry())

    labels = [i["raw_value"] for i in images]
    assert all(labels), "an image row was stored with no label at all"
    assert not any(label.endswith((".jpg", ".png", ".webp")) for label in labels), (
        "the row fell back to the file name; the shop's own caption was dropped")
    assert any("كرسى" in label or "كرسي" in label
               for label in labels), "the caption is not the merchant's own words"

