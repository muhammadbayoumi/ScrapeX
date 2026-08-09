"""Fourteen minutes and thirty-four hours are two products, not two settings.

The owner decided on 2026-08-05 that crawl depth is a PER-SOURCE choice, and the
measurements on muqawil.org are the argument:

    the listing            860 pages          14 minutes at 1s
    every detail page    121,157 requests     34 hours at 1s, 17 at 0.5s

Change-tracking repeats whichever was chosen, so the difference is not paid once.

WHAT THESE TESTS PROTECT. Not arithmetic — the arithmetic is three lines. They
protect two decisions that are easy to erode later, both in the direction of
costing a user a day and a half they never agreed to:

  · the DEFAULT stays the cheapest one
  · naming a slice is REQUIRED, not defaulted to "everything"
"""

from __future__ import annotations

import sqlite3

import pytest

from scrapex.crawlscope import (
    DEFAULT, CrawlScope, SliceRequired, is_expensive, plan,
)

#: Measured on muqawil.org and used only as a realistic size. No production code
#: carries these — one site's numbers are not every site's.
MUQAWIL_LISTING = 860
MUQAWIL_DETAILS = 121_157


def test_listing_only_fetches_the_listing_and_nothing_else():
    p = plan(CrawlScope.LISTING_ONLY,
             listing_pages=MUQAWIL_LISTING, detail_pages=MUQAWIL_DETAILS)

    assert p.detail_pages == 0
    assert p.requests == MUQAWIL_LISTING
    assert round(p.seconds_at(1.0) / 60) == 14, "the measured fourteen minutes"


def test_the_full_crawl_is_the_thirty_four_hours_it_says_it_is():
    """The expensive option is not hidden or discouraged — it is offered with
    its price attached. FULL_THEN_LISTING exists so an owner who wants
    everything can have it deliberately."""
    p = plan(CrawlScope.FULL_THEN_LISTING,
             listing_pages=MUQAWIL_LISTING, detail_pages=MUQAWIL_DETAILS)

    assert round(p.hours_at(1.0)) == 34
    assert round(p.hours_at(0.5)) == 17, "the measured half-pace figure"


def test_a_slice_must_be_named_and_is_never_assumed():
    """THE DECISION MOST EASILY ERODED. The obvious default for a missing slice
    is 'all of them' — which is the thirty-four hours, arriving under the name
    of the cheap option. It is refused instead."""
    with pytest.raises(SliceRequired, match="needs the slice named"):
        plan(CrawlScope.LISTING_PLUS_SLICE,
             listing_pages=MUQAWIL_LISTING, detail_pages=MUQAWIL_DETAILS)

    p = plan(CrawlScope.LISTING_PLUS_SLICE, listing_pages=MUQAWIL_LISTING,
             detail_pages=MUQAWIL_DETAILS, slice_pages=1_200, slice_of="Riyadh")

    assert p.slice_of == "Riyadh"
    assert p.detail_pages == 1_200, "the slice, not every detail page"
    assert p.hours_at(1.0) < 1, "a slice that costs hours is not a slice"


def test_the_default_is_the_cheapest_one():
    """A default that costs thirty-four hours is a default that runs before
    anyone has understood what they asked for."""
    assert DEFAULT is CrawlScope.LISTING_ONLY


def test_an_expensive_crawl_can_be_told_apart_before_it_starts():
    """Not a refusal — the owner may want it. The difference between a choice
    and a surprise."""
    cheap = plan(CrawlScope.LISTING_ONLY,
                 listing_pages=MUQAWIL_LISTING, detail_pages=MUQAWIL_DETAILS)
    dear = plan(CrawlScope.FULL_THEN_LISTING,
                listing_pages=MUQAWIL_LISTING, detail_pages=MUQAWIL_DETAILS)

    assert not is_expensive(cheap, pace_s=1.0)
    assert is_expensive(dear, pace_s=1.0)
    # Even at half pace it is seventeen hours, so the pace is not the answer.
    assert is_expensive(dear, pace_s=0.5)


def test_it_is_not_the_scope_that_already_exists():
    """`vocab.ExtractScope` is CONTRACT WIDTH for a price payload — how many
    fields it may carry. This is how many PAGES a crawl may fetch. One name for
    both would make every later reader work out which was meant."""
    from scrapex.vocab import ExtractScope

    assert not set(CrawlScope) & set(ExtractScope), (
        "the two scopes share a value, so a stored string no longer says which "
        "question it answers")


# ---- and the database carries it, per source --------------------------------

def test_every_source_carries_its_own_scope(tmp_path):
    """Per-source is the whole decision. A project-wide setting would make one
    site's affordable answer another site's day and a half."""
    from scrapex.databases.domain import EngineDatabase

    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()

    con = db.connect()
    try:
        con.execute(
            "INSERT INTO site_profile (site_key, display_name, base_url, lifecycle) "
            "VALUES ('muqawil', 'muqawil.org', 'https://muqawil.org/', 'draft')")
        con.commit()
        scope, sl = con.execute(
            "SELECT crawl_scope, crawl_slice FROM site_profile "
            "WHERE site_key='muqawil'").fetchone()
    finally:
        con.close()

    # A row that was never asked gets the cheapest answer, not the dearest.
    assert scope == DEFAULT.value
    assert sl is None, "a slice was invented for a scope that does not use one"
