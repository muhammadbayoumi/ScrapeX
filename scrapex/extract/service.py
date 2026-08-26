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
from ..fields import arranged, list_fields
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
#: THE ROW'S HANDLE, and it is not a column. `offer_id` is what the products payload
#: carries so `grid.js` can open a card for the row that was selected — it rides in
#: `rows` and is absent from `BROWSE_COLUMNS`, so it never draws. A dataset row had no
#: equivalent: `generic_record_id` was SELECTed and then dropped on the floor by the
#: emitting loop, so `grid.js`'s `rows.filter((row) => row.offer_id)` matched nothing
#: and selecting a contractor could not open anything at all.
#:
#: `observed_` PREFIXED like the rest, for the reason the block above gives: it is a
#: fact about our storage rather than one the site published, and no site's own label
#: slugs to it. Deliberately NOT added to `OBSERVED_COLUMNS` — a handle the reader
#: never sees is the whole point.
OBSERVED_RECORD_ID = "observed_record_id"

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


def _rows_unchanged(conn: sqlite3.Connection, dataset_id: int,
                   rows: list[dict], record_keys: list[str]) -> bool:
    """Would writing these rows change anything? Read from what is already stored.

    THE SAME COMPARISON THE WRITE PATH MAKES, and deliberately the same expression:
    `already.get(record_key) == content_hash`, where `content_hash` is
    `_digest(_canonical(row))`. Two ways of deciding "unchanged" is one way of deciding
    it and one liability, and this one runs BEFORE the upsert for the reason that path
    already records — once the row is written, `content_hash` holds the new value and
    the question can no longer be asked.

    A ROW THIS DATASET HAS NEVER SEEN COUNTS AS CHANGED, and it needs no extra check to
    say so: `stored.get(key)` is `None` for a key that was never written, and `None`
    never equals a digest. A `len(stored) != len(record_keys)` guard was written here
    first and a mutation deleted it with every test still passing — the second line today
    that read like protection and could not fail. The comparison below is what protects
    this, and it is the only thing that does.
    """
    if not record_keys:
        return True
    holes = ",".join("?" * len(record_keys))
    stored = {
        found["record_key"]: found["content_hash"]
        for found in conn.execute(
            "SELECT record_key, content_hash FROM generic_record "
            f" WHERE dataset_definition_id = ? AND record_key IN ({holes})",
            (dataset_id, *record_keys))
    }
    return all(stored.get(key) == _digest(_canonical(row))
               for row, key in zip(rows, record_keys, strict=True))


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
        # DEC-10 / `R-40`: SAME REQUEST IS NOT SAME ROWS. Everything checked above is
        # about identity and shape, and none of it moves when a parser is CORRECTED — so
        # a fixed parse of the same page matched here, answered `recovered=True` and
        # wrote nothing. On 34,834 profile pages that would cost a re-crawl to repair
        # what should be a re-parse, which is precisely what the fetch/interpret seam
        # exists to prevent.
        #
        # ASKED OF THE ROWS THEMSELVES, AND NO COLUMN WAS ADDED FOR IT. The first
        # attempt put a `rows_hash` on `generic_ingestion` and that table is
        # append-only in BOTH directions and UNIQUE on `(snapshot, locator)` — so the
        # digest would have been unwritable after the first insert, and there can never
        # be a second ingestion for one page. `generic_record.content_hash` already
        # holds exactly this fact per row, and the write path below already reads it.
        if _rows_unchanged(conn, int(recovered["dataset_definition_id"]),
                           rows, record_keys):
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
    if recovered is None:
        ingestion_id = int(conn.execute(
            "INSERT INTO generic_ingestion "
            "(dataset_definition_id, schema_version_id, source_snapshot_id, "
            "source_locator, record_count) VALUES (?,?,?,?,?)",
            (dataset_id, schema_version_id, snapshot_id, candidate.locator,
             len(rows)),
        ).lastrowid)
    else:
        # NO SECOND INGESTION, AND THE SCHEMA IS WHAT SAYS SO: `generic_ingestion` is
        # UNIQUE on `(source_snapshot_id, source_locator)` and append-only in both
        # directions. That is right — "this page was ingested" happened once and is not
        # revisable. A re-parse changes the ROWS, and their history lives in
        # `generic_record_revision`, which is where a changed value belongs.
        ingestion_id = int(recovered["generic_ingestion_id"])
    result = _dataset_public(conn, dataset_id)
    result.update({
        "site_profile_id": int(site["site_profile_id"]),
        "schema_version_id": schema_version_id,
        "generic_ingestion_id": ingestion_id,
        "recovered": False,
        # NAMED SEPARATELY FROM `recovered`, because a caller counting re-parses and a
        # caller counting no-ops are asking different questions. `scrapex contractors
        # --approve` prints the recovered count out loud so a run that repaired nothing
        # cannot be mistaken for one that did; this is the other half of that report.
        "reparsed": recovered is not None,
    })
    return result


