"""Retention policy and the always-preserve set (spec section 18).

This module decides WHICH observations a compaction carries forward. It never
touches a file and contains no DELETE against price_observation — the invariant
that the warehouse never rewrites its own history is not negotiable here.

The always-preserve set is enforced structurally: `carry_forward_sql` builds the
protected term itself and unions it into whatever the policy selects, so a caller
cannot compose a selection without it. Even `archive_only`, the most aggressive
setting available, still carries first, latest, minimum, maximum and every pin.

`protected_keys_independently` re-derives the same set in Python, deliberately
NOT sharing code with the SQL view. A compaction is verified by comparing the
two: if a view edit or a tie-breaking change ever made them disagree, they
disagree in the check rather than silently in the data.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

DEFAULT_KEY = "*"

KEEP_ALL = "keep_all"
DAILY_SUMMARY = "daily_summary"
WEEKLY_SUMMARY = "weekly_summary"
ARCHIVE_ONLY = "archive_only"

ACTIONS = {
    KEEP_ALL: "Keep everything (nothing is ever left behind)",
    DAILY_SUMMARY: "Keep one observation per day",
    WEEKLY_SUMMARY: "Keep one observation per week",
    ARCHIVE_ONLY: "Keep only the protected observations",
}

MIN_DETAIL_DAYS = 7


class PolicyError(ValueError):
    """An unusable policy, refused before it can be saved."""


@dataclass(frozen=True)
class Policy:
    source_key: str
    detail_days: int
    older_than_action: str
    excluded: bool = False

    @property
    def is_noop(self) -> bool:
        return self.excluded or self.older_than_action == KEEP_ALL


# ---- policies ----------------------------------------------------------------

def get_policies(conn: sqlite3.Connection) -> dict[str, Policy]:
    return {r["source_key"]: Policy(r["source_key"], r["detail_days"],
                                    r["older_than_action"], bool(r["excluded"]))
            for r in conn.execute(
                "SELECT source_key, detail_days, older_than_action, excluded "
                "FROM retention_policy")}


def policy_for(conn: sqlite3.Connection, source_key: str) -> Policy:
    """The policy in force for one dataset: its own, else the global default."""
    policies = get_policies(conn)
    default = policies.get(DEFAULT_KEY, Policy(DEFAULT_KEY, 3650, KEEP_ALL))
    own = policies.get(source_key)
    if own is None:
        return Policy(source_key, default.detail_days, default.older_than_action)
    return own


def save_policy(conn: sqlite3.Connection, source_key: str, *, detail_days: int,
                older_than_action: str, excluded: bool = False) -> Policy:
    if older_than_action not in ACTIONS:
        raise PolicyError(f"unknown retention action {older_than_action!r}; "
                          f"choose one of {sorted(ACTIONS)}")
    if int(detail_days) < MIN_DETAIL_DAYS:
        raise PolicyError(
            f"Keeping detailed history for fewer than {MIN_DETAIL_DAYS} days is "
            "refused: a week is the shortest window in which a price change is "
            "still legible.")
    conn.execute(
        "INSERT INTO retention_policy (source_key, detail_days, older_than_action, excluded) "
        "VALUES (?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET "
        "detail_days = excluded.detail_days, "
        "older_than_action = excluded.older_than_action, "
        "excluded = excluded.excluded, "
        "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')",
        (source_key, int(detail_days), older_than_action, 1 if excluded else 0))
    return Policy(source_key, int(detail_days), older_than_action, excluded)


def policy_digest(policies: dict[str, Policy]) -> str:
    """A fingerprint of the whole policy set.

    A preview is only allowed to authorise the compaction it actually measured;
    if any policy changed in between, the digests differ and the run is refused.
    """
    payload = sorted((p.source_key, p.detail_days, p.older_than_action, p.excluded)
                     for p in policies.values())
    return hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()


# ---- pins --------------------------------------------------------------------

def pin(conn: sqlite3.Connection, offer_id: int, business_date: str,
        record_hash: str, note: str = "") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO retention_pin (offer_id, business_date, record_hash, note) "
        "VALUES (?,?,?,?)", (offer_id, business_date, record_hash, note))


def unpin(conn: sqlite3.Connection, retention_pin_id: int) -> bool:
    """Remove a MARK. The observation it pointed at is untouched, as always."""
    cursor = conn.execute("DELETE FROM retention_pin WHERE retention_pin_id = ?",
                          (retention_pin_id,))
    return cursor.rowcount > 0


def list_pins(conn: sqlite3.Connection, source_key: str | None = None,
              limit: int = 200) -> list[dict]:
    sql = ("SELECT p.retention_pin_id, p.offer_id, p.business_date, p.record_hash, "
           "       p.note, p.pinned_at, ss.source_key, sp.source_name "
           "FROM retention_pin p "
           "JOIN source_offer so ON so.offer_id = p.offer_id "
           "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
           "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
           "JOIN source_site ss ON ss.source_id = sp.source_id ")
    params: list = []
    if source_key:
        sql += "WHERE ss.source_key = ? "
        params.append(source_key)
    sql += "ORDER BY p.pinned_at DESC LIMIT ?"
    params.append(max(1, min(limit, 1000)))
    return [dict(r) for r in conn.execute(sql, params)]


# ---- the protected set -------------------------------------------------------

Key = tuple[int, str, str]          # (offer_id, business_date, record_hash)


def protected_keys(conn: sqlite3.Connection) -> set[Key]:
    """The always-preserve set, straight from the view the selection uses."""
    return {(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT offer_id, business_date, record_hash FROM v_retention_protected")}


def protected_reasons(conn: sqlite3.Connection) -> dict[str, int]:
    return {r[0]: r[1] for r in conn.execute(
        "SELECT reason, COUNT(*) FROM v_retention_protected GROUP BY reason")}


def protected_keys_independently(conn: sqlite3.Connection) -> set[Key]:
    """The same set, derived a SECOND way — in Python, per offer.

    This intentionally duplicates the view's logic instead of calling it. A
    shared helper would hide exactly the class of bug this exists to catch: a
    view edited without its verification being edited too.
    """
    keys: set[Key] = set()
    offers = [r[0] for r in conn.execute("SELECT DISTINCT offer_id FROM price_observation")]
    for offer_id in offers:
        rows = conn.execute(
            "SELECT business_date, record_hash, observed_at, effective_price "
            "FROM price_observation WHERE offer_id = ?", (offer_id,)).fetchall()
        if not rows:
            continue
        earliest = min(r["observed_at"] for r in rows)
        latest = max(r["observed_at"] for r in rows)
        priced = [r for r in rows if r["effective_price"] is not None]
        cheapest = min((r["effective_price"] for r in priced), default=None)
        dearest = max((r["effective_price"] for r in priced), default=None)
        for row in rows:
            # Ties are kept, not broken: every row sharing an extreme is
            # protected. The view uses equality joins and does the same.
            if (row["observed_at"] in (earliest, latest)
                    or (row["effective_price"] is not None
                        and row["effective_price"] in (cheapest, dearest))):
                keys.add((offer_id, row["business_date"], row["record_hash"]))
    for row in conn.execute("SELECT offer_id, business_date, record_hash FROM retention_pin"):
        keys.add((row[0], row[1], row[2]))
    return keys


# ---- what a compaction carries forward ---------------------------------------

_PROTECTED_TERM = (
    "SELECT po.price_observation_id FROM price_observation po "
    "JOIN v_retention_protected v ON v.offer_id = po.offer_id "
    " AND v.business_date = po.business_date AND v.record_hash = po.record_hash"
)


def carry_forward_ids_sql(policies: dict[str, Policy], cutoffs: dict[str, str]) -> tuple[str, list]:
    """SQL yielding the price_observation_id of every row a compaction keeps.

    The protected term is unioned in HERE, by this function. There is no
    parameter that removes it, so no caller — present or future — can build a
    selection that drops a first, latest, minimum, maximum or pinned row.

    `cutoffs` maps source_key to the ISO date before which the policy's
    older-than action applies; it is passed in rather than computed so the
    caller owns "now" and tests are deterministic.
    """
    terms = [_PROTECTED_TERM]
    params: list = []
    for policy in policies.values():
        if policy.source_key == DEFAULT_KEY:
            continue
        cutoff = cutoffs.get(policy.source_key)
        if cutoff is None:
            continue
        if policy.is_noop:
            terms.append(_all_rows_for_source())
            params.append(policy.source_key)
            continue
        terms.append(_recent_rows_for_source())
        params.extend([policy.source_key, cutoff])
        if policy.older_than_action in (DAILY_SUMMARY, WEEKLY_SUMMARY):
            terms.append(_summary_rows_for_source(policy.older_than_action))
            params.extend([policy.source_key, cutoff])
        # archive_only adds no further term: the protected set is all that remains.
    return " UNION ".join(terms), params


def _source_join() -> str:
    return ("FROM price_observation po "
            "JOIN source_offer so ON so.offer_id = po.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id ")


def _all_rows_for_source() -> str:
    return f"SELECT po.price_observation_id {_source_join()} WHERE ss.source_key = ?"


def _recent_rows_for_source() -> str:
    return (f"SELECT po.price_observation_id {_source_join()} "
            "WHERE ss.source_key = ? AND po.business_date >= ?")


def _summary_rows_for_source(action: str) -> str:
    """One survivor per offer per day or per ISO week, for rows past the cutoff.

    The survivor is the LAST observation of its bucket, which is the one a
    reader would see as that day's or that week's price.
    """
    bucket = "po.business_date" if action == DAILY_SUMMARY else \
        "strftime('%Y-%W', po.business_date)"
    return (f"SELECT MAX(po.price_observation_id) {_source_join()} "
            "WHERE ss.source_key = ? AND po.business_date < ? "
            f"GROUP BY po.offer_id, {bucket}")


def sources_with_data(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT ss.source_key FROM source_site ss "
        "JOIN source_product sp ON sp.source_id = ss.source_id "
        "JOIN source_variant sv ON sv.source_product_id = sp.source_product_id "
        "JOIN source_offer so ON so.source_variant_id = sv.source_variant_id "
        "JOIN price_observation po ON po.offer_id = so.offer_id")]


def cutoff_dates(conn: sqlite3.Connection, today: str) -> dict[str, str]:
    """source_key -> the business_date before which its policy's action applies."""
    from datetime import date, timedelta

    base = date.fromisoformat(today)
    out = {}
    for source_key in sources_with_data(conn):
        policy = policy_for(conn, source_key)
        out[source_key] = (base - timedelta(days=policy.detail_days)).isoformat()
    return out


