"""Field-level change detection (spec section 15).

The classification rules are PURE functions so they can be pinned by tests without
a database; `record_change` is the only part that touches SQLite. ingest calls
these at the two points where old and new state are both in hand.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from .vocab import Availability, ChangeType

# Product fields worth tracking. Deliberately a short explicit list (P5): these
# are the source-local descriptive fields the owner sees, not every column.
TRACKED_PRODUCT_FIELDS = (
    ("source_name", "product_name"),   # (stored column, incoming row key)
    ("product_url", "product_url"),
    ("brand_raw", "brand_raw"),
    ("external_sku", "external_sku"),
)

# Fields whose OLD value is an identity worth remembering (spec 14): if a site
# re-slugs a URL or re-issues a SKU, the previous value must stay findable or a
# re-crawl mints a duplicate and splits the price history.
ALIAS_FIELDS = {"product_url": "product_url", "external_sku": "external_sku"}


def classify_price(previous: Decimal | float | None,
                   current: Decimal | float | None) -> ChangeType | None:
    """Price movement, or None when there is nothing to report.

    No previous price is NOT a change — the 'new' event already covers that.
    """
    if previous is None or current is None:
        return None
    prev, cur = Decimal(str(previous)), Decimal(str(current))
    if cur > prev:
        return ChangeType.PRICE_INCREASE
    if cur < prev:
        return ChangeType.PRICE_DECREASE
    return None


def classify_availability(previous: str | None, current: str | None) -> ChangeType | None:
    """in_stock -> out_of_stock is 'unavailable'; the way back is 'returned'.

    Transitions through 'unknown' are deliberately NOT reported: a connector that
    briefly cannot read stock would otherwise emit a fake disappearance.
    """
    known = {Availability.IN_STOCK.value, Availability.OUT_OF_STOCK.value}
    if previous not in known or current not in known or previous == current:
        return None
    return (ChangeType.UNAVAILABLE if current == Availability.OUT_OF_STOCK.value
            else ChangeType.RETURNED)


def product_field_diffs(stored: dict, incoming: dict) -> list[tuple[str, str, str]]:
    """(field_key, previous, new) for every tracked product field that changed.

    An incoming EMPTY value is treated as 'the connector did not report it', never
    as 'the source cleared it' — otherwise a partial parse would wipe good data.
    """
    diffs: list[tuple[str, str, str]] = []
    for column, row_key in TRACKED_PRODUCT_FIELDS:
        new = (incoming.get(row_key) or "").strip()
        old = (stored.get(column) or "").strip()
        if new and new != old:
            diffs.append((column, old, new))
    return diffs


def record_change(conn: sqlite3.Connection, change_type: ChangeType, field_key: str, *,
                  previous_value=None, new_value=None, source_product_id: int | None = None,
                  source_variant_id: int | None = None, offer_id: int | None = None,
                  run_id: int | None = None, job_id: int | None = None) -> None:
    conn.execute(
        "INSERT INTO change_event (source_product_id, source_variant_id, offer_id, field_key, "
        " previous_value, new_value, change_type, run_id, job_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (source_product_id, source_variant_id, offer_id, field_key,
         None if previous_value is None else str(previous_value),
         None if new_value is None else str(new_value),
         change_type.value, run_id, job_id),
    )


def record_alias(conn: sqlite3.Connection, source_product_id: int,
                 alias_type: str, alias_value: str) -> None:
    """Remember a superseded identity value. Idempotent: seeing the same old value
    again (a site that flip-flops) must not raise."""
    if not alias_value:
        return
    conn.execute(
        "INSERT OR IGNORE INTO identity_alias (source_product_id, alias_type, alias_value, retired_at) "
        "VALUES (?,?,?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
        (source_product_id, alias_type, alias_value),
    )


def aliases_of(conn: sqlite3.Connection, source_product_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT alias_type, alias_value, retired_at FROM identity_alias "
        "WHERE source_product_id = ? ORDER BY identity_alias_id", (source_product_id,))]


def change_summary(conn: sqlite3.Connection, source_key: str, run_id: int | None = None) -> dict:
    """Counts per change_type for one source — the panel's change summary."""
    sql = ("SELECT c.change_type, COUNT(*) FROM change_event c "
           "JOIN source_product sp ON sp.source_product_id = c.source_product_id "
           "JOIN source_site ss ON ss.source_id = sp.source_id WHERE ss.source_key = ?")
    params: list = [source_key]
    if run_id is not None:
        sql += " AND c.run_id = ?"
        params.append(run_id)
    sql += " GROUP BY c.change_type"
    return {row[0]: row[1] for row in conn.execute(sql, params)}


def recent_changes(conn: sqlite3.Connection, source_key: str | None = None,
                   limit: int = 50) -> list[dict]:
    """Newest-first change feed, always bounded (A8).

    The offer's region is resolved here because product_name alone is ambiguous
    for a commodity source: a price move on Egyptian diesel and one on Saudi
    diesel would otherwise both read as just "DIESEL".
    """
    sql = ("SELECT c.*, sp.source_name AS product_name, so.region AS region "
           "FROM change_event c "
           "LEFT JOIN source_product sp ON sp.source_product_id = c.source_product_id "
           "LEFT JOIN source_offer so ON so.offer_id = c.offer_id ")
    params: list = []
    if source_key is not None:
        sql += ("JOIN source_site ss ON ss.source_id = sp.source_id "
                "WHERE ss.source_key = ? ")
        params.append(source_key)
    sql += "ORDER BY c.change_event_id DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))

    from .reports import region_name          # display-only resolution (ISO -> name)
    out = []
    for row in conn.execute(sql, params):
        item = dict(row)
        item["region"] = item.get("region") or ""
        item["region_name"] = region_name(item["region"])
        out.append(item)
    return out
