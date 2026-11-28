"""Chrome's helper is registered by the engine the person runs, and never taken from the project files (#839).

A FRESH MACHINE NEVER HAD A HELPER. `packaging/engine_entry.py` said the double-clicked
engine "cannot know the id" of the panel, so nothing registered `com.scrapex.engine`, and
Start engine and Start with Windows stayed dead on every new install. The id IS knowable:
`extension/manifest.json`'s `key` pins it, so the first run can register it.

WHAT IT MUST NEVER DO is move a working registration away from the project files. On the
owner's machine the helper starts his source checkout through the `.bat` shim, and a
double-click of the downloaded engine must leave that alone. Between two copies of the
installed engine it is the other way round: a download lands beside the old file as
`scrapex-engine (1).exe`, the new copy upgrades the warehouse, and a helper still naming
the old copy would start an engine that refuses it ("Needs a newer ScrapeX").

THE RE-LINK ROUTE ADDS AN ID AND NOTHING ELSE. Any extension may reach
`/api/native-host/register` by design; it used to re-point the launcher at whichever
engine answered, so one press could move the owner's helper off his project files. It now
writes a launcher only where none works, which is the case Chrome reports as "not found".

WHAT CHROME CALLS "NOT FOUND", read from its source at
chromium/src@4b0844bf `chrome/browser/extensions/api/messaging/launch_context.cc:186-245`
and `launch_context_win.cc:183-211`: no registry key under HKCU (then HKLM), a manifest
that does not load or names another host, or a manifest whose program does not exist.
A manifest that does not list the caller is "forbidden" instead, and is checked before the
program is looked for. `nativehost.registration` reads it the same way.

No test here touches the real registry or the real manifest folder: the folder is a
`tmp_path`, and the registry is a dict.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from scrapex import nativehost
from scrapex.nativehost import HOST_NAME, PANEL_EXTENSION_ID

# Reads extension/manifest.json, so a change there must run it (the extension gate).
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
OTHER_ID = "b" * 32
THIRD_ID = "c" * 32


class FakeRegistry:
    """HKCU's `NativeMessagingHosts\\com.scrapex.engine` default value, in memory."""

    def __init__(self) -> None:
        self.value: str | None = None
        self.writes: list[str] = []

    def read(self) -> str | None:
        return self.value

    def write(self, target: Path) -> None:
        self.value = str(target)
        self.writes.append(str(target))


@pytest.fixture()
def machine(tmp_path, monkeypatch):
    """A Windows machine whose manifest folder and registry are the test's own."""
    folder = tmp_path / "AppData-Local-ScrapeX"
    monkeypatch.setattr(nativehost, "_MANIFEST_DIRS",
                        {"win32": folder, "linux": folder, "darwin": folder})
    registry = FakeRegistry()
    monkeypatch.setattr(nativehost, "_read_windows_registry", registry.read)
    monkeypatch.setattr(nativehost, "_write_windows_registry", registry.write)
    return folder, registry


def _as_frozen(monkeypatch, tmp_path, name="scrapex-engine.exe") -> Path:
    """This process becomes a double-clicked copy of the installed engine."""
    exe = tmp_path / "Downloads" / name
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    return exe


def _register(folder: Path, registry: FakeRegistry, launcher: Path | str,
              ids: list[str]) -> Path:
    """A registration as `install-native-host` leaves one, written by hand."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / f"{HOST_NAME}.json"
    manifest.write_text(json.dumps(nativehost.build_manifest(ids, str(launcher)), indent=2),
                        encoding="utf-8")
    registry.value = str(manifest)
    return manifest


def _project_shim(folder: Path, python: str) -> Path:
    """The `.bat` `write_launcher` writes for a source checkout, naming its venv."""
    folder.mkdir(parents=True, exist_ok=True)
    shim = folder / "scrapex-native-host.bat"
    shim.write_text(f'@echo off\r\n"{python}" -m scrapex.cli native-host %*\r\n',
                    encoding="utf-8")
    return shim


def _manifest(folder: Path) -> dict:
    return json.loads((folder / f"{HOST_NAME}.json").read_text(encoding="utf-8"))


def _ids(body: dict) -> list[str]:
    return [o.removeprefix("chrome-extension://").rstrip("/") for o in body["allowed_origins"]]


# ---- the id the engine registers is the one the extension carries -----------------------

def test_the_panel_id_the_engine_registers_is_the_one_the_manifest_key_pins():
    """A COPY, HELD TO ITS SOURCE. The engine cannot read `extension/` at run time — the
    installed build does not carry it — so the id is written in `nativehost.py`, and this
    derives it from the key the way Chrome does: the first 32 hex digits of SHA-256 over
    the key's bytes, each digit mapped onto a-p."""
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    derived = "".join(chr(ord("a") + int(digit, 16)) for digit in digest)
    assert PANEL_EXTENSION_ID == derived, (
        "the engine would register an id no build of the panel has, and Chrome would "
        "refuse the panel as 'forbidden' on every machine it set up")


