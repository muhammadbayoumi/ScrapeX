"""Column presentation without schema destruction (spec section 22).

The whole point of this module is one rule: **a presentation change is never a
destructive schema change**. Renaming a column edits a label; hiding one removes
it from a view. Neither touches `field_key`, the stored values, or what future
crawls collect — a hidden column keeps filling up so un-hiding it later shows a
complete history, not a gap.

There is deliberately NO delete_field(): removing a column from a view is what
hiding is for, and the data behind it is not this layer's to destroy.
"""
from __future__ import annotations

import json
import sqlite3

ORIGINAL_SCHEMA = "original"      # every field, discovery order — the raw contract
CURRENT_VIEW = "current"          # the owner's arrangement: visible only, their order


def ensure_fields(conn: sqlite3.Connection, source_key: str, columns: list[str]) -> None:
    """Register any column not seen before, preserving its original name+order.

    Idempotent and additive: an existing field is left completely alone, so a
    connector that grows a column never disturbs the owner's arrangement of the
    ones already there.
    """
    known = {r["field_key"] for r in conn.execute(
        "SELECT field_key FROM dataset_field WHERE source_key = ?", (source_key,))}
    next_order = conn.execute(
        "SELECT COALESCE(MAX(display_order), -1) + 1 FROM dataset_field WHERE source_key = ?",
        (source_key,)).fetchone()[0]
    for column in columns:
        if column in known:
            continue
        # INSERT OR IGNORE, not a bare INSERT: two callers can race between the
        # SELECT above and here, and losing that race must be a no-op rather than
        # an IntegrityError on ux_dataset_field.
        conn.execute(
            "INSERT OR IGNORE INTO dataset_field "
            "(source_key, field_key, original_name, display_order) VALUES (?,?,?,?)",
            (source_key, column, column, next_order))
        known.add(column)          # a duplicate within `columns` must not re-insert
        next_order += 1


def list_fields(conn: sqlite3.Connection, source_key: str) -> list[dict]:
    """Every field, hidden ones included — the "manage columns" surface."""
    rows = conn.execute(
        "SELECT field_key, original_name, display_name, data_type, is_hidden, display_order "
        "FROM dataset_field WHERE source_key = ? ORDER BY display_order, dataset_field_id",
        (source_key,))
    return [{**dict(r), "is_hidden": bool(r["is_hidden"]),
             "label": r["display_name"] or r["original_name"]} for r in rows]


def visible_columns(conn: sqlite3.Connection, source_key: str,
                    fallback: list[str] | None = None) -> list[str]:
    """field_keys the current view shows, in the owner's order.

    The fallback triggers on "no fields REGISTERED", not on "none visible".
    Keying it off visibility meant that hiding every column made the current-view
    export fall back to showing them ALL — the exact opposite of what was asked.
    """
    rows = conn.execute(
        "SELECT field_key, is_hidden FROM dataset_field WHERE source_key = ? "
        "ORDER BY display_order, dataset_field_id", (source_key,)).fetchall()
    if not rows:
        return fallback or []
    return [r["field_key"] for r in rows if not r["is_hidden"]]


def hidden_columns(conn: sqlite3.Connection, source_key: str) -> set[str]:
    """Only the keys the owner EXPLICITLY hid.

    The complement of visible_columns for a different question: a column that
    was never registered was never hidden, and must default to SHOWN. Deriving
    "wanted" from the registered-visible list silently suppressed every column
    added after a source's view was first seeded — brand, category and the
    discount arrived in the payload rows and never in the column list."""
    return {r["field_key"] for r in conn.execute(
        "SELECT field_key FROM dataset_field WHERE source_key = ? AND is_hidden = 1",
        (source_key,))}


def arranged(conn: sqlite3.Connection, source_key: str) -> bool:
    """Has a person arranged this source's columns, or is it still the default?

    The distinction decides which order every surface shows. A default is ours
    to improve; an arrangement is his, and the day we "correct" one is the day
    the product overwrote its owner.
    """
    row = conn.execute(
        "SELECT 1 FROM dataset_field WHERE source_key = ? AND arranged_at IS NOT NULL "
        "LIMIT 1", (source_key,)).fetchone()
    return row is not None


