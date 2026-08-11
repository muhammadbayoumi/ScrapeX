"""The engine builds the bundle; the panel puts it in Drive.

THE OWNER'S RULING, 2026-08-11: the engine fetches and saves locally, and the
extension owns every Google operation. These two routes are the whole of the
engine's part in a Drive backup, and the property that matters most is a
NEGATIVE one — that no route here accepts a Google token. A credential that
never crosses the boundary cannot leak from the far side of it.

The rest is the handover: a bundle that verifies, an archive whose bytes are
the ones described, and a download that cannot be pointed at a file outside the
backup folder.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scrapex import bundle
from scrapex.webui.app import create_app

# Guards the extension: the negative test below names extension/drive.js as the
# place this work lives instead, so a change to that file must run this.
# See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A real engine over a real database, with its backup folder in tmp_path."""
    from scrapex.databases.domain import EngineDatabase

    db_path = tmp_path / "engine" / "scrapex-engine.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    EngineDatabase(db_path).initialize()

    backups = tmp_path / "backups"
    backups.mkdir()
    import scrapex.webui.app as module
    monkeypatch.setattr(module, "backup_folder", lambda conn, path: backups)

    app = create_app(db_path=db_path)
    with TestClient(app) as connected:
        yield connected, backups


def test_no_route_in_the_engine_accepts_a_google_token(client):
    """THE ONE THAT MATTERS, and it is a property of the whole surface rather
    than of one handler — so it is asserted against the source, not by trying
    every route with a token and hoping one of them refuses.

    If this ever fails, the ruling has been reversed by an edit rather than by a
    decision, and the token is now living in a second process.
    """
    source = Path(__file__).resolve().parent.parent / "scrapex" / "webui" / "app.py"
    body = source.read_text(encoding="utf-8")

    for smell in ('"access_token"', "'access_token'", '"Authorization"',
                  "headers.get(\"authorization\")", "Bearer "):
        assert smell not in body, (
            f"{smell} appears in the web layer. The engine is not supposed to "
            "receive, hold or forward a Google token — see the owner's ruling "
            "of 2026-08-11 and extension/drive.js, which does this work in the "
            "panel where the token already lives.")


def test_a_built_bundle_is_described_by_what_was_actually_packed(client):
    connected, backups = client

    described = connected.post("/api/bundle").json()

    archives = list(backups.glob("scrapex-bundle-*.zip"))
    assert len(archives) == 1, f"expected one archive, found {archives}"
    archive = archives[0]
    assert described["name"] == archive.name
    assert described["bytes"] == archive.stat().st_size, (
        "the size reported to the panel is not the size of the file it will "
        "upload, so the pointer written to Drive would describe a different "
        "archive from the one stored")
    assert described["sha256"] == bundle.sha256_of(archive)
    assert described["bundle_format"] == bundle.BUNDLE_FORMAT
    assert described["engine_version"]
    assert described["created_at"].endswith("Z")


def test_the_staging_copy_is_not_left_on_the_owners_disk(client):
    """An expanded bundle is a second full copy of the warehouse. Leaving one
    behind per backup fills the disk of the machine the backups exist to
    protect."""
    connected, backups = client

    connected.post("/api/bundle")

    leftover = [p for p in backups.iterdir() if p.is_dir()]
    assert leftover == [], f"the staging directory was left behind: {leftover}"


def test_the_archive_downloads_whole_and_opens(client):
    connected, backups = client
    described = connected.post("/api/bundle").json()

    got = connected.get("/api/bundle/archive")

    assert got.status_code == 200
    assert got.headers["content-type"] == "application/zip"
    assert len(got.content) == described["bytes"], (
        "the panel would upload a different number of bytes than the engine "
        "reported, and the size check in drive.js would reject its own backup")
    with zipfile.ZipFile(io.BytesIO(got.content)) as opened:
        names = opened.namelist()
    assert "manifest.json" in names
    assert any(n.endswith(".db") for n in names), (
        f"the archive carries no database: {names}")


def test_asking_for_an_archive_before_one_is_built_says_which_step_is_missing(client):
    connected, _ = client

    refused = connected.get("/api/bundle/archive")

    assert refused.status_code == 404
    assert "POST /api/bundle" in refused.json()["detail"], (
        "the refusal does not name the step that was skipped")


def test_the_newest_bundle_is_the_one_served(client):
    """Two backups in one session must not hand the panel the older archive."""
    connected, backups = client
    first = connected.post("/api/bundle").json()
    # Age the first archive so the ordering is decided by mtime rather than by
    # two files that happen to share a timestamp to the second.
    import os
    older = backups / first["name"]
    os.utime(older, (1_600_000_000, 1_600_000_000))
    second = connected.post("/api/bundle").json()

    got = connected.get("/api/bundle/archive")

    assert len(got.content) == second["bytes"]
    assert got.headers["content-disposition"].endswith(f'"{second["name"]}"')


def test_the_download_path_cannot_be_chosen_by_the_caller(client):
    """The route takes no argument at all, so there is nothing to traverse with.
    Asserted rather than assumed, because the obvious next feature — "let me
    download an older one" — is exactly where a caller-supplied name gets added.
    """
    connected, _ = client
    connected.post("/api/bundle")

    for attempt in ("?name=../../../etc/passwd", "?path=C:/Windows/win.ini",
                    "?file=latest.json"):
        got = connected.get(f"/api/bundle/archive{attempt}")
        assert got.status_code == 200
        assert got.headers["content-disposition"].count("scrapex-bundle-") == 1, (
            f"the query string {attempt} changed which file was served")


def test_the_manifest_inside_names_the_format_the_panel_checks(client):
    """drive.js writes bundle_format into the Drive pointer and a restoring
    machine refuses a format it does not read. The number has to come from the
    same place at both ends."""
    connected, backups = client
    described = connected.post("/api/bundle").json()

    with zipfile.ZipFile(backups / described["name"]) as opened:
        manifest = json.loads(opened.read("manifest.json"))

    assert manifest["bundle_format"] == described["bundle_format"]
