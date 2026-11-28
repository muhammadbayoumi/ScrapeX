"""Register ScrapeX as a Chrome Native Messaging host (spec: local runtime install).

Chrome will only launch a native host it has a MANIFEST for, and the manifest
must name the exact extension ids allowed to talk to it. This module writes that
manifest and, on Windows, the registry key that points Chrome at it.

The registry write is a real change to the user's machine, so it happens only
when someone asks for it, and each asker may change only its own share (#839):

    `scrapex install-native-host`   by hand: exactly the ids and launcher given
    the double-clicked engine       registers itself, or moves the helper off
                                    another copy of itself; never off the project
                                    files (`link_installed_engine`)
    /api/native-host/register       adds one extension; writes a launcher only
                                    where none works (`link`)

Never as a side effect of importing or of any other command.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HOST_NAME = "com.scrapex.engine"

#: THE PANEL'S EXTENSION ID, AS IT SHIPS. `extension/manifest.json`'s `key` pins it,
#: so every unpacked load carries it, and the store listing must keep it or Google
#: sign-in breaks (docs/store-listing.md). The installed engine does not carry
#: `extension/`, so this is a copy, and
#: `tests/test_the_helper_links_itself.py` derives it from the key the way Chrome
#: does, as `PROTOCOL_VERSION` is held to its twin in transport.js.
PANEL_EXTENSION_ID = "ekcgggphcfdbjgfkcmjagehfjhijeang"

# Where HKCU names the manifest. Chrome looks here first, then HKLM, and HKCU wins
# (chromium/src@4b0844bf launch_context_win.cc:183-201); ScrapeX writes only HKCU.
_REGISTRY_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"

#: A source checkout is started through an interpreter, so its launcher is a SCRIPT:
#: the shim `write_launcher` writes, or one given by hand with `--executable`. The
#: installed engine is one compiled program and is its own launcher.
_SCRIPT_SUFFIXES = frozenset({".bat", ".cmd", ".sh"})

# Chrome looks for the manifest in a per-OS location.
_MANIFEST_DIRS = {
    "win32": Path.home() / "AppData/Local/ScrapeX",
    "darwin": Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts",
    "linux": Path.home() / ".config/google-chrome/NativeMessagingHosts",
}


def manifest_path(platform: str | None = None) -> Path:
    platform = platform or sys.platform
    base = _MANIFEST_DIRS.get(platform, _MANIFEST_DIRS["linux"])
    return base / f"{HOST_NAME}.json"


def write_launcher(directory: Path) -> Path:
    """A tiny shim that runs the native host through the current interpreter.

    Chrome executes `path` DIRECTLY with no arguments, so pointing it at a bare
    `python.exe` would just open a REPL on the pipe and hang forever. The shim is
    what makes a source install launchable at all.
    """
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        shim = directory / "scrapex-native-host.bat"
        shim.write_text(f'@echo off\r\n"{sys.executable}" -m scrapex.cli native-host %*\r\n',
                        encoding="utf-8")
    else:
        shim = directory / "scrapex-native-host.sh"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m scrapex.cli native-host "$@"\n',
                        encoding="utf-8")
        shim.chmod(0o755)
    return shim


#: The interpreter a shim `write_launcher` wrote names, read back by `registration`,
#: so a moved project whose shim names a Python that is gone reads as starting
#: nothing. One format in two places, held together by a test that writes a shim
#: and reads it back (tests/test_the_helper_links_itself.py).
_SHIM_INTERPRETER = re.compile(r'"([^"]+)"\s+-m\s+scrapex\.cli\s+native-host')


def resolve_launcher(executable: str | None, directory: Path) -> str:
    """An executable Chrome can actually start."""
    if executable:
        return executable
    if getattr(sys, "frozen", False):        # the PyInstaller build: run ourselves
        return sys.executable
    return str(write_launcher(directory))


def build_manifest(extension_ids: list[str], executable: str) -> dict:
    """The host manifest Chrome reads.

    `allowed_origins` is an allowlist: only these extension ids may start the
    host. An empty list would let nobody in, which is safer than a wildcard —
    Chrome does not support one here, and we would not want it if it did.
    """
    if not executable:
        raise ValueError("a launchable executable is required")
    return {
        "name": HOST_NAME,
        "description": "ScrapeX local engine",
        "path": executable,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{eid}/" for eid in extension_ids],
    }


# How many extension ids the manifest may name at once. A developer reloads an
# unpacked extension from a handful of folders over a project's life, not from
# fifty — and an allowlist that only ever grows is an allowlist nobody prunes.
MAX_ALLOWED_IDS = 5


def allowed_extension_ids(platform: str | None = None,
                          path: Path | None = None) -> list[str]:
    """The ids this manifest currently names, newest first. [] if there is none.

    Lives here, beside the file it reads, because this manifest is THE allowlist
    deciding which extension may drive this machine — the web layer asks this
    function rather than keeping a second parser of the same file in step.
    """
    target = path or manifest_path(platform)
    try:
        manifest = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ids: list[str] = []
    for origin in manifest.get("allowed_origins") or []:
        candidate = str(origin).removeprefix("chrome-extension://").rstrip("/")
        if candidate.isalnum() and candidate not in ids:
            ids.append(candidate)
    return ids


def install(extension_ids: list[str], executable: str | None = None,
            platform: str | None = None, write_registry: bool = True,
            *, replace: bool = False) -> Path:
    """Write the manifest (and on Windows the registry pointer). Returns its path.

    ADDS by default; it used to replace. Replacing meant one call could evict a
    working extension, and /api/native-host/register is reachable from ANY
    extension by design (the re-link route repairs an id the allowlist no longer
    names, so holding it to that allowlist would lock out the repair). With
    replacement, two installed extensions could take the host from each other
    turn by turn, and the owner would see a Start-engine button that worked
    every other time for no visible reason. Adding cannot do that.

    `replace=True` is the deliberate prune, for `install-native-host` run by
    hand — that caller means the list it passed, not the list plus history.
    """
    if not extension_ids:
        raise ValueError("at least one extension id is required — Chrome will not "
                         "start a native host that no extension is allowed to call")
    platform = platform or sys.platform
    target = manifest_path(platform)
    target.parent.mkdir(parents=True, exist_ok=True)
    launcher = resolve_launcher(executable, target.parent)
    # Once each, in the order given: `link` passes the asking id first and then
    # the ids already there, which may include it.
    merged = list(dict.fromkeys(extension_ids))
    if not replace:
        # Newest first, so the cap drops the oldest folder a developer has
        # long stopped loading from — never the id that just asked.
        for known in allowed_extension_ids(platform, target):
            if known not in merged:
                merged.append(known)
    merged = merged[:MAX_ALLOWED_IDS]
    target.write_text(json.dumps(build_manifest(merged, launcher), indent=2) + "\n",
                      encoding="utf-8")

    if platform == "win32" and write_registry:
        _write_windows_registry(target)
    return target


@dataclass(frozen=True)
class Registration:
    """The helper Chrome would find for HOST_NAME, read the way Chrome reads it.

    `works` is Chrome's own test, from chromium/src@4b0844bf
    `chrome/browser/extensions/api/messaging/launch_context.cc:186-245`: a manifest
    the registry names (Windows) or Chrome's folder holds (elsewhere), that loads,
    names this host, allows some extension, and whose program exists — and, for the
    shim `write_launcher` writes, whose Python exists too. In every other state nothing
    starts for anyone: Chrome answers "not found" (`absent` in extension/transport.js),
    "forbidden" to everyone when no extension is allowed, or starts a shim that exits
    at once (`crashed`). So nothing that works is ever lost by replacing it.
    """

    manifest: Path | None
    launcher: str | None              # the program Chrome would start
    extension_ids: tuple[str, ...]
    works: bool

    @property
    def starts_project_files(self) -> bool:
        return (self.launcher is not None
                and Path(self.launcher).suffix.lower() in _SCRIPT_SUFFIXES)


def registration(platform: str | None = None) -> Registration:
    platform = platform or sys.platform
    if platform == "win32":
        named = _read_windows_registry()
        manifest = Path(named) if named and Path(named).is_absolute() else None
    else:
        manifest = manifest_path(platform)
    try:
        body = json.loads(manifest.read_text(encoding="utf-8")) if manifest else None
    except (OSError, ValueError):
        body = None
    # What Chrome's loader requires before it reads `path`
    # (native_messaging_host_manifest.cc:77-118): one entry that is not a string
    # and it loads nothing at all.
    origins = body.get("allowed_origins") if isinstance(body, dict) else None
    if not isinstance(body, dict) or body.get("name") != HOST_NAME \
            or not body.get("description") or body.get("type") != "stdio" \
            or not isinstance(body.get("path"), str) or not isinstance(origins, list) \
            or not all(isinstance(origin, str) for origin in origins):
        return Registration(manifest, None, (), False)
    program = Path(body["path"])
    if not program.is_absolute() and platform == "win32":
        program = manifest.parent / program      # Chrome's rule on Windows (:224-234)
    ids = tuple(allowed_extension_ids(platform, manifest))
    works = bool(ids) and program.is_absolute() and program.is_file()
    if works and program.suffix.lower() in _SCRIPT_SUFFIXES:
        # A SHIM WHOSE PYTHON IS GONE STARTS NOTHING, though every file Chrome looks
        # for is there: Chrome starts the script and it exits at once ("Native host
        # has exited."). Measured 2026-11-28, when OneDrive moved the project folder.
        # A script this module did not write names no interpreter it can read, and is
        # believed while it exists.
        try:
            named = _SHIM_INTERPRETER.search(program.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            named = None
        works = named is None or Path(named.group(1)).is_file()
    return Registration(manifest, str(program), ids, works)


def link(extension_id: str, platform: str | None = None) -> Path:
    """Let one more extension start the engine, WITHOUT CHANGING WHICH ENGINE STARTS.

    The re-link route's write (`/api/native-host/register`). It used to call
    `install`, which re-pointed the launcher at whichever engine answered — so any
    extension the helper refused could move the owner's helper off his project files
    onto a downloaded engine, with nothing said. A working launcher is now kept, and
    this engine's own is written only where none works: the "not found" a fresh
    machine, a deleted folder or a moved download gives (#839).
    """
    found = registration(platform)
    return install([extension_id, *found.extension_ids],
                   executable=found.launcher if found.works else None, platform=platform)


def link_installed_engine(platform: str | None = None) -> tuple[str, Registration]:
    """What a double-click of the installed engine does to Chrome's helper.

    Returns what happened and the registration as it was before:

        linked    none worked, or the panel was missing from this program's own:
                  Chrome now starts this program for the panel
        moved     it started another copy of the installed engine: it starts this
                  one now, and every extension it allowed is still allowed
        kept      it starts the project files, which are never moved by this
        already   it already starts this program for the panel; nothing written

    MOVED, BECAUSE A DOWNLOAD LANDS BESIDE THE OLD FILE: Chrome uniquifies, so the
    next one is `scrapex-engine (1).exe`, which upgrades the warehouse on its way up,
    and a helper still naming the old copy would start an engine that refuses it.
    KEPT, BECAUSE THE PROJECT FILES ARE A CHOICE someone made by hand; a download
    tried out beside them is not a reason to stop starting them.

    THE INSTALLED ENGINE ONLY. From source, `sys.executable` is a bare interpreter,
    which Chrome would start as a REPL on its pipe; the project files are registered
    by `install-native-host`, which writes the shim.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("only the installed engine registers itself when it is "
                           "double-clicked; the project files use install-native-host")
    found = registration(platform)
    this_program = sys.executable                # the installed engine is its own launcher
    if found.works and found.starts_project_files:
        return "kept", found
    mine = found.works and Path(found.launcher) == Path(this_program)
    if mine and PANEL_EXTENSION_ID in found.extension_ids:
        return "already", found
    install([PANEL_EXTENSION_ID, *found.extension_ids], executable=this_program,
            platform=platform)
    return ("moved" if found.works and not mine else "linked"), found


def _read_windows_registry() -> str | None:
    """The manifest HKCU names for HOST_NAME, or None when there is no such key."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, None)
    except FileNotFoundError:
        return None
    return value if isinstance(value, str) and value else None


def _write_windows_registry(target: Path) -> None:
    """HKCU (per-user) — never HKLM: this needs no admin rights and cannot affect
    other accounts on the machine."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, str(target))


def install_instructions() -> str:
    """English, copy-pasteable — shown in the extension's setup screen."""
    return (
        "1. Install the ScrapeX engine on this machine\n"
        "2. Run:  scrapex install-native-host --extension-id <YOUR_EXTENSION_ID>\n"
        "3. Reload the extension in chrome://extensions\n"
        "4. The engine status in the side panel turns green when it connects"
    )