def column_order(conn: sqlite3.Connection, source_key: str,
                 keys: list[str]) -> list[str]:
    """The order to show `keys` in — the ONE answer all three surfaces use.

    Until now there were three. The grid read a literal list in reports.py, the
    Choose-Columns panel and the export read dataset_field.display_order, and
    they disagreed at position 0: MADAR opened product_name on the grid and
    product_name_ar in the panel, with price 18th against 13th. So the only
    reorder control the product has — the drag handles in Choose Columns —
    saved, reloaded the page, and changed nothing the owner could see.

    Not arranged: the agreed reading order, identity then the offer then the
    filing, computed from reports.COLUMN_RANK. Anything with no rank keeps its
    given position, after the ranked ones, so a column this file has never
    heard of is never dropped.

    Arranged: his display_order, exactly. No blending, no "improving" — a
    default we may replace and an arrangement we may not are different things.
    """
    from . import reports

    if arranged(conn, source_key):
        stored = {row["field_key"]: row["display_order"]
                  for row in conn.execute(
                      "SELECT field_key, display_order FROM dataset_field "
                      "WHERE source_key = ?", (source_key,))}
        ceiling = len(stored) + len(keys)
        return sorted(keys, key=lambda key: (stored.get(key, ceiling), key))
    ceiling = len(reports.COLUMN_RANK)
    return [key for _, key in sorted(
        enumerate(keys),
        key=lambda pair: reports.COLUMN_RANK.get(pair[1], ceiling + pair[0]))]


def set_display_name(conn: sqlite3.Connection, source_key: str, field_key: str,
                     display_name: str | None) -> bool:
    """Rename the LABEL. field_key and original_name are untouched, so a rename
    can never break ingest or lose what the source actually called it."""
    cur = conn.execute(
        "UPDATE dataset_field SET display_name = ? WHERE source_key = ? AND field_key = ?",
        ((display_name or "").strip() or None, source_key, field_key))
    return cur.rowcount == 1


def set_visibility(conn: sqlite3.Connection, source_key: str, field_key: str,
                   hidden: bool) -> bool:
    """Hide/show a column. This is a VIEW operation — the column keeps receiving
    updates while hidden, which is exactly why it is not a delete."""
    cur = conn.execute(
        "UPDATE dataset_field SET is_hidden = ? WHERE source_key = ? AND field_key = ?",
        (1 if hidden else 0, source_key, field_key))
    return cur.rowcount == 1


def reorder(conn: sqlite3.Connection, source_key: str, ordered_keys: list[str]) -> None:
    """Apply an explicit column order.

    A PARTIAL list is allowed: fields the caller didn't mention keep their
    relative order and follow the listed ones. The full order is computed here
    rather than nudged with offsets, so repeated reorders stay stable.
    """
    if not ordered_keys:
        return
    current = [f["field_key"] for f in list_fields(conn, source_key)]
    listed = [key for key in ordered_keys if key in current]
    rest = [key for key in current if key not in listed]
    for position, field_key in enumerate(listed + rest):
        conn.execute(
            "UPDATE dataset_field SET display_order = ? WHERE source_key = ? AND field_key = ?",
            (position, source_key, field_key))
    # This is the only path a PERSON can reach — the drag handles and the
    # Arrow Up/Down keys in Choose Columns both land here. Stamping it is what
    # lets every surface tell an arrangement from a default, which is the whole
    # reason a stored order can be trusted at all (0059).
    conn.execute(
        "UPDATE dataset_field SET arranged_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE source_key = ?", (source_key,))


def reset_view(conn: sqlite3.Connection, source_key: str) -> None:
    """Restore the default: original names, everything visible, discovery order."""
    conn.execute(
        "UPDATE dataset_field SET display_name = NULL, is_hidden = 0, "
        "display_order = dataset_field_id, arranged_at = NULL "
        "WHERE source_key = ?", (source_key,))


# ---- saved views -------------------------------------------------------------

