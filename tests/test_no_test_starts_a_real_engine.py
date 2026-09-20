"""No test may send START_ENGINE without first neutralising the spawn.

WHAT THIS COSTS WHEN IT IS MISSING, measured on the owner's machine on 2026-09-20. Three
tests patched `_engine_listening` and nothing else. `start_engine` consults that only as a
first check and then asks `_engine_answering` for a real reply, so on any box where nothing
answers port 8000 the call fell through to `_spawn_engine` -- which started a DETACHED
`pythonw -m scrapex.cli ui --port 8000`, inheriting conftest's `SCRAPEX_DATA_ROOT` and so
opening a warehouse inside `%TEMP%`.

That engine outlived the run, held the panel's own port, and the panel connected to it. The
owner's screen then read:

    Temporary database -- Not your data. The engine has a database open inside <<Temp>>,
    a folder meant to be thrown away, so nothing on these screens is your collection.

25 such roots had accumulated since 2026-09-11 (#981), and #1023 records that the panel
offers no way out of the state -- its Restart control inherits the same variable (#988) and
reproduces it. So a leak here does not merely litter: it takes over the product.

TWO WAYS TO BE SAFE, and the guard accepts either, because `start_engine` reaches the spawn
only when `_engine_answering` returns None (`scrapex/native.py:389-395`):

  * patch `_spawn_engine`   -- the spawn is a no-op
  * patch `_engine_answering` to answer -- `start_engine` returns at its early branch

READ AS A SYNTAX TREE, and only real `setattr` CALLS count. A substring search for
`_spawn_engine` scores a test safe because its COMMENT mentions the name -- which is exactly
how a first pass at this guard cleared three of the leaking tests, and the same defect this
repository has recorded once already in a sibling guard (#1021).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

# Guards the native host's test tier; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

TESTS = pathlib.Path(__file__).resolve().parent

# Neutralising either one stops the spawn. See the module docstring.
DISARMS = frozenset({"_spawn_engine", "_engine_answering"})


def _monkeypatched_names(node: ast.FunctionDef) -> set[str]:
    """Every attribute name this function patches, by a real `setattr(...)` call.

    Deliberately blind to comments and docstrings -- see the module docstring for why
    that distinction is the whole point of parsing rather than grepping.
    """
    names: set[str] = set()
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        if getattr(inner.func, "attr", None) != "setattr":
            continue
        for arg in inner.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.add(arg.value)
    return names


def _sends_a_start_engine_command(node: ast.FunctionDef) -> bool:
    """Does this test hand the native host a `{"command": "START_ENGINE"}` DICT?

    The dict is the discriminator, not the word. `tests/test_panel_dom.py:3495`
    asserts that the STRING `sendNative({ command: "START_ENGINE" }, ...)` appears in
    `extension/transport.js` -- it reads the file as text, never imports
    `scrapex.native` and cannot spawn anything. A first version of this guard scored
    it a leak, which is the same over-broad reading that this file's docstring warns
    about from the other direction.
    """
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Dict):
            continue
        for key, value in zip(inner.keys, inner.values):
            if (isinstance(key, ast.Constant) and key.value == "command"
                    and isinstance(value, ast.Constant) and value.value == "START_ENGINE"):
                return True
        # `{"command": c}` inside `for c in ("PING", "START_ENGINE")` -- the name is
        # bound, so the dict alone cannot show it. Fall through to the loop check.
    for inner in ast.walk(node):
        if isinstance(inner, ast.For) and isinstance(inner.iter, (ast.Tuple, ast.List)):
            for element in inner.iter.elts:
                if isinstance(element, ast.Constant) and element.value == "START_ENGINE":
                    return True
    return False


def _tests_that_start_the_engine() -> list[tuple[pathlib.Path, ast.FunctionDef, str]]:
    """(file, function, its source) for every test that really drives START_ENGINE."""
    found = []
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == pathlib.Path(__file__).name:
            continue
        source = path.read_text(encoding="utf-8")
        if "START_ENGINE" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            if not _sends_a_start_engine_command(node):
                continue
            found.append((path, node, ast.get_source_segment(source, node) or ""))
    return found


def _ids(case) -> str:
    path, node, _ = case
    return f"{path.name}::{node.name}"


CASES = _tests_that_start_the_engine()


def test_there_are_start_engine_tests_to_check():
    """A glob that silently matches nothing is a green test checking nothing."""
    assert len(CASES) >= 8, (
        f"only {len(CASES)} test(s) send START_ENGINE: {[_ids(c) for c in CASES]}. "
        f"Ten did when this guard was written; a number this low means the tier moved "
        f"and this file is looking in the wrong place."
    )


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_the_spawn_is_disarmed_before_start_engine_is_sent(case):
    path, node, _body = case
    patched = _monkeypatched_names(node)
    assert patched & DISARMS, (
        f"{path.name}:{node.lineno} `{node.name}` sends START_ENGINE and patches "
        f"{sorted(patched) or 'nothing'} -- none of which stops the spawn.\n"
        f"\n"
        f"`_engine_listening` is NOT enough: start_engine consults it first and then "
        f"asks `_engine_answering` for a real reply (scrapex/native.py:389), so where "
        f"nothing answers the port this reaches `_spawn_engine` and starts a detached "
        f"engine on 8000 -- the panel's own port -- carrying conftest's "
        f"SCRAPEX_DATA_ROOT into a %TEMP% warehouse that outlives the run (#1023).\n"
        f"\n"
        f"Add one of:\n"
        f'    monkeypatch.setattr(native, "_spawn_engine", lambda port: None)\n'
        f'    monkeypatch.setattr(native, "_engine_answering",\n'
        f'                        lambda port, timeout=1.5: {{"app": "scrapex"}})'
    )
