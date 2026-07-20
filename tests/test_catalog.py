"""G1 generic catalogue: additive identities, dynamic fields and safe relations."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import catalog, catalog_relations
from scrapex import db as dbmod
from scrapex import catalog_models as models


@pytest.fixture()
def conn(tmp_path: Path):
    connection = dbmod.connect(tmp_path / "catalog.db")
    dbmod.migrate(connection)
    try:
        yield connection
    finally:
        connection.close()


def site(key: str = "example_site", url: str = "https://example.com"):
    return models.SiteCreate(site_key=key, display_name="Example", base_url=url)


def dataset(key: str, name: str, method: str = "html_table"):
    return models.DatasetCreate(
        dataset_key=key,
        original_name=name,
        dataset_kind="table",
        discovery_method=method,
        locator={"selector": f"#{key}"},
    )


def field(key: str, name: str, order: int = 0, data_type: str = "text"):
    return models.FieldCreate(
        field_key=key,
        original_name=name,
        display_order=order,
        data_type=data_type,
    )


def test_migration_creates_the_catalogue_and_integrity_triggers(conn):
    objects = {
        row["name"]: row["type"] for row in conn.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','trigger')"
        )
    }
    assert objects["site_profile"] == "table"
    assert objects["dataset_definition"] == "table"
    assert objects["field_definition"] == "table"
    assert objects["dataset_relationship"] == "table"
    assert objects["relationship_field_pair"] == "table"
    assert objects["trg_dataset_relationship_same_site_insert"] == "trigger"
    assert objects["trg_relationship_field_pair_matches_insert"] == "trigger"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 15


def test_one_site_can_hold_multiple_tables_with_different_dynamic_columns(conn):
    catalog.register_site(conn, site())
    orders = catalog.register_dataset(conn, "example_site", dataset("orders", "Orders"))
    customers = catalog.register_dataset(
        conn, "example_site", dataset("customers", "Customers")
    )
    for order, key in enumerate(("order_id", "customer_id", "total")):
        catalog.register_field(
            conn, orders["dataset_definition_id"], field(key, key.title(), order)
        )
    for order, key in enumerate(("customer_id", "name")):
        catalog.register_field(
            conn, customers["dataset_definition_id"], field(key, key.title(), order)
        )

    datasets = catalog.list_datasets(conn, "example_site")["datasets"]
    assert [item["dataset_key"] for item in datasets] == ["orders", "customers"]
    assert len(catalog.list_fields(
        conn, orders["dataset_definition_id"]
    )["fields"]) == 3
    assert len(catalog.list_fields(
        conn, customers["dataset_definition_id"]
    )["fields"]) == 2


def test_repeat_discovery_is_idempotent_and_preserves_original_names(conn):
    first_site = catalog.register_site(conn, site())
    second_site = catalog.register_site(conn, site())
    first_dataset = catalog.register_dataset(
        conn, "example_site", dataset("orders", "Orders table")
    )
    second_dataset = catalog.register_dataset(
        conn, "example_site", dataset("orders", "Orders table")
    )
    first_field = catalog.register_field(
        conn, first_dataset["dataset_definition_id"], field("order_id", "Order ID")
    )
    second_field = catalog.register_field(
        conn, first_dataset["dataset_definition_id"], field("order_id", "Order ID")
    )

    assert first_site["site_profile_id"] == second_site["site_profile_id"]
    assert first_dataset["dataset_definition_id"] == second_dataset["dataset_definition_id"]
    assert first_field["field_definition_id"] == second_field["field_definition_id"]
    assert conn.execute("SELECT COUNT(*) FROM site_profile").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM dataset_definition").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM field_definition").fetchone()[0] == 1

    with pytest.raises(models.CatalogConflict, match="another definition"):
        catalog.register_field(
            conn, first_dataset["dataset_definition_id"],
            field("order_id", "A different original name"),
        )
    stored = conn.execute(
        "SELECT original_name FROM field_definition"
    ).fetchone()[0]
    assert stored == "Order ID"


def test_retired_identities_are_never_silently_reused(conn):
    registered = catalog.register_site(conn, site())
    conn.execute(
        "UPDATE site_profile SET valid_to='2026-07-19T00:00:00Z' "
        "WHERE site_profile_id=?",
        (registered["site_profile_id"],),
    )
    with pytest.raises(models.CatalogConflict, match="reactivate it explicitly"):
        catalog.register_site(conn, site())
    assert catalog.list_sites(conn)["sites"] == []


def test_every_unbounded_catalogue_read_is_cursor_paginated(conn):
    for number in range(4):
        catalog.register_site(conn, site(
            key=f"site_{number}", url=f"https://site-{number}.example"
        ))
    first = catalog.list_sites(conn, limit=2)
    second = catalog.list_sites(conn, after_id=first["next_after_id"], limit=2)
    assert [item["site_key"] for item in first["sites"]] == ["site_0", "site_1"]
    assert [item["site_key"] for item in second["sites"]] == ["site_2", "site_3"]
    assert first["next_after_id"] is not None
    assert second["next_after_id"] is None
    with pytest.raises(ValueError, match="between 1 and"):
        catalog.list_sites(conn, limit=models.MAX_PAGE_SIZE + 1)


def _related_catalogue(conn):
    catalog.register_site(conn, site())
    parents = catalog.register_dataset(conn, "example_site", dataset("orders", "Orders"))
    children = catalog.register_dataset(
        conn, "example_site", dataset("lines", "Order lines")
    )
    parent_field = catalog.register_field(
        conn, parents["dataset_definition_id"],
        field("order_id", "Order ID", data_type="integer"),
    )
    child_field = catalog.register_field(
        conn, children["dataset_definition_id"],
        field("order_id", "Order ID", data_type="integer"),
    )
    return parents, children, parent_field, child_field


def test_relationships_stay_suggestions_and_carry_explicit_field_pairs(conn):
    parents, children, parent_field, child_field = _related_catalogue(conn)
    request = models.RelationshipCreate(
        relationship_key="orders_to_lines",
        parent_dataset_id=parents["dataset_definition_id"],
        child_dataset_id=children["dataset_definition_id"],
        cardinality="one_to_many",
        confidence=0.91,
        evidence={"matching_values": 42},
        field_pairs=[{
            "parent_field_id": parent_field["field_definition_id"],
            "child_field_id": child_field["field_definition_id"],
        }],
    )
    first = catalog_relations.propose_relationship(conn, "example_site", request)
    second = catalog_relations.propose_relationship(conn, "example_site", request)
    assert first["dataset_relationship_id"] == second["dataset_relationship_id"]
    assert first["review_status"] == "suggested"
    assert first["field_pairs"][0]["parent_field_key"] == "order_id"
    assert catalog_relations.list_relationships(
        conn, "example_site"
    )["relationships"] == [first]


def test_cross_site_relationships_are_refused_by_code_and_sql(conn):
    parents, _, parent_field, _ = _related_catalogue(conn)
    catalog.register_site(conn, site("other_site", "https://other.example"))
    other = catalog.register_dataset(conn, "other_site", dataset("other_rows", "Other"))
    other_field = catalog.register_field(
        conn, other["dataset_definition_id"], field("order_id", "Order ID")
    )
    request = models.RelationshipCreate(
        relationship_key="invalid_relation",
        parent_dataset_id=parents["dataset_definition_id"],
        child_dataset_id=other["dataset_definition_id"],
        field_pairs=[{
            "parent_field_id": parent_field["field_definition_id"],
            "child_field_id": other_field["field_definition_id"],
        }],
    )
    with pytest.raises(models.CatalogConflict, match="requested site"):
        catalog_relations.propose_relationship(conn, "example_site", request)

    example_id = conn.execute(
        "SELECT site_profile_id FROM site_profile WHERE site_key='example_site'"
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="same site profile"):
        conn.execute(
            "INSERT INTO dataset_relationship "
            "(site_profile_id, relationship_key, parent_dataset_id, child_dataset_id) "
            "VALUES (?,?,?,?)",
            (
                example_id, "direct_invalid", parents["dataset_definition_id"],
                other["dataset_definition_id"],
            ),
        )


def test_relationship_field_trigger_rejects_a_field_from_the_wrong_dataset(conn):
    parents, children, parent_field, child_field = _related_catalogue(conn)
    cursor = conn.execute(
        "INSERT INTO dataset_relationship "
        "(site_profile_id, relationship_key, parent_dataset_id, child_dataset_id) "
        "VALUES ((SELECT site_profile_id FROM site_profile WHERE site_key=?),?,?,?)",
        (
            "example_site", "orders_to_lines", parents["dataset_definition_id"],
            children["dataset_definition_id"],
        ),
    )
    with pytest.raises(sqlite3.IntegrityError, match="mapped datasets"):
        conn.execute(
            "INSERT INTO relationship_field_pair "
            "(dataset_relationship_id, parent_field_id, child_field_id) VALUES (?,?,?)",
            (
                cursor.lastrowid, child_field["field_definition_id"],
                parent_field["field_definition_id"],
            ),
        )


def test_catalogue_services_have_no_delete_path():
    for module in (catalog, catalog_relations):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "DELETE FROM" not in source
