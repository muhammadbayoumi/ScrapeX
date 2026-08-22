"""The profile page has seven cards and three of them had no reader.

WHAT HE SAID, mid-measurement on 2026-08-22, and it changed the design:

    «المعلومات غير ثابته ولا متفقثة بين الصفح يعنى ممكن تلاقى معلومات تانية وطريقة
     عرض مختلفة»

The information is neither fixed nor consistent between pages; you may find other
information and a different presentation. He was right, and the parser was reading
one card of seven while three written premises in this repository said otherwise.

WHAT 2,419 REAL PROFILE PAIRS SAID, pulled read-only off the running crawl rather
than off the two committed fixtures:

    card                                        pages          what was wrong
    ------------------------------------------  -------------  -----------------------
    Contractor Detail (div.info-box)            2,419 / 2,419  nothing -- 11 labels,
                                                               all known, no drops
    التراخيص ومستوى الجاهزية                     2,419, rows on 228   deferred: "six
                                                               samples is not enough"
    العقود سعر البناء (برنامج البناء الذاتي)      713, rows on 163   NAMED BY NOBODY
    Previous Projects / المشاريع السابقة          92             filed under the wrong
                                                               card in the record
    Contract Request / طلب تعاقد                 2,419 / 2,419  believed absent
    Interests / الأنشطة                          2,419 / 2,419  nothing
    Map / الموقع                                 2,419 / 2,419  nothing

THE THREE CORRECTIONS, each of which was written down somewhere as fact:

  1. `extract/muqawil.py`'s module docstring named **the technical rating** as the
     fifth `<table>` on the page. There is no such table. `div#contractor-tab4`, the
     pane the tab button `التقييم الفني` points at, holds ZERO tables in its DOM
     subtree on 2,360 of 2,360 pages. The fifth table is the SELF-BUILD PRICE
     schedule, which is a **price**, in a price-tracking warehouse.
  2. The plan for this step says `contract_request_url` *"has no known URL pattern
     and is not on the card"*. The card is on 100% of pages; the URL is a site-wide
     constant, so it earns no column -- and the form it belongs to carries the
     **Commercial Registration number**, one of his own requested columns, on 2,542
     of 2,543 pages, ten digits, no two contractors sharing one.
  3. `write_groups` deferred the licences because *"six samples, one malformed, is
     not enough to declare that rule on"*. 1,685 rows say the split rule is
     provable, and say something the six could not: the dash in that cell is a
     HIERARCHY separator, not a language separator.

AND ONE MEASUREMENT THAT PREVENTED A BAD MERGE. Interests and licensed activities
look like one vocabulary and are two -- 211 English paths against 19, with **zero**
exact overlap -- while their Arabic ROOTS do overlap, and `ensure_path` is
idempotent on the Arabic name. One scheme would have fused the trees at the roots.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import taxonomy
from scrapex.contractors import write_groups
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.directories import get
from scrapex.extract.muqawil import (
    CONTRACT_COUNT_COLUMNS,
    GROUPS_MEASURED_EMPTY,
    MULTI_VALUED_GROUPS,
    PROFILE_CARDS,
    PROFILE_FIELD_ORDER,
    SELF_BUILD_PRICE_TIERS,
    UnknownPriceTier,
    bilingual_profile_candidate,
    read_cards,
    read_commercial_registration,
    read_contract_counts,
    read_licensed_activities,
    read_self_build_prices,
    undeclared_cards,
)
from scrapex.extract.service import _canonical, _digest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"

#: The contractor the committed fixtures are. Its own numbers, read off the pages.
FIXTURE_CR = "7007506731"
FIXTURE_LICENCE_ROWS = 6
FIXTURE_INTEREST_NODES = 25


def _page(locale: str) -> str:
    return (FIXTURES / f"profile-{locale}.html").read_text(encoding="utf-8")


@pytest.fixture()
def pages() -> tuple[str, str]:
    return _page("en"), _page("ar")


# ---- the census, which is his warning made mechanical ------------------------

def test_the_declaration_covers_every_card_the_page_publishes(pages):
    """THE GUARD HE ASKED FOR WITHOUT ASKING FOR IT. A parser reads the cards it knows
    and cannot tell a card that is absent from a card nobody declared."""
    for html in pages:
        assert undeclared_cards(html) == (), (
            "this page publishes a data-carrying card PROFILE_CARDS does not name, "
            "which is the state the price card sat in for months")


def test_the_price_card_is_declared_and_it_was_the_one_nobody_named(pages):
    """The specific hole. Had `PROFILE_CARDS` existed a day earlier, this card would
    have been reported the first time a profile was read."""
    declared = {card.key for card in PROFILE_CARDS}
    assert "self_build_prices" in declared
    assert "contract_counts" in declared
    english, _ = pages
    titles = [title for title, _ in read_cards(english)]
    assert "العقود سعر البناء (برنامج البناء الذاتي)" in titles


def test_a_new_card_with_a_table_is_reported(pages):
    """THE PROPERTY, not the fixture's luck: an unknown card carrying data is news.

    Injected rather than waited for, because the point is what happens the day the
    site adds a section — and this repository has a documented case of exactly that
    going unnoticed.
    """
    english, _ = pages
    grown = english.replace(
        '<div class="section-card">',
        '<div class="section-card"><h4 class="card-title">Bank Guarantees</h4>'
        "<table><thead><tr><th>Bank</th></tr></thead>"
        "<tbody><tr><td>Al Rajhi</td></tr></tbody></table></div>"
        '<div class="section-card">', 1)

    assert "Bank Guarantees" in undeclared_cards(grown)


def test_the_contractors_own_name_is_not_reported_as_a_new_card(pages):
    """THE FALSE POSITIVE THAT WOULD MAKE THE GUARD USELESS, and the reason the filter
    is content and not position.

    The company name is a card too and its title differs on every page. Measured
    across both locales: by POSITION the name card is first on 5,666 of 5,668 pages —
    wrong on 40 — and by CONTENT it carries neither table nor list on 5,668 of 5,668.
    """
    english, arabic = pages
    titles = {title for title, _ in read_cards(english)}
    assert "sca" in titles, "the fixture's own company-name card moved"
    assert "sca" not in undeclared_cards(english)
    assert "شركة البناء التجريبية" not in undeclared_cards(arabic)


# ---- the commercial registration, found in the form nobody opened ------------

def test_the_commercial_registration_comes_off_the_contract_form(pages):
    """One of HIS columns, believed unavailable. `Commercial Registration` appears four
    times in his study and no extractor had it."""
    for html in pages:
        assert read_commercial_registration(html) == FIXTURE_CR


def test_it_is_a_column_on_the_row(pages):
    """READ IS NOT STORED. A reader nobody wired produces nothing, which is the state
    `read_profile` left the profile's other cards in."""
    english, arabic = pages
    candidate = bilingual_profile_candidate(english, arabic, contractor_id="775")
    row = candidate.rows[0]

    assert row["commercial_registration"] == FIXTURE_CR
    assert "commercial_registration" in PROFILE_FIELD_ORDER


