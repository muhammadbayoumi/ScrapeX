"""The Stop button, on the two SSR connectors that were ignoring it.

CrawlInterrupted subclasses CrawlBlocked deliberately (base.py) so that every
connector's broad per-page guard, which re-raises CrawlBlocked, propagates the
owner's Cancel for free. salla and zid never had that arm: CrawlBlocked is a
RuntimeError, `except Exception: continue` ate it, and the walk carried on
through every remaining URL. On a 1,233-product shop behind a 10-second crawl
delay that is hours of knocking on a door that already said no.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import CrawlBlocked, CrawlInterrupted
from scrapex.connectors.jsonld import SitemapUnreadable
from scrapex.connectors.salla import SallaConnector
from scrapex.connectors.zid import ZidConnector
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _RefusingFetcher:
    """Answers the sitemap, then refuses at the Nth product page."""

    def __init__(self, sitemap: str, page: str, error: Exception, refuse_after: int = 1):
        self.sitemap, self.page, self.error = sitemap, page, error
        self.child = sitemap.replace("_sitemap", "_subsitemap")
        self.refuse_after = refuse_after
        self.pages_fetched = 0
        self.requests_count = 0

    def get(self, url: str, **kwargs):
        self.requests_count += 1
        if url.endswith(".xml"):
            # The root lists a child sitemap; the child lists the products.
            return _Resp(_read(self.child if "sitemap-products" in url else self.sitemap))
        self.pages_fetched += 1
        if self.pages_fetched > self.refuse_after:
            raise self.error
        return _Resp(_read(self.page))


def salla_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="ALSWEED", source_name="السويد", base_url="https://alsweed.sa",
        family="salla-html", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)]))


def zid_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="ADVANCEDCASTLE", source_name="القلعة", base_url="https://advancedcastle.com",
        family="zid-html", currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)]))


@pytest.mark.parametrize("stop", [
    CrawlInterrupted("cancel"),              # the owner pressed Stop
    CrawlBlocked("403 five times over"),     # the site is refusing us
])
def test_salla_stops_when_told_to_stop(stop):
    fetcher = _RefusingFetcher("salla_sitemap.xml", "salla_product_simple.html", stop)
    connector = SallaConnector(fetcher)

    with pytest.raises(CrawlBlocked):
        list(connector.fetch(salla_entry()))

    assert fetcher.pages_fetched == 2, (
        "the walk carried on past the stop signal — it fetched "
        f"{fetcher.pages_fetched} pages")


@pytest.mark.parametrize("stop", [
    CrawlInterrupted("pause"),
    CrawlBlocked("403 five times over"),
])
def test_zid_stops_when_told_to_stop(stop):
    fetcher = _RefusingFetcher("zid_sitemap.xml", "zid_product_simple.html", stop)
    connector = ZidConnector(fetcher)

    with pytest.raises(CrawlBlocked):
        list(connector.fetch(zid_entry()))

    assert fetcher.pages_fetched == 2


def test_an_ordinary_dead_page_is_still_survived_and_counted():
    """The guard must narrow to the stop signal, not to every failure: one page
    that 404s has always been survivable, and reporting it is the GPP lesson."""
    fetcher = _RefusingFetcher("salla_sitemap.xml", "salla_product_simple.html",
                               RuntimeError("connection reset"), refuse_after=1)
    tables = list(SallaConnector(fetcher).fetch(salla_entry()))

    warnings = [w for t in tables for w in t.warnings]
    assert any("could not be fetched" in w for w in warnings), warnings
    # Every product in the fixture was still attempted, and the one that
    # answered still landed: a dead page costs its own row and nothing more.
    assert fetcher.pages_fetched == 2, "one dead page ended the whole crawl"
    assert sum(len(t.rows) for t in tables) == 1


class _BlockedSitemapFetcher:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.requests_count = 0

    def get(self, url: str, **kwargs):
        self.requests_count += 1
        raise self.error


def test_a_stop_on_the_sitemap_is_not_reported_as_an_empty_catalogue():
    """`except Exception: return []` said "this shop lists no products" when it
    meant "we never read the index". A cancelled crawl then published as a
    legitimate empty one."""
    for connector, entry in ((SallaConnector, salla_entry), (ZidConnector, zid_entry)):
        with pytest.raises(CrawlBlocked):
            list(connector(_BlockedSitemapFetcher(CrawlInterrupted("cancel"))).fetch(entry()))


def test_an_unreadable_sitemap_fails_the_source_instead_of_landing_zero_rows():
    for connector, entry in ((SallaConnector, salla_entry), (ZidConnector, zid_entry)):
        with pytest.raises(SitemapUnreadable):
            list(connector(_BlockedSitemapFetcher(OSError("no route to host"))).fetch(entry()))
