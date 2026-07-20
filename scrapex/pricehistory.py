"""Deriving the price timeline from the evidence (spec: price-history semantics).

`price_observation` is the evidence: append-only, never rewritten. This module
builds the three layers the owner actually reads from it —

    offer_state     what it costs now, and whether it can be bought
    price_period    one row per continuous confirmed price
    absence_period  when it stopped being seen, and when it came back

— and every one of them is REBUILDABLE. That is the whole reason they are
allowed to be mutable while the evidence beneath them is not: none of them is a
source of truth, so a bug here costs a rebuild rather than a history.

Rebuilding is also how existing warehouses get their timeline. Databases written
before this migration hold one observation per crawl, including runs where
nothing moved; `rebuild` collapses each run of equal price keys into a single
period. It deletes no observation and never could — the schema triggers forbid
touching them.
"""
from __future__ import annotations

import sqlite3

from . import pricekey

# Rows written before migration 0015 carry no price_hash. Their key is unknown,
# not empty: they are folded into whatever period surrounds them rather than
# being treated as a distinct price.
UNKNOWN_KEY = ""


def _observations(conn: sqlite3.Connection, offer_id: int) -> list[sqlite3.Row]:
    """Every observation for one offer, oldest first.

    The tie-break matters: one crawl stamps every row with the same observed_at,
    so ordering by time alone leaves the sequence undefined and a rebuild would
    produce a different timeline each run.
    """
    return conn.execute(
        "SELECT price_observation_id, observed_at, business_date, effective_price, "
        "       regular_price, sale_price, currency, vat_included, availability, "
        "       stock_quantity, price_hash, price_fields "
        "FROM price_observation WHERE offer_id = ? "
        "ORDER BY observed_at, price_observation_id",
        (offer_id,),
    ).fetchall()


def _same_price(previous: sqlite3.Row, current: sqlite3.Row) -> tuple[bool, str]:
    """Is `current` a continuation of `previous`? Plus why, when it is not.

    Two keys built from different field sets cannot be compared: the later one
    may include a manufacturer the earlier never had. That is the source
    publishing more, not the price moving — a distinction that decides whether
    the owner sees a price change.
    """
    old_hash = previous["price_hash"] or UNKNOWN_KEY
    new_hash = current["price_hash"] or UNKNOWN_KEY
    if not old_hash or not new_hash:
        # Pre-0015 evidence. Fall back to the number itself: it is the only
        # comparable thing those rows carry.
        return previous["effective_price"] == current["effective_price"], "price_change"

    old_fields = pricekey.parse_fields(previous["price_fields"])
    new_fields = pricekey.parse_fields(current["price_fields"])
    if not pricekey.comparable(old_fields, new_fields):
        return False, "fields_changed"
    return old_hash == new_hash, "price_change"


def rebuild_offer(conn: sqlite3.Connection, offer_id: int) -> int:
    """Rebuild one offer's periods and state. Returns the number of periods.

    Idempotent: running it twice produces the same rows, because it derives
    everything from the evidence rather than from what it found last time.
    """
    conn.execute("DELETE FROM price_period WHERE offer_id = ?", (offer_id,))
    rows = _observations(conn, offer_id)
    if not rows:
        conn.execute("DELETE FROM offer_state WHERE offer_id = ?", (offer_id,))
        return 0

    periods = 0
    open_period: sqlite3.Row | None = None
    open_id: int | None = None
    reason = "first_seen"

    for row in rows:
        if open_period is not None:
            continues, why = _same_price(open_period, row)
            if continues:
                conn.execute(
                    "UPDATE price_period SET last_confirmed_at = ? WHERE price_period_id = ?",
                    (row["observed_at"], open_id))
                continue
            conn.execute(
                "UPDATE price_period SET closed_at = ? WHERE price_period_id = ?",
                (row["observed_at"], open_id))
            reason = why

        cursor = conn.execute(
            "INSERT INTO price_period (offer_id, price_hash, price_fields, "
            " effective_price, regular_price, sale_price, currency, vat_included, "
            " first_detected_at, last_confirmed_at, opened_because) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (offer_id, row["price_hash"] or UNKNOWN_KEY, row["price_fields"] or "",
             row["effective_price"], row["regular_price"], row["sale_price"],
             row["currency"], row["vat_included"], row["observed_at"],
             row["observed_at"], reason))
        open_id = int(cursor.lastrowid)
        open_period = row
        periods += 1
        reason = "price_change"

    latest = rows[-1]
    conn.execute(
        "INSERT INTO offer_state (offer_id, effective_price, currency, availability, "
        " stock_quantity, price_hash, price_fields, last_confirmed_at, last_seen_at, "
        " first_seen_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
        "ON CONFLICT(offer_id) DO UPDATE SET "
        " effective_price = excluded.effective_price, currency = excluded.currency, "
        " availability = excluded.availability, stock_quantity = excluded.stock_quantity, "
        " price_hash = excluded.price_hash, price_fields = excluded.price_fields, "
        " last_confirmed_at = excluded.last_confirmed_at, "
        " last_seen_at = excluded.last_seen_at, first_seen_at = excluded.first_seen_at, "
        " updated_at = excluded.updated_at",
        (offer_id, latest["effective_price"], latest["currency"], latest["availability"],
         latest["stock_quantity"], latest["price_hash"], latest["price_fields"],
         latest["observed_at"], latest["observed_at"], rows[0]["observed_at"]))
    return periods