def test_a_page_with_no_contract_form_answers_empty_and_does_not_raise(pages):
    """ABSENT IS A STATE. 1 of 2,543 pages measured carries no form, and one page
    without one must not stop the approval of the others."""
    english, _ = pages
    without = english.replace("init_econtract_draft", "somewhere-else")

    assert read_commercial_registration(without) == ""


# ---- the prices, which are a price -------------------------------------------

def test_the_three_tiers_are_read_by_label_and_not_by_position():
    """MEASURED: the same three labels arrive in different orders on different pages.
    Position would have put the over-ten price in the under-five column on some pages
    and not others — a defect invisible in any column count.

    Built by shuffling the fixture's own card, because the fixture contractor
    publishes the card with no rows: 713 of 2,419 pages have the card and 163 have
    rows, so an empty one is the common case and cannot demonstrate the ordering.
    """
    labels = list(SELF_BUILD_PRICE_TIERS)
    rows = "".join(f"<tr><td>{label}</td><td>{value}</td></tr>"
                   for label, value in zip(reversed(labels), ("1000", "2000", "3000"),
                                           strict=True))
    html = ('<div class="section-card">'
            '<h4 class="card-title">العقود سعر البناء (برنامج البناء الذاتي)</h4>'
            f"<table><tbody>{rows}</tbody></table></div>")

    prices = read_self_build_prices(html)

    # The LAST label in the declaration was published FIRST, so a positional reader
    # would have given `under_five` the over-ten row's value.
    assert prices[SELF_BUILD_PRICE_TIERS[labels[-1]]] == "1000"
    assert prices[SELF_BUILD_PRICE_TIERS[labels[0]]] == "3000"