def save_view(conn: sqlite3.Connection, source_key: str, view_name: str, config: dict) -> int:
    """Create or overwrite a named arrangement of this dataset."""
    conn.execute(
        "INSERT INTO saved_view (source_key, view_name, config_json) VALUES (?,?,?) "
        "ON CONFLICT(source_key, view_name) DO UPDATE SET config_json = excluded.config_json",
        (source_key, view_name, json.dumps(config, ensure_ascii=False)))
    return int(conn.execute(
        "SELECT saved_view_id FROM saved_view WHERE source_key = ? AND view_name = ?",
        (source_key, view_name)).fetchone()[0])


def list_views(conn: sqlite3.Connection, source_key: str) -> list[dict]:
    return [{"saved_view_id": r["saved_view_id"], "view_name": r["view_name"],
             "config": json.loads(r["config_json"]), "created_at": r["created_at"]}
            for r in conn.execute(
                "SELECT * FROM saved_view WHERE source_key = ? ORDER BY view_name",
                (source_key,))]


def delete_view(conn: sqlite3.Connection, saved_view_id: int) -> bool:
    """Views ARE deletable — a view holds no data, only an arrangement."""
    cur = conn.execute("DELETE FROM saved_view WHERE saved_view_id = ?", (saved_view_id,))
    return cur.rowcount == 1


# ---- applying a schema choice to an exported table ---------------------------

def apply_schema(conn: sqlite3.Connection, source_key: str, header: list[str],
                 rows: list[list], schema: str = ORIGINAL_SCHEMA) -> tuple[list[str], list[list]]:
    """Project an exported table through the chosen schema (spec 22: export and
    sync may use either the Original Schema or the Current View).

    ORIGINAL_SCHEMA returns the table untouched — the raw contract, so a
    downstream consumer is never surprised by the owner's cosmetic choices.
    """
    ensure_fields(conn, source_key, header)
    if schema == ORIGINAL_SCHEMA:
        return header, rows

    keep = [c for c in visible_columns(conn, source_key, header) if c in header]
    labels = {f["field_key"]: f["label"] for f in list_fields(conn, source_key)}
    index = [header.index(c) for c in keep]
    return [labels.get(c, c) for c in keep], [[row[i] for i in index] for row in rows]


# ---- promoting a DETAIL to a COLUMN (0044) -----------------------------------
#
# The owner's question: are the exported tables not already assembled from the
# system's own tables? They are — madar's export is 56 declared columns plus 64
# pivoted out of source_product_attribute, the details table itself. What was
# missing was never the machine. It was that the SHOP decided which detail rose:
# an attribute became a column only where the site published it as a facet, so
# madar got 64 and sika, whose shop publishes none, got nothing at all.

# An axis and an attribute can share a name — madar publishes «المقاس» as both a
# variation axis and a product specification — so a promotion has to say WHICH
# it promoted. The prefix is stored, never displayed.
AXIS_PREFIX = "axis:"


