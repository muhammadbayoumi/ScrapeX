"""Spec 18: retention policy and the always-preserve set.

The load-bearing guarantee under test: no policy, however aggressive, can drop
an offer's first, latest, cheapest or dearest observation, or anything pinned.
"""
from __future__ import annotations

import pytest

from scrapex import db as dbmod
from scrapex import retention
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row

SOURCE = "ELSEWEDYSHOP"

# A year of prices for one offer, deliberately shaped so the extremes are in the
# middle: a policy that keeps only recent rows would lose both without the
# protected set.
HISTORY = [
    ("2026-01-05", "100.00"),
    ("2026-02-05", "40.00"),     # the cheapest, long past any cutoff
    ("2026-03-05", "110.00"),
    ("2026-04-05", "900.00"),    # the dearest, also long past
    ("2026-05-05", "120.00"),
    ("2026-06-05", "130.00"),
    ("2026-07-05", "140.00"),
]
TODAY = "2026-07-19"


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(c)
    entry = make_entry()
    for date, price in HISTORY:
        ingest_payloads(c, entry, [make_payload(
            [one_row(effective_price=price)], scraped_at=f"{date}T10:00:00Z")])
    c.commit()
    try:
        yield c
    finally:
        c.close()


def kept_ids(conn, action: str, detail_days: int = 30) -> set[int]:
    retention.save_policy(conn, SOURCE, detail_days=detail_days, older_than_action=action)
    policies = retention.effective_policies(conn)
    cutoffs = retention.cutoff_dates(conn, TODAY)
    sql, params = retention.carry_forward_ids_sql(policies, cutoffs)
    return {r[0] for r in conn.execute(sql, params)}


def prices_of(conn, ids: set[int]) -> set[float]:
    if not ids:
        return set()
    holes = ", ".join("?" for _ in ids)
    return {r[0] for r in conn.execute(
        f"SELECT effective_price FROM price_observation WHERE price_observation_id IN ({holes})",
        list(ids))}


# ---- the observations actually landed ---------------------------------------

def test_the_fixture_really_holds_a_year_of_prices(conn):
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == len(HISTORY)


# ---- policies ----------------------------------------------------------------

def test_the_shipped_default_changes_nothing(conn):
    """A migration that started deleting history on install would be indefensible."""
    default = retention.get_policies(conn)[retention.DEFAULT_KEY]
    assert default.older_than_action == retention.KEEP_ALL and default.is_noop


def test_a_dataset_without_its_own_policy_inherits_the_default(conn):
    assert retention.policy_for(conn, SOURCE).older_than_action == retention.KEEP_ALL


def test_an_unknown_action_is_refused(conn):
    with pytest.raises(retention.PolicyError, match="unknown retention action"):
        retention.save_policy(conn, SOURCE, detail_days=30, older_than_action="burn_it")


def test_an_absurdly_short_window_is_refused_with_the_reason(conn):
    with pytest.raises(retention.PolicyError, match="shortest window"):
        retention.save_policy(conn, SOURCE, detail_days=1,
                              older_than_action=retention.ARCHIVE_ONLY)


def test_the_digest_changes_when_any_policy_changes(conn):
    before = retention.policy_digest(retention.get_policies(conn))
    retention.save_policy(conn, SOURCE, detail_days=90,
                          older_than_action=retention.DAILY_SUMMARY)
    assert retention.policy_digest(retention.get_policies(conn)) != before


# ---- the always-preserve set -------------------------------------------------

def test_the_most_aggressive_policy_still_carries_first_and_latest(conn):
    kept = prices_of(conn, kept_ids(conn, retention.ARCHIVE_ONLY))
    assert 100.0 in kept, "the first observation was dropped"
    assert 140.0 in kept, "the latest observation was dropped"