def test_an_empty_price_card_is_not_an_absent_one(pages):
    """Both are real states and neither is an error: the fixture contractor is in the
    self-build programme and has not priced it."""
    english, _ = pages

    assert read_self_build_prices(english) == {}
    assert any(card.key == "self_build_prices" for card in PROFILE_CARDS)


def test_a_fourth_tier_stops_rather_than_being_dropped():
    """THE ONE FAILURE A PRICE WAREHOUSE CANNOT HAVE. A price the site publishes and
    this warehouse silently does not store looks exactly like success.

    The same choice `CoordinatesMoved` already makes, applied to a number that is
    worth more than a coordinate.
    """
    html = ('<div class="section-card">'
            '<h4 class="card-title">العقود سعر البناء (برنامج البناء الذاتي)</h4>'
            "<table><tbody><tr>"
            "<td>سعر المتر المربع في حال الحصول على أكثر من عشرين مشروعا</td>"
            "<td>900</td></tr></tbody></table></div>")

    with pytest.raises(UnknownPriceTier, match="not one of the three declared tiers"):
        read_self_build_prices(html)


def test_two_price_cards_are_refused_rather_than_one_being_picked():
    """A title that has stopped being unique has stopped being a declaration —
    `locate_group`'s rule, and this reader obeys the same one."""
    card = ('<div class="section-card">'
            '<h4 class="card-title">العقود سعر البناء (برنامج البناء الذاتي)</h4>'
            "<table></table></div>")

    with pytest.raises(ValueError, match="no longer a declaration"):
        read_self_build_prices(card + card)


# ---- the contract counts, under a card named for something else --------------

def test_the_counts_are_keyed_on_the_headers_and_not_on_the_card_title(pages):
    """THE CARD IS NAMED FOR SOMETHING ELSE. It prints `Previous Projects` /
    `المشاريع السابقة` and its table holds two contract counts."""
    for html in pages:
        counts = read_contract_counts(html)
        assert counts == {"model_contract_count": "455",
                          "registered_contract_count": "64"}, counts
    assert set(CONTRACT_COUNT_COLUMNS.values()) == {"model_contract_count",
                                                   "registered_contract_count"}


def test_the_counts_reach_the_row(pages):
    english, arabic = pages
    row = bilingual_profile_candidate(english, arabic, contractor_id="775").rows[0]

    assert row["model_contract_count"] == "455"
    assert row["registered_contract_count"] == "64"


# ---- the licences, and the split rule --------------------------------------

def test_the_dash_is_a_hierarchy_separator_and_not_a_language_one(pages):
    """THE TRAP THE SIX SAMPLES HID. `write_groups` recorded the activity cell as
    carrying both languages *"in one string with no separator"*. There ARE dashes in
    it — they sit inside each language and they separate LEVELS.

    A parser that split on the dash would have cut a three-level path into pieces and
    called each piece a language.
    """
    english, _ = pages
    first = read_licensed_activities(english)[0]

    assert first.arabic == ("تشييد المباني", "تشييد المباني", "جميع الأنواع")
    assert first.english == ("Construction of Buildings",
                            "Construction of Buildings", "All Types")
    assert first.published_as.count(" - ") >= 2, (
        "the fixture's own cell no longer carries the dashes this rule is about")


def test_the_language_boundary_is_the_first_latin_letter(pages):
    """MEASURED over 1,500 rows: the script-run signature of every activity cell is
    `AL` — Arabic then Latin, exactly one transition, 1,500 of 1,500."""
    english, _ = pages

    for activity in read_licensed_activities(english):
        assert not any("؀" <= ch <= "ۿ" for part in activity.english
                       for ch in part), (
            f"Arabic leaked into the English half: {activity.english}")
        assert activity.arabic, "the Arabic half is the identity and cannot be empty"