# ---- reading the registration the way Chrome reads it -----------------------------------

def test_nothing_registered_reads_as_a_helper_that_does_not_work(machine):
    found = nativehost.registration("win32")
    assert found.works is False
    assert found.manifest is None and found.launcher is None


def test_a_registry_key_whose_manifest_is_gone_does_not_work(machine, tmp_path):
    """The owner's machine on 2026-09-24: the folder was gone and the key with it. With
    the key alone left behind, Chrome finds the key and fails to load the file."""
    _, registry = machine
    registry.value = str(tmp_path / "nowhere" / f"{HOST_NAME}.json")
    assert nativehost.registration("win32").works is False


def test_a_manifest_on_disk_with_no_registry_key_does_not_work(machine, tmp_path):
    """Chrome on Windows looks only where the registry points, so a manifest nobody
    points at is a helper Chrome cannot find."""
    folder, registry = machine
    _register(folder, registry, _as_frozen_path(tmp_path), [PANEL_EXTENSION_ID])
    registry.value = None
    assert nativehost.registration("win32").works is False


def _as_frozen_path(tmp_path: Path) -> Path:
    exe = tmp_path / "Program" / "scrapex-engine.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    return exe


@pytest.mark.parametrize("defect, works", [
    (None, True),
    ("unparseable", False),
    ("another-host", False),
    ("no-description", False),
    ("no-type", False),
    ("no-path", False),
    ("no-extension", False),
    ("origins-not-a-list", False),
    ("an-origin-not-a-string", False),
])
def test_a_manifest_chrome_cannot_load_does_not_work(machine, tmp_path, defect, works):
    """Each case is a manifest that works but for ONE field Chrome's loader requires
    (native_messaging_host_manifest.cc:77-112), so each check is tested on its own."""
    folder, registry = machine
    folder.mkdir(parents=True, exist_ok=True)
    body = nativehost.build_manifest([PANEL_EXTENSION_ID], str(_as_frozen_path(tmp_path)))
    if defect == "another-host":
        body["name"] = "com.someone.else"
    elif defect == "no-description":
        body["description"] = ""
    elif defect == "no-type":
        del body["type"]
    elif defect == "no-path":
        del body["path"]
    elif defect == "no-extension":
        body["allowed_origins"] = []
    elif defect == "origins-not-a-list":
        body["allowed_origins"] = f"chrome-extension://{PANEL_EXTENSION_ID}/"
    elif defect == "an-origin-not-a-string":
        body["allowed_origins"].append(7)
    manifest = folder / f"{HOST_NAME}.json"
    manifest.write_text("{ not json" if defect == "unparseable" else json.dumps(body),
                        encoding="utf-8")
    registry.value = str(manifest)
    assert nativehost.registration("win32").works is works


def test_a_manifest_whose_program_is_gone_does_not_work(machine, tmp_path):
    """The case Chrome checks LAST and reports as 'not found': the downloaded engine was
    moved or deleted, and the registration still names it."""
    folder, registry = machine
    gone = tmp_path / "Downloads" / "scrapex-engine.exe"
    _register(folder, registry, gone, [PANEL_EXTENSION_ID])
    found = nativehost.registration("win32")
    assert found.works is False
    assert found.launcher == str(gone)
    assert found.extension_ids == (PANEL_EXTENSION_ID,)


def test_a_relative_program_is_found_beside_the_manifest_on_windows(machine):
    """Chrome resolves a relative `path` against the manifest's folder on Windows
    (`launch_context.cc:224-234`), so a relative shim that exists there works."""
    folder, registry = machine
    shim = _project_shim(folder, r"C:\project\.venv\Scripts\python.exe")
    _register(folder, registry, shim.name, [PANEL_EXTENSION_ID])
    assert nativehost.registration("win32").works is True


