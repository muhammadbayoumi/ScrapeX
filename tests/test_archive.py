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

    ingest_payloads(conn, entry, [make_payload([one_row(price="1,250.00")],
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


# ---- the copy is atomic, because the policy now deletes ----------------------

def test_a_failure_after_the_copy_leaves_nothing_at_the_final_name(tmp_path, monkeypatch):
    """THE HAZARD THE RETENTION POLICY CREATED FOR ITSELF.

    `source.backup(target)` fills its destination page by page. While nothing pruned
    the pre-upgrade lineage, a copy interrupted halfway was clutter; once the upgrade
    path started applying the keep-N policy (`OP-136`), a partial file carrying the
    NEWEST stamp of its lineage could be kept while a complete older copy was
    deleted — the one moment a backup is needed being the one where it had been
    replaced by a fragment.
    """
    import os as _os

    live = tmp_path / "scrapex-engine.db"
    conn = sqlite3.connect(str(live))
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    def refuse(src, dst):
        raise OSError("the disk filled while the copy was being renamed")

    monkeypatch.setattr(_os, "replace", refuse)

    with pytest.raises(OSError):
        backup_database(live, tag="pre-upgrade")

    assert not list(tmp_path.glob("*.backup.db")), \
        "a copy that never completed took the name of a finished one"
    assert not list(tmp_path.glob("*.part")), "the partial file was left behind"
    assert live.is_file(), "the live database was disturbed by a failed backup"


def test_a_completed_copy_leaves_no_partial_beside_it(tmp_path):
    live = tmp_path / "scrapex-engine.db"
    conn = sqlite3.connect(str(live))
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()

    made = backup_database(live, tag="pre-upgrade")

    assert made.is_file() and made.name.endswith(".backup.db")
    assert not list(tmp_path.glob("*.part"))
    restored = sqlite3.connect(str(made))
    try:
        assert restored.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] >= 1
    finally:
        restored.close()
