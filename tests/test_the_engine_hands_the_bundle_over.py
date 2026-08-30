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

import inspect
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


def test_the_panel_pack_is_lifted_out_of_the_archive(client):
    """THE FILE THE BROWSER CAN ACTUALLY READ.

    A browser has DecompressionStream for gzip and no zip reader at all, and
    this repository ships no npm dependency on purpose. So `panel.jsonl.gz`
    inside the archive is unreachable to the one reader it was written for.

    MEASURED on the owner's warehouse, 2026-08-12: the bundle is 207.9 MB raw
    and 36.0 MB zipped, so the zip stays. The pack is 4.0 MB and already
    gzipped, so carrying it separately costs 11% more upload and removes the
    need for a zip reader entirely.
    """
    connected, backups = client

    described = connected.post("/api/bundle").json()

    assert described["panel_pack"], "no panel pack was reported"
    pack = backups / described["panel_pack"]["name"]
    assert pack.is_file(), f"the pack was reported but not written: {pack}"
    assert described["panel_pack"]["bytes"] == pack.stat().st_size
    assert described["panel_pack"]["sha256"] == bundle.sha256_of(pack)
    assert pack.name.endswith(".jsonl.gz")


def test_the_pack_is_readable_gzip_and_not_re_compressed(client):
    """Served as a gzip FILE, not as a response the browser inflates on the way
    in. Getting that wrong hands bundleview.js already-decompressed bytes that
    it then tries to decompress again."""
    import gzip

    connected, _ = client
    connected.post("/api/bundle")

    got = connected.get("/api/bundle/panel-pack")

    assert got.status_code == 200
    assert got.headers["content-type"] == "application/gzip"
    assert "content-encoding" not in {k.lower() for k in got.headers}, (
        "the pack is declared as an encoding rather than a file, so the "
        "browser would inflate it before bundleview.js ever sees it")
    # It really is gzip, and it really is JSON Lines.
    text = gzip.decompress(got.content).decode("utf-8")
    for line in [line for line in text.splitlines() if line.strip()][:5]:
        entry = json.loads(line)
        assert "dataset" in entry, f"a pack line carries no dataset key: {entry}"


def test_asking_for_a_pack_before_one_is_built_says_which_step_is_missing(client):
    connected, _ = client

    refused = connected.get("/api/bundle/panel-pack")

    assert refused.status_code == 404
    assert "POST /api/bundle" in refused.json()["detail"]


def test_the_pack_route_cannot_be_pointed_anywhere_either(client):
    connected, _ = client
    connected.post("/api/bundle")

    for attempt in ("?name=../../../etc/passwd", "?which=archive"):
        got = connected.get(f"/api/bundle/panel-pack{attempt}")
        assert got.status_code == 200
        assert got.headers["content-disposition"].endswith('.jsonl.gz"'), (
            f"the query string {attempt} changed which file was served")


# ---- the rows the panel writes into a spreadsheet ---------------------------

def test_the_export_route_hands_over_the_same_table_the_xlsx_carries(client):
    """ONE EXPRESSION OF WHAT AN EXPORT IS, not a third.

    `export_source_table` already feeds the .xlsx download and the Apps Script
    funnel. A separate query for the panel would drift from those two, which is
    the drift `fields.column_order` exists to prevent — and the drift would show
    as two spreadsheets of the same source with different columns.
    """
    from scrapex.reports import EXPORT_HEADER

    connected, _ = client
    # An empty warehouse still has to answer with the right SHAPE: the panel
    # decides whether to write a tab from `rows`, and a 500 here would read to
    # the owner as "Google refused" when Google was never asked.
    known = connected.get("/api/sources").json()["sources"]
    if not known:
        pytest.skip("no sources in the fixture warehouse")
    key = known[0]["source_key"]

    table = connected.get(f"/api/export/{key}").json()

    assert table["header"] == EXPORT_HEADER
    assert table["source_key"] == key
    assert isinstance(table["rows"], list)
    assert table["truncated"] is False


def test_a_source_that_does_not_exist_is_named_rather_than_empty(client):
    """An unknown key answering with zero rows would have the panel write an
    empty tab over a real one and report success."""
    connected, _ = client

    refused = connected.get("/api/export/NO_SUCH_SOURCE")

    assert refused.status_code == 404
    assert "NO_SUCH_SOURCE" in refused.json()["detail"]