def test_a_registration_chrome_can_start_works_and_says_what_it_starts(machine, tmp_path):
    folder, registry = machine
    exe = _as_frozen_path(tmp_path)
    _register(folder, registry, exe, [OTHER_ID, PANEL_EXTENSION_ID])
    found = nativehost.registration("win32")
    assert found.works is True
    assert found.launcher == str(exe)
    assert found.extension_ids == (OTHER_ID, PANEL_EXTENSION_ID)
    assert found.starts_project_files is False


@pytest.mark.parametrize("launcher, project_files", [
    ("scrapex-native-host.bat", True),
    ("run-my-checkout.cmd", True),
    ("scrapex-native-host.sh", True),
    ("scrapex-engine.exe", False),
    ("scrapex-engine (1).exe", False),
    ("scrapex-engine", False),
])
def test_a_script_launcher_is_the_project_files_and_a_program_is_an_installed_engine(
        machine, launcher, project_files):
    """A source checkout is started through an interpreter, so its launcher is a script:
    the shim `write_launcher` writes, or one given by hand with `--executable`. The
    installed engine is one compiled program and is its own launcher."""
    folder, registry = machine
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / launcher
    program.write_bytes(b"x")
    _register(folder, registry, program, [PANEL_EXTENSION_ID])
    assert nativehost.registration("win32").starts_project_files is project_files


def test_other_platforms_read_the_manifest_from_chromes_folder(machine, tmp_path):
    folder, registry = machine
    exe = _as_frozen_path(tmp_path)
    _register(folder, registry, exe, [PANEL_EXTENSION_ID])
    registry.value = None   # no registry outside Windows
    assert nativehost.registration("linux").works is True


# ---- the double-clicked engine ----------------------------------------------------------

def test_a_first_run_with_nothing_registered_registers_itself_for_the_panel(
        machine, tmp_path, monkeypatch):
    """THE FRESH MACHINE. Before this, nothing ever registered the helper, and Start
    engine and Start with Windows answered 'not found' for good."""
    folder, registry = machine
    exe = _as_frozen(monkeypatch, tmp_path)

    outcome, before = nativehost.link_installed_engine("win32")

    assert outcome == "linked"
    assert before.works is False
    body = _manifest(folder)
    assert body["path"] == str(exe)
    assert _ids(body) == [PANEL_EXTENSION_ID]
    assert registry.writes == [str(folder / f"{HOST_NAME}.json")]
    assert nativehost.registration("win32").works is True


def test_a_first_run_never_touches_a_helper_that_starts_the_project_files(
        machine, tmp_path, monkeypatch):
    """THE OWNER'S MACHINE. His helper starts his source checkout; downloading the
    engine to try a release must not move it, or Start engine would quietly launch an
    older build against a warehouse the project files have upgraded."""
    folder, registry = machine
    shim = _project_shim(folder, r"C:\project\.venv\Scripts\python.exe")
    manifest = _register(folder, registry, shim, [OTHER_ID])
    manifest_bytes = manifest.read_bytes()
    shim_bytes = shim.read_bytes()
    _as_frozen(monkeypatch, tmp_path)

    outcome, before = nativehost.link_installed_engine("win32")

    assert outcome == "kept"
    assert before.launcher == str(shim)
    assert manifest.read_bytes() == manifest_bytes, "the project files' helper was rewritten"
    assert shim.read_bytes() == shim_bytes, "the project files' launcher was rewritten"
    assert registry.writes == [], "the registry was written over the project files' helper"


def test_a_first_run_moves_the_helper_from_another_copy_of_the_installed_engine(
        machine, tmp_path, monkeypatch):
    """A NEW DOWNLOAD LANDS BESIDE THE OLD ONE as `scrapex-engine (1).exe` (Chrome's
    default is to uniquify, and `startInstallerDownload` passes no conflictAction). The
    copy run last is the one Chrome starts; the extensions already linked stay linked."""
    folder, registry = machine
    old = _as_frozen(monkeypatch, tmp_path, "scrapex-engine.exe")
    _register(folder, registry, old, [OTHER_ID])
    new = _as_frozen(monkeypatch, tmp_path, "scrapex-engine (1).exe")

    outcome, before = nativehost.link_installed_engine("win32")

    assert outcome == "moved"
    assert before.launcher == str(old)
    body = _manifest(folder)
    assert body["path"] == str(new)
    assert _ids(body) == [PANEL_EXTENSION_ID, OTHER_ID]


