"""The corruption scan is a question somebody asks, not a thing a page draws.

MEASURED ON HIS WAREHOUSE, 2026-09-06, at 2,080,395,264 bytes:

    GET /api/storage end to end   7.81 s   (10.26 s on a second reading)
    the deadline that path gets   5.000 s  (`STARTUP_DEADLINES.destinationData`)
      storage.health()            5.73 s
        PRAGMA quick_check        2.89 s
        PRAGMA foreign_key_check  1.50 s
      everything else             0.048 s
    after this change             0.060 s

So the Database page did not show a slow verdict -- it showed `unreadable` over three
empty cards, on every open, and so did the Settings screen's four rows before it. Both
pragmas are O(FILE SIZE), so raising the deadline buys time and not a fix.

THE SPLIT IS A RULE THIS CODEBASE ALREADY STATED. `EngineDatabase.health` took the same
keyword, for the same reason, off the same kind of measurement at 1,067 MB, and
`storage._warehouse_identity` says in terms: *"Integrity and identity are deliberately
separate checks."* `storage.health` asked both questions under one name. This is the
caller that was missed, not a new idea.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod, settings, storage  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def warehouse(tmp_path):
    """A real engine warehouse, built by the shipped migrator."""
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    try:
        yield conn, path
    finally:
        conn.close()


def _plant_a_foreign_key_violation(path: Path) -> None:
    """A child row whose parent does not exist.

    `PRAGMA foreign_key_check` is one of the two scans being made optional, so the
    cheapest honest way to prove the scan is what finds a fault is to plant a fault only
    that scan can see. `foreign_keys = OFF` is how it gets past the constraint on the
    way in -- which is also how a real one arrives: a restore, a merge, or a migration
    that ran with enforcement off.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO generic_page_snapshot "
            "  (source_url, content_type, html_content, content_hash, crawl_run_ref, "
            "   run_id) "
            "VALUES ('https://example.test/x', 'text/html', X'00', 'deadbeef', "
            "        'run-x', 999999)")
        conn.commit()
        planted = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()
    assert planted, (
        "the fixture planted no foreign key violation, so a test built on it would "
        "prove nothing about the scan")


def test_the_routine_verdict_does_not_run_the_scan(warehouse):
    """`integrity_checked` is the whole contract: it says which question was asked."""
    conn, path = warehouse

    answer = storage.storage_status(conn, path)

    assert answer["health"]["integrity_checked"] is False, (
        "GET /api/storage still runs the corruption scan, which is 5.68 s of a 5.73 s "
        "call on a 2 GB warehouse against a 5,000 ms deadline")
    assert "not been checked" in answer["health"]["detail"], (
        "the verdict says 'No problems found' after looking for none, which is a clean "
        f"bill of health for a question nobody asked: {answer['health']['detail']!r}")


def test_the_scan_is_what_finds_the_fault_and_asking_for_it_finds_it(warehouse):
    """THE MUTATION IS IN THE TEST. A damaged file must read `damaged` when the scan
    runs and `healthy` when it does not -- one file, two questions, two answers. If the
    narrow call reported `damaged` too, the flag would be skipping nothing."""
    conn, path = warehouse
    conn.close()
    _plant_a_foreign_key_violation(path)

    wide = storage.health(path, integrity=True)
    narrow = storage.health(path, integrity=False)

    assert wide["status"] == "damaged" and wide["ok"] is False, wide
    assert wide["foreign_key_problems"] >= 1, (
        "the wide verdict did not count the planted violation, so the scan it claims "
        f"to run is not running: {wide}")
    assert wide["integrity_checked"] is True
    assert narrow["status"] == "healthy" and narrow["ok"] is True, (
        "the narrow verdict found the fault, so `integrity=False` is not skipping the "
        f"scan and this whole change saves nothing: {narrow}")
    assert narrow["integrity_checked"] is False


def test_every_verdict_says_which_question_it_answered(tmp_path, warehouse):
    """EVERY EXIT, not the happy one. A caller branching on `integrity_checked` gets
    `None` from any path that forgot to stamp it, and `None` is neither claim."""
    conn, path = warehouse
    verdicts = [
        storage.health(tmp_path / "nothing-here.db"),
        storage.health(path, integrity=True),
        storage.health(path, integrity=False),
    ]
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    verdicts.append(storage.health(empty))
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not sqlite" * 100)
    verdicts.append(storage.health(junk))

    for verdict in verdicts:
        assert "integrity_checked" in verdict, (
            f"a verdict with no integrity_checked: {verdict}")
        assert isinstance(verdict["integrity_checked"], bool), verdict


