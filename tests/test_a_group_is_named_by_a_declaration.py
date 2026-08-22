"""`R-41`: a repeating group is named by a DECLARED map, and all three alternatives fail.

`R-38` needs to know which of `R-19`'s groups a row belongs to. Three rules suggest
themselves and every one of them was measured against the committed profile:

| rule | why it fails |
|---|---|
| the detector's own name | `Table 1` … `Table 5` — that is position, and position moves |
| the nearest heading | three of the five tables share one, and for two of them the nearest heading is a **tab button belonging to a different section** |
| the column signature | two tables carry the same `# / الإسم` pair, and both are **empty**, so there is not even a row to tell them apart |

So each site declares it, the way `CARD_FIELDS` and `PROFILE_FIELD_ORDER` already declare
what a listing and a profile publish.

TWO MEASUREMENTS MAKE THE DECLARATION SAFE, AND THEY POINT OPPOSITE WAYS.
Every table header and every contractor-tab label is **identical in both locales** —
Arabic even on the English page — so a selector built on that text is locale-stable. The
interests card is **not**: it reads `Interests` in English and `الأنشطة` in Arabic, which
is not a translation of it. So that one is located structurally and the rest by their
untranslated text, and this file asserts both facts rather than trusting either.

AND WHAT COULD NOT BE FOUND IS DECLARED TOO. `R-19` names five groups; two of them are
listing FILTER axes and not profile sections, one is two groups in separate tabs, and the
technical-rating tab holds no table at all. Recording that keeps "we could not find it"
from becoming a silently shorter list — which is how a build covers four of five groups
and reports success.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scrapex.extract.html_table import detect_html_tables
from scrapex.extract.muqawil import (
    GROUPS_NOT_LOCATED,
    MULTI_VALUED_GROUPS,
    locate_group,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


def _html(locale: str) -> str:
    return (FIXTURES / f"profile-{locale}.html").read_text(encoding="utf-8")


def _size(element, kind: str) -> int:
    if element is None:
        return -1
    return len(element.select("tbody tr" if kind == "table" else "li.list-item"))


# ---- the declaration works, and identically in both locales -------------------

def test_every_declared_group_is_found_on_the_profile():
    located = {group.key: locate_group(_html("en"), group.key) is not None
               for group in MULTI_VALUED_GROUPS}

    assert located == dict.fromkeys(located, True), located
    assert len(MULTI_VALUED_GROUPS) == 5


def test_both_locales_locate_the_same_groups_with_the_same_sizes():
    """THE PARITY THAT CATCHES A LOCALE-DEPENDENT SELECTOR. It is the assertion that
    found the interests bug: a title-based rule read 25 nodes from English and 0 from
    Arabic, and nothing else would have noticed."""
    english = {g.key: _size(locate_group(_html("en"), g.key), g.kind)
               for g in MULTI_VALUED_GROUPS}
    arabic = {g.key: _size(locate_group(_html("ar"), g.key), g.kind)
              for g in MULTI_VALUED_GROUPS}

    assert english == arabic
    assert english["interests"] == 25
    assert english["licensed_activities"] == 6


def test_three_of_the_five_are_empty_and_that_is_a_real_state():
    """`R-19`'s own "one contractor" limit, from the other side. Two contractor lists and
    the contract-counts table are the groups this contractor barely fills — so a build
    verified against this fixture alone proves very little about them."""
    sizes = {g.key: _size(locate_group(_html("en"), g.key), g.kind)
             for g in MULTI_VALUED_GROUPS}

    assert sizes["sub_contractors"] == 0
    assert sizes["main_contractors"] == 0
    assert sizes["contract_counts"] == 1


# ---- the two measurements the selectors rest on ------------------------------

def test_the_table_headers_are_not_translated_which_is_what_makes_them_usable():
    """A SELECTOR ON CONTENT IS ONLY SAFE IF THE CONTENT IS STABLE, and here it is —
    measured, not assumed. Every table header is the same string on both pages."""
    headers = {}
    for locale in ("en", "ar"):
        soup = BeautifulSoup(_html(locale), "html.parser")
        headers[locale] = [
            [th.get_text(" ", strip=True) for th in table.select("th")]
            for table in soup.find_all("table")]

    assert headers["en"] == headers["ar"]
    assert "الأنشطة المرخصة" in headers["en"][0]


def test_the_interests_card_title_IS_translated_which_is_why_it_is_structural():
    """THE OPPOSITE MEASUREMENT, and it is why one group is declared differently from
    the other four. `Interests` and `الأنشطة` are not translations of each other, so a
    title-based selector reads one locale and silently misses the other."""
    titles = {}
    for locale in ("en", "ar"):
        card = locate_group(_html(locale), "interests")
        titles[locale] = card.select_one("h3.card-title").get_text(strip=True)

    assert titles["en"] == "Interests"
    assert titles["ar"] == "الأنشطة"

    interests = next(g for g in MULTI_VALUED_GROUPS if g.key == "interests")
    assert "Interests" not in interests.selector, (
        "the interests selector must not name a title — that is the bug it exists to "
        "avoid")


def test_the_two_identical_tables_are_separated_by_an_id_and_nothing_else():
    """WHY A DECLARATION AND NOT A SIGNATURE. These two carry the same headers and both
    are empty, so an id is the only thing that distinguishes them — which is exactly what
    a declared selector can say and a heuristic cannot."""
    soup = BeautifulSoup(_html("en"), "html.parser")
    sub = locate_group(_html("en"), "sub_contractors")
    main = locate_group(_html("en"), "main_contractors")

    assert [th.get_text(strip=True) for th in sub.select("th")] == \
           [th.get_text(strip=True) for th in main.select("th")]
    assert sub.find_parent("div", class_="tab-pane").get("id") == "contractor-tab2"
    assert main.find_parent("div", class_="tab-pane").get("id") == "contractor-tab3"
    # THE BUTTON IS WHAT NAMES THE PANE, and it points at it with `data-bs-target` — not
    # `href`, which the first version of this assertion assumed and which matches nothing
    # on the page. The evidence for calling this group `sub_contractors` is that label, so
    # the test reads it rather than trusting the name we gave it.
    assert soup.select_one('[data-bs-target="#contractor-tab2"]').get_text(
        strip=True) == "المقاولين بالباطن"
    assert soup.select_one('[data-bs-target="#contractor-tab3"]').get_text(
        strip=True) == "المقاولين الرئيسيين"


def test_the_detectors_own_names_are_positional_so_none_is_used():
    """PINS THE REASON the map exists at all."""
    assert [table.name for table in detect_html_tables(_html("en"))] == [
        f"Table {n}" for n in range(1, 6)]
    assert not any(group.key.startswith("table") for group in MULTI_VALUED_GROUPS)


# ---- the failure modes --------------------------------------------------------

def test_an_undeclared_key_says_what_is_declared_and_what_was_not_found():
    with pytest.raises(KeyError) as raised:
        locate_group(_html("en"), "qualification_programs")

    said = str(raised.value)
    assert "interests" in said, "it must list what IS declared"
    assert "qualification_programs" in said, "and name why this one is not"


def test_a_selector_that_stopped_being_unique_is_refused():
    """A selector matching twice has stopped being a declaration, and picking the first
    would read one group's values as another's."""
    doubled = (
        "<html><body>"
        "<div id='contractor-tab2'><table><tr><th>#</th></tr></table></div>"
        "<div id='contractor-tab2'><table><tr><th>#</th></tr></table></div>"
        "</body></html>")

    with pytest.raises(ValueError) as raised:
        locate_group(doubled, "sub_contractors")

    assert "no longer a declaration" in str(raised.value)


def test_a_profile_without_the_group_answers_none_rather_than_raising():
    """Three of five are empty here and two render nothing at all, so a missing section
    is the common case — an exception would make one absence break a whole profile."""
    assert locate_group("<html><body></body></html>", "interests") is None


# ---- and what R-19 names that the page does not publish -----------------------

def test_what_could_not_be_located_is_declared_rather_than_dropped():
    """"We could not find it" has to be a recorded fact. Otherwise the list is quietly
    shorter and a build covers four of five groups while reporting success."""
    keys = {key for key, _ in GROUPS_NOT_LOCATED}

    assert {"qualification_programs", "balady_services"} <= keys
    reasons = dict(GROUPS_NOT_LOCATED)
    assert "lc_program_list_id" in reasons["qualification_programs"]
    assert "balady_service_id" in reasons["balady_services"]
    assert "contractor-tab4" in reasons["technical_rating"]


def test_the_declared_and_the_unlocated_do_not_overlap():
    """A group cannot be both found and not found, and a name in both lists would make
    every count computed from them wrong."""
    declared = {group.key for group in MULTI_VALUED_GROUPS}
    missing = {key for key, _ in GROUPS_NOT_LOCATED}

    assert declared & missing == set()
    # R-19 names five groups; the page publishes five, and they are not the same five.
    assert len(declared) == 5
    assert len(missing) == 3
