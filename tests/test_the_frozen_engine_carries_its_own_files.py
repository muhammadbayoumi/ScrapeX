"""A shipped engine must carry the files it opens, and be started inside them.

THE DEFECT, measured on the published `engine-v0.3.0` — the tag cut on 2026-08-22,
the newest thing the panel's Download button offers, and the build the owner ran
on 2026-08-23:

    [1/3] Unpacking...        done.
    [2/3] Preparing your database...   already there: ...\\scrapex-engine.db
    [3/3] Starting the engine...
    error: Directory 'C:\\...\\_MEI000036d42\\scrapex\\webui\\static' does not exist

Every step it announced succeeded. The engine unpacked, opened its warehouse, and
then could not serve a single page, because `packaging/build_engine.py` named two
things — `db` and `sources.yaml` — and the runtime reads five.

WHY PYINSTALLER CANNOT WORK THIS OUT. It bundles MODULES. A package that also
opens files off disk is invisible to it, so `scrapex/webui/static` was never in
the archive; `webui.app`'s `STATIC_DIR` computes `Path(__file__).parent / "static"`,
which in a one-file build is `_MEIPASS/scrapex/webui/static` — the exact path in
that message — and `StaticFiles(check_dir=True)` refuses to mount what is not
there.

AND THE RELEASE GATE PASSED IT, which is the part a test can prevent. The
double-click step demanded three lines: `ScrapeX-Engine`, `Preparing your
database`, and `Starting the engine`. **All three are printed BEFORE `create_app`
is called** (`packaging/engine_entry.py:_set_up_then_serve`), so the gate stopped
one line short of the failure — the same shape of mistake as 0.2.1, where it
stopped at `--version`. The line that proves a server exists is
`scrapex/cli.py:_cmd_ui`, printed only after `create_app` returned, and
`tests/test_the_release_proves_the_double_click.py` now requires it.

HOW THESE TESTS AVOID A TEN-MINUTE BUILD. What must stay true is that
`RUNTIME_DATA` covers everything the engine opens, and the path arithmetic that
decides it is `Path(__file__)` — identical in a bundle and in any directory laid
out like one. So a bundle is STAGED the way PyInstaller would lay it out (modules,
then `RUNTIME_DATA`, and nothing else) and the engine is started inside it. A
resource added tomorrow and forgotten fails here, in seconds, instead of on
somebody's desktop.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD_RECIPE = ROOT / "packaging" / "build_engine.py"

#: What the staged engine is asked to prove, and it is deliberately the whole of
#: `_first_run` past the unpack: open the warehouse (`db`), load the contracts
#: (`sources.yaml`), build the app (`scrapex/webui/static`, the one that crashed),
#: find every page (`scrapex/webui/templates`) and hand over the Apps Script
#: (`apps_script`). One report, so a single run names every gap rather than the
#: first one.
#:
#: `sys.path` IS REPLACED, not appended to, because a bundle has exactly one
#: import root and this test is worthless if it accidentally imports the working
#: tree. An editable install of this repository registers a meta-path finder that
#: wins over `sys.path` entirely — the trap CLAUDE.md names — so it is dropped
#: too, and the report carries `scrapex.__file__` for the assertion that catches
#: any remaining leak.
PROBE = r'''
import json, os, sys

stage = os.environ["SCRAPEX_STAGE"]
sys.path.insert(0, stage)
sys.meta_path = [f for f in sys.meta_path
                 if "__editable__" not in getattr(type(f), "__module__", "")]

import scrapex
if not os.path.abspath(scrapex.__file__).startswith(os.path.abspath(stage)):
    raise SystemExit(f"LEAKED: imported {scrapex.__file__}, not the staged bundle")

from scrapex.config import load_manifest
from scrapex.databases.registry import DatabaseRegistry
from scrapex.outputs import apps_script_script_text

registry = DatabaseRegistry.defaults()
registry.ensure_ready()

from scrapex.extract import api as extract_api
from scrapex.webui import app as webui

# The line that crashed on the owner's machine. Nothing above it touches static.
application = webui.create_app(None, start_worker=False, databases=registry)

report = {
    "package": scrapex.__file__,
    "sources": len(load_manifest(None).sources),
    "static_mounted": any(getattr(route, "name", None) == "static"
                          for route in application.routes),
    "templates": sorted(webui.TEMPLATES.env.list_templates()),
    "extract_templates": sorted(extract_api.TEMPLATES.env.list_templates()),
    "base_html_compiles": bool(webui.TEMPLATES.get_template("base.html")),
    "apps_script_chars": len(apps_script_script_text()),
}
print("REPORT " + json.dumps(report))
'''


def _recipe():
    """`packaging/build_engine.py`, which is not importable as a package."""
    assert BUILD_RECIPE.is_file(), f"{BUILD_RECIPE} is gone; this guard must follow it"
    spec = importlib.util.spec_from_file_location("scrapex_build_recipe", BUILD_RECIPE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage(destination: Path, data: tuple[tuple[str, str], ...]) -> Path:
    """Lay out a bundle the way PyInstaller lays out `_MEIPASS`.

    MODULES ONLY from the package, then the declared data. Copying the package
    wholesale would drag `webui/static` in as a side effect and this test would
    pass no matter what the recipe said — which is the failure mode it exists to
    catch, so the `*.py` filter is the whole point rather than a tidiness.
    """
    for module in ROOT.joinpath("scrapex").rglob("*.py"):
        if "__pycache__" in module.parts:
            continue
        target = destination / module.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(module, target)
    for source, where in data:
        origin = ROOT / source
        if origin.is_dir():
            # PyInstaller copies the CONTENTS of a directory into the
            # destination, which is why `("db", "db")` is not `("db", ".")`.
            shutil.copytree(origin, destination / where, dirs_exist_ok=True)
        else:
            landing = (destination / where).resolve()
            landing.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, landing / origin.name)
    return destination


def _start_inside(stage: Path, data_root: Path) -> subprocess.CompletedProcess:
    """Run the engine's own start-up path with the bundle as its only import root."""
    environment = dict(os.environ)
    environment["SCRAPEX_STAGE"] = str(stage)
    # ITS OWN WAREHOUSE. `DatabaseRegistry` reads this at import, and a test that
    # opened — and migrated — the owner's real database would be a worse defect
    # than the one it is checking for.
    environment["SCRAPEX_DATA_ROOT"] = str(data_root)
    environment.pop("SCRAPEX_SOURCES", None)   # so `sources.yaml` must be bundled
    environment["PYTHONPATH"] = str(stage)
    return subprocess.run(
        [sys.executable, "-c", PROBE], cwd=str(stage), env=environment,
        capture_output=True, text=True, timeout=300,
    )


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    """One staged bundle, started once, and the report it printed."""
    recipe = _recipe()
    stage = _stage(tmp_path_factory.mktemp("bundle"), recipe.RUNTIME_DATA)
    done = _start_inside(stage, tmp_path_factory.mktemp("data-root"))
    assert done.returncode == 0, (
        "THE ENGINE CANNOT START INSIDE ITS OWN BUNDLE. This is the 0.3.0 defect: "
        "packaging/build_engine.py names what rides along in the .exe, and "
        "something the runtime opens is not on that list.\n\n"
        f"stdout:\n{done.stdout}\n\nstderr:\n{done.stderr}"
    )
    line = next((l for l in done.stdout.splitlines() if l.startswith("REPORT ")), None)
    assert line, f"the probe printed no report:\n{done.stdout}\n{done.stderr}"
    return {**json.loads(line[len("REPORT "):]), "stage": str(stage)}


