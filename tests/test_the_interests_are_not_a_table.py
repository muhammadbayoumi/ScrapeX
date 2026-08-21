"""The biggest of `R-19`'s five groups is not a table, and the plan said it was.

WHAT THE PLAN ASSERTED. *"The profile page carries five real `<table>` elements — the
licences and their readiness, the two contractor lists, the technical rating, the
contract counts. Those go through `detect_html_tables` like any other site's tables, and
they are exactly the multi-valued groups `R-19` wants in child tables."*

WHAT IS ACTUALLY THERE, measured against the committed profile:

    <table> elements                       5
    …of which are Interests                0
    Interests is a nested <ul class="list list-numerical"> in a div.section-card

`R-19`'s five named groups are Interests, Licensed Activities, Qualification Programs,
Balady Services and contractor relations. Interests is the **largest** — the study
measured 30 values in 6 groups for one contractor and priced the group at ~235 MB at
full scale — so building on the five-tables premise would have produced four groups and
silently missed the biggest one.

AND THREE OF THE FIVE TABLES ARE EMPTY on the only committed profile: the two contractor
lists and the technical rating parse to 0 rows. That is the same evidence limit `R-19`
named about itself — *"one contractor"* — arriving from the other side.

WHAT IS BUILT HERE AND WHAT IS NOT. Reading is built, because every candidate storage
shape needs it. WRITING is not: whether these become a child dataset referencing
`classification_node` (the study's recommendation, shape F) or a pure taxonomy (shape D)
is `R-19`'s open question and is **awaiting his ruling**.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scrapex.extract.html_table import detect_html_tables
from scrapex.extract.muqawil import read_interests

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


def _html(locale: str) -> str:
    return (FIXTURES / f"profile-{locale}.html").read_text(encoding="utf-8")


# ---- the premise this corrects -------------------------------------------------

def test_the_page_has_five_tables_and_none_of_them_is_interests():
    """THE MEASUREMENT THAT CORRECTS THE PLAN. Five `<table>` elements, and the
    interests block is not one of them."""
    html = _html("en")
    soup = BeautifulSoup(html, "html.parser")

    assert len(soup.find_all("table")) == 5

    card = soup.select_one("div.section-card:has(ul.list-numerical li.list-item)")
    assert card is not None, "the interests block must exist to be missing from tables"
    assert card.find("table") is None, "interests are a list, not a table"
    assert not any(table.find_parent("div", class_="section-card") is card
                   for table in soup.find_all("table"))


def test_three_of_the_five_tables_are_empty_for_this_contractor():
    """`R-19`'s own evidence limit, from the other side. The two contractor lists and
    the technical rating carry no data rows on the only committed profile — so a build
    that verified itself against this fixture alone would prove almost nothing about
    three of the five groups."""
    found = detect_html_tables(_html("en"))

    assert len(found) == 5
    empty = [table for table in found if not table.rows]
    assert len(empty) == 3


def test_detect_html_tables_names_them_by_position_not_by_meaning():
    """WHY THE GROUPS CANNOT BE IDENTIFIED FROM THE TABLE ALONE. The names come back
    `Table 1`…`Table 5`, and the nearest heading does not disambiguate either: three of
    the five sit under one heading. Whatever `R-19` is built on will need a naming rule
    that is neither positional nor "the previous `<h3>`".
    """
    found = detect_html_tables(_html("en"))

    assert [table.name for table in found] == [f"Table {n}" for n in range(1, 6)]

    soup = BeautifulSoup(_html("en"), "html.parser")
    headings = [table.find_previous(["h1", "h2", "h3", "h4"]).get_text(strip=True)
                for table in soup.find_all("table")]
    assert len(set(headings)) < len(headings), "at least two tables share a heading"


# ---- reading the hierarchy ----------------------------------------------------

def test_both_locales_read_the_same_shape():
    """THE ASSERTION THAT CAUGHT THE REAL BUG. The first version of `read_interests`
    matched the heading text `"Interests"` and read **25 nodes from English and 0 from
    Arabic**, because the Arabic heading is `الأنشطة` — "Activities", not a translation.

    Titles are content and are not parallel between locales. `DSN-05` cost a day to the
    same class of mistake, where a slug filter reduced every Arabic label to nothing and
    produced two empty strings for every contractor in the country.
    """
    english = read_interests(_html("en"))
    arabic = read_interests(_html("ar"))

    assert len(english) == len(arabic) == 25
    assert (Counter(len(path) for path in english)
            == Counter(len(path) for path in arabic) == {1: 3, 2: 5, 3: 17})


def test_the_headings_really_do_differ_so_the_selector_must_be_structural():
    """PINS THE REASON, so nobody re-simplifies the selector back to a title match."""
    titles = {}
    for locale in ("en", "ar"):
        soup = BeautifulSoup(_html(locale), "html.parser")
        card = soup.select_one("div.section-card:has(ul.list-numerical li.list-item)")
        titles[locale] = card.select_one("h3.card-title").get_text(strip=True)

    assert titles["en"] == "Interests"
    assert titles["ar"] == "الأنشطة"
    assert titles["en"] != titles["ar"]


def test_every_node_is_a_path_and_the_interior_nodes_are_there():
    """A TAXONOMY NEEDS ITS PARENTS TO EXIST. `classification_node` has
    `parent_node_id`, so a leaf cannot be written before the node above it — returning
    leaves alone would leave the parents to be inferred, which is the guessing this
    function removes."""
    paths = read_interests(_html("en"))

    roots = {path[0] for path in paths}
    assert len(roots) == 3
    # Every path's own prefix is also a node that was returned.
    returned = set(paths)
    for path in paths:
        for depth in range(1, len(path)):
            assert path[:depth] in returned, f"{path[:depth]} is a parent nobody wrote"


def test_a_name_repeats_across_levels_so_a_name_is_not_an_identity():
    """THE STUDY'S FINDING, ON THIS FIXTURE. `Construction of buildings` is both a
    level-1 node and a level-2 node beneath itself — so an identity built from the name
    would merge two different nodes, which is exactly what the `R-19` study measured
    with `الصرف الصحي` sitting under more than one parent."""
    paths = read_interests(_html("en"))

    names = Counter(path[-1] for path in paths)
    repeated = {name for name, count in names.items() if count > 1}

    assert repeated, "no repeated leaf name, so this fixture cannot make the point"
    assert "Construction of buildings" in repeated


def test_the_parent_is_the_preceding_sibling_and_not_an_ancestor():
    """THE MARKUP'S ONE TRAP. A child `<ul>` sits BESIDE the `<li>` it belongs to, so
    walking `parents` finds the right depth and never the right names — every leaf would
    come back as a child of nothing."""
    paths = read_interests(_html("en"))

    deep = [path for path in paths if len(path) == 3]
    assert deep
    assert ("Civil engineering", "Construction of roads and railways") in {
        path[:2] for path in deep}


# ---- the failure modes --------------------------------------------------------

def test_a_profile_without_the_section_reads_as_empty_and_does_not_raise():
    """ABSENT IS A REAL STATE. A contractor with no interests exists, and an exception
    would make the whole profile unreadable for one missing section."""
    assert read_interests("<html><body><div class='section-card'></div></body></html>") == ()


def test_two_numerical_lists_are_refused_rather_than_guessed():
    """AMBIGUOUS IS NOT A GUESS. The card is identified by holding the list, so a page
    that grows a second one makes that description mean two things — and picking the
    first would read one group's values as another's."""
    doubled = (
        "<html><body>"
        "<div class='section-card'><ul class='list list-numerical'>"
        "<li class='list-item'>one</li></ul></div>"
        "<div class='section-card'><ul class='list list-numerical'>"
        "<li class='list-item'>two</li></ul></div>"
        "</body></html>")

    with pytest.raises(ValueError) as raised:
        read_interests(doubled)

    assert "layout has changed" in str(raised.value)
