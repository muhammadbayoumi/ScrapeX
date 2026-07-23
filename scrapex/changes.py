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
    # Classification is product identity the source states (owner ruling
    # 2026-07-22): tracked like brand, so a product the site re-files under a
    # new category records the move instead of silently forgetting the old one.
    ("category_path", "category_path"),
    ("category_path_en", "category_path_en"),
    ("category_external_id", "category_external_id"),
    # The English name, tracked like the primary one — a bilingual site
    # renaming in either language is a recorded change, not a silent drift.
    ("source_name_en", "product_name_en"),
    ("name_lang", "lang"),
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
    sql = ("SELECT c.*, sp.source_name AS product_name, so.region AS region, "
           "       su.unit_code AS unit_code, so.basis_quantity AS basis_quantity "
           "FROM change_event c "
           "LEFT JOIN source_product sp ON sp.source_product_id = c.source_product_id "
           "LEFT JOIN source_offer so ON so.offer_id = c.offer_id "
           # A feed reading "325 -> 300" without saying per WHAT leaves the reader
           # to assume the unit held still. That is exactly what may have moved.
           "LEFT JOIN selling_unit su ON su.selling_unit_id = so.selling_unit_id ")
    params: list = []
    if source_key is not None:
        sql += ("JOIN source_site ss ON ss.source_id = sp.source_id "
                "WHERE ss.source_key = ? ")
        params.append(source_key)
    sql += "ORDER BY c.change_event_id DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))

    from .reports import price_unit, region_name   # display-only resolution
    out = []
    for row in conn.execute(sql, params):
        item = dict(row)
        item["region"] = item.get("region") or ""
        item["region_name"] = region_name(item["region"])
        item["unit"] = price_unit(item.pop("unit_code", None),
                                  item.pop("basis_quantity", 1))
        _describe(item)
        out.append(item)
    return _collapse_new_pairs(out)


def _collapse_new_pairs(items: list[dict]) -> list[dict]:
    """Drop a first-seen VARIANT row that only repeats its product's row.

    Registering one record emits two events — product and variant — and for a
    source without option labels the variant one carries no name of its own, so
    the feed showed every new record twice, one of the pair labelled `variant`
    with nothing to add. Display-level only: both events stay stored. A variant
    event WITH its own label (a shop's "Red / Large") names something the
    product row does not, and stays.
    """
    said = {(item["source_product_id"], item.get("run_id"))
            for item in items
            if item.get("change_type") == "new"
            and item.get("field_key") == "source_product"}
    kept = []
    for item in items:
        if (item.get("change_type") == "new"
                and item.get("field_key") == "source_variant"
                and item.get("new_value") is None
                and (item.get("source_product_id"), item.get("run_id")) in said):
            continue
        kept.append(item)
    return kept


# What each stored field_key is CALLED on screen. The feed used to print the
# vocabulary raw — a reader met `source_variant` as a "field" with `None` on
# both sides, which states nothing. The stored keys never change (they are the
# vocabulary); only their names for humans live here.
_FIELD_LABELS = {
    "effective_price": "price",
    "availability": "availability",
    "source_product": "record",
    "source_variant": "variant",
}


def _describe(item: dict) -> None:
    """Attach display_* fields; the stored row is never altered.

    A 'new' event's meaning is "this thing was first seen", not a value moving
    from None to None — which is how the feed rendered it: two rows per new
    record, field names straight from the schema, dashes for both values.
    """
    item["field_label"] = _FIELD_LABELS.get(
        item.get("field_key") or "", (item.get("field_key") or "").replace("_", " "))
    kind = item.get("change_type")
    name = item.get("new_value") or item.get("product_name") or ""
    if kind == "new":
        item["display_previous"] = ""
        item["display_new"] = name
        item["display_change"] = "first seen"
        return
    previous, new = item.get("previous_value"), item.get("new_value")
    item["display_previous"] = "" if previous is None else str(previous)
    item["display_new"] = "" if new is None else str(new)
    item["display_change"] = ""
    try:
        before, after = float(previous), float(new)
        if before:
            # Absolute AND percent: "+2.05 (+10.0%)". Either alone makes the
            # reader compute the other in their head.
            item["display_change"] = (f"{after - before:+.2f} "
                                      f"({(after - before) / before * 100:+.1f}%)")
    except (TypeError, ValueError):
        pass                                    # words moved, not numbers


def changes_for_offer(conn: sqlite3.Connection, offer_id: int,
                      limit: int = 100) -> list[dict]:
    """Every change event that speaks about ONE offer, newest first (A8).

    Includes the parent variant/product 'new' events: "first seen" is part of
    this offer's story even though those rows carry no offer_id — they were
    recorded before the offer existed.
    """
    from .reports import price_unit, region_name

    rows = conn.execute(
        "SELECT c.*, sp.source_name AS product_name, so2.region AS region, "
        "       su.unit_code AS unit_code, so2.basis_quantity AS basis_quantity "
        "FROM change_event c "
        "LEFT JOIN source_product sp ON sp.source_product_id = c.source_product_id "
        "LEFT JOIN source_offer so2 ON so2.offer_id = c.offer_id "
        "LEFT JOIN selling_unit su ON su.selling_unit_id = so2.selling_unit_id "
        "WHERE c.offer_id = ? "
        "   OR (c.offer_id IS NULL AND c.source_variant_id = "
        "         (SELECT source_variant_id FROM source_offer WHERE offer_id = ?)) "
        "ORDER BY c.change_event_id DESC LIMIT ?",
        (offer_id, offer_id, max(1, min(limit, 500)))).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["region"] = item.get("region") or ""
        item["region_name"] = region_name(item["region"])
        item["unit"] = price_unit(item.pop("unit_code", None),
                                  item.pop("basis_quantity", 1))
        _describe(item)
        out.append(item)
    # Same collapse as the feed: the panel and the Changes page must agree.
    return _collapse_new_pairs(out)
