"""T1: a source may declare the pace it needs, and slowest always wins.

WHY THIS EXISTS, measured 2026-08-13 against the live warehouse. ALSWEED was
aborting on "5 refusals in a row (last: HTTP 429)" — jobs 84 and 85 on 1 August,
98 on 2 August, 120 and 121 on 11 August — and each of those runs collected
nothing at all.

The remedy on record was to restore `crawl_honour_delay`. It would not have
worked: alsweed.sa/robots.txt publishes a Sitemap, one Disallow and NO
Crawl-delay, and `honour_crawl_delay` only takes effect when a site declares one
(connectors/base.py, `_robots_for`). The switch would have been flipped, nothing
would have improved, and the diagnosis would have lost its credibility.

The only other lever was the tool-wide `crawl_min_interval_s`, and raising that
slows elburoj's 6,720 products — a source that already asks for ten seconds — to
spare one shop.

AND ONE OF THE THREE PACES WAS NEVER CONNECTED. `robots_custom.crawl_delay_s` is
declared in the manifest, documented on the model, shown in the web UI and
computed all the way into `Decision.delay_s` — and `decide()`'s verdict is read
only for `may_fetch`, on a path robots.txt DISALLOWS. An owner who set a
per-source delay saw it in the interface and it did nothing.
"""
from __future__ import annotations

import pytest

from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import resolve_fetcher
from scrapex.vocab import ExtractKind, ExtractScope


def entry(**over) -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="TESTSHOP", source_name="Test Shop",
        base_url="https://example.test", family="zid-html",
        currency="SAR", default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                             scope=ExtractScope.CENSUS)],
        **over))


def pace(source, **settings) -> float:
    fetcher = resolve_fetcher(source, {"min_interval_s": 1.0, **settings})
    return fetcher._min_interval_s


def test_a_source_that_asks_for_nothing_keeps_the_owners_pace():
    """The overwhelmingly common case, and the one a regression would hit
    first: eleven of twelve sources declare no pace at all."""
    assert pace(entry()) == 1.0
    assert pace(entry(), min_interval_s=2.5) == 2.5


def test_a_source_may_ask_to_be_crawled_more_slowly():
    assert pace(entry(crawl_pace_s=3.0)) == 3.0


def test_it_can_only_ever_slow_a_crawl_down():
    """A per-source pace is a brake, never an accelerator.

    Otherwise a number typed too small — or copied from another source — would
    quietly overrule the owner's own setting and crawl FASTER than he chose,
    which is the one direction politeness never goes."""
    assert pace(entry(crawl_pace_s=0.2), min_interval_s=2.0) == 2.0
    assert pace(entry(crawl_pace_s=5.0), min_interval_s=2.0) == 5.0


def test_a_pace_of_zero_or_less_is_refused_by_the_manifest():
    """Not clamped quietly. Zero seconds between requests is not a pace anyone
    means, and accepting it would put the fastest possible crawl one typo away
    from a field whose entire purpose is to slow one down."""
    for refused in (0, -1, -0.5):
        with pytest.raises(Exception):
            entry(crawl_pace_s=refused)


def test_the_custom_robots_delay_finally_reaches_the_fetcher():
    """THE DEFECT THIS TEST WAS WRITTEN FOR.

    `robots_custom.crawl_delay_s` was declared, documented, surfaced in the web
    UI and computed into `Decision.delay_s`, and no code read it. Break the
    `custom_delay` branch in `resolve_fetcher` and this fails."""
    source = entry(robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": 4.0})
    assert pace(source) == 4.0


def test_when_both_are_declared_the_slower_one_wins():
    source = entry(crawl_pace_s=2.0, robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": 6.0})
    assert pace(source) == 6.0

    source = entry(crawl_pace_s=8.0, robots="custom",
                   robots_custom={"enforce_disallow": False, "crawl_delay_s": 6.0})
    assert pace(source) == 8.0


def test_a_null_custom_delay_still_means_the_sites_own():
    """The documented meaning of a null: "A null delay means the site's own."
    So it must NOT be read as zero and must not disturb the pace here — the
    site's own delay is applied later, in `_robots_for`."""
    source = entry(robots="custom",
                   robots_custom={"enforce_disallow": True, "crawl_delay_s": None})
    assert pace(source, min_interval_s=1.5) == 1.5


def test_alsweed_carries_the_pace_this_task_was_about():
    """Pinned against the real manifest, because a per-source setting that gets
    dropped in an edit is invisible: the crawl simply speeds back up and the
    429s return weeks later."""
    from scrapex import config

    manifest = config.load_manifest()
    sources = getattr(manifest, "sources", manifest)
    alsweed = next(s for s in sources if s.source_key == "ALSWEED")
    assert alsweed.crawl_pace_s is not None, (
        "ALSWEED's per-source pace is gone; it was refused with HTTP 429 at the "
        "tool-wide one second")
    assert alsweed.crawl_pace_s >= 2.0
    # And it must actually reach the transport, not merely sit in the file.
    assert pace(alsweed) == alsweed.crawl_pace_s


def test_the_pace_survives_the_panel_saving_that_source(tmp_path, monkeypatch):
    """A per-source setting that the panel silently drops on the next edit is
    worse than one that never existed: the crawl speeds back up and the 429s
    return weeks later with nothing to point at.

    manifest_io.py already carries a warning about exactly this — twelve fields
    were once rebuilt out of existence every time the panel saved a rename — so
    the new field is driven through the REAL writer rather than trusted to a
    generic loop that looks like it covers everything."""
    from scrapex import config, manifest_io

    written = tmp_path / "sources.yaml"
    written.write_text(
        __import__("pathlib").Path("sources.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    monkeypatch.setenv("SCRAPEX_SOURCES", str(written))

    def alsweed():
        manifest = config.load_manifest()
        sources = getattr(manifest, "sources", manifest)
        return next(s for s in sources if s.source_key == "ALSWEED")

    before = alsweed()
    assert before.crawl_pace_s == 3.0
    manifest_io.update_source("ALSWEED", before, path=written)

    assert alsweed().crawl_pace_s == 3.0, (
        "saving ALSWEED through the panel's own writer dropped its pace")