def test_the_sites_own_broken_english_is_detected_by_a_level_count(pages):
    """THE LOAD-BEARING LUCK, and it is why nothing has to recognise an activity.

    Measured over 1,685 rows, the site publishes 100 with an English half that is
    truncated (`Civil Engineering -`, 30 rows) or names a DIFFERENT ACTIVITY (70
    rows). Every one of the three cases changes the number of levels, so comparing
    counts catches all of them — and the committed fixture happens to carry one.
    """
    english, _ = pages
    activities = read_licensed_activities(english)

    assert len(activities) == FIXTURE_LICENCE_ROWS
    unpaired = [one for one in activities if not one.paired]
    assert len(unpaired) == 1, (
        "the fixture's truncated row is what this asserts on; if the site fixed it, "
        "re-point this at another")
    assert unpaired[0].arabic == ("الهندسة المدنية", "الصرف الصحي")
    assert unpaired[0].english == (), (
        "a truncated English half must be EMPTY, not stored as a name: "
        "`Civil Engineering -` is the same string for two different activities, so "
        "storing it would merge them")
    assert "Civil Engineering -" in unpaired[0].published_as, (
        "the raw cell is kept as evidence so the disagreement can be looked at")


def test_the_readiness_level_is_read_even_though_it_is_not_stored(pages):
    """READ AND NOT STORED, on a count: empty on 1,490 of 1,500 rows. Reading it now
    means the day it earns a column it is a re-parse and not a re-crawl."""
    english, _ = pages
    first = read_licensed_activities(english)[0]

    assert (first.readiness_ar, first.readiness_en) == ("أساسي", "Basic")
    assert all(not one.readiness_ar for one in read_licensed_activities(english)[1:])


def test_one_page_is_enough_for_the_licences(pages):
    """THE DIFFERENCE FROM INTERESTS, and it is a property worth having: the cell is
    already bilingual, so a profile whose Arabic half never arrived still yields its
    licences in full. Nothing here can raise `CannotPairLocales`."""
    english, arabic = pages

    assert read_licensed_activities(english) == read_licensed_activities(arabic)


# ---- and the two of them reaching the warehouse ------------------------------

def _warehouse(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    return registry.engine.connect()


def _a_profile_row(conn, contractor_id: str = "775") -> None:
    """The one row `write_groups` requires, in the PROFILE dataset it looks in."""
    conn.execute("INSERT INTO site_profile (site_key, display_name, base_url) "
                 "VALUES ('muqawil_org','Contractors','https://muqawil.org')")
    conn.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash) "
        "VALUES ('https://muqawil.org/en/contractors/775/143','<html></html>','h')")
    conn.execute(
        "INSERT INTO dataset_definition (site_profile_id, dataset_key, original_name, "
        " dataset_kind, discovery_method, locator_json) "
        "VALUES (1,'contractor_profiles','contractor_profiles','table','html_table','{}')")
    conn.execute("INSERT INTO dataset_schema_version (dataset_definition_id, "
                 " version_number, schema_hash) VALUES (1,1,'h')")
    conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        " schema_version_id, data_json, source_snapshot_id, source_locator, "
        " content_hash) VALUES (1,?,1,'{}',1,'div.info-box','c')",
        (_digest(_canonical([contractor_id])),))
    conn.commit()


def _a_second_contractor(conn, contractor_id: str) -> None:
    """Another row in the same profile dataset, so a second page can be written."""
    conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        " schema_version_id, data_json, source_snapshot_id, source_locator, "
        " content_hash) VALUES (1,?,1,'{}',1,'div.info-box',?)",
        (_digest(_canonical([contractor_id])), f"c{contractor_id}"))
    conn.commit()


def _a_licences_page(cell: str, readiness: str = "") -> str:
    """A page carrying nothing but the licences card, with one row.

    Built rather than fetched because the property under test is what happens when a
    SECOND page arrives, and the committed fixtures are one contractor.
    """
    return ('<div class="section-card">'
            '<h4 class="card-title">التراخيص ومستوى الجاهزية</h4>'
            "<table><thead><tr><th>الأنشطة المرخصة</th>"
            "<th>مستوى الجاهزية</th></tr></thead><tbody>"
            f"<tr><td>{cell}</td><td>{readiness}</td></tr>"
            "</tbody></table></div>")


