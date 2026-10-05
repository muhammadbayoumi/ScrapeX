"""A node's records, answered ahead of time, are the records the table's filter keeps.

THE CONTRACT #1200 READS. With no engine, the Data page filters a contractor table
from `taxonomy.selected_by_node`, stored in the light file (#1199): *any* is the union
of the chosen nodes' lists, *all* is their intersection. That is only right if each
list is exactly what `dataset_table_payload(nodes=[n])` keeps. So every assertion here
compares with the engine's own filter, never with a list written out by hand, and the
fixture holds both storage conventions his warehouse has: `licensed_activities` keeps
leaves only, `interests` keeps the whole path (`taxonomy.held_counts`).
"""
from __future__ import annotations

from itertools import combinations

from scrapex import taxonomy
from scrapex.extract import service
from tests.test_an_activity_filter_reads_what_is_stored import (
    DATASET,
    _dataset,
    _hold,
    _record,
    _tree,
    warehouse,
)

OTHER_DATASET = "contractors"


def _second_dataset(conn) -> tuple[int, int]:
    """Another dataset on the same site, holding the same tree."""
    source = conn.execute(
        "SELECT source_id FROM source_site WHERE source_key = 'muqawil_org'").fetchone()[0]
    definition = conn.execute(
        "INSERT INTO dataset_definition "
        "  (source_id, dataset_key, original_name, dataset_kind, discovery_method) "
        "VALUES (?, ?, 'Contractors', 'table', 'repeating_dom') "
        "RETURNING dataset_definition_id", (source, OTHER_DATASET)).fetchone()[0]
    version = conn.execute(
        "INSERT INTO dataset_schema_version "
        "  (dataset_definition_id, version_number, schema_hash) "
        "VALUES (?, 1, 'hash-2') RETURNING schema_version_id",
        (definition,)).fetchone()[0]
    conn.commit()
    return int(definition), int(version)


def _filtered(conn, nodes, mode="any", dataset=DATASET) -> list[int]:
    """The record ids the engine's own filter keeps."""
    payload = service.dataset_table_payload(conn, dataset, nodes=nodes, nodes_mode=mode)
    return sorted(row[service.OBSERVED_RECORD_ID] for row in payload["rows"])


def _directory(conn):
    """Two datasets, one tree, and every way a record can hold it.

    - `leaf_only` holds the leaf alone: the `licensed_activities` convention.
    - `whole_path` holds root, branch and leaf, and `other` too: the `interests`
      convention, plus a second root.
    - `other_only`, `undeclared`, and `nothing` holds no node at all.
    - `elsewhere` is the second dataset's, holding the root and `other`.
    """
    definition, version = _dataset(conn)
    nodes = _tree(conn)
    held = {name: _record(conn, definition, version, cid) for name, cid in (
        ("leaf_only", "4001"), ("whole_path", "4002"), ("other_only", "4003"),
        ("undeclared", "4004"), ("nothing", "4005"))}
    _hold(conn, held["leaf_only"], nodes["leaf"], group_key="licensed_activities")
    for node in ("root", "branch", "leaf", "other"):
        _hold(conn, held["whole_path"], nodes[node])
    _hold(conn, held["other_only"], nodes["other"])
    _hold(conn, held["undeclared"], nodes["undeclared"])

    other_definition, other_version = _second_dataset(conn)
    held["elsewhere"] = _record(conn, other_definition, other_version, "5001")
    _hold(conn, held["elsewhere"], nodes["root"])
    _hold(conn, held["elsewhere"], nodes["other"])
    return definition, other_definition, nodes, held


def test_every_node_selects_exactly_what_the_filter_keeps(warehouse):
    """If this fails, an offline filter shows a different table from the engine's."""
    definition, _, nodes, held = _directory(warehouse)

    selected = taxonomy.selected_by_node(warehouse, definition, nodes.values())

    assert set(selected) == set(nodes.values())
    for name, node in nodes.items():
        assert selected[node] == _filtered(warehouse, [node]), name
    # NOT VACUOUS: the root must reach the record that holds only its leaf, which a
    # list matching the node itself, instead of its subtree, would miss.
    assert selected[nodes["root"]] == sorted([held["leaf_only"], held["whole_path"]])


def test_a_union_is_any_and_an_intersection_is_all(warehouse):
    """The rule #1200 applies to these lists, held for every pair of nodes."""
    definition, _, nodes, held = _directory(warehouse)
    selected = taxonomy.selected_by_node(warehouse, definition, nodes.values())

    for a, b in combinations(sorted(nodes.values()), 2):
        union = sorted(set(selected[a]) | set(selected[b]))
        both = sorted(set(selected[a]) & set(selected[b]))
        assert union == _filtered(warehouse, [a, b], "any"), (a, b)
        assert both == _filtered(warehouse, [a, b], "all"), (a, b)
    # One pair where the two answers differ, so the loop above compared something.
    assert sorted(set(selected[nodes["leaf"]]) & set(selected[nodes["other"]])) \
        == [held["whole_path"]]


def test_another_datasets_records_never_appear(warehouse):
    """The membership table holds every dataset's records; only this one's are asked."""
    definition, other_definition, nodes, held = _directory(warehouse)

    mine = taxonomy.selected_by_node(warehouse, definition, nodes.values())
    theirs = taxonomy.selected_by_node(warehouse, other_definition, nodes.values())

    assert all(held["elsewhere"] not in records for records in mine.values())
    assert theirs[nodes["root"]] == [held["elsewhere"]]
    assert theirs[nodes["root"]] == _filtered(
        warehouse, [nodes["root"]], dataset=OTHER_DATASET)


def test_the_undeclared_node_is_answered_like_any_other(warehouse):
    """The page draws it above the tree (`group_tree`), and it filters like a node."""
    definition, _, nodes, held = _directory(warehouse)

    selected = taxonomy.selected_by_node(warehouse, definition, [nodes["undeclared"]])

    assert selected == {nodes["undeclared"]: [held["undeclared"]]}


def test_an_unknown_node_selects_nothing_and_no_node_asks_nothing(warehouse):
    """The same answers the filter gives: a stale id narrows to no rows."""
    definition, _, nodes, _held = _directory(warehouse)
    missing = max(nodes.values()) + 100

    assert taxonomy.selected_by_node(warehouse, definition, [missing]) == {missing: []}
    assert _filtered(warehouse, [missing]) == []
    assert taxonomy.selected_by_node(warehouse, definition, []) == {}