def effective_policies(conn: sqlite3.Connection) -> dict[str, Policy]:
    """The policy actually applied to each dataset that holds data."""
    return {key: policy_for(conn, key) for key in sources_with_data(conn)}


# ---- derived rows that CAN be pruned in place --------------------------------

# change_event and job_log_entry carry no append-only trigger and nothing
# references them, so removing old ones destroys no history and reclaims space
# without touching a file.
#
# crawl_run is deliberately NOT in this list: price_observation.run_id is a
# NOT NULL foreign key into it (schema.sql:206), so pruning crawl_run would
# orphan the very table this whole design exists to protect.
PRUNABLE = {
    "change_event": "detected_at",
    "job_log_entry": "logged_at",
}


def prunable_counts(conn: sqlite3.Connection, before_date: str) -> dict[str, int]:
    counts = {}
    for table, column in PRUNABLE.items():
        try:
            counts[table] = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} < ?", (before_date,)
            ).fetchone()[0]
        except sqlite3.OperationalError:
            counts[table] = 0
    return counts


def prune_derived(conn: sqlite3.Connection, before_date: str) -> dict[str, int]:
    """Remove old derived rows. Never touches price_observation.

    Safe while the observations behind these rows are still present: a change
    event is recomputable from the two observations either side of it. After a
    summarising compaction has left some of those observations behind, it is
    not — which is why the interface states the ordering rather than hiding it.
    """
    removed = {}
    for table, column in PRUNABLE.items():
        try:
            cursor = conn.execute(f"DELETE FROM {table} WHERE {column} < ?", (before_date,))
            removed[table] = cursor.rowcount
        except sqlite3.OperationalError:
            removed[table] = 0
    return removed
