"""Every file the engine's pages are served from is in pyproject.toml's package-data (#1046).

Two declarations say which files the web UI needs at runtime: the engine build's
RUNTIME_DATA (packaging/build_engine.py), which bundles the whole of
scrapex/webui/templates and scrapex/webui/static, and `[tool.setuptools.package-data]`,
which a wheel is built from. The second was a list of globs, and it missed five tracked
files the first one ships, among them static/pages/data-model.js, which
templates/data_model.html loads.

Nothing builds a wheel today, so this is the drift a wheel built tomorrow would inherit.
The globs are expanded the way setuptools expands them: `glob(..., recursive=True)`
under the package's directory, where `*` does not cross `/` and `**` does.
"""
from __future__ import annotations

import glob
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "scrapex" / "webui"
TREES = ("scrapex/webui/templates", "scrapex/webui/static")


def _patterns() -> list[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["tool"]["setuptools"]["package-data"]["scrapex.webui"]


def _packaged(patterns: list[str]) -> set[str]:
    return {Path(path).relative_to(ROOT).as_posix()
            for pattern in patterns
            for path in glob.glob(str(PACKAGE / pattern), recursive=True)
            if Path(path).is_file()}


def _tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files", "--", *TREES], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    return set(out.splitlines())


def test_every_tracked_webui_file_matches_a_package_data_glob():
    tracked = _tracked()
    # The two trees hold the pages, the stylesheets and the scripts; an empty or tiny
    # listing means git answered for a different tree, and every file would pass.
    assert len(tracked) >= 50, tracked
    assert "scrapex/webui/static/pages/data-model.js" in tracked
    missing = sorted(tracked - _packaged(_patterns()))
    assert not missing, ("tracked files a wheel would leave out:\n  " + "\n  ".join(missing)
                         + "\npackaging/build_engine.py's RUNTIME_DATA ships them; "
                         "pyproject.toml's [tool.setuptools.package-data] must too.")


def test_the_expansion_does_not_let_a_star_cross_a_directory():
    """The one way this test could pass while a wheel still lacked a file: matching with
    fnmatch, where `*` crosses `/`. setuptools' glob does not, and neither does this."""
    assert "scrapex/webui/static/pages/data-model.js" not in _packaged(["static/*.js"])
    assert "scrapex/webui/static/pages/data-model.js" in _packaged(["static/**/*.js"])
