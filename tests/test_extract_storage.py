"""Persistent generic records, approval safety, recovery, and coexistence tests."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import (
    CandidateApproval, CandidateNotApprovable, SnapshotCreate,
)
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row


TABLE_HTML = """
<table id="city-report">
  <caption>City report</caption>
  <thead><tr><th>City</th><th>Population</th><th>Coastal</th></tr></thead>
  <tbody>
    <tr><td>الرياض</td><td>7000000</td><td>No</td></tr>
    <tr><td>Jeddah</td><td>4700000</td><td>Yes</td></tr>
  </tbody>
</table>
"""


@pytest.fixture()
def databases(tmp_path: Path):
    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    return registry


@pytest.fixture()
def conn(databases: DatabaseRegistry):
    connection = databases.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def save(conn, html: str = TABLE_HTML, url: str = "https://example.com/report"):
    return service.save_snapshot(
        conn, SnapshotCreate(source_url=url, html_content=html)
    )


def approval(candidate, identity: set[str] | None = None):
    identity = identity or {candidate.fields[0].field_key}
    return CandidateApproval(
        table_index=candidate.table_index,
        site_key="example_site",
        site_display_name="Example site",
        dataset_key="city_report",
        dataset_name="City report",
        fields=[
            {
                "field_key": field.field_key,
                "display_name": field.source_name,
                "data_type": field.data_type,
                "identity": field.field_key in identity,
            }
            for field in candidate.fields
        ],
    )


def test_the_generic_storage_and_its_immutable_evidence_are_present(conn):
    """RENAMED FROM test_general_0002_adds_generic_storage_and_immutable_evidence.

    The version number moved and the objects did not. The generic stream reached
    this shape at its v3; the engine's schema carries the same tables and the
    same triggers at v1, because db/engine/schema.sql is DERIVED from that
    stream rather than replaying it. Asserting the number would now be asserting
    which migration happened to introduce them — history, not a guarantee. What
    has to stay true is that they are here.
    """
    from scrapex.databases.domain import EngineDatabase
    assert dbmod.schema_version(conn) == EngineDatabase(":memory:").latest_schema_version
    objects = {
        row["name"]: row["type"]
        for row in conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('table','trigger') LIMIT 500"
        )
    }
    assert objects["generic_page_snapshot"] == "table"
    assert objects["dataset_schema_version"] == "table"
    assert objects["generic_record"] == "table"
    assert objects["generic_record_revision"] == "table"
    assert objects["generic_ingestion"] == "table"
    assert objects["trg_generic_page_snapshot_immutable_update"] == "trigger"
    assert objects["trg_generic_record_revision_append_only_delete"] == "trigger"
    # `assert "trg_price_obs_no_update" not in objects` stood here and was the
    # point of the split: the generic database was proved to carry NO price
    # machinery. One database inverts it — the price trigger is expected now,
    # and its ABSENCE would mean the derived schema dropped half of itself.
    assert objects["trg_price_obs_no_update"] == "trigger"

    snapshot = save(conn)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(
            "UPDATE generic_page_snapshot SET html_content='changed' "
            "WHERE page_snapshot_id=?",
            (snapshot["page_snapshot_id"],),
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute(
            "DELETE FROM generic_page_snapshot WHERE page_snapshot_id=?",
            (snapshot["page_snapshot_id"],),
        )


def test_legacy_0014_remains_available_for_explicit_unified_sessions(tmp_path: Path):
    legacy = dbmod.connect(tmp_path / "legacy.db")
    try:
        dbmod.migrate(legacy)
        assert dbmod.schema_version(legacy) == 61   # +0061 the weight the price is quoted against
        for table in ("price_observation", "generic_record"):
            assert legacy.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
                (table,),
            ).fetchone() is not None
    finally:
        legacy.close()


def test_generic_records_and_price_rows_land_in_the_same_database(tmp_path: Path):
    """REPLACES test_split_moves_existing_g2_records_to_general_and_keeps_prices
    _in_marketlens, which asserted the exact opposite and was right to, until M5.

    That test proved the two kinds of data ended up in DIFFERENT files and that
    neither file carried the other's tables. One database inverts it: the point
    now is that both survive together, in one place, with no ATTACH and no
    second connection. The assertion is kept rather than dropped because what it
    was really protecting — that approving a candidate does not lose the price
    history, and ingesting prices does not lose the records — is unchanged.
    """
    engine = EngineDatabase(tmp_path / "scrapex-engine.db")
    engine.initialize()

    conn = engine.connect()
    try:
        snapshot = save(conn)
        candidate = service._candidate(
            conn, service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0)
        service.approve_candidate(
            conn, snapshot["page_snapshot_id"], approval(candidate))
        ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
        conn.commit()

        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("generic_page_snapshot", "generic_record",
                          "generic_record_revision", "price_observation")
        }
    finally:
        conn.close()

    assert counts == {"generic_page_snapshot": 1, "generic_record": 2,
                      "generic_record_revision": 2, "price_observation": 1}


def test_discovery_returns_candidates_without_polluting_permanent_datasets(conn):
    snapshot = save(conn)

    result = service.discover_snapshot(conn, snapshot["page_snapshot_id"])

    assert result["candidates"][0]["name"] == "City report"
    for table in (
        "site_profile", "dataset_definition", "field_definition",
        "dataset_schema_version", "generic_record", "generic_ingestion",
    ):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} LIMIT 1").fetchone()[0] == 0


def test_owner_approval_atomically_creates_schema_and_typed_generic_records(conn):
    snapshot = save(conn)
    candidate = service._candidate(
        conn, service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0
    )

    result = service.approve_candidate(
        conn, snapshot["page_snapshot_id"], approval(candidate)
    )
    conn.commit()
    page = service.browse_records(conn, result["dataset_definition_id"], limit=1)

    assert result["record_count"] == 2
    assert result["recovered"] is False
    assert [field["field_key"] for field in page["fields"]] == [
        "city", "population", "coastal",
    ]
    assert page["fields"][0]["identity"] is True
    assert page["records"][0]["data"] == {
        "city": "الرياض", "population": 7000000, "coastal": False,
    }
    assert page["next_after_id"] is not None
    stored = conn.execute(
        "SELECT source_locator, data_json FROM generic_record "
        "WHERE generic_record_id=? LIMIT 1",
        (page["records"][0]["generic_record_id"],),
    ).fetchone()
    assert stored["source_locator"] == "table#city-report::row(1)"
    assert json.loads(stored["data_json"])["population"] == 7000000
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision LIMIT 1"
    ).fetchone()[0] == 2


def test_failed_identity_approval_rolls_back_and_a_corrected_retry_recovers(
    conn, databases: DatabaseRegistry,
):
    html = """
    <table><tr><th>Region</th><th>Code</th></tr>
      <tr><td>North</td><td>N-1</td></tr>
      <tr><td>North</td><td>N-2</td></tr>
    </table>
    """
    snapshot = save(conn, html)
    candidate = service._candidate(
        conn, service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0
    )

    with pytest.raises(CandidateNotApprovable, match="duplicate record keys"):
        service.approve_candidate(
            conn, snapshot["page_snapshot_id"], approval(candidate, {"region"})
        )
    assert conn.execute(
        "SELECT COUNT(*) FROM dataset_definition LIMIT 1"
    ).fetchone()[0] == 0
    with closing(databases.engine.connect()) as marketlens:
        assert marketlens.execute(
            "SELECT COUNT(*) FROM price_observation LIMIT 1"
        ).fetchone()[0] == 0

    recovered = service.approve_candidate(
        conn, snapshot["page_snapshot_id"], approval(candidate, {"code"})
    )
    conn.commit()
    assert recovered["record_count"] == 2


def test_retry_after_a_lost_success_response_is_idempotent(conn):
    snapshot = save(conn)
    candidate = service._candidate(
        conn, service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0
    )
    request = approval(candidate)
    first = service.approve_candidate(conn, snapshot["page_snapshot_id"], request)
    conn.commit()

    second = service.approve_candidate(conn, snapshot["page_snapshot_id"], request)
    conn.commit()

    assert second["dataset_definition_id"] == first["dataset_definition_id"]
    assert second["recovered"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_ingestion LIMIT 1"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision LIMIT 1"
    ).fetchone()[0] == 2


def test_later_snapshot_updates_current_record_and_appends_revision(conn):
    first_snapshot = save(conn)
    first_candidate = service._candidate(
        conn, service._snapshot_row(conn, first_snapshot["page_snapshot_id"]), 0
    )
    request = approval(first_candidate)
    first = service.approve_candidate(
        conn, first_snapshot["page_snapshot_id"], request
    )
    conn.commit()
    changed_html = TABLE_HTML.replace("7000000", "7100000")
    next_snapshot = save(conn, changed_html, "https://example.com/report?page=2")

    service.approve_candidate(conn, next_snapshot["page_snapshot_id"], request)
    conn.commit()
    page = service.browse_records(conn, first["dataset_definition_id"])

    assert page["records"][0]["data"]["population"] == 7100000
    # THREE, NOT FOUR, AND THIS ASSERTION USED TO SAY FOUR. Two rows were approved,
    # then ONE value changed. `R-20`: an unchanged row is confirmed, not
    # re-recorded — so the second approval appends one revision, not two. The old
    # expectation encoded the defect that produced 34,550 revisions for 11,059
    # contractors.
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision LIMIT 1"
    ).fetchone()[0] == 3
    # And it is the CHANGED row that gained the history, which a total cannot show.
    per_record = dict(conn.execute(
        "SELECT generic_record_id, COUNT(*) FROM generic_record_revision "
        " GROUP BY generic_record_id"))
    assert sorted(per_record.values()) == [1, 2], (
        f"one row changed and one did not: {per_record}")
    # Both rows were SEEN, though, and `last_seen_at` is where a confirmation goes.
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_record WHERE status = 'active'"
    ).fetchone()[0] == 2
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_ingestion LIMIT 1"
    ).fetchone()[0] == 2


def test_generic_ingestion_and_price_ingestion_share_one_database(
    databases: DatabaseRegistry,
):
    """REPLACES test_generic_ingestion_and_price_ingestion_stay_in_separate_
    databases, which asserted the exact opposite — and was right to, until M5.

    It proved each file REFUSED the other's tables: reading price_observation
    out of the generic database raised "no such table", and generic_record was
    absent from the price one. That was the whole point of the split, and it is
    the whole point of the collapse that it is no longer true.

    The guarantee worth keeping is underneath it: approving a candidate and
    ingesting prices are independent, and neither loses the other's rows. Two
    files used to enforce that by construction. Nothing enforces it now except
    this test, which is why it is kept rather than deleted.
    """
    with closing(databases.engine.connect()) as conn:
        snapshot = save(conn)
        candidate = service._candidate(
            conn, service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0)
        service.approve_candidate(
            conn, snapshot["page_snapshot_id"], approval(candidate))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM generic_record").fetchone()[0] == 2

        result = ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
        conn.commit()

        assert result.source_key
        assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM generic_record").fetchone()[0] == 2, (
            "ingesting prices disturbed the generic records sharing the file")


def test_an_unchanged_row_is_confirmed_and_writes_no_history(conn):
    """`R-20` · «مراجعة عند التغير فقط» — an unchanged contractor is CONFIRMED, not
    re-recorded.

    THE MEASUREMENT THAT FORCED IT: 34,550 revisions for 11,059 contractors, from two
    crawls of a directory that barely moved. `content_hash` was on the table and was
    never consulted on ingest, so every crawl wrote a row of history for every record
    whether anything had changed or not — and the ruling records that as a change to
    the write path rather than a description of it.

    It is `SR-6` applied to a directory instead of a price — *"an unchanged price is
    confirmed, not appended"* — and a year of identical rows is not history.
    """
    snapshot = save(conn)
    candidate = service._candidate(
        conn, service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0)
    request = approval(candidate)
    service.approve_candidate(conn, snapshot["page_snapshot_id"], request)
    conn.commit()

    before = conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]
    seen_at = [row[0] for row in conn.execute(
        "SELECT last_seen_at FROM generic_record ORDER BY generic_record_id")]

    # The SAME rows arriving again on a DIFFERENT page — a second crawl of a
    # directory where nothing moved.
    again = save(conn, TABLE_HTML, "https://example.com/report?page=99")
    service.approve_candidate(conn, again["page_snapshot_id"], request)
    conn.commit()

    after = conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]
    assert after == before, (
        f"nothing changed and {after - before} revision(s) were written anyway — "
        "this is the defect R-20 exists to end")

    # CONFIRMED, THOUGH — the record is still marked as seen, which is the whole
    # distinction the ruling draws. A row that stopped being confirmed would be
    # indistinguishable from one that had vanished.
    now = [row[0] for row in conn.execute(
        "SELECT last_seen_at FROM generic_record ORDER BY generic_record_id")]
    assert len(now) == len(seen_at)
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_record WHERE status = 'active'"
    ).fetchone()[0] == len(now)
    # And the newer snapshot IS the record's source now, so the evidence a reader
    # would open is the most recent page that showed the row.
    sources = {row[0] for row in conn.execute(
        "SELECT source_snapshot_id FROM generic_record")}
    assert sources == {again["page_snapshot_id"]}


def test_a_changed_row_still_writes_its_revision(conn):
    """The other half, so the fix cannot be "never write history". A real change must
    still be recorded, or "when did this classification change" stops being
    answerable — which is the question the revisions exist for."""
    snapshot = save(conn)
    candidate = service._candidate(
        conn, service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0)
    request = approval(candidate)
    service.approve_candidate(conn, snapshot["page_snapshot_id"], request)
    conn.commit()
    before = conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]

    changed = save(conn, TABLE_HTML.replace("7000000", "7250000"),
                   "https://example.com/report?page=100")
    service.approve_candidate(conn, changed["page_snapshot_id"], request)
    conn.commit()

    after = conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]
    assert after == before + 1, "one row changed, so exactly one revision"