#: The freshness read, as a constant so a test can put it through
#: `EXPLAIN QUERY PLAN` and pin the index. `INDEXED BY` is the whole of the 390x
#: below and nothing about the ANSWER changes when it is removed, so no
#: assertion about a returned value can defend it.
LAST_EVIDENCE_SQL = (
    "SELECT max(p.captured_at) FROM generic_ingestion AS g "
    "JOIN generic_page_snapshot AS p INDEXED BY ix_generic_page_snapshot_page "
    "ON p.page_snapshot_id = g.source_snapshot_id "
    "WHERE g.dataset_definition_id = ?"
)


def last_evidence_captured_at(conn: sqlite3.Connection,
                              dataset_id: int) -> str | None:
    """When this dataset was last FED A PAGE, read off the evidence itself.

    THE DEFECT THIS ANSWERS. The panel's source card said *"no successful crawl
    yet"* under `17,304 products` — and 17,304 rows plainly came from a crawl.
    The price pipeline records one `crawl_run` row per ingest and the card reads
    it; the generic pipeline records none, because `crawl_run.source_id` is
    `NOT NULL REFERENCES source_site(source_id)` (db/engine/schema.sql:122) and
    muqawil has no `source_site` row at all — it lives in `site_profile`, and
    which registry a source lands in is the open question `REQ-25` holds. So the
    card was reading a table that cannot describe a dataset, and answering
    honestly about the wrong thing.

    Nothing new is recorded to fix it. `generic_page_snapshot.captured_at` is
    when a page was fetched and `generic_ingestion` is which pages this dataset
    was built from — both already written on every crawl — so the freshness is
    a read, not a column.

    `generic_ingestion` AND NOT `generic_record.source_snapshot_id`, and the
    difference is a re-crawl that changes nothing. A record keeps pointing at
    the snapshot that last CHANGED it (`R-20`: unchanged means no revision), so
    a confirming pass would leave the date stale — exactly the complaint. On his
    warehouse, measured 2026-08-22: 3,883 ingestions against 2,139 distinct
    record snapshots for `contractors`, and the two answers differ —
    `17:56:31Z` from the ingestions, `17:54:31Z` from the records.

    `INDEXED BY`, AND IT IS 390x. `ix_generic_page_snapshot_page` is
    `(page_snapshot_id, captured_at)` (db/engine/schema.sql:843) and had no
    reader; SQLite prefers the rowid because the planner cannot see that the row
    it lands on carries a compressed 100 KB body. Measured on his 24,480-page
    warehouse: **353-373 ms** on the rowid against **0.9 ms** on the covering
    index, for the identical answer. A8 asks for the covering index to be noted;
    this is the query that needed it. If the index is ever dropped, SQLite
    raises rather than quietly paying the 373 ms — which is the failure anyone
    would rather have.

    AND NOT `max(page_snapshot_id)`, WHICH LOOKS EQUIVALENT AND IS NOT.
    `save_snapshot` never supplies `captured_at`, so within one machine the ids
    and the timestamps rise together and the newest id is the newest page — 0.2
    ms instead of 0.9. `warehousemerge.py:269` breaks it: a merge INSERTs the
    other machine's `captured_at` verbatim under freshly assigned local ids, so
    after the merge `R-43` makes routine, the highest id can be the oldest page.
    The 0.7 ms is not worth a claim that his own workflow falsifies.

    None means no page has ever been ingested into this dataset. That is a real
    answer and the card must say so in words.
    """
    row = conn.execute(LAST_EVIDENCE_SQL, (dataset_id,)).fetchone()
    return row[0] if row is not None else None


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