def test_the_row_ceiling_is_the_same_number_in_all_three_places():
    """The engine's route, the function it calls, and the panel that writes the
    result each carry this limit. Two of them agreeing is not enough: the panel
    refuses at its own number BEFORE calling Google, so a lower ceiling there
    would reject rows the engine was willing to send, and a higher one would
    hand Google more than the engine ever produces.
    """
    import re

    from scrapex.reports import export_source_table
    from scrapex.webui import app as webui

    engine_default = inspect.signature(export_source_table).parameters["limit"].default
    route_limit = re.search(r"EXPORT_ROW_LIMIT = ([\d_]+)",
                            Path(webui.__file__).read_text(encoding="utf-8"))
    panel_limit = re.search(
        r"MAX_EXPORT_ROWS = ([\d_]+)",
        (Path(__file__).resolve().parent.parent / "extension" / "sheets.js")
        .read_text(encoding="utf-8"))

    assert route_limit, "EXPORT_ROW_LIMIT is gone from the web layer"
    assert panel_limit, "MAX_EXPORT_ROWS is gone from extension/sheets.js"
    assert int(route_limit.group(1).replace("_", "")) == engine_default
    assert int(panel_limit.group(1).replace("_", "")) == engine_default


# ---- one build at a time, and no rubbish left behind -------------------------
#
# ALL OF THIS IS ABOUT A ROUTE THAT ANSWERS ONLY WHEN IT IS FINISHED. On the
# owner's warehouse the build takes 104 seconds, the panel used to abort at ten
# and re-enable its button, and nothing stopped the next click from starting a
# second build over the top of the first. The deadline is fixed in
# extension/startup.js; these are the consequences that outlived it.


def _fake_backup(folder, stamp: str, *, staging: bool = False):
    """A backup that some earlier build left in the folder."""
    if staging:
        made = folder / f"scrapex-bundle-{stamp}"
        made.mkdir()
        (made / "warehouse.db").write_bytes(b"not really")
        return made
    archive = folder / f"scrapex-bundle-{stamp}.zip"
    archive.write_bytes(b"not really a zip")
    (folder / f"scrapex-bundle-{stamp}-panel.jsonl.gz").write_bytes(b"not really gzip")
    return archive


def test_a_second_build_is_refused_while_the_first_is_still_running(client, monkeypatch):
    """THE DOUBLE CLICK. Two builds share a folder, a stamp format and `_newest`,
    so the second does not merely waste 104 seconds of disk — it can leave the
    panel holding the manifest of one build and the archive of the other."""
    import threading

    import scrapex.webui.app as module

    connected, _ = client
    real = module.bundle.build
    inside, may_finish = threading.Event(), threading.Event()

    def slow_build(db_path, staging, **kw):
        inside.set()
        may_finish.wait(timeout=10)
        return real(db_path, staging, **kw)

    monkeypatch.setattr(module.bundle, "build", slow_build)

    first: dict = {}
    worker = threading.Thread(
        target=lambda: first.update(status=connected.post("/api/bundle").status_code))
    worker.start()
    try:
        assert inside.wait(timeout=10), "the first build never started"
        refused = connected.post("/api/bundle")
    finally:
        may_finish.set()
        worker.join(timeout=30)

    assert refused.status_code == 409, refused.text
    assert "already being built" in refused.json()["detail"]
    assert first["status"] == 200, "refusing the second must not disturb the first"


def test_the_lock_is_released_when_a_build_fails(client, monkeypatch):
    """A refusal that outlives its cause is worse than the collision it prevents:
    every later backup would answer 409 until the engine was restarted."""
    import scrapex.webui.app as module

    connected, _ = client

    def broken_build(*a, **kw):
        raise ValueError("nope")

    monkeypatch.setattr(module.bundle, "build", broken_build)
    assert connected.post("/api/bundle").status_code == 400

    monkeypatch.undo()
    assert connected.post("/api/bundle").status_code == 200, (
        "the lock was not released after a failed build")


def test_only_the_newest_backups_survive_a_build(client):
    """NOTHING PRUNED THESE UNTIL 2026-08-29. The archive is 372.6 MB on the
    owner's machine and every successful backup left one behind for good."""
    connected, backups = client
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        _fake_backup(backups, stamp)

    connected.post("/api/bundle")

    stamps = sorted({p.name[len("scrapex-bundle-"):][:15]
                     for p in backups.glob("scrapex-bundle-*") if p.is_file()})
    assert len(stamps) == module_keep(), stamps
    assert "20260101-000000" not in stamps, "the oldest should have gone first"
    assert "20260103-000000" in stamps, "the newest predecessor should survive"


