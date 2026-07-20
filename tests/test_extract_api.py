"""End-to-end HTTP and Workspace coverage for generic HTML-table extraction."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex.databases import (  # noqa: E402
    DatabaseRegistry,
    GeneralDatabase,
    MarketLensDatabase,
)
from scrapex.webui.app import create_app  # noqa: E402


HTML = """
<table id="regional-offices">
  <caption>Regional offices</caption>
  <tr><th>Office code</th><th>Office name</th><th>Employees</th></tr>
  <tr><td>RUH</td><td>الرياض</td><td>120</td></tr>
  <tr><td>JED</td><td>Jeddah</td><td>85</td></tr>
</table>
"""


@pytest.fixture()
def workspace(tmp_path: Path):
    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "general.db"),
        MarketLensDatabase(tmp_path / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    with TestClient(create_app(databases=registry)) as client:
        yield client, registry


def save_and_detect(client: TestClient, html: str = HTML):
    saved = client.post("/api/general/extract/snapshots", json={
        "source_url": "https://example.com/offices",
        "html_content": html,
    })
    assert saved.status_code == 201
    snapshot = saved.json()
    detected = client.get(
        f"/api/general/extract/snapshots/{snapshot['page_snapshot_id']}/candidates"
    )
    assert detected.status_code == 200
    return snapshot, detected.json()["candidates"]


def approval(candidate, identity_keys: set[str] | None = None):
    identity_keys = identity_keys or set(candidate["candidate_identity_fields"])
    return {
        "table_index": candidate["table_index"],
        "site_key": "example_site",
        "site_display_name": "Example site",
        "dataset_key": "regional_offices",
        "dataset_name": "Regional offices",
        "fields": [
            {
                "field_key": field["field_key"],
                "display_name": field["display_name"],
                "data_type": field["data_type"],
                "identity": field["field_key"] in identity_keys,
            }
            for field in candidate["fields"]
        ],
    }


def test_workspace_exposes_empty_loading_success_and_failure_states(workspace):
    client, _ = workspace

    response = client.get("/datasets")

    assert response.status_code == 200
    assert "Generic datasets" in response.text
    assert "Empty:" in response.text
    assert "Loading:" in response.text
    assert 'setState(discoveryState, "success"' in response.text
    assert 'setState(discoveryState, "failure"' in response.text
    assert "Save and detect tables" in response.text
    assert "Approve and ingest dataset" in response.text
    assert "Dynamic table" in response.text


def test_discovery_is_temporary_until_owner_approval(workspace):
    client, _ = workspace

    _, candidates = save_and_detect(client)

    assert candidates[0]["name"] == "Regional offices"
    assert client.get("/api/general/extract/datasets").json()["datasets"] == []


def test_non_product_table_is_approved_ingested_and_browsed_end_to_end(workspace):
    client, registry = workspace
    snapshot, candidates = save_and_detect(client)
    candidate = candidates[0]

    approved = client.post(
        f"/api/general/extract/snapshots/{snapshot['page_snapshot_id']}/approve",
        json=approval(candidate),
    )

    assert approved.status_code == 201
    dataset = approved.json()
    assert dataset["record_count"] == 2
    page = client.get(
        f"/api/general/extract/datasets/{dataset['dataset_definition_id']}/records",
        params={"limit": 1},
    )
    assert page.status_code == 200
    payload = page.json()
    assert [field["field_key"] for field in payload["fields"]] == [
        "office_code", "office_name", "employees",
    ]
    assert payload["records"][0]["data"] == {
        "office_code": "RUH", "office_name": "الرياض", "employees": 120,
    }
    assert payload["next_after_id"] is not None
    with closing(registry.general.connect()) as general:
        assert general.execute(
            "SELECT COUNT(*) FROM generic_record LIMIT 1"
        ).fetchone()[0] == 2
    with closing(registry.marketlens.connect()) as marketlens:
        assert marketlens.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'generic_record' LIMIT 1"
        ).fetchone() is None


def test_failure_is_actionable_and_corrected_approval_recovers(workspace):
    client, _ = workspace
    html = """
    <table><tr><th>Region</th><th>Code</th></tr>
      <tr><td>North</td><td>N-1</td></tr>
      <tr><td>North</td><td>N-2</td></tr>
    </table>
    """
    snapshot, candidates = save_and_detect(client, html)
    candidate = candidates[0]
    endpoint = (
        f"/api/general/extract/snapshots/{snapshot['page_snapshot_id']}/approve"
    )

    failed = client.post(endpoint, json=approval(candidate, {"region"}))

    assert failed.status_code == 422
    assert "duplicate record keys" in failed.json()["detail"]
    assert "try again" in failed.json()["detail"]
    assert client.get("/api/general/extract/datasets").json()["datasets"] == []

    recovered = client.post(endpoint, json=approval(candidate, {"code"}))
    assert recovered.status_code == 201
    assert recovered.json()["record_count"] == 2


def test_retry_and_restart_preserve_one_approved_ingestion(workspace):
    client, registry = workspace
    snapshot, candidates = save_and_detect(client)
    endpoint = (
        f"/api/general/extract/snapshots/{snapshot['page_snapshot_id']}/approve"
    )
    request = approval(candidates[0])
    first = client.post(endpoint, json=request)
    assert first.status_code == 201

    retry = client.post(endpoint, json=request)

    assert retry.status_code == 201
    assert retry.json()["recovered"] is True
    dataset_id = first.json()["dataset_definition_id"]
    with TestClient(create_app(databases=registry)) as restarted:
        datasets = restarted.get(
            "/api/general/extract/datasets"
        ).json()["datasets"]
        records = restarted.get(
            f"/api/general/extract/datasets/{dataset_id}/records"
        ).json()["records"]
    assert len(datasets) == 1
    assert len(records) == 2


def test_unknown_snapshot_and_invalid_page_limit_are_bounded_actionable_errors(workspace):
    client, _ = workspace

    missing = client.get("/api/general/extract/snapshots/999/candidates")
    too_large = client.get(
        "/api/general/extract/datasets", params={"limit": 101}
    )

    assert missing.status_code == 404
    assert "Save the HTML again and retry" in missing.json()["detail"]
    assert too_large.status_code == 422


def test_untrusted_values_are_never_inserted_into_workspace_markup(workspace):
    client, _ = workspace
    malicious = (
        "<table><tr><th>Payload</th></tr>"
        "<tr><td>&lt;img src=x onerror=alert(1)&gt;</td></tr></table>"
    )

    _, candidates = save_and_detect(client, malicious)
    page = client.get("/datasets")

    assert candidates[0]["sample_records"][0]["payload"] == (
        "<img src=x onerror=alert(1)>"
    )
    assert "<img src=x onerror=alert(1)>" not in page.text
    assert ".innerHTML" not in page.text
    assert "textContent" in page.text
    assert 'cell.dir = "auto"' in page.text
