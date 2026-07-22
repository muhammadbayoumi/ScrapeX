"""T5: integration tests against the REAL schema.sql on in-memory SQLite.

Schema and code can never drift — the same DDL the owner's harvest.db runs is
exercised here, including the A7 append-only triggers.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.vocab import CurationStatus, ReviewStatus


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = dbmod.connect(":memory:")
    dbmod.migrate(connection)
    yield connection
    connection.close()


def _seed_minimal(conn: sqlite3.Connection) -> dict[str, int]:
    """One site -> product -> variant -> offer -> run: the spine every test needs."""
    conn.execute(
        "INSERT INTO source_site (source_key, source_name, currency, default_vat_mode)"
        " VALUES ('MADAR', 'المدار', 'SAR', 'excl')"
    )
    source_id = conn.execute("SELECT source_id FROM source_site").fetchone()[0]
    conn.execute(
        "INSERT INTO source_product (source_id, external_product_id, external_sku, source_name)"
        " VALUES (?, '4672', '12015-FRP', 'Fire Retardant Plywood')",
        (source_id,),
    )
    product_id = conn.execute("SELECT source_product_id FROM source_product").fetchone()[0]
    conn.execute(
        "INSERT INTO source_variant (source_product_id, external_variant_id, external_sku, option_fingerprint)"
        " VALUES (?, '4671', '120151848', 'thickness_mm=18')",
        (product_id,),
    )
    variant_id = conn.execute("SELECT source_variant_id FROM source_variant").fetchone()[0]
    conn.execute(
        "INSERT INTO source_offer (source_variant_id, region, currency, vat_included)"
        " VALUES (?, 'SA', 'SAR', 0)",
        (variant_id,),
    )
    offer_id = conn.execute("SELECT offer_id FROM source_offer").fetchone()[0]
    conn.execute("INSERT INTO crawl_run (source_id) VALUES (?)", (source_id,))
    run_id = conn.execute("SELECT run_id FROM crawl_run").fetchone()[0]
    return {"source_id": source_id, "product_id": product_id,
            "variant_id": variant_id, "offer_id": offer_id, "run_id": run_id}


def _insert_observation(conn, ids, price: float = 168.78, hash_: str = "h1") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO price_observation"
        " (offer_id, observed_at, business_date, effective_price, currency, vat_included, run_id, record_hash)"
        " VALUES (?, '2026-07-16T10:00:00Z', '2026-07-16', ?, 'SAR', 0, ?, ?)",
        (ids["offer_id"], price, ids["run_id"], hash_),
    )


def test_migration_reaches_latest_version(conn):
    assert dbmod.schema_version(conn) == 27  # +0027 indexed view latest-pick


def test_all_owner_tables_exist(conn):
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    expected = {
        "material", "material_variant", "source_site", "source_product",
        "source_variant", "source_offer", "price_observation",
        "attribute_definition", "variant_attribute_value", "material_attribute_value",
        "classification_scheme", "classification_node", "material_classification",
        "classification_mapping", "source_product_match", "source_variant_match",
        "crawl_run", "raw_snapshot", "feed_assignment", "brand", "selling_unit",
        "crawl_job", "job_log_entry", "change_event",
    }
    missing = expected - tables
    assert not missing, f"schema.sql is missing tables: {missing}"


def test_price_observation_update_is_aborted(conn):
    """A7: append-only enforced by the schema itself, not by convention."""
    ids = _seed_minimal(conn)
    _insert_observation(conn, ids)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE price_observation SET effective_price = 1.0")


def test_price_observation_delete_is_aborted(conn):
    ids = _seed_minimal(conn)
    _insert_observation(conn, ids)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM price_observation")


def test_ingest_idempotency_via_dedupe_index(conn):
    """T4 foundation: same offer + business day + content hash -> one row."""
    ids = _seed_minimal(conn)
    _insert_observation(conn, ids, hash_="samehash")
    _insert_observation(conn, ids, hash_="samehash")  # INSERT OR IGNORE
    count = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    assert count == 1
    # A changed price produces a different record_hash -> second row appends.
    _insert_observation(conn, ids, price=170.00, hash_="newhash")
    count = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    assert count == 2


def test_source_product_unique_per_source(conn):
    """The owner's mandated UNIQUE(source_id, external_product_id)."""
    ids = _seed_minimal(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO source_product (source_id, external_product_id) VALUES (?, '4672')",
            (ids["source_id"],),
        )