def module_keep() -> int:
    """`BUNDLE_KEEP` is a closure inside `create_app`, so it is read from source
    rather than imported — the alternative is hard-coding 2 in this file and
    having the test disagree silently with the code the day it changes."""
    import re
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "scrapex" / "webui" / "app.py")
    found = re.search(r"^\s*BUNDLE_KEEP = (\d+)", source.read_text(encoding="utf-8"),
                      re.MULTILINE)
    assert found, "BUNDLE_KEEP is no longer in scrapex/webui/app.py"
    return int(found.group(1))


def test_both_files_of_a_backup_are_pruned_together(client):
    """The two files of one backup do NOT share an mtime — `shutil.copy2` gives
    the panel pack the timestamp of the staged file it came from, minutes before
    the archive beside it is closed. Pruning each suffix independently could keep
    an archive from one build and a pack from another, and the panel uploads the
    pair as one description of one warehouse."""
    connected, backups = client
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        _fake_backup(backups, stamp)

    connected.post("/api/bundle")

    for path in backups.glob("scrapex-bundle-*.zip"):
        stamp = path.name[len("scrapex-bundle-"):][:15]
        assert (backups / f"scrapex-bundle-{stamp}-panel.jsonl.gz").is_file(), (
            f"{path.name} survived without its panel pack")


def test_a_staging_tree_left_by_a_killed_engine_is_swept(client):
    """WHAT ACTUALLY SURVIVES A CRASH. The build itself cannot — it is a thread
    inside the engine — but the staging directory it was writing does, because
    the `rmtree` that removes it runs in a `finally` the process never reached.
    That tree is the bundle expanded: 1.5 GB on the owner's machine."""
    import os
    import time

    connected, backups = client
    orphan = _fake_backup(backups, "20260101-000000", staging=True)
    old = time.time() - (7 * 3600)
    os.utime(orphan, (old, old))

    connected.post("/api/bundle")

    assert not orphan.exists(), "the orphaned staging tree was left on disk"


def test_a_staging_tree_that_may_still_be_in_use_is_left_alone(client):
    """The age guard. `start_engine` refuses to spawn a second engine on a held
    port (scrapex/native.py), so within one port there is never a second builder
    — but an engine started by hand elsewhere would share this folder, and
    deleting a live foreign build is a worse failure than the leak it fixes."""
    connected, backups = client
    fresh = _fake_backup(backups, "20260101-000000", staging=True)

    connected.post("/api/bundle")

    assert fresh.is_dir(), "a staging tree young enough to be live was deleted"


def test_a_failed_build_does_not_take_the_last_good_archive_with_it(client, monkeypatch):
    """Pruning runs only after a build that verified and packed. A build that
    dies must not be able to delete the backup the owner still has."""
    import scrapex.webui.app as module

    connected, backups = client
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        _fake_backup(backups, stamp)

    monkeypatch.setattr(module.bundle, "build",
                        lambda *a, **kw: (_ for _ in ()).throw(ValueError("nope")))
    assert connected.post("/api/bundle").status_code == 400

    survived = {p.name[len("scrapex-bundle-"):][:15]
                for p in backups.glob("scrapex-bundle-*.zip")}
    assert survived == {"20260101-000000", "20260102-000000", "20260103-000000"}


# ---- an archive is only servable when it is whole (OP-111) --------------------
#
# On 2026-08-30 a 0-byte archive reached the owner's Drive under a pointer
# saying a backup existed. Two builds overlapped; the second had CREATED its zip
# and not yet filled it; and this route answers with the newest `.zip` on disk.
# `zipfile.ZipFile(path, "w")` makes that window thirty seconds wide on his
# warehouse. The archive is now written beside its real name and renamed into
# place, so the name either does not exist or names a complete file.


def test_a_finished_build_leaves_no_half_written_file_behind(client):
    connected, backups = client

    connected.post("/api/bundle")

    leftovers = [p.name for p in backups.glob("*.part")]
    assert not leftovers, f"the build left a partial file behind: {leftovers}"


def test_an_archive_still_being_written_is_never_served(client):
    """THE INCIDENT, as a test. The partial file is deliberately the NEWEST
    thing in the folder, because mtime is exactly what the route sorts on."""
    import os
    import time

    connected, backups = client
    connected.post("/api/bundle")
    whole = next(iter(backups.glob("scrapex-bundle-*.zip")))

    partial = backups / "scrapex-bundle-29991231-235959.zip.part"
    partial.write_bytes(b"")
    later = time.time() + 60
    os.utime(partial, (later, later))

    got = connected.get("/api/bundle/archive")

    assert got.status_code == 200, got.text
    assert len(got.content) == whole.stat().st_size, (
        "the route served something other than the complete archive")
    assert len(got.content) > 0, "the route served an empty archive"


