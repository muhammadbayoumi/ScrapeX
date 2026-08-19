"""What marks a test file actually DECLARES, read from its `pytestmark`.

WHY THIS IS NOT A SUBSTRING SEARCH, and the answer was measured rather than
guessed. Both gate files used to ask `"pytest.mark.extension" in source`, and both
were wrong in the same way: a file that merely MENTIONS the name -- in a docstring,
in an assertion message telling the reader to add the mark, in the gate's own
detector -- counts as marked. Deleting

    pytestmark = pytest.mark.docs

from `tests/test_the_docs_gate_is_complete.py` left the string in four other places
in that same file, so the guard went on reporting the file as a member of the set it
had just left. The gate that exists to catch a missing mark could not catch its own.

`ast`, not a regex, because `pytestmark` is written both ways here --
`pytestmark = pytest.mark.extension` and
`pytestmark = [pytest.mark.extension, pytest.mark.docs]` -- and a list may be
wrapped across lines at any time without anyone thinking about this file.
"""
from __future__ import annotations

import ast
import pathlib


def _named(node: ast.AST) -> str | None:
    """`pytest.mark.docs` -> "docs". Anything else -> None."""
    if (isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "mark"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "pytest"):
        return node.attr
    return None


def declared_marks(source: str) -> frozenset[str]:
    """Every mark this file puts on itself or on one of its tests.

    BOTH PLACEMENTS COUNT, because the question a gate asks is *will anything in
    this file run under `-m <mark>`*, and a decorator answers it as well as a
    module-level assignment does.
    `tests/test_the_lint_gate_cannot_be_quietly_widened.py` writes
    `@pytest.mark.extension` on the single test that reads extension/ and says why
    in a comment: only that one has to run on an extension-only change. A helper
    that read `pytestmark` alone called that file unmarked, which is how this
    second half came to be written.

    A file that cannot be parsed returns nothing rather than raising: a syntax
    error is the test run's failure to report, not this helper's, and a guard that
    died here would hide it behind a traceback about marks.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return frozenset()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark"
                for t in node.targets):
            value = node.value
            items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
            found.update(n for n in (_named(item) for item in items) if n)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # A parametrised decorator -- `pytest.mark.skipif(...)` -- is a Call
            # whose func carries the attribute chain, so both shapes are unwrapped.
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                name = _named(target)
                if name:
                    found.add(name)
    return frozenset(found)


def carries(path: pathlib.Path, mark: str) -> bool:
    """Whether this test file declares `mark` at module level."""
    return mark in declared_marks(path.read_text(encoding="utf-8"))