def test_curation_status_vocabulary_matches_vocab_enum(conn):
    """Q1: the CHECK constraint and the Python enum can never drift."""
    ids = _seed_minimal(conn)
    for status in CurationStatus:
        conn.execute(
            "UPDATE source_product SET curation_status = ? WHERE source_product_id = ?",
            (status.value, ids["product_id"]),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE source_product SET curation_status = 'not_a_status' WHERE source_product_id = ?",
            (ids["product_id"],),
        )


def test_job_status_vocabulary_matches_vocab_enum(conn):
    """Q1 again, for crawl_job — migration 0020 widened this CHECK, and the
    rebuilt table must accept every JobStatus (completed_with_errors included)."""
    from scrapex.vocab import JobStatus

    conn.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys)"
                 " VALUES ('job_t', 'update', '[\"A\"]')")
    for status in JobStatus:
        conn.execute("UPDATE crawl_job SET status = ? WHERE job_ref = 'job_t'",
                     (status.value,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE crawl_job SET status = 'not_a_status' WHERE job_ref = 'job_t'")


def test_migration_0020_preserves_existing_jobs_and_their_log_references():
    """The CHECK widening rebuilds crawl_job on a LIVE warehouse; rows, ids and
    the job_log_entry references through job_id must survive the swap intact."""
    upgrading = dbmod.connect(":memory:")
    try:
        for number, file in dbmod._migration_files():     # the pre-0020 warehouse
            if number >= 20:
                continue
            upgrading.executescript(file.read_text(encoding="utf-8"))
            upgrading.execute(f"PRAGMA user_version = {number}")
        upgrading.execute("INSERT INTO crawl_job (job_ref, run_mode, status, source_keys)"
                          " VALUES ('job_old', 'update', 'completed', '[\"A\"]')")
        job_id = upgrading.execute("SELECT job_id FROM crawl_job").fetchone()[0]
        upgrading.execute("INSERT INTO job_log_entry (job_id, message) VALUES (?, 'kept')",
                          (job_id,))
        upgrading.commit()

        assert dbmod.migrate(upgrading) == [20, 21, 22, 23, 24, 25, 26, 27]

        joined = upgrading.execute(
            "SELECT j.job_ref, j.status, l.message FROM job_log_entry l"
            " JOIN crawl_job j ON j.job_id = l.job_id").fetchone()
        assert (joined["job_ref"], joined["status"], joined["message"]) == (
            "job_old", "completed", "kept")
        # The FK is enforced against the REBUILT table, not silently dangling.
        with pytest.raises(sqlite3.IntegrityError):
            upgrading.execute("INSERT INTO job_log_entry (job_id, message) VALUES (999, 'x')")
    finally:
        upgrading.close()


def test_review_status_vocabulary_matches_vocab_enum(conn):
    ids = _seed_minimal(conn)
    conn.execute("INSERT INTO material (material_name_en) VALUES ('FR Plywood')")
    material_id = conn.execute("SELECT material_id FROM material").fetchone()[0]
    for status in ReviewStatus:
        conn.execute(
            "INSERT INTO source_product_match (source_product_id, material_id, review_status, valid_to)"
            " VALUES (?, ?, ?, '2026-01-01')",  # valid_to set: avoids the active-unique index
            (ids["product_id"], material_id, status.value),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO source_product_match (source_product_id, material_id, review_status)"
            " VALUES (?, ?, 'not_a_status')",
            (ids["product_id"], material_id),
        )


def test_one_active_approved_match_per_source_product(conn):
    """The partial unique index: one current approved match, history retained."""
    ids = _seed_minimal(conn)
    conn.execute("INSERT INTO material (material_name_en) VALUES ('FR Plywood')")
    material_id = conn.execute("SELECT material_id FROM material").fetchone()[0]
    conn.execute(
        "INSERT INTO source_product_match (source_product_id, material_id, review_status)"
        " VALUES (?, ?, 'approved')",
        (ids["product_id"], material_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO source_product_match (source_product_id, material_id, review_status)"
            " VALUES (?, ?, 'approved')",
            (ids["product_id"], material_id),
        )
    # Retiring the first (valid_to) then approving a new one is legal history.
    conn.execute("UPDATE source_product_match SET valid_to = '2026-07-16' WHERE valid_to IS NULL")
    conn.execute(
        "INSERT INTO source_product_match (source_product_id, material_id, review_status)"
        " VALUES (?, ?, 'approved')",
        (ids["product_id"], material_id),
    )


def test_feed_assignment_unique_active_slot(conn):
    """ux_feed_assignment_active: one active row per (material, variant, region, priority)."""
    _seed_minimal(conn)
    conn.execute("INSERT INTO material (material_name_en) VALUES ('Diesel')")
    material_id = conn.execute("SELECT material_id FROM material").fetchone()[0]
    source_id = conn.execute("SELECT source_id FROM source_site").fetchone()[0]
    conn.execute(
        "INSERT INTO feed_assignment (material_id, region, source_id, priority, freshness_days)"
        " VALUES (?, 'SA', ?, 1, 40)",
        (material_id, source_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO feed_assignment (material_id, region, source_id, priority, freshness_days)"
            " VALUES (?, 'SA', ?, 1, 10)",
            (material_id, source_id),
        )
    # Same cell, priority 2 (declared fallback) is legal.
    conn.execute(
        "INSERT INTO feed_assignment (material_id, region, source_id, priority, freshness_days)"
        " VALUES (?, 'SA', ?, 2, 10)",
        (material_id, source_id),
    )


def test_flat_view_returns_matched_latest_observation(conn):
    """The Phase 0 skeleton view: only matched variants surface, latest obs wins."""
    ids = _seed_minimal(conn)
    _insert_observation(conn, ids, price=168.78, hash_="h1")
    # Unmatched variant -> view must be empty (unmatched data never publishes).
    assert conn.execute("SELECT COUNT(*) FROM v_material_price_tracking").fetchone()[0] == 0

    conn.execute("INSERT INTO material (material_name_en) VALUES ('FR Plywood')")
    material_id = conn.execute("SELECT material_id FROM material").fetchone()[0]
    conn.execute(
        "INSERT INTO material_variant (material_id, variant_name, spec_fingerprint)"
        " VALUES (?, '18mm 2440x1220', 'thickness=18mm')",
        (material_id,),
    )
    mv_id = conn.execute("SELECT variant_id FROM material_variant").fetchone()[0]
    conn.execute(
        "INSERT INTO source_variant_match (source_variant_id, variant_id, review_status)"
        " VALUES (?, ?, 'approved')",
        (ids["variant_id"], mv_id),
    )
    rows = conn.execute("SELECT * FROM v_material_price_tracking").fetchall()
    assert len(rows) == 1
    assert rows[0]["effective_price"] == 168.78

    # A newer observation replaces the old one in the view (append-only history kept).
    conn.execute(
        "INSERT INTO price_observation"
        " (offer_id, observed_at, business_date, effective_price, currency, vat_included, run_id, record_hash)"
        " VALUES (?, '2026-07-17T10:00:00Z', '2026-07-17', 172.50, 'SAR', 0, ?, 'h2')",
        (ids["offer_id"], ids["run_id"]),
    )
    rows = conn.execute("SELECT * FROM v_material_price_tracking").fetchall()
    assert len(rows) == 1
    assert rows[0]["effective_price"] == 172.50
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 2
