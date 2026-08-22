"""A membership carries what the site said about it, and the contractor does not.

WHY THIS TABLE AND NOT THE CONTRACTORS TABLE. `Q-17` asked him whether the licences'
readiness level should be a column or should go unstored. He refused the question:

    «لا داعى لوضعها فى عمود خاص فى الجدول ولكن عند الضغط على صف معين وهو يحملها تظهر
     فى الكارد الخاص بالمقاول · لان المقاولون سيكون هناك عدة مصادر له فى المستقبل»

A field is not a column — `R-45`. And the shape follows from the page rather than from
the ruling alone: `مستوى الجاهزية` is published in the licences table BESIDE each
activity, one grade per activity. A contractor with six licences can be graded on one
and ungraded on five, which is exactly what the committed fixture does. On the
contractors table that fact has no home that is not a lie about which activity it
describes.

THE MEASUREMENTS THIS FILE IS WRITTEN AGAINST, over 1,685 real licence rows on 2,419
profile pairs:

    rows publishing a readiness      10 of 1,500      so NULL is the common case
    distinct values                  5                ذهبي|Gold, فضي|Silver,
                                                      ماسي|Dimond (the site's
                                                      spelling), أساسي|Basic
    the separator                     " | "           arabic, pipe, latin
    interests publishing one          0                there is no column beside them

AND NO CHECK CONSTRAINT ON THE VALUE, which one of these tests pins. Five levels are a
closed set today, and a CHECK would turn the site adding a sixth into an error we
invented — `R-45`'s other half: «ما يقوله الموقع هو مصدر الحقيقة الوحيد لا نعدل عليه».
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import taxonomy
from scrapex.contractors import write_groups
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.directories import get
from scrapex.extract.muqawil import read_licensed_activities
from scrapex.extract.service import _canonical, _digest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"

#: The fixture's own numbers, read off the pages rather than assumed.
FIXTURE_LICENCE_ROWS = 6
FIXTURE_GRADED_ROWS = 1
FIXTURE_INTEREST_NODES = 25
READINESS_LABEL = "مستوى الجاهزية"


def _page(locale: str) -> str:
    return (FIXTURES / f"profile-{locale}.html").read_text(encoding="utf-8")


@pytest.fixture()
def pages() -> tuple[str, str]:
    return _page("en"), _page("ar")


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    _a_profile_row(connection, "775")
    try:
        yield connection
    finally:
        connection.close()


def _a_profile_row(conn, contractor_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO site_profile (site_key, display_name, base_url) "
                 "VALUES ('muqawil_org','Contractors','https://muqawil.org')")
    conn.execute(
        "INSERT OR IGNORE INTO generic_page_snapshot "
        "(page_snapshot_id, source_url, html_content, content_hash) "
        "VALUES (1,'https://muqawil.org/en/contractors/775/143','<html></html>','h')")
    conn.execute(
        "INSERT OR IGNORE INTO dataset_definition (dataset_definition_id, "
        " site_profile_id, dataset_key, original_name, dataset_kind, "
        " discovery_method, locator_json) "
        "VALUES (1,1,'contractor_profiles','contractor_profiles','table',"
        " 'html_table','{}')")
    conn.execute("INSERT OR IGNORE INTO dataset_schema_version "
                 "(schema_version_id, dataset_definition_id, version_number, "
                 " schema_hash) VALUES (1,1,1,'h')")
    conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        " schema_version_id, data_json, source_snapshot_id, source_locator, "
        " content_hash) VALUES (1,?,1,'{}',1,'div.info-box',?)",
        (_digest(_canonical([contractor_id])), f"c{contractor_id}"))
    conn.commit()


def _record_id(conn, contractor_id: str) -> int:
    return int(conn.execute(
        "SELECT generic_record_id FROM generic_record WHERE record_key = ?",
        (_digest(_canonical([contractor_id])),)).fetchone()[0])


# ---- the schema ---------------------------------------------------------------

def test_the_three_columns_exist_and_are_nullable(conn):
    """ADDITIVE, which is what lets 15,559 stored memberships keep their rows. Every
    one of them reads NULL and the next `--approve` fills in the ten per fifteen
    hundred that have something to say."""
    columns = {row[1]: row for row in
               conn.execute("PRAGMA table_info(generic_record_node)")}

    for name in ("attribute_label", "attribute_value", "attribute_value_ar"):
        assert name in columns, f"{name} is missing; migration 0010 did not apply"
        assert columns[name][3] == 0, (
            f"{name} is NOT NULL, but 1,490 of 1,500 measured licence rows publish "
            "nothing here and every interest publishes nothing by construction")


def test_the_value_has_no_check_constraint(conn):
    """`R-45` PINNED IN THE SCHEMA. Five readiness levels are a closed set today; a
    CHECK would make the site adding a sixth an error we invented, and the site is the
    record."""
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'generic_record_node'"
    ).fetchone()[0]
    tail = sql[sql.index("attribute_label"):] if "attribute_label" in sql else ""

    assert "CHECK" not in tail.upper(), (
        "a CHECK now constrains the attribute columns, so a readiness level the site "
        f"invents becomes our error rather than its news: {tail!r}")


# ---- the write ---------------------------------------------------------------

def test_the_attribute_is_stored_and_read_back(conn):
    node = taxonomy.ensure_path(
        conn, taxonomy.ensure_scheme(conn, 1, name="Licensed Activities",
                                     name_ar="الأنشطة المرخصة"),
        path=("Construction of Buildings",), path_ar=("تشييد المباني",))

    taxonomy.link(conn, generic_record_id=_record_id(conn, "775"), node_id=node,
                  group_key="licensed_activities", source_snapshot_id=1,
                  attribute=(READINESS_LABEL, "Basic", "أساسي"))

    held = taxonomy.memberships(conn, _record_id(conn, "775"))
    assert len(held) == 1
    assert held[0].attribute_label == READINESS_LABEL
    assert held[0].attribute_value == "Basic"
    assert held[0].attribute_value_ar == "أساسي"


def test_a_membership_with_nothing_said_about_it_reads_empty_not_none(conn):
    """The card renders these, and `None` in a template prints "None". Empty is the
    only honest rendering of "the site graded nothing"."""
    node = taxonomy.ensure_path(
        conn, taxonomy.ensure_scheme(conn, 1, name="Interests", name_ar="الأنشطة"),
        path=("Civil engineering",), path_ar=("الهندسة المدنية",))
    taxonomy.link(conn, generic_record_id=_record_id(conn, "775"), node_id=node,
                  group_key="interests", source_snapshot_id=1)

    held = taxonomy.memberships(conn, _record_id(conn, "775"))

    assert (held[0].attribute_label, held[0].attribute_value,
            held[0].attribute_value_ar) == ("", "", "")


def test_a_regrade_overwrites_rather_than_keeping_the_old_grade(conn):
    """A contractor promoted from `أساسي` to `ذهبي` must not keep both. The membership
    is unchanged — same contractor, same activity — so the upsert has to move the
    attribute the way it already moves `source_snapshot_id`."""
    scheme = taxonomy.ensure_scheme(conn, 1, name="Licensed Activities",
                                    name_ar="الأنشطة المرخصة")
    node = taxonomy.ensure_path(conn, scheme, path=("Demolition",),
                                path_ar=("الهدم",))
    record = _record_id(conn, "775")
    taxonomy.link(conn, generic_record_id=record, node_id=node,
                  group_key="licensed_activities", source_snapshot_id=1,
                  attribute=(READINESS_LABEL, "Basic", "أساسي"))

    fresh = taxonomy.link(conn, generic_record_id=record, node_id=node,
                          group_key="licensed_activities", source_snapshot_id=1,
                          attribute=(READINESS_LABEL, "Gold", "ذهبي"))

    assert fresh is False, "a regrade is a confirmation of the membership, not a new one"
    held = taxonomy.memberships(conn, record)
    assert held[0].attribute_value == "Gold"
    assert held[0].attribute_value_ar == "ذهبي"


def test_the_attribute_belongs_to_the_membership_and_not_to_the_node(conn):
    """THE PROPERTY THE WHOLE MIGRATION IS FOR. Two contractors licensed for the same
    activity at different grades must each keep their own — which is impossible if the
    grade hangs off `classification_node`, the shape a reader might reach for because
    the vocabulary is shared."""
    _a_profile_row(conn, "776")
    scheme = taxonomy.ensure_scheme(conn, 1, name="Licensed Activities",
                                    name_ar="الأنشطة المرخصة")
    node = taxonomy.ensure_path(conn, scheme, path=("Site Preparation",),
                                path_ar=("تحضير الموقع",))
    for contractor, grade, grade_ar in (("775", "Basic", "أساسي"),
                                        ("776", "Gold", "ذهبي")):
        taxonomy.link(conn, generic_record_id=_record_id(conn, contractor),
                      node_id=node, group_key="licensed_activities",
                      source_snapshot_id=1,
                      attribute=(READINESS_LABEL, grade, grade_ar))

    first = taxonomy.memberships(conn, _record_id(conn, "775"))[0]
    second = taxonomy.memberships(conn, _record_id(conn, "776"))[0]

    assert first.node_id == second.node_id, "the fixture no longer shares one node"
    assert (first.attribute_value, second.attribute_value) == ("Basic", "Gold")


# ---- the reader, and the label that is the site's ----------------------------

def test_the_label_comes_off_the_page_and_not_off_a_constant(pages):
    """`R-45`: the site's words are the record. A constant would keep asserting
    `مستوى الجاهزية` after the site renamed that column, and the warehouse would
    carry a name the site had stopped using."""
    english, _ = pages
    graded = [one for one in read_licensed_activities(english) if one.readiness_ar]

    assert len(graded) == FIXTURE_GRADED_ROWS
    assert graded[0].readiness_label == READINESS_LABEL

    # THE HEADER CELL ONLY, and the first attempt at this test taught why. The card's
    # own TITLE is `التراخيص ومستوى الجاهزية` -- it CONTAINS the column's name as a
    # substring -- so a whole-page replace renamed the title too, `_card` stopped
    # finding the card by title, and the reader returned nothing at all. The test
    # failed for the right reason and told the wrong story.
    renamed = english.replace(f">{READINESS_LABEL}<", ">درجة التأهيل<")
    assert READINESS_LABEL in renamed, (
        "the card title lost its own name, so this rename hit more than the header")
    graded_again = [one for one in read_licensed_activities(renamed)
                    if one.readiness_ar]
    assert graded_again, "the rename made the card unreadable instead of renaming it"
    assert graded_again[0].readiness_label == "درجة التأهيل", (
        "the label is hardcoded, so a renamed column would be recorded under its old "
        "name for as long as nobody noticed")


def test_an_ungraded_licence_carries_no_label_either(pages):
    """A label with no value is a column heading, not a fact about this activity."""
    english, _ = pages
    ungraded = [one for one in read_licensed_activities(english)
                if not one.readiness_ar and not one.readiness_en]

    assert len(ungraded) == FIXTURE_LICENCE_ROWS - FIXTURE_GRADED_ROWS
    assert all(one.readiness_label == "" for one in ungraded)


# ---- and end to end, on the committed pages ---------------------------------

def test_the_fixture_grades_exactly_one_of_its_six_licences(conn, pages):
    """THE SHAPE THAT MAKES THIS A MEMBERSHIP ATTRIBUTE, on real published data: one
    contractor, six licences, one grade. A column on the contractors table would have
    to choose which of the six it described."""
    english, arabic = pages

    write_groups(conn, get("muqawil_org"), 1, english=english, arabic=arabic,
                 contractor_id="775")

    held = taxonomy.memberships(conn, _record_id(conn, "775"))
    licences = [one for one in held if one.group_key == "licensed_activities"]
    interests = [one for one in held if one.group_key == "interests"]

    assert len(licences) == FIXTURE_LICENCE_ROWS
    assert len(interests) == FIXTURE_INTEREST_NODES

    graded = [one for one in licences if one.attribute_value_ar]
    assert len(graded) == FIXTURE_GRADED_ROWS, (
        f"{len(graded)} of {len(licences)} licences carry a grade; the committed "
        "contractor publishes exactly one")
    assert graded[0].attribute_value_ar == "أساسي"
    assert graded[0].attribute_value == "Basic"
    assert graded[0].attribute_label == READINESS_LABEL


def test_no_interest_carries_an_attribute(conn, pages):
    """There is no column beside the interests list, so `None` there is a READING and
    not a default that happened to be right."""
    english, arabic = pages
    write_groups(conn, get("muqawil_org"), 1, english=english, arabic=arabic,
                 contractor_id="775")

    interests = [one for one in taxonomy.memberships(conn, _record_id(conn, "775"))
                 if one.group_key == "interests"]

    assert interests, "the fixture stored no interests at all"
    assert all(not one.attribute_label and not one.attribute_value
               and not one.attribute_value_ar for one in interests)


def test_the_stored_attribute_survives_a_second_approval(conn, pages):
    """A re-parse over the snapshots on disk is the recovery path `R-40` repaired, and
    it must not blank an attribute it re-reads identically."""
    english, arabic = pages
    directory = get("muqawil_org")
    write_groups(conn, directory, 1, english=english, arabic=arabic,
                 contractor_id="775")
    write_groups(conn, directory, 1, english=english, arabic=arabic,
                 contractor_id="775")

    graded = [one for one in taxonomy.memberships(conn, _record_id(conn, "775"))
              if one.attribute_value_ar]

    assert len(graded) == FIXTURE_GRADED_ROWS
    assert graded[0].attribute_value_ar == "أساسي"
