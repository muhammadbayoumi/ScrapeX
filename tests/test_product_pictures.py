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
from scrapex.connectors.zid import ZidConnector, image_identity
from scrapex.connectors.zid import page_pictures as zid_pictures
from scrapex.rowspec import ENRICHMENT, RowView
from scrapex.vocab import DetailGroup, ExtractKind, ExtractScope

LIVE = Path(__file__).parent / "fixtures" / "live"
ZID_PAGE = (LIVE / "advancedcastle_product_pictures_2026-07-30.trimmed.html"
            ).read_text(encoding="utf-8")
SALLA_PAGE = (LIVE / "alsweed_product_pictures_2026-07-30.trimmed.html"
              ).read_text(encoding="utf-8")

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0 Safari/537.36"
SALLA_PID = "448819456"


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------
class _Resp:
    def __init__(self, text): self.text = text


class _ZidSite:
    """advancedcastle, serving the captured page for every product URL.

    `page` is what the product URL answers, so a test can hand it a DRIFTED
    page — the same shop after a theme update — without touching the connector.
    """

    SITEMAP = ("<?xml version='1.0' encoding='UTF-8'?><urlset>"
               "<url><loc>https://advancedcastle.com/products/flasher-lamp</loc></url>"
               "</urlset>")

    def __init__(self, page: str = ZID_PAGE):
        self.page = page
        self.requests_count = 0

    def get(self, url, **kwargs):
        self.requests_count += 1
        if url.endswith("/sitemap.xml"):
            return _Resp(self.SITEMAP)
        if "/products/" in url:
            return _Resp(self.page)
        raise RuntimeError("404 " + url)

    def close(self): pass


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


def zid_entry(): return _entry("ADVANCEDCASTLE", "https://advancedcastle.com",
                               "zid-html", CHROME_UA)


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
def test_a_zid_theme_that_stops_publishing_its_picture_list_is_announced():
    """The whole point of this file.

    The store's bootstrap is renamed — exactly what a theme update does — and
    everything else still works: the sitemap parses, the page answers, the
    JSON-LD is intact, the price lands. The one thing that changed is that the
    fuller picture route now matches nothing, and a run that did not SAY so
    would look identical to a healthy one forever.
    """
    site = _ZidSite(drifted(ZID_PAGE, r"var\s+productImages"))
    images, warnings, defects = run(ZidConnector(site), zid_entry())

    assert defects, (
        "the picture list could not be read on every product page and the run "
        "reported no defect — a theme update would silently halve this "
        "source's images and never be noticed")
    assert any("picture list could not be read" in d for d in defects)
    assert any("theme" in d.lower() for d in defects)
    # It degrades to the summary rather than to nothing: still honest data.
    assert len(images) == 3, "the JSON-LD pictures must still land"
    assert any("picture list" in w for w in warnings), (
        "the COUNT belongs in the run's notes as well: the defect says the "
        "shape changed, the note says how many products it cost")


def test_a_salla_theme_that_renames_its_slides_is_announced():
    site = _SallaSite(drifted(SALLA_PAGE, r"data-fslightbox"))
    images, warnings, defects = run(SallaConnector(site), salla_entry())

    assert defects, (
        "the slide anchors matched nothing and the run reported no defect — "
        "this source would drop from 8 pictures to 1 in silence")
    assert len(images) == 1, "the JSON-LD picture must still land"


def test_a_healthy_run_raises_no_picture_defect():
    """The guard has to be quiet when nothing is wrong, or it is noise."""
    for connector, entry in ((ZidConnector(_ZidSite()), zid_entry()),
                             (SallaConnector(_SallaSite()), salla_entry())):
        _images, _warnings, defects = run(connector, entry)
        assert defects == [], f"a healthy page raised {defects}"


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
def test_one_picture_named_by_both_routes_is_stored_once():
    """The trap that makes URL-based dedup wrong.

    advancedcastle names a picture at `.../thumbs/<uuid>-…-1000x1000-70.jpg` in
    its JSON-LD and renders `.../<uuid>.jpg` in its gallery. Measured over all
    168 products: 0 JSON-LD URLs are string-equal to a gallery src, and 0 name
    a picture the gallery lacks — so a URL-keyed merge would have doubled every
    picture while looking perfectly correct.
    """
    node = parse_product_jsonld(ZID_PAGE)
    summary = jsonld_pictures(node, identity=image_identity)
    record = zid_pictures(ZID_PAGE)
    merged = merge_pictures(record, summary)

    assert len(summary) == 3 and len(record) == 6
    assert len(merged) == 6, "the 3 summary pictures are already among the 6"
    assert len({p.identity for p in merged}) == len(merged)
    assert len({p.url for p in merged}) == len(merged)


def test_no_two_image_rows_share_a_url_or_a_code():
    for connector, entry, expected in ((ZidConnector(_ZidSite()), zid_entry(), 6),
                                       (SallaConnector(_SallaSite()), salla_entry(), 8)):
        images, _w, _d = run(connector, entry)
        assert len(images) == expected
        urls = [i["value_url"] for i in images]
        codes = [i["attribute_code"] for i in images]
        assert len(set(urls)) == len(urls), f"one picture stored twice: {urls}"
        assert len(set(codes)) == len(codes), f"one code used twice: {codes}"


def test_the_merged_urls_reproduce_what_the_summary_already_stored():
    """No churn: every URL this source already holds is still the same string.

    The bootstrap publishes five sizes and `large` is the one the store's own
    JSON-LD names — 429 of 429 matched URLs byte-identical, measured on the
    whole catalogue. Recording `large` is therefore what makes the merge
    provably duplicate-free rather than merely tidy.
    """
    node = parse_product_jsonld(ZID_PAGE)
    summary = jsonld_pictures(node, identity=image_identity)
    merged_urls = {p.url for p in merge_pictures(zid_pictures(ZID_PAGE), summary)}
    for picture in summary:
        assert picture.url in merged_urls, (
            f"{picture.url} was replaced by another rendition — the same "
            "picture would now sit at two addresses")