def test_a_panel_pack_still_being_copied_is_never_served(client):
    """Four megabytes copy fast, and `shutil.copy2` is still not atomic."""
    import os
    import time

    connected, backups = client
    connected.post("/api/bundle")
    whole = next(iter(backups.glob("scrapex-bundle-*-panel.jsonl.gz")))

    partial = backups / "scrapex-bundle-29991231-235959-panel.jsonl.gz.part"
    partial.write_bytes(b"")
    later = time.time() + 60
    os.utime(partial, (later, later))

    got = connected.get("/api/bundle/panel-pack")

    assert got.status_code == 200, got.text
    assert len(got.content) == whole.stat().st_size
    assert len(got.content) > 0


def test_a_partial_file_left_by_a_crash_is_pruned_with_its_stamp(client):
    """It carries a stamp like any other file of that backup, so retention
    reaches it. A crash that leaves 372 MB behind is the leak this closes."""
    connected, backups = client
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        _fake_backup(backups, stamp)
    orphan = backups / "scrapex-bundle-20260101-000000.zip.part"
    orphan.write_bytes(b"half a zip")

    connected.post("/api/bundle")

    assert not orphan.exists(), "the partial file outlived its own stamp"


def test_a_pack_that_dies_leaves_nothing_that_looks_like_a_backup(tmp_path, monkeypatch):
    """A raise mid-zip must not leave a file the next reader could serve."""
    from scrapex import bundle as bundlemod

    source = tmp_path / "src"
    source.mkdir()
    (source / "warehouse.db").write_bytes(b"x" * 32)

    # A bundle that verifies, so `pack` gets past its own refusal and reaches
    # the zip -- which is where the failure is injected.
    monkeypatch.setattr(
        bundlemod, "verify",
        lambda root: bundlemod.BundleReport(root=Path(root), files=1, bytes=32))

    real_zipfile = bundlemod.zipfile.ZipFile

    class DiesMidWrite:
        def __init__(self, path, *a, **kw):
            self._inner = real_zipfile(path, *a, **kw)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def write(self, *a, **kw):
            raise OSError("the disk filled up")

        def __exit__(self, *exc):
            return self._inner.__exit__(*exc)

    monkeypatch.setattr(bundlemod.zipfile, "ZipFile", DiesMidWrite)

    archive = tmp_path / "scrapex-bundle-20260101-000000.zip"
    with pytest.raises(OSError):
        bundlemod.pack(source, archive)

    assert not archive.exists(), "a failed pack published an archive"
    assert not list(tmp_path.glob("*.part")), "a failed pack left a partial file"


def test_the_final_name_appears_only_when_the_archive_is_complete(tmp_path, monkeypatch):
    """THE DECISIVE ONE. The tests above prove a `.part` is not served; this
    proves the archive is written as one, which is what makes that true.

    Asserted from INSIDE the zip write, because that is the only moment the old
    code was wrong: `zipfile.ZipFile(archive, "w")` created the real name up
    front and left it empty for the length of the deflate.
    """
    from scrapex import bundle as bundlemod

    source = tmp_path / "src"
    source.mkdir()
    (source / "warehouse.db").write_bytes(b"x" * 4096)
    monkeypatch.setattr(
        bundlemod, "verify",
        lambda root: bundlemod.BundleReport(root=Path(root), files=1, bytes=4096))

    archive = tmp_path / "scrapex-bundle-20260101-000000.zip"
    real_zipfile = bundlemod.zipfile.ZipFile
    seen = []

    class Watching:
        def __init__(self, path, *a, **kw):
            seen.append(("opened", archive.exists()))
            self._inner = real_zipfile(path, *a, **kw)

        def __enter__(self):
            self._inner.__enter__()
            return self

        def write(self, *a, **kw):
            seen.append(("writing", archive.exists()))
            return self._inner.write(*a, **kw)

        def __exit__(self, *exc):
            return self._inner.__exit__(*exc)

    monkeypatch.setattr(bundlemod.zipfile, "ZipFile", Watching)
    bundlemod.pack(source, archive)

    assert seen, "the zip was never opened; this test proved nothing"
    for moment, existed in seen:
        assert not existed, (
            f"the archive existed under its final name while {moment} — that is "
            "the window a concurrent reader served 0 bytes out of")
    assert archive.exists() and archive.stat().st_size > 0