def dataset_schema_fields(
    conn: sqlite3.Connection, dataset_key: str,
) -> tuple[int, list[sqlite3.Row]] | None:
    """This dataset's id and its CURRENT schema's fields, in schema order.

    ONE QUERY, TWO READERS, and the second reader is why this is a function.
    `dataset_table_payload` needs it to build the table; `/api/fields` needs it
    to know which columns the Choose-Columns panel may offer at all. That second
    endpoint had no way to ask the catalogue, so it asked the PRICE path instead
    — and seeded `dataset_field` with ELEVEN price-path keys against
    `contractors` (`price`, `tax`, `stock_quantity`, …), none of which the
    directory publishes. Measured against the live warehouse on 2026-08-22.

    Returns None when no dataset carries the key, so a caller can fall through
    to the price path rather than having to ask twice — the same contract
    `dataset_table_payload` already offers.
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
    return dataset_id, fields


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
    answer is what it costs. RE-MEASURED 2026-08-22 against the live warehouse,
    because the first numbers here were taken at 11,059 rows and the profile
    crawl has been adding since — a bare figure in a docstring goes stale the
    same week:

        17,304 rows x 34 cols = 24.26 MB
        query 373 ms + json 110 ms          = 483 ms  server
        + 133 ms transfer over 127.0.0.1    = 616 ms  against the panel's
                                              5,000 ms deadline — 12% of it
        then in the browser at 360 px:
        parse 78 ms + Tabulator build 384 ms + paint 23 ms = 485 ms

    So the whole path is ~1.1 s and the request uses an eighth of its budget.
    Pagination is what saves the render: 80 rows reach the DOM, not 17,304.
    A caller that needs a bound still passes one; what changed is that the
    default no longer decides for him.
    """
    resolved = dataset_schema_fields(conn, dataset_key)
    if resolved is None:
        return None
    dataset_id, fields = resolved

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

    # LIMIT only when a caller asked for one. `LIMIT -1` is SQLite's own idiom
    # for no limit and is used rather than building two query strings, so the
    # bounded and unbounded paths cannot drift apart.
    # EVERY FACT THE STATE NEEDS, IN ONE QUERY. `changed_at` is the newest revision
    # for this record, which is what makes `updated` knowable — and it is only
    # meaningful because `R-20` stopped writing a revision when nothing changed.
    # Before that every row had one every crawl and `updated` would have been every
    # row. `LEFT JOIN`, because a record whose only revision is its first has none
    # after it and must not vanish from its own table.
    #
    # STREAMED, AND EXECUTED LAST ON PURPOSE. It used to end in `.fetchall()` up
    # beside the COUNT, which meant every raw `data_json` string stayed live for the
    # whole of the loop below that parses them — two full-population structures in
    # memory at once, plus `sighted` as a third. Measured on a 28-field,
    # 17,304-row fixture: `stored` alone 60 MB, `stored` + `rows` 160 MB, peak with
    # the serialised body 307 MB against a 43 MB wire payload — 7.2x, and that
    # figure EXCLUDES `sighted`. Iterating the cursor drops the first of the three.
    #
    # It is executed here rather than above `newest` so that nothing runs on this
    # connection between opening this cursor and draining it. `conn.execute` hands
    # back a fresh cursor each call and interleaving would in fact be safe, but a
    # reader should not have to know that to trust the function.
    stored = conn.execute(
        "SELECT r.generic_record_id, r.record_key, r.data_json, r.status, "
        "       r.first_seen_at, r.last_seen_at, "
        "       (SELECT MAX(v.observed_at) FROM generic_record_revision AS v "
        "         WHERE v.generic_record_id = r.generic_record_id) AS changed_at "
        "  FROM generic_record AS r WHERE r.dataset_definition_id = ? "
        " ORDER BY r.generic_record_id LIMIT ?",
        (dataset_id, -1 if cap is None else int(cap)))

    rows = []
    for row in stored:
        record = json.loads(row["data_json"])
        external = record.get(identity_field) if identity_field else None
        seen_at, absent_at = sighted.get(str(external), (None, None))
        # BESIDE THE SITE'S FIELDS, NEVER MERGED INTO THEM. These are facts about our
        # OBSERVATION, not facts the site published, and `data_json` is source truth —
        # so they are added to the row the grid renders and never written back.
        record[OBSERVED_RECORD_ID] = row["generic_record_id"]
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

    # THE OWNER'S ARRANGEMENT, AND UNTIL NOW IT WAS IGNORED IN SILENCE. The
    # columns come from `field_definition` — the site's own schema, which is
    # source truth and stays so — but WHICH of them are in the table, what they
    # are called and in what order is his, and it lives in `dataset_field`
    # exactly as it does for products. This function never read it, so hiding a
    # column on a contractor table saved a row and changed nothing on screen:
    # the same defect `extension/datatable.js` warns about in its own comment,
    # in the other direction («dragging a column saved, reloaded the page, and
    # changed nothing, because the grid was reading its own copy»).
    #
    # A HIDDEN COLUMN IS MOVED, NEVER LOST — `R-45`, and `reports.py` already
    # says it for products: "hiding a column is 'move it to the details' and
    # showing it is 'move it back'". So the hidden ones leave `columns` and
    # arrive in `moved_to_details`, which is the list the record card reads.
    #
    # DEGRADES SAFELY ACROSS THE LEGACY SPLIT. `dataset_field` is engine-schema
    # and `general_db_path` "names an engine database like any other", so in the
    # one-database product this is the same file. If some legacy split ever put
    # the presentation rows in the other file, this finds none and every column
    # stays visible — today's behaviour, not a corruption.
    presentation = {row["field_key"]: row for row in list_fields(conn, dataset_key)}
    site_columns = [
        {"key": row["field_key"],
         # His rename wins; otherwise the SITE's name, never the bare key —
         # `field_definition.display_name` is what makes the heading read
         # "Company Name" instead of "company_name".
         "label": ((presentation.get(row["field_key"]) or {}).get("display_name")
                   or row["display_name"] or row["original_name"])}
        for row in fields]
    # His ORDER only once he has actually arranged something, which is the same
    # question `/api/fields` answers as `order_source`. Before that the schema's
    # own `field_order` is the agreed order, and imposing `display_order` would
    # silently reshuffle a table nobody had touched.
    if arranged(conn, dataset_key):
        site_columns.sort(
            key=lambda column: (presentation.get(column["key"]) or {})
            .get("display_order", 0))
    hidden = {key for key, row in presentation.items() if row["is_hidden"]}
    return {
        "source_key": dataset_key,
        "columns": [column for column in site_columns
                    if column["key"] not in hidden]
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
        # The columns he moved OUT of the table, so the record card can show
        # them and nothing is lost by tidying the grid. Populated for the first
        # time here; on the engine's own page nothing renders it yet for a
        # dataset, because that card is gated on `offer_id` and a contractor has
        # none. Stated rather than left to be discovered: this is the DATA half
        # of `REQ-32`, and the card is the other half.
        "moved_to_details": [column for column in site_columns
                             if column["key"] in hidden],
    }