def test_a_first_run_repairs_a_helper_whose_program_is_gone(machine, tmp_path, monkeypatch):
    folder, registry = machine
    _register(folder, registry, tmp_path / "Deleted" / "scrapex-engine.exe",
              [OTHER_ID, PANEL_EXTENSION_ID])
    exe = _as_frozen(monkeypatch, tmp_path)

    outcome, _ = nativehost.link_installed_engine("win32")

    assert outcome == "linked"
    body = _manifest(folder)
    assert body["path"] == str(exe)
    assert _ids(body) == [PANEL_EXTENSION_ID, OTHER_ID]


def test_a_first_run_repairs_a_shim_whose_file_is_gone(machine, tmp_path, monkeypatch):
    """A project-files registration whose `.bat` was deleted starts nothing at all, so
    it is not the project files' to keep: the engine being run takes it."""
    folder, registry = machine
    _register(folder, registry, folder / "scrapex-native-host.bat", [PANEL_EXTENSION_ID])
    exe = _as_frozen(monkeypatch, tmp_path)

    outcome, _ = nativehost.link_installed_engine("win32")

    assert outcome == "linked"
    assert _manifest(folder)["path"] == str(exe)


def test_a_first_run_that_finds_itself_already_registered_writes_nothing(
        machine, tmp_path, monkeypatch):
    folder, registry = machine
    exe = _as_frozen(monkeypatch, tmp_path)
    manifest = _register(folder, registry, exe, [PANEL_EXTENSION_ID, OTHER_ID])
    written = manifest.read_bytes()

    outcome, _ = nativehost.link_installed_engine("win32")

    assert outcome == "already"
    assert manifest.read_bytes() == written
    assert registry.writes == []


def test_a_double_click_from_source_registers_nothing(machine, monkeypatch):
    """From source `sys.executable` is a bare interpreter, which Chrome would start as
    a REPL on its pipe and wait on forever: no manifest, no registry key."""
    folder, registry = machine
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    with pytest.raises(RuntimeError, match="install-native-host"):
        nativehost.link_installed_engine("win32")

    assert not (folder / f"{HOST_NAME}.json").exists()
    assert registry.writes == []


def test_a_first_run_adds_the_panel_to_its_own_registration_when_it_is_missing(
        machine, tmp_path, monkeypatch):
    """Registered by hand for another id only: the program is right, the panel is not
    allowed. It is added, and the id that was there stays."""
    folder, registry = machine
    exe = _as_frozen(monkeypatch, tmp_path)
    _register(folder, registry, exe, [OTHER_ID])

    outcome, _ = nativehost.link_installed_engine("win32")

    assert outcome == "linked"
    assert _ids(_manifest(folder)) == [PANEL_EXTENSION_ID, OTHER_ID]


# ---- the re-link route: one more extension, never another engine ------------------------

def test_relinking_keeps_the_project_files_launcher_when_the_engine_is_installed(
        machine, tmp_path, monkeypatch):
    """THE SILENT SWITCH THIS CLOSES. The route re-pointed the launcher at whichever
    engine answered, so a panel that was refused while the downloaded engine ran moved
    the owner's helper off his project files, with nothing said."""
    folder, registry = machine
    shim = _project_shim(folder, r"C:\project\.venv\Scripts\python.exe")
    _register(folder, registry, shim, [OTHER_ID])
    shim_bytes = shim.read_bytes()
    _as_frozen(monkeypatch, tmp_path)

    nativehost.link(THIRD_ID, "win32")

    body = _manifest(folder)
    assert body["path"] == str(shim), "the re-link moved the helper to another engine"
    assert shim.read_bytes() == shim_bytes
    assert _ids(body) == [THIRD_ID, OTHER_ID]


def test_relinking_from_another_checkout_does_not_rewrite_the_shim(machine, monkeypatch):
    """A source engine's launcher is a `.bat` naming ITS interpreter, and `install`
    rewrites that file for whoever calls it. The re-link only adds an id."""
    folder, registry = machine
    shim = _project_shim(folder, r"C:\project\.venv\Scripts\python.exe")
    _register(folder, registry, shim, [OTHER_ID])
    shim_bytes = shim.read_bytes()
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\elsewhere\.venv\Scripts\python.exe")

    nativehost.link(THIRD_ID, "win32")

    assert shim.read_bytes() == shim_bytes, "the re-link re-pointed the project files' shim"


