"""A record card finds its change events by index, not by reading all of them.

MEASURED ON A COPY OF HIS WAREHOUSE, 2026-10-03 (#1206): `changes_for_offer` read all
173,742 change events for every card, because no index covered `offer_id` or
`source_variant_id`. That is about 43 ms a card on `/api/offer`, and 90-95% of the
light file's build. Migration 0021 adds the two indexes. This holds the query to them,
by asking SQLite how it plans the very statement the function runs, so a rename of
either column, a rewrite of the WHERE, or a lost index all fail here rather than as a
slow card on his machine.
"""
from __future__ import annotations

from pathlib import Path

from scrapex import changes
from scrapex import db as dbmod


def _plan_of_changes_for_offer(tmp_path: Path) -> list[str]:
    """The query plan of the statement `changes_for_offer` runs, on a migrated warehouse."""
    conn = dbmod.connect(tmp_path / "warehouse.db")
    try:
        dbmod.migrate(conn)
        ran: list[str] = []
        conn.set_trace_callback(ran.append)
        changes.changes_for_offer(conn, 1)
        conn.set_trace_callback(None)
        statement = next(sql for sql in ran if "FROM change_event c" in sql)
        return [row[-1] for row in conn.execute("EXPLAIN QUERY PLAN " + statement)]
    finally:
        conn.close()


def test_a_card_reads_its_changes_by_index_and_never_scans_them(tmp_path):
    """If this fails, every record card reads every change event the warehouse holds:
    173,742 of them on his, for each card."""
    plan = _plan_of_changes_for_offer(tmp_path)

    assert not any(step.startswith("SCAN c") for step in plan), plan
    assert any("ix_change_event_offer" in step for step in plan), plan
    assert any("ix_change_event_variant" in step for step in plan), plan
