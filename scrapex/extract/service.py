"""Persistent approval and browsing for bounded HTML-table extraction."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from .. import catalog
from ..catalog_models import DatasetCreate, FieldCreate, SiteCreate
from .html_table import TableCandidate, candidate_by_index, detect_html_tables
from .models import (
    DEFAULT_RECORD_PAGE_SIZE,
    MAX_HTML_BYTES,
    MAX_RECORD_PAGE_SIZE,
    CandidateApproval,
    CandidateNotApprovable,
    ExtractionConflict,
    ExtractionNotFound,
    SnapshotCreate,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _site_base_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _snapshot_row(conn: sqlite3.Connection, snapshot_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT page_snapshot_id, source_url, content_type, html_content, "
        "content_hash, captured_at FROM generic_page_snapshot "
        "WHERE page_snapshot_id = ? LIMIT 1",
        (snapshot_id,),
    ).fetchone()
    if row is None:
        raise ExtractionNotFound(
            "The saved HTML snapshot was not found. Save the HTML again and retry."
        )
    return row


def _snapshot_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "page_snapshot_id": row["page_snapshot_id"],
        "source_url": row["source_url"],
        "content_type": row["content_type"],
        "content_hash": row["content_hash"],
        "captured_at": row["captured_at"],
    }


def save_snapshot(conn: sqlite3.Connection, request: SnapshotCreate) -> dict[str, Any]:
    """Persist immutable HTML evidence without creating a dataset candidate."""
    html_bytes = request.html_content.encode("utf-8")
    if len(html_bytes) > MAX_HTML_BYTES:
        raise CandidateNotApprovable(
            f"The saved HTML exceeds {MAX_HTML_BYTES:,} bytes. Save a smaller page "
            "snapshot and try again."
        )
    source_url = str(request.source_url)
    cursor = conn.execute(
        "INSERT INTO generic_page_snapshot "
        "(source_url, html_content, content_hash) VALUES (?,?,?)",
        (source_url, request.html_content, _digest(request.html_content)),
    )
    return _snapshot_public(_snapshot_row(conn, int(cursor.lastrowid)))


def discover_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> dict[str, Any]:
    """Recompute temporary candidates from saved evidence without catalogue writes."""
    snapshot = _snapshot_row(conn, snapshot_id)
    candidates = detect_html_tables(snapshot["html_content"])
    return {
        "snapshot": _snapshot_public(snapshot),
        "candidates": [candidate.public() for candidate in candidates],
    }


def _candidate(snapshot: sqlite3.Row, table_index: int) -> TableCandidate:
    try:
        return candidate_by_index(snapshot["html_content"], table_index)
    except LookupError:
        raise ExtractionNotFound(
            "The selected table candidate no longer exists in this snapshot. "
            "Run detection again and choose one of the returned candidates."
        ) from None


def _convert(value: str | None, data_type: str, field_name: str) -> Any:
    if value in (None, ""):
        return None
    try:
        if data_type in {"text", "unknown"}:
            return value
        if data_type == "integer":
            return int(value)
        if data_type == "decimal":
            number = Decimal(value)
            if not number.is_finite():
                raise ValueError
            return float(number)
        if data_type == "boolean":
            lowered = value.casefold()
            if lowered in {"true", "yes"}:
                return True
            if lowered in {"false", "no"}:
                return False
            raise ValueError
        if data_type == "date":
            return date.fromisoformat(value).isoformat()
        if data_type == "datetime":
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        if data_type == "url":
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError
            return value
        if data_type == "json":
            return json.loads(value)
    except (InvalidOperation, json.JSONDecodeError, ValueError):
        pass
    raise CandidateNotApprovable(
        f"The value in {field_name!r} does not match the approved {data_type} "
        "type. Change that field type or correct the saved HTML, then try again."
    )


def _validated_rows(
    candidate: TableCandidate, approval: CandidateApproval
) -> tuple[list[dict[str, Any]], list[str]]:
    if len(approval.fields) != len(candidate.fields):
        raise CandidateNotApprovable(
            "The approved field list no longer matches the detected table. Run "
            "detection again, review every field, and retry."
        )
    identity_keys = [field.field_key for field in approval.fields if field.identity]
    rows: list[dict[str, Any]] = []
    record_keys: list[str] = []
    for source_row in candidate.rows:
        converted: dict[str, Any] = {}
        for inferred, approved in zip(candidate.fields, approval.fields, strict=True):
            converted[approved.field_key] = _convert(
                source_row.get(inferred.field_key),
                approved.data_type.value,
                approved.display_name,
            )
        identity = [converted[key] for key in identity_keys]
        if any(value in (None, "") for value in identity):
            raise CandidateNotApprovable(
                "An approved identity field contains an empty value. Choose fields "
                "that identify every row, then try again."
            )
        rows.append(converted)
        record_keys.append(_digest(_canonical(identity)))
    if len(record_keys) != len(set(record_keys)):
        raise CandidateNotApprovable(
            "The approved identity fields produce duplicate record keys. Select a "
            "unique field or composite identity, then try again."
        )
    return rows, record_keys


def _schema_payload(
    candidate: TableCandidate, approval: CandidateApproval
) -> list[dict[str, Any]]:
    return [
        {
            "field_key": approved.field_key,
            "source_name": inferred.source_name,
            "data_type": approved.data_type.value,
            "nullable": inferred.nullable,
            "identity": approved.identity,
            "position": position,
        }
        for position, (inferred, approved) in enumerate(
            zip(candidate.fields, approval.fields, strict=True)
        )
    ]


def _approved_ingestion(
    conn: sqlite3.Connection, snapshot_id: int, locator: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT i.generic_ingestion_id, i.dataset_definition_id, "
        "i.schema_version_id, s.site_key, d.dataset_key, v.schema_hash "
        "FROM generic_ingestion AS i "
        "JOIN dataset_definition AS d ON d.dataset_definition_id = i.dataset_definition_id "
        "JOIN site_profile AS s ON s.site_profile_id = d.site_profile_id "
        "JOIN dataset_schema_version AS v ON v.schema_version_id = i.schema_version_id "
        "WHERE i.source_snapshot_id = ? AND i.source_locator = ? LIMIT 1",
        (snapshot_id, locator),
    ).fetchone()


def _ensure_schema(
    conn: sqlite3.Connection,
    dataset_id: int,
    candidate: TableCandidate,
    approval: CandidateApproval,
    schema_hash: str,
) -> int:
    existing = conn.execute(
        "SELECT schema_version_id FROM dataset_schema_version "
        "WHERE dataset_definition_id = ? AND schema_hash = ? LIMIT 1",
        (dataset_id, schema_hash),
    ).fetchone()
    if existing is not None:
        return int(existing["schema_version_id"])
    active = conn.execute(
        "SELECT schema_version_id FROM dataset_schema_version "
        "WHERE dataset_definition_id = ? AND valid_to IS NULL LIMIT 1",
        (dataset_id,),
    ).fetchone()
    if active is not None:
        raise ExtractionConflict(
            "This dataset already has a different approved schema. Use a new dataset "
            "key, or wait for schema-drift review support before retrying."
        )
    version_row = conn.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version "
        "FROM dataset_schema_version WHERE dataset_definition_id = ? LIMIT 1",
        (dataset_id,),
    ).fetchone()
    cursor = conn.execute(
        "INSERT INTO dataset_schema_version "
        "(dataset_definition_id, version_number, schema_hash) VALUES (?,?,?)",
        (dataset_id, int(version_row["next_version"]), schema_hash),
    )
    schema_version_id = int(cursor.lastrowid)
    for position, (inferred, approved) in enumerate(
        zip(candidate.fields, approval.fields, strict=True)
    ):
        field = catalog.register_field(
            conn,
            dataset_id,
            FieldCreate(
                field_key=approved.field_key,
                original_name=inferred.source_name,
                data_type=approved.data_type,
                is_nullable=inferred.nullable,
                identity_role="key_part" if approved.identity else "none",
                display_order=position,
            ),
        )
        conn.execute(
            "UPDATE field_definition SET display_name = ? "
            "WHERE field_definition_id = ?",
            (approved.display_name, field["field_definition_id"]),
        )
        conn.execute(
            "INSERT INTO schema_version_field "
            "(schema_version_id, field_definition_id, field_order) VALUES (?,?,?)",
            (schema_version_id, field["field_definition_id"], position),
        )
    return schema_version_id


def _dataset_row(conn: sqlite3.Connection, dataset_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT d.dataset_definition_id, d.dataset_key, d.original_name, "
        "d.display_name, d.discovery_method, d.first_seen_at, d.last_seen_at, "
        "s.site_key, s.display_name AS site_display_name "
        "FROM dataset_definition AS d "
        "JOIN site_profile AS s ON s.site_profile_id = d.site_profile_id "
        "WHERE d.dataset_definition_id = ? AND d.valid_to IS NULL LIMIT 1",
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise ExtractionNotFound(
            "The approved dataset was not found. Return to Datasets and choose an "
            "available dataset."
        )
    return row


def _dataset_public(conn: sqlite3.Connection, dataset_id: int) -> dict[str, Any]:
    row = _dataset_row(conn, dataset_id)
    count_row = conn.execute(
        "SELECT COUNT(*) AS record_count FROM generic_record "
        "WHERE dataset_definition_id = ? LIMIT 1",
        (dataset_id,),
    ).fetchone()
    ingestion = conn.execute(
        "SELECT ingested_at FROM generic_ingestion "
        "WHERE dataset_definition_id = ? ORDER BY generic_ingestion_id DESC LIMIT 1",
        (dataset_id,),
    ).fetchone()
    return {
        "dataset_definition_id": row["dataset_definition_id"],
        "dataset_key": row["dataset_key"],
        "original_name": row["original_name"],
        "display_name": row["display_name"],
        "label": row["display_name"] or row["original_name"],
        "discovery_method": row["discovery_method"],
        "site_key": row["site_key"],
        "site_display_name": row["site_display_name"],
        "record_count": int(count_row["record_count"]),
        "last_ingested_at": ingestion["ingested_at"] if ingestion else None,
    }


def approve_candidate(
    conn: sqlite3.Connection, snapshot_id: int, approval: CandidateApproval
) -> dict[str, Any]:
    """Atomically turn one reviewed candidate into definitions and generic rows."""
    snapshot = _snapshot_row(conn, snapshot_id)
    candidate = _candidate(snapshot, approval.table_index)
    if not candidate.approvable:
        reason = candidate.warnings[0] if candidate.warnings else "The table is incomplete."
        raise CandidateNotApprovable(
            f"This table cannot be approved: {reason} Correct the saved HTML and try again."
        )
    rows, record_keys = _validated_rows(candidate, approval)
    schema_hash = _digest(_canonical(_schema_payload(candidate, approval)))
    recovered = _approved_ingestion(conn, snapshot_id, candidate.locator)
    if recovered is not None:
        same_request = (
            recovered["site_key"] == approval.site_key
            and recovered["dataset_key"] == approval.dataset_key
            and recovered["schema_hash"] == schema_hash
        )
        if not same_request:
            raise ExtractionConflict(
                "This table candidate was already approved with a different identity "
                "or schema. Open the existing dataset instead of approving it again."
            )
        result = _dataset_public(conn, int(recovered["dataset_definition_id"]))
        result.update({
            "schema_version_id": int(recovered["schema_version_id"]),
            "generic_ingestion_id": int(recovered["generic_ingestion_id"]),
            "recovered": True,
        })
        return result

    site = catalog.register_site(
        conn,
        SiteCreate(
            site_key=approval.site_key,
            display_name=approval.site_display_name,
            base_url=_site_base_url(snapshot["source_url"]),
        ),
    )
    dataset = catalog.register_dataset(
        conn,
        approval.site_key,
        DatasetCreate(
            dataset_key=approval.dataset_key,
            original_name=candidate.name,
            dataset_kind="table",
            discovery_method="html_table",
            locator={"selector": candidate.locator},
        ),
    )
    dataset_id = int(dataset["dataset_definition_id"])
    conn.execute(
        "UPDATE dataset_definition SET display_name = ? "
        "WHERE dataset_definition_id = ?",
        (approval.dataset_name, dataset_id),
    )
    schema_version_id = _ensure_schema(
        conn, dataset_id, candidate, approval, schema_hash
    )
    for row_position, (row, record_key) in enumerate(
        zip(rows, record_keys, strict=True), start=1
    ):
        data_json = _canonical(row)
        content_hash = _digest(data_json)
        row_locator = f"{candidate.locator}::row({row_position})"
        cursor = conn.execute(
            "INSERT INTO generic_record "
            "(dataset_definition_id, record_key, schema_version_id, data_json, "
            "source_snapshot_id, source_locator, content_hash) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(dataset_definition_id, record_key) DO UPDATE SET "
            "schema_version_id=excluded.schema_version_id, "
            "data_json=excluded.data_json, source_snapshot_id=excluded.source_snapshot_id, "
            "source_locator=excluded.source_locator, content_hash=excluded.content_hash, "
            "last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), status='active' "
            "RETURNING generic_record_id",
            (
                dataset_id,
                record_key,
                schema_version_id,
                data_json,
                snapshot_id,
                row_locator,
                content_hash,
            ),
        )
        record_id = int(cursor.fetchone()["generic_record_id"])
        conn.execute(
            "INSERT INTO generic_record_revision "
            "(generic_record_id, schema_version_id, source_snapshot_id, data_json, "
            "content_hash) VALUES (?,?,?,?,?)",
            (record_id, schema_version_id, snapshot_id, data_json, content_hash),
        )
    ingestion = conn.execute(
        "INSERT INTO generic_ingestion "
        "(dataset_definition_id, schema_version_id, source_snapshot_id, "
        "source_locator, record_count) VALUES (?,?,?,?,?)",
        (dataset_id, schema_version_id, snapshot_id, candidate.locator, len(rows)),
    )
    result = _dataset_public(conn, dataset_id)
    result.update({
        "site_profile_id": int(site["site_profile_id"]),
        "schema_version_id": schema_version_id,
        "generic_ingestion_id": int(ingestion.lastrowid),
        "recovered": False,
    })
    return result


def list_datasets(
    conn: sqlite3.Connection,
    *,
    after_id: int = 0,
    limit: int = DEFAULT_RECORD_PAGE_SIZE,
) -> dict[str, Any]:
    if limit < 1 or limit > MAX_RECORD_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_RECORD_PAGE_SIZE}")
    rows = conn.execute(
        "SELECT DISTINCT d.dataset_definition_id FROM dataset_definition AS d "
        "JOIN generic_ingestion AS i "
        "ON i.dataset_definition_id = d.dataset_definition_id "
        "WHERE d.valid_to IS NULL AND d.dataset_definition_id > ? "
        "ORDER BY d.dataset_definition_id LIMIT ?",
        (max(0, after_id), limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "datasets": [
            _dataset_public(conn, int(row["dataset_definition_id"])) for row in page
        ],
        "next_after_id": (
            int(page[-1]["dataset_definition_id"]) if has_more else None
        ),
    }


def browse_records(
    conn: sqlite3.Connection,
    dataset_id: int,
    *,
    after_id: int = 0,
    limit: int = DEFAULT_RECORD_PAGE_SIZE,
) -> dict[str, Any]:
    if limit < 1 or limit > MAX_RECORD_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_RECORD_PAGE_SIZE}")
    dataset = _dataset_public(conn, dataset_id)
    fields = conn.execute(
        "SELECT f.field_key, f.original_name, f.display_name, f.data_type, "
        "f.identity_role, svf.field_order "
        "FROM dataset_schema_version AS sv "
        "JOIN schema_version_field AS svf "
        "ON svf.schema_version_id = sv.schema_version_id "
        "JOIN field_definition AS f "
        "ON f.field_definition_id = svf.field_definition_id "
        "WHERE sv.dataset_definition_id = ? AND sv.valid_to IS NULL "
        "ORDER BY svf.field_order LIMIT ?",
        (dataset_id, 100),
    ).fetchall()
    rows = conn.execute(
        "SELECT generic_record_id, record_key, data_json, status, first_seen_at, "
        "last_seen_at FROM generic_record "
        "WHERE dataset_definition_id = ? AND generic_record_id > ? "
        "ORDER BY generic_record_id LIMIT ?",
        (dataset_id, max(0, after_id), limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "dataset": dataset,
        "fields": [
            {
                "field_key": row["field_key"],
                "original_name": row["original_name"],
                "display_name": row["display_name"],
                "label": row["display_name"] or row["original_name"],
                "data_type": row["data_type"],
                "identity": row["identity_role"] == "key_part",
                "position": row["field_order"],
            }
            for row in fields
        ],
        "records": [
            {
                "generic_record_id": row["generic_record_id"],
                "record_key": row["record_key"],
                "data": json.loads(row["data_json"]),
                "status": row["status"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in page
        ],
        "next_after_id": (
            int(page[-1]["generic_record_id"]) if has_more else None
        ),
    }
