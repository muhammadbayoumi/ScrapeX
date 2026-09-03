"""The panel can restore a snapshot, which it could not do at all until now.

MEASURED 2026-09-02, and it is the reason this file exists rather than a worry:

    controls on the engine's storage page          9
    of those the panel could call                  0
    callers of bundle.py unpack() outside tests    0

So the owner had a **backup button in his only interface and not one restore
control anywhere in it** — the Drive bundle could be built and uploaded and never
read back, and the local snapshot's restore lived on `_storage.html`, a page
`R-81` records that he does not open: *«انا لا استخدم terminal نهائى انا فقط
استخدم الواجهة من خلال extension»*.

WHAT THIS GUARDS, and each is a way the control could exist and not work:

  1. the route the panel calls is one the engine serves — the class of defect
     `OP-116` shipped, where a poll asked for a path that had been deleted;
  2. the listing carries every field the confirmation needs, because a
     destructive question that cannot name WHICH snapshot is unanswerable;
  3. the request is bounded by a deadline that covers a multi-gigabyte move. The
     first defect he reported on 2026-09-02 was "The request exceeded its
     10000 ms deadline" on a backup of a 1,490 MB warehouse, and shipping a
     restore under the generic bound would have reproduced it on the one action
     that must not stop halfway;
  4. the restore ASKS first, and the question names the snapshot.
"""
from __future__ import annotations

import pathlib
import re
import sqlite3

import pytest

pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS = ROOT / "extension" / "app.js"
APP_HTML = ROOT / "extension" / "app.html"
STARTUP = ROOT / "extension" / "startup.js"


def test_the_listing_route_exists_and_the_panel_asks_for_that_exact_path():
    """Two independently-maintained things: what the panel asks for, and what the
    engine mounts. `OP-116` is what happens when only one of them moves."""
    app_py = (ROOT / "scrapex" / "webui" / "app.py").read_text(encoding="utf-8")
    asked = re.findall(r'api\("(/api/storage/[a-z-]+)"', APP_JS.read_text(encoding="utf-8"))
    posted = re.findall(r'post\("(/api/storage/[a-z-]+)"', APP_JS.read_text(encoding="utf-8"))

    assert "/api/storage/backups" in asked, (
        "the panel does not read the snapshot listing, so it cannot offer a "
        "restore: /api/storage/restore takes a backup_path and nothing in the "
        "panel would know one")
    assert "/api/storage/restore" in posted, "the panel does not call restore"
    for path in set(asked + posted):
        assert f'"{path}"' in app_py, (
            f"the panel asks for {path} and scrapex/webui/app.py does not mount it")


def test_the_listing_carries_what_the_question_needs(tmp_path):
    """A confirmation that cannot name the snapshot is a question nobody can
    answer, so the fields are part of the contract and not a convenience."""
    from fastapi.testclient import TestClient

    from scrapex.databases.domain import EngineDatabase
    from scrapex.webui.app import create_app

    db = tmp_path / "engine.db"
    EngineDatabase(db).initialize()
    client = TestClient(create_app(db_path=db))

    empty = client.get("/api/storage/backups")
    assert empty.status_code == 200
    assert empty.json()["backups"] == [], "a fresh database has no snapshots"
    assert empty.json()["folder"], "the listing does not say where they are kept"

    assert client.post("/api/storage/backup").status_code == 200
    listed = client.get("/api/storage/backups").json()["backups"]
    assert len(listed) == 1
    assert set(listed[0]) == {"path", "name", "bytes", "modified_at", "tag"}, (
        f"the listing returns {sorted(listed[0])}. `path` is what restore takes, "
        "and the other four are what the confirmation has to show; anything MORE "
        "is a path the panel could be handed, which is the shape open-folder "
        "deliberately refuses")
    assert listed[0]["bytes"] > 0, "a snapshot of no bytes would restore nothing"


def test_a_restored_snapshot_really_becomes_the_live_database(tmp_path):
    """The whole point, end to end: the copy is made live and the old file is moved
    aside rather than deleted."""
    from fastapi.testclient import TestClient

    from scrapex.databases.domain import EngineDatabase
    from scrapex.webui.app import create_app

    db = tmp_path / "engine.db"
    EngineDatabase(db).initialize()
    client = TestClient(create_app(db_path=db))
    client.post("/api/storage/backup")
    snapshot = client.get("/api/storage/backups").json()["backups"][0]

    # A row that exists only AFTER the snapshot, so restoring must remove it.
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("INSERT INTO scrapex_meta (key, value) VALUES ('probe', 'after')")
        conn.commit()
    finally:
        conn.close()

    answer = client.post("/api/storage/restore", json={"backup_path": snapshot["path"]})
    assert answer.status_code == 200, answer.text

    conn = sqlite3.connect(str(db))
    try:
        found = conn.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'probe'").fetchone()
    finally:
        conn.close()
    assert found is None, (
        "the row written after the snapshot survived the restore, so the file that "
        "is live is not the snapshot")


def test_the_restore_request_is_bounded_for_a_multi_gigabyte_move():
    """`POST /api/storage/restore` does not stream, so the deadline must cover the
    whole operation. The generic bound is what produced the first defect he
    reported."""
    text = STARTUP.read_text(encoding="utf-8")
    assert "storageRestore" in text, "restore has no deadline of its own"
    match = re.search(r"storageRestore:\s*(\d+)", text)
    assert match, "storageRestore is not a number"
    assert int(match.group(1)) >= 300_000, (
        f"restore is bounded at {match.group(1)} ms. A 2 GB file move does not fit "
        "in that, and the failure mode is a report of failure over an operation "
        "that is still running — on the one action that must not stop halfway")
    assert re.search(r"api\\/storage\\/restore", text), (
        "no policy row matches the restore path, so it falls through to the generic "
        "deadline whatever storageRestore says")


def test_the_restore_asks_first_and_the_question_names_the_snapshot():
    """A destructive action behind a confirmation is the panel's own convention —
    the disconnect dialog — and the question has to be answerable."""
    html = APP_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")

    assert 'id="restore-veil"' in html and 'id="restore-confirm"' in html, (
        "there is no confirmation, so a click restores a warehouse")
    assert 'class="danger"' in html.split('id="restore-veil"')[1][:600], (
        "the confirm button is not marked danger, so it does not look like what it is")

    copy = js.split("function openRestoreDialog")[1][:1200]
    for needed, why in (
            ("modified_at", "the question does not say WHEN the snapshot was taken"),
            ("fmtMegabytes", "the question does not say how big it is"),
            ("moved aside", "the question does not say the live database is kept")):
        assert needed in copy, why

    failure = js.split("async function restoreSnapshot")[1][:1600]
    assert "Nothing has been changed" in failure, (
        "a failed restore does not tell the person nothing happened, which is the "
        "one thing they need after pressing a destructive button")
