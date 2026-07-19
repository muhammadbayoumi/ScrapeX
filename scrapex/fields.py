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


def reset_view(conn: sqlite3.Connection, source_key: str) -> None:
    """Restore the default: original names, everything visible, discovery order."""
    conn.execute(
        "UPDATE dataset_field SET display_name = NULL, is_hidden = 0, "
        "display_order = dataset_field_id WHERE source_key = ?", (source_key,))


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