def rebuild_all(conn: sqlite3.Connection, source_key: str | None = None) -> dict:
    """Rebuild every offer's timeline, optionally for one source only.

    This is how a warehouse written before the price layers existed gets one:
    the evidence was always there, only the reading of it is new.
    """
    sql = ("SELECT DISTINCT po.offer_id FROM price_observation po "
           "JOIN source_offer so ON so.offer_id = po.offer_id "
           "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
           "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
           "JOIN source_site ss ON ss.source_id = sp.source_id")
    params: tuple = ()
    if source_key:
        sql += " WHERE ss.source_key = ?"
        params = (source_key,)

    offers = [r[0] for r in conn.execute(sql, params)]
    periods = sum(rebuild_offer(conn, offer_id) for offer_id in offers)
    return {"offers": len(offers), "periods": periods}


# ---- reading the timeline ----------------------------------------------------

def timeline(conn: sqlite3.Connection, offer_id: int, limit: int = 500) -> list[dict]:
    """The change-only history: the first price and each real change.

    Daily unchanged confirmations do not appear. That is the point — the owner
    asked for a timeline of price changes, not a copy of an unchanged row per
    crawl.
    """
    return [dict(r) for r in conn.execute(
        "SELECT price_period_id, price_hash, price_fields, effective_price, "
        "       regular_price, sale_price, currency, vat_included, "
        "       first_detected_at, last_confirmed_at, closed_at, opened_because "
        "FROM price_period WHERE offer_id = ? "
        "ORDER BY first_detected_at, price_period_id LIMIT ?",
        (offer_id, max(1, min(limit, 1000))))]


def price_on(conn: sqlite3.Connection, offer_id: int, on_date: str) -> dict:
    """The price on a given date, saying plainly when it is not known.

    The spec is explicit that an unconfirmed date must NOT be answered by
    assuming the previous price held: it returns the last known price together
    with the date it was actually observed, and says the requested date has no
    reliable observation.
    """
    covering = conn.execute(
        "SELECT effective_price, currency, first_detected_at, last_confirmed_at "
        "FROM price_period WHERE offer_id = ? "
        "  AND date(first_detected_at) <= date(?) "
        "  AND date(last_confirmed_at) >= date(?) "
        "ORDER BY first_detected_at DESC LIMIT 1",
        (offer_id, on_date, on_date)).fetchone()
    if covering is not None:
        return {"status": "confirmed", "date": on_date,
                "effective_price": covering["effective_price"],
                "currency": covering["currency"],
                "observed_at": covering["last_confirmed_at"],
                "detail": "A successful run confirmed this price on that date."}

    earliest = conn.execute(
        "SELECT MIN(first_detected_at) FROM price_period WHERE offer_id = ?",
        (offer_id,)).fetchone()[0]
    if earliest is None:
        return {"status": "no_history", "date": on_date, "effective_price": None,
                "currency": None, "observed_at": None,
                "detail": "Nothing has ever been recorded for this offer."}
    if on_date < earliest[:10]:
        return {"status": "before_tracking", "date": on_date, "effective_price": None,
                "currency": None, "observed_at": earliest,
                "detail": f"Tracking began on {earliest[:10]}; there is nothing earlier."}

    previous = conn.execute(
        "SELECT effective_price, currency, last_confirmed_at FROM price_period "
        "WHERE offer_id = ? AND date(first_detected_at) <= date(?) "
        "ORDER BY first_detected_at DESC LIMIT 1",
        (offer_id, on_date)).fetchone()
    if previous is None:
        return {"status": "unknown", "date": on_date, "effective_price": None,
                "currency": None, "observed_at": None,
                "detail": "There is no reliable observation on or before that date."}
    return {"status": "last_known", "date": on_date,
            "effective_price": previous["effective_price"],
            "currency": previous["currency"],
            "observed_at": previous["last_confirmed_at"],
            "detail": ("No reliable observation exists for that date. This is the "
                       f"last known price, observed on {previous['last_confirmed_at'][:10]}.")}
