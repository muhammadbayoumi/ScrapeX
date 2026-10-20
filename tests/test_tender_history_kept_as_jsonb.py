"""The tender history kept as SQLite JSONB (migration 0026), on the real migration stream.

His decision on #1733, 2026-10-20: "the best, not the cheapest, with a reference". The
references (ES-6): Supabase recommends jsonb "for almost all cases"; PostgreSQL prefers
it unless the exact text matters, and the exact text is kept in `fetched_responses`;
SQLite's JSONB "is smaller and faster than text JSON". Measured on the six real
releases: 11% smaller, `json_extract` 4.8 times faster, the compile's read unchanged.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import tenderstore
from scrapex.databases.domain import EngineDatabase
from scrapex.sites import worldbank as wb

MIGRATION = "0026_tender_history_kept_as_jsonb.sql"
FIXTURE = Path(__file__).parent / "fixtures" / "worldbank" / "notices.json"
NOTICES = {n["id"]: n for n in json.loads(FIXTURE.read_text(encoding="utf-8"))["notices"]}
IFB = "OP00158446"


@pytest.fixture()
def conn(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    connection.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                       ("worldbank_org", "World Bank procurement notices"))
    connection.commit()
    yield connection
    connection.close()


def _site(conn) -> int:
    return conn.execute("SELECT source_id FROM source_site WHERE source_key = 'worldbank_org'"
                        ).fetchone()[0]


def _store(conn, notice_id: str) -> tenderstore.Stored:
    stored = tenderstore.store_release(conn, source_site_id=_site(conn),
                                       release=wb.release_from_notice(NOTICES[notice_id]),
                                       fetched_response_id=None)
    conn.commit()
    return stored


def test_a_release_is_stored_as_jsonb_and_read_back_whole(conn):
    stored = _store(conn, IFB)
    kind, text = conn.execute("SELECT typeof(payload), json(payload) FROM tender_releases "
                              "WHERE id = ?", (stored.tender_release_id,)).fetchone()
    assert kind == "blob"
    assert json.loads(text) == wb.release_from_notice(NOTICES[IFB]).payload


def test_sql_reads_a_field_of_the_payload(conn):
    _store(conn, IFB)
    title = conn.execute("SELECT json_extract(payload, '$.tender.title') FROM tender_releases"
                         ).fetchone()[0]
    assert title == wb.release_from_notice(NOTICES[IFB]).payload["tender"]["title"]


def test_the_compile_reads_the_jsonb_history(conn):
    stored = _store(conn, IFB)
    assert conn.execute("SELECT title FROM tenders WHERE tender_process_id = ?",
                        (stored.tender_process_id,)).fetchone()[0]


def test_the_digest_is_still_the_canonical_texts(conn):
    stored = _store(conn, IFB)
    digest = conn.execute("SELECT payload_sha256 FROM tender_releases WHERE id = ?",
                          (stored.tender_release_id,)).fetchone()[0]
    canonical = json.dumps(wb.release_from_notice(NOTICES[IFB]).payload, ensure_ascii=False,
                           sort_keys=True, separators=(",", ":"))
    assert digest == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("payload", [
    '{"id": "text, not jsonb"}',                  # text JSON is not what the column holds
    b"not jsonb at all",                          # a blob that is not JSONB
    # JSONB on the surface, an object by its header, malformed inside: `json_valid(x, 4)`
    # passes it, and only the strict check, `json_valid(x, 8)`, refuses it.
    bytes.fromhex("cc0c006127626317644b13311332"),
])
def test_the_column_takes_jsonb_only(conn, payload):
    stored = _store(conn, IFB)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tender_releases (tender_process_id, release_ref, released_at, tags, "
            "payload, payload_sha256) VALUES (?, 'OP00000001', '2026-01-01', '[]', ?, ?)",
            (stored.tender_process_id, payload, "0" * 64))


def test_the_column_takes_an_object_only(conn):
    stored = _store(conn, IFB)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tender_releases (tender_process_id, release_ref, released_at, tags, "
            "payload, payload_sha256) VALUES (?, 'OP00000001', '2026-01-01', '[]', "
            "jsonb('[1, 2]'), ?)", (stored.tender_process_id, "0" * 64))


def test_the_history_stays_append_only(conn):
    stored = _store(conn, IFB)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE tender_releases SET language = 'ar' WHERE id = ?",
                     (stored.tender_release_id,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM tender_releases WHERE id = ?", (stored.tender_release_id,))


def test_its_indexes_and_its_unique_key_stand_again(conn):
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(tender_releases)")}
    assert {"tender_releases_tender_process_id_idx",
            "tender_releases_fetched_response_id_idx"} <= indexes
    stored = _store(conn, IFB)
    again = tenderstore.store_release(conn, source_site_id=_site(conn),
                                      release=wb.release_from_notice(NOTICES[IFB]),
                                      fetched_response_id=None)
    assert not again.new and again.tender_release_id == stored.tender_release_id


def test_a_warehouse_at_0025_keeps_every_release_it_held(tmp_path, monkeypatch):
    """The table is empty on every installation before part 3b's first crawl; the migration
    still carries any row over, converted, and its digest unchanged."""
    db = EngineDatabase(tmp_path / "upgraded.db")
    whole = db._migrations
    at = [one.name for one in whole].index(MIGRATION)
    monkeypatch.setattr(db, "_migrations", whole[:at])
    db.initialize()
    payload = wb.release_from_notice(NOTICES[IFB]).payload
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with db.connect() as before:
        before.execute("INSERT INTO source_site (source_key, source_name) VALUES ('w', 'W')")
        before.execute("INSERT INTO tender_processes (ocid, source_site_id, source_record_id) "
                       "VALUES ('o', 1, 'k')")
        before.execute("INSERT INTO tender_releases (tender_process_id, release_ref, "
                       "released_at, tags, payload, payload_sha256) VALUES (1, ?, ?, ?, ?, ?)",
                       (payload["id"], payload["date"], json.dumps(payload["tag"]), canonical,
                        digest))
        before.commit()
    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    assert db.initialize() == [whole[at].number]
    with db.connect() as after:
        kind, text, kept = after.execute("SELECT typeof(payload), json(payload), "
                                         "payload_sha256 FROM tender_releases").fetchone()
        assert kind == "blob" and json.loads(text) == payload and kept == digest
        assert after.execute("SELECT count(*) FROM tender_releases").fetchone()[0] == 1
