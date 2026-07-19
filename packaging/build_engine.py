"""Build the standalone ScrapeX engine executable (spec: frictionless install).

Run this on the TARGET platform — PyInstaller does not cross-compile, so a
Windows .exe must be built on Windows and a macOS binary on macOS.

    pip install -e ".[ui,local,commodity]" pyinstaller
    python packaging/build_engine.py

The result is dist/scrapex-engine(.exe): a single file the user double-clicks,
with no Python install and no `pip` step. That executable is also what the native
messaging manifest should point at:

    scrapex install-native-host --extension-id <ID> --executable <path to exe>

NOT IMPLEMENTED HERE — stated plainly rather than stubbed:
  * Code signing. An unsigned binary trips SmartScreen/Gatekeeper. Signing needs
    a certificate that only the owner can hold.
  * OTA self-update. That needs a release feed + signature verification; shipping
    an updater that fetches and executes unsigned code would be worse than none.
    Until it exists, `PING` returns app_version and the extension surfaces a
    version mismatch so an out-of-date engine is at least VISIBLE.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "packaging" / "engine_entry.py"
NAME = "scrapex-engine"


def build() -> int:
    if not ENTRY.exists():
        print(f"missing entry point: {ENTRY}", file=sys.stderr)
        return 1
    command = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        # The DDL is the source of truth and is read at runtime, so it must ride along.
        "--add-data", f"{ROOT / 'db'}{';' if sys.platform == 'win32' else ':'}db",
        "--add-data", f"{ROOT / 'sources.yaml'}{';' if sys.platform == 'win32' else ':'}.",
        str(ENTRY),
    ]
    print(" ".join(command))
    try:
        return subprocess.call(command)
    except FileNotFoundError:
        print("PyInstaller is not installed: pip install pyinstaller", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(build())
