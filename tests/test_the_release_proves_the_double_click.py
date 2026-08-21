"""The release must run the engine the way a PERSON runs it, and hear something.

THE DEFECT THIS EXISTS FOR, measured on 2026-08-21 against the published
`engine-v0.2.1` — the byte-exact file the panel's Download button hands a user,
70,872,447 bytes and sha256 `df7a00ee…`, matching the release manifest exactly:

    ./scrapex-engine.exe --version   ->  "ScrapeX-Engine 0.2.1 (protocol 1)"
    ./scrapex-engine.exe             ->  ZERO BYTES, and still alive after 20s

The owner double-clicked it, met a black window with nothing in it, and reported
that the engine had not installed. Nothing was wrong with the download.

WHY IT SHIPPED THAT WAY. The tag `engine-v0.2.1` is commit `4386d25`, and at
that commit `packaging/engine_entry.py` sent bare invocation to `serve()` — the
Chrome native messaging host, which waits on stdin for framed JSON and prints
nothing at all. `_first_run` landed SIX HOURS LATER (`7a067c5`) and the unpack
splash the day after (`756fa39`). The repository has held the fix ever since and
has never cut a release carrying it.

AND THE RELEASE GATE PASSED IT, which is the part a test can prevent. The only
question the workflow asked the built binary was `--version`: the one argument
no user ever types, on the one branch that was already right. The source-level
dispatch has been guarded all along by
`tests/test_native.py::test_the_entry_point_tells_its_three_callers_apart`;
NOTHING guarded the artifact, so a binary that is silent to a human passed every
check and was published.

These tests read the workflow rather than building a binary — a build takes
minutes and needs PyInstaller, and what has to stay true is a property of the
recipe. That is the same reasoning
`test_the_release_build_is_not_the_test_build.py` gives for reading it too.
"""
from __future__ import annotations

import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-engine.yml"
ENTRY = ROOT / "packaging" / "engine_entry.py"

#: How the workflow spells "run the thing that was just built". Both existing
#: run-steps use it; the checksum step says a bare `scrapex-engine.exe` after a
#: `cd dist`, and that one is an argument to `sha256sum` rather than a launch.
#: Pinning the spelling is deliberate — if it changes, every test below fails
#: loudly instead of quietly finding nothing to check.
LAUNCH = re.compile(r"\./dist/scrapex-engine\.exe(?P<rest>[^\n]*)")

#: What an ARGUMENT looks like where it would sit. A redirect, a pipe, a closing
#: paren or end-of-line means the binary was launched with nothing — which is
#: what Explorer does on a double-click, and what Chrome never does.
ARGUMENT = re.compile(r"^[\w./-]")

GREPPED = re.compile(r"""grep\s+-q\s+["'](?P<pattern>[^"']+)["']""")


@pytest.fixture(scope="module")
def steps() -> list[dict]:
    assert WORKFLOW.is_file(), f"{WORKFLOW} is gone; this guard must follow it"
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for step in document["jobs"]["build"]["steps"] if step.get("run")]


@pytest.fixture(scope="module")
def bare_run(steps) -> str:
    """The one run-step that launches the built engine with no arguments."""
    found = [
        step["run"] for step in steps
        for match in LAUNCH.finditer(step["run"])
        if not ARGUMENT.match(match.group("rest").strip())
    ]
    assert found, (
        "the release never launches the built engine the way a person launches "
        "it — with no arguments. That is the branch of engine_entry.main that "
        "shipped as a black window in 0.2.1, and asking it `--version` does not "
        "exercise it"
    )
    assert len(found) == 1, "two steps double-click the engine; say which is the gate"
    return found[0]


@pytest.fixture(scope="module")
def double_click_path() -> str:
    """The source of what a double-click actually executes.

    Sliced at `_first_run` rather than read whole, so a line that only exists in
    the `--version` branch or in a comment near the top cannot be mistaken for
    something the double-click prints.
    """
    source = ENTRY.read_text(encoding="utf-8")
    start = source.find("def _first_run(")
    assert start != -1, (
        "packaging/engine_entry.py has no _first_run — bare invocation has "
        "stopped being a first run, which is exactly the 0.2.1 defect"
    )
    return source[start:]


