"""Register ScrapeX as a Chrome Native Messaging host (spec: local runtime install).

Chrome will only launch a native host it has a MANIFEST for, and the manifest
must name the exact extension ids allowed to talk to it. This module writes that
manifest and, on Windows, the registry key that points Chrome at it.

The registry write is a real change to the user's machine, so it happens ONLY
when the owner runs `scrapex install-native-host` — never as a side effect of
importing or of any other command.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HOST_NAME = "com.scrapex.engine"

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


def install(extension_ids: list[str], executable: str | None = None,
            platform: str | None = None, write_registry: bool = True) -> Path:
    """Write the manifest (and on Windows the registry pointer). Returns its path."""
    if not extension_ids:
        raise ValueError("at least one extension id is required — Chrome will not "
                         "start a native host that no extension is allowed to call")
    platform = platform or sys.platform
    target = manifest_path(platform)
    target.parent.mkdir(parents=True, exist_ok=True)
    launcher = resolve_launcher(executable, target.parent)
    target.write_text(json.dumps(build_manifest(extension_ids, launcher), indent=2) + "\n",
                      encoding="utf-8")

    if platform == "win32" and write_registry:
        _write_windows_registry(target)
    return target


def _write_windows_registry(target: Path) -> None:
    """HKCU (per-user) — never HKLM: this needs no admin rights and cannot affect
    other accounts on the machine."""
    import winreg

    key_path = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, str(target))


def install_instructions() -> str:
    """English, copy-pasteable — shown in the extension's setup screen."""
    return (
        "1. Install the ScrapeX engine on this machine\n"
        "2. Run:  scrapex install-native-host --extension-id <YOUR_EXTENSION_ID>\n"
        "3. Reload the extension in chrome://extensions\n"
        "4. The engine status in the side panel turns green when it connects"
    )