# --------------------------------------------------------------------------
# 3. the extra pictures, and the ordering
# --------------------------------------------------------------------------
def test_the_pictures_the_summary_omits_reach_the_rows():
    images, _w, _d = run(ZidConnector(_ZidSite()), zid_entry())
    assert len(images) == 6, "JSON-LD named 3; the page lists 6"
    assert [i["attribute_code"] for i in images] == [
        "image", "image_1", "image_2", "image_3", "image_4", "image_5"]
    assert all(i["attribute_group"] == DetailGroup.MEDIA.value for i in images)


def test_salla_reads_the_whole_slider_not_the_one_picture_the_summary_names():
    images, _w, _d = run(SallaConnector(_SallaSite()), salla_entry())
    assert len(images) == 8, "JSON-LD named 1; the slider names 8"


def test_the_picture_the_shop_shows_first_is_the_one_filed_as_image():
    """schema.org's chosen picture is NOT reliably the main one.

    On 44 of advancedcastle's 168 products the JSON-LD image is not the
    gallery's first, and on this alsweed product it is the EIGHTH slide. The
    shop's own order decides, so `image` is the picture it shows first.
    """
    record = zid_pictures(ZID_PAGE)
    images, _w, _d = run(ZidConnector(_ZidSite()), zid_entry())
    assert images[0]["value_url"] == record[0].url

    salla_record = salla_pictures(SALLA_PAGE, SALLA_PID)
    salla_images, _w2, _d2 = run(SallaConnector(_SallaSite()), salla_entry())
    assert salla_images[0]["value_url"] == salla_record[0].url
    summary_url = jsonld_pictures(parse_product_jsonld(SALLA_PAGE))[0].url
    assert summary_url != salla_images[0]["value_url"], (
        "this fixture was chosen because the summary's picture is the LAST "
        "slide — if that stops being true the ordering claim is untested")
    assert salla_images[-1]["value_url"] == summary_url


def test_a_picture_only_the_summary_names_is_never_dropped():
    """The merge must never store less than the route it replaces.

    On 4 of 168 advancedcastle products the page's own list and the JSON-LD
    disagree, leaving 6 pictures that exist only in the summary. A reader that
    simply replaced one route with the other would lose them.
    """
    only_in_summary = Picture(identity="ghost", url="https://example.com/ghost.jpg")
    merged = merge_pictures(zid_pictures(ZID_PAGE), [only_in_summary])
    assert merged[-1].url == "https://example.com/ghost.jpg"
    assert len(merged) == 7


# --------------------------------------------------------------------------
# 4. never invent, never translate, never download
# --------------------------------------------------------------------------
def test_the_label_is_the_shops_own_words_and_the_url_is_untouched():
    images, _w, _d = run(ZidConnector(_ZidSite()), zid_entry())
    labelled = [i for i in images if i["raw_value"] == "لمبة تحذير"]
    assert labelled, "the merchant's own alt_text must be the row's label"
    assert all(i["value_url"].startswith("https://media.zid.store/")
               for i in images), "the URL is stored exactly as published"


def test_a_picture_without_a_label_falls_back_to_its_file_name():
    """Never blank, never invented: the file name is still the shop's own."""
    images, _w, _d = run(ZidConnector(_ZidSite()), zid_entry())
    unlabelled = [i for i in images if i["raw_value"].endswith(".jpg")
                  or i["raw_value"].endswith(".png")]
    assert unlabelled, "the picture with no alt_text should carry its file name"
    for image in unlabelled:
        assert image["raw_value"] in image["value_url"]


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


def test_a_page_with_no_pictures_at_all_yields_no_image_rows():
    """A shop that publishes one picture gets one; a page with none gets none,
    and nothing is substituted for it."""
    bare = re.sub(r'"image":\s*(\[[^\]]*\]|"[^"]*")', '"image": []', ZID_PAGE)
    bare = re.sub(r"var\s+productImages\s*=\s*\[.*?\]\s*;", "var productImages = [];",
                  bare, flags=re.S)
    images, _w, defects = run(ZidConnector(_ZidSite(bare)), zid_entry())
    assert images == []
    assert defects == [], "no pictures published is not a drift"


# --------------------------------------------------------------------------
# 5. the readers, in isolation
# --------------------------------------------------------------------------
def test_zid_identity_is_the_picture_not_the_size():
    full = ("https://media.zid.store/c8ea395e-772e-4ce7-bcfb-117308676724/"
            "f04cd61c-5abc-4e1c-b8ab-9b9733370f89.jpg")
    thumb = ("https://media.zid.store/thumbs/c8ea395e-772e-4ce7-bcfb-117308676724/"
             "f04cd61c-5abc-4e1c-b8ab-9b9733370f89-thumbnail-1000x1000-70.jpg")
    assert image_identity(full) == image_identity(thumb)
    assert image_identity(full) == "f04cd61c-5abc-4e1c-b8ab-9b9733370f89"


def test_an_unreadable_bootstrap_yields_nothing_rather_than_half_a_list():
    assert zid_pictures("<html>no bootstrap here</html>") == []
    assert zid_pictures("<script>var productImages = [{broken</script>") == []
    assert zid_pictures("") == []


def test_the_slider_of_another_product_is_never_read():
    """`data-fslightbox="product_{id}"` is why a related-products carousel on
    the same page cannot leak its pictures into this product's rows."""
    assert salla_pictures(SALLA_PAGE, "999999999") == []
    assert salla_pictures(SALLA_PAGE, "") == []