def test_every_declared_file_is_actually_in_the_repository():
    """A recipe naming a path that does not exist builds a bundle without it.

    PyInstaller WARNS and carries on, inside a ten-minute log nobody reads, so
    the .exe that comes out is the broken one — which is why the build refuses
    here as well.
    """
    missing = [source for source, _ in _recipe().RUNTIME_DATA
               if not (ROOT / source).exists()]
    assert not missing, f"packaging/build_engine.py names what is not here: {missing}"


def test_the_engine_imported_is_the_staged_one_and_not_the_working_tree(bundle):
    """THE TRAP THIS REPOSITORY NAMES FIRST, asserted rather than hoped for.

    `scrapex` is pip-installed editable against the MAIN checkout. Had the probe
    imported that, every check below would pass by reading the working tree's
    `webui/static` and this file would guard nothing at all.
    """
    imported = Path(bundle["package"]).resolve()
    assert imported.is_relative_to(Path(bundle["stage"]).resolve()), (
        f"the probe imported {imported}, which is not the staged bundle"
    )
    assert not imported.is_relative_to(ROOT), "it read the working tree instead"


def test_the_static_directory_is_in_the_bundle(bundle):
    """The mount that raised on the owner's machine, asked of a bundle.

    `create_app` returning at all is the proof — `StaticFiles(check_dir=True)`
    raises before it can — and the mount is named so a future `check_dir=False`
    cannot turn this into a pass with no files behind it.
    """
    assert bundle["static_mounted"], (
        "the app was built without a /static mount, so the CSS and JS every "
        "page asks for would 404 even though the engine started"
    )


