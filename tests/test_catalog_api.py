"""G1 HTTP boundary: arbitrary catalogue definitions without generic-data claims."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "catalog-api.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


def _post_site(client, key="example_site", url="https://example.com"):
    response = client.post("/api/catalog/sites", json={
        "site_key": key,
        "display_name": "Example",
        "base_url": url,
    })
    assert response.status_code == 201
    return response.json()


def _post_dataset(client, site_key, key, name):
    response = client.post(f"/api/catalog/sites/{site_key}/datasets", json={
        "dataset_key": key,
        "original_name": name,
        "dataset_kind": "table",
        "discovery_method": "html_table",
        "locator": {"selector": f"#{key}"},
    })
    assert response.status_code == 201
    return response.json()


def _post_field(client, dataset_id, key, name):
    response = client.post(f"/api/catalog/datasets/{dataset_id}/fields", json={
        "field_key": key,
        "original_name": name,
        "data_type": "integer" if key.endswith("id") else "text",
    })
    assert response.status_code == 201
    return response.json()


def test_api_builds_two_dynamic_tables_and_a_suggested_relation(client):
    _post_site(client)
    orders = _post_dataset(client, "example_site", "orders", "Orders")
    lines = _post_dataset(client, "example_site", "lines", "Order lines")
    order_id = _post_field(
        client, orders["dataset_definition_id"], "order_id", "Order ID"
    )
    _post_field(client, orders["dataset_definition_id"], "total", "Total")
    line_order_id = _post_field(
        client, lines["dataset_definition_id"], "order_id", "Order ID"
    )

    relation = client.post(
        "/api/catalog/sites/example_site/relationships",
        json={
            "relationship_key": "orders_to_lines",
            "parent_dataset_id": orders["dataset_definition_id"],
            "child_dataset_id": lines["dataset_definition_id"],
            "cardinality": "one_to_many",
            "confidence": 0.8,
            "evidence": {"source": "matching_values"},
            "field_pairs": [{
                "parent_field_id": order_id["field_definition_id"],
                "child_field_id": line_order_id["field_definition_id"],
            }],
        },
    )
    assert relation.status_code == 201
    assert relation.json()["review_status"] == "suggested"

    datasets = client.get("/api/catalog/sites/example_site/datasets").json()
    assert [row["dataset_key"] for row in datasets["datasets"]] == ["orders", "lines"]
    assert len(client.get(
        f"/api/catalog/datasets/{orders['dataset_definition_id']}/fields"
    ).json()["fields"]) == 2
    assert len(client.get(
        f"/api/catalog/datasets/{lines['dataset_definition_id']}/fields"
    ).json()["fields"]) == 1
    assert len(client.get(
        "/api/catalog/sites/example_site/relationships"
    ).json()["relationships"]) == 1


def test_api_rejects_untyped_or_ambiguous_catalogue_input(client):
    assert client.post("/api/catalog/sites", json={
        "site_key": "Not Stable",
        "display_name": "Bad",
        "base_url": "not a url",
    }).status_code == 422

    _post_site(client)
    dataset = _post_dataset(client, "example_site", "orders", "Orders")
    bad_type = client.post(
        f"/api/catalog/datasets/{dataset['dataset_definition_id']}/fields",
        json={
            "field_key": "total",
            "original_name": "Total",
            "data_type": "whatever-the-source-said",
        },
    )
    assert bad_type.status_code == 422


def test_api_is_cursor_paginated_and_unknown_parents_are_404(client):
    for number in range(3):
        _post_site(client, f"site_{number}", f"https://site-{number}.example")
    first = client.get("/api/catalog/sites", params={"limit": 2}).json()
    second = client.get("/api/catalog/sites", params={
        "limit": 2, "after_id": first["next_after_id"]
    }).json()
    assert len(first["sites"]) == 2
    assert [row["site_key"] for row in second["sites"]] == ["site_2"]
    assert client.get(
        "/api/catalog/datasets/999/fields"
    ).status_code == 404
    assert client.get(
        "/api/catalog/sites/no_such_site/datasets"
    ).status_code == 404


def test_feature_manifest_reports_foundation_without_enabling_the_ui(client):
    features = {
        item["key"]: item for item in client.get("/api/features").json()["features"]
    }
    catalog_feature = features["generic_dataset_catalog"]
    assert catalog_feature["stage"] == "foundation"
    assert catalog_feature["enabled"] is False