def test_the_most_aggressive_policy_still_carries_the_extremes(conn):
    kept = prices_of(conn, kept_ids(conn, retention.ARCHIVE_ONLY))
    assert 40.0 in kept, "the cheapest price was dropped"
    assert 900.0 in kept, "the dearest price was dropped"


def test_a_pinned_observation_survives_archive_only(conn):
    row = conn.execute(
        "SELECT offer_id, business_date, record_hash, price_observation_id "
        "FROM price_observation WHERE effective_price = 110.0").fetchone()
    retention.pin(conn, row[0], row[1], row[2], note="the day the tender closed")
    assert row[3] in kept_ids(conn, retention.ARCHIVE_ONLY)


def test_unpinning_removes_the_mark_and_not_the_observation(conn):
    row = conn.execute("SELECT offer_id, business_date, record_hash FROM price_observation "
                       "WHERE effective_price = 110.0").fetchone()
    retention.pin(conn, row[0], row[1], row[2])
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    pin_id = conn.execute("SELECT retention_pin_id FROM retention_pin").fetchone()[0]
    assert retention.unpin(conn, pin_id) is True
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == before


def test_the_two_protected_set_derivations_agree(conn):
    """The view and the independent Python derivation must never disagree —
    that is the whole point of having two."""
    assert retention.protected_keys(conn) == retention.protected_keys_independently(conn)


def test_the_protected_set_explains_itself_by_reason(conn):
    reasons = retention.protected_reasons(conn)
    assert set(reasons) >= {"first", "latest", "minimum", "maximum"}


# ---- what each action actually keeps -----------------------------------------

def test_keep_all_keeps_literally_everything(conn):
    assert len(kept_ids(conn, retention.KEEP_ALL)) == len(HISTORY)


def test_archive_only_keeps_less_than_keep_all(conn):
    aggressive = kept_ids(conn, retention.ARCHIVE_ONLY)
    assert 0 < len(aggressive) < len(HISTORY)


def test_recent_history_inside_the_window_is_always_kept(conn):
    """detail_days is a promise about recent data, not a suggestion."""
    kept = prices_of(conn, kept_ids(conn, retention.ARCHIVE_ONLY, detail_days=200))
    assert {100.0, 110.0, 120.0, 130.0, 140.0, 40.0, 900.0} <= kept


def test_an_excluded_dataset_is_never_touched(conn):
    retention.save_policy(conn, SOURCE, detail_days=30,
                          older_than_action=retention.ARCHIVE_ONLY, excluded=True)
    policies = retention.effective_policies(conn)
    cutoffs = retention.cutoff_dates(conn, TODAY)
    sql, params = retention.carry_forward_ids_sql(policies, cutoffs)
    assert len({r[0] for r in conn.execute(sql, params)}) == len(HISTORY)


# ---- derived rows that may be pruned -----------------------------------------

def test_crawl_run_is_not_prunable(conn):
    """price_observation.run_id is a NOT NULL foreign key into crawl_run, so
    pruning runs would orphan the very table retention exists to protect."""
    assert "crawl_run" not in retention.PRUNABLE


def test_pruning_derived_rows_never_touches_observations(conn):
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    retention.prune_derived(conn, "2026-06-01")
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == before


def test_pruning_removes_the_old_change_events_it_counted(conn):
    counts = retention.prunable_counts(conn, "2026-06-01")
    removed = retention.prune_derived(conn, "2026-06-01")
    assert removed["change_event"] == counts["change_event"]
    assert conn.execute(
        "SELECT COUNT(*) FROM change_event WHERE detected_at < '2026-06-01'"
    ).fetchone()[0] == 0


# ---- the invariant itself ----------------------------------------------------

def test_the_append_only_triggers_still_refuse_a_delete(conn):
    """If this ever passes, retention has quietly become deletion."""
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM price_observation")


def test_retention_contains_no_delete_against_observations():
    from pathlib import Path

    source = Path(retention.__file__).read_text(encoding="utf-8")
    assert "DELETE FROM price_observation" not in source
