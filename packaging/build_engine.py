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

#: EVERYTHING THE ENGINE OPENS OFF DISK, as `(what to copy, where it lands)`
#: relative to the bundle root. PyInstaller bundles MODULES; it never guesses
#: that a package also reads files, so anything not named here is simply absent
#: from the .exe and its absence is discovered by a person, on their machine.
#:
#: THE DEFECT THIS LIST EXISTS FOR, measured on the published `engine-v0.3.0` —
#: the build the panel's Download button was handing every user:
#:
#:     [3/3] Starting the engine...
#:     error: Directory 'C:\...\_MEI000036d42\scrapex\webui\static' does not exist
#:
#: The recipe named `db` and `sources.yaml`. The runtime reads FIVE things, and
#: `scrapex/webui/app.py`'s `STATIC_DIR` computes `Path(__file__).parent / "static"` —
#: under a one-file build is `_MEIPASS/scrapex/webui/static`, exactly the path in
#: that message. `StaticFiles(check_dir=True)` refuses to mount a directory that
#: is not there, `create_app` raises, `main()`'s catch-all in `scrapex/cli.py` prints
#: engine that unpacked and prepared a database perfectly cannot serve one page.
#:
#: A LIST, RATHER THAN THREE MORE `--add-data` ARGUMENTS, because the drift is
#: the defect. `pyproject.toml` already carries the same fact for wheels under
#: `[tool.setuptools.package-data]`, the two disagreed, and nothing compared
#: them. `tests/test_the_frozen_engine_carries_its_own_files.py` now stages this
#: list the way PyInstaller would and starts the engine inside it, so a resource
#: added tomorrow fails in CI instead of on a desktop.
RUNTIME_DATA: tuple[tuple[str, str], ...] = (
    # The DDL and every migration: read at runtime, and the source of truth.
    ("db", "db"),
    # The shop contracts — `scrapex/config.py`'s `MANIFEST_FILE`.
    ("sources.yaml", "."),
    # Every page the engine serves — the `TEMPLATES` of `scrapex/webui/app.py` and
    # of `scrapex/extract/api.py`. Jinja2Templates does NOT check its directory
    # at construction, so a missing templates tree is not a startup error; it is
    # a `TemplateNotFound` on whichever page the owner opens first.
    ("scrapex/webui/templates", "scrapex/webui/templates"),
    # The CSS, JS and icons those pages ask for — `scrapex/webui/app.py`'s `STATIC_DIR`.
    ("scrapex/webui/static", "scrapex/webui/static"),
    # What "Copy Script" hands the owner — `outputs.apps_script_script_text`. Its absence
    # is the quiet one: the function returns "" and the route answers 404 saying
    # the script "is not bundled", which was true of every build ever shipped.
    ("apps_script/StagingAppScript.txt", "apps_script"),
)


def add_data_arguments() -> list[str]:
    """`RUNTIME_DATA` as PyInstaller arguments, with the platform's separator."""
    separator = ";" if sys.platform == "win32" else ":"
    arguments: list[str] = []
    for source, destination in RUNTIME_DATA:
        arguments += ["--add-data", f"{ROOT / source}{separator}{destination}"]
    return arguments


def build() -> int:
    if not ENTRY.exists():
        print(f"missing entry point: {ENTRY}", file=sys.stderr)
        return 1
    # REFUSED HERE RATHER THAN AT RUNTIME. PyInstaller warns about a missing
    # `--add-data` source and builds anyway, and the warning scrolls past inside
    # a ten-minute build log. The engine that comes out starts, unpacks, prepares
    # a database and then cannot serve a page — which is a defect nobody meets
    # until it is published.
    missing = [source for source, _ in RUNTIME_DATA if not (ROOT / source).exists()]
    if missing:
        print(f"the engine reads these at runtime and they are not here: {missing}",
              file=sys.stderr)
        return 1
    command = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", NAME,
        # THE ONLY THING THAT CAN SPEAK BEFORE PYTHON DOES. A one-file binary
        # opens its console and then extracts ~60 MB before a single line of
        # our code runs -- measured at 2.6-6.9 seconds on a warm machine, and
        # longer on a first run while Defender inspects a new unsigned exe. All
        # of it is a black window with no text, which is how the owner met the
        # engine on 2026-08-10 and concluded it was broken.
        #
        # `_say` flushes correctly and prints early; neither helps, because
        # Python has not started. PyInstaller draws this image itself, from the
        # bootloader, during the extraction. engine_entry closes it as soon as
        # it has something real to show.
        #
        # Trimming the bundle does NOT fix this: dropping the test extras took
        # it from 67.6 MB to 60.1 MB, which is still seconds of unpacking. Size
        # and silence are two problems and this one is the silence.
        "--splash", str(ROOT / "packaging" / "splash.png"),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        *add_data_arguments(),
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