@pytest.fixture()
def warehouse(tmp_path: Path):
    conn = _warehouse(tmp_path)
    _a_profile_row(conn)
    try:
        yield conn
    finally:
        conn.close()


def test_both_groups_reach_the_warehouse_and_they_land_in_two_schemes(warehouse,
                                                                     pages):
    """THE MEASUREMENT THAT PREVENTED A MERGE, asserted. Interests publishes 211
    English paths and the licences 19, with zero exact overlap, while their Arabic
    ROOTS overlap and `ensure_path` is idempotent on the Arabic name.

    One scheme would have fused the two trees at the roots and let them diverge below
    — and the fixture is enough to show it, because `الهندسة المدنية` is a root in
    both.
    """
    english, arabic = pages

    written, repeated = write_groups(warehouse, get("muqawil_org"), 1,
                                     english=english, arabic=arabic,
                                     contractor_id="775")

    assert repeated == 0
    assert written == FIXTURE_INTEREST_NODES + FIXTURE_LICENCE_ROWS, (
        f"{written} memberships written; expected the interests plus the licences")

    schemes = dict(warehouse.execute(
        "SELECT scheme_name_ar, scheme_id FROM classification_scheme").fetchall())
    assert set(schemes) == {"الأنشطة", "الأنشطة المرخصة"}, (
        f"the two vocabularies did not stay apart: {sorted(schemes)}")

    by_group = dict(warehouse.execute(
        "SELECT group_key, COUNT(*) FROM generic_record_node "
        " GROUP BY group_key").fetchall())
    assert by_group == {"interests": FIXTURE_INTEREST_NODES,
                        "licensed_activities": FIXTURE_LICENCE_ROWS}, by_group


def test_the_licence_root_is_a_different_node_from_the_interest_root(warehouse,
                                                                    pages):
    """THE FUSION, named. `الهندسة المدنية` is a root in both vocabularies and the
    English names differ by case — `Civil engineering` against `Civil Engineering`.
    In one scheme the second arrival would have matched the first by Arabic name and
    inherited the other vocabulary's English."""
    english, arabic = pages
    write_groups(warehouse, get("muqawil_org"), 1, english=english, arabic=arabic,
                 contractor_id="775")

    rows = warehouse.execute(
        "SELECT s.scheme_name_ar, n.node_name FROM classification_node AS n "
        "  JOIN classification_scheme AS s ON s.scheme_id = n.scheme_id "
        " WHERE n.node_name_ar = 'الهندسة المدنية' AND n.parent_node_id IS NULL "
        " ORDER BY s.scheme_name_ar").fetchall()

    assert len(rows) == 2, (
        f"the shared Arabic root produced {len(rows)} node(s); two vocabularies must "
        "keep two")
    # ONE OF THE TWO IS EMPTY, and that is the fixture rather than a defect: the only
    # `الهندسة المدنية` licence row this contractor holds is the TRUNCATED one, so its
    # whole path is stored under its Arabic identity with no English name. The next
    # test is the repair, and the corpus measurement behind it.
    assert {row["node_name"] for row in rows} == {"Civil engineering", ""}, (
        "the interests root lost its English name, or the licence root gained one it "
        "was never published")


