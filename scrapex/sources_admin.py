"""Renaming and removing a source, with its data.

WHY THIS IS ITS OWN MODULE
--------------------------
`source_key` is not a label. It is the join every part of the warehouse uses to
say which shop a row came from, and it appears in NINE tables — so changing it
in the manifest alone does not rename a source, it ORPHANS one: the manifest
would describe a shop the warehouse has never heard of while 1,203 products sat
under a name nothing points at any more.

The owner's ruling (2026-07-28) was that a rename must be a real migration that
moves the rows with the name. That is what this module is.

WHAT `source_key` MEANS IN EACH TABLE, because it does NOT mean the same thing
in all of them and one of these must not be swept up blindly:

    source_site                 the shop itself                     RENAME
    dataset_field               the owner's saved column layout     RENAME
    saved_view                  a saved filter/column arrangement   RENAME
    schedule                    when this source runs               RENAME
    retention_policy            how long its rows are kept          RENAME
    tax_rule                    the tax position for its prices     RENAME
    source_attribute_promotion  details the owner promoted          RENAME
    job_log_entry               which source a log line was about   RENAME
    currency_rate               the RATE PROVIDER, not the shop     conditional

currency_rate is the trap. Its source_key names whoever published the exchange
rate: 'google_finance' for the rates module, and a SHOP's own key when that shop
publishes implied rates (GPP writes its local/USD pairs under GPP_ENERGY). So
renaming GPP_ENERGY must carry its rate rows, and renaming any other source must
not touch a single one. Scoping it to the key being renamed does exactly that,
which is why it is included rather than excluded — but it is included knowingly,
not by pattern-matching a column name across a schema.
"""
from __future__ import annotations

import sqlite3

# Every table whose source_key names THIS source. Written out rather than
# discovered by scanning the schema for the column: a future table could use the
# name for something else entirely (currency_rate nearly did), and a rename that
# guesses is a rename that corrupts.
_KEYED_TABLES = (
    "source_site",
    "dataset_field",
    "saved_view",
    "schedule",
    "retention_policy",
    "tax_rule",
    "source_attribute_promotion",
    "job_log_entry",
    "currency_rate",
)


class SourceKeyInUse(ValueError):
    """The new key already names a different source."""


def rename_source(conn: sqlite3.Connection, old_key: str, new_key: str) -> dict[str, int]:
    """Move a source and everything joined to it, in ONE transaction.

    Returns table -> rows moved, so the caller can report what actually happened
    rather than assert that something did.

    All-or-nothing on purpose: a rename that updated six tables and failed on the
    seventh would leave the warehouse describing two shops that are really one,
    which is worse than not renaming at all.
    """
    old_key = (old_key or "").strip()
    new_key = (new_key or "").strip()
    if not old_key or not new_key:
        raise ValueError("both the old and the new source_key are required")
    if old_key == new_key:
        return {}

    taken = conn.execute("SELECT 1 FROM source_site WHERE source_key = ?",
                         (new_key,)).fetchone()
    if taken:
        raise SourceKeyInUse(
            f"{new_key!r} already names another source; renaming onto it would "
            "merge two shops' rows into one history")
    if not conn.execute("SELECT 1 FROM source_site WHERE source_key = ?",
                        (old_key,)).fetchone():
        raise KeyError(old_key)

    moved: dict[str, int] = {}
    with conn:                       # one transaction: all of it, or none of it
        for table in _KEYED_TABLES:
            cursor = conn.execute(
                f"UPDATE {table} SET source_key = ? WHERE source_key = ?",
                (new_key, old_key))
            if cursor.rowcount:
                moved[table] = cursor.rowcount
    return moved


def source_footprint(conn: sqlite3.Connection, source_key: str) -> dict[str, int]:
    """What a source actually holds, for a UI that must not delete blindly.

    The owner asked for "stop this source" and "erase its data" to be two
    separate buttons with two clear outcomes. A button that says how many
    products and how many price observations it is about to erase is the
    difference between a choice and a guess.
    """
    counts: dict[str, int] = {}
    row = conn.execute("SELECT source_id FROM source_site WHERE source_key = ?",
                       (source_key,)).fetchone()
    if row is None:
        return counts
    source_id = row[0]
    counts["products"] = conn.execute(
        "SELECT COUNT(*) FROM source_product WHERE source_id = ?", (source_id,)).fetchone()[0]
    counts["observations"] = conn.execute(
        "SELECT COUNT(*) FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.source_id = ?", (source_id,)).fetchone()[0]
    counts["details"] = conn.execute(
        "SELECT COUNT(*) FROM source_product_attribute spa "
        "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
        "WHERE sp.source_id = ?", (source_id,)).fetchone()[0]
    counts["runs"] = conn.execute(
        "SELECT COUNT(*) FROM crawl_run WHERE source_id = ?", (source_id,)).fetchone()[0]
    return counts
