"""DB1: physical General/MarketLens isolation, migration, and recovery."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import catalog
from scrapex import catalog_models as models
from scrapex import db as legacy_db
from scrapex.databases import (
    DatabaseKindError,
    DatabaseRegistry,
    GeneralDatabase,
    MarketLensDatabase,
)
from scrapex.databases.split import (
    DatabaseSplitError,
    rollback_to_legacy,
    split_legacy_database,
)
from scrapex.ingest import ingest_payloads
from scrapex.webui.app import create_app
from tests.test_ingest import make_entry, make_payload, one_row

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _legacy_with_both_domains(path: Path) -> None:
    conn = legacy_db.connect(path)
    legacy_db.migrate(conn)
    result = ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    source_id = conn.execute(
        "SELECT source_id FROM source_site WHERE source_key = ? LIMIT 1",
        (result.source_key,),
    ).fetchone()[0]
    catalog.register_site(conn, models.SiteCreate(
        site_key="example_site",
        display_name="Example",
        base_url="https://example.com",
        price_source_id=source_id,
    ))
    catalog.register_dataset(conn, "example_site", models.DatasetCreate(
        dataset_key="rates",
        original_name="Reference rates",
        dataset_kind="table",
        discovery_method="html_table",
        locator={"selector": "#rates"},
    ))
    conn.commit()
    conn.close()


def test_fresh_registry_creates_two_typed_databases_without_domain_tables_crossing(
    tmp_path: Path,
):
    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "general" / "general.db"),
        MarketLensDatabase(tmp_path / "marketlens" / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )
    applied = registry.initialize()

    assert applied["general"] == list(
        range(1, registry.general.latest_schema_version + 1)
    )
    assert applied["marketlens"] == list(range(1, 19))   # +15 periods, +16 tax, +17 provenance, +18 job status
    assert registry.health()["general"]["status"] == "Healthy"
    assert registry.health()["marketlens"]["status"] == "Healthy"

    general = registry.general.connect()
    marketlens = registry.marketlens.connect()
    try:
        assert general.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'price_observation' LIMIT 1"
        ).fetchone() is None
        assert marketlens.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'site_profile' LIMIT 1"
        ).fetchone() is None
        assert general.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'database_kind' LIMIT 1"
        ).fetchone()[0] == "general"
        assert marketlens.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'database_kind' LIMIT 1"
        ).fetchone()[0] == "marketlens"
    finally:
        general.close()
        marketlens.close()

    with pytest.raises(DatabaseKindError, match="expected a general database"):
        GeneralDatabase(registry.marketlens.path).connect()
    with pytest.raises(legacy_db.WrongDatabaseKindError, match="General database"):
        legacy_db.connect(registry.general.path)

    ingested = registry.marketlens.write(
        lambda conn: ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    )
    assert ingested.observations == 1
    price_check = registry.marketlens.connect()
    try:
        assert price_check.execute(
            "SELECT COUNT(*) FROM price_observation LIMIT 1"
        ).fetchone()[0] == 1
    finally:
        price_check.close()


def test_split_preserves_price_history_and_moves_catalogue_to_general(tmp_path: Path):
    legacy = tmp_path / "harvest.db"
    _legacy_with_both_domains(legacy)
    pointer = tmp_path / "databases.json"

    result = split_legacy_database(
        legacy,
        general_path=tmp_path / "general" / "general.db",
        marketlens_path=tmp_path / "marketlens" / "marketlens.db",
        pointer_file=pointer,
    )

    assert result.status == "Succeeded"
    assert Path(result.legacy_backup).is_file()
    registry = DatabaseRegistry.read(pointer)
    general = registry.general.connect()
    marketlens = registry.marketlens.connect()
    try:
        site = general.execute(
            "SELECT site_key, marketlens_source_key FROM site_profile LIMIT 1"
        ).fetchone()
        assert tuple(site) == ("example_site", "ELSEWEDYSHOP")
        assert marketlens.execute(
            "SELECT COUNT(*) FROM price_observation LIMIT 1"
        ).fetchone()[0] == 1
        assert marketlens.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'site_profile' LIMIT 1"
        ).fetchone() is None
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            marketlens.execute("DELETE FROM price_observation")
    finally:
        general.close()
        marketlens.close()

    legacy_conn = sqlite3.connect(str(legacy))
    try:
        assert legacy_conn.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'sealed_at' LIMIT 1"
        ).fetchone() is not None
    finally:
        legacy_conn.close()


def test_failed_split_keeps_legacy_live_and_a_retry_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    legacy = tmp_path / "harvest.db"
    _legacy_with_both_domains(legacy)
    pointer = tmp_path / "databases.json"
    general = tmp_path / "general.db"
    marketlens = tmp_path / "marketlens.db"

    from scrapex.databases import split as split_module
    real_copy = split_module._copy_general

    def fail_copy(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(split_module, "_copy_general", fail_copy)
    with pytest.raises(OSError, match="disk full"):
        split_legacy_database(
            legacy, general_path=general, marketlens_path=marketlens,
            pointer_file=pointer,
        )
    assert not pointer.exists()
    assert not general.exists()
    assert not marketlens.exists()
    check = legacy_db.connect(legacy)
    try:
        assert check.execute(
            "SELECT COUNT(*) FROM price_observation LIMIT 1"
        ).fetchone()[0] == 1
    finally:
        check.close()

    monkeypatch.setattr(split_module, "_copy_general", real_copy)
    recovered = split_legacy_database(
        legacy, general_path=general, marketlens_path=marketlens,
        pointer_file=pointer,
    )
    assert recovered.status == "Succeeded"


def test_rollback_switches_pointer_without_deleting_split_databases(tmp_path: Path):
    legacy = tmp_path / "harvest.db"
    _legacy_with_both_domains(legacy)
    pointer = tmp_path / "databases.json"
    general = tmp_path / "general.db"
    marketlens = tmp_path / "marketlens.db"
    split_legacy_database(
        legacy, general_path=general, marketlens_path=marketlens,
        pointer_file=pointer,
    )

    restored = rollback_to_legacy(pointer)

    assert restored == legacy.resolve()
    assert general.exists() and marketlens.exists()
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    assert payload["mode"] == "legacy"
    check = legacy_db.connect(legacy)
    try:
        assert check.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'sealed_at' LIMIT 1"
        ).fetchone() is None
    finally:
        check.close()


def test_restore_refuses_the_other_database_kind_without_displacing_live_data(
    tmp_path: Path,
):
    general = GeneralDatabase(tmp_path / "general.db")
    marketlens = MarketLensDatabase(tmp_path / "marketlens.db")
    general.initialize()
    marketlens.initialize()
    original = general.path.read_bytes()

    with pytest.raises(DatabaseKindError, match="expected a general database"):
        general.restore(marketlens.path)

    assert general.path.read_bytes() == original
    assert not list(tmp_path.glob("general.replaced-*.db"))


def test_backup_restore_and_locks_are_independent_per_domain(tmp_path: Path):
    general = GeneralDatabase(tmp_path / "general.db")
    marketlens = MarketLensDatabase(tmp_path / "marketlens.db")
    general.initialize()
    marketlens.initialize()
    general.write(lambda conn: catalog.register_site(conn, models.SiteCreate(
        site_key="before_backup", display_name="Before", base_url="https://before.example"
    )))
    backup = general.backup(tmp_path / "backups")
    general.write(lambda conn: catalog.register_site(conn, models.SiteCreate(
        site_key="after_backup", display_name="After", base_url="https://after.example"
    )))

    with legacy_db.write_lock(general.path, timeout_s=0.1):
        with legacy_db.write_lock(marketlens.path, timeout_s=0.1):
            pass

    displaced = general.restore(backup)
    restored = general.connect()
    try:
        keys = [row[0] for row in restored.execute(
            "SELECT site_key FROM site_profile ORDER BY site_profile_id LIMIT 10"
        ).fetchall()]
    finally:
        restored.close()
    assert keys == ["before_backup"]
    assert displaced.is_file()
    assert marketlens.health().ok is True


def test_workspace_uses_general_catalogue_across_restart_and_reports_both_health_states(
    tmp_path: Path,
):
    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "general.db"),
        MarketLensDatabase(tmp_path / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    first = TestClient(create_app(databases=registry))
    created = first.post("/api/general/catalog/sites", json={
        "site_key": "example_site",
        "display_name": "Example",
        "base_url": "https://example.com",
        "marketlens_source_key": "ELSEWEDYSHOP",
    })
    assert created.status_code == 201

    restarted = TestClient(create_app(databases=DatabaseRegistry.read(registry.pointer_file)))
    sites = restarted.get("/api/general/catalog/sites", params={"limit": 10})
    health = restarted.get("/api/databases/health")
    price_health = restarted.get("/api/health")
    general_health = restarted.get("/api/general/health")
    marketlens_health = restarted.get("/api/marketlens/health")

    assert sites.json()["sites"][0]["site_key"] == "example_site"
    assert price_health.status_code == 200
    assert health.json()["status"] == "Healthy"
    assert set(health.json()["databases"]) == {"general", "marketlens"}
    assert general_health.json()["kind"] == "general"
    assert marketlens_health.json()["kind"] == "marketlens"


def test_workspace_move_changes_only_marketlens_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    from scrapex import storage

    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "legacy-location.json")
    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "general" / "general.db"),
        MarketLensDatabase(tmp_path / "marketlens" / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    original_general = registry.general.path
    client = TestClient(create_app(databases=registry))

    response = client.post("/api/storage/move", json={"folder": str(tmp_path / "moved")})

    assert response.status_code == 200, response.text
    followed = DatabaseRegistry.read(registry.pointer_file)
    assert followed.general.path == original_general
    assert followed.marketlens.path == tmp_path / "moved" / "marketlens.db"
    assert followed.health()["marketlens"]["status"] == "Healthy"