def test_relinking_with_nothing_registered_registers_the_engine_that_answered(
        machine, tmp_path, monkeypatch):
    """THE CASE #839 IS ABOUT: Chrome says 'not found' while an engine answers over HTTP.
    There is no launcher to keep, so the engine that answered becomes it."""
    folder, registry = machine
    exe = _as_frozen(monkeypatch, tmp_path)

    written = nativehost.link(PANEL_EXTENSION_ID, "win32")

    assert written == folder / f"{HOST_NAME}.json"
    body = _manifest(folder)
    assert body["path"] == str(exe)
    assert _ids(body) == [PANEL_EXTENSION_ID]
    assert registry.writes == [str(written)]


def test_relinking_a_helper_whose_program_is_gone_points_it_at_the_engine_that_answered(
        machine, tmp_path, monkeypatch):
    folder, registry = machine
    _register(folder, registry, tmp_path / "Deleted" / "scrapex-engine.exe", [OTHER_ID])
    exe = _as_frozen(monkeypatch, tmp_path)

    nativehost.link(PANEL_EXTENSION_ID, "win32")

    body = _manifest(folder)
    assert body["path"] == str(exe)
    assert _ids(body) == [PANEL_EXTENSION_ID, OTHER_ID]


def test_relinking_writes_the_registry_key_a_working_manifest_was_missing(
        machine, tmp_path, monkeypatch):
    """A manifest nobody points at is invisible to Chrome; the re-link points at it."""
    folder, registry = machine
    exe = _as_frozen_path(tmp_path)
    _register(folder, registry, exe, [OTHER_ID])
    registry.value = None
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    nativehost.link(PANEL_EXTENSION_ID, "win32")

    assert nativehost.registration("win32").works is True


