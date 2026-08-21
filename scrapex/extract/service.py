"""Persistent approval and browsing for bounded HTML-table extraction."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from .. import catalog
from ..catalog_models import DatasetCreate, FieldCreate, SiteCreate
from ..sightings import STATE_MEANING, row_state
from ..snapshotbody import decode, encode
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

#: What WE observed, as against what the site published. `R-27`: «يجب ان يظل الصف
#: ظاهر للمستخدم مهما اختلف حالة الرصد» — the row never disappears, and its state is a
#: column instead.
#:
#: PREFIXED, AND THE PREFIX IS THE POINT. These keys go into the row the grid renders,
#: beside the dataset's own fields, and a site that ever publishes a column called
#: `status` or `first_seen_at` would otherwise collide with them silently — one value
#: overwriting the other with nothing to say which won. `observed_` is not a name any
#: site's own label would slug to.
#:
#: AND THEY ARE NEVER WRITTEN BACK INTO `data_json`. That column is source truth. A
#: fact about our observation is not a fact the site stated, and mixing the two is how
#: a warehouse stops being able to say where a value came from.
OBSERVED_STATE = "observed_state"
OBSERVED_STATE_MEANING = "observed_state_meaning"
OBSERVED_FIRST_SEEN = "observed_first_seen"
OBSERVED_LAST_SEEN = "observed_last_seen"
OBSERVED_CHANGED = "observed_last_changed"
OBSERVED_STATUS = "observed_status"

#: THE STATE COLUMN LEADS, on his instruction: «عمود يوضح الحالة الجديدة لا تدع
#: المستخدم يستنتج الحالة». The dates stay — they are the evidence behind the state and
#: a reader who wants to check it can — but the state itself is stated, not implied.
#:
#: Two columns replaced by one: `observed_gone_in_last_crawl` and
#: `observed_new_in_last_crawl` were a first attempt that asked the reader to combine
#: two yes/no answers and read `retired`, `returned` and `unsighted` out of a status
#: and three dates. Eight states do not fit in two booleans.
OBSERVED_COLUMNS: tuple[tuple[str, str], ...] = (
    (OBSERVED_STATE, "State"),
    (OBSERVED_STATE_MEANING, "What that means"),
    (OBSERVED_LAST_SEEN, "Last seen"),
    (OBSERVED_FIRST_SEEN, "First seen"),
    (OBSERVED_CHANGED, "Last changed"),
    (OBSERVED_STATUS, "Record status"),
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
        "content_hash, captured_at, html_codec, html_dict_id "
        "FROM generic_page_snapshot "
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
    # THE HASH IS OF THE PAGE, NEVER OF ITS ENCODING. Two runs that fetch the
    # same page must agree on its content_hash whether one compressed it and the
    # other did not -- identity is a fact about content, and the day a codec
    # changes must not be the day every page becomes a different page.
    body, codec, dict_id = encode(conn, request.html_content,
                                  label=request.body_class)
    cursor = conn.execute(
        "INSERT INTO generic_page_snapshot "
        "(source_url, html_content, content_hash, crawl_run_ref, html_codec, "
        " html_dict_id) VALUES (?,?,?,?,?,?)",
        (source_url, body, _digest(request.html_content),
         request.crawl_run_ref, codec, dict_id),
    )
    return _snapshot_public(_snapshot_row(conn, int(cursor.lastrowid)))


def discover_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> dict[str, Any]:
    """Recompute temporary candidates from saved evidence without catalogue writes."""
    snapshot = _snapshot_row(conn, snapshot_id)
    candidates = detect_html_tables(decode(conn, snapshot))
    return {
        "snapshot": _snapshot_public(snapshot),
        "candidates": [candidate.public() for candidate in candidates],
    }


def _candidate(conn: sqlite3.Connection, snapshot: sqlite3.Row,
               table_index: int) -> TableCandidate:
    try:
        return candidate_by_index(decode(conn, snapshot), table_index)
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
            return datetime.fromisoformat(value).isoformat()
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


def _retire_or_refuse(conn: sqlite3.Connection, active_version_id: int,
                      approval: CandidateApproval) -> None:
    """A GROWN schema opens a new version; a SHRUNK one is still refused.

    `R-31`. Until 2026-08-21 any difference from the approved field set raised
    `ExtractionConflict`, whose own message pointed at "schema-drift review support"
    that did not exist. It could not have existed: reaching version 2 requires the
    active version to be retired, and `valid_to` was READ in five places and written
    in none. So a site that added a field could never be recorded at all.

    THE RULE IS DIRECTIONAL, AND THAT IS THE WHOLE SAFETY OF IT.

        every approved field still present, plus new ones  ->  retire, open v2
        a field missing, renamed or re-keyed               ->  refuse, as before

    #234 IS WHY, and it is the case that makes the naive version wrong. `region_id=0`
    publishes contractors with no location box, so its 74 pages taught a schema of 21
    fields where the declared set is 22 — a SUBSET — and 823 pages were refused. Had
    any drift opened a new version, that parser would have quietly retired a column
    the site still publishes, and every row after it would have lost `card_city_region`
    with nothing raised. A subset is the signature of a bad sample or a broken parser,
    never of a site adding information.

    A RENAME LOOKS LIKE A SUBSET PLUS A SUPERSET and is therefore refused, which is
    the honest outcome: nothing here can tell `card_city` renamed to `card_town` from
    one field vanishing and another appearing, and guessing would silently orphan
    every value already stored under the old key.
    """
    approved = {
        str(row["field_key"]) for row in conn.execute(
            "SELECT f.field_key FROM schema_version_field AS svf "
            "  JOIN field_definition AS f "
            "    ON f.field_definition_id = svf.field_definition_id "
            " WHERE svf.schema_version_id = ?", (active_version_id,))
    }
    now = {one.field_key for one in approval.fields}
    lost = sorted(approved - now)
    if lost:
        raise ExtractionConflict(
            f"This dataset's approved schema has {len(approved)} field(s) and this "
            f"page declares {len(now)}, dropping {lost!r}. A field the site still "
            "publishes must not be retired by one page's sample — that is how "
            "region_id=0's 74 pages refused 823 others (#234). Fix the parser, or "
            "use a new dataset key if the directory really has changed shape."
        )
    gained = sorted(now - approved)
    conn.execute(
        "UPDATE dataset_schema_version "
        "   SET valid_to = strftime('%Y-%m-%dT%H:%M:%SZ','now'), status = 'retired' "
        " WHERE schema_version_id = ?", (active_version_id,))
    logging.getLogger(__name__).info(
        "schema grew by %s; version %s retired, a new one opens",
        gained, active_version_id)


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
        _retire_or_refuse(conn, int(active["schema_version_id"]), approval)
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
    conn: sqlite3.Connection, snapshot_id: int, approval: CandidateApproval,
    *, candidate: TableCandidate | None = None
) -> dict[str, Any]:
    """Atomically turn one reviewed candidate into definitions and generic rows.

    `candidate` LETS A SITE SUPPLY ITS OWN, and everything below this line is
    unchanged by it. Nothing in the storage half has anything to do with
    `<table>` — only the DETECTION does — and a page can hold rows without
    holding a table: muqawil.org's contractor listing has TWENTY rows and ZERO
    `<table>` elements, so `detect_html_tables` finds nothing on it at all.

    The alternative was a second path from such a page to `generic_record`, and
    that would be a second copy of the atomicity, the idempotency and the
    revision history — two copies that drift apart on the first bug fixed in
    only one of them. `scrapex/extract/muqawil.py:listing_candidate` is the
    first caller.
    """
    snapshot = _snapshot_row(conn, snapshot_id)
    if candidate is None:
        candidate = _candidate(conn, snapshot, approval.table_index)
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
    # WHAT EACH OF THESE ROWS ALREADY LOOKS LIKE, in ONE query rather than one per
    # row. `R-20`: an unchanged contractor is CONFIRMED, not re-recorded — so the
    # write path has to know whether anything changed before it writes history, and
    # `content_hash` is the column that answers it. It existed and was never read:
    # measured at 34,550 revisions for 11,059 contractors, roughly three apiece from
    # two crawls of a directory that barely moved.
    #
    # KEYED ON THIS PAGE'S RECORDS ONLY. Loading every record of the dataset would
    # be a full scan per page — 897 pages against 17,000 rows — where twenty
    # look-ups on the unique `(dataset_definition_id, record_key)` index cost
    # nothing.
    already = {}
    if record_keys:
        holes = ",".join("?" * len(record_keys))
        already = {
            found["record_key"]: found["content_hash"]
            for found in conn.execute(
                "SELECT record_key, content_hash FROM generic_record "
                f" WHERE dataset_definition_id = ? AND record_key IN ({holes})",
                (dataset_id, *record_keys))
        }

    for row_position, (row, record_key) in enumerate(
        zip(rows, record_keys, strict=True), start=1
    ):
        data_json = _canonical(row)
        content_hash = _digest(data_json)
        # UNCHANGED IS DECIDED BEFORE THE UPSERT OVERWRITES THE EVIDENCE. Once the
        # row is written, `content_hash` holds the NEW value and the comparison is
        # impossible — which is why this cannot be a `RETURNING` clause.
        unchanged = already.get(record_key) == content_hash
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
        if not unchanged:
            # A REVISION PER REAL CHANGE, which is what makes "when did this
            # classification change" answerable. `R-20`, and it is `SR-6` applied to
            # a directory instead of a price — *"an unchanged price is confirmed, not
            # appended"* — because a year of identical rows is not history, it is a
            # table that grows with every crawl and says nothing.
            #
            # `last_seen_at` still moved: the upsert above sets it unconditionally, so
            # a confirmation is recorded on the RECORD and not in its history. That is
            # the distinction the ruling draws.
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


def dataset_table_payload(conn: sqlite3.Connection, dataset_key: str,
                          *, cap: int | None = None) -> dict[str, Any] | None:
    """One generic dataset in the shape the grid already renders.

    THE PAGE NEEDS NO CHANGE, AND THAT IS THE WHOLE DESIGN. `grid.js` never asks
    where a payload came from — it reads `columns`, `rows`, `total`,
    `truncated` and `bilingual`, and draws its filters, its column menus, its
    export and its AR|EN toggle off those. `reports.table_payload` fills them
    from `price_observation`; this fills the same keys from `generic_record`.
    A contractor directory is then a table like any other table, on the page
    the owner already has, with nothing new to learn.

    THE BILINGUAL PAIRS ARE DERIVED, NEVER LISTED. `reports.BILINGUAL_COLUMNS`
    is a dict written out by hand for products and has no per-source form, so a
    second table could never have used it. Here any field ending `_ar` pairs
    with the field of the same name without it — which is what products already
    do (`product_name` / `product_name_ar`), and which cannot go stale when a
    column is added. `grid.js:1905` reads `Object.entries(payload.bilingual)`
    and its own comment says the toggle "never hardcodes a field list"; this is
    the first caller to take it at its word.

    Returns None when no dataset carries this key, so a caller can fall through
    to the price path rather than having to ask twice.

    `cap=None` MEANS EVERY ROW, and that is the default on the owner's
    instruction of 2026-08-20: «اريد تحميل كل الصفوف بلا حد». It used to default
    to 5,000, so the page read "Loaded 5,000 of 11,059" and -- the part that
    actually cost him something -- the grid's filters and its search only ever
    saw the loaded prefix, so a search for a contractor in the other 6,059
    found nothing and said so as if the contractor did not exist.

    The number was also inconsistent with the docstring above it. A price table
    loads reports.TABLE_ROW_CAP = 20,000 and a price EXPORT 40,000, so
    "a table like any other table" was capped at a quarter of the smaller of
    those, for no reason recorded anywhere.

    MEASURED before removing it, because A8 asks for a bound and the honest
    answer is what it costs: all 11,059 rows read and parsed in 0.09s for a
    13.2 MB JSON payload, against 6.0 MB for the first 5,000. At the 17,283 the
    sweep counted it is ~21 MB. A caller that needs a bound still passes one;
    what changed is that the default no longer decides for him.
    """
    found = conn.execute(
        "SELECT d.dataset_definition_id AS id, d.display_name, d.original_name "
        "FROM dataset_definition AS d "
        "WHERE d.dataset_key = ? AND d.valid_to IS NULL LIMIT 1",
        (dataset_key,)).fetchone()
    if found is None:
        return None

    dataset_id = int(found["id"])
    fields = conn.execute(
        "SELECT f.field_key, f.display_name, f.original_name, f.data_type, "
        "       f.identity_role "
        "FROM dataset_schema_version AS sv "
        "JOIN schema_version_field AS svf "
        "ON svf.schema_version_id = sv.schema_version_id "
        "JOIN field_definition AS f "
        "ON f.field_definition_id = svf.field_definition_id "
        "WHERE sv.dataset_definition_id = ? AND sv.valid_to IS NULL "
        "ORDER BY svf.field_order",
        (dataset_id,)).fetchall()

    # THE DATASET'S OWN IDENTITY FIELD, asked of the schema rather than hardcoded.
    # `contractor_id` is muqawil's answer; Balady's and the UAE's will not be, and
    # this function is the one the panel calls for every generic source.
    identity = [row["field_key"] for row in fields
                if row["identity_role"] == "key_part"]
    identity_field = identity[0] if len(identity) == 1 else None

    # NO `status` FILTER, AND THAT IS `R-27`. «يجب ان يظل الصف ظاهر للمستخدم مهما
    # اختلف حالة الرصد» — a row stays on screen whatever the crawl saw. It used to
    # read `AND status = 'active'` on both this count and the rows below, so a
    # contractor the site stopped publishing would simply VANISH from his screen the
    # moment anything marked the row, and the disappearance he wants to see would be
    # the one thing he could not.
    total = conn.execute(
        "SELECT count(*) FROM generic_record WHERE dataset_definition_id = ?",
        (dataset_id,)).fetchone()[0]
    # LIMIT only when a caller asked for one. `LIMIT -1` is SQLite's own idiom
    # for no limit and is used rather than building two query strings, so the
    # bounded and unbounded paths cannot drift apart.
    # EVERY FACT THE STATE NEEDS, IN ONE QUERY. `changed_at` is the newest revision
    # for this record, which is what makes `updated` knowable — and it is only
    # meaningful because `R-20` stopped writing a revision when nothing changed.
    # Before that every row had one every crawl and `updated` would have been every
    # row. `LEFT JOIN`, because a record whose only revision is its first has none
    # after it and must not vanish from its own table.
    stored = conn.execute(
        "SELECT r.generic_record_id, r.record_key, r.data_json, r.status, "
        "       r.first_seen_at, r.last_seen_at, "
        "       (SELECT MAX(v.observed_at) FROM generic_record_revision AS v "
        "         WHERE v.generic_record_id = r.generic_record_id) AS changed_at "
        "  FROM generic_record AS r WHERE r.dataset_definition_id = ? "
        " ORDER BY r.generic_record_id LIMIT ?",
        (dataset_id, -1 if cap is None else int(cap))).fetchall()

    # WHEN THE MOST RECENT CRAWL SAW ANYTHING — one aggregate, not a per-row
    # question. Derived, never stored: written into the row it would be stale the
    # moment the next crawl ran (`R-27`).
    newest = conn.execute(
        "SELECT MAX(last_seen_at) FROM generic_record WHERE dataset_definition_id = ?",
        (dataset_id,)).fetchone()[0]

    # THE SIGHTING SIDE, READ ONCE. `unsighted` and `returned` are the two states that
    # cannot be answered from `generic_record` alone, and joining per row would be the
    # correlated-subquery defect `OP-27` measured at 49s all over again.
    sighted: dict[str, tuple[str | None, str | None]] = {}
    if dataset_key:
        sighted = {
            key: (seen, absent)
            for key, seen, absent in conn.execute(
                "SELECT external_id, last_seen_at, last_absent_at "
                "  FROM dataset_sighting WHERE dataset_key = ?", (dataset_key,))
        }

    rows = []
    for row in stored:
        record = json.loads(row["data_json"])
        external = record.get(identity_field) if identity_field else None
        seen_at, absent_at = sighted.get(str(external), (None, None))
        # BESIDE THE SITE'S FIELDS, NEVER MERGED INTO THEM. These are facts about our
        # OBSERVATION, not facts the site published, and `data_json` is source truth —
        # so they are added to the row the grid renders and never written back.
        record[OBSERVED_FIRST_SEEN] = row["first_seen_at"]
        record[OBSERVED_LAST_SEEN] = row["last_seen_at"]
        record[OBSERVED_STATUS] = row["status"]
        record[OBSERVED_CHANGED] = row["changed_at"]
        # ONE COLUMN THAT SAYS THE STATE, decided in `sightings.row_state` and nowhere
        # else. «لا تدع المستخدم يستنتج الحالة» — and two readers inferring from four
        # dates will infer differently, with one of them wrong.
        state = row_state(
            status=row["status"], first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"], newest=newest,
            changed_at=row["changed_at"], sighted_at=seen_at,
            last_absent_at=absent_at)
        record[OBSERVED_STATE] = state
        record[OBSERVED_STATE_MEANING] = STATE_MEANING.get(state, "")
        rows.append(record)

    keys = {row["field_key"] for row in fields}
    return {
        "source_key": dataset_key,
        "columns": [{"key": row["field_key"],
                     "label": row["display_name"] or row["original_name"]}
                    for row in fields]
        + [{"key": key, "label": label} for key, label in OBSERVED_COLUMNS],
        "rows": rows,
        "total": total,
        "returned": len(rows),
        # A PREFIX PRESENTED AS THE WHOLE is the failure the bound exists to
        # prevent, and the grid already draws a notice from this flag.
        "truncated": total > len(rows),
        # NEITHER IS TRUE OF A DIRECTORY, and both are answered rather than
        # omitted: `grid.js` reads them unconditionally, and an absent key would
        # be a crash where a false is a switch the page simply does not offer.
        "folded": False,
        "fold_variants": False,
        "foldable": False,
        "tree": {},
        "bilingual": {key: key[:-3] for key in sorted(keys)
                      if key.endswith("_ar") and key[:-3] in keys},
        "tax_states": {},
        "moved_to_details": [],
    }
