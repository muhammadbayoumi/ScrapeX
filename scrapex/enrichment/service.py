"""Definitions, facts, materialization and resumable organization jobs."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from .. import catalog, catalog_relations
from ..catalog_models import (
    DatasetCreate,
    FieldCreate,
    RelationshipCreate,
    RelationshipFieldPairCreate,
    RelationshipReviewStatus,
)
from ..payload import utc_now_iso
from ..vocab import JobControl, JobStage, JobStatus, LogLevel, RunMode
from .matching import email_domain, normalized_phone, registrable_domain
from .models import (
    FIELD_ROLES,
    OUTPUT_FIELDS,
    DefinitionCreate,
    EnrichmentRunMode,
    FieldFact,
    OrganizationIdentity,
    OrganizationMergeCreate,
    OrganizationMergeReverseCreate,
    OutputField,
    ReviewDecisionCreate,
)
from .providers import (
    build_providers,
    estimate_requests,
    provider_availability,
    provider_versions,
)


class EnrichmentError(ValueError):
    """A safe refusal that the API can return directly to the extension."""


_SOURCE_BATCH_SIZE = 50
_PROVIDER_CIRCUIT_LIMIT = 3
_RECORD_RETRY_LIMIT = 3


_ROLE_CANDIDATES = {
    "company_name": ("company_name", "organization_name", "firm_name", "name"),
    "company_name_ar": (
        "company_name_ar", "organization_name_ar", "firm_name_ar", "name_ar",
    ),
    "email": ("organization_email", "company_email", "email"),
    "phone": (
        "organization_mobile_number", "organization_phone", "company_phone", "phone",
        "mobile_number", "mobile",
    ),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lng", "lon"),
    "city": ("city", "card_city"),
    "country": ("country", "country_name", "country_code"),
    "profile_url": ("profile_url", "company_url", "record_url"),
    "website": ("website_url", "organization_website", "company_website", "website"),
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dataset(
    conn: sqlite3.Connection, key: str, site_key: str | None = None
) -> sqlite3.Row:
    sql = (
        "SELECT d.*, s.source_key AS site_key, "
        "s.source_name AS site_display_name, s.base_url "
        "FROM dataset_definition AS d JOIN source_site AS s "
        "ON s.source_id = d.source_id "
        "WHERE d.dataset_key = ? AND d.valid_to IS NULL AND s.valid_to IS NULL "
    )
    parameters: tuple[str, ...] = (key,)
    if site_key:
        sql += "AND s.source_key = ? "
        parameters += (site_key,)
    rows = conn.execute(
        sql + "ORDER BY d.dataset_definition_id LIMIT 2", parameters
    ).fetchall()
    if not rows:
        scope = f" for site {site_key!r}" if site_key else ""
        raise EnrichmentError(f"unknown active dataset {key!r}{scope}")
    if len(rows) > 1:
        sites = ", ".join(repr(row["site_key"]) for row in rows)
        raise EnrichmentError(
            f"dataset key {key!r} is ambiguous across sites {sites}; provide site_key"
        )
    return rows[0]


def _fields(conn: sqlite3.Connection, dataset_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT f.field_definition_id, f.field_key, f.original_name, f.display_name, "
        "f.data_type, f.identity_role, svf.field_order "
        "FROM dataset_schema_version AS sv "
        "JOIN schema_version_field AS svf "
        "ON svf.schema_version_id = sv.schema_version_id "
        "JOIN field_definition AS f "
        "ON f.field_definition_id = svf.field_definition_id "
        "WHERE sv.dataset_definition_id = ? AND sv.valid_to IS NULL "
        "ORDER BY svf.field_order",
        (dataset_id,),
    ).fetchall()
    return [{**dict(row), "label": row["display_name"] or row["original_name"]}
            for row in rows]


def _suggest(fields: list[dict[str, Any]], scope: str = "") -> dict[str, str]:
    keys = {str(field["field_key"]).casefold(): str(field["field_key"])
            for field in fields}
    result: dict[str, str] = {}
    for role, candidates in _ROLE_CANDIDATES.items():
        for candidate in candidates:
            if candidate in keys:
                result[role] = f"{scope}:{keys[candidate]}" if scope else keys[candidate]
                break
    return result


def _definition_row(conn: sqlite3.Connection, definition_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT e.*, s.source_key AS site_key, "
        "s.source_name AS site_display_name, s.base_url, "
        "source.dataset_key AS source_dataset_key, "
        "detail.dataset_key AS detail_dataset_key, "
        "output.dataset_key AS output_dataset_key, "
        "output.display_name AS output_display_name, "
        "output.original_name AS output_original_name "
        "FROM organization_enrichment_definition AS e "
        "JOIN source_site AS s ON s.source_id = e.source_id "
        "JOIN dataset_definition AS source "
        "ON source.dataset_definition_id = e.source_dataset_id "
        "LEFT JOIN dataset_definition AS detail "
        "ON detail.dataset_definition_id = e.detail_dataset_id "
        "JOIN dataset_definition AS output "
        "ON output.dataset_definition_id = e.output_dataset_id "
        "WHERE e.enrichment_definition_id = ? LIMIT 1",
        (definition_id,),
    ).fetchone()
    if row is None:
        raise EnrichmentError(f"unknown enrichment definition {definition_id}")
    return row


def _definition_public(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    counts = conn.execute(
        "SELECT count(*) AS organizations, "
        "sum(CASE WHEN json_extract(r.data_json, '$.verification_status') = 'verified' "
        "THEN 1 ELSE 0 END) AS verified, "
        "sum(CASE WHEN json_extract(r.data_json, '$.manual_review_status') = 'open' "
        "THEN 1 ELSE 0 END) AS needs_review "
        "FROM generic_record AS r WHERE r.dataset_definition_id = ? "
        "AND r.status = 'active'",
        (row["output_dataset_id"],),
    ).fetchone()
    latest_job = conn.execute(
        "SELECT j.job_ref, j.status FROM organization_enrichment_job AS e "
        "JOIN crawl_job AS j ON j.job_id = e.job_id "
        "WHERE e.enrichment_definition_id = ? ORDER BY j.job_id DESC LIMIT 1",
        (row["enrichment_definition_id"],),
    ).fetchone()
    return {
        "enrichment_definition_id": row["enrichment_definition_id"],
        "site_key": row["site_key"],
        "site_display_name": row["site_display_name"],
        "source_dataset_key": row["source_dataset_key"],
        "detail_dataset_key": row["detail_dataset_key"],
        "output_dataset_key": row["output_dataset_key"],
        "output_dataset_name": row["output_display_name"] or row["output_original_name"],
        "entity_key_field": row["entity_key_field"],
        "detail_key_field": row["detail_key_field"],
        "field_mapping": json.loads(row["field_mapping_json"]),
        "providers": json.loads(row["providers_json"]),
        "configuration_version": int(row["configuration_version"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_run_at": row["last_run_at"],
        "latest_job": dict(latest_job) if latest_job is not None else None,
        "counts": {
            "organizations": int(counts["organizations"] or 0),
            "verified": int(counts["verified"] or 0),
            "needs_review": int(counts["needs_review"] or 0),
        },
    }


def get_definition(conn: sqlite3.Connection, definition_id: int) -> dict[str, Any]:
    row = _definition_row(conn, definition_id)
    return _definition_public(conn, row)


def _existing_for_source(
    conn: sqlite3.Connection, source_dataset_id: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT enrichment_definition_id "
        "FROM organization_enrichment_definition WHERE source_dataset_id = ? "
        "LIMIT 1",
        (source_dataset_id,),
    ).fetchone()
    return get_definition(conn, int(row[0])) if row else None


def propose_definition(
    conn: sqlite3.Connection,
    source_dataset_key: str,
    *,
    site_key: str | None = None,
) -> dict[str, Any]:
    source = _dataset(conn, source_dataset_key, site_key)
    if json.loads(source["locator_json"] or "{}").get("kind") == \
            "organization_enrichment":
        raise EnrichmentError("an enrichment output cannot be used as its own source")
    site_id = int(source["source_id"])
    rows = conn.execute(
        "SELECT d.dataset_definition_id, d.dataset_key, d.original_name, d.display_name, "
        "d.dataset_kind, d.locator_json "
        "FROM dataset_definition AS d WHERE d.source_id = ? "
        "AND d.valid_to IS NULL ORDER BY d.dataset_definition_id",
        (site_id,),
    ).fetchall()
    datasets = []
    for row in rows:
        locator = json.loads(row["locator_json"] or "{}")
        if locator.get("kind") == "organization_enrichment":
            continue
        fields = _fields(conn, int(row["dataset_definition_id"]))
        datasets.append({
            "dataset_definition_id": row["dataset_definition_id"],
            "dataset_key": row["dataset_key"],
            "label": row["display_name"] or row["original_name"],
            "dataset_kind": row["dataset_kind"],
            "fields": fields,
        })
    by_id = {item["dataset_definition_id"]: item for item in datasets}
    related = conn.execute(
        "SELECT child_dataset_id FROM dataset_relationship "
        "WHERE parent_dataset_id = ? AND cardinality = 'one_to_one' "
        "AND review_status = 'confirmed' AND valid_to IS NULL "
        "ORDER BY dataset_relationship_id",
        (source["dataset_definition_id"],),
    ).fetchall()
    detail = next((by_id.get(int(row[0])) for row in related
                   if by_id.get(int(row[0]))), None)
    primary_fields = next(
        item["fields"] for item in datasets
        if item["dataset_definition_id"] == source["dataset_definition_id"]
    )
    detail_fields = detail["fields"] if detail else []
    mapping = _suggest(primary_fields, "source")
    mapping.update(_suggest(detail_fields, "detail"))
    # The listing's names are more useful than a detail page that may not carry
    # a title at all. Detail wins for contacts and coordinates, not by accident
    # of update order for identity labels.
    primary_suggestion = _suggest(primary_fields, "source")
    for role in ("company_name", "company_name_ar", "profile_url"):
        if primary_suggestion.get(role):
            mapping[role] = primary_suggestion[role]
    identity = next(
        (field["field_key"] for field in primary_fields
         if field["identity_role"] == "key_part"),
        primary_fields[0]["field_key"] if primary_fields else "",
    )
    detail_keys = {field["field_key"] for field in detail_fields}
    detail_key = identity if identity in detail_keys else next(
        (field["field_key"] for field in detail_fields
         if field["identity_role"] == "key_part"), None,
    )
    preflight = _preflight_source(
        conn,
        int(source["dataset_definition_id"]),
        identity,
        int(detail["dataset_definition_id"]) if detail and detail_key else None,
        detail_key,
    )
    return {
        "site": {
            "site_key": source["site_key"],
            "display_name": source["site_display_name"],
            "base_url": source["base_url"],
        },
        "datasets": datasets,
        "proposal": {
            "site_key": source["site_key"],
            "source_dataset_key": source_dataset_key,
            "detail_dataset_key": detail["dataset_key"] if detail else None,
            "output_dataset_key": _default_output_key(source_dataset_key),
            "output_dataset_name": "Organization Enrichment",
            "entity_key_field": identity,
            "detail_key_field": detail_key,
            "field_mapping": mapping,
            # Paid providers are always an explicit opt-in, even when their
            # credential is configured on this engine.
            "providers": ["website"],
        },
        "field_roles": list(FIELD_ROLES),
        "provider_availability": provider_availability(),
        "preflight": preflight,
        "estimated_requests": estimate_requests(
            ["website"], int(preflight["source_records"])
        ),
        "definition": _existing_for_source(
            conn, int(source["dataset_definition_id"])
        ),
    }


def _default_output_key(source_key: str) -> str:
    if source_key.endswith("ies"):
        stem = source_key[:-3] + "y"
    elif source_key.endswith("s") and not source_key.endswith("ss"):
        stem = source_key[:-1]
    else:
        stem = source_key
    suffix = "_enrichment"
    return f"{stem[:64 - len(suffix)]}{suffix}"


def _field_id(conn: sqlite3.Connection, dataset_id: int, field_key: str) -> int:
    row = conn.execute(
        "SELECT field_definition_id FROM field_definition "
        "WHERE dataset_definition_id = ? AND field_key = ? AND valid_to IS NULL",
        (dataset_id, field_key),
    ).fetchone()
    if row is None:
        raise EnrichmentError(
            f"field {field_key!r} does not belong to dataset {dataset_id}"
        )
    return int(row[0])


def _field_reference(reference: str) -> tuple[str, str]:
    scope, separator, key = str(reference or "").partition(":")
    if separator and scope in ("source", "detail"):
        return scope, key
    return "", str(reference or "")


def _preflight_source(
    conn: sqlite3.Connection,
    source_dataset_id: int,
    entity_key_field: str,
    detail_dataset_id: int | None = None,
    detail_key_field: str | None = None,
) -> dict[str, Any]:
    total = missing_identity = duplicate_identities = 0
    identities: set[str] = set()
    duplicate_identity_samples: list[str] = []
    for row in conn.execute(
        "SELECT data_json FROM generic_record WHERE dataset_definition_id = ? "
        "AND status = 'active'",
        (source_dataset_id,),
    ):
        total += 1
        data = json.loads(row[0])
        key = str(data.get(entity_key_field) or "").strip()
        if not key:
            missing_identity += 1
        elif key in identities:
            duplicate_identities += 1
            if len(duplicate_identity_samples) < 10:
                duplicate_identity_samples.append(key)
        else:
            identities.add(key)

    detail_total = duplicate_detail_keys = matched_detail = 0
    duplicate_detail_samples: list[str] = []
    detail_keys: set[str] = set()
    if detail_dataset_id is not None and detail_key_field:
        for row in conn.execute(
            "SELECT data_json FROM generic_record WHERE dataset_definition_id = ? "
            "AND status = 'active'",
            (detail_dataset_id,),
        ):
            detail_total += 1
            data = json.loads(row[0])
            key = str(data.get(detail_key_field) or "").strip()
            if not key:
                continue
            if key in detail_keys:
                duplicate_detail_keys += 1
                if len(duplicate_detail_samples) < 10:
                    duplicate_detail_samples.append(key)
            detail_keys.add(key)
        matched_detail = len(identities & detail_keys)

    return {
        "source_records": total,
        "identity_present": total - missing_identity,
        "missing_identity": missing_identity,
        "duplicate_identity_count": duplicate_identities,
        "duplicate_identity_samples": duplicate_identity_samples,
        "detail_records": detail_total,
        "duplicate_detail_keys": duplicate_detail_keys,
        "duplicate_detail_samples": duplicate_detail_samples,
        "matched_detail_records": matched_detail,
        "detail_join_coverage": round(matched_detail / total, 4) if total else 0.0,
    }


def _assert_preflight(preflight: dict[str, Any]) -> None:
    if preflight["missing_identity"]:
        raise EnrichmentError(
            f"entity key is empty in {preflight['missing_identity']} active source record(s)"
        )
    if preflight["duplicate_identity_samples"]:
        raise EnrichmentError(
            "entity key is not unique; duplicate samples: "
            + ", ".join(repr(item) for item in preflight["duplicate_identity_samples"])
        )
    if preflight["duplicate_detail_keys"]:
        raise EnrichmentError(
            "detail join key is not unique; duplicate samples: "
            + ", ".join(repr(item) for item in preflight["duplicate_detail_samples"])
        )


def _create_output_schema(conn: sqlite3.Connection, dataset_id: int) -> int:
    payload = [{"field_key": item.key, "data_type": item.data_type,
                "identity": item.identity, "position": position}
               for position, item in enumerate(OUTPUT_FIELDS)]
    schema_hash = _digest(payload)
    active = conn.execute(
        "SELECT schema_version_id, schema_hash FROM dataset_schema_version "
        "WHERE dataset_definition_id = ? AND valid_to IS NULL LIMIT 1",
        (dataset_id,),
    ).fetchone()
    if active is not None and active["schema_hash"] == schema_hash:
        return int(active["schema_version_id"])
    version = int(conn.execute(
        "SELECT coalesce(max(version_number), 0) + 1 FROM dataset_schema_version "
        "WHERE dataset_definition_id = ?",
        (dataset_id,),
    ).fetchone()[0])
    fields: list[tuple[int, OutputField]] = []
    for position, item in enumerate(OUTPUT_FIELDS):
        field = catalog.register_field(
            conn,
            dataset_id,
            FieldCreate(
                field_key=item.key,
                original_name=item.key,
                data_type=item.data_type,
                is_nullable=not item.identity,
                identity_role="key_part" if item.identity else "none",
                display_order=position,
            ),
        )
        conn.execute(
            "UPDATE field_definition SET display_name = ?, display_order = ? "
            "WHERE field_definition_id = ?",
            (item.key, position, field["field_definition_id"]),
        )
        fields.append((int(field["field_definition_id"]), item))
    if active is not None:
        conn.execute(
            "UPDATE dataset_schema_version SET valid_to = ?, status = 'retired' "
            "WHERE schema_version_id = ?",
            (utc_now_iso(), active["schema_version_id"]),
        )
    cursor = conn.execute(
        "INSERT INTO dataset_schema_version "
        "(dataset_definition_id, version_number, schema_hash) VALUES (?,?,?)",
        (dataset_id, version, schema_hash),
    )
    schema_id = int(cursor.lastrowid)
    for position, (field_id, _) in enumerate(fields):
        conn.execute(
            "INSERT INTO schema_version_field "
            "(schema_version_id, field_definition_id, field_order) VALUES (?,?,?)",
            (schema_id, field_id, position),
        )
    return schema_id


def create_definition(
    conn: sqlite3.Connection, request: DefinitionCreate
) -> dict[str, Any]:
    source = _dataset(conn, request.source_dataset_key, request.site_key)
    if json.loads(source["locator_json"] or "{}").get("kind") == \
            "organization_enrichment":
        raise EnrichmentError("an enrichment output cannot be used as its own source")
    existing = _existing_for_source(conn, int(source["dataset_definition_id"]))
    if existing is not None:
        proposed_output_key = request.output_dataset_key or _default_output_key(
            request.source_dataset_key
        )
        proposed_output_name = request.output_dataset_name or "Organization Enrichment"
        same_definition = (
            existing["detail_dataset_key"] == request.detail_dataset_key
            and existing["output_dataset_key"] == proposed_output_key
            and existing["output_dataset_name"] == proposed_output_name
            and existing["entity_key_field"] == request.entity_key_field
            and existing["detail_key_field"] == request.detail_key_field
            and existing["field_mapping"] == request.field_mapping
            and sorted(existing["providers"])
            == sorted(str(item) for item in request.providers)
        )
        if not same_definition:
            raise EnrichmentError(
                "this source already has a different enrichment definition"
            )
        return existing
    source_fields = {item["field_key"] for item in _fields(
        conn, int(source["dataset_definition_id"])
    )}
    if request.entity_key_field not in source_fields:
        raise EnrichmentError(
            f"entity key {request.entity_key_field!r} is not in the source dataset"
        )
    detail = _dataset(conn, request.detail_dataset_key, str(source["site_key"])) \
        if request.detail_dataset_key else None
    detail_fields: set[str] = set()
    if detail is not None:
        if detail["dataset_definition_id"] == source["dataset_definition_id"]:
            raise EnrichmentError("source and detail datasets must be different")
        if detail["source_id"] != source["source_id"]:
            raise EnrichmentError("source and detail datasets must belong to one site")
        detail_fields = {item["field_key"] for item in _fields(
            conn, int(detail["dataset_definition_id"])
        )}
        if request.detail_key_field not in detail_fields:
            raise EnrichmentError(
                f"detail key {request.detail_key_field!r} is not in the detail dataset"
            )
    missing = []
    for reference in request.field_mapping.values():
        scope, key = _field_reference(reference)
        exists = key in source_fields if scope == "source" else (
            key in detail_fields if scope == "detail" else
            key in source_fields or key in detail_fields
        )
        if not exists:
            missing.append(reference)
        if scope == "detail" and detail is None:
            missing.append(reference)
    missing = sorted(set(missing))
    if missing:
        raise EnrichmentError(f"mapped fields do not exist in the selected datasets: {missing}")
    preflight = _preflight_source(
        conn,
        int(source["dataset_definition_id"]),
        str(request.entity_key_field),
        int(detail["dataset_definition_id"]) if detail is not None else None,
        str(request.detail_key_field) if request.detail_key_field else None,
    )
    _assert_preflight(preflight)
    available_providers = {item["key"] for item in provider_availability()
                           if item["available"]}
    unavailable = sorted(str(item) for item in request.providers
                         if str(item) not in available_providers)
    if unavailable:
        raise EnrichmentError(f"enrichment providers are not configured: {unavailable}")

    output_key = request.output_dataset_key or _default_output_key(
        request.source_dataset_key
    )
    output_name = request.output_dataset_name or "Organization Enrichment"
    occupied = conn.execute(
        "SELECT dataset_definition_id FROM dataset_definition "
        "WHERE source_id = ? AND dataset_key = ? LIMIT 1",
        (source["source_id"], output_key),
    ).fetchone()
    if occupied is not None:
        raise EnrichmentError(
            f"output dataset key {output_key!r} is already in use; choose a new key"
        )
    output = catalog.register_dataset(
        conn,
        str(source["site_key"]),
        DatasetCreate(
            dataset_key=output_key,
            original_name=output_name,
            dataset_kind="detail",
            discovery_method="inferred",
            locator={
                "kind": "organization_enrichment",
                "source_dataset_key": request.source_dataset_key,
                "detail_dataset_key": request.detail_dataset_key,
            },
        ),
    )
    output_id = int(output["dataset_definition_id"])
    conn.execute(
        "UPDATE dataset_definition SET display_name = ? "
        "WHERE dataset_definition_id = ?",
        (output_name, output_id),
    )
    _create_output_schema(conn, output_id)
    parent_field_id = _field_id(
        conn, int(source["dataset_definition_id"]), request.entity_key_field
    )
    child_field_id = _field_id(conn, output_id, "source_external_id")
    relationship_key = f"{request.source_dataset_key}_to_{output_key}"[:64]
    catalog_relations.propose_relationship(
        conn,
        str(source["site_key"]),
        RelationshipCreate(
            relationship_key=relationship_key,
            parent_dataset_id=int(source["dataset_definition_id"]),
            child_dataset_id=output_id,
            cardinality="one_to_one",
            confidence=1.0,
            evidence={
                "kind": "organization_enrichment",
                "created_by": "owner_reviewed_mapping",
            },
            field_pairs=[RelationshipFieldPairCreate(
                parent_field_id=parent_field_id,
                child_field_id=child_field_id,
            )],
        ),
    )
    catalog_relations.review_relationship(
        conn,
        str(source["site_key"]),
        relationship_key,
        status=RelationshipReviewStatus.CONFIRMED,
    )
    cursor = conn.execute(
        "INSERT INTO organization_enrichment_definition "
        "(source_id, source_dataset_id, detail_dataset_id, output_dataset_id, "
        "entity_key_field, detail_key_field, field_mapping_json, providers_json) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            source["source_id"],
            source["dataset_definition_id"],
            detail["dataset_definition_id"] if detail is not None else None,
            output_id,
            request.entity_key_field,
            request.detail_key_field,
            _canonical(request.field_mapping),
            _canonical([str(item) for item in request.providers]),
        ),
    )
    return get_definition(conn, int(cursor.lastrowid))


def update_definition(
    conn: sqlite3.Connection, definition_id: int, request: DefinitionCreate
) -> dict[str, Any]:
    """Create a new immutable configuration version on the existing output."""
    current = _definition_row(conn, definition_id)
    if current["status"] == "retired":
        raise EnrichmentError("a retired enrichment definition cannot be edited")
    if request.source_dataset_key != current["source_dataset_key"]:
        raise EnrichmentError("an enrichment definition cannot move to another source")
    if request.site_key and request.site_key != current["site_key"]:
        raise EnrichmentError("an enrichment definition cannot move to another site")
    proposed_output_key = request.output_dataset_key or current["output_dataset_key"]
    if proposed_output_key != current["output_dataset_key"]:
        raise EnrichmentError("an enrichment definition cannot replace its output dataset")
    active = conn.execute(
        "SELECT j.job_ref FROM organization_enrichment_job AS e "
        "JOIN crawl_job AS j ON j.job_id = e.job_id "
        "WHERE e.enrichment_definition_id = ? AND j.status NOT IN "
        "('cancelled','completed','completed_with_errors','partially_completed','failed') "
        "LIMIT 1",
        (definition_id,),
    ).fetchone()
    if active is not None:
        raise EnrichmentError(
            f"enrichment job {active['job_ref']} is active; update after it finishes"
        )

    source_fields = {item["field_key"] for item in _fields(
        conn, int(current["source_dataset_id"])
    )}
    if request.entity_key_field not in source_fields:
        raise EnrichmentError(
            f"entity key {request.entity_key_field!r} is not in the source dataset"
        )
    detail = _dataset(conn, request.detail_dataset_key, str(current["site_key"])) \
        if request.detail_dataset_key else None
    detail_fields = {item["field_key"] for item in _fields(
        conn, int(detail["dataset_definition_id"])
    )} if detail is not None else set()
    if detail is not None and request.detail_key_field not in detail_fields:
        raise EnrichmentError(
            f"detail key {request.detail_key_field!r} is not in the detail dataset"
        )
    missing = []
    for reference in request.field_mapping.values():
        scope, key = _field_reference(reference)
        exists = key in source_fields if scope == "source" else (
            key in detail_fields if scope == "detail" else
            key in source_fields or key in detail_fields
        )
        if not exists:
            missing.append(reference)
    if missing:
        raise EnrichmentError(
            f"mapped fields do not exist in the selected datasets: {sorted(set(missing))}"
        )
    available = {item["key"] for item in provider_availability() if item["available"]}
    unavailable = sorted(set(request.providers) - available)
    if unavailable:
        raise EnrichmentError(f"enrichment providers are not configured: {unavailable}")
    preflight = _preflight_source(
        conn, int(current["source_dataset_id"]), str(request.entity_key_field),
        int(detail["dataset_definition_id"]) if detail is not None else None,
        str(request.detail_key_field) if request.detail_key_field else None,
    )
    _assert_preflight(preflight)

    proposed = {
        "detail_dataset_key": request.detail_dataset_key,
        "output_dataset_key": current["output_dataset_key"],
        "output_dataset_name": request.output_dataset_name
        or current["output_display_name"] or current["output_original_name"],
        "entity_key_field": str(request.entity_key_field),
        "detail_key_field": str(request.detail_key_field)
        if request.detail_key_field else None,
        "field_mapping": request.field_mapping,
        "providers": list(request.providers),
    }
    existing_public = get_definition(conn, definition_id)
    if all(existing_public.get(key) == value for key, value in proposed.items()):
        return existing_public

    conn.execute(
        "INSERT INTO organization_enrichment_definition_history "
        "(enrichment_definition_id, configuration_version, definition_json) "
        "VALUES (?,?,?)",
        (
            definition_id, current["configuration_version"],
            _canonical(_definition_snapshot(current)),
        ),
    )
    output_name = str(proposed["output_dataset_name"])
    conn.execute(
        "UPDATE organization_enrichment_definition SET detail_dataset_id=?, "
        "entity_key_field=?, detail_key_field=?, field_mapping_json=?, "
        "providers_json=?, status='active', configuration_version="
        "configuration_version+1, updated_at=? WHERE enrichment_definition_id=?",
        (
            detail["dataset_definition_id"] if detail is not None else None,
            request.entity_key_field, request.detail_key_field,
            _canonical(request.field_mapping), _canonical(list(request.providers)),
            utc_now_iso(), definition_id,
        ),
    )
    conn.execute(
        "UPDATE dataset_definition SET display_name = ? WHERE dataset_definition_id = ?",
        (output_name, current["output_dataset_id"]),
    )
    _create_output_schema(conn, int(current["output_dataset_id"]))
    return get_definition(conn, definition_id)


def set_definition_status(
    conn: sqlite3.Connection, definition_id: int, status: str
) -> dict[str, Any]:
    if status not in ("active", "paused", "retired"):
        raise EnrichmentError(f"unknown enrichment definition status {status!r}")
    definition = _definition_row(conn, definition_id)
    if definition["status"] == status:
        return get_definition(conn, definition_id)
    active = conn.execute(
        "SELECT j.job_ref FROM organization_enrichment_job AS e "
        "JOIN crawl_job AS j ON j.job_id=e.job_id "
        "WHERE e.enrichment_definition_id=? AND j.status NOT IN "
        "('cancelled','completed','completed_with_errors','partially_completed','failed') "
        "LIMIT 1",
        (definition_id,),
    ).fetchone()
    if active is not None:
        raise EnrichmentError(
            f"enrichment job {active['job_ref']} is active; change status after it finishes"
        )
    conn.execute(
        "UPDATE organization_enrichment_definition SET status=?, updated_at=? "
        "WHERE enrichment_definition_id=?",
        (status, utc_now_iso(), definition_id),
    )
    return get_definition(conn, definition_id)


def _definition_snapshot(definition: sqlite3.Row) -> dict[str, Any]:
    return {
        "enrichment_definition_id": int(definition["enrichment_definition_id"]),
        "configuration_version": int(definition["configuration_version"]),
        "site_key": str(definition["site_key"]),
        "base_url": str(definition["base_url"]),
        "source_dataset_key": str(definition["source_dataset_key"]),
        "detail_dataset_key": definition["detail_dataset_key"],
        "output_dataset_key": str(definition["output_dataset_key"]),
        "entity_key_field": str(definition["entity_key_field"]),
        "detail_key_field": definition["detail_key_field"],
        "field_mapping": json.loads(definition["field_mapping_json"] or "{}"),
        "providers": json.loads(definition["providers_json"] or "[]"),
    }


def _json_path(field_key: str) -> str:
    return '$."' + field_key.replace('"', '\\"') + '"'


def _snapshot_run_items(
    conn: sqlite3.Connection, job_id: int, definition: sqlite3.Row
) -> int:
    source_path = _json_path(str(definition["entity_key_field"]))
    if definition["detail_dataset_id"] is None:
        conn.execute(
            "INSERT INTO organization_enrichment_run_item "
            "(job_id, generic_record_id, source_snapshot_id, source_data_json, "
            "source_content_hash, source_url, source_external_id) "
            "SELECT ?, source.generic_record_id, source.source_snapshot_id, "
            "source.data_json, source.content_hash, page.source_url, "
            "trim(CAST(json_extract(source.data_json, ?) AS TEXT)) "
            "FROM generic_record AS source "
            "JOIN generic_page_snapshot AS page "
            "ON page.page_snapshot_id = source.source_snapshot_id "
            "WHERE source.dataset_definition_id = ? AND source.status = 'active'",
            (job_id, source_path, definition["source_dataset_id"]),
        )
    else:
        detail_path = _json_path(str(definition["detail_key_field"]))
        # JSON expressions on both sides of a direct join force SQLite into an
        # O(source x detail) scan.  Build a connection-local indexed lookup so
        # large listing/profile datasets remain linear without loading every
        # detail row into Python memory.
        conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS enrichment_detail_snapshot ("
            "join_key TEXT PRIMARY KEY, data_json TEXT NOT NULL, "
            "content_hash TEXT NOT NULL) WITHOUT ROWID"
        )
        conn.execute("DELETE FROM enrichment_detail_snapshot")
        try:
            conn.execute(
                "INSERT INTO enrichment_detail_snapshot "
                "(join_key, data_json, content_hash) "
                "SELECT trim(CAST(json_extract(data_json, ?) AS TEXT)), data_json, "
                "content_hash "
                "FROM generic_record WHERE dataset_definition_id = ? "
                "AND status = 'active' "
                "AND trim(CAST(json_extract(data_json, ?) AS TEXT)) <> ''",
                (detail_path, definition["detail_dataset_id"], detail_path),
            )
            conn.execute(
                "INSERT INTO organization_enrichment_run_item "
                "(job_id, generic_record_id, source_snapshot_id, source_data_json, "
                "source_content_hash, detail_data_json, detail_content_hash, "
                "source_url, source_external_id) "
                "SELECT ?, source.generic_record_id, source.source_snapshot_id, "
                "source.data_json, source.content_hash, detail.data_json, "
                "detail.content_hash, page.source_url, "
                "trim(CAST(json_extract(source.data_json, ?) AS TEXT)) "
                "FROM generic_record AS source "
                "JOIN generic_page_snapshot AS page "
                "ON page.page_snapshot_id = source.source_snapshot_id "
                "LEFT JOIN enrichment_detail_snapshot AS detail "
                "ON detail.join_key = "
                "trim(CAST(json_extract(source.data_json, ?) AS TEXT)) "
                "WHERE source.dataset_definition_id = ? AND source.status = 'active'",
                (
                    job_id, source_path, source_path,
                    definition["source_dataset_id"],
                ),
            )
        finally:
            conn.execute("DROP TABLE IF EXISTS enrichment_detail_snapshot")
    return int(conn.execute(
        "SELECT count(*) FROM organization_enrichment_run_item WHERE job_id = ?",
        (job_id,),
    ).fetchone()[0])


def _compatible_incremental_baseline(
    conn: sqlite3.Connection,
    *,
    definition_id: int,
    before_job_id: int,
    definition_json: str,
    provider_versions_json: str,
) -> sqlite3.Row | None:
    """Return the latest finished snapshot that is safe to increment from."""
    return conn.execute(
        "SELECT e.job_id, j.job_ref FROM organization_enrichment_job AS e "
        "JOIN crawl_job AS j ON j.job_id=e.job_id "
        "WHERE e.enrichment_definition_id=? AND e.job_id<? "
        "AND e.definition_json=? AND e.provider_versions_json=? "
        "AND j.status IN ('completed','completed_with_errors','partially_completed') "
        "ORDER BY e.job_id DESC LIMIT 1",
        (
            definition_id,
            before_job_id,
            definition_json,
            provider_versions_json,
        ),
    ).fetchone()


def _keep_incremental_run_items(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    definition_id: int,
    definition_json: str,
    provider_versions_json: str,
) -> int:
    """Drop inputs unchanged since their latest compatible finished attempt."""
    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS enrichment_incremental_latest ("
        "source_external_id TEXT PRIMARY KEY, job_id INTEGER NOT NULL) WITHOUT ROWID"
    )
    conn.execute("DELETE FROM enrichment_incremental_latest")
    try:
        conn.execute(
            "INSERT INTO enrichment_incremental_latest (source_external_id, job_id) "
            "SELECT item.source_external_id, max(item.job_id) "
            "FROM organization_enrichment_run_item AS item "
            "JOIN organization_enrichment_job AS enrichment_job "
            "ON enrichment_job.job_id=item.job_id "
            "JOIN crawl_job AS crawl ON crawl.job_id=item.job_id "
            "WHERE enrichment_job.enrichment_definition_id=? AND item.job_id<? "
            "AND enrichment_job.definition_json=? "
            "AND enrichment_job.provider_versions_json=? "
            "AND crawl.status IN "
            "('completed','completed_with_errors','partially_completed') "
            "GROUP BY item.source_external_id",
            (definition_id, job_id, definition_json, provider_versions_json),
        )
        conn.execute(
            "DELETE FROM organization_enrichment_run_item AS current "
            "WHERE current.job_id=? AND EXISTS ("
            "SELECT 1 FROM enrichment_incremental_latest AS latest "
            "JOIN organization_enrichment_run_item AS previous "
            "ON previous.job_id=latest.job_id "
            "AND previous.source_external_id=latest.source_external_id "
            "WHERE latest.source_external_id=current.source_external_id "
            "AND previous.source_content_hash=current.source_content_hash "
            "AND coalesce(previous.detail_content_hash,'')="
            "coalesce(current.detail_content_hash,'') "
            "AND previous.item_status='completed' AND NOT EXISTS ("
            "SELECT 1 FROM organization_source_record AS link "
            "JOIN organization_provider_observation AS observation "
            "ON observation.organization_id=link.organization_id "
            "AND observation.job_id=previous.job_id "
            "WHERE link.enrichment_definition_id=? "
            "AND link.generic_record_id=previous.generic_record_id "
            "AND observation.observation_status IN "
            "('failed','system_error','skipped')"
            "))",
            (job_id, definition_id),
        )
    finally:
        conn.execute("DROP TABLE IF EXISTS enrichment_incremental_latest")
    return int(conn.execute(
        "SELECT count(*) FROM organization_enrichment_run_item WHERE job_id=?",
        (job_id,),
    ).fetchone()[0])


def estimate_definition_run(
    conn: sqlite3.Connection, definition_id: int
) -> dict[str, Any]:
    definition = _definition_row(conn, definition_id)
    organizations = int(conn.execute(
        "SELECT count(*) FROM generic_record WHERE dataset_definition_id = ? "
        "AND status = 'active'",
        (definition["source_dataset_id"],),
    ).fetchone()[0])
    names = json.loads(definition["providers_json"] or "[]")
    return {
        "organizations": organizations,
        "providers": names,
        "estimated_requests": estimate_requests(names, organizations),
        "estimate_is_upper_bound": True,
    }


def definition_diagnostics(
    conn: sqlite3.Connection, definition_id: int
) -> dict[str, Any]:
    definition = _definition_row(conn, definition_id)
    latest = conn.execute(
        "SELECT e.job_id, j.job_ref, j.status, e.provider_versions_json, "
        "e.estimated_requests FROM organization_enrichment_job AS e "
        "JOIN crawl_job AS j ON j.job_id=e.job_id "
        "WHERE e.enrichment_definition_id=? ORDER BY e.job_id DESC LIMIT 1",
        (definition_id,),
    ).fetchone()
    providers = []
    if latest is not None:
        providers = [dict(row) for row in conn.execute(
            "SELECT provider, observation_status, count(*) AS organizations, "
            "sum(request_count) AS requests, "
            "round(avg(latency_ms), 1) AS average_latency_ms "
            "FROM organization_provider_observation WHERE job_id=? "
            "GROUP BY provider, observation_status ORDER BY provider, observation_status",
            (latest["job_id"],),
        )]
    durable_google_content = int(conn.execute(
        "SELECT count(*) FROM organization_fact AS fact "
        "JOIN organization_source_record AS link "
        "ON link.organization_id=fact.organization_id "
        "WHERE link.enrichment_definition_id=? AND fact.provider='google_places' "
        "AND fact.field_key NOT IN ('google_place_id','google_attribution')",
        (definition_id,),
    ).fetchone()[0])
    legacy_output_paths = (
        "$.google_maps_url", "$.google_maps_cid_url", "$.google_business_name",
        "$.google_formatted_address", "$.google_phone", "$.google_website",
        "$.google_business_status", "$.gmaps_rating", "$.reviews_count",
        "$.google_match_status", "$.google_match_score",
    )
    legacy_output_condition = " OR ".join(
        "json_extract(data_json, ?) IS NOT NULL" for _ in legacy_output_paths
    )
    legacy_revision_condition = " OR ".join(
        "json_extract(revision.data_json, ?) IS NOT NULL"
        for _ in legacy_output_paths
    )
    legacy_output_rows = int(conn.execute(
        "SELECT count(*) FROM generic_record WHERE dataset_definition_id=? AND ("
        + legacy_output_condition + ")",
        (definition["output_dataset_id"], *legacy_output_paths),
    ).fetchone()[0])
    legacy_output_revisions = int(conn.execute(
        "SELECT count(*) FROM generic_record_revision AS revision "
        "JOIN generic_record AS record "
        "ON record.generic_record_id=revision.generic_record_id "
        "WHERE record.dataset_definition_id=? AND (" + legacy_revision_condition + ")",
        (definition["output_dataset_id"], *legacy_output_paths),
    ).fetchone()[0])
    return {
        "definition_id": definition_id,
        "configuration_version": int(definition["configuration_version"]),
        "estimate": estimate_definition_run(conn, definition_id),
        "latest_job": ({
            "job_ref": latest["job_ref"],
            "status": latest["status"],
            "provider_versions": json.loads(latest["provider_versions_json"] or "{}"),
            "estimated_requests": int(latest["estimated_requests"] or 0),
        } if latest is not None else None),
        "provider_observations": providers,
        "compliance": {
            "google_storage_mode": "place_id_only",
            "legacy_durable_google_fact_count": durable_google_content,
            "legacy_google_output_row_count": legacy_output_rows,
            "legacy_google_output_revision_count": legacy_output_revisions,
            "requires_owner_cleanup": any((
                durable_google_content, legacy_output_rows, legacy_output_revisions,
            )),
        },
    }


def create_enrichment_job(
    conn: sqlite3.Connection,
    definition_id: int,
    *,
    run_mode: EnrichmentRunMode | str = EnrichmentRunMode.UPDATE,
) -> dict[str, Any]:
    from .. import jobs

    try:
        selected_mode = EnrichmentRunMode(run_mode)
    except ValueError as exc:
        raise EnrichmentError(f"unknown enrichment run mode {run_mode!r}") from exc
    definition = _definition_row(conn, definition_id)
    if definition["status"] != "active":
        raise EnrichmentError(
            f"enrichment definition {definition_id} is {definition['status']}"
        )
    requested_providers = set(json.loads(definition["providers_json"] or "[]"))
    available_providers = {
        item["key"] for item in provider_availability() if item["available"]
    }
    unavailable = sorted(requested_providers - available_providers)
    if unavailable:
        raise EnrichmentError(
            f"enrichment providers are no longer configured: {unavailable}"
        )
    active = conn.execute(
        "SELECT j.job_ref FROM organization_enrichment_job AS e "
        "JOIN crawl_job AS j ON j.job_id = e.job_id "
        "WHERE e.enrichment_definition_id = ? AND j.status NOT IN "
        "('cancelled','completed','completed_with_errors','partially_completed','failed') "
        "ORDER BY j.job_id DESC LIMIT 1",
        (definition_id,),
    ).fetchone()
    if active is not None:
        raise EnrichmentError(
            f"enrichment job {active['job_ref']} is already active for this dataset"
        )
    _create_output_schema(conn, int(definition["output_dataset_id"]))
    try:
        budget = int(os.environ.get("SCRAPEX_ENRICHMENT_REQUEST_BUDGET", "0") or 0)
    except ValueError as exc:
        raise EnrichmentError(
            "SCRAPEX_ENRICHMENT_REQUEST_BUDGET must be a non-negative integer"
        ) from exc
    if budget < 0:
        raise EnrichmentError(
            "SCRAPEX_ENRICHMENT_REQUEST_BUDGET must be a non-negative integer"
        )
    provider_names = json.loads(definition["providers_json"] or "[]")
    definition_json = _canonical(_definition_snapshot(definition))
    provider_versions_json = _canonical(provider_versions(provider_names))
    internal_mode = RunMode.UPDATE if selected_mode is EnrichmentRunMode.UPDATE \
        else RunMode.FULL_REBUILD
    conn.execute("SAVEPOINT enrichment_job_creation")
    try:
        job_ref = jobs.create_job(
            conn,
            [str(definition["source_dataset_key"])],
            internal_mode,
            job_kind="organization_enrichment",
            commit=False,
        )
        job = jobs.get_job(conn, job_ref)
        conn.execute(
            "INSERT INTO organization_enrichment_job "
            "(job_id, enrichment_definition_id, providers_json, definition_json, "
            "provider_versions_json, estimated_requests) VALUES (?,?,?,?,?,?)",
            (
                job["job_id"], definition_id, definition["providers_json"],
                definition_json, provider_versions_json, 0,
            ),
        )
        source_count = _snapshot_run_items(conn, int(job["job_id"]), definition)
        baseline = None
        item_count = source_count
        if selected_mode is EnrichmentRunMode.UPDATE:
            baseline = _compatible_incremental_baseline(
                conn,
                definition_id=definition_id,
                before_job_id=int(job["job_id"]),
                definition_json=definition_json,
                provider_versions_json=provider_versions_json,
            )
            if baseline is not None:
                item_count = _keep_incremental_run_items(
                    conn,
                    job_id=int(job["job_id"]),
                    definition_id=definition_id,
                    definition_json=definition_json,
                    provider_versions_json=provider_versions_json,
                )
        estimated_requests = estimate_requests(provider_names, item_count)
        if budget > 0 and estimated_requests > budget:
            raise EnrichmentError(
                f"estimated provider requests ({estimated_requests}) exceed "
                f"SCRAPEX_ENRICHMENT_REQUEST_BUDGET ({budget})"
            )
        conn.execute(
            "UPDATE organization_enrichment_job SET estimated_requests=? "
            "WHERE job_id=?",
            (estimated_requests, job["job_id"]),
        )
        conn.execute(
            "UPDATE crawl_job SET progress_total = ? WHERE job_id = ?",
            (item_count, job["job_id"]),
        )
        conn.execute("RELEASE SAVEPOINT enrichment_job_creation")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT enrichment_job_creation")
        conn.execute("RELEASE SAVEPOINT enrichment_job_creation")
        raise
    conn.commit()
    return {
        "job_ref": job_ref,
        "status": "queued",
        "job_kind": "organization_enrichment",
        "enrichment_definition_id": definition_id,
        "source_keys": [definition["source_dataset_key"]],
        "mode": selected_mode.value,
        "organizations": item_count,
        "source_organizations": source_count,
        "unchanged_skipped": source_count - item_count,
        "baseline_job_ref": baseline["job_ref"] if baseline is not None else None,
        "estimated_requests": estimated_requests,
    }


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _coordinate(value: Any, minimum: float, maximum: float) -> float | None:
    parsed = _float(value)
    if parsed is None or not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        return None
    return parsed


def _identity(
    definition: sqlite3.Row, source: sqlite3.Row, detail: dict[str, Any] | None
) -> OrganizationIdentity:
    source_data = json.loads(source["data_json"])
    mapping = json.loads(definition["field_mapping_json"])
    external_id = str(source_data.get(definition["entity_key_field"]) or "").strip()
    if not external_id:
        raise EnrichmentError(
            f"source record {source['generic_record_id']} has no value in "
            f"{definition['entity_key_field']!r}"
        )
    organization_id = "org_" + _digest(
        [definition["site_key"], definition["source_dataset_key"], external_id]
    )[:24]

    def value(role: str) -> str:
        scope, key = _field_reference(mapping.get(role, ""))
        primary = source_data.get(key)
        detailed = (detail or {}).get(key)
        if scope == "source":
            return str(primary or "").strip()
        if scope == "detail":
            return str(detailed or "").strip()
        # The field picker lists Source before Detail and de-duplicates equal
        # keys. Therefore a populated source field must win an ambiguous key;
        # otherwise the UI would say Source while the engine silently read
        # Detail. A uniquely named detail field still works as expected.
        selected = primary if primary not in (None, "") else detailed
        return str(selected or "").strip()

    return OrganizationIdentity(
        organization_id=organization_id,
        external_id=external_id,
        source_record_id=int(source["generic_record_id"]),
        source_snapshot_id=int(source["source_snapshot_id"]),
        source_url=value("profile_url") or str(source["source_url"] or definition["base_url"]),
        company_name=value("company_name"),
        company_name_ar=value("company_name_ar"),
        email=value("email"),
        phone=value("phone"),
        latitude=_coordinate(value("latitude"), -90.0, 90.0),
        longitude=_coordinate(value("longitude"), -180.0, 180.0),
        city=value("city"),
        country=value("country"),
        profile_url=value("profile_url"),
        website=value("website"),
    )


def _source_facts(identity: OrganizationIdentity) -> list[FieldFact]:
    values = {
        "source_record_id": identity.source_record_id,
        "source_external_id": identity.external_id,
        "company_name": identity.company_name,
        "company_name_ar": identity.company_name_ar,
    }
    facts = [FieldFact(
        key, value, "source", source_url=identity.source_url,
        confidence=1.0, verification_status="verified",
        evidence={"source_record_id": identity.source_record_id},
        entity_match_confidence=1.0, extraction_confidence=1.0,
        source_authority=1.0,
    ) for key, value in values.items() if value not in (None, "")]
    domain = email_domain(identity.email)
    if domain:
        facts.append(FieldFact(
            "company_domain", domain, "email_domain_candidate",
            source_url=identity.source_url, confidence=0.55,
            verification_status="candidate",
            evidence={"reason": "derived from a non-generic organization email"},
            entity_match_confidence=1.0, extraction_confidence=0.95,
            source_authority=0.55,
        ))
    return facts


def _canonical_organization_id(conn: sqlite3.Connection, organization_id: str) -> str:
    current = organization_id
    seen = set()
    while current not in seen:
        seen.add(current)
        row = conn.execute(
            "SELECT canonical_organization_id FROM organization_entity "
            "WHERE organization_id = ?",
            (current,),
        ).fetchone()
        if row is None or not row[0]:
            return current
        current = str(row[0])
    raise EnrichmentError(f"organization identity cycle detected at {organization_id!r}")


def _record_identity_aliases(
    conn: sqlite3.Connection, definition: sqlite3.Row, identity: OrganizationIdentity
) -> None:
    aliases = [(
        "source_external_id",
        f"{definition['site_key']}:{definition['source_dataset_key']}:{identity.external_id}",
        "source", 1.0, "confirmed",
    )]
    domain = registrable_domain(identity.website) or email_domain(identity.email)
    if domain:
        aliases.append(("domain", domain, "source", 0.75, "candidate"))
    phone = normalized_phone(identity.phone)
    if len(phone) >= 7:
        aliases.append(("phone", phone, "source", 0.65, "candidate"))
    for alias_type, value, provider, confidence, status in aliases:
        conn.execute(
            "INSERT INTO organization_identity_alias "
            "(organization_id, alias_type, normalized_value, value_hash, "
            "source_provider, confidence, review_status) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(organization_id, alias_type, value_hash, source_provider) "
            "DO UPDATE SET last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
            "confidence=max(confidence, excluded.confidence)",
            (
                identity.organization_id, alias_type, value, _digest(value), provider,
                confidence, status,
            ),
        )


def _upsert_fact(
    conn: sqlite3.Connection, organization_id: str, fact: FieldFact,
    observation_id: int | None = None,
) -> bool:
    value_json = _canonical(fact.value)
    value_hash = _digest(value_json)
    existing = conn.execute(
        "SELECT * FROM organization_fact WHERE organization_id = ? "
        "AND field_key = ? AND provider = ? AND valid_to IS NULL",
        (organization_id, fact.field_key, fact.provider),
    ).fetchone()
    evidence_json = _canonical(fact.evidence)
    source_url = fact.source_url or None
    confidence = max(0.0, min(float(fact.confidence), 1.0))
    entity_confidence = max(0.0, min(float(
        fact.entity_match_confidence
        if fact.entity_match_confidence is not None else confidence
    ), 1.0))
    extraction_confidence = max(0.0, min(float(
        fact.extraction_confidence
        if fact.extraction_confidence is not None else confidence
    ), 1.0))
    source_authority = max(0.0, min(float(
        fact.source_authority if fact.source_authority is not None else confidence
    ), 1.0))
    observed_at = utc_now_iso()
    if existing is not None and existing["value_hash"] == value_hash and \
            existing["verification_status"] == fact.verification_status and \
            float(existing["confidence"]) == confidence and \
            float(existing["entity_match_confidence"] or 0.0) == entity_confidence and \
            float(existing["extraction_confidence"] or 0.0) == extraction_confidence and \
            float(existing["source_authority"] or 0.0) == source_authority and \
            existing["source_url"] == source_url and \
            existing["evidence_json"] == evidence_json:
        conn.execute(
            "UPDATE organization_fact SET last_seen_at = ?, observed_at = ?, "
            "observation_id = ? "
            "WHERE organization_fact_id = ?",
            (observed_at, observed_at, observation_id, existing["organization_fact_id"]),
        )
        return False
    if existing is not None:
        conn.execute(
            "UPDATE organization_fact SET valid_to = ? WHERE organization_fact_id = ?",
            (utc_now_iso(), existing["organization_fact_id"]),
        )
    conn.execute(
        "INSERT INTO organization_fact "
        "(organization_id, field_key, value_json, value_hash, provider, source_url, "
        "confidence, verification_status, evidence_json, observation_id, "
        "entity_match_confidence, extraction_confidence, source_authority, observed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            organization_id,
            fact.field_key,
            value_json,
            value_hash,
            fact.provider,
            source_url,
            confidence,
            fact.verification_status,
            evidence_json,
            observation_id,
            entity_confidence,
            extraction_confidence,
            source_authority,
            observed_at,
        ),
    )
    return True


def _provider_input_hash(identity: OrganizationIdentity, provider: str) -> str:
    return _digest({
        "provider": provider,
        "company_name": identity.company_name,
        "company_name_ar": identity.company_name_ar,
        "email": identity.email,
        "phone": identity.phone,
        "latitude": identity.latitude,
        "longitude": identity.longitude,
        "city": identity.city,
        "country": identity.country,
        "website": identity.website,
    })


def _fresh_provider_observation(
    conn: sqlite3.Connection,
    organization_id: str,
    provider: str,
    provider_version: str,
    input_hash: str,
    ttl_seconds: int,
) -> bool:
    if ttl_seconds <= 0:
        return False
    cutoff = datetime.fromtimestamp(
        datetime.now(UTC).timestamp() - ttl_seconds, UTC
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return conn.execute(
        "SELECT 1 FROM organization_provider_observation "
        "WHERE organization_id = ? AND provider = ? AND provider_version = ? "
        "AND input_hash = ? "
        "AND observation_status IN ('completed','not_found','cached') "
        "AND observed_at >= ? ORDER BY observation_id DESC LIMIT 1",
        (organization_id, provider, provider_version, input_hash, cutoff),
    ).fetchone() is not None


def _record_provider_observation(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    organization_id: str,
    provider: str,
    provider_version: str,
    input_hash: str,
    status: str,
    fields_seen: set[str] | None = None,
    request_count: int = 0,
    latency_ms: int = 0,
    error: str = "",
) -> int:
    cursor = conn.execute(
        "INSERT INTO organization_provider_observation "
        "(job_id, organization_id, provider, provider_version, input_hash, "
        "observation_status, fields_seen_json, request_count, latency_ms, error) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(job_id, organization_id, provider) DO UPDATE SET "
        "provider_version=excluded.provider_version, input_hash=excluded.input_hash, "
        "observation_status=excluded.observation_status, "
        "fields_seen_json=excluded.fields_seen_json, "
        "request_count=excluded.request_count, latency_ms=excluded.latency_ms, "
        "error=excluded.error, observed_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "RETURNING observation_id",
        (
            job_id, organization_id, provider, provider_version, input_hash, status,
            _canonical(sorted(fields_seen or set())), max(0, request_count),
            max(0, latency_ms), error or None,
        ),
    )
    return int(cursor.fetchone()[0])


def _expire_missing_provider_facts(
    conn: sqlite3.Connection,
    organization_id: str,
    provider: str,
    fields_seen: set[str],
) -> int:
    rows = conn.execute(
        "SELECT organization_fact_id, field_key FROM organization_fact "
        "WHERE organization_id = ? AND provider = ? AND valid_to IS NULL",
        (organization_id, provider),
    ).fetchall()
    missing = [int(row["organization_fact_id"]) for row in rows
               if str(row["field_key"]) not in fields_seen]
    if not missing:
        return 0
    now = utc_now_iso()
    conn.executemany(
        "UPDATE organization_fact SET valid_to = ? WHERE organization_fact_id = ?",
        [(now, fact_id) for fact_id in missing],
    )
    return len(missing)


def _expire_unselected_provider_facts(
    conn: sqlite3.Connection,
    organization_id: str,
    configured_providers: set[str],
) -> int:
    retained = {"source", "email_domain_candidate", "owner_review"} \
        | configured_providers
    placeholders = ",".join("?" for _ in retained)
    cursor = conn.execute(
        "UPDATE organization_fact SET valid_to=? WHERE organization_id=? "
        "AND valid_to IS NULL "
        f"AND provider NOT IN ({placeholders})",
        (utc_now_iso(), organization_id, *sorted(retained)),
    )
    return max(0, int(cursor.rowcount))


_STATUS_RANK = {
    "verified": 5,
    "probable": 4,
    "candidate": 3,
    "manual_review": 2,
    "conflict": 1,
    "not_found": 0,
}
_PROVIDER_RANK = {"owner_review": 6, "source": 5, "website": 4, "google_places": 3,
                  "email_domain_candidate": 1}


def _materialized_data(
    conn: sqlite3.Connection, identity: OrganizationIdentity, job_id: int | None = None
) -> dict[str, Any]:
    canonical_id = _canonical_organization_id(conn, identity.organization_id)
    rows = conn.execute(
        "SELECT field_key, value_json, provider, source_url, confidence, "
        "verification_status, first_seen_at, last_seen_at, value_hash, "
        "entity_match_confidence, extraction_confidence, source_authority, observed_at "
        "FROM organization_fact "
        "WHERE organization_id IN (SELECT organization_id FROM organization_entity "
        "WHERE organization_id = ? OR canonical_organization_id = ?) "
        "AND valid_to IS NULL",
        (canonical_id, canonical_id),
    ).fetchall()
    selected: dict[str, sqlite3.Row] = {}
    for row in rows:
        key = str(row["field_key"])
        rank = (
            _STATUS_RANK.get(str(row["verification_status"]), -1),
            float(row["confidence"]),
            _PROVIDER_RANK.get(str(row["provider"]), 0),
        )
        previous = selected.get(key)
        if previous is None:
            selected[key] = row
            continue
        previous_rank = (
            _STATUS_RANK.get(str(previous["verification_status"]), -1),
            float(previous["confidence"]),
            _PROVIDER_RANK.get(str(previous["provider"]), 0),
        )
        if rank > previous_rank:
            selected[key] = row
    data = {key: json.loads(row["value_json"]) for key, row in selected.items()}
    data["organization_id"] = canonical_id
    # Canonical groups share external evidence, never dataset lineage. Each
    # materialized output must keep the source row and join key belonging to
    # its own definition or its confirmed source relationship would break.
    data["source_record_id"] = identity.source_record_id
    data["source_external_id"] = identity.external_id
    data["company_name"] = identity.company_name or None
    data["company_name_ar"] = identity.company_name_ar or None
    external_rows = [row for row in rows if row["provider"] not in (
        "source", "email_domain_candidate",
    )]
    by_field: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        field_key = str(row["field_key"])
        if field_key in {
            "source_record_id", "source_external_id", "company_name", "company_name_ar",
        } or row["verification_status"] == "not_found" or field_key.endswith(
            ("_match_status", "_match_score")
        ):
            continue
        by_field.setdefault(field_key, []).append(row)
    conflicts = set()
    for key, candidates in by_field.items():
        if any(row["provider"] == "owner_review" for row in candidates):
            continue
        if len({str(row["value_hash"]) for row in candidates}) > 1:
            conflicts.add(key)
    statuses = {str(row["verification_status"]) for row in external_rows}
    meaningful_statuses = {
        str(row["verification_status"]) for row in external_rows
        if row["verification_status"] != "not_found"
    }
    if conflicts or "conflict" in statuses or "manual_review" in statuses:
        verification, review = "needs_manual_review", "open"
    elif meaningful_statuses and meaningful_statuses == {"verified"}:
        verification, review = "verified", "none"
    elif meaningful_statuses & {"verified", "probable", "candidate"}:
        verification, review = "probable", "none"
    else:
        verification, review = "source_only", "none"
    data["verification_status"] = verification
    provider_rows = [row for row in selected.values() if row["provider"] not in (
        "source", "email_domain_candidate",
    ) and row["verification_status"] != "not_found"
        and not str(row["field_key"]).endswith(("_match_status", "_match_score"))
        and row["field_key"] != "google_attribution"]
    axes_by_provider: dict[str, list[tuple[float, float]]] = {}
    for row in provider_rows:
        entity_score = float(row["entity_match_confidence"] or row["confidence"])
        quality_score = (
            float(row["extraction_confidence"] or row["confidence"])
            * float(row["source_authority"] or row["confidence"])
        )
        axes_by_provider.setdefault(str(row["provider"]), []).append(
            (entity_score, quality_score)
        )
    provider_axes = [(
        sum(entity for entity, _ in axes) / len(axes),
        sum(quality for _, quality in axes) / len(axes),
    ) for axes in axes_by_provider.values()]
    entity_scores = [entity for entity, _ in provider_axes]
    quality_scores = [quality for _, quality in provider_axes]
    combined_scores = [entity * quality for entity, quality in provider_axes]
    data["entity_match_score"] = round(
        sum(entity_scores) / len(entity_scores), 4
    ) if entity_scores else 0.0
    data["data_quality_score"] = round(
        sum(quality_scores) / len(quality_scores), 4
    ) if quality_scores else 0.0
    data["verification_score"] = round(
        sum(combined_scores) / len(combined_scores), 4
    ) if combined_scores else 0.0
    data["manual_review_status"] = review
    observations = conn.execute(
        "SELECT provider, observation_status FROM organization_provider_observation "
        "WHERE job_id = ? AND organization_id = ?",
        (job_id, identity.organization_id),
    ).fetchall() if job_id is not None else []
    data["providers_checked"] = sorted({
        str(row["provider"]) for row in observations
        if row["observation_status"] in ("completed", "not_found", "cached")
    } or {str(row["provider"]) for row in rows
          if row["provider"] in ("website", "google_places", "linkedin")})
    if any(row["observation_status"] in ("failed", "system_error")
           for row in observations):
        data["freshness_status"] = "provider_error"
    else:
        data["freshness_status"] = "current"
    data["evidence_urls"] = sorted({str(row["source_url"]) for row in rows
                                     if row["source_url"]})
    entity = conn.execute(
        "SELECT created_at FROM organization_entity WHERE organization_id = ?",
        (canonical_id,),
    ).fetchone()
    first = str(entity["created_at"]) if entity is not None else min(
        (str(row["first_seen_at"]) for row in rows), default=utc_now_iso()
    )
    # The visible row changes when evidence changes, not merely because an
    # identical fact was checked again. `last_seen_at` still records that
    # reinforcement in organization_fact; using it here would create a new
    # generic revision on every no-op run.
    last = max((str(row["first_seen_at"]) for row in rows), default=utc_now_iso())
    data["first_enriched_at"] = first
    data["last_enriched_at"] = last
    return {item.key: data.get(item.key) for item in OUTPUT_FIELDS}


def _write_output(
    conn: sqlite3.Connection, definition: sqlite3.Row,
    identity: OrganizationIdentity, data: dict[str, Any]
) -> bool:
    schema = conn.execute(
        "SELECT schema_version_id FROM dataset_schema_version "
        "WHERE dataset_definition_id = ? AND valid_to IS NULL LIMIT 1",
        (definition["output_dataset_id"],),
    ).fetchone()
    if schema is None:
        raise EnrichmentError("the enrichment output has no active schema")
    data_json = _canonical(data)
    content_hash = _digest(data_json)
    output_organization_id = str(data.get("organization_id") or identity.organization_id)
    record_key = _digest([output_organization_id])
    existing = conn.execute(
        "SELECT generic_record_id, content_hash FROM generic_record "
        "WHERE dataset_definition_id = ? AND record_key = ?",
        (definition["output_dataset_id"], record_key),
    ).fetchone()
    unchanged = existing is not None and existing["content_hash"] == content_hash
    cursor = conn.execute(
        "INSERT INTO generic_record "
        "(dataset_definition_id, record_key, schema_version_id, data_json, "
        "source_snapshot_id, source_locator, content_hash) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(dataset_definition_id, record_key) DO UPDATE SET "
        "schema_version_id=excluded.schema_version_id, data_json=excluded.data_json, "
        "source_snapshot_id=excluded.source_snapshot_id, "
        "source_locator=excluded.source_locator, content_hash=excluded.content_hash, "
        "last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now'), status='active' "
        "RETURNING generic_record_id",
        (
            definition["output_dataset_id"],
            record_key,
            schema["schema_version_id"],
            data_json,
            identity.source_snapshot_id,
            f"organization:{output_organization_id}",
            content_hash,
        ),
    )
    record_id = int(cursor.fetchone()["generic_record_id"])
    if not unchanged:
        conn.execute(
            "INSERT INTO generic_record_revision "
            "(generic_record_id, schema_version_id, source_snapshot_id, data_json, "
            "content_hash) VALUES (?,?,?,?,?)",
            (
                record_id,
                schema["schema_version_id"],
                identity.source_snapshot_id,
                data_json,
                content_hash,
            ),
        )
    return not unchanged


def _record_output_sighting(
    conn: sqlite3.Connection,
    definition: sqlite3.Row,
    organization_id: str,
    job_ref: str,
) -> None:
    """Make a generated output row participate in the generic state model.

    ``dataset_table_payload`` deliberately treats a generic record with no
    sighting as historical data that predates the sighting ledger.  Enrichment
    outputs are generated rather than crawled, but a completed run is still the
    observation that proves the row exists.  Recording that observation here
    prevents a row created seconds ago from being labelled ``unsighted`` while
    preserving the same new/updated/confirmed state machinery as every other
    generic dataset.

    This stays in the caller's per-record transaction.  ``record_sightings``
    commits internally for crawler callers, which would make a provider result
    durable before the run item and its checkpoint were committed.
    """
    conn.execute(
        "INSERT INTO dataset_sighting "
        "(dataset_key, external_id, first_run_ref) VALUES (?,?,?) "
        "ON CONFLICT(dataset_key, external_id) DO UPDATE SET "
        "seen_count=seen_count+1, "
        "last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')",
        (
            str(definition["output_dataset_key"]),
            organization_id,
            job_ref,
        ),
    )


def _close_providers(providers) -> None:
    close_all = getattr(providers, "close", None)
    if close_all is not None:
        close_all()
        return
    for provider in providers:
        close = getattr(provider, "close", None)
        if close is not None:
            close()


def _park_for_control(conn: sqlite3.Connection, job: dict) -> bool:
    from .. import jobs

    control = jobs._control_of(conn, job["job_id"])
    if control == JobControl.PAUSE.value:
        jobs._update(
            conn, job["job_id"], status=JobStatus.PAUSED.value,
            control=JobControl.NONE.value, stage=None,
            last_heartbeat_at=utc_now_iso(),
        )
        jobs.append_log(conn, job["job_id"], "enrichment paused at a record boundary")
        conn.commit()
        return True
    if control == JobControl.CANCEL.value:
        jobs._finish(conn, job["job_id"], JobStatus.CANCELLED, None)
        return True
    return False


def run_enrichment_job_once(conn: sqlite3.Connection, job_ref: str) -> dict:
    """Run one immutable input snapshot; failed items earn bounded retries."""
    from .. import jobs

    job = jobs.get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job.get("job_kind") != "organization_enrichment":
        raise EnrichmentError(f"job {job_ref!r} is not an organization enrichment")
    if job["status"] in {status.value for status in jobs.TERMINAL_JOB_STATUSES}:
        return job
    linked = conn.execute(
        "SELECT enrichment_definition_id, providers_json, definition_json, "
        "provider_versions_json "
        "FROM organization_enrichment_job WHERE job_id = ?",
        (job["job_id"],),
    ).fetchone()
    if linked is None:
        raise EnrichmentError(f"job {job_ref!r} has no enrichment definition")
    current_definition = _definition_row(
        conn, int(linked["enrichment_definition_id"])
    )
    snapshot = json.loads(linked["definition_json"] or "{}")
    # Output storage and foreign-key ids remain on the live row, while every
    # semantic input used to interpret the captured source records comes from
    # the immutable job snapshot.
    definition = dict(current_definition)
    definition.update({
        "configuration_version": snapshot.get(
            "configuration_version", current_definition["configuration_version"]
        ),
        "site_key": snapshot.get("site_key", current_definition["site_key"]),
        "base_url": snapshot.get("base_url", current_definition["base_url"]),
        "source_dataset_key": snapshot.get(
            "source_dataset_key", current_definition["source_dataset_key"]
        ),
        "detail_dataset_key": snapshot.get(
            "detail_dataset_key", current_definition["detail_dataset_key"]
        ),
        "entity_key_field": snapshot.get(
            "entity_key_field", current_definition["entity_key_field"]
        ),
        "detail_key_field": snapshot.get(
            "detail_key_field", current_definition["detail_key_field"]
        ),
        "field_mapping_json": _canonical(snapshot.get(
            "field_mapping", json.loads(current_definition["field_mapping_json"])
        )),
        "providers_json": _canonical(snapshot.get(
            "providers", json.loads(current_definition["providers_json"])
        )),
    })
    checkpoint = job["checkpoint"]
    counters = dict(job["counters"])
    conn.execute(
        "UPDATE organization_enrichment_run_item SET item_status = 'pending' "
        "WHERE job_id = ? AND item_status = 'running'",
        (job["job_id"],),
    )
    total = int(conn.execute(
        "SELECT count(*) FROM organization_enrichment_run_item WHERE job_id = ?",
        (job["job_id"],),
    ).fetchone()[0])
    processed = int(conn.execute(
        "SELECT count(*) FROM organization_enrichment_run_item WHERE job_id = ? "
        "AND (item_status = 'completed' OR "
        "(item_status = 'failed' AND attempts >= ?))",
        (job["job_id"], _RECORD_RETRY_LIMIT),
    ).fetchone()[0])
    jobs._update(
        conn, job["job_id"], status=JobStatus.PREPARING.value,
        stage=JobStage.PREPARING.value, progress_total=total,
        last_heartbeat_at=utc_now_iso(),
        **({} if job["started_at"] else {"started_at": utc_now_iso()}),
    )
    jobs.append_log(
        conn, job["job_id"],
        f"organization enrichment started ({total:,} source records)",
    )
    conn.commit()
    configured_provider_names = set(json.loads(linked["providers_json"] or "[]"))
    providers = build_providers(sorted(configured_provider_names))
    errors: list[str] = list(checkpoint.get("errors", []))
    disabled_providers: set[str] = set()
    consecutive_system_errors: dict[str, int] = {}
    versions = json.loads(linked["provider_versions_json"] or "{}")
    actual_provider_names = {str(provider.name) for provider in providers}
    provider_startup_errors = []
    missing_providers = sorted(configured_provider_names - actual_provider_names)
    unexpected_providers = sorted(actual_provider_names - configured_provider_names)
    if missing_providers:
        provider_startup_errors.append(f"unavailable providers: {missing_providers}")
    if unexpected_providers:
        provider_startup_errors.append(f"unexpected providers: {unexpected_providers}")
    for provider in providers:
        name = str(provider.name)
        queued_version = str(versions.get(name, "unknown"))
        actual_version = str(getattr(provider, "version", queued_version))
        if actual_version != queued_version:
            provider_startup_errors.append(
                f"{name} changed from queued version {queued_version!r} "
                f"to runtime version {actual_version!r}"
            )
    if provider_startup_errors:
        _close_providers(providers)
        summary = "; ".join(provider_startup_errors) + "; queue a new run"
        jobs.append_log(conn, job["job_id"], summary, level=LogLevel.ERROR)
        jobs._finish(conn, job["job_id"], JobStatus.FAILED, summary)
        return jobs.get_job(conn, job_ref)

    def pending_items():
        after = 0
        while True:
            rows = conn.execute(
                "SELECT * FROM organization_enrichment_run_item WHERE job_id = ? "
                "AND item_status IN ('pending','failed') AND attempts < ? "
                "AND generic_record_id > ? ORDER BY generic_record_id LIMIT ?",
                (job["job_id"], _RECORD_RETRY_LIMIT, after, _SOURCE_BATCH_SIZE),
            ).fetchall()
            if not rows:
                return
            yield from rows
            after = int(rows[-1]["generic_record_id"])

    try:
        while True:
            attempted = False
            for item in pending_items():
                attempted = True
                current = jobs.get_job(conn, job_ref)
                if _park_for_control(conn, current):
                    return jobs.get_job(conn, job_ref)
                record_id = int(item["generic_record_id"])
                conn.execute(
                    "UPDATE organization_enrichment_run_item "
                    "SET item_status = 'running' WHERE job_id = ? AND generic_record_id = ?",
                    (job["job_id"], record_id),
                )
                conn.commit()
                try:
                    source = {
                        "data_json": item["source_data_json"],
                        "generic_record_id": record_id,
                        "source_snapshot_id": int(item["source_snapshot_id"]),
                        "source_url": item["source_url"],
                    }
                    detail = json.loads(item["detail_data_json"]) \
                        if item["detail_data_json"] else None
                    identity = _identity(definition, source, detail)
                    conn.execute(
                        "INSERT INTO organization_entity (organization_id) VALUES (?) "
                        "ON CONFLICT(organization_id) DO UPDATE SET updated_at = "
                        "strftime('%Y-%m-%dT%H:%M:%SZ','now')",
                        (identity.organization_id,),
                    )
                    _record_identity_aliases(conn, definition, identity)
                    conn.execute(
                        "INSERT INTO organization_source_record "
                        "(enrichment_definition_id, generic_record_id, organization_id, "
                        "source_external_id) VALUES (?,?,?,?) "
                        "ON CONFLICT(enrichment_definition_id, generic_record_id) "
                        "DO UPDATE SET organization_id=excluded.organization_id, "
                        "source_external_id=excluded.source_external_id, "
                        "last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')",
                        (
                            definition["enrichment_definition_id"], record_id,
                            identity.organization_id, identity.external_id,
                        ),
                    )

                    source_facts = _source_facts(identity)
                    changed = _expire_unselected_provider_facts(
                        conn, identity.organization_id, configured_provider_names
                    )
                    for source_provider in ("source", "email_domain_candidate"):
                        facts = [fact for fact in source_facts
                                 if fact.provider == source_provider]
                        fields_seen = {fact.field_key for fact in facts}
                        observation_id = _record_provider_observation(
                            conn, job_id=int(job["job_id"]),
                            organization_id=identity.organization_id,
                            provider=source_provider, provider_version="1",
                            input_hash=_provider_input_hash(identity, source_provider),
                            status="completed" if facts else "not_found",
                            fields_seen=fields_seen,
                        )
                        changed += sum(
                            _upsert_fact(conn, identity.organization_id, fact, observation_id)
                            for fact in facts
                        )
                        changed += _expire_missing_provider_facts(
                            conn, identity.organization_id, source_provider, fields_seen
                        )

                    provider_errors = 0
                    for provider in providers:
                        provider_name = str(provider.name)
                        provider_version = str(getattr(
                            provider, "version", versions.get(provider_name, "unknown")
                        ))
                        input_hash = _provider_input_hash(identity, provider_name)
                        if provider_name in disabled_providers:
                            _record_provider_observation(
                                conn, job_id=int(job["job_id"]),
                                organization_id=identity.organization_id,
                                provider=provider_name, provider_version=provider_version,
                                input_hash=input_hash, status="failed",
                                error="provider circuit is open",
                            )
                            continue
                        ttl = int(getattr(provider, "ttl_seconds", 0) or 0)
                        if _fresh_provider_observation(
                            conn, identity.organization_id, provider_name,
                            provider_version, input_hash, ttl
                        ):
                            _record_provider_observation(
                                conn, job_id=int(job["job_id"]),
                                organization_id=identity.organization_id,
                                provider=provider_name, provider_version=provider_version,
                                input_hash=input_hash, status="cached",
                            )
                            counters["provider_cache_hits"] = int(
                                counters.get("provider_cache_hits", 0)
                            ) + 1
                            continue
                        # Do not hold SQLite's writer lock while an external
                        # provider is in flight. The source facts and any prior
                        # provider result are idempotent if this item later retries.
                        conn.commit()
                        request_before = int(getattr(provider, "requests_made", 0) or 0)
                        started = time.monotonic()
                        result = provider.run(identity)
                        elapsed_ms = int((time.monotonic() - started) * 1000)
                        request_count = max(
                            0, int(getattr(provider, "requests_made", request_before) or 0)
                            - request_before,
                        )
                        fields_seen = {fact.field_key for fact in result.facts}
                        if result.system_error:
                            observation_status = "system_error"
                        elif result.error:
                            observation_status = "failed"
                        elif not result.checked:
                            observation_status = "skipped"
                        elif not result.facts or all(
                            fact.verification_status == "not_found" for fact in result.facts
                        ):
                            observation_status = "not_found"
                        else:
                            observation_status = "completed"
                        observation_id = _record_provider_observation(
                            conn, job_id=int(job["job_id"]),
                            organization_id=identity.organization_id,
                            provider=provider_name, provider_version=provider_version,
                            input_hash=input_hash, status=observation_status,
                            fields_seen=fields_seen, request_count=request_count,
                            latency_ms=elapsed_ms, error=result.error,
                        )
                        if result.system_error:
                            consecutive_system_errors[provider_name] = (
                                consecutive_system_errors.get(provider_name, 0) + 1
                            )
                        else:
                            consecutive_system_errors[provider_name] = 0
                        if result.error:
                            provider_errors += 1
                            jobs.append_log(
                                conn, job["job_id"],
                                f"{identity.external_id}: {provider_name}: {result.error}",
                                level=LogLevel.WARNING,
                            )
                        if observation_status in ("completed", "not_found"):
                            changed += sum(
                                _upsert_fact(
                                    conn, identity.organization_id, fact, observation_id
                                )
                                for fact in result.facts
                            )
                            changed += _expire_missing_provider_facts(
                                conn, identity.organization_id, provider_name, fields_seen
                            )
                        if consecutive_system_errors.get(provider_name, 0) \
                                >= _PROVIDER_CIRCUIT_LIMIT:
                            disabled_providers.add(provider_name)
                            counters["providers_disabled"] = int(
                                counters.get("providers_disabled", 0)
                            ) + 1
                            jobs.append_log(
                                conn, job["job_id"],
                                f"{provider_name}: disabled after "
                                f"{_PROVIDER_CIRCUIT_LIMIT} consecutive system errors",
                                level=LogLevel.ERROR,
                            )

                    data = _materialized_data(conn, identity, int(job["job_id"]))
                    row_changed = _write_output(conn, definition, identity, data)
                    _record_output_sighting(
                        conn,
                        definition,
                        str(data.get("organization_id") or identity.organization_id),
                        str(job["job_ref"]),
                    )
                    processed += 1
                    counters["organizations"] = processed
                    counters["facts_changed"] = int(
                        counters.get("facts_changed", 0)
                    ) + changed
                    counters["rows_changed"] = int(
                        counters.get("rows_changed", 0)
                    ) + int(row_changed)
                    counters["provider_errors"] = int(
                        counters.get("provider_errors", 0)
                    ) + provider_errors
                    status = data["verification_status"]
                    counters[status] = int(counters.get(status, 0)) + 1
                    conn.execute(
                        "UPDATE organization_enrichment_run_item "
                        "SET item_status='completed', attempts=attempts+1, "
                        "last_error=NULL, completed_at=? "
                        "WHERE job_id=? AND generic_record_id=?",
                        (utc_now_iso(), job["job_id"], record_id),
                    )
                    checkpoint = {"last_source_record_id": record_id, "errors": errors[-100:]}
                    jobs._update(
                        conn, job["job_id"], status=JobStatus.RUNNING.value,
                        stage="enriching", current_source_key=identity.external_id,
                        progress_done=processed, counters_json=_canonical(counters),
                        checkpoint_json=_canonical(checkpoint),
                        last_heartbeat_at=utc_now_iso(),
                    )
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    error = f"record {record_id}: {exc}"
                    errors = [*errors, error][-100:]
                    conn.execute(
                        "UPDATE organization_enrichment_run_item "
                        "SET item_status='failed', attempts=attempts+1, last_error=? "
                        "WHERE job_id=? AND generic_record_id=?",
                        (str(exc), job["job_id"], record_id),
                    )
                    attempts = int(conn.execute(
                        "SELECT attempts FROM organization_enrichment_run_item "
                        "WHERE job_id=? AND generic_record_id=?",
                        (job["job_id"], record_id),
                    ).fetchone()[0])
                    counters["record_attempt_errors"] = int(
                        counters.get("record_attempt_errors", 0)
                    ) + 1
                    if attempts >= _RECORD_RETRY_LIMIT:
                        processed += 1
                        counters["errors"] = int(counters.get("errors", 0)) + 1
                    jobs.append_log(
                        conn, job["job_id"],
                        error + (f"; retry {attempts}/{_RECORD_RETRY_LIMIT}"
                                 if attempts < _RECORD_RETRY_LIMIT else "; retries exhausted"),
                        level=LogLevel.ERROR,
                    )
                    checkpoint = {"last_source_record_id": record_id, "errors": errors}
                    jobs._update(
                        conn, job["job_id"], status=JobStatus.RUNNING.value,
                        stage="enriching", progress_done=processed,
                        counters_json=_canonical(counters),
                        checkpoint_json=_canonical(checkpoint),
                        last_heartbeat_at=utc_now_iso(),
                    )
                    conn.commit()
            if not attempted:
                break
    finally:
        _close_providers(providers)

    # Only a complete pass owns the entire current membership. An incremental
    # update deliberately omits unchanged inputs and therefore cannot infer
    # that omitted output rows disappeared from the source.
    if job["run_mode"] == RunMode.FULL_REBUILD.value:
        conn.execute(
            "UPDATE generic_record SET status = 'unavailable' "
            "WHERE dataset_definition_id = ? "
            "AND source_locator LIKE 'organization:%' AND source_locator NOT IN ("
            "SELECT 'organization:' || coalesce(entity.canonical_organization_id, "
            "link.organization_id) "
            "FROM organization_source_record AS link "
            "JOIN organization_entity AS entity "
            "ON entity.organization_id=link.organization_id "
            "JOIN organization_enrichment_run_item AS item "
            "ON item.generic_record_id = link.generic_record_id "
            "WHERE link.enrichment_definition_id = ? AND item.job_id = ?)",
            (
                definition["output_dataset_id"],
                definition["enrichment_definition_id"],
                job["job_id"],
            ),
        )
    conn.execute(
        "UPDATE organization_enrichment_definition SET last_run_at = ?, updated_at = ? "
        "WHERE enrichment_definition_id = ?",
        (utc_now_iso(), utc_now_iso(), definition["enrichment_definition_id"]),
    )
    # Completed inputs no longer need full duplicate JSON for resume. Keep
    # hashes, snapshot IDs and membership for provenance; failed items retain
    # their payload so an owner can diagnose them.
    conn.execute(
        "UPDATE organization_enrichment_run_item SET source_data_json=NULL, "
        "detail_data_json=NULL WHERE job_id=? AND item_status='completed'",
        (job["job_id"],),
    )
    provider_error_count = int(counters.get("provider_errors", 0))
    status = JobStatus.COMPLETED_WITH_ERRORS \
        if errors or provider_error_count else JobStatus.COMPLETED
    summary = "; ".join(errors[-5:])
    if not summary and provider_error_count:
        summary = f"{provider_error_count} provider request(s) failed"
    jobs._finish(conn, job["job_id"], status, summary or None)
    return jobs.get_job(conn, job_ref)


def review_queue(
    conn: sqlite3.Connection, definition_id: int, *, limit: int = 100,
    after_id: int = 0,
) -> dict[str, Any]:
    definition = _definition_row(conn, definition_id)
    rows = conn.execute(
        "SELECT f.organization_fact_id, f.organization_id, f.field_key, f.value_json, "
        "f.provider, f.source_url, f.confidence, f.verification_status, "
        "f.evidence_json, f.last_seen_at "
        "FROM organization_fact AS f "
        "JOIN organization_source_record AS link "
        "ON link.organization_id = f.organization_id "
        "JOIN organization_entity AS linked_entity "
        "ON linked_entity.organization_id=f.organization_id "
        "JOIN generic_record AS source "
        "ON source.generic_record_id = link.generic_record_id "
        "WHERE link.enrichment_definition_id = ? AND f.valid_to IS NULL "
        "AND source.status = 'active' "
        "AND f.organization_fact_id > ? AND ("
        "f.verification_status IN ('manual_review','conflict') OR ("
        "f.verification_status <> 'not_found' "
        "AND f.field_key NOT IN ('source_record_id','source_external_id',"
        "'company_name','company_name_ar') "
        "AND f.field_key NOT LIKE '%_match_status' "
        "AND f.field_key NOT LIKE '%_match_score' "
        "AND NOT EXISTS (SELECT 1 FROM organization_fact AS owner "
        "JOIN organization_entity AS owner_entity "
        "ON owner_entity.organization_id=owner.organization_id "
        "WHERE owner.field_key=f.field_key "
        "AND coalesce(owner_entity.canonical_organization_id,owner.organization_id)="
        "coalesce(linked_entity.canonical_organization_id,f.organization_id) "
        "AND owner.provider='owner_review' AND owner.valid_to IS NULL) "
        "AND EXISTS (SELECT 1 FROM organization_fact AS other "
        "JOIN organization_entity AS other_entity "
        "ON other_entity.organization_id=other.organization_id "
        "WHERE coalesce(other_entity.canonical_organization_id,other.organization_id)="
        "coalesce(linked_entity.canonical_organization_id,f.organization_id) "
        "AND other.field_key=f.field_key "
        "AND other.organization_fact_id<>f.organization_fact_id "
        "AND other.valid_to IS NULL AND other.verification_status<>'not_found' "
        "AND other.value_hash<>f.value_hash))) "
        "ORDER BY f.organization_fact_id LIMIT ?",
        (
            definition["enrichment_definition_id"], max(0, after_id),
            max(1, min(limit, 500)) + 1,
        ),
    ).fetchall()
    page_limit = max(1, min(limit, 500))
    page = rows[:page_limit]
    items = []
    for row in page:
        item = {**dict(row), "value": json.loads(row["value_json"]),
                "evidence": json.loads(row["evidence_json"])}
        canonical_id = _canonical_organization_id(
            conn, str(row["organization_id"])
        )
        competing = conn.execute(
            "SELECT organization_fact_id, provider, value_json, confidence "
            "FROM organization_fact WHERE organization_id IN ("
            "SELECT organization_id FROM organization_entity "
            "WHERE organization_id=? OR canonical_organization_id=?) "
            "AND field_key=? "
            "AND valid_to IS NULL AND organization_fact_id<>? "
            "AND verification_status<>'not_found' AND value_hash<>?",
            (
                canonical_id, canonical_id, row["field_key"],
                row["organization_fact_id"],
                _digest(row["value_json"]),
            ),
        ).fetchall()
        if competing:
            item["verification_status"] = "conflict"
            item["competing_facts"] = [{
                **dict(other), "value": json.loads(other["value_json"]),
            } for other in competing]
        items.append(item)
    return {
        "items": items,
        "next_after_id": int(page[-1]["organization_fact_id"])
        if len(rows) > page_limit and page else None,
    }


def _identity_for_organization(
    conn: sqlite3.Connection, definition: sqlite3.Row, organization_id: str
) -> OrganizationIdentity:
    source = conn.execute(
        "SELECT record.*, page.source_url FROM organization_source_record AS link "
        "JOIN generic_record AS record ON record.generic_record_id=link.generic_record_id "
        "JOIN generic_page_snapshot AS page "
        "ON page.page_snapshot_id=record.source_snapshot_id "
        "WHERE link.enrichment_definition_id=? AND link.organization_id=? "
        "AND record.status='active' LIMIT 1",
        (definition["enrichment_definition_id"], organization_id),
    ).fetchone()
    if source is None:
        raise EnrichmentError(f"organization {organization_id!r} has no active source link")
    source_data = json.loads(source["data_json"])
    external = str(source_data.get(definition["entity_key_field"]) or "").strip()
    detail = None
    if definition["detail_dataset_id"] is not None:
        detail_row = conn.execute(
            "SELECT data_json FROM generic_record WHERE dataset_definition_id=? "
            "AND status='active' AND trim(CAST(json_extract(data_json, ?) AS TEXT))=? "
            "LIMIT 1",
            (
                definition["detail_dataset_id"],
                _json_path(str(definition["detail_key_field"])), external,
            ),
        ).fetchone()
        detail = json.loads(detail_row[0]) if detail_row is not None else None
    return _identity(definition, source, detail)


def identity_candidates(
    conn: sqlite3.Connection, definition_id: int, *, limit: int = 100,
    after_id: int = 0,
) -> dict[str, Any]:
    definition = _definition_row(conn, definition_id)
    rows = conn.execute(
        "SELECT DISTINCT mine.identity_alias_id, mine.organization_id, mine.alias_type, "
        "mine.normalized_value, mine.confidence, other.organization_id AS candidate_id, "
        "other.confidence AS candidate_confidence "
        "FROM organization_identity_alias AS mine "
        "JOIN organization_source_record AS link "
        "ON link.organization_id=mine.organization_id "
        "JOIN organization_identity_alias AS other "
        "ON other.alias_type=mine.alias_type AND other.value_hash=mine.value_hash "
        "AND other.organization_id<>mine.organization_id "
        "JOIN organization_source_record AS other_source "
        "ON other_source.organization_id=other.organization_id "
        "JOIN organization_entity AS mine_entity "
        "ON mine_entity.organization_id=mine.organization_id "
        "JOIN organization_entity AS other_entity "
        "ON other_entity.organization_id=other.organization_id "
        "WHERE link.enrichment_definition_id=? AND mine.identity_alias_id>? "
        "AND mine.review_status='candidate' AND other.review_status<>'rejected' "
        "AND NOT EXISTS (SELECT 1 FROM organization_source_record AS other_link "
        "WHERE other_link.enrichment_definition_id=? "
        "AND other_link.organization_id=other.organization_id) "
        "AND coalesce(mine_entity.canonical_organization_id, mine.organization_id) "
        "<> coalesce(other_entity.canonical_organization_id, other.organization_id) "
        "ORDER BY mine.identity_alias_id LIMIT ?",
        (
            definition["enrichment_definition_id"], max(0, after_id),
            definition["enrichment_definition_id"],
            max(1, min(limit, 500)) + 1,
        ),
    ).fetchall()
    page_limit = max(1, min(limit, 500))
    page = rows[:page_limit]
    return {
        "items": [dict(row) for row in page],
        "next_after_id": int(page[-1]["identity_alias_id"])
        if len(rows) > page_limit and page else None,
    }


def merge_organization(
    conn: sqlite3.Connection,
    definition_id: int,
    source_organization_id: str,
    request: OrganizationMergeCreate,
) -> dict[str, Any]:
    _definition_row(conn, definition_id)
    linked = conn.execute(
        "SELECT 1 FROM organization_source_record WHERE enrichment_definition_id=? "
        "AND organization_id=?",
        (definition_id, source_organization_id),
    ).fetchone()
    if linked is None:
        raise EnrichmentError(
            f"organization {source_organization_id!r} does not belong to this definition"
        )
    source_root = _canonical_organization_id(conn, source_organization_id)
    target_root = _canonical_organization_id(conn, request.target_organization_id)
    if source_root == target_root:
        raise EnrichmentError("the two organizations are already linked")
    if conn.execute(
        "SELECT 1 FROM organization_entity WHERE organization_id=?",
        (target_root,),
    ).fetchone() is None:
        raise EnrichmentError(f"unknown target organization {target_root!r}")
    if conn.execute(
        "SELECT 1 FROM organization_source_record AS link "
        "JOIN organization_entity AS entity ON entity.organization_id=link.organization_id "
        "JOIN generic_record AS source ON source.generic_record_id=link.generic_record_id "
        "WHERE source.status='active' AND (link.organization_id=? "
        "OR entity.canonical_organization_id=?) LIMIT 1",
        (target_root, target_root),
    ).fetchone() is None:
        raise EnrichmentError(
            f"target organization {target_root!r} has no source-backed identity"
        )

    source_definitions = {int(row[0]) for row in conn.execute(
        "SELECT DISTINCT link.enrichment_definition_id "
        "FROM organization_source_record AS link "
        "JOIN organization_entity AS entity ON entity.organization_id=link.organization_id "
        "JOIN generic_record AS source ON source.generic_record_id=link.generic_record_id "
        "WHERE source.status='active' AND (link.organization_id=? "
        "OR entity.canonical_organization_id=?)",
        (source_root, source_root),
    )}
    target_definitions = {int(row[0]) for row in conn.execute(
        "SELECT DISTINCT link.enrichment_definition_id "
        "FROM organization_source_record AS link "
        "JOIN organization_entity AS entity ON entity.organization_id=link.organization_id "
        "JOIN generic_record AS source ON source.generic_record_id=link.generic_record_id "
        "WHERE source.status='active' AND (link.organization_id=? "
        "OR entity.canonical_organization_id=?)",
        (target_root, target_root),
    )}
    overlap = source_definitions & target_definitions
    if overlap:
        raise EnrichmentError(
            "organizations from the same enrichment definition cannot be merged; "
            "resolve the duplicate source records first"
        )
    source_members = conn.execute(
        "SELECT organization_id, canonical_organization_id "
        "FROM organization_entity WHERE organization_id=? "
        "OR canonical_organization_id=? ORDER BY organization_id",
        (source_root, source_root),
    ).fetchall()
    cursor = conn.execute(
        "INSERT INTO organization_merge_event "
        "(source_organization_id,target_organization_id,reviewer,reason) "
        "VALUES (?,?,?,?)",
        (source_root, target_root, request.reviewer, request.reason),
    )
    merge_id = int(cursor.lastrowid)
    conn.executemany(
        "INSERT INTO organization_merge_member "
        "(organization_merge_id,organization_id,previous_canonical_id) "
        "VALUES (?,?,?)",
        [
            (merge_id, row["organization_id"], row["canonical_organization_id"])
            for row in source_members
        ],
    )
    conn.execute(
        "UPDATE organization_entity SET canonical_organization_id=? "
        "WHERE organization_id=? OR canonical_organization_id=?",
        (target_root, source_root, source_root),
    )

    affected = conn.execute(
        "SELECT DISTINCT link.enrichment_definition_id, link.organization_id "
        "FROM organization_source_record AS link "
        "JOIN organization_entity AS entity ON entity.organization_id=link.organization_id "
        "JOIN generic_record AS source ON source.generic_record_id=link.generic_record_id "
        "WHERE source.status='active' AND (link.organization_id=? "
        "OR entity.canonical_organization_id=?)",
        (target_root, target_root),
    ).fetchall()
    for row in affected:
        definition = _definition_row(conn, int(row["enrichment_definition_id"]))
        identity = _identity_for_organization(
            conn, definition, str(row["organization_id"])
        )
        _write_output(conn, definition, identity, _materialized_data(conn, identity))
    for affected_definition in source_definitions:
        output_id = _definition_row(conn, affected_definition)["output_dataset_id"]
        conn.execute(
            "UPDATE generic_record SET status='unavailable' "
            "WHERE dataset_definition_id=? AND source_locator=?",
            (output_id, f"organization:{source_root}"),
        )
    return {
        "organization_merge_id": merge_id,
        "source_organization_id": source_root,
        "canonical_organization_id": target_root,
        "definitions_rematerialized": sorted(source_definitions | target_definitions),
    }


def merge_history(
    conn: sqlite3.Connection, definition_id: int, *, limit: int = 100,
    after_id: int = 0,
) -> dict[str, Any]:
    _definition_row(conn, definition_id)
    page_limit = max(1, min(limit, 500))
    rows = conn.execute(
        "SELECT event.*, (SELECT count(*) FROM organization_merge_member AS member "
        "WHERE member.organization_merge_id=event.organization_merge_id) "
        "AS member_count FROM organization_merge_event AS event "
        "WHERE event.organization_merge_id>? AND EXISTS ("
        "SELECT 1 FROM organization_merge_member AS member "
        "JOIN organization_source_record AS link "
        "ON link.organization_id=member.organization_id "
        "WHERE member.organization_merge_id=event.organization_merge_id "
        "AND link.enrichment_definition_id=?) "
        "ORDER BY event.organization_merge_id LIMIT ?",
        (max(0, after_id), definition_id, page_limit + 1),
    ).fetchall()
    page = rows[:page_limit]
    return {
        "items": [dict(row) for row in page],
        "next_after_id": int(page[-1]["organization_merge_id"])
        if len(rows) > page_limit and page else None,
    }


def reverse_organization_merge(
    conn: sqlite3.Connection,
    definition_id: int,
    merge_id: int,
    request: OrganizationMergeReverseCreate,
) -> dict[str, Any]:
    _definition_row(conn, definition_id)
    event = conn.execute(
        "SELECT event.* FROM organization_merge_event AS event "
        "WHERE event.organization_merge_id=? AND EXISTS ("
        "SELECT 1 FROM organization_merge_member AS member "
        "JOIN organization_source_record AS link "
        "ON link.organization_id=member.organization_id "
        "WHERE member.organization_merge_id=event.organization_merge_id "
        "AND link.enrichment_definition_id=?)",
        (merge_id, definition_id),
    ).fetchone()
    if event is None:
        raise EnrichmentError(f"unknown organization merge {merge_id}")
    if event["reversed_at"]:
        raise EnrichmentError(f"organization merge {merge_id} is already reversed")
    members = conn.execute(
        "SELECT member.organization_id, member.previous_canonical_id, "
        "entity.canonical_organization_id AS current_canonical_id "
        "FROM organization_merge_member AS member "
        "JOIN organization_entity AS entity "
        "ON entity.organization_id=member.organization_id "
        "WHERE member.organization_merge_id=? ORDER BY member.organization_id",
        (merge_id,),
    ).fetchall()
    target_root = str(event["target_organization_id"])
    if not members or any(
        str(row["current_canonical_id"] or "") != target_root for row in members
    ):
        raise EnrichmentError(
            "this merge has a newer canonical change; reverse the newer merge first"
        )
    conn.executemany(
        "UPDATE organization_entity SET canonical_organization_id=? "
        "WHERE organization_id=?",
        [(row["previous_canonical_id"], row["organization_id"]) for row in members],
    )
    conn.execute(
        "UPDATE organization_merge_event SET reversed_at=?, reversed_by=?, "
        "reverse_reason=? WHERE organization_merge_id=?",
        (utc_now_iso(), request.reviewer, request.reason, merge_id),
    )
    member_ids = [str(row["organization_id"]) for row in members]
    placeholders = ",".join("?" for _ in member_ids)
    affected = conn.execute(
        "SELECT DISTINCT link.enrichment_definition_id, link.organization_id "
        "FROM organization_source_record AS link "
        "JOIN generic_record AS source ON source.generic_record_id=link.generic_record_id "
        "JOIN organization_entity AS entity ON entity.organization_id=link.organization_id "
        f"WHERE source.status='active' AND (link.organization_id IN ({placeholders}) "
        "OR coalesce(entity.canonical_organization_id,link.organization_id)=?)",
        (*member_ids, target_root),
    ).fetchall()
    affected_definitions: set[int] = set()
    for row in affected:
        affected_definition_id = int(row["enrichment_definition_id"])
        affected_definitions.add(affected_definition_id)
        definition = _definition_row(conn, affected_definition_id)
        identity = _identity_for_organization(
            conn, definition, str(row["organization_id"])
        )
        _write_output(conn, definition, identity, _materialized_data(conn, identity))

    source_definitions = {int(row[0]) for row in conn.execute(
        "SELECT DISTINCT enrichment_definition_id FROM organization_source_record "
        f"WHERE organization_id IN ({placeholders})",
        member_ids,
    )}
    for source_definition_id in source_definitions:
        still_uses_target = conn.execute(
            "SELECT 1 FROM organization_source_record AS link "
            "JOIN generic_record AS source ON source.generic_record_id=link.generic_record_id "
            "JOIN organization_entity AS entity "
            "ON entity.organization_id=link.organization_id "
            "WHERE link.enrichment_definition_id=? AND source.status='active' "
            "AND coalesce(entity.canonical_organization_id,link.organization_id)=? LIMIT 1",
            (source_definition_id, target_root),
        ).fetchone()
        if still_uses_target is None:
            output_id = _definition_row(conn, source_definition_id)["output_dataset_id"]
            conn.execute(
                "UPDATE generic_record SET status='unavailable' "
                "WHERE dataset_definition_id=? AND source_locator=?",
                (output_id, f"organization:{target_root}"),
            )
    return {
        "organization_merge_id": merge_id,
        "source_organization_id": event["source_organization_id"],
        "target_organization_id": target_root,
        "status": "reversed",
        "definitions_rematerialized": sorted(affected_definitions),
    }


def decide_review(
    conn: sqlite3.Connection,
    definition_id: int,
    fact_id: int,
    request: ReviewDecisionCreate,
) -> dict[str, Any]:
    definition = _definition_row(conn, definition_id)
    fact = conn.execute(
        "SELECT f.* FROM organization_fact AS f "
        "JOIN organization_source_record AS link "
        "ON link.organization_id=f.organization_id "
        "WHERE f.organization_fact_id=? AND link.enrichment_definition_id=? "
        "AND f.valid_to IS NULL LIMIT 1",
        (fact_id, definition_id),
    ).fetchone()
    if fact is None:
        raise EnrichmentError(f"review fact {fact_id} is not current for this definition")
    value = request.value if request.action.value == "override" \
        else json.loads(fact["value_json"])
    if request.action.value == "override":
        field = next(
            (item for item in OUTPUT_FIELDS if item.key == fact["field_key"]), None
        )
        if field is None:
            raise EnrichmentError(
                f"field {fact['field_key']!r} is not materialized by this schema"
            )
        valid = (
            isinstance(value, str)
            if field.data_type in ("text", "datetime") else
            isinstance(value, str) and urlsplit(value).scheme in ("http", "https")
            if field.data_type == "url" else
            isinstance(value, int) and not isinstance(value, bool)
            if field.data_type == "integer" else
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))
            if field.data_type == "decimal" else
            isinstance(value, (list, dict))
            if field.data_type == "json" else False
        )
        if not valid:
            raise EnrichmentError(
                f"override for {fact['field_key']!r} must be {field.data_type}"
            )
    cursor = conn.execute(
        "INSERT INTO organization_review_decision "
        "(organization_fact_id, action, override_value_json, reviewer, reason) "
        "VALUES (?,?,?,?,?)",
        (
            fact_id, request.action.value,
            _canonical(request.value) if request.action.value == "override" else None,
            request.reviewer, request.reason,
        ),
    )
    decision_id = int(cursor.lastrowid)
    now = utc_now_iso()
    if request.action.value == "reject":
        conn.execute(
            "UPDATE organization_fact SET valid_to=? WHERE organization_fact_id=?",
            (now, fact_id),
        )
    else:
        conn.execute(
            "UPDATE organization_fact SET valid_to=? WHERE organization_id=? "
            "AND field_key=? AND valid_to IS NULL",
            (now, fact["organization_id"], fact["field_key"]),
        )
        _upsert_fact(
            conn,
            str(fact["organization_id"]),
            FieldFact(
                str(fact["field_key"]), value, "owner_review",
                source_url=str(fact["source_url"] or ""), confidence=1.0,
                verification_status="verified",
                evidence={
                    "decision_id": decision_id,
                    "reviewed_fact_id": fact_id,
                    "reviewed_provider": fact["provider"],
                    "reviewer": request.reviewer,
                    "reason": request.reason,
                },
                entity_match_confidence=1.0, extraction_confidence=1.0,
                source_authority=1.0,
            ),
        )
    identity = _identity_for_organization(
        conn, definition, str(fact["organization_id"])
    )
    data = _materialized_data(conn, identity)
    _write_output(conn, definition, identity, data)
    return {
        "review_decision_id": decision_id,
        "organization_fact_id": fact_id,
        "organization_id": fact["organization_id"],
        "field_key": fact["field_key"],
        "action": request.action.value,
        "materialized_value": data.get(str(fact["field_key"])),
        "verification_status": data["verification_status"],
    }
