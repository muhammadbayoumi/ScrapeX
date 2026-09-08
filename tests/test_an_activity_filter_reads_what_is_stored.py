"""407,384 stored memberships become a filter, and the counting is the hard part.

WHAT WAS WRONG, MEASURED ON HIS WAREHOUSE 2026-09-08. `taxonomy.memberships` is
written, tested and has **no caller in `scrapex/` outside its own tests**, so a
contractor's activities were invisible on every screen he has:

    Interests / الأنشطة              214 nodes · 8 roots · 3 levels · 398,933 memberships
    Licensed Activities / المرخصة     29 nodes · 4 roots · 3 levels ·   8,451 memberships
                                     over 17,811 records · avg 22.9 each · max 213

AND THE TWO GROUPS STORE THE TREE IN OPPOSITE WAYS, which is what makes the counting
a design question rather than a `GROUP BY`:

    interests            367,015 of 367,015 child memberships carry their ancestor
    licensed_activities        0 of   8,451

So a count of the stored rows per node is right for the first and reports **zero** for
every parent in the second -- an empty category rather than a visibly wrong query.
Both halves of this file are the one definition that is correct in both: **held at, or
anywhere under.** Issue 800 carries the study of the conventions themselves.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex import taxonomy
from scrapex.extract import service

DATASET = "contractor_profiles"


@pytest.fixture()
def warehouse(tmp_path):
    conn = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(conn)
    try:
        yield conn
    finally:
        conn.close()


def _dataset(conn: sqlite3.Connection) -> tuple[int, int]:
    """The full foreign-key chain a `generic_record` needs, and no shortcut."""
    source = conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url) "
        "VALUES ('muqawil_org', 'Saudi Contractors Authority', "
        "        'https://muqawil.org/') RETURNING source_id").fetchone()[0]
    definition = conn.execute(
        "INSERT INTO dataset_definition "
        "  (source_id, dataset_key, original_name, dataset_kind, discovery_method) "
        "VALUES (?, ?, 'Contractor profiles', 'table', 'repeating_dom') "
        "RETURNING dataset_definition_id", (source, DATASET)).fetchone()[0]
    version = conn.execute(
        "INSERT INTO dataset_schema_version "
        "  (dataset_definition_id, version_number, schema_hash) "
        "VALUES (?, 1, 'hash') RETURNING schema_version_id",
        (definition,)).fetchone()[0]
    # THE FIELD REACHES THE PAYLOAD THROUGH `schema_version_field`, which is the
    # three-table chain `dataset_schema_fields` reads: a version, the fields bound to
    # it, and their definitions. `dataset_field` is a DIFFERENT table -- the panel's
    # column arrangement, keyed by `source_key` -- and writing there would have left
    # the payload with no identity column and every row without its contractor id.
    field = conn.execute(
        "INSERT INTO field_definition (dataset_definition_id, field_key, "
        "                              original_name, data_type, identity_role) "
        "VALUES (?, 'contractor_id', 'Contractor id', 'text', 'key_part') "
        "RETURNING field_definition_id", (definition,)).fetchone()[0]
    conn.execute(
        "INSERT INTO schema_version_field (schema_version_id, field_definition_id, "
        "                                  field_order) VALUES (?, ?, 1)",
        (version, field))
    conn.commit()
    return int(definition), int(version)


def _record(conn, definition: int, version: int, contractor_id: str) -> int:
    """One profile row, stored through the production snapshot writer."""
    from scrapex.extract.models import SnapshotCreate
    snapshot = service.save_snapshot(conn, SnapshotCreate(
        source_url=f"https://muqawil.org/en/contractors/{contractor_id}/143",
        html_content="<html><body>fixture</body></html>"))
    row = conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        "  schema_version_id, data_json, source_snapshot_id, source_locator, "
        "  content_hash, status) "
        "VALUES (?, ?, ?, ?, ?, 'div.info-box::row(1)', ?, 'active') "
        "RETURNING generic_record_id",
        (definition, f"key-{contractor_id}", version,
         json.dumps({"contractor_id": contractor_id}),
         int(snapshot["page_snapshot_id"]), f"hash-{contractor_id}")).fetchone()[0]
    conn.commit()
    return int(row)


def _tree(conn) -> dict[str, int]:
    """`root -> branch -> leaf`, plus a second root and the undeclared node."""
    scheme = taxonomy.ensure_scheme(conn, 1, name="Interests", name_ar="الأنشطة")
    made: dict[str, int] = {}
    for label, path_en, path_ar in (
        ("root", ("Construction",), ("تشييد",)),
        ("branch", ("Construction", "Electrical"), ("تشييد", "كهرباء")),
        ("leaf", ("Construction", "Electrical", "Wiring"), ("تشييد", "كهرباء", "أسلاك")),
        ("other", ("Civil",), ("مدني",)),
        ("undeclared", ("No Data",), ("لا يوجد بيانات",)),
    ):
        made[label] = taxonomy.ensure_path(
            conn, scheme, path=path_en, path_ar=path_ar)
    conn.commit()
    return made


def _hold(conn, record_id: int, node_id: int,
          group_key: str = "interests") -> None:
    """Through the production writer, which is where the link table's rules live.

    THE SNAPSHOT IS READ OFF THE RECORD rather than threaded through every call: the
    link table requires the page the membership was read from, and it is by
    construction the page the record itself came from.
    """
    snapshot = conn.execute(
        "SELECT source_snapshot_id FROM generic_record WHERE generic_record_id = ?",
        (record_id,)).fetchone()[0]
    taxonomy.link(conn, generic_record_id=record_id, node_id=node_id,
                  group_key=group_key, source_snapshot_id=int(snapshot))
    conn.commit()


# ---- the counting -----------------------------------------------------------

def test_a_node_is_held_by_everyone_under_it(warehouse):
    """THE ONE DEFINITION THAT SURVIVES BOTH CONVENTIONS. This contractor holds the
    LEAF and nothing above it -- which is exactly how `licensed_activities` stores
    every one of its 8,451 memberships -- so a count that matched node ids would
    report the root as held by nobody."""
    definition, version = _dataset(warehouse)
    nodes = _tree(warehouse)
    only_leaf = _record(warehouse, definition, version, "1001")
    _hold(warehouse, only_leaf, nodes["leaf"])

    counts = taxonomy.held_counts(warehouse, "interests")

    assert counts.get(nodes["leaf"]) == 1
    assert counts.get(nodes["branch"]) == 1, (
        "the branch above a held leaf reports nobody, which is how a real category "
        "looks empty")
    assert counts.get(nodes["root"]) == 1
    assert counts.get(nodes["other"]) is None


def test_a_contractor_holding_a_whole_path_is_counted_once(warehouse):
    """`COUNT(DISTINCT)` IS LOAD-BEARING. `interests` stores every ancestor -- 367,015
    of 367,015 -- so one contractor holds the root, the branch and the leaf. A plain
    `COUNT(*)` up the subtree would report the root as held three times by one
    contractor, and his roots average 22.9 memberships each."""
    definition, version = _dataset(warehouse)
    nodes = _tree(warehouse)
    whole_path = _record(warehouse, definition, version, "1002")
    for label in ("root", "branch", "leaf"):
        _hold(warehouse, whole_path, nodes[label])

    counts = taxonomy.held_counts(warehouse, "interests")

    assert counts.get(nodes["root"]) == 1, (
        f"one contractor counted {counts.get(nodes['root'])} times up its own path")


def test_the_undeclared_node_is_separated_and_still_counted(warehouse):
    """HIS RULING: a state said in a line, not a category in the tree -- and NOT
    deleted, because 9,001 contractors having declared nothing is a fact about them."""
    definition, version = _dataset(warehouse)
    nodes = _tree(warehouse)
    silent = _record(warehouse, definition, version, "1003")
    _hold(warehouse, silent, nodes["undeclared"])

    tree = taxonomy.group_tree(warehouse, "interests")

    assert tree["undeclared"]["held"] == 1
    assert nodes["undeclared"] not in [one["node_id"] for one in tree["nodes"]], (
        "the undeclared node reached the tree the filter draws")
    assert tree["scheme"]["name_ar"] == "الأنشطة"


def test_a_group_with_nothing_stored_answers_emptily(warehouse):
    """A directory declares five groups and two are wired. Asking for one of the other
    three must answer rather than raise, or the route 500s on a shape the source itself
    describes."""
    _dataset(warehouse)

    tree = taxonomy.group_tree(warehouse, "sub_contractors")

    assert tree == {"group_key": "sub_contractors", "scheme": None, "nodes": [],
                    "undeclared": None}


# ---- the filter -------------------------------------------------------------

def _payload(conn, **kwargs):
    return service.dataset_table_payload(conn, DATASET, **kwargs)


def test_choosing_a_root_reaches_a_contractor_holding_only_a_leaf(warehouse):
    """THE FILTER DESCENDS, for the reason the counting does."""
    definition, version = _dataset(warehouse)
    nodes = _tree(warehouse)
    deep = _record(warehouse, definition, version, "2001")
    _hold(warehouse, deep, nodes["leaf"])
    elsewhere = _record(warehouse, definition, version, "2002")
    _hold(warehouse, elsewhere, nodes["other"])

    whole = _payload(warehouse)
    narrowed = _payload(warehouse, nodes=[nodes["root"]])

    assert whole["total"] == 2 and whole["population"] == 2
    assert narrowed["total"] == 1, (
        "choosing a root missed the contractor holding only its leaf")
    assert [row["contractor_id"] for row in narrowed["rows"]] == ["2001"]
    assert narrowed["population"] == 2, (
        "the unfiltered population is gone, so 1 of 2 reads as a dataset that lost a row")


def test_any_widens_and_all_narrows(warehouse):
    """HIS RULING WAS A TOGGLE, so both have to be right. `all` cannot be built from a
    count of distinct nodes: under a stored-path convention one deep membership already
    satisfies several nodes, and `all` would quietly mean `any`."""
    definition, version = _dataset(warehouse)
    nodes = _tree(warehouse)
    both = _record(warehouse, definition, version, "3001")
    _hold(warehouse, both, nodes["leaf"])
    _hold(warehouse, both, nodes["other"])
    one_only = _record(warehouse, definition, version, "3002")
    _hold(warehouse, one_only, nodes["leaf"])

    picked = [nodes["root"], nodes["other"]]
    any_of = _payload(warehouse, nodes=picked, nodes_mode="any")
    all_of = _payload(warehouse, nodes=picked, nodes_mode="all")

    assert any_of["total"] == 2, any_of["total"]
    assert all_of["total"] == 1, (
        f"'all of them' returned {all_of['total']} where one contractor holds both")
    assert [row["contractor_id"] for row in all_of["rows"]] == ["3001"]
    assert all_of["filtered_by"] == {"nodes": sorted(picked), "mode": "all"}


def test_an_unknown_mode_widens_rather_than_narrowing(warehouse):
    """A STALE BOOKMARK IS A VIEW, NOT AN ERROR. The widening reading is the safe one:
    it shows too much rather than answering zero and reading as no data."""
    definition, version = _dataset(warehouse)
    nodes = _tree(warehouse)
    one = _record(warehouse, definition, version, "4001")
    _hold(warehouse, one, nodes["leaf"])
    two = _record(warehouse, definition, version, "4002")
    _hold(warehouse, two, nodes["other"])

    out = _payload(warehouse, nodes=[nodes["root"], nodes["other"]],
                   nodes_mode="whatever")

    assert out["total"] == 2
    assert out["filtered_by"]["mode"] == "any"


def test_no_selection_leaves_the_payload_exactly_as_it_was(warehouse):
    """EVERY EXISTING READER OF `total` IS UNTOUCHED, which is why `population` is a new
    key rather than a redefinition of an old one."""
    definition, version = _dataset(warehouse)
    nodes = _tree(warehouse)
    one = _record(warehouse, definition, version, "5001")
    _hold(warehouse, one, nodes["leaf"])

    out = _payload(warehouse)

    assert out["total"] == out["population"] == 1
    assert out["filtered_by"] == {"nodes": [], "mode": "any"}
    assert out["truncated"] is False
