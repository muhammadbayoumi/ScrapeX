"""Every browser test file launches ONE Chromium, and the launch is module-scoped.

WHY THIS IS A GUARD AND NOT A PREFERENCE. `tests/test_grid_dom.py` declared a
`scope="module"` fixture whose launch sat inside the closure it returned, so
`sync_playwright().start()` and `chromium.launch()` ran on every one of its 24 tests
while only the temp directory was hoisted. Measured: 60.8 s for that file against 31.4 s
once the launch was hoisted -- and the 23 extra driver-and-browser pairs were alive while
the rest of the suite ran beside them.

THE COST LANDED IN OTHER FILES. Three Playwright timeouts are recorded against three
DIFFERENT files -- #958 `test_grid_dom`, #976 `test_panel_startup`, #1019
`test_signing_out_really_signs_out` and `test_panel_dom` -- each failing at a 30-second
wait under full-suite load and passing alone. A starved machine is the shape they share,
which is why this is checked for every file rather than fixed in the one that had it.

READ AS A SYNTAX TREE, not as text: the defect was invisible to a grep, because the
decorator said `scope="module"` and the launch was two indents further in.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

# Guards the browser tier's shape; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

TESTS = pathlib.Path(__file__).resolve().parent


def _browser_launchers(source: str) -> list[tuple[str, str, int]]:
    """(function name, fixture scope, line) for every function that launches Chromium."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "sync_playwright" not in ast.dump(node):
            continue
        scope = "function"
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                for keyword in decorator.keywords:
                    if keyword.arg == "scope" and isinstance(keyword.value, ast.Constant):
                        scope = keyword.value.value
        found.append((node.name, scope, node.lineno))
    return found


def _browser_files() -> list[pathlib.Path]:
    """Every test file that actually launches a browser.

    THIS FILE IS EXCLUDED BY NAME, and not by cleverness: it names `sync_playwright` in
    its prose and in the parser below, so a plain substring search selects it, finds no
    fixture, and the guard fails on itself.
    """
    return sorted(path for path in TESTS.glob("test_*.py")
                  if path.name != pathlib.Path(__file__).name
                  and "sync_playwright" in path.read_text(encoding="utf-8"))


def test_there_are_browser_files_to_check():
    """A glob that silently matches nothing is a green test checking nothing."""
    files = _browser_files()
    assert len(files) >= 8, (
        f"only {len(files)} test file(s) use Playwright: {[f.name for f in files]}. "
        f"Nine did when this guard was written; a number this low means the tier moved "
        f"and this file is looking in the wrong place."
    )


@pytest.mark.parametrize("path", _browser_files(), ids=lambda p: p.name)
def test_the_launch_is_hoisted_to_the_module(path: pathlib.Path):
    """The function that calls `sync_playwright` must itself be module-scoped.

    Nesting the launch inside a function-scoped helper, or inside a closure a
    module-scoped fixture returns, costs one driver and one browser process per test --
    which is what this guard exists to refuse.
    """
    launchers = _browser_launchers(path.read_text(encoding="utf-8"))

    assert launchers, (
        f"{path.name} imports sync_playwright and no function launches a browser; "
        f"either the import is dead or the launch moved somewhere this cannot see it"
    )
    assert len(launchers) == 1, (
        f"{path.name} launches a browser from {len(launchers)} places: "
        f"{[(name, line) for name, _, line in launchers]}. One per file, so the cost is "
        f"one browser however many tests the file holds."
    )
    name, scope, line = launchers[0]
    assert scope == "module", (
        f"{path.name}:{line} launches Chromium from `{name}`, which is {scope}-scoped. "
        f"Every test in the file then pays a driver and a browser process, and they are "
        f"alive while the rest of the suite runs -- the starvation behind the 30-second "
        f"Playwright timeouts in #958, #976 and #1019. Hoist the launch into a "
        f"`scope=\"module\"` fixture and give each test a fresh CONTEXT instead."
    )