def promotable_axes(conn: sqlite3.Connection, source_key: str) -> list[dict]:
    """Every variation axis this source publishes, with how many products carry it.

    An axis is what the SHOP varies a product by — a 20mm blade against a 30mm
    one. Until now every axis became a main-table column the moment it was
    first seen, with no way to send it back, because the chooser only ever read
    source_product_attribute. Madar reached 59 of them, 33 non-empty on under
    1% of its rows, and the owner asked three times to have them moved.

    Counted per PRODUCT rather than per variant, so the number means the same
    thing as the attribute counts beside it in the chooser.
    """
    rows = conn.execute(
        "SELECT sv.variant_axes, sv.variant_axes_ar, sp.source_product_id "
        "FROM source_variant sv "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND sv.status = 'active' AND sp.status = 'active'",
        (source_key,)).fetchall()
    seen: dict[str, set] = {}
    for axes_en, axes_ar, product in rows:
        for blob in (axes_en, axes_ar):
            try:
                parsed = json.loads(blob or "{}") or {}
            except (TypeError, ValueError):
                continue
            for name in parsed:
                seen.setdefault(name, set()).add(product)
    total = conn.execute(
        "SELECT COUNT(*) FROM source_product sp "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND sp.status = 'active'", (source_key,)).fetchone()[0] or 0
    chosen = promoted_attributes(conn, source_key)
    return [{"attribute_code": AXIS_PREFIX + name, "label": name, "group": "",
             "lang": "", "products": len(products), "of_products": total,
             # Never "the site said so": a site filter is the shop saying this
             # is how people shop for it, and an axis is only how it varies.
             "by_the_site": False, "promoted": AXIS_PREFIX + name in chosen,
             "is_column": AXIS_PREFIX + name in chosen, "kind": "axis"}
            for name, products in sorted(seen.items(),
                                         key=lambda kv: (-len(kv[1]), kv[0]))]


def promotable_attributes(conn: sqlite3.Connection, source_key: str) -> list[dict]:
    """Every detail this source publishes that COULD be a column, with the
    count of products that actually fill it, and whether it is a column now.

    The count is the point: an attribute two products carry is a column of
    blanks, and the owner should see that before choosing, not after
    exporting.

    Single-product codes are left out, and the measurement is why: sika
    publishes 535 `image_N` and 202 `attachment_N` codes, one per file, so
    737 of its 760 details belong to exactly one product. Those are that
    product's own rows, not KINDS of fact, and offering them turned the
    chooser into 760 lines nobody can read. Sika drops to 23, madar to 16 —
    which is the list a person can actually decide from.
    """
    rows = conn.execute(
        "SELECT spa.attribute_code, "
        "       COALESCE(NULLIF(spa.attribute_label,''), spa.attribute_code) AS label, "
        "       spa.attribute_group, spa.lang, "
        "       COUNT(DISTINCT spa.source_product_id) AS products, "
        "       MAX(spa.is_site_filter) AS by_the_site "
        "FROM source_product_attribute spa "
        "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND sp.status = 'active' "
        "GROUP BY spa.attribute_code "
        "ORDER BY products DESC, label",
        (source_key,)).fetchall()
    chosen = promoted_attributes(conn, source_key)
    total = conn.execute(
        "SELECT COUNT(*) FROM source_product sp "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND sp.status = 'active'", (source_key,)).fetchone()[0] or 0
    offered = [{"attribute_code": r[0], "label": r[1], "group": r[2], "lang": r[3] or "",
                "products": r[4], "of_products": total,
                # Two different reasons a detail is a column, and the owner
                # should tell them apart: the site said so, or he did.
                "by_the_site": bool(r[5]), "promoted": r[0] in chosen,
                "is_column": bool(r[5]) or r[0] in chosen, "kind": "detail"}
               for r in rows
               # A code that covers exactly ONE product is that product's own
               # row, not a KIND of fact — sika publishes 535 image_N and 202
               # attachment_N codes that way, and 737 of its 760 details are
               # single-product. A column for one of them is 86 blanks and one
               # value, and 760 of them is a chooser nobody can read. Anything
               # already a column stays listed whatever its coverage, so a
               # choice can always be undone.
               if r[4] > 1 or bool(r[5]) or r[0] in chosen]
    # The axes ride the same list, so the panel that already reads it gains
    # them without a second endpoint — and the owner sees details and axes in
    # one place, ranked by how much of his data each actually fills.
    return offered + promotable_axes(conn, source_key)


def promoted_attributes(conn: sqlite3.Connection, source_key: str) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT attribute_code FROM source_attribute_promotion WHERE source_key = ?",
        (source_key,))}


def set_promotion(conn: sqlite3.Connection, source_key: str,
                  attribute_code: str, promote: bool) -> bool:
    """Promote a detail to a column, or send it back. Returns the new state.

    Reversible by construction — the row IS the promotion, so demoting deletes
    it and nothing has to remember a previous shape. The opposite direction for
    a column that was always a column already works: hiding it moves it to the
    details panel, showing it brings it back.
    """
    if promote:
        conn.execute(
            "INSERT OR IGNORE INTO source_attribute_promotion (source_key, attribute_code) "
            "VALUES (?,?)", (source_key, attribute_code))
    else:
        conn.execute(
            "DELETE FROM source_attribute_promotion WHERE source_key = ? AND attribute_code = ?",
            (source_key, attribute_code))
    return promote
