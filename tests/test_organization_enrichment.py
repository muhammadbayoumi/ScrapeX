"""A source dataset becomes a linked, evidence-backed organization dataset."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from scrapex import catalog
from scrapex.catalog_models import (
    DatasetCreate,
    DiscoveryMethod,
    RelationshipCreate,
    RelationshipFieldPairCreate,
    RelationshipReviewStatus,
    SiteCreate,
)
from scrapex.catalog_relations import propose_relationship, review_relationship
from scrapex.config import MANIFEST_FILE
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.enrichment import service as enrichment
from scrapex.enrichment.matching import email_domain, name_similarity
from scrapex.enrichment.models import (
    DefinitionCreate,
    FieldFact,
    OrganizationIdentity,
    OrganizationMergeCreate,
    OrganizationMergeReverseCreate,
    OutputField,
    ProviderResult,
    ReviewDecisionCreate,
)
from scrapex.enrichment.providers import website as website_provider
from scrapex.enrichment.providers.google_places import GooglePlacesProvider
from scrapex.enrichment.providers.website import FetchedPage, WebsiteProvider
from scrapex.extract import service as extraction
from scrapex.extract.models import ApprovalField, CandidateApproval, SnapshotCreate
from scrapex.extract.muqawil import bilingual_profile_candidate, listing_candidate
from scrapex.jobs import JobRunner, create_job, get_job
from scrapex.webui.app import create_app

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
PROFILE_EN = (FIXTURES / "profile-en.html").read_text(encoding="utf-8")
PROFILE_AR = (FIXTURES / "profile-ar.html").read_text(encoding="utf-8")


def _approve(conn, *, url: str, html: str, candidate, key: str, name: str) -> int:
    snapshot = extraction.save_snapshot(
        conn, SnapshotCreate(source_url=url, html_content=html)
    )
    result = extraction.approve_candidate(
        conn,
        int(snapshot["page_snapshot_id"]),
        CandidateApproval(
            table_index=0,
            site_key="muqawil_org",
            site_display_name="Saudi Contractors Authority",
            dataset_key=key,
            dataset_name=name,
            fields=[
                ApprovalField(
                    field_key=field.field_key,
                    display_name=field.source_name,
                    data_type="text",
                    identity=(field.field_key == "contractor_id"),
                )
                for field in candidate.fields
            ],
        ),
        candidate=candidate,
    )
    return int(result["dataset_definition_id"])


def _field_id(conn, dataset_id: int, key: str) -> int:
    row = conn.execute(
        "SELECT field_definition_id FROM field_definition "
        "WHERE dataset_definition_id = ? AND field_key = ? AND valid_to IS NULL",
        (dataset_id, key),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _seed(registry: DatabaseRegistry) -> None:
    conn = registry.engine.connect()
    try:
        source_id = _approve(
            conn,
            url="https://muqawil.org/en/contractors?page=1",
            html=LISTING,
            candidate=listing_candidate(LISTING),
            key="contractors",
            name="Contractors",
        )
        detail_id = _approve(
            conn,
            url="https://muqawil.org/en/contractors/881/143",
            html=PROFILE_EN,
            candidate=bilingual_profile_candidate(
                PROFILE_EN, PROFILE_AR, contractor_id="881"
            ),
            key="contractor_profiles",
            name="Contractor Profiles",
        )
        propose_relationship(
            conn,
            "muqawil_org",
            RelationshipCreate(
                relationship_key="contractor_profile",
                parent_dataset_id=source_id,
                child_dataset_id=detail_id,
                cardinality="one_to_one",
                confidence=1.0,
                evidence={"joined_on": "contractor_id"},
                field_pairs=[RelationshipFieldPairCreate(
                    parent_field_id=_field_id(conn, source_id, "contractor_id"),
                    child_field_id=_field_id(conn, detail_id, "contractor_id"),
                )],
            ),
        )
        review_relationship(
            conn,
            "muqawil_org",
            "contractor_profile",
            status=RelationshipReviewStatus.CONFIRMED,
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def registry(tmp_path: Path) -> DatabaseRegistry:
    value = DatabaseRegistry(
        EngineDatabase(tmp_path / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json",
    )
    value.initialize()
    _seed(value)
    return value


@pytest.fixture()
def conn(registry: DatabaseRegistry):
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def _request(conn) -> DefinitionCreate:
    proposal = enrichment.propose_definition(conn, "contractors")["proposal"]
    return DefinitionCreate(**proposal)


def test_the_engine_migration_keeps_definitions_facts_and_job_kind(conn):
    objects = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    assert {
        "organization_enrichment_definition",
        "organization_entity",
        "organization_source_record",
        "organization_fact",
        "organization_enrichment_job",
    } <= objects
    columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_job)")}
    assert "job_kind" in columns
    indexes = {row[1] for row in conn.execute(
        "PRAGMA index_list(organization_source_record)"
    )}
    assert "ix_organization_source_record_org" in indexes


def test_muqawil_is_proposed_as_listing_plus_profile(conn, monkeypatch):
    monkeypatch.setenv("SCRAPEX_GOOGLE_PLACES_API_KEY", "configured-but-paid")
    payload = enrichment.propose_definition(conn, "contractors")
    proposal = payload["proposal"]

    assert proposal["site_key"] == "muqawil_org"
    assert proposal["detail_dataset_key"] == "contractor_profiles"
    assert proposal["entity_key_field"] == "contractor_id"
    assert proposal["detail_key_field"] == "contractor_id"
    assert proposal["output_dataset_key"] == "contractor_enrichment"
    assert proposal["field_mapping"]["company_name"] == "source:company_name"
    assert proposal["field_mapping"]["email"] == "detail:organization_email"
    assert proposal["field_mapping"]["latitude"] == "detail:latitude"
    assert payload["provider_availability"][0]["key"] == "website"
    assert next(item for item in payload["provider_availability"]
                if item["key"] == "google_places")["available"] is True
    assert proposal["providers"] == ["website"]


def test_duplicate_dataset_keys_require_the_site_instead_of_guessing(conn):
    catalog.register_site(
        conn,
        SiteCreate(
            site_key="other_directory",
            display_name="Other Directory",
            base_url="https://directory.example/",
        ),
    )
    catalog.register_dataset(
        conn,
        "other_directory",
        DatasetCreate(
            dataset_key="contractors",
            original_name="Contractors",
            dataset_kind="list",
            discovery_method=DiscoveryMethod.MANUAL,
        ),
    )

    with pytest.raises(enrichment.EnrichmentError, match="ambiguous across sites"):
        enrichment.propose_definition(conn, "contractors")

    exact = enrichment.propose_definition(
        conn, "contractors", site_key="muqawil_org"
    )
    assert exact["site"]["site_key"] == "muqawil_org"
    assert exact["proposal"]["site_key"] == "muqawil_org"
    exact_table = extraction.dataset_table_payload(
        conn, "contractors", site_key="muqawil_org"
    )
    assert exact_table is not None
    assert exact_table["total"] == 4


def test_creation_adds_a_wide_dataset_and_a_confirmed_link(conn):
    made = enrichment.create_definition(conn, _request(conn))

    assert made["output_dataset_key"] == "contractor_enrichment"
    output_id = conn.execute(
        "SELECT dataset_definition_id FROM dataset_definition "
        "WHERE dataset_key = 'contractor_enrichment'"
    ).fetchone()[0]
    fields = {row[0] for row in conn.execute(
        "SELECT field_key FROM field_definition WHERE dataset_definition_id = ?",
        (output_id,),
    )}
    assert {
        "website_url", "company_domain", "iso_certifications", "core_specialties",
        "careers_contact", "contact_page_url", "contact_emails", "contact_phones",
        "whatsapp_url", "linkedin_company_url", "key_decision_makers",
        "google_maps_url", "google_maps_cid_url", "gmaps_rating", "reviews_count",
        "verified_phone_secondary", "verification_score",
    } <= fields
    relation = conn.execute(
        "SELECT cardinality, review_status FROM dataset_relationship "
        "WHERE child_dataset_id = ? AND valid_to IS NULL",
        (output_id,),
    ).fetchone()
    assert tuple(relation) == ("one_to_one", "confirmed")


def test_creation_refuses_to_reuse_an_existing_dataset_as_output(conn):
    request = _request(conn).model_copy(
        update={"output_dataset_key": "contractor_profiles"}
    )

    with pytest.raises(
        enrichment.EnrichmentError,
        match="output dataset key 'contractor_profiles' is already in use",
    ):
        enrichment.create_definition(conn, request)

    assert conn.execute(
        "SELECT count(*) FROM organization_enrichment_definition"
    ).fetchone()[0] == 0


def test_definition_requires_evidence_and_a_distinct_detail_dataset(conn):
    proposal = enrichment.propose_definition(conn, "contractors")["proposal"]
    with pytest.raises(ValueError, match="at least 1 item"):
        DefinitionCreate(**{**proposal, "providers": []})

    same_detail = DefinitionCreate(**{
        **proposal,
        "detail_dataset_key": "contractors",
        "detail_key_field": proposal["entity_key_field"],
    })
    with pytest.raises(
        enrichment.EnrichmentError,
        match="source and detail datasets must be different",
    ):
        enrichment.create_definition(conn, same_detail)


def test_definition_creation_is_idempotent_but_never_ignores_changed_settings(conn):
    request = _request(conn)
    first = enrichment.create_definition(conn, request)

    repeated = enrichment.create_definition(conn, request)
    assert repeated["enrichment_definition_id"] == first["enrichment_definition_id"]

    changed = request.model_copy(update={"output_dataset_name": "Different Result"})
    with pytest.raises(
        enrichment.EnrichmentError,
        match="already has a different enrichment definition",
    ):
        enrichment.create_definition(conn, changed)


def test_fact_history_versions_changed_evidence_but_not_an_identical_recheck(conn):
    conn.execute("INSERT INTO organization_entity (organization_id) VALUES ('org_test')")
    first = FieldFact(
        "website_url", "https://example.com", "website",
        source_url="https://example.com", confidence=0.8,
        verification_status="probable", evidence={"published_name": "Example"},
    )
    changed_evidence = FieldFact(
        "website_url", "https://example.com", "website",
        source_url="https://example.com/about", confidence=0.9,
        verification_status="probable", evidence={"published_name": "Example LLC"},
    )

    assert enrichment._upsert_fact(conn, "org_test", first) is True
    assert enrichment._upsert_fact(conn, "org_test", first) is False
    assert enrichment._upsert_fact(conn, "org_test", changed_evidence) is True

    history = conn.execute(
        "SELECT count(*), sum(valid_to IS NOT NULL) FROM organization_fact "
        "WHERE organization_id = 'org_test' AND field_key = 'website_url'"
    ).fetchone()
    assert tuple(history) == (2, 1)


def test_an_ambiguous_field_key_uses_the_source_value_the_picker_names():
    definition = {
        "field_mapping_json": json.dumps({"company_name": "name", "email": "email"}),
        "entity_key_field": "id", "site_key": "site", "source_dataset_key": "firms",
        "base_url": "https://source.example",
    }
    source = {
        "data_json": json.dumps({
            "id": "42", "name": "Source Name", "email": "source@example.com",
        }),
        "generic_record_id": 7, "source_snapshot_id": 9,
        "source_url": "https://source.example/42",
    }

    identity = enrichment._identity(
        definition, source,
        {"name": "Detail Name", "email": "detail@example.com"},
    )

    assert identity.company_name == "Source Name"
    assert identity.email == "source@example.com"


def test_only_a_plausible_non_generic_email_can_propose_a_company_domain():
    assert email_domain("info@example.com") == "example.com"
    assert email_domain("person@gmail.com") == ""
    assert email_domain("@example.com") == ""
    assert email_domain("info@localhost") == ""
    assert email_domain("info@8.8.8.8") == ""
    assert email_domain("info@example.com/path") == ""
    assert email_domain("info@example..com") == ""
    assert email_domain("bad local@example.com") == ""
    assert email_domain("info@-example.com") == ""


def test_invalid_coordinates_are_omitted_before_a_provider_request():
    definition = {
        "field_mapping_json": json.dumps({
            "company_name": "name", "latitude": "lat", "longitude": "lng",
        }),
        "entity_key_field": "id", "site_key": "site", "source_dataset_key": "firms",
        "base_url": "https://source.example",
    }
    source = {
        "data_json": json.dumps({
            "id": "42", "name": "Source Name", "lat": "91", "lng": "Infinity",
        }),
        "generic_record_id": 7, "source_snapshot_id": 9,
        "source_url": "https://source.example/42",
    }

    identity = enrichment._identity(definition, source, None)

    assert identity.latitude is None
    assert identity.longitude is None


def test_first_enriched_at_stays_the_entity_creation_time(conn):
    conn.execute(
        "INSERT INTO organization_entity (organization_id, created_at) VALUES (?,?)",
        ("org_timestamp", "2020-01-02T03:04:05Z"),
    )
    enrichment._upsert_fact(
        conn,
        "org_timestamp",
        FieldFact(
            "website_url", "https://example.com", "website",
            confidence=0.9, verification_status="verified",
        ),
    )
    identity = OrganizationIdentity(
        organization_id="org_timestamp", external_id="1", source_record_id=1,
        source_snapshot_id=1, source_url="https://source.example/1",
    )

    materialized = enrichment._materialized_data(conn, identity)

    assert materialized["first_enriched_at"] == "2020-01-02T03:04:05Z"


def test_a_run_refuses_a_provider_that_is_no_longer_configured(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    monkeypatch.setattr(enrichment, "provider_availability", lambda: [{
        "key": "website", "available": False,
    }])

    with pytest.raises(
        enrichment.EnrichmentError,
        match=r"providers are no longer configured: \['website'\]",
    ):
        enrichment.create_enrichment_job(
            conn, definition["enrichment_definition_id"]
        )

    assert conn.execute("SELECT count(*) FROM crawl_job").fetchone()[0] == 0


class _FakeWebsite:
    name = "website"

    def __init__(self, changed_external_id: str | None = None):
        self.changed_external_id = changed_external_id

    def run(self, identity):
        suffix = "-new" if identity.external_id == self.changed_external_id else ""
        url = f"https://contractor-{identity.external_id}{suffix}.example"
        return ProviderResult("website", (
            FieldFact(
                "website_url", url, "website", source_url=url,
                confidence=0.96, verification_status="verified",
                evidence={"published_name": identity.company_name},
            ),
            FieldFact(
                "website_match_status", "verified", "website", source_url=url,
                confidence=0.96, verification_status="verified",
            ),
            FieldFact(
                "website_match_score", 0.96, "website", source_url=url,
                confidence=0.96, verification_status="verified",
            ),
        ))


class _SystemFailureProvider:
    name = "website"

    def __init__(self):
        self.calls = 0

    def run(self, identity):
        self.calls += 1
        return ProviderResult(
            self.name, checked=False, error="quota unavailable", system_error=True
        )


def _run(conn, definition_id: int, monkeypatch, provider) -> dict:
    monkeypatch.setattr(enrichment, "build_providers", lambda names: [provider])
    queued = enrichment.create_enrichment_job(conn, definition_id)
    return enrichment.run_enrichment_job_once(conn, queued["job_ref"])


def test_runs_are_resumable_idempotent_and_keep_changed_fact_history(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    definition_id = definition["enrichment_definition_id"]
    first = _run(conn, definition_id, monkeypatch, _FakeWebsite())
    assert first["status"] == "completed", first["error_summary"]

    output_id = conn.execute(
        "SELECT output_dataset_id FROM organization_enrichment_definition "
        "WHERE enrichment_definition_id = ?", (definition_id,)
    ).fetchone()[0]
    row_count = conn.execute(
        "SELECT count(*) FROM generic_record WHERE dataset_definition_id = ?",
        (output_id,),
    ).fetchone()[0]
    revisions = conn.execute(
        "SELECT count(*) FROM generic_record_revision AS revision "
        "JOIN generic_record AS record "
        "ON record.generic_record_id = revision.generic_record_id "
        "WHERE record.dataset_definition_id = ?", (output_id,)
    ).fetchone()[0]
    assert row_count == revisions == 4
    sightings = conn.execute(
        "SELECT external_id, first_run_ref FROM dataset_sighting "
        "WHERE dataset_key = 'contractor_enrichment' ORDER BY external_id"
    ).fetchall()
    assert len(sightings) == 4
    assert all(row["first_run_ref"] == first["job_ref"] for row in sightings)
    table = extraction.dataset_table_payload(
        conn, "contractor_enrichment", site_key="muqawil_org"
    )
    assert table is not None
    assert {row["observed_state"] for row in table["rows"]} == {"new"}

    _run(conn, definition_id, monkeypatch, _FakeWebsite())
    unchanged_revisions = conn.execute(
        "SELECT count(*) FROM generic_record_revision AS revision "
        "JOIN generic_record AS record "
        "ON record.generic_record_id = revision.generic_record_id "
        "WHERE record.dataset_definition_id = ?", (output_id,)
    ).fetchone()[0]
    assert unchanged_revisions == revisions

    changed_id = conn.execute(
        "SELECT source_external_id FROM organization_source_record ORDER BY rowid LIMIT 1"
    ).fetchone()[0]
    _run(conn, definition_id, monkeypatch, _FakeWebsite(changed_id))
    changed_revisions = conn.execute(
        "SELECT count(*) FROM generic_record_revision AS revision "
        "JOIN generic_record AS record "
        "ON record.generic_record_id = revision.generic_record_id "
        "WHERE record.dataset_definition_id = ?", (output_id,)
    ).fetchone()[0]
    assert changed_revisions == revisions + 1
    history = conn.execute(
        "SELECT count(*), sum(valid_to IS NOT NULL) FROM organization_fact AS fact "
        "JOIN organization_source_record AS source "
        "ON source.organization_id = fact.organization_id "
        "WHERE source.source_external_id = ? AND fact.field_key = 'website_url'",
        (changed_id,),
    ).fetchone()
    assert tuple(history) == (2, 1)

    linked = conn.execute(
        "SELECT source.generic_record_id, link.organization_id "
        "FROM organization_source_record AS link "
        "JOIN generic_record AS source "
        "ON source.generic_record_id = link.generic_record_id "
        "WHERE link.source_external_id = ?", (changed_id,)
    ).fetchone()
    conn.execute(
        "UPDATE generic_record SET status = 'unavailable' WHERE generic_record_id = ?",
        (linked["generic_record_id"],),
    )
    conn.commit()
    _run(conn, definition_id, monkeypatch, _FakeWebsite(changed_id))
    output_status = conn.execute(
        "SELECT status FROM generic_record WHERE dataset_definition_id = ? "
        "AND source_locator = ?",
        (output_id, f"organization:{linked['organization_id']}"),
    ).fetchone()[0]
    assert output_status == "unavailable"
    assert enrichment.get_definition(conn, definition_id)["counts"]["organizations"] == 3

    conn.execute(
        "UPDATE generic_record SET status = 'active' WHERE generic_record_id = ?",
        (linked["generic_record_id"],),
    )
    conn.commit()
    _run(conn, definition_id, monkeypatch, _FakeWebsite(changed_id))
    reactivated = conn.execute(
        "SELECT status FROM generic_record WHERE dataset_definition_id = ? "
        "AND source_locator = ?",
        (output_id, f"organization:{linked['organization_id']}"),
    ).fetchone()[0]
    assert reactivated == "active"
    assert enrichment.get_definition(conn, definition_id)["counts"]["organizations"] == 4


def test_repeated_system_errors_open_a_provider_circuit(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    provider = _SystemFailureProvider()

    completed = _run(
        conn, definition["enrichment_definition_id"], monkeypatch, provider
    )

    assert provider.calls == enrichment._PROVIDER_CIRCUIT_LIMIT
    assert completed["status"] == "completed_with_errors"
    assert completed["counters"]["provider_errors"] == 3
    assert completed["counters"]["providers_disabled"] == 1
    assert "3 provider request(s) failed" in completed["error_summary"]


def test_duplicate_detail_join_keys_are_refused_instead_of_last_row_winning(conn):
    detail_id = conn.execute(
        "SELECT dataset_definition_id FROM dataset_definition "
        "WHERE dataset_key = 'contractor_profiles'"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO generic_record "
        "(dataset_definition_id, record_key, schema_version_id, data_json, "
        "source_snapshot_id, source_locator, content_hash) "
        "SELECT dataset_definition_id, record_key || '-duplicate', schema_version_id, "
        "data_json, source_snapshot_id, source_locator || '#duplicate', content_hash "
        "FROM generic_record WHERE dataset_definition_id = ? LIMIT 1",
        (detail_id,),
    )
    with pytest.raises(
        enrichment.EnrichmentError, match="detail join key is not unique"
    ):
        enrichment.create_definition(conn, _request(conn))


def test_snapshot_items_are_processed_in_bounded_pages(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    monkeypatch.setattr(enrichment, "_SOURCE_BATCH_SIZE", 2)
    statements = []
    conn.set_trace_callback(statements.append)
    try:
        completed = _run(
            conn, definition["enrichment_definition_id"], monkeypatch, _FakeWebsite()
        )
    finally:
        conn.set_trace_callback(None)

    assert completed["progress_done"] == 4
    assert any(
        "FROM organization_enrichment_run_item" in statement
        and "LIMIT 2" in statement
        for statement in statements
    )


def test_the_extension_api_creates_and_queues_the_same_definition(registry, tmp_path):
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    client = TestClient(create_app(databases=registry, manifest_path=manifest))

    proposal = client.get("/api/enrichment/sources/contractors")
    assert proposal.status_code == 200
    created = client.post(
        "/api/enrichment/definitions", json=proposal.json()["proposal"]
    )
    assert created.status_code == 201
    definition_id = created.json()["enrichment_definition_id"]
    queued = client.post(f"/api/enrichment/definitions/{definition_id}/runs", json={})
    assert queued.status_code == 202
    job = client.get(f"/api/jobs/{queued.json()['job_ref']}").json()
    assert job["job_kind"] == "organization_enrichment"
    assert job["progress"]["unit"] == "organizations"
    refreshed = client.get("/api/enrichment/sources/contractors").json()
    assert refreshed["definition"]["latest_job"] == {
        "job_ref": queued.json()["job_ref"], "status": "queued",
    }
    duplicate = client.post(
        f"/api/enrichment/definitions/{definition_id}/runs", json={}
    )
    assert duplicate.status_code == 400
    diagnostics = client.get(
        f"/api/enrichment/definitions/{definition_id}/diagnostics"
    )
    assert diagnostics.status_code == 200
    assert diagnostics.json()["compliance"] == {
        "google_storage_mode": "place_id_only",
        "legacy_durable_google_fact_count": 0,
        "legacy_google_output_row_count": 0,
        "legacy_google_output_revision_count": 0,
        "requires_owner_cleanup": False,
    }


def test_the_background_runner_dispatches_the_enrichment_job(registry, monkeypatch):
    # This test proves JobRunner dispatch, not whether a live website answers
    # during the suite. Keep the provider deterministic and network-free.
    monkeypatch.setattr(
        enrichment, "build_providers", lambda names: [_FakeWebsite()]
    )
    conn = registry.engine.connect()
    try:
        definition = enrichment.create_definition(conn, _request(conn))
        queued = enrichment.create_enrichment_job(
            conn, definition["enrichment_definition_id"]
        )
    finally:
        conn.close()

    path = str(registry.engine.path)
    runner = JobRunner(path, lambda: None, path_provider=lambda: path)
    runner._start_job(queued["job_ref"], None)
    deadline = time.monotonic() + 8
    while runner._running[queued["job_ref"]].is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    runner._running[queued["job_ref"]].join(timeout=1)

    check = registry.engine.connect()
    try:
        completed = get_job(check, queued["job_ref"])
    finally:
        check.close()
    assert completed["status"] == "completed", completed["error_summary"]
    assert completed["progress_done"] == 4


def _identity(**changes):
    from scrapex.enrichment.models import OrganizationIdentity

    values = {
        "organization_id": "org_1", "external_id": "1", "source_record_id": 1,
        "source_snapshot_id": 1, "source_url": "https://source.example/1",
        "company_name": "Example Builders", "email": "info@example.com",
    }
    values.update(changes)
    return OrganizationIdentity(**values)


def test_website_provider_extracts_only_after_the_published_name_matches():
    root = """<html><head><title>Example Builders</title>
      <meta name='description' content='Infrastructure and bridge construction'>
      <script type='application/ld+json'>{"@type":"Organization",
        "name":"Example Builders","serviceType":["Infrastructure","Bridges"]}</script>
      </head><body><h1>Example Builders</h1><a href='/careers'>Careers</a></body></html>"""
    careers = """<html><body>Certified ISO 9001 and ISO 45001.
      <a href='mailto:hr@example.com'>Recruitment</a>
      <a href='tel:+966112223333'>Call</a></body></html>"""

    def fetch(url):
        return FetchedPage(url, careers if url.endswith("/careers") else root)

    result = WebsiteProvider(fetch).run(_identity())
    facts = {fact.field_key: fact.value for fact in result.facts}
    assert facts["website_match_status"] == "verified"
    assert facts["iso_certifications"] == ["ISO 45001", "ISO 9001"]
    assert facts["core_specialties"] == ["Infrastructure", "Bridges"]
    assert facts["careers_contact"] == "hr@example.com"
    assert facts["verified_phone_secondary"] == "+966112223333"

    mismatch = WebsiteProvider(lambda url: FetchedPage(
        url, "<html><head><title>Unrelated Bakery</title></head><body>ISO 9001"
             "<a href='mailto:info@example.com'>Email</a>"
             "<a href='https://linkedin.com/company/example-builders'>LinkedIn</a>"
             "</body></html>"
    )).run(_identity())
    mismatch_facts = {fact.field_key: fact.value for fact in mismatch.facts}
    assert mismatch_facts["website_match_status"] == "manual_review"
    assert "iso_certifications" not in mismatch_facts
    assert "contact_emails" not in mismatch_facts
    assert "linkedin_company_url" not in mismatch_facts

    mention_only = WebsiteProvider(lambda url: FetchedPage(
        url, "<html><head><title>Example Builders</title></head>"
             "<body>Our consultants can explain ISO 9001 to customers.</body></html>"
    )).run(_identity())
    mention_facts = {fact.field_key: fact.value for fact in mention_only.facts}
    assert "iso_certifications" not in mention_facts

    negated = WebsiteProvider(lambda url: FetchedPage(
        url, "<html><head><title>Example Builders</title></head>"
             "<body>We are not certified to ISO 9001.</body></html>"
    )).run(_identity())
    negated_facts = {fact.field_key: fact.value for fact in negated.facts}
    assert "iso_certifications" not in negated_facts


def test_website_provider_uses_official_contact_and_linkedin_links_as_evidence():
    root = """<html><head><title>Example Builders</title></head><body>
      <a href='/about-company'>About the company</a>
      <a href='/contact-us'>Contact us</a>
      <a href='https://www.linkedin.com/company/example-builders/about/?trk=site'>LinkedIn</a>
      <a href='https://linkedin.com/in/not-the-company'>Founder</a>
      <a href='https://linkedin.com.evil.example/company/example-builders'>Fake</a>
      </body></html>"""
    contact = """<html><head><title>Contact Example Builders</title></head><body>
      <a href='mailto:INFO@EXAMPLE.COM?subject=Hello'>Email</a>
      <a href='mailto:hr@example.com'>Careers</a>
      <a href='mailto:media@outside-agency.com'>External media agency</a>
      <a href='tel:+966 11 222 3333'>Main phone</a>
      <a href='tel:+966112224444'>Second phone</a>
      <a href='https://wa.me/966501112233?text=Hello'>WhatsApp</a>
      </body></html>"""

    def fetch(url):
        return FetchedPage(url, contact if url.endswith("/contact-us") else root)

    result = WebsiteProvider(fetch).run(
        _identity(phone="+966 11 222 3333")
    )
    facts = {fact.field_key: fact for fact in result.facts}

    assert facts["contact_page_url"].value == "https://example.com/contact-us"
    assert facts["contact_emails"].value == ["info@example.com", "hr@example.com"]
    assert facts["contact_phones"].value == ["+966 11 222 3333", "+966112224444"]
    assert facts["verified_phone_secondary"].value == "+966112224444"
    assert facts["whatsapp_url"].value == "https://wa.me/966501112233"
    assert facts["linkedin_company_url"].value \
        == "https://www.linkedin.com/company/example-builders/"
    assert facts["linkedin_match_status"].value == "verified"
    assert facts["linkedin_match_score"].value == facts["website_match_score"].value
    assert facts["linkedin_company_url"].provider == "website"
    assert facts["linkedin_company_url"].evidence == {
        "relationship": "official_website_outbound_link",
        "linkedin_page_fetched": False,
    }


def test_multiple_official_linkedin_company_links_require_manual_review():
    root = """<html><head><title>Example Builders</title></head><body>
      <a href='https://linkedin.com/company/example-builders'>LinkedIn</a>
      <a href='https://linkedin.com/company/example-holdings'>Holding company</a>
      </body></html>"""

    result = WebsiteProvider(lambda url: FetchedPage(url, root)).run(_identity())
    facts = {fact.field_key: fact for fact in result.facts}

    assert "linkedin_company_url" not in facts
    assert facts["linkedin_match_status"].value == "manual_review"
    assert facts["linkedin_match_status"].evidence["candidates"] == [
        "https://www.linkedin.com/company/example-builders/",
        "https://www.linkedin.com/company/example-holdings/",
    ]


def test_website_accepts_an_exact_source_email_even_when_its_domain_is_generic():
    root = """<html><head><title>Example Builders</title></head><body>
      <a href='mailto:owner@gmail.com'>Source-confirmed email</a>
      <a href='mailto:media@outside-agency.com'>External media agency</a>
      </body></html>"""

    result = WebsiteProvider(lambda url: FetchedPage(url, root)).run(
        _identity(website="https://example.com", email="owner@gmail.com")
    )
    facts = {fact.field_key: fact for fact in result.facts}

    assert facts["contact_emails"].value == ["owner@gmail.com"]


def test_contact_page_is_not_starved_by_many_careers_links():
    html = "<html><body>" + "".join(
        f"<a href='/careers/{index}'>Careers {index}</a>" for index in range(6)
    ) + "<a href='/contact'>Contact</a></body></html>"

    links = website_provider._useful_links(
        website_provider.BeautifulSoup(html, "lxml"), "https://example.com"
    )

    assert links[0] == "https://example.com/contact"
    assert "https://example.com/contact" in links[:4]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://linkedin.com/company/acme", "https://www.linkedin.com/company/acme/"),
        ("http://sa.linkedin.com/company/123/about", "https://www.linkedin.com/company/123/"),
        ("https://linkedin.com/in/person", ""),
        ("https://linkedin.com/shareArticle?url=x", ""),
        ("https://linkedin.com.evil.example/company/acme", ""),
        ("javascript:alert(1)", ""),
    ],
)
def test_linkedin_company_links_are_canonical_and_fail_closed(value, expected):
    assert website_provider._linkedin_company_url(value) == expected


def test_website_provider_deduplicates_specialties_across_discovery_pages():
    root = """<html><head><title>Example Builders</title>
      <script type='application/ld+json'>{"@type":"Organization",
        "name":"Example Builders","serviceType":["Bridges","Roads"]}</script>
      </head><body><a href='/about'>About</a></body></html>"""
    about = """<html><head><title>About Example Builders</title>
      <script type='application/ld+json'>{"@type":"Organization",
        "name":"Example Builders","serviceType":["Bridges","Roads"]}</script>
      </head></html>"""

    result = WebsiteProvider(
        lambda url: FetchedPage(url, about if url.endswith("/about") else root)
    ).run(_identity())
    facts = {fact.field_key: fact.value for fact in result.facts}

    assert facts["core_specialties"] == ["Bridges", "Roads"]


def test_website_peer_verification_fails_closed_for_rebinding_or_missing_peer():
    class Stream:
        def __init__(self, address):
            self.address = address

        def get_extra_info(self, name):
            return self.address if name == "server_addr" else None

    public = httpx.Response(
        200, extensions={"network_stream": Stream(("8.8.8.8", 443))}
    )
    private = httpx.Response(
        200, extensions={"network_stream": Stream(("127.0.0.1", 443))}
    )

    assert website_provider._public_peer(public) is True
    assert website_provider._public_peer(private) is False
    assert website_provider._public_peer(httpx.Response(200)) is False


def test_website_request_connects_to_the_address_that_was_validated(monkeypatch):
    class Stream:
        def get_extra_info(self, name):
            return ("8.8.8.8", 443) if name == "server_addr" else None

    seen = {}

    def answer(request):
        seen["host"] = request.url.host
        seen["header"] = request.headers["host"]
        seen["sni"] = request.extensions["sni_hostname"]
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text="<h1>Example</h1>",
            extensions={"network_stream": Stream()}, request=request,
        )

    monkeypatch.setattr(
        website_provider, "_public_addresses", lambda host, port=443: ("8.8.8.8",)
    )
    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        page = website_provider._fetch_with_client(client, "https://example.com/about")

    assert page.url == "https://example.com/about"
    assert seen == {"host": "8.8.8.8", "header": "example.com", "sni": "example.com"}


def test_website_request_refuses_nonstandard_ports_before_connect(monkeypatch):
    called = False

    def answer(request):
        nonlocal called
        called = True
        return httpx.Response(200, request=request)

    with httpx.Client(transport=httpx.MockTransport(answer)) as client, pytest.raises(
        ValueError, match="non-standard network port"
    ):
        website_provider._fetch_with_client(client, "https://example.com:8443/")
    assert called is False


def test_website_dns_resolution_has_a_bounded_wait(monkeypatch):
    monkeypatch.setenv("SCRAPEX_DNS_TIMEOUT_SECONDS", "0.01")

    def slow_resolution(*args, **kwargs):
        time.sleep(0.2)
        return []

    monkeypatch.setattr(website_provider.socket, "getaddrinfo", slow_resolution)

    started = time.monotonic()
    assert website_provider._public_addresses("slow.example") == ()
    assert time.monotonic() - started < 0.15


def test_website_rejects_redirects_outside_the_candidate_domain(monkeypatch):
    class Stream:
        def get_extra_info(self, name):
            return ("8.8.8.8", 443) if name == "server_addr" else None

    calls = 0

    def answer(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            302, headers={"location": "https://unrelated.invalid/landing"},
            extensions={"network_stream": Stream()}, request=request,
        )

    monkeypatch.setattr(
        website_provider, "_public_addresses", lambda host, port=443: ("8.8.8.8",)
    )
    with httpx.Client(transport=httpx.MockTransport(answer)) as client, pytest.raises(
        ValueError, match="outside its organization domain"
    ):
        website_provider._fetch_with_client(client, "https://example.com/")
    assert calls == 1


def test_website_obeys_robots_for_discovered_pages():
    fetched = []

    def fetch(url):
        fetched.append(url)
        if url.endswith("/private"):
            return FetchedPage(
                url,
                "<html><title>Example Builders</title>"
                "<p>We are certified to ISO 9001.</p></html>",
            )
        return FetchedPage(
            "https://example.com/",
            "<html><title>Example Builders</title>"
            "<a href='/private'>About our company</a></html>",
        )

    provider = WebsiteProvider(fetch)
    provider._robots_fetch = lambda url: FetchedPage(
        url, "User-agent: *\nDisallow: /private\n", 200
    )
    result = provider.run(_identity())

    assert fetched == ["https://example.com"]
    assert "iso_certifications" not in {fact.field_key for fact in result.facts}


def test_google_places_requires_identity_evidence_before_verification():
    place = {
        "id": "place-1",
        "displayName": {"text": "Example Builders"},
        "formattedAddress": "Riyadh, Saudi Arabia",
        "internationalPhoneNumber": "+966 11 222 3333",
        "websiteUri": "https://example.com",
        "googleMapsUri": "https://maps.google.com/?cid=123",
        "businessStatus": "OPERATIONAL",
        "rating": 4.7,
        "userRatingCount": 91,
        "location": {"latitude": 24.7136, "longitude": 46.6753},
    }
    provider = GooglePlacesProvider("secret", post=lambda key, body: {"places": [place]})
    result = provider.run(_identity(
        phone="+966500000000", latitude=24.7136, longitude=46.6753,
        city="Riyadh", country="Saudi Arabia",
    ))
    facts = {fact.field_key: fact.value for fact in result.facts}
    assert facts["google_place_id"] == "place-1"
    assert facts["google_attribution"] == "Google Maps"
    assert "google_match_status" not in facts
    assert "google_match_score" not in facts
    assert "reviews_count" not in facts
    assert "google_maps_url" not in facts
    assert "google_maps_cid_url" not in facts
    assert "verified_phone_secondary" not in facts

    malformed_phone = provider.run(_identity(phone="N/A", email=""))
    malformed_facts = {fact.field_key: fact.value for fact in malformed_phone.facts}
    assert malformed_facts == {}

    mismatch = provider.run(_identity(
        company_name="Another Company", email="info@another.example",
        phone="+966500000000", latitude=24.7136, longitude=46.6753,
    ))
    mismatch_facts = {fact.field_key: fact.value for fact in mismatch.facts}
    assert mismatch_facts == {}


def test_business_activity_words_remain_identity_evidence():
    assert name_similarity("Advanced Contracting", "Advanced Trading") < 0.88
    assert name_similarity("المتقدمة للمقاولات", "المتقدمة للتجارة") < 0.88


class _ChangingFactsProvider:
    name = "website"

    def __init__(self, *, fail: bool = False, include_phone: bool = True):
        self.fail = fail
        self.include_phone = include_phone

    def run(self, identity):
        if self.fail:
            return ProviderResult(
                self.name, checked=False, error="temporary outage", system_error=True
            )
        facts = [FieldFact(
            "website_url", f"https://{identity.external_id}.example", self.name,
            confidence=0.95, verification_status="verified",
        )]
        if self.include_phone:
            facts.append(FieldFact(
                "verified_phone_secondary", "+966112223333", self.name,
                confidence=0.9, verification_status="verified",
            ))
        return ProviderResult(self.name, tuple(facts))


def test_successful_observation_expires_missing_facts_but_failure_keeps_them(
    conn, monkeypatch
):
    definition = enrichment.create_definition(conn, _request(conn))
    definition_id = definition["enrichment_definition_id"]
    _run(conn, definition_id, monkeypatch, _ChangingFactsProvider())

    _run(conn, definition_id, monkeypatch, _ChangingFactsProvider(fail=True))
    assert conn.execute(
        "SELECT count(*) FROM organization_fact WHERE provider='website' "
        "AND field_key='verified_phone_secondary' AND valid_to IS NULL"
    ).fetchone()[0] == 4

    _run(conn, definition_id, monkeypatch, _ChangingFactsProvider(include_phone=False))
    assert conn.execute(
        "SELECT count(*) FROM organization_fact WHERE provider='website' "
        "AND field_key='verified_phone_secondary' AND valid_to IS NULL"
    ).fetchone()[0] == 0


def test_removed_provider_facts_remain_consistent_until_the_next_run(
    conn, monkeypatch
):
    request = _request(conn)
    definition = enrichment.create_definition(conn, request)
    definition_id = definition["enrichment_definition_id"]
    _run(conn, definition_id, monkeypatch, _FakeWebsite())
    monkeypatch.setattr(enrichment, "provider_availability", lambda: [
        {"key": "website", "available": True},
        {"key": "replacement", "available": True},
    ])
    enrichment.update_definition(
        conn, definition_id, request.model_copy(update={"providers": ["replacement"]})
    )
    assert conn.execute(
        "SELECT count(*) FROM organization_fact WHERE provider='website' "
        "AND valid_to IS NULL"
    ).fetchone()[0] > 0

    class ReplacementProvider:
        name = "replacement"

        def run(self, identity):
            return ProviderResult(self.name)

    _run(conn, definition_id, monkeypatch, ReplacementProvider())
    assert conn.execute(
        "SELECT count(*) FROM organization_fact WHERE provider='website' "
        "AND valid_to IS NULL"
    ).fetchone()[0] == 0
    output_id = enrichment._definition_row(conn, definition_id)["output_dataset_id"]
    assert conn.execute(
        "SELECT count(*) FROM generic_record WHERE dataset_definition_id=? "
        "AND status='active' AND json_extract(data_json,'$.website_url') IS NOT NULL",
        (output_id,),
    ).fetchone()[0] == 0


def test_provider_cache_is_invalidated_by_a_provider_version_change(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    definition_id = definition["enrichment_definition_id"]

    class CachedProvider:
        name = "website"
        ttl_seconds = 3600

        def __init__(self):
            self.calls = 0

        def run(self, identity):
            self.calls += 1
            return ProviderResult(self.name, (
                FieldFact(
                    "website_url", f"https://{identity.external_id}.example",
                    self.name, confidence=0.9, verification_status="verified",
                ),
            ))

    first = CachedProvider()
    _run(conn, definition_id, monkeypatch, first)
    same = CachedProvider()
    _run(conn, definition_id, monkeypatch, same)
    conn.execute(
        "UPDATE organization_provider_observation SET provider_version='obsolete' "
        "WHERE provider='website'"
    )
    changed = CachedProvider()
    _run(conn, definition_id, monkeypatch, changed)

    assert first.calls == 4
    assert same.calls == 0
    assert changed.calls == 4


def test_job_creation_can_join_a_larger_atomic_transaction(conn):
    job_ref = create_job(
        conn, ["contractors"], job_kind="organization_enrichment", commit=False
    )
    assert get_job(conn, job_ref) is not None
    conn.rollback()
    assert get_job(conn, job_ref) is None


def test_job_reads_the_source_snapshot_captured_when_it_was_queued(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    queued = enrichment.create_enrichment_job(
        conn, definition["enrichment_definition_id"]
    )
    first = conn.execute(
        "SELECT generic_record_id, data_json FROM generic_record "
        "WHERE dataset_definition_id=(SELECT source_dataset_id FROM "
        "organization_enrichment_definition WHERE enrichment_definition_id=?) "
        "ORDER BY generic_record_id LIMIT 1",
        (definition["enrichment_definition_id"],),
    ).fetchone()
    original = json.loads(first["data_json"])["company_name"]
    conn.execute(
        "UPDATE generic_record SET data_json=json_set(data_json, '$.company_name', ?) "
        "WHERE generic_record_id=?",
        ("Mutated after queue", first["generic_record_id"]),
    )
    conn.commit()

    captured = []

    class CaptureProvider:
        name = "website"

        def run(self, identity):
            captured.append(identity.company_name)
            return ProviderResult(self.name)

    monkeypatch.setattr(enrichment, "build_providers", lambda names: [CaptureProvider()])
    enrichment.run_enrichment_job_once(conn, queued["job_ref"])

    assert original in captured
    assert "Mutated after queue" not in captured
    compacted = conn.execute(
        "SELECT count(*) AS total, "
        "sum(source_data_json IS NULL AND length(source_content_hash) > 0) AS compacted "
        "FROM organization_enrichment_run_item WHERE job_id=("
        "SELECT job_id FROM crawl_job WHERE job_ref=?)",
        (queued["job_ref"],),
    ).fetchone()
    assert compacted["compacted"] == compacted["total"] == 4


def test_job_uses_the_mapping_version_captured_when_it_was_queued(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    queued = enrichment.create_enrichment_job(
        conn, definition["enrichment_definition_id"]
    )
    conn.execute(
        "UPDATE organization_enrichment_definition SET field_mapping_json=? "
        "WHERE enrichment_definition_id=?",
        (
            json.dumps({"company_name": "source:profile_url"}),
            definition["enrichment_definition_id"],
        ),
    )
    conn.commit()
    captured = []

    class CaptureProvider:
        name = "website"

        def run(self, identity):
            captured.append(identity.company_name)
            return ProviderResult(self.name)

    monkeypatch.setattr(enrichment, "build_providers", lambda names: [CaptureProvider()])
    enrichment.run_enrichment_job_once(conn, queued["job_ref"])

    assert captured
    assert all(name and not name.startswith("http") for name in captured)


def test_definition_status_controls_runs_and_retirement_is_recoverable(conn):
    definition = enrichment.create_definition(conn, _request(conn))
    definition_id = definition["enrichment_definition_id"]

    assert enrichment.set_definition_status(conn, definition_id, "paused")["status"] \
        == "paused"
    with pytest.raises(enrichment.EnrichmentError, match="is paused"):
        enrichment.create_enrichment_job(conn, definition_id)
    assert enrichment.set_definition_status(conn, definition_id, "active")["status"] \
        == "active"
    assert enrichment.set_definition_status(conn, definition_id, "retired")["status"] \
        == "retired"
    assert enrichment.set_definition_status(conn, definition_id, "active")["status"] \
        == "active"


def test_reviewed_cross_source_merge_shares_evidence_but_keeps_dataset_lineage(
    conn, monkeypatch
):
    first = enrichment.create_definition(conn, _request(conn))
    first_id = first["enrichment_definition_id"]
    _run(conn, first_id, monkeypatch, _FakeWebsite())

    _approve(
        conn,
        url="https://muqawil.org/en/other-contractors?page=1",
        html=LISTING,
        candidate=listing_candidate(LISTING),
        key="other_contractors",
        name="Other Contractors",
    )
    second_request = DefinitionCreate(**enrichment.propose_definition(
        conn, "other_contractors"
    )["proposal"])
    second = enrichment.create_definition(conn, second_request)
    second_id = second["enrichment_definition_id"]
    _run(conn, second_id, monkeypatch, _FakeWebsite())

    external_id = conn.execute(
        "SELECT source_external_id FROM organization_source_record "
        "WHERE enrichment_definition_id=? ORDER BY generic_record_id LIMIT 1",
        (first_id,),
    ).fetchone()[0]
    source_org = conn.execute(
        "SELECT organization_id FROM organization_source_record "
        "WHERE enrichment_definition_id=? AND source_external_id=?",
        (first_id, external_id),
    ).fetchone()[0]
    target_org = conn.execute(
        "SELECT organization_id FROM organization_source_record "
        "WHERE enrichment_definition_id=? AND source_external_id=?",
        (second_id, external_id),
    ).fetchone()[0]
    alias = "shared.example"
    conn.executemany(
        "INSERT INTO organization_identity_alias "
        "(organization_id,alias_type,normalized_value,value_hash,source_provider,"
        "confidence,review_status) VALUES (?,?,?,?,?,?,?)",
        [
            (source_org, "domain", alias, enrichment._digest(alias), "test", 0.8,
             "candidate"),
            (target_org, "domain", alias, enrichment._digest(alias), "test", 0.8,
             "candidate"),
        ],
    )
    enrichment._upsert_fact(
        conn,
        target_org,
        FieldFact(
            "website_url", "https://different.example", "website",
            confidence=0.96, verification_status="verified",
        ),
    )

    candidates = enrichment.identity_candidates(conn, first_id)["items"]
    assert any(item["candidate_id"] == target_org for item in candidates)
    merged = enrichment.merge_organization(
        conn,
        first_id,
        source_org,
        OrganizationMergeCreate(
            target_organization_id=target_org,
            reason="Owner confirmed both directory records describe one company",
        ),
    )
    assert merged["canonical_organization_id"] == target_org

    output_id = conn.execute(
        "SELECT output_dataset_id FROM organization_enrichment_definition "
        "WHERE enrichment_definition_id=?",
        (first_id,),
    ).fetchone()[0]
    output = json.loads(conn.execute(
        "SELECT data_json FROM generic_record WHERE dataset_definition_id=? "
        "AND source_locator=? AND status='active'",
        (output_id, f"organization:{target_org}"),
    ).fetchone()[0])
    assert output["organization_id"] == target_org
    assert output["source_external_id"] == external_id
    assert output["verification_status"] == "needs_manual_review"
    assert any(
        item["field_key"] == "website_url"
        for item in enrichment.review_queue(conn, first_id)["items"]
    )
    history = enrichment.merge_history(conn, first_id)["items"]
    assert history[0]["organization_merge_id"] == merged["organization_merge_id"]
    reversed_merge = enrichment.reverse_organization_merge(
        conn,
        first_id,
        merged["organization_merge_id"],
        OrganizationMergeReverseCreate(
            reason="Owner determined that the shared domain was not exclusive",
        ),
    )
    assert reversed_merge["status"] == "reversed"
    restored = json.loads(conn.execute(
        "SELECT data_json FROM generic_record WHERE dataset_definition_id=? "
        "AND source_locator=? AND status='active'",
        (output_id, f"organization:{source_org}"),
    ).fetchone()[0])
    assert restored["organization_id"] == source_org
    assert restored["source_external_id"] == external_id
    assert not any(
        item["field_key"] == "website_url"
        for item in enrichment.review_queue(conn, first_id)["items"]
    )


def test_record_exceptions_retry_the_same_snapshot_item(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    attempts = {}
    target = {"id": None}

    class FlakyProvider:
        name = "website"

        def run(self, identity):
            if target["id"] is None:
                target["id"] = identity.external_id
            attempts[identity.external_id] = attempts.get(identity.external_id, 0) + 1
            if identity.external_id == target["id"] and attempts[identity.external_id] < 3:
                raise RuntimeError("transient parser failure")
            return ProviderResult(self.name)

    completed = _run(
        conn, definition["enrichment_definition_id"], monkeypatch, FlakyProvider()
    )

    assert attempts[target["id"]] == 3
    assert completed["progress_done"] == 4
    assert conn.execute(
        "SELECT attempts FROM organization_enrichment_run_item AS item "
        "JOIN organization_enrichment_job AS job ON job.job_id=item.job_id "
        "WHERE job.enrichment_definition_id=? AND item.source_external_id=? "
        "ORDER BY item.job_id DESC LIMIT 1",
        (definition["enrichment_definition_id"], target["id"]),
    ).fetchone()[0] == 3


def test_output_schema_upgrades_additively(conn, monkeypatch):
    definition = enrichment.create_definition(conn, _request(conn))
    row = enrichment._definition_row(conn, definition["enrichment_definition_id"])
    monkeypatch.setattr(
        enrichment, "OUTPUT_FIELDS",
        (*enrichment.OUTPUT_FIELDS, OutputField("future_verified_signal")),
    )

    enrichment._create_output_schema(conn, int(row["output_dataset_id"]))

    versions = conn.execute(
        "SELECT version_number, valid_to FROM dataset_schema_version "
        "WHERE dataset_definition_id=? ORDER BY version_number",
        (row["output_dataset_id"],),
    ).fetchall()
    assert [item["version_number"] for item in versions] == [1, 2]
    assert versions[0]["valid_to"] is not None and versions[1]["valid_to"] is None


def test_definition_update_versions_configuration_and_review_can_resolve_a_fact(
    conn, monkeypatch
):
    request = _request(conn)
    definition = enrichment.create_definition(conn, request)
    updated = enrichment.update_definition(
        conn,
        definition["enrichment_definition_id"],
        request.model_copy(update={"output_dataset_name": "Verified Organizations"}),
    )
    assert updated["configuration_version"] == 2
    assert conn.execute(
        "SELECT count(*) FROM organization_enrichment_definition_history"
    ).fetchone()[0] == 1

    _run(conn, updated["enrichment_definition_id"], monkeypatch, _FakeWebsite())
    organization_id = conn.execute(
        "SELECT organization_id FROM organization_source_record LIMIT 1"
    ).fetchone()[0]
    fact_id = conn.execute(
        "INSERT INTO organization_fact "
        "(organization_id,field_key,value_json,value_hash,provider,confidence,"
        "verification_status,evidence_json) VALUES (?,?,?,?,?,?,?,?) "
        "RETURNING organization_fact_id",
        (
            organization_id, "careers_url", json.dumps("https://candidate.example/jobs"),
            enrichment._digest(json.dumps("https://candidate.example/jobs")),
            "website", 0.5, "manual_review", "{}",
        ),
    ).fetchone()[0]
    queue = enrichment.review_queue(conn, updated["enrichment_definition_id"])
    assert any(item["organization_fact_id"] == fact_id for item in queue["items"])

    with pytest.raises(enrichment.EnrichmentError, match="must be url"):
        enrichment.decide_review(
            conn, updated["enrichment_definition_id"], fact_id,
            ReviewDecisionCreate(action="override", value="javascript:alert(1)"),
        )

    decision = enrichment.decide_review(
        conn, updated["enrichment_definition_id"], fact_id,
        ReviewDecisionCreate(action="approve", reason="Official careers page"),
    )
    assert decision["materialized_value"] == "https://candidate.example/jobs"
    assert conn.execute(
        "SELECT count(*) FROM organization_fact WHERE organization_id=? "
        "AND field_key='careers_url' AND provider='owner_review' AND valid_to IS NULL",
        (organization_id,),
    ).fetchone()[0] == 1
