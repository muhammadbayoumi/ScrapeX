"""Spec 13: full rebuild archives instead of deleting, and keeps a rollback path."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.archive import archive_source, backup_database
from scrapex.ingest import ingest_payloads
from scrapex.vocab import ChangeType
from tests.test_ingest import make_entry, make_payload, one_row


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def test_archive_marks_products_vanished_without_touching_history(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    observations_before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]

    assert archive_source(conn, "ELSEWEDYSHOP") == 1
    assert conn.execute("SELECT status FROM source_product").fetchone()[0] == "vanished"
    # append-only history is untouched — a rebuild never destroys prices
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == observations_before


def test_archive_is_scoped_to_one_source(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    assert archive_source(conn, "MADAR") == 0     # a different source is untouched
    assert conn.execute("SELECT status FROM source_product").fetchone()[0] == "active"


def test_recrawling_an_archived_product_revives_it_as_returned(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    archive_source(conn, "ELSEWEDYSHOP")

    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="1,250.00")],
                                               scraped_at="2026-07-17T10:00:00Z")])
    assert conn.execute("SELECT status FROM source_product").fetchone()[0] == "active"
    kinds = [r[0] for r in conn.execute("SELECT change_type FROM change_event")]
    assert ChangeType.RETURNED.value in kinds


def test_backup_database_makes_a_readable_copy(tmp_path: Path):
    src = tmp_path / "harvest.db"
    conn = dbmod.connect(src)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.commit()
    conn.close()

    backup = backup_database(src, tag="rebuild")
    assert backup.exists() and backup != src
    restored = dbmod.connect(backup)
    try:
        assert restored.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1
    finally:
        restored.close()