def test_the_route_keeps_the_launcher_a_working_registration_starts(
        machine, tmp_path, monkeypatch):
    """The same, through the route the panel calls, from an extension the helper does
    not list yet: Origin is any extension by design (`RefuseForeignOrigins`). It runs
    on this machine's own platform, Windows through the fake registry."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex import db as dbmod
    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    warehouse = tmp_path / "warehouse.db"
    conn = dbmod.connect(warehouse)
    dbmod.migrate(conn)
    conn.close()
    sources = tmp_path / "sources.yaml"
    sources.write_bytes(Path(MANIFEST_FILE).read_bytes())

    folder, registry = machine
    shim = _project_shim(folder, r"C:\project\.venv\Scripts\python.exe")
    _register(folder, registry, shim, [OTHER_ID])
    _as_frozen(monkeypatch, tmp_path)
    client = TestClient(create_app(warehouse, manifest_path=sources))

    reply = client.post("/api/native-host/register", json={"extension_id": THIRD_ID},
                        headers={"Origin": f"chrome-extension://{THIRD_ID}"})

    assert reply.status_code == 200, reply.text
    assert reply.json()["allowed_extension_ids"] == [THIRD_ID, OTHER_ID]
    assert _manifest(folder)["path"] == str(shim)


# ---- the double-click, step by step ------------------------------------------------------

class _Registry:
    """`DatabaseRegistry.defaults()` with a report the test chooses."""

    def __init__(self, path: Path, statuses: list[tuple[bool, str]]) -> None:
        self.engine = type("Engine", (), {"path": path})()
        self._statuses = statuses

    def ensure_ready(self):
        databases = {f"db{i}": {"ok": ok, "status": status}
                     for i, (ok, status) in enumerate(self._statuses)}
        return {"ok": all(ok for ok, _ in self._statuses), "created": [],
                "databases": databases}


def _entry_module():
    entry = ROOT / "packaging" / "engine_entry.py"
    spec = importlib.util.spec_from_file_location("scrapex_engine_entry_link", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def double_click(monkeypatch, tmp_path):
    """`_set_up_then_serve` with the database, the helper and the server recorded."""
    from scrapex import cli as scrapex_cli
    from scrapex.databases import registry as registry_module

    module = _entry_module()
    said: list[str] = []
    seen: list[str] = []
    monkeypatch.setattr(module, "_say", lambda line="": said.append(line))
    monkeypatch.setattr(scrapex_cli, "main", lambda: seen.append("serve") or 0)

    def arrange(statuses, link=None):
        monkeypatch.setattr(registry_module.DatabaseRegistry, "defaults",
                            classmethod(lambda cls: _Registry(tmp_path / "w.db", statuses)))

        def linked(platform=None):
            seen.append("link")
            if isinstance(link, Exception):
                raise link
            return link or ("linked", None)
        monkeypatch.setattr(nativehost, "link_installed_engine", linked)
        code = module._set_up_then_serve()
        return code, said, seen
    return arrange


def test_the_double_click_links_the_helper_after_the_database_and_before_serving(double_click):
    code, said, seen = double_click([(True, "Healthy")])
    assert code == 0
    assert seen == ["link", "serve"]
    text = "\n".join(said)
    assert text.index("Preparing your database") < text.index("Linking Chrome") \
        < text.index("Starting the engine")


def test_a_database_that_is_only_behind_still_lets_the_engine_take_the_helper(double_click):
    """`scrapex ui` upgrades a database that is only behind (`cli._cmd_ui`), so this
    engine is about to serve it."""
    from scrapex.dbupgrade import BEHIND

    _, _, seen = double_click([(False, BEHIND)])
    assert seen == ["link", "serve"]


def test_an_engine_that_cannot_open_the_warehouse_does_not_take_the_helper(double_click):
    """AN OLDER COPY RUN AFTER A NEWER ONE. It cannot serve the upgraded warehouse, and a
    helper moved to it would make Start engine fail for the copy that can."""
    _, said, seen = double_click([(False, "Needs a newer ScrapeX")])
    assert seen == ["serve"], "an engine that cannot open the warehouse took the helper"
    assert any("Needs a newer ScrapeX" in line for line in said)


def test_a_helper_that_cannot_be_written_does_not_stop_the_engine(double_click):
    """The data path is plain HTTP and needs no helper: a refused registry write is said,
    and the engine still starts."""
    code, said, seen = double_click([(True, "Healthy")],
                                    link=PermissionError("Access is denied"))
    assert code == 0
    assert seen == ["link", "serve"]
    assert any("Access is denied" in line for line in said)


@pytest.mark.parametrize("outcome, link, db, says", [
    ("linked", ("linked", None), (True, "Healthy"), True),
    ("moved", ("moved", None), (True, "Healthy"), True),
    ("already", ("already", None), (True, "Healthy"), True),
    ("kept", ("kept", None), (True, "Healthy"), False),
    ("skipped", ("linked", None), (False, "Needs a newer ScrapeX"), False),
    ("could not", PermissionError("Access is denied"), (True, "Healthy"), False),
])
def test_the_window_says_start_engine_brings_it_back_only_when_chrome_starts_this_copy(
        double_click, tmp_path, outcome, link, db, says):
    """After "kept" Chrome starts the PROJECT FILES, and after a refusal it starts
    nothing: telling him the panel brings THIS engine back would be false in both."""
    if isinstance(link, tuple):
        link = (link[0], nativehost.Registration(tmp_path / "m.json", str(tmp_path / "x"),
                                                 (PANEL_EXTENSION_ID,), True))
    _, said, _ = double_click([db], link=link)
    promised = any("Start engine in the ScrapeX panel starts it again" in line
                   for line in said)
    assert promised is says, f"after {outcome!r} the window promised a restart: {promised}"


def test_the_window_names_the_check_again_control_the_panel_draws(double_click):
    """THE CONTROL AS IT NAMES ITSELF, read off the markup so the two cannot drift: the
    window said 'Check ScrapeX-Engine again', which no control in the panel is called."""
    import re

    _, said, _ = double_click([(True, "Healthy")])
    markup = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")
    label = re.search(r'<button id="setup-recheck"[^>]*>([^<]+)</button>', markup).group(1)
    assert any(f'press "{label.strip()}"' in line for line in said), (
        f"the window tells him to press something Run's card does not call {label!r}")


@pytest.mark.parametrize("outcome", ["linked", "moved", "kept", "already"])
def test_every_outcome_of_the_link_is_said(double_click, tmp_path, outcome):
    before = nativehost.Registration(tmp_path / "m.json", str(tmp_path / "old.bat"),
                                     (PANEL_EXTENSION_ID,), True)
    _, said, _ = double_click([(True, "Healthy")], link=(outcome, before))
    step = "\n".join(said)
    step = step[step.index("Linking Chrome"):step.index("Starting the engine")]
    assert step.strip().count("\n") >= 1, f"the {outcome!r} outcome printed no result line"
    if outcome in ("moved", "kept"):
        assert str(tmp_path / "old.bat") in step, (
            f"the {outcome!r} line does not name the program Chrome started before")
