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
    #: WHAT THE SITE SAID ABOUT THIS MEMBERSHIP, from `0010`: the site's own name
    #: for the attribute and its two published halves. Empty strings where the
    #: group publishes no attribute column, which is every interest and 1,490 of
    #: 1,500 measured licences.
    #:
    #: THIS IS WHAT THE ROW'S CARD SHOWS AND THE TABLE CANNOT. `R-45`: a field is
    #: not a column, and `مستوى الجاهزية` describes one activity rather than the
    #: contractor -- so it has no honest home on the contractors table at all.
    attribute_label: str = ""
    attribute_value: str = ""
    attribute_value_ar: str = ""


def ensure_scheme(conn: sqlite3.Connection, source_id: int, *,
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
        "(scheme_name_ar, scheme_name, scheme_type, source_id) "
        "VALUES (?,?,'source',?)", (name_ar, name, source_id))
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
         group_key: str, source_snapshot_id: int,
         attribute: tuple[str, str, str] | None = None) -> bool:
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

    `attribute` IS `(label, value, value_ar)` AND IT BELONGS TO THE MEMBERSHIP, which is
    `0010` and `R-45`. What the site says about one activity — muqawil publishes
    `مستوى الجاهزية` beside each licence, `أساسي | Basic` — describes THAT membership and
    not the contractor, so a contractor with six licences can be graded on one and
    ungraded on five. `None` is the common case: measured, 1,490 of 1,500 licence rows
    publish nothing here and interests publish nothing by construction.

    THE LABEL IS THE SITE'S, NEVER OURS, which is why it is a value rather than a column
    name. A column called `readiness` on a table that serves every site would need a
    fourth for Balady's attribute and a fifth for the UAE's — the shape his ruling was
    about, one level down.

    A REPEAT OVERWRITES IT RATHER THAN KEEPING THE OLD ONE, on the same reasoning as
    `source_snapshot_id` on the line below it: the newest reading of a page is the one
    whose evidence we still hold. A contractor upgraded from `أساسي` to `ذهبي` must not
    keep the old grade because the membership itself is unchanged.
    """
    label, value, value_ar = attribute or ("", "", "")
    seen = conn.execute(
        "INSERT INTO generic_record_node "
        "(generic_record_id, node_id, group_key, source_snapshot_id, "
        " attribute_label, attribute_value, attribute_value_ar) "
        "VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(generic_record_id, node_id, group_key) DO UPDATE SET "
        "  last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        "  seen_count = seen_count + 1, "
        "  source_snapshot_id = excluded.source_snapshot_id, "
        "  attribute_label = excluded.attribute_label, "
        "  attribute_value = excluded.attribute_value, "
        "  attribute_value_ar = excluded.attribute_value_ar "
        "RETURNING seen_count",
        (generic_record_id, node_id, group_key, source_snapshot_id,
         label or None, value or None, value_ar or None)).fetchone()
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
    # THE ATTRIBUTE IS CARRIED THROUGH THE RECURSION RATHER THAN JOINED AGAIN.
    # It lives on the membership row, which only the ANCHOR of this CTE touches --
    # every later step walks `classification_node` upward and has no membership to
    # read. Selecting it once in the anchor and passing it along costs three
    # columns; a second join would cost a query per membership, which is the round
    # trip this CTE exists to avoid.
    rows = conn.execute(
        "WITH RECURSIVE up(node_id, group_key, leaf_id, name, name_ar, parent, "
        "                  label, value, value_ar) AS ("
        "  SELECT n.node_id, m.group_key, n.node_id, n.node_name, n.node_name_ar, "
        "         n.parent_node_id, m.attribute_label, m.attribute_value, "
        "         m.attribute_value_ar "
        "    FROM generic_record_node AS m "
        "    JOIN classification_node AS n ON n.node_id = m.node_id "
        "   WHERE m.generic_record_id = ? "
        "     AND (? IS NULL OR m.group_key = ?) "
        "  UNION ALL "
        "  SELECT p.node_id, up.group_key, up.leaf_id, p.node_name, p.node_name_ar, "
        "         p.parent_node_id, up.label, up.value, up.value_ar "
        "    FROM up JOIN classification_node AS p ON p.node_id = up.parent "
        ") "
        "SELECT leaf_id, group_key, name, name_ar, label, value, value_ar FROM up "
        " ORDER BY group_key, leaf_id, node_id",
        (generic_record_id, group_key, group_key)).fetchall()

    built: dict[tuple[str, int], tuple[list[str], list[str]]] = {}
    said: dict[tuple[str, int], tuple[str, str, str]] = {}
    for row in rows:
        key = (row["group_key"], int(row["leaf_id"]))
        names, names_ar = built.setdefault(key, ([], []))
        names.append(row["name"] or "")
        names_ar.append(row["name_ar"])
        said[key] = (row["label"] or "", row["value"] or "", row["value_ar"] or "")
    return tuple(
        Membership(group_key=group, node_id=leaf,
                   path=tuple(names), path_ar=tuple(names_ar),
                   attribute_label=said[(group, leaf)][0],
                   attribute_value=said[(group, leaf)][1],
                   attribute_value_ar=said[(group, leaf)][2])
        for (group, leaf), (names, names_ar) in sorted(built.items()))


#: The node the site publishes where a contractor declared nothing. It is a LEVEL-1
#: node of the `interests` scheme with 9,001 contractors under it on his warehouse --
#: larger than `Construction of buildings` at 7,634 -- and it is not a category. His
#: ruling, 2026-09-08: **a state said in a line, not a category in the tree.**
#:
#: MATCHED ON THE ARABIC, because that is the identity the schema chose:
#: `node_name_ar` is `NOT NULL` and carries the unique index while `node_name` is
#: nullable, so the English `No Data` is the softer of the two names to key on.
#:
#: NOT DELETED, AND THAT IS THE OTHER HALF OF HIS RULING. 9,001 contractors having
#: declared nothing is a fact about them; dropping the rows would make it
#: indistinguishable from 9,001 contractors nobody has fetched.
UNDECLARED_NODE_NAMES_AR: tuple[str, ...] = ("لا يوجد بيانات",)


def held_counts(conn: sqlite3.Connection, group_key: str) -> dict[int, int]:
    """Per node: how many records hold it OR anything under it.

    ONE DEFINITION THAT IS CORRECT UNDER BOTH STORAGE CONVENTIONS, which is what makes
    issue 800 safe to defer. Measured on his warehouse: `interests` stores the whole
    path (367,015 of 367,015 child memberships carry their ancestor) and
    `licensed_activities` stores leaves only (0 of 8,451). A count of the stored rows
    per node is therefore the right answer for the first group and reports **zero** for
    every parent in the second -- an empty category rather than a wrong query, which is
    the worst way for this to be wrong.

    Counting the SUBTREE gives one quantity in both, and it is the quantity the filter
    acts on: pick a node, get everyone under it.

    `COUNT(DISTINCT)` IS LOAD-BEARING, NOT DEFENSIVE. Under a stored-path convention a
    contractor holding a leaf holds its ancestors too, so a plain `COUNT(*)` up the
    subtree counts the same contractor once per level of the path -- 22.9 memberships
    per contractor on average, and a root would report several times its own population.

    ONE QUERY AND NOT ONE PER NODE. The recursive term walks the tree, which is 214
    nodes for `interests`, and the membership table is scanned once against it -- 214
    subtree counts in place of 214 round trips.
    """
    rows = conn.execute(
        "WITH RECURSIVE sub(root, node) AS ("
        "  SELECT node_id, node_id FROM classification_node "
        "  UNION ALL "
        "  SELECT sub.root, child.node_id FROM sub "
        "    JOIN classification_node AS child ON child.parent_node_id = sub.node "
        ") "
        "SELECT sub.root, COUNT(DISTINCT m.generic_record_id) "
        "  FROM sub JOIN generic_record_node AS m ON m.node_id = sub.node "
        " WHERE m.group_key = ? "
        " GROUP BY sub.root",
        (group_key,))
    return {int(root): int(held) for root, held in rows}


def subtree_ids(conn: sqlite3.Connection, node_ids) -> frozenset[int]:
    """These nodes and everything under them.

    THE FILTER'S OWN CORRECTNESS, for the reason `held_counts` gives: a chosen parent
    must reach the contractors who hold only its children, and whether those children's
    ancestors happen to be stored differs by group. Descending makes the question the
    same in both.

    Returns an empty set for an empty ask, so a caller can pass a selection straight
    through without deciding what "nothing chosen" means to SQL.
    """
    wanted = tuple({int(one) for one in node_ids})
    if not wanted:
        return frozenset()
    marks = ",".join("?" * len(wanted))
    rows = conn.execute(
        f"WITH RECURSIVE down(node) AS ("
        f"  SELECT node_id FROM classification_node WHERE node_id IN ({marks}) "
        f"  UNION "
        f"  SELECT child.node_id FROM down "
        f"    JOIN classification_node AS child ON child.parent_node_id = down.node "
        f") SELECT node FROM down", wanted)
    return frozenset(int(row[0]) for row in rows)


def group_tree(conn: sqlite3.Connection, group_key: str) -> dict:
    """One group's vocabulary, with what holds it, ready for a filter control.

    THE UNDECLARED NODE IS SEPARATED RATHER THAN DROPPED. His ruling: it is a state,
    said in a line above the tree, so it leaves `nodes` and arrives as `undeclared`
    with its own count. A filter whose largest category is `No Data` is a filter
    answering a question nobody asked.

    THE SCHEME IS NAMED IN BOTH LOCALES because the panel draws whichever the reader
    has chosen, and `classification_scheme` carries both.
    """
    counts = held_counts(conn, group_key)
    scheme = conn.execute(
        "SELECT s.scheme_id, s.scheme_name, s.scheme_name_ar "
        "  FROM classification_scheme AS s "
        " WHERE s.scheme_id = ("
        "   SELECT n.scheme_id FROM generic_record_node AS m "
        "     JOIN classification_node AS n ON n.node_id = m.node_id "
        "    WHERE m.group_key = ? LIMIT 1)",
        (group_key,)).fetchone()
    if scheme is None:
        # NOTHING STORED FOR THIS GROUP, WHICH IS NOT AN ERROR. A directory declares
        # five groups and two are wired; asking for one of the other three has to
        # answer emptily rather than raise, or the route would 500 on a shape the
        # source itself describes.
        return {"group_key": group_key, "scheme": None, "nodes": [],
                "undeclared": None}
    nodes, undeclared = [], None
    for row in conn.execute(
            "SELECT node_id, parent_node_id, level, node_name, node_name_ar "
            "  FROM classification_node WHERE scheme_id = ? "
            " ORDER BY level, node_name_ar", (scheme["scheme_id"],)):
        entry = {"node_id": int(row["node_id"]),
                 "parent_node_id": (None if row["parent_node_id"] is None
                                    else int(row["parent_node_id"])),
                 "level": int(row["level"] or 0),
                 "name": row["node_name"],
                 "name_ar": row["node_name_ar"],
                 "held": int(counts.get(int(row["node_id"]), 0))}
        if row["node_name_ar"] in UNDECLARED_NODE_NAMES_AR:
            undeclared = entry
        else:
            nodes.append(entry)
    return {"group_key": group_key,
            "scheme": {"scheme_id": int(scheme["scheme_id"]),
                       "name": scheme["scheme_name"],
                       "name_ar": scheme["scheme_name_ar"]},
            "nodes": nodes, "undeclared": undeclared}
