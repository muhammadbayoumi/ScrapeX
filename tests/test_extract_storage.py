"""Persistent generic records, approval safety, recovery, and coexistence tests."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
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
def conn(tmp_path: Path):
    connection = dbmod.connect(tmp_path / "generic.db")
    dbmod.migrate(connection)
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


def test_0014_adds_separate_generic_storage_and_immutable_evidence(conn):
    assert dbmod.schema_version(conn) == 14
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
        service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0
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


def test_failed_identity_approval_rolls_back_and_a_corrected_retry_recovers(conn):
    html = """
    <table><tr><th>Region</th><th>Code</th></tr>
      <tr><td>North</td><td>N-1</td></tr>
      <tr><td>North</td><td>N-2</td></tr>
    </table>
    """
    snapshot = save(conn, html)
    candidate = service._candidate(
        service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0
    )

    with pytest.raises(CandidateNotApprovable, match="duplicate record keys"):
        service.approve_candidate(
            conn, snapshot["page_snapshot_id"], approval(candidate, {"region"})
        )
    assert conn.execute(
        "SELECT COUNT(*) FROM dataset_definition LIMIT 1"
    ).fetchone()[0] == 0

    recovered = service.approve_candidate(
        conn, snapshot["page_snapshot_id"], approval(candidate, {"code"})
    )
    conn.commit()
    assert recovered["record_count"] == 2


def test_retry_after_a_lost_success_response_is_idempotent(conn):
    snapshot = save(conn)
    candidate = service._candidate(
        service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0
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
        service._snapshot_row(conn, first_snapshot["page_snapshot_id"]), 0
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
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision LIMIT 1"
    ).fetchone()[0] == 4
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_ingestion LIMIT 1"
    ).fetchone()[0] == 2


def test_generic_ingestion_does_not_change_the_append_only_price_path(conn):
    snapshot = save(conn)
    candidate = service._candidate(
        service._snapshot_row(conn, snapshot["page_snapshot_id"]), 0
    )
    service.approve_candidate(conn, snapshot["page_snapshot_id"], approval(candidate))

    result = ingest_payloads(conn, make_entry(), [make_payload([one_row()])])

    assert result.observations == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM price_observation LIMIT 1"
    ).fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE price_observation SET effective_price=1.0")