def test_a_later_page_repairs_the_root_the_truncation_left_empty(warehouse, pages):
    """WHAT THE TRUNCATION ACTUALLY COSTS, measured over the whole corpus rather than
    argued: **3 leaf names out of 29 nodes**, and not one interior node.

    Simulated `ensure_path`'s rule across all 22 distinct activity cells: every ROOT
    gets its English name from some other contractor's cleanly-paired row —
    `الهندسة المدنية` becomes `Civil Engineering` — and exactly three nodes are left
    without one. They are the three the site itself publishes wrongly, and no correct
    English name for them exists anywhere on the site to recover.

    So the honest choice costs three leaf names, and it buys the repair below. Copying
    the Arabic into the English column would have cost nothing today and made this
    repair impossible forever, because `ensure_path` tests `if not node_name`.
    """
    english, arabic = pages
    directory = get("muqawil_org")
    write_groups(warehouse, directory, 1, english=english, arabic=arabic,
                 contractor_id="775")
    _a_second_contractor(warehouse, "776")

    # A page whose two halves DO agree, for the same root and a different leaf --
    # which is what 109 of the corpus's rows look like.
    clean = _a_licences_page(
        "الهندسة المدنية - تشييد الطرق والسكك الحديدية "
        "Civil Engineering - Construction of Roads & Railways")
    write_groups(warehouse, directory, 1, english=clean, arabic=clean,
                 contractor_id="776")

    named = dict(warehouse.execute(
        "SELECT n.node_name_ar, n.node_name FROM classification_node AS n "
        "  JOIN classification_scheme AS s ON s.scheme_id = n.scheme_id "
        " WHERE s.scheme_name_ar = 'الأنشطة المرخصة'").fetchall())

    assert named["الهندسة المدنية"] == "Civil Engineering", (
        "the root the truncation left empty was not repaired by a later page, so "
        "`ensure_path`'s fill-in branch is not being reached")
    assert named["الصرف الصحي"] == "", (
        "the truncated LEAF must stay empty -- the site publishes "
        "'Civil Engineering -' for two different activities, so there is nothing "
        "correct to fill it with")


def test_the_unpaired_licence_stores_an_empty_english_name_for_later(warehouse,
                                                                    pages):
    """WHY THE ARABIC IS NOT COPIED INTO THE ENGLISH COLUMN. `ensure_path` repairs a
    node whose English name is empty the first time a usable one arrives — and it
    tests `if not found["node_name"]`, so a column holding Arabic would never look
    empty again and the repair could never happen."""
    english, arabic = pages
    write_groups(warehouse, get("muqawil_org"), 1, english=english, arabic=arabic,
                 contractor_id="775")

    name = warehouse.execute(
        "SELECT n.node_name FROM classification_node AS n "
        "  JOIN classification_scheme AS s ON s.scheme_id = n.scheme_id "
        " WHERE s.scheme_name_ar = 'الأنشطة المرخصة' "
        "   AND n.node_name_ar = 'الصرف الصحي'").fetchone()

    assert name is not None, "the truncated row did not store its Arabic identity"
    assert not name["node_name"], (
        f"the English column holds {name['node_name']!r}; the site published "
        "'Civil Engineering -' for two different activities, so an empty column is "
        "the honest state and the repairable one")


def test_a_second_pass_writes_nothing_and_says_so(warehouse, pages):
    """A re-parse over stored snapshots must be free. `R-40` repaired the idempotency
    that makes this the recovery path instead of a re-crawl."""
    english, arabic = pages
    directory = get("muqawil_org")
    write_groups(warehouse, directory, 1, english=english, arabic=arabic,
                 contractor_id="775")

    written, repeated = write_groups(warehouse, directory, 1, english=english,
                                     arabic=arabic, contractor_id="775")

    assert (written, repeated) == (0, FIXTURE_INTEREST_NODES
                                   + FIXTURE_LICENCE_ROWS)


# ---- the declarations that record what was NOT built -------------------------

def test_the_two_empty_groups_are_declared_rather_than_forgotten():
    """"WE MEASURED IT AND IT IS EMPTY" IS A DIFFERENT FACT FROM A SHORTER LIST, and
    this is the shape that keeps them apart — the same argument
    `GROUPS_NOT_LOCATED` already makes for the groups that are not on the page."""
    measured = dict(GROUPS_MEASURED_EMPTY)

    assert set(measured) == {"sub_contractors", "main_contractors"}
    for key, why in measured.items():
        assert "2,419" in why, f"{key} records no count: {why!r}"
    declared = {group.key for group in MULTI_VALUED_GROUPS}
    assert set(measured) <= declared, (
        "a group measured empty must still be declared, or the day the site fills it "
        "in nothing knows where to look")


def test_only_the_groups_with_a_vocabulary_are_wired():
    """A group is wired by naming its scheme. Three of the five name none, and that
    is the record of a decision rather than an omission."""
    wired = {group.key for group in MULTI_VALUED_GROUPS if group.scheme_name_ar}

    assert wired == {"interests", "licensed_activities"}, wired
