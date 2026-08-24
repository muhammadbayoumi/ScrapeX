"""Definitions, facts, materialization and resumable organization jobs."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any

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
from .matching import email_domain
from .models import (
    FIELD_ROLES,
    OUTPUT_FIELDS,
    DefinitionCreate,
    FieldFact,
    OrganizationIdentity,
)
from .providers import build_providers, provider_availability


class EnrichmentError(ValueError):
    """A safe refusal that the API can return directly to the extension."""


_SOURCE_BATCH_SIZE = 50
_PROVIDER_CIRCUIT_LIMIT = 3


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
        "SELECT d.*, s.site_key, s.display_name AS site_display_name, s.base_url "
        "FROM dataset_definition AS d JOIN site_profile AS s "
        "ON s.site_profile_id = d.site_profile_id "
        "WHERE d.dataset_key = ? AND d.valid_to IS NULL AND s.valid_to IS NULL "
    )
    parameters: tuple[str, ...] = (key,)
    if site_key:
        sql += "AND s.site_key = ? AND s.valid_to IS NULL "
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


def _suggest(fields: list[dict[str, Any]]) -> dict[str, str]:
    keys = {str(field["field_key"]).casefold(): str(field["field_key"])
            for field in fields}
    result: dict[str, str] = {}
    for role, candidates in _ROLE_CANDIDATES.items():
        for candidate in candidates:
            if candidate in keys:
                result[role] = keys[candidate]
                break
    return result


def _definition_row(conn: sqlite3.Connection, definition_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT e.*, s.site_key, s.display_name AS site_display_name, s.base_url, "
        "source.dataset_key AS source_dataset_key, "
        "detail.dataset_key AS detail_dataset_key, "
        "output.dataset_key AS output_dataset_key, "
        "output.display_name AS output_display_name, "
        "output.original_name AS output_original_name "
        "FROM organization_enrichment_definition AS e "
        "JOIN site_profile AS s ON s.site_profile_id = e.site_profile_id "
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
        "AND status <> 'retired' LIMIT 1",
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
    site_id = int(source["site_profile_id"])
    rows = conn.execute(
        "SELECT d.dataset_definition_id, d.dataset_key, d.original_name, d.display_name, "
        "d.dataset_kind, d.locator_json "
        "FROM dataset_definition AS d WHERE d.site_profile_id = ? "
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
    mapping = _suggest(primary_fields)
    mapping.update(_suggest(detail_fields))
    # The listing's names are more useful than a detail page that may not carry
    # a title at all. Detail wins for contacts and coordinates, not by accident
    # of update order for identity labels.
    primary_suggestion = _suggest(primary_fields)
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


def _create_output_schema(conn: sqlite3.Connection, dataset_id: int) -> int:
    payload = [{"field_key": item.key, "data_type": item.data_type,
                "identity": item.identity, "position": position}
               for position, item in enumerate(OUTPUT_FIELDS)]
    schema_hash = _digest(payload)
    cursor = conn.execute(
        "INSERT INTO dataset_schema_version "
        "(dataset_definition_id, version_number, schema_hash) VALUES (?,?,?)",
        (dataset_id, 1, schema_hash),
    )
    schema_id = int(cursor.lastrowid)
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
            "UPDATE field_definition SET display_name = ? "
            "WHERE field_definition_id = ?",
            (item.key, field["field_definition_id"]),
        )
        conn.execute(
            "INSERT INTO schema_version_field "
            "(schema_version_id, field_definition_id, field_order) VALUES (?,?,?)",
            (schema_id, field["field_definition_id"], position),
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
        if detail["site_profile_id"] != source["site_profile_id"]:
            raise EnrichmentError("source and detail datasets must belong to one site")
        detail_fields = {item["field_key"] for item in _fields(
            conn, int(detail["dataset_definition_id"])
        )}
        if request.detail_key_field not in detail_fields:
            raise EnrichmentError(
                f"detail key {request.detail_key_field!r} is not in the detail dataset"
            )
    available_fields = source_fields | detail_fields
    missing = sorted(set(request.field_mapping.values()) - available_fields)
    if missing:
        raise EnrichmentError(f"mapped fields do not exist in the selected datasets: {missing}")
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
        "WHERE site_profile_id = ? AND dataset_key = ? LIMIT 1",
        (source["site_profile_id"], output_key),
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
        "(site_profile_id, source_dataset_id, detail_dataset_id, output_dataset_id, "
        "entity_key_field, detail_key_field, field_mapping_json, providers_json) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            source["site_profile_id"],
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


def create_enrichment_job(conn: sqlite3.Connection, definition_id: int) -> dict[str, Any]:
    from .. import jobs

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
    job_ref = jobs.create_job(
        conn,
        [str(definition["source_dataset_key"])],
        RunMode.UPDATE,
        job_kind="organization_enrichment",
    )
    job = jobs.get_job(conn, job_ref)
    conn.execute(
        "INSERT INTO organization_enrichment_job "
        "(job_id, enrichment_definition_id, providers_json) VALUES (?,?,?)",
        (job["job_id"], definition_id, definition["providers_json"]),
    )
    conn.commit()
    return {
        "job_ref": job_ref,
        "status": "queued",
        "job_kind": "organization_enrichment",
        "enrichment_definition_id": definition_id,
        "source_keys": [definition["source_dataset_key"]],
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
        key = mapping.get(role, "")
        primary = source_data.get(key)
        detailed = (detail or {}).get(key)
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
    ) for key, value in values.items() if value not in (None, "")]
    domain = email_domain(identity.email)
    if domain:
        facts.append(FieldFact(
            "company_domain", domain, "email_domain_candidate",
            source_url=identity.source_url, confidence=0.55,
            verification_status="candidate",
            evidence={"reason": "derived from a non-generic organization email"},
        ))
    return facts


def _upsert_fact(
    conn: sqlite3.Connection, organization_id: str, fact: FieldFact
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
    if existing is not None and existing["value_hash"] == value_hash and \
            existing["verification_status"] == fact.verification_status and \
            float(existing["confidence"]) == confidence and \
            existing["source_url"] == source_url and \
            existing["evidence_json"] == evidence_json:
        conn.execute(
            "UPDATE organization_fact SET last_seen_at = ? "
            "WHERE organization_fact_id = ?",
            (utc_now_iso(), existing["organization_fact_id"]),
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
        "confidence, verification_status, evidence_json) VALUES (?,?,?,?,?,?,?,?,?)",
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
        ),
    )
    return True


_STATUS_RANK = {
    "verified": 5,
    "probable": 4,
    "candidate": 3,
    "manual_review": 2,
    "conflict": 1,
    "not_found": 0,
}
_PROVIDER_RANK = {"source": 5, "website": 4, "google_places": 3,
                  "email_domain_candidate": 1}


def _materialized_data(
    conn: sqlite3.Connection, identity: OrganizationIdentity
) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT field_key, value_json, provider, source_url, confidence, "
        "verification_status, first_seen_at, last_seen_at FROM organization_fact "
        "WHERE organization_id = ? AND valid_to IS NULL",
        (identity.organization_id,),
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
    data["organization_id"] = identity.organization_id
    statuses = {str(row["verification_status"]) for row in rows
                if row["provider"] not in ("source", "email_domain_candidate")}
    if "conflict" in statuses or "manual_review" in statuses:
        verification, review = "needs_manual_review", "open"
    elif "verified" in statuses:
        verification, review = "verified", "none"
    elif "probable" in statuses:
        verification, review = "probable", "none"
    else:
        verification, review = "source_only", "none"
    data["verification_status"] = verification
    provider_rows = [row for row in rows if row["provider"] in (
        "website", "google_places", "linkedin",
    )]
    data["verification_score"] = round(max(
        (float(row["confidence"]) for row in provider_rows), default=0.0
    ), 4)
    data["manual_review_status"] = review
    data["providers_checked"] = sorted({str(row["provider"]) for row in rows
                                        if row["provider"] in ("website", "google_places",
                                                               "linkedin")})
    data["evidence_urls"] = sorted({str(row["source_url"]) for row in rows
                                     if row["source_url"]})
    entity = conn.execute(
        "SELECT created_at FROM organization_entity WHERE organization_id = ?",
        (identity.organization_id,),
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
    record_key = _digest([identity.organization_id])
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
            f"organization:{identity.organization_id}",
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


def _detail_lookup(
    conn: sqlite3.Connection, definition: sqlite3.Row
) -> dict[str, dict[str, Any]]:
    if definition["detail_dataset_id"] is None:
        return {}
    result = {}
    for row in conn.execute(
        "SELECT data_json FROM generic_record WHERE dataset_definition_id = ? "
        "AND status = 'active'",
        (definition["detail_dataset_id"],),
    ):
        data = json.loads(row["data_json"])
        key = str(data.get(definition["detail_key_field"]) or "").strip()
        if key:
            if key in result:
                raise EnrichmentError(
                    f"detail dataset has duplicate active join key {key!r}"
                )
            result[key] = data
    return result


def _active_source_rows(
    conn: sqlite3.Connection, dataset_id: int, after_id: int
):
    """Yield a stable, bounded page at a time instead of loading the crawl whole."""
    cursor_id = after_id
    while True:
        rows = conn.execute(
            "SELECT r.*, p.source_url FROM generic_record AS r "
            "JOIN generic_page_snapshot AS p "
            "ON p.page_snapshot_id = r.source_snapshot_id "
            "WHERE r.dataset_definition_id = ? AND r.status = 'active' "
            "AND r.generic_record_id > ? ORDER BY r.generic_record_id LIMIT ?",
            (dataset_id, cursor_id, _SOURCE_BATCH_SIZE),
        ).fetchall()
        if not rows:
            return
        yield from rows
        cursor_id = int(rows[-1]["generic_record_id"])


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
    """Run or resume one enrichment job; the network never owns job state."""
    from .. import jobs

    job = jobs.get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job.get("job_kind") != "organization_enrichment":
        raise EnrichmentError(f"job {job_ref!r} is not an organization enrichment")
    if job["status"] in {status.value for status in jobs.TERMINAL_JOB_STATUSES}:
        return job
    linked = conn.execute(
        "SELECT enrichment_definition_id, providers_json "
        "FROM organization_enrichment_job WHERE job_id = ?",
        (job["job_id"],),
    ).fetchone()
    if linked is None:
        raise EnrichmentError(f"job {job_ref!r} has no enrichment definition")
    definition = _definition_row(conn, int(linked["enrichment_definition_id"]))
    checkpoint = job["checkpoint"]
    after_id = int(checkpoint.get("last_source_record_id", 0))
    counters = dict(job["counters"])
    processed = int(job["progress_done"] or 0)
    remaining = int(conn.execute(
        "SELECT count(*) FROM generic_record WHERE dataset_definition_id = ? "
        "AND status = 'active' AND generic_record_id > ?",
        (definition["source_dataset_id"], after_id),
    ).fetchone()[0])
    total = processed + remaining
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
    details = _detail_lookup(conn, definition)
    providers = build_providers(json.loads(linked["providers_json"] or "[]"))
    source_rows = _active_source_rows(
        conn, int(definition["source_dataset_id"]), after_id
    )
    errors: list[str] = list(checkpoint.get("errors", []))
    disabled_providers: set[str] = set()
    consecutive_system_errors: dict[str, int] = {}
    for source in source_rows:
        current = jobs.get_job(conn, job_ref)
        if _park_for_control(conn, current):
            _close_providers(providers)
            return jobs.get_job(conn, job_ref)
        try:
            source_data = json.loads(source["data_json"])
            external = str(source_data.get(definition["entity_key_field"]) or "").strip()
            identity = _identity(definition, source, details.get(external))
            conn.execute(
                "INSERT INTO organization_entity (organization_id) VALUES (?) "
                "ON CONFLICT(organization_id) DO UPDATE SET updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%SZ','now')",
                (identity.organization_id,),
            )
            conn.execute(
                "INSERT INTO organization_source_record "
                "(enrichment_definition_id, generic_record_id, organization_id, "
                "source_external_id) VALUES (?,?,?,?) "
                "ON CONFLICT(enrichment_definition_id, generic_record_id) DO UPDATE SET "
                "organization_id=excluded.organization_id, "
                "source_external_id=excluded.source_external_id, "
                "last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')",
                (
                    definition["enrichment_definition_id"],
                    identity.source_record_id,
                    identity.organization_id,
                    identity.external_id,
                ),
            )
            changed = sum(_upsert_fact(conn, identity.organization_id, fact)
                          for fact in _source_facts(identity))
            provider_errors = 0
            for provider in providers:
                if provider.name in disabled_providers:
                    continue
                result = provider.run(identity)
                if result.system_error:
                    consecutive_system_errors[provider.name] = (
                        consecutive_system_errors.get(provider.name, 0) + 1
                    )
                else:
                    consecutive_system_errors[provider.name] = 0
                if result.error:
                    provider_errors += 1
                    jobs.append_log(
                        conn, job["job_id"],
                        f"{identity.external_id}: {result.provider}: {result.error}",
                        level=LogLevel.WARNING,
                    )
                if consecutive_system_errors[provider.name] >= _PROVIDER_CIRCUIT_LIMIT:
                    disabled_providers.add(provider.name)
                    counters["providers_disabled"] = int(
                        counters.get("providers_disabled", 0)
                    ) + 1
                    jobs.append_log(
                        conn, job["job_id"],
                        f"{provider.name}: disabled after "
                        f"{_PROVIDER_CIRCUIT_LIMIT} consecutive system errors",
                        level=LogLevel.ERROR,
                    )
                changed += sum(_upsert_fact(conn, identity.organization_id, fact)
                               for fact in result.facts)
            data = _materialized_data(conn, identity)
            row_changed = _write_output(conn, definition, identity, data)
            processed += 1
            counters["organizations"] = processed
            counters["facts_changed"] = int(counters.get("facts_changed", 0)) + changed
            counters["rows_changed"] = int(counters.get("rows_changed", 0)) + int(row_changed)
            counters["provider_errors"] = int(counters.get("provider_errors", 0)) \
                + provider_errors
            status = data["verification_status"]
            counters[status] = int(counters.get(status, 0)) + 1
            checkpoint = {
                "last_source_record_id": int(source["generic_record_id"]),
                "errors": errors,
            }
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
            errors.append(f"record {source['generic_record_id']}: {exc}")
            processed += 1
            counters["errors"] = int(counters.get("errors", 0)) + 1
            checkpoint = {
                "last_source_record_id": int(source["generic_record_id"]),
                "errors": errors[-100:],
            }
            jobs.append_log(
                conn, job["job_id"], errors[-1], level=LogLevel.ERROR,
            )
            jobs._update(
                conn, job["job_id"], status=JobStatus.RUNNING.value,
                stage="enriching", progress_done=processed,
                counters_json=_canonical(counters), checkpoint_json=_canonical(checkpoint),
                last_heartbeat_at=utc_now_iso(),
            )
            conn.commit()
    _close_providers(providers)
    # A company that is no longer active in the source does not stay current in
    # the derived table. Its row and fact history remain queryable; only the
    # current materialization is marked unavailable.
    conn.execute(
        "UPDATE generic_record SET status = 'unavailable' "
        "WHERE dataset_definition_id = ? "
        "AND source_locator LIKE 'organization:%' AND source_locator NOT IN ("
        "SELECT 'organization:' || link.organization_id "
        "FROM organization_source_record AS link "
        "JOIN generic_record AS source "
        "ON source.generic_record_id = link.generic_record_id "
        "WHERE link.enrichment_definition_id = ? AND source.status = 'active')",
        (definition["output_dataset_id"], definition["enrichment_definition_id"]),
    )
    conn.execute(
        "UPDATE organization_enrichment_definition SET last_run_at = ?, updated_at = ? "
        "WHERE enrichment_definition_id = ?",
        (utc_now_iso(), utc_now_iso(), definition["enrichment_definition_id"]),
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
    conn: sqlite3.Connection, definition_id: int, *, limit: int = 100
) -> list[dict[str, Any]]:
    definition = _definition_row(conn, definition_id)
    rows = conn.execute(
        "SELECT f.organization_fact_id, f.organization_id, f.field_key, f.value_json, "
        "f.provider, f.source_url, f.confidence, f.verification_status, "
        "f.evidence_json, f.last_seen_at "
        "FROM organization_fact AS f "
        "JOIN organization_source_record AS link "
        "ON link.organization_id = f.organization_id "
        "JOIN generic_record AS source "
        "ON source.generic_record_id = link.generic_record_id "
        "WHERE link.enrichment_definition_id = ? AND f.valid_to IS NULL "
        "AND source.status = 'active' "
        "AND f.verification_status IN ('manual_review','conflict') "
        "ORDER BY f.confidence DESC, f.organization_fact_id LIMIT ?",
        (definition["enrichment_definition_id"], max(1, min(limit, 500))),
    ).fetchall()
    return [{**dict(row), "value": json.loads(row["value_json"]),
             "evidence": json.loads(row["evidence_json"])} for row in rows]