def test_every_page_the_engine_serves_is_in_the_bundle(bundle):
    """TEMPLATES ARE THE QUIET ONE, and that is why they get their own check.

    `Jinja2Templates` does not look at its directory when it is constructed, so a
    missing templates tree is not a start-up failure at all — the engine comes
    up, reports itself healthy, and every page the owner opens is a
    `TemplateNotFound`. Nothing in a release log would show it.
    """
    expected = sorted(
        str(page.relative_to(ROOT / "scrapex" / "webui" / "templates")).replace("\\", "/")
        for page in (ROOT / "scrapex" / "webui" / "templates").rglob("*.html")
    )
    assert bundle["templates"] == expected, (
        "the bundle's template set is not the repository's: "
        f"missing {sorted(set(expected) - set(bundle['templates']))}"
    )
    # `scrapex/extract/api.py` builds a SECOND environment over the same
    # directory. It is asked separately because it resolves the path its own way.
    assert bundle["extract_templates"] == expected
    assert bundle["base_html_compiles"]


def test_the_contracts_and_the_schema_came_along(bundle):
    """`sources.yaml` and `db/` — the two the recipe already had, kept honest."""
    assert bundle["sources"] > 0, (
        "the bundled engine loaded no sources, so sources.yaml is missing and "
        "every crawl would have nothing to crawl"
    )


def test_the_apps_script_the_owner_pastes_is_in_the_bundle(bundle):
    """THE SILENT ONE. It has never shipped, and it fails as a 404, not a crash.

    `outputs.apps_script_script_text` returns `""` when the file is absent and the route
    answers 404 saying the script "is not bundled" — a sentence that was true of
    every engine ever published. The owner presses Copy Script and gets nothing,
    with no failure anywhere to read.
    """
    source = ROOT / "apps_script" / "StagingAppScript.txt"
    assert bundle["apps_script_chars"] == len(source.read_text(encoding="utf-8")), (
        "Copy Script would hand the owner an empty script from the shipped engine"
    )


def test_a_bundle_missing_the_static_directory_is_caught_here(tmp_path):
    """THE MUTATION, because a staging test that cannot fail proves nothing.

    This removes exactly the entry that shipped broken and requires the probe to
    die the way 0.3.0 died — with Starlette's own words, so the failure this file
    reproduces is demonstrably the owner's and not a different one.
    """
    recipe = _recipe()
    without = tuple((source, where) for source, where in recipe.RUNTIME_DATA
                    if source != "scrapex/webui/static")
    assert len(without) == len(recipe.RUNTIME_DATA) - 1, (
        "'scrapex/webui/static' is no longer the name of the entry that shipped "
        "missing; this mutation is removing nothing"
    )
    stage = _stage(tmp_path / "bundle", without)
    done = _start_inside(stage, tmp_path / "data-root")
    assert done.returncode != 0, (
        "a bundle with no static directory started anyway, so this file's staging "
        "does not reproduce the shipped layout and none of it guards anything"
    )
    assert "does not exist" in done.stderr and "static" in done.stderr, (
        f"it failed for some other reason than the missing static tree:\n{done.stderr}"
    )
