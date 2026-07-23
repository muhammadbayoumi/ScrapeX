"""Start the engine with Windows itself — the terminal leaves the story.

Two halves make "no terminal, ever": the native host's START_ENGINE covers
"it died mid-session" from the panel, and THIS covers "the machine rebooted" —
a silent launcher in the per-user Startup folder runs the same command the
host spawns, hidden, appending to the same ~/.scrapex/engine.log.

A Startup-folder .vbs rather than a service or scheduled task, deliberately:
it needs no elevation, it runs as the owner with the owner's environment, and
turning it off is deleting ONE file the owner can see and read — the file
says in its own header who wrote it and how to remove it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

LAUNCHER_NAME = "ScrapeX Engine.vbs"
DEFAULT_ENGINE_PORT = 8000     # mirrors native.DEFAULT_ENGINE_PORT (import-free
                               # so the CLI path stays light)


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def launcher_path() -> Path:
    return _startup_dir() / LAUNCHER_NAME


def _command(port: int) -> str:
    """The exact engine command the native host spawns, as one cmd line.

    cmd /c carries the cd (the engine expects the repo as its working dir,
    same as native._spawn_engine) and the append-redirect into engine.log —
    a boot-time process with no log is undiagnosable the day it fails to
    come up. pythonw where it exists so nothing can flash a console; the
    VBS run-style 0 hides the cmd window itself.
    """
    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    runner = windowless if windowless.exists() else interpreter
    repo = Path(__file__).resolve().parent.parent
    log = Path.home() / ".scrapex" / "engine.log"
    return (f'cmd /c cd /d "{repo}" && "{runner}" -m scrapex.cli ui '
            f'--port {int(port)} >> "{log}" 2>&1')


def install(port: int = DEFAULT_ENGINE_PORT) -> Path:
    """Write (or rewrite) the launcher. Idempotent: one file, latest paths win —
    a moved repo or a new interpreter is fixed by installing again."""
    target = launcher_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    (Path.home() / ".scrapex").mkdir(parents=True, exist_ok=True)
    command = _command(port).replace('"', '""')     # VBS escapes quotes by doubling
    target.write_text(
        "' ScrapeX: starts the local engine silently at Windows logon.\n"
        "' Written by ScrapeX (scrapex autostart install / the panel toggle).\n"
        "' To stop starting with Windows: delete this file, or run\n"
        "' `scrapex autostart remove`, or turn the panel toggle off.\n"
        f'CreateObject("Wscript.Shell").Run "{command}", 0, False\n',
        encoding="utf-8")
    return target


def remove() -> bool:
    """Delete the launcher. True when there was one to delete."""
    target = launcher_path()
    if target.exists():
        target.unlink()
        return True
    return False


def status() -> dict:
    """{"installed": bool, "path": str} — the file's existence IS the truth."""
    target = launcher_path()
    return {"installed": target.exists(), "path": str(target)}
