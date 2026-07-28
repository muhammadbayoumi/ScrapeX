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
    """Every observation WE made for one offer, oldest first.

    The tie-break matters: one crawl stamps every row with the same observed_at,
    so ordering by time alone leaves the sequence undefined and a rebuild would
    produce a different timeline each run.

    Reported rows are excluded by design: the derived timeline is the record of
    what ScrapeX watched happen (owner rule: real changes only). A publisher's
    backfilled anchor sits in the same table for display and analysis, but
    letting it open and close periods would let someone else's dating write our
    history.
    """
    return conn.execute(
        "SELECT price_observation_id, observed_at, business_date, effective_price, "
        "       regular_price, sale_price, currency, vat_included, availability, "
        "       stock_quantity, price_hash, price_fields "
        "FROM price_observation WHERE offer_id = ? AND provenance = 'observed' "
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
    if old_hash == new_hash:
        return True, "price_change"
    if (previous["currency"] or "") != (current["currency"] or ""):
        # Same field set, different currency: the two amounts are incomparable,
        # so the new period opens for a currency flip, not a price move — the
        # distinction decides what the owner is told happened (0030).
        return False, "currency_change"
    return False, "price_change"


def rebuild_offer(conn: sqlite3.Connection, offer_id: int) -> int:
    """Rebuild one offer's periods and state. Returns the number of periods.

    Idempotent: running it twice produces the same rows, because the SHAPE of
    the timeline — where each period begins and ends — is derived entirely from
    the evidence.

    One thing is NOT derivable and is preserved rather than recomputed:
    `last_confirmed_at`. A refresh that finds an unchanged price appends no
    observation, by design — the history is a timeline of changes, not a daily
    copy — so the evidence cannot say a price was still true last Tuesday. That
    fact is written at run finalisation and would be destroyed by a naive
    rebuild, quietly rolling every confirmation back to the last time the price
    actually moved.

    That protection used to cover only the OPEN period, which is exactly the
    naive case it warns about wearing a different hat: while a period stayed
    open, offer_state held its confirmation and handed it back; the moment the
    period CLOSED, its confirmation reverted to the last observation that
    continued it. Every genuine price change therefore destroyed the proof that
    the old price had been true through the quiet days before it. Every
    period's confirmation is now carried across the rebuild, not just the last
    one's.
    """
    held = conn.execute(
        "SELECT last_confirmed_at FROM offer_state WHERE offer_id = ?",
        (offer_id,)).fetchone()
    confirmed_through = held["last_confirmed_at"] if held else None
    # EVERY period's confirmation is preserved, not just the open one's.
    #
    # A refresh that finds an unchanged price appends no observation — that is
    # the design, the history is a timeline of changes — so a confirmation is
    # written onto the open period's row (ingest._confirm_seen) and NOWHERE
    # else. Rebuilding from observations alone therefore cannot re-derive it,
    # and the rebuild deletes the only copy. While a period stayed open the
    # damage was invisible, because offer_state carries the latest confirmation
    # and it was handed back below. The moment a period CLOSED, its
    # last_confirmed_at silently reverted to the last observation that
    # continued it: proof that the price was still true through every quiet day
    # in between, destroyed on the first real price change and unrecoverable.
    prior = {(r["price_hash"], r["first_detected_at"]): r["last_confirmed_at"]
             for r in conn.execute(
                 "SELECT price_hash, first_detected_at, last_confirmed_at "
                 "FROM price_period WHERE offer_id = ?", (offer_id,))}
    # (price_hash, first_detected_at) is a sound key across a rebuild: both are
    # derived deterministically from the same observations, so the same period
    # reappears under the same key. A pre-0015 row with no hash is still told
    # apart by the moment it opened.
    conn.execute("DELETE FROM price_period WHERE offer_id = ?", (offer_id,))
    rows = _observations(conn, offer_id)
    if not rows:
        conn.execute("DELETE FROM offer_state WHERE offer_id = ?", (offer_id,))
        return 0

    def confirmed_for(row: sqlite3.Row) -> str:
        """What this period was last known to be true, evidence and record."""
        return max(row["observed_at"],
                   prior.get((row["price_hash"] or UNKNOWN_KEY, row["observed_at"]), ""))

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
                    (max(row["observed_at"], confirmed_for(open_period)), open_id))
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
             confirmed_for(row), reason))
        open_id = int(cursor.lastrowid)
        open_period = row
        periods += 1
        reason = "price_change"

    latest = rows[-1]
    # offer_state carries the LATEST confirmation, which belongs to whichever
    # period is open now. Taken as a max against what the open period already
    # holds, so this can only ever move a confirmation forward: the period may
    # already carry a later one preserved above, and overwriting it here would
    # reintroduce the very loss this function now guards against.
    confirmed_at = max(latest["observed_at"], confirmed_through or "",
                       confirmed_for(open_period) if open_period is not None else "")
    if open_id is not None:
        conn.execute(
            "UPDATE price_period SET last_confirmed_at = ? "
            "WHERE price_period_id = ? AND last_confirmed_at < ?",
            (confirmed_at, open_id, confirmed_at))
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
         confirmed_at, confirmed_at, rows[0]["observed_at"]))
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
