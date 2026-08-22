"""A site's own vocabulary, stored once, and the contractors that point at it.

`R-38`. `R-19` ruled that the five multi-valued contractor groups go in child tables
rather than JSON, and every measurement upheld it. What it left open was *how*, and he
settled it: a **taxonomy plus a link table** — shape D — not five child datasets inside
`generic_record`, which was the study's recommendation.

WHY THIS MODULE IS SMALL. Half of shape D already existed and had never been used:
`classification_scheme` and `classification_node` are a generic self-referencing tree
with `parent_node_id`, `node_name`, `node_name_ar` and `level`, and
`ux_classification_node_name` makes `(scheme_id, ifnull(parent_node_id,0),
node_name_ar)` its identity. Only the link was new, and that is migration 0009.

THE IDENTITY IS THE ARABIC NAME, and that is the schema's choice rather than this
module's: `node_name_ar` is `NOT NULL` and carries the unique index, while `node_name`
is nullable. So a path is matched on its Arabic form and the English is written
alongside it — which means the two locales' readings have to be PAIRED before anything
is written, and `ensure_path` refuses a pair it cannot align.

WHAT IS DELIBERATELY NOT HERE. Nothing decides which groups exist or where they are on
a page — that is `R-41`'s declared map in `extract/muqawil.py`. Nothing decides what a
group's values MEAN. This module stores a tree and the memberships in it, for any site.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


class CannotPairLocales(ValueError):
    """Two locales' readings of one group do not line up, so nothing is written.

    THE ALTERNATIVE IS SILENT AND WRONG. The two readings are paired BY POSITION —
    measured on the committed profile, both locales publish 25 interest nodes with the
    same depths in the same document order — so a count that differs means the position
    of one no longer describes the other, and writing anyway would attach an English
    name to a different Arabic node.

    `DSN-05` is the same failure one level up: a locale-blind alignment produced two
    empty strings for every contractor in the country and nothing raised.
    """


@dataclass(frozen=True)
class Membership:
    """One row of `generic_record_node`, in the shape a reader wants it."""

    group_key: str
    node_id: int
    path: tuple[str, ...]
    path_ar: tuple[str, ...]


def ensure_scheme(conn: sqlite3.Connection, site_profile_id: int, *,
                  name: str, name_ar: str) -> int:
    """The site's own vocabulary, created once.

    `scheme_type='source'` because this is the SITE's taxonomy and not one we invented
    — the column's own `CHECK` already names the three kinds, and `'internal'` would
    claim we authored a vocabulary we are only reading.

    `scheme_name_ar` IS UNIQUE IN THE SCHEMA, so it is what the lookup keys on. That is
    the same choice `classification_node` makes for its own identity and for the same
    reason: the Arabic name is the one the schema requires to exist.
    """
    found = conn.execute(
        "SELECT scheme_id FROM classification_scheme WHERE scheme_name_ar = ?",
        (name_ar,)).fetchone()
    if found is not None:
        return int(found[0])
    cursor = conn.execute(
        "INSERT INTO classification_scheme "
        "(scheme_name_ar, scheme_name, scheme_type, site_profile_id) "
        "VALUES (?,?,'source',?)", (name_ar, name, site_profile_id))
    return int(cursor.lastrowid)


def ensure_path(conn: sqlite3.Connection, scheme_id: int, *,
                path: tuple[str, ...], path_ar: tuple[str, ...]) -> int:
    """Every node on one root-to-leaf path, created as needed. Returns the LEAF's id.

    EVERY LEVEL, BECAUSE A CHILD CANNOT EXIST WITHOUT ITS PARENT. `parent_node_id`
    references this same table, so writing a leaf means writing the nodes above it —
    which is why `read_interests` returns paths rather than leaf names.

    IDEMPOTENT ON `(scheme, parent, node_name_ar)`, which is the unique index the schema
    already declares. Running an identical parse twice creates nothing and returns the
    same ids, so a re-parse is free.

    THE ENGLISH NAME IS FILLED IN BUT NEVER MATCHED ON. A node first seen on an Arabic
    page has no English name yet; the next English page supplies it. Matching on it would
    make the same node two nodes depending on which locale arrived first.
    """
    if len(path) != len(path_ar):
        raise CannotPairLocales(
            f"a path of {len(path)} names cannot be paired with one of {len(path_ar)}: "
            f"{path!r} against {path_ar!r}")
    if not path:
        raise CannotPairLocales("an empty path names no node")

    parent: int | None = None
    for level, (name, name_ar) in enumerate(zip(path, path_ar, strict=True), start=1):
        found = conn.execute(
            "SELECT node_id, node_name FROM classification_node "
            " WHERE scheme_id = ? AND ifnull(parent_node_id, 0) = ? "
            "   AND node_name_ar = ?",
            (scheme_id, parent or 0, name_ar)).fetchone()
        if found is None:
            cursor = conn.execute(
                "INSERT INTO classification_node "
                "(scheme_id, parent_node_id, node_name_ar, node_name, level) "
                "VALUES (?,?,?,?,?)", (scheme_id, parent, name_ar, name, level))
            parent = int(cursor.lastrowid)
            continue
        parent = int(found["node_id"])
        if not found["node_name"] and name:
            # THE OTHER LOCALE ARRIVING SECOND. A node first written from an Arabic page
            # has no English name; this is where it gets one, and it is an UPDATE rather
            # than a second node because the Arabic name is the identity.
            conn.execute(
                "UPDATE classification_node SET node_name = ? WHERE node_id = ?",
                (name, parent))
    return int(parent)


def link(conn: sqlite3.Connection, *, generic_record_id: int, node_id: int,
         group_key: str, source_snapshot_id: int) -> bool:
    """This contractor holds this node, in this group. `True` if it is new.

    IDEMPOTENT BY THE PRIMARY KEY, not by a check here — `(generic_record_id, node_id,
    group_key)` is the table's key, so a repeat cannot be written even by a caller that
    forgot to look. `R-38` chose shape D partly for this: shape F would have written
    these through `approve_candidate`, the function whose idempotency key `R-40` had to
    repair.

    `last_seen_at` MOVES ON A REPEAT AND `first_seen_at` DOES NOT, which is the same
    distinction `R-20` draws for a record: a confirmation is not a change. It is what
    makes "this contractor has held this activity since March" answerable later.

    `source_snapshot_id` IS REQUIRED BY THE SCHEMA and passed by every caller, because a
    membership whose evidence is unnamed is a claim rather than a reading.

    "IS IT NEW" IS ANSWERED BY THE COUNTER AND NOT BY THE CLOCK. The first version
    compared `first_seen_at = last_seen_at`, and both come from `strftime(...,'now')` at
    SECOND resolution — so a write and its confirmation inside the same second are
    indistinguishable. Measured: a second identical pass over one profile reported all 25
    memberships as new. `seen_count` is incremented by the upsert and returned, so `= 1`
    means "written just now" with no extra read and nothing to race.
    """
    seen = conn.execute(
        "INSERT INTO generic_record_node "
        "(generic_record_id, node_id, group_key, source_snapshot_id) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(generic_record_id, node_id, group_key) DO UPDATE SET "
        "  last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        "  seen_count = seen_count + 1, "
        "  source_snapshot_id = excluded.source_snapshot_id "
        "RETURNING seen_count",
        (generic_record_id, node_id, group_key, source_snapshot_id)).fetchone()
    return int(seen[0]) == 1


def memberships(conn: sqlite3.Connection, generic_record_id: int, *,
                group_key: str | None = None) -> tuple[Membership, ...]:
    """Everything this contractor holds, with each node's full path rebuilt.

    THE PATH IS REBUILT RATHER THAN STORED, which is the whole point of the taxonomy: the
    string `تشييد المباني` is written once however many contractors hold something under
    it. Storing the path per membership is shape A, and the study measured that at 4.7x
    this.

    A RECURSIVE CTE AND NOT A LOOP, because a loop is one query per level per membership
    — on 500K memberships three levels deep that is 1.5M round trips for an answer SQLite
    can assemble in one.
    """
    rows = conn.execute(
        "WITH RECURSIVE up(node_id, group_key, leaf_id, name, name_ar, parent) AS ("
        "  SELECT n.node_id, m.group_key, n.node_id, n.node_name, n.node_name_ar, "
        "         n.parent_node_id "
        "    FROM generic_record_node AS m "
        "    JOIN classification_node AS n ON n.node_id = m.node_id "
        "   WHERE m.generic_record_id = ? "
        "     AND (? IS NULL OR m.group_key = ?) "
        "  UNION ALL "
        "  SELECT p.node_id, up.group_key, up.leaf_id, p.node_name, p.node_name_ar, "
        "         p.parent_node_id "
        "    FROM up JOIN classification_node AS p ON p.node_id = up.parent "
        ") "
        "SELECT leaf_id, group_key, name, name_ar FROM up "
        " ORDER BY group_key, leaf_id, node_id",
        (generic_record_id, group_key, group_key)).fetchall()

    built: dict[tuple[str, int], tuple[list[str], list[str]]] = {}
    for row in rows:
        key = (row["group_key"], int(row["leaf_id"]))
        names, names_ar = built.setdefault(key, ([], []))
        names.append(row["name"] or "")
        names_ar.append(row["name_ar"])
    return tuple(
        Membership(group_key=group, node_id=leaf,
                   path=tuple(names), path_ar=tuple(names_ar))
        for (group, leaf), (names, names_ar) in sorted(built.items()))
