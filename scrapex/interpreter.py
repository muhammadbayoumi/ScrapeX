"""Which Python this engine runs on, judged against the Python ScrapeX is pinned to (#1321).

His engine runs from source, started by the native-host launcher, and the launcher names
its interpreter once, when it is registered: `nativehost.write_launcher` writes
`sys.executable` into it. A pin move moves CI and the release build and never that
launcher, so after one his engine runs below `requires-python`. pip enforces that floor
only at install time, so the engine keeps starting, and until this module nothing said so.

THE FLOOR IS READ FROM `.python-version`, NOT FROM `requires-python`. They are one fact:
`.python-version` names it, and `pyproject.toml` carries a copy only because pip cannot
read the file (`tests/test_one_python_version.py` holds the copy to it). The engine can
read the file, so it reads the source and not the copy. The release build bundles it
(`RUNTIME_DATA` in `packaging/build_engine.py`), so an installed engine reads the pin it
was built from.

READ WHEN ASKED, NOT AT IMPORT. A pin move pulled into his checkout is true of the code
on disk before the engine restarts, and a restart onto the same interpreter does not
change it, so the panel says it from the next poll.

A REPORT, NEVER A REFUSAL TO START, as `db.wal_reset_bug` is for SQLite: the interpreter
is whatever the launcher names. `/api/health` carries it on the panel's timed poll, so
`report` never raises. A pin it cannot read is said as unknown, and the reason travels
with it.
"""
from __future__ import annotations

import platform
import re
import sys
from collections.abc import Sequence
from pathlib import Path

#: The one file that names the engine's Python.
PIN_FILE = Path(__file__).resolve().parent.parent / ".python-version"


def floor(pin_file: Path | None = None) -> tuple[int, int]:
    """The oldest Python ScrapeX runs on: the MAJOR.MINOR the pin names.

    Any other shape raises `ValueError` rather than being read as some version, and a
    file that cannot be opened raises `OSError`. ASCII digits only, because `\\d` also
    matches an Arabic-Indic digit and `int` reads it.
    """
    path = PIN_FILE if pin_file is None else pin_file
    text = path.read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)", text)
    if match is None:
        raise ValueError(f"{path.name} must hold MAJOR.MINOR, and it holds {text!r}")
    return int(match.group(1)), int(match.group(2))


def verdict(version: Sequence[int], minimum: tuple[int, int]) -> str:
    """"ok" at or above the floor, "below" under it.

    Compared on MAJOR.MINOR, which is all a `>=MAJOR.MINOR` floor asks of a release.
    It matches pip, which judges `requires-python` against `sys.version_info[:3]` and
    so drops a pre-release tag: 3.15.0a1 meets a 3.15 floor.
    """
    return "ok" if tuple(version[:2]) >= minimum else "below"


def report() -> dict:
    """What `/api/health` carries: this interpreter's version, the floor, the verdict."""
    version = platform.python_version()
    try:
        minimum = floor()
    except (OSError, ValueError) as exc:
        return {"version": version, "floor": None, "verdict": "unknown",
                "detail": f"the pin could not be read: {type(exc).__name__}: {exc}"}
    return {"version": version, "floor": f"{minimum[0]}.{minimum[1]}",
            "verdict": verdict(sys.version_info, minimum)}