def test_a_finding_nobody_cleared_still_counts(warehouse):
    """The routine verdict stopped looking for corruption, so on its own it would report
    a file the owner was told last week was damaged as ready -- "Enabled" on the same
    screen that said "damaged". The last WIDE verdict holds until another replaces it.
    """
    conn, path = warehouse
    assert storage.storage_status(conn, path)["ready"] is True

    settings.set_state(conn, "storage_integrity", {
        "status": "damaged", "ok": False, "at": "2026-09-06T12:00:00Z",
        "detail": "SQLite reported problems. Back up first, then run Repair."})
    conn.commit()

    answer = storage.storage_status(conn, path)

    assert answer["ready"] is False, (
        "a stored damaged verdict does not hold, so the page reports a file somebody "
        "was told is damaged as ready")
    assert "Repair" in answer["blocker"], answer["blocker"]
    assert answer["integrity"]["at"] == "2026-09-06T12:00:00Z", (
        "the route does not carry the stored verdict, so no page can say WHEN "
        "corruption was last looked for")


def test_a_cleared_finding_stops_holding(warehouse):
    """The other half, and the reason it is a separate test: a rule that only ever says
    no is not a rule. A later clean check must release what the damaged one held."""
    conn, path = warehouse
    settings.set_state(conn, "storage_integrity", {"status": "damaged", "ok": False,
                                                   "at": "2026-09-06T12:00:00Z"})
    conn.commit()
    assert storage.storage_status(conn, path)["ready"] is False

    settings.set_state(conn, "storage_integrity", {"status": "healthy", "ok": True,
                                                   "at": "2026-09-06T13:00:00Z"})
    conn.commit()

    answer = storage.storage_status(conn, path)
    assert answer["ready"] is True, "a clean check cannot clear an old finding"
    assert answer["blocker"] == ""


def test_the_state_key_is_declared_and_separate_from_the_last_action(warehouse):
    """`storage_last` is the last storage OPERATION -- a backup, a compaction, a repair.
    An integrity check acts on nothing, and reading one out of the other would date the
    answer to the wrong event. THIS IS NOT HYPOTHETICAL: the Database page's Backups row
    read `storage_last` and printed a backup from 2026-08-30 as the newest while the
    newest copy on disk was taken 2026-09-06."""
    conn, _path = warehouse

    assert "storage_integrity" in settings.STATE_KEYS
    assert settings.get_state(conn, "storage_integrity") is None, (
        "a database nobody has checked reports a check")
    settings.set_state(conn, "storage_integrity", {"ok": True, "at": "then"})
    conn.commit()

    assert settings.get_state(conn, "storage_last") is None, (
        "recording an integrity check wrote the last-action key as well, so a backup "
        "date now moves when nothing was backed up")


# ---- the route the control presses ------------------------------------------


@pytest.fixture()
def served(tmp_path):
    """The engine, over its real routes."""
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(path, manifest_path=manifest)), path


def test_the_route_answers_the_wide_question_and_records_it(served):
    """POST BECAUSE IT RECORDS WHAT IT FOUND, not because it changes the warehouse.
    Without a recorded moment, a card showing no problems is indistinguishable from a
    card that never asked."""
    client, path = served

    before = client.get("/api/storage").json()
    assert before["health"]["integrity_checked"] is False
    assert before["integrity"] is None

    answer = client.post("/api/storage/integrity")

    assert answer.status_code == 200, answer.text
    verdict = answer.json()
    assert verdict["integrity_checked"] is True, verdict
    assert verdict["status"] == "healthy" and verdict["ok"] is True, verdict
    assert verdict["at"], "the verdict carries no moment, so no page can date it"

    after = client.get("/api/storage").json()
    assert after["integrity"]["at"] == verdict["at"], (
        "the verdict was not recorded, so the next reading of the page cannot say when "
        "corruption was last looked for")
    assert after["health"]["integrity_checked"] is False, (
        "asking once turned the routine reading back into a full scan, which puts the "
        "5.7 s back on every page open")


def test_the_route_reports_damage_as_a_finding_and_stores_it(served):
    """A damaged verdict is a successful REQUEST with bad news in it. The route must not
    500 -- a page that cannot tell "the check failed" from "the file is damaged" tells
    the owner neither."""
    client, path = served
    _plant_a_foreign_key_violation(path)

    verdict = client.post("/api/storage/integrity")

    assert verdict.status_code == 200, verdict.text
    found = verdict.json()
    assert found["ok"] is False and found["status"] == "damaged", found

    after = client.get("/api/storage").json()
    assert after["ready"] is False, (
        "the route found damage and the next reading still reports the warehouse ready")
    assert after["integrity"]["ok"] is False


def test_the_routine_route_is_not_the_slow_one_any_more(served):
    """THE POINT OF THE WHOLE CHANGE, asserted structurally rather than by a clock: a
    timing test on a 4 KB fixture proves nothing about a 2 GB file, and the numbers that
    do are in this module's docstring. What IS checkable here is that the cheap route
    does not carry a scan and the expensive one does."""
    client, _path = served

    cheap = client.get("/api/storage").json()
    wide = client.post("/api/storage/integrity").json()

    assert cheap["health"]["integrity_checked"] is False
    assert wide["integrity_checked"] is True
    assert set(cheap) >= {"path", "sizes", "schema", "backups", "health", "integrity"}, (
        "the cheap route stopped carrying something the Database page draws")
