"""The census asks the PAGE, and every probe here was wrong once.

ISSUE 546. The standing claim -- "the site publishes nothing we do not read" -- rested on
1,200 of 34,834 pages that were the first 1,200 snapshot ids, which is the lowest
contractor ids and not a sample; and `undeclared_cards` cannot report a text-only card,
because nothing distinguishes one from the contractor's own name card.

RUN ON 2,000 RANDOMLY SAMPLED PAGES, 2026-09-09: the claim holds. Zero undeclared labels,
zero undeclared cards carrying data, and every field the page publishes reaches the row.
The low fill rates are the SITE's -- address 8.3%, activity 5.3%, mobile 31.7%, a real map
pin 15.1%.

AND IT ONLY HOLDS BECAUSE TWO PROBES WERE CORRECTED FIRST. Both measured a PROXY and
both reported the parser's own documented judgement as a defect:

    read_coordinates() is not None       299 of 299 pages "have" coordinates against
                                         42 stored rows -- a 257-page phantom gap
    the self-build CARD is published      26 pages against 6 rows -- another phantom

A census whose instrument is a proxy agrees with nothing and accuses the parser. Every
test below is one of those lessons, kept so the phantom cannot come back.
"""
from __future__ import annotations

import pathlib

import pytest

from scrapex.extract.muqawil import DEFAULT_MAP_PIN, PROFILE_FIELDS

# THE TOOL IMPORTS `bs4` AT MODULE LEVEL, so this import IS the skip condition -- an
# `importorskip` after it would run too late.
pytest.importorskip("bs4")
from tools.profile_card_census import (
    LISTING_ONLY_LABELS,
    census_page,
    declared_card_titles,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "muqawil"
PROFILE = (FIXTURES / "profile-en.html").read_text(encoding="utf-8")
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")


def test_a_real_profile_publishes_only_labels_we_declare():
    """THE MEASUREMENT THE ISSUE ASKED FOR, on one page rather than two thousand: every
    label the page carries is one of the eleven, so there is nothing unread."""
    facts = census_page(PROFILE)

    assert facts.seen, "the census read no labels at all off a real profile"
    undeclared = set(facts.seen) - set(PROFILE_FIELDS)
    assert undeclared == set(), (
        f"the page publishes labels nothing declares: {sorted(undeclared)}")
    assert facts.is_a_listing is False


def test_a_listing_page_is_named_and_kept_out_of_the_label_census():
    """A LISTING'S LABELS ARE ANOTHER DOCUMENT'S. 5 of 2,000 sampled pages were the
    contractors listing -- what the site answers with when an id no longer resolves, at
    HTTP 200 -- and folding their boxes in would report listing columns as profile
    fields."""
    facts = census_page(LISTING)

    assert facts.is_a_listing, (
        f"a listing page was censused as a profile; its labels were "
        f"{sorted(facts.seen)[:6]}")
    assert LISTING_ONLY_LABELS & set(facts.seen), "the listing marker is not the labels"
    assert len(facts.linked_ids) > 1, (
        "a listing links to many contractors and a profile to itself alone")


def test_the_default_map_pin_is_not_a_coordinate():
    """THE 257-PAGE PHANTOM. `merge_locales` refuses to promote `DEFAULT_MAP_PIN` to a
    coordinate column because the site emits the centre of Riyadh identically for 14,621
    contractors, so it says nothing about any of them. A probe that counted any pair
    reported that refusal as a 257-page defect."""
    default = _with_pin(*DEFAULT_MAP_PIN)
    real = _with_pin(24.671699788528482, 46.39415764160163)

    assert census_page(default).has_coordinates is False, (
        "the site's default pin was counted as a place, so the census accuses the "
        "parser of losing 14,621 coordinates it deliberately refused")
    assert census_page(real).has_coordinates is True
    assert census_page(_with_pin(24.4493518, 0)).has_coordinates is False, (
        "a zero half is the site's 'no pin' and was counted as the Gulf of Guinea")


def test_a_self_build_card_with_no_priced_row_is_not_a_price():
    """THE SECOND PHANTOM. `read_self_build_prices` records that the card sits on 713 of
    2,419 pages and carries rows on 163: a contractor in the programme who has not priced
    it has the card and no rows, and both are real states."""
    # THE COMMITTED PROFILE IS THE PHANTOM ITSELF: it publishes the card and prices
    # nothing, which is why "the card is published" was the wrong question.
    assert census_page(PROFILE).has_self_build_row is False, (
        "the committed profile prices nothing and was counted as a price, which is "
        "how 26 pages became a 20-row phantom gap")
    assert census_page(_empty_self_build()).has_self_build_row is False
    assert census_page(_priced_self_build()).has_self_build_row is True, (
        "a card with a filled value cell is a price and the probe missed it")


def test_a_text_only_card_is_censused_even_though_the_guard_cannot_see_it():
    """THE BLIND SPOT, COVERED BY CENSUS RATHER THAN BY CHANGING THE GUARD.
    `undeclared_cards` reports only cards CARRYING DATA, because a text-only card cannot
    be told from the contractor's own name -- measured wrong on 0 of 5,668 pages that
    way and on 40 by position. So this counts every title with its carries-data flag and
    lets a person read the list.

    On the 2,000-page sample that turned up `Commercial Registration Certificate`, which
    looked like an unread section and is the identity card wearing a heading: 9 info
    boxes, no table, no list, and all nine already stored.
    """
    facts = census_page(_titled_text_card("Commercial Registration Certificate"))

    titles = dict(facts.cards)
    assert "Commercial Registration Certificate" in titles, (
        "a text-only card is invisible to the census as well as to the guard, so the "
        "blind spot is still blind")
    assert titles["Commercial Registration Certificate"] is False, (
        "a card with no table and no list was reported as carrying data")
    assert "Commercial Registration Certificate" not in declared_card_titles()


def test_a_title_that_appears_twice_keeps_its_data_flag():
    """ANY CARRYING INSTANCE WINS. The same title can appear twice on one page, and a
    census that let the last one decide would file a data card as text-only.

    THE DATA CARD COMES FIRST, AND THAT ORDER IS THE TEST. With the text card last, a
    "last one wins" mutation is invisible -- it was, and the mutation survived until
    the order was swapped. Written down because the same shape hides in any test of an
    accumulator.
    """
    both = _titled_data_card("Interests") + _titled_text_card("Interests")

    assert dict(census_page(both).cards)["Interests"] is True


# ---- the smallest pages that carry each fact --------------------------------

def _with_pin(lat: float, lng: float) -> str:
    return ("<html><body><script>var latlang = { lat: " + repr(lat)
            + ", lng: " + repr(lng) + " };</script></body></html>")


def _titled_text_card(title: str) -> str:
    return (f'<div class="section-card"><h4 class="card-title">{title}</h4>'
            '<div class="info-box"><span class="info-name">City</span>'
            '<span class="info-value">RIYADH</span></div></div>')


def _titled_data_card(title: str) -> str:
    return (f'<div class="section-card"><h4 class="card-title">{title}</h4>'
            '<ul class="list-numerical"><li class="list-item">Something</li></ul></div>')


def _self_build(value: str) -> str:
    return ('<div class="section-card"><h4 class="card-title">'
            'العقود سعر البناء (برنامج البناء الذاتي)</h4>'
            '<table><tr><td>Under five projects</td><td>' + value
            + '</td></tr></table></div>')


def _empty_self_build() -> str:
    return _self_build("")


def _priced_self_build() -> str:
    return _self_build("1,500 SAR")