def test_the_release_launches_the_engine_with_no_arguments(bare_run):
    """Asked of the artifact, because the source was never the thing that shipped."""
    assert "scrapex-engine.exe" in bare_run


def test_a_silent_first_run_is_refused(bare_run):
    """PRINTING NOTHING IS THE FAILURE, and it has to be named as one.

    0.2.1 exited 0. Every check that reads an exit code — and the `--version`
    step is one — calls that a pass. The only evidence that separates a working
    engine from a black window is whether any characters arrived, so the step
    must test the OUTPUT and refuse it when empty.
    """
    assert re.search(r'\[\s+-z\s+"\$\w+"\s+\]', bare_run), (
        "the double-click step does not refuse empty output, so a binary that "
        "prints nothing at all still passes the release gate"
    )
    assert "exit 1" in bare_run, "it notices the silence and ships anyway"


def test_the_bare_run_is_bounded_because_a_good_first_run_never_returns(bare_run):
    """A successful first run IS the running engine, so it cannot be waited on.

    `_first_run` ends inside uvicorn and does not come back — the window being
    open is the same fact as the engine being up. A release step that simply
    called it would hang until the job timed out, so the bound is what makes
    this check possible at all rather than a nicety.
    """
    assert "timeout " in bare_run, (
        "nothing bounds the double-click run, and a first run that works never "
        "returns — this step would hang the release rather than gate it"
    )


def test_it_does_not_touch_a_warehouse_it_did_not_make(bare_run):
    """A first run CREATES a database. A release check must create its own.

    `_first_run` calls `DatabaseRegistry.defaults()`, which reads
    `SCRAPEX_DATA_ROOT` and otherwise lands in the home directory. On a runner
    that is merely untidy; the rule matters because this same step is what a
    person reaches for when reproducing a release locally, and there it would
    open — and upgrade — their real warehouse.

    Asserted as an ASSIGNMENT rather than a mention, because a mention is what
    the weaker version of this test accepted: pointing the export at a different
    variable left the name behind in the `mkdir` line beside it and the check
    passed while the run had gone back to the real data root. Found by mutating
    it.
    """
    assert re.search(r"SCRAPEX_DATA_ROOT\s*=", bare_run), (
        "the double-click step runs against the default data root, so it opens "
        "whatever warehouse the machine already has"
    )


def test_every_line_it_demands_is_one_the_double_click_actually_prints(
        bare_run, double_click_path):
    """THE GUARD MUST NOT DRIFT FROM THE CODE IT GUARDS.

    A `grep` for a sentence nobody prints any more fails every release for a
    reason that is nothing to do with the engine; a `grep` loosened to something
    trivially true stops guarding anything. So each demanded string is checked
    against the source of the path that would have to print it — and both kinds
    of drift become this one failure.
    """
    demanded = [m.group("pattern") for m in GREPPED.finditer(bare_run)]
    assert demanded, (
        "the step accepts any output at all. Non-empty is not the same as "
        "working: an engine that prints only a traceback would pass"
    )
    missing = [line for line in demanded if line not in double_click_path]
    assert not missing, (
        f"the release demands {missing} of a double-click, and nothing on the "
        f"double-click path in packaging/engine_entry.py prints it"
    )


def test_it_proves_the_database_step_survived(bare_run, double_click_path):
    """The last of the three steps, which is the one worth asking for.

    `_set_up_then_serve` names each step before attempting it, so "Preparing
    your database" proves only that the attempt STARTED. The line after it is
    printed only once `ensure_ready()` has returned, so demanding that one turns
    this check from "the engine spoke" into "the engine got a warehouse ready" —
    the step with the most ways to fail on somebody else's machine, and the one
    that fails on the owner's right now.
    """
    demanded = [m.group("pattern") for m in GREPPED.finditer(bare_run)]
    later = double_click_path.find("Starting the engine")
    earlier = double_click_path.find("Preparing your database")
    assert later != -1 and earlier != -1 and earlier < later, (
        "the three steps of _set_up_then_serve have been reordered or renamed; "
        "this guard's reasoning about what proves what no longer holds"
    )
    assert any("Starting the engine" in line for line in demanded), (
        "the release does not require the engine to get past preparing a "
        "database, so a build that dies there still ships"
    )
