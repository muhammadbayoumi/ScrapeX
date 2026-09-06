"""The crawl's report reaches the panel, so it may not tell him to open a terminal.

`R-81`: he works only from the extension panel. `contractors.say` writes to whatever sink
is installed, and `scrapex/directoryjob.py` installs one that appends to `job_log_entry`
-- so on a panel-started crawl every `say` line is rendered in the job card's Live log.

WHY THIS IS A STATIC SCAN AND NOT A SCENARIO. Issue #323 removed a command he cannot run
from four surfaces and missed a fifth; this one was then found by reading, not by a test,
after he had already read it in his own log. The surfaces keep being found one at a time
because nothing enumerates them. A scan over the call sites enumerates them.

AND IT IS AN ALLOWLIST BY CALL PATH, NOT BY STRING. Three functions are genuinely
console-only -- reached from the CLI, with no sink installed on that path -- so a flag in
their text is addressed to somebody who typed a flag to get there. Naming them by function
rather than by their wording means a reworded line stays exempt and a NEW line in a
reachable function does not.

WHAT IT FOUND ON ITS FIRST RUN, which is the argument for writing it at all: two more
lines that reading had missed, in `open_engine` and `details`. The fifth surface was four
lines in one module.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COLLECTOR = ROOT / "scrapex" / "contractors.py"

#: Functions whose `say` lines cannot reach the panel, each with the reason it cannot.
#: `_run_for` is not here: everything reachable from `crawl` is in scope, because
#: `directoryjob` installs its sink around the whole call.
CONSOLE_ONLY = {
    # Reached from the `--reapprove` path only. Interpreting stored evidence with no
    # network is a command-line operation and has no panel control to offer instead.
    "_say_reapprove_one",
    # Reached from `--disown-impostors` only, same reason: a repair a person asks for
    # by typing, whose dry-run has to name the flag that applies it.
    "disown_impostors",
    # THE CLI'S OWN DOOR, and it cannot be reached with a sink installed. Its only
    # caller is `run()` at the bottom of this module, which opens the warehouse BEFORE
    # any crawl and therefore before `lines_go_to`; the job runner never calls it at
    # all, because a runner is handed its connection. So a person reading this line
    # typed a command to get here and can type another.
    "open_engine",
}

#: What a runnable command looks like in a sentence. `--flag` catches the common form and
#: `scrapex ` the explicit one; both appear in the two lines this guard was written for.
COMMAND = re.compile(r"(?<![\w-])--[a-z][a-z-]{2,}|\bscrapex\s+[a-z]", re.IGNORECASE)


def _say_lines() -> list[tuple[str, int, str]]:
    """Every `say(...)` call in the collector, as (enclosing function, line, text).

    STRING CONSTANTS ONLY, joined. An f-string's literal parts are read and its
    expressions are not -- a command assembled at runtime is out of reach for a static
    scan, and pretending otherwise would be the vacuous half of this guard.
    """
    found: list[tuple[str, int, str]] = []

    def visit(node: ast.AST, holder: str) -> None:
        """Descend, carrying the name of the function we are currently inside.

        A RECURSIVE DESCENT RATHER THAN `ast.walk`, because `walk` is breadth-first with
        no parent link, so crediting a call to its enclosing function meant a map keyed
        on `id()` and two passes that could disagree about a nested `def`. Carrying the
        name down is what the question actually is.
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            holder = node.name
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "say" and node.args):
            parts = [piece.value for piece in ast.walk(node.args[0])
                     if isinstance(piece, ast.Constant)
                     and isinstance(piece.value, str)]
            if parts:
                found.append((holder, node.lineno, " ".join(parts)))
        for child in ast.iter_child_nodes(node):
            visit(child, holder)

    visit(ast.parse(COLLECTOR.read_text(encoding="utf-8")), "<module>")
    return found


def test_the_scan_can_see_the_lines_it_is_scanning():
    """The guard's own eyesight, because a scan that finds nothing passes everything.

    Measured when this was written: 40-plus `say` call sites with string text. A refactor
    that moved the report elsewhere would silently empty this test, which is the failure
    `PINNED_FLOOR` exists for one document over.
    """
    lines = _say_lines()

    assert len(lines) >= 25, (
        f"the scan found only {len(lines)} `say` call sites with literal text. Either "
        "the report moved out of this module -- in which case this guard must follow "
        "it -- or the walk stopped working")
    assert any(name in CONSOLE_ONLY for name, _line, _text in lines), (
        "no call site resolves to a console-only function, so the allowlist is not "
        "being exercised and could be stale without anyone noticing")


def test_no_line_the_panel_can_show_names_a_command():
    """`R-81`, enumerated instead of discovered.

    #323 removed a command he cannot run from four surfaces. The fifth was this module's
    `the profile half is not part of this run`, which named `scrapex contractors
    --details` and which he read in his own job log while his crawl was paused.
    """
    offenders = [
        f"contractors.py:{line} in {name}(): {COMMAND.search(text).group(0)!r} "
        f"-- {text[:90]}"
        for name, line, text in _say_lines()
        if name not in CONSOLE_ONLY and COMMAND.search(text)]

    assert not offenders, "\n  ".join([
        "these lines reach the job log and name a runnable command. `R-81`: the panel "
        "is his only interface, so a command in a message is offered to nobody. Name "
        "the ACTION and, if there is no control for it, say that there is none -- "
        "leaving the gap visible is the point. If the function genuinely cannot reach "
        "a sink, add it to CONSOLE_ONLY with the reason:",
        *offenders])


def test_every_exempted_function_still_exists_and_still_says_something():
    """AN EXEMPTION THAT OUTLIVES THE THING IT EXEMPTS IS WORSE THAN NO EXEMPTION.

    A typo in `CONSOLE_ONLY`, or a rename of one of those functions, leaves a name that
    exempts nothing while looking accounted for -- and the next reader counts three
    exemptions and stops looking. So every name must resolve to a function that is
    really in the module AND really has a `say` line, because a function with no report
    needs no exemption from a report guard.
    """
    module = ast.parse(COLLECTOR.read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(module)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = sorted(CONSOLE_ONLY - defined)
    assert not missing, (
        f"CONSOLE_ONLY names functions that are not in contractors.py: {missing}. "
        "A renamed function leaves a dead exemption that reads as coverage")

    speaking = {name for name, _line, _text in _say_lines()}
    silent = sorted(CONSOLE_ONLY - speaking)
    assert not silent, (
        f"these functions are exempted and have no `say` line to exempt: {silent}. "
        "Delete them -- the set is a count coming down")


@pytest.mark.parametrize("text", [
    "run `scrapex contractors --details` to fetch them",
    "add --repair to apply it",
    "pass --run-ref to continue",
])
def test_the_pattern_catches_the_forms_that_actually_appeared(text):
    """Anchored on the real wordings, so a narrowed pattern fails here first."""
    assert COMMAND.search(text), f"the pattern misses {text!r}"


@pytest.mark.parametrize("text", [
    "the profile pages are a separate collector over this same registration",
    "it has no control in the panel yet",
    "running it again under the same run reference continues from here",
    "cells proven complete 0 of 0",
    "exhaustiveness deficit 1 -- the run is not provably complete",
])
def test_the_pattern_does_not_flag_ordinary_prose(text):
    """The replacement wordings, and four lines that were always fine.

    A guard that fires on the fix is worse than no guard: it teaches the next person to
    add an exemption rather than to reword.
    """
    assert not COMMAND.search(text), (
        f"the pattern reads ordinary prose as a command: {text!r}")
