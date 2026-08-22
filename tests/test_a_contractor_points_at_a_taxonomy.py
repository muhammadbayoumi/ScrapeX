"""`R-38`: the five multi-valued groups are a taxonomy plus a link table — shape D.

HE OVERRULED THE STUDY'S RECOMMENDATION AND WAS RIGHT. The study recommended shape F, a
child dataset per group inside `generic_record`, because it reuses machinery the warehouse
already contains. Measured the same day: `classification_node`,
`classification_scheme`, `dataset_relationship` and `relationship_field_pair` hold **zero
rows between them**. Existing machinery that has never carried a row is not an asset —
this one session found `is_enabled` with no callers, `record_absences` with no callers, and
a slice scope that was "built, tested, never used" and turned out to be *wrong*.

And F paid a whole `generic_record` row — `data_json` averaging 1,049 bytes, a
64-character key, a 64-character hash, two timestamps, a status and four foreign keys —
for a membership fact that is two integers.

WHAT THIS FILE GUARDS, in the order the reasons matter:

  * the STRING IS STORED ONCE. That is the whole of shape D; if a path's names are
    repeated per membership it has become shape A, which the study measured at 4.7x.
  * PROVENANCE IS ENFORCED, not remembered. `source_snapshot_id NOT NULL` is F's one
    real advantage and `R-38` says explicitly it must be carried over.
  * IDEMPOTENCY IS THE PRIMARY KEY, so a re-parse cannot duplicate — which is why D
    needs nothing like the repair `R-40` had to make to `approve_candidate`.
  * `group_key` IS IN THE KEY, because one node can be held as an interest AND as a
    licensed activity, and merging those two facts would be silent.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import taxonomy
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract.muqawil import read_interests
from scrapex.taxonomy import CannotPairLocales

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    _a_contractor(connection)
    try:
        yield connection
    finally:
        connection.close()


def _a_contractor(conn) -> None:
    """One stored contractor with one snapshot behind it, minimally shaped."""
    for sql in (
        "INSERT INTO site_profile (site_key, display_name, base_url) "
        "VALUES ('muqawil_org','Contractors','https://muqawil.org')",
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash) "
        "VALUES ('https://muqawil.org/en/contractors/1/143','<html></html>','h')",
        "INSERT INTO dataset_definition (site_profile_id, dataset_key, original_name, "
        " dataset_kind, discovery_method, locator_json) "
        "VALUES (1,'contractors','contractors','table','html_table','{}')",
        "INSERT INTO dataset_schema_version (dataset_definition_id, version_number, "
        " schema_hash) VALUES (1,1,'h')",
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        " schema_version_id, data_json, source_snapshot_id, source_locator, "
        " content_hash) VALUES (1,'contractor-1',1,'{}',1,'x','c')",
    ):
        conn.execute(sql)
    conn.commit()


def _scheme(conn) -> int:
    return taxonomy.ensure_scheme(conn, 1, name="Interests", name_ar="الأنشطة")


def _interests(locale: str):
    return read_interests(
        (FIXTURES / f"profile-{locale}.html").read_text(encoding="utf-8"))


def _store_the_interests(conn) -> int:
    """The real reading of the committed profile, both locales, stored. Returns new count."""
    scheme = _scheme(conn)
    new = 0
    for path, path_ar in zip(_interests("en"), _interests("ar"), strict=True):
        node = taxonomy.ensure_path(conn, scheme, path=path, path_ar=path_ar)
        new += taxonomy.link(conn, generic_record_id=1, node_id=node,
                             group_key="interests", source_snapshot_id=1)
    conn.commit()
    return new


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---- the shape itself ---------------------------------------------------------

def test_the_real_profile_stores_as_a_tree_and_not_as_strings(conn):
    """THE WHOLE OF SHAPE D IN ONE ASSERTION. 25 memberships over 25 nodes, and the
    interior nodes are shared rather than repeated — `تشييد المباني` is written once
    however many contractors sit under it."""
    new = _store_the_interests(conn)

    assert new == 25
    assert _count(conn, "generic_record_node") == 25
    assert _count(conn, "classification_node") == 25
    depths = dict(conn.execute(
        "SELECT level, COUNT(*) FROM classification_node GROUP BY level").fetchall())
    assert depths == {1: 3, 2: 5, 3: 17}


def test_a_name_is_stored_once_however_many_contractors_hold_it(conn):
    """SHAPE D VERSUS SHAPE A, which is the 4.7x. A second contractor holding the same
    activities adds memberships and NOT ONE NODE."""
    _store_the_interests(conn)
    nodes = _count(conn, "classification_node")
    conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        " schema_version_id, data_json, source_snapshot_id, source_locator, "
        " content_hash) VALUES (1,'contractor-2',1,'{}',1,'y','d')")
    conn.commit()

    scheme = _scheme(conn)
    for path, path_ar in zip(_interests("en"), _interests("ar"), strict=True):
        node = taxonomy.ensure_path(conn, scheme, path=path, path_ar=path_ar)
        taxonomy.link(conn, generic_record_id=2, node_id=node,
                      group_key="interests", source_snapshot_id=1)
    conn.commit()

    assert _count(conn, "classification_node") == nodes, "not one new node"
    assert _count(conn, "generic_record_node") == 50


def test_the_path_is_rebuilt_with_both_locales(conn):
    """The reason `ensure_path` pairs the two readings: a reader wants either language
    from one row, and the string exists once per language per node."""
    _store_the_interests(conn)

    found = taxonomy.memberships(conn, 1)

    assert len(found) == 25
    deepest = [one for one in found if len(one.path) == 3]
    assert deepest
    one = deepest[0]
    assert all(one.path) and all(one.path_ar)
    assert one.path != one.path_ar


def test_reading_one_group_does_not_return_another(conn):
    """`group_key` FILTERS, and it has to: the licensed-activities values are drawn from
    the same activity vocabulary as the interests tree, so without this a contractor's
    interests and its licences would come back as one list."""
    _store_the_interests(conn)
    scheme = _scheme(conn)
    node = taxonomy.ensure_path(conn, scheme, path=("Civil engineering",),
                                path_ar=("الهندسة المدنية",))
    taxonomy.link(conn, generic_record_id=1, node_id=node,
                  group_key="licensed_activities", source_snapshot_id=1)
    conn.commit()

    interests = taxonomy.memberships(conn, 1, group_key="interests")
    licences = taxonomy.memberships(conn, 1, group_key="licensed_activities")

    assert len(interests) == 25
    assert len(licences) == 1
    assert len(taxonomy.memberships(conn, 1)) == 26


def test_one_node_can_be_held_in_two_groups_at_once(conn):
    """WHY `group_key` IS IN THE PRIMARY KEY. The same activity is a legitimate interest
    AND a legitimate licence, and a key of `(record, node)` alone would silently merge
    two different facts into one row."""
    scheme = _scheme(conn)
    node = taxonomy.ensure_path(conn, scheme, path=("Civil engineering",),
                                path_ar=("الهندسة المدنية",))

    assert taxonomy.link(conn, generic_record_id=1, node_id=node,
                         group_key="interests", source_snapshot_id=1) is True
    assert taxonomy.link(conn, generic_record_id=1, node_id=node,
                         group_key="licensed_activities", source_snapshot_id=1) is True
    conn.commit()

    assert _count(conn, "generic_record_node") == 2


# ---- what F's advantage was, carried over ------------------------------------

def test_a_membership_without_its_evidence_is_refused_by_the_schema(conn):
    """F'S ONE REAL ADVANTAGE, AND `R-38` SAYS IT MUST BE CARRIED OVER.
    `generic_record.source_snapshot_id NOT NULL` is what makes provenance enforced rather
    than remembered; the link table carries the same column under the same constraint."""
    scheme = _scheme(conn)
    node = taxonomy.ensure_path(conn, scheme, path=("x",), path_ar=("س",))

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO generic_record_node "
            "(generic_record_id, node_id, group_key) VALUES (?,?,?)",
            (1, node, "interests"))
    conn.rollback()


def test_the_evidence_must_be_a_page_that_exists(conn):
    """NOT NULL is half of it; the foreign key is the other half. A snapshot id nobody
    stored is a claim wearing the clothes of a reading."""
    scheme = _scheme(conn)
    node = taxonomy.ensure_path(conn, scheme, path=("x",), path_ar=("س",))

    with pytest.raises(sqlite3.IntegrityError):
        taxonomy.link(conn, generic_record_id=1, node_id=node,
                      group_key="interests", source_snapshot_id=9999)
    conn.rollback()


def test_deleting_a_contractor_takes_its_memberships(conn):
    """`OP-25` was settled by WIPING `generic_record` and re-approving from disk — 1,172
    rows became 13,892 with zero network — so deletion is a route this warehouse actually
    takes, and links that survived it would point at nothing."""
    _store_the_interests(conn)

    conn.execute("DELETE FROM generic_record WHERE record_key = 'contractor-1'")
    conn.commit()

    assert _count(conn, "generic_record_node") == 0
    assert _count(conn, "classification_node") == 25, (
        "the VOCABULARY survives a wipe — it is the site's, not the contractor's")


# ---- idempotency, by construction --------------------------------------------

def test_a_second_identical_pass_writes_nothing_new(conn):
    """`R-38`'s fourth reason for D. Shape F would have gone through
    `approve_candidate`, whose idempotency key `R-40` had to repair; here the primary key
    makes a duplicate impossible even for a caller that forgot to check."""
    first = _store_the_interests(conn)
    second = _store_the_interests(conn)

    assert (first, second) == (25, 0)
    assert _count(conn, "generic_record_node") == 25
    assert _count(conn, "classification_node") == 25


def test_a_repeat_is_counted_rather_than_timed(conn):
    """THE CLOCK CANNOT ANSWER THIS, and the first version of `link` tried. Both
    timestamps come from `strftime(...,'now')` at SECOND resolution, so a write and its
    confirmation in the same second are indistinguishable — measured, a second identical
    pass reported all 25 memberships as new."""
    _store_the_interests(conn)
    _store_the_interests(conn)

    counts = dict(conn.execute(
        "SELECT seen_count, COUNT(*) FROM generic_record_node GROUP BY 1").fetchall())

    assert counts == {2: 25}


# ---- the pairing, and what it refuses ----------------------------------------

def test_two_locales_that_do_not_line_up_are_refused(conn):
    """WRITING ANYWAY WOULD ATTACH AN ENGLISH NAME TO A DIFFERENT ARABIC NODE, and
    nothing would raise. `DSN-05` is the same failure one level up."""
    scheme = _scheme(conn)

    with pytest.raises(CannotPairLocales):
        taxonomy.ensure_path(conn, scheme, path=("a", "b"), path_ar=("س",))


def test_the_arabic_name_is_the_identity_and_the_english_fills_in_later(conn):
    """THE SCHEMA CHOSE THIS, not this module: `node_name_ar` is NOT NULL and carries
    `ux_classification_node_name`, while `node_name` is nullable. So a node first seen on
    an Arabic-only reading is the SAME node when the English arrives — matching on the
    English would make it two nodes depending on which locale came first."""
    scheme = _scheme(conn)

    first = taxonomy.ensure_path(conn, scheme, path=("",), path_ar=("الهندسة المدنية",))
    second = taxonomy.ensure_path(conn, scheme, path=("Civil engineering",),
                                  path_ar=("الهندسة المدنية",))
    conn.commit()

    assert first == second
    assert _count(conn, "classification_node") == 1
    assert conn.execute(
        "SELECT node_name FROM classification_node WHERE node_id = ?",
        (first,)).fetchone()[0] == "Civil engineering"


def test_the_same_name_under_two_parents_is_two_nodes(conn):
    """THE STUDY'S FINDING, GUARDED. `الصرف الصحي` sits under more than one parent, and
    an identity built from the leaf name would merge two different activities. The
    committed profile proves it too: `Construction of buildings` is a level-1 node and a
    level-2 node beneath itself."""
    scheme = _scheme(conn)

    under_a = taxonomy.ensure_path(conn, scheme, path=("A", "shared"),
                                   path_ar=("أ", "مشترك"))
    under_b = taxonomy.ensure_path(conn, scheme, path=("B", "shared"),
                                   path_ar=("ب", "مشترك"))
    conn.commit()

    assert under_a != under_b
    assert _count(conn, "classification_node") == 4
