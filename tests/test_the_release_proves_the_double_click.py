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
#: THE SECOND HALF OF A DOUBLE-CLICK, and leaving it out is what let 0.3.0 ship.
#: `_set_up_then_serve` ends by setting `argv` to `["ui", "--no-open"]` and calling
#: `cli.main`, so everything a person sees after "Starting the engine..." is
#: printed by `_cmd_ui` — including the only line that proves a server exists.
#: A guard that reads `engine_entry.py` alone believes the double-click path ends
#: three lines before the work does.
CLI = ROOT / "scrapex" / "cli.py"

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

#: A curl INVOCATION and its flags, so a check can ask about each one separately
#: rather than about the step as a lump. Both of this file's substring tests were
#: fooled by text belonging to a different line until mutation said so.
CURL = re.compile(r"curl(?P<flags>(?:\s+-\S+)*)(?P<rest>[^\n]*)")
FAIL_ON_ERROR = re.compile(r"-\w*f")


def _commands(run: str) -> str:
    """A run-step with its comment lines removed.

    THREE OF THIS FILE'S CHECKS WERE SATISFIED BY A COMMENT before mutation said
    so, and the shape is always the same: a step explains what it does directly
    above doing it, so the words survive deleting the command. A guard that reads
    the whole block cannot tell "this step kills the engine" from "this step
    mentions killing the engine". Anything asking whether a COMMAND is present
    asks this instead.
    """
    return "\n".join(line for line in run.splitlines()
                     if not line.lstrip().startswith("#"))


@pytest.fixture(scope="module")
def steps() -> list[dict]:
    assert WORKFLOW.is_file(), f"{WORKFLOW} is gone; this guard must follow it"
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for step in document["jobs"]["build"]["steps"] if step.get("run")]


def _bare_launches(steps) -> list[str]:
    """Every run-step that launches the built engine the way Explorer does.

    THERE ARE TWO NOW, and the assertion that used to demand exactly one said
    "say which is the gate" — so they are told apart by MECHANISM rather than by
    step name, because a name is prose and drifts. One CONSUMES the process to
    read what it printed; the other backgrounds it and talks to it over HTTP.
    Neither can be written the other's way, which is what makes the test sound.
    """
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
    return found


@pytest.fixture(scope="module")
def bare_run(steps) -> str:
    """The step that double-clicks the engine and READS WHAT IT PRINTED."""
    found = [run for run in _bare_launches(steps) if "127.0.0.1" not in run]
    assert len(found) == 1, (
        "expected exactly one step that launches the engine bare and judges its "
        f"OUTPUT; found {len(found)}. Two would each be half a gate"
    )
    return found[0]


@pytest.fixture(scope="module")
def serve_run(steps) -> str:
    """The step that double-clicks the engine and ASKS IT FOR A PAGE.

    A separate step rather than more lines in the one above, and separate for a
    mechanical reason: reading a process's output means waiting for it to end,
    and talking to it over HTTP means it must still be running. One step cannot
    do both to one process.
    """
    found = [run for run in _bare_launches(steps) if "127.0.0.1" in run]
    assert found, (
        "NOTHING IN THE RELEASE EVER ASKS THE BUILT ENGINE FOR A PAGE. Every "
        "check stops at what it printed, and an engine missing "
        "scrapex/webui/templates prints all of it: Jinja2Templates does not "
        "check its directory at construction, so the engine starts, reports "
        "itself healthy, and answers every page with a TemplateNotFound"
    )
    assert len(found) == 1, "two steps fetch a page; say which is the gate"
    return found[0]


@pytest.fixture(scope="module")
def double_click_path() -> str:
    """The source of what a double-click actually executes.

    Sliced at `_first_run` rather than read whole, so a line that only exists in
    the `--version` branch or in a comment near the top cannot be mistaken for
    something the double-click prints.

    AND IT CONTINUES INTO `_cmd_ui`, because that is where the double-click
    actually goes. `_set_up_then_serve` prints its three steps and then calls
    `cli.main` with `["ui", "--no-open"]`; every later line — the one that says a
    server is up among them — belongs to `scrapex/cli.py`. This fixture used to
    stop at `engine_entry.py`, so the gate it guards could only ever demand lines
    printed BEFORE the app was built, which is the whole of the 0.3.0 defect.
    """
    source = ENTRY.read_text(encoding="utf-8")
    start = source.find("def _first_run(")
    assert start != -1, (
        "packaging/engine_entry.py has no _first_run — bare invocation has "
        "stopped being a first run, which is exactly the 0.2.1 defect"
    )
    return source[start:] + ui_command()


def ui_command() -> str:
    """`scrapex/cli.py:_cmd_ui` — what a double-click runs after the three steps."""
    source = CLI.read_text(encoding="utf-8")
    start = source.find("def _cmd_ui(")
    assert start != -1, (
        "scrapex/cli.py has no _cmd_ui, and packaging/engine_entry.py hands a "
        "double-click to the `ui` subcommand; this guard has lost the second "
        "half of the path it guards"
    )
    end = source.find("\ndef ", start + 1)
    return source[start:end if end != -1 else len(source)]


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


def test_it_proves_a_SERVER_came_up_and_not_only_that_three_lines_printed(bare_run):
    r"""THE 0.3.0 DEFECT, AND THE SECOND TIME THIS GATE STOPPED ONE LINE SHORT.

    The three steps above are all printed BEFORE the app is built. `_cmd_ui`
    announces nothing until `create_app` has RETURNED — the static mount, both
    template environments and the job worker are all inside it — so a build that
    is missing a file the runtime opens prints every line this gate demanded and
    then dies. Measured on the published `engine-v0.3.0`, on the owner's machine:

        [3/3] Starting the engine...
        error: Directory '...\_MEI000036d42\scrapex\webui\static' does not exist

    `packaging/build_engine.py` named `db` and `sources.yaml`; the runtime opens
    five things (`RUNTIME_DATA` is the list now, and
    `tests/test_the_frozen_engine_carries_its_own_files.py` is what keeps it
    complete). But the reason it REACHED a user is here: the gate's last demand
    sat on the wrong side of the only call that can fail.

    So the property is not "demand this sentence" — it is **demand something
    printed after `create_app` returns**. Located by index in `_cmd_ui`'s own
    source, so renaming the line moves this check with it instead of breaking it.
    """
    body = ui_command()
    built = body.find("create_app(")
    assert built != -1, (
        "scrapex/cli.py:_cmd_ui no longer calls create_app; this guard's whole "
        "notion of 'after the app exists' has to be rewritten with it"
    )
    after = {
        message.group("text")
        for message in re.finditer(r'print\(f?"(?P<text>[^"{]+)', body[built:])
    }
    demanded = [m.group("pattern") for m in GREPPED.finditer(bare_run)]
    proves_a_server = [
        line for line in demanded
        if any(line in printed for printed in after)
    ]
    assert proves_a_server, (
        "every line the double-click gate demands is printed BEFORE create_app, "
        "so an engine that unpacks, opens its warehouse and then cannot build an "
        f"app passes this release. Nothing demanded is one of {sorted(after)}"
    )


def _printing_statement(source: str, at: int) -> str | None:
    """The `print(...)` or `_say(...)` call that produces the text at `at`.

    Sliced by matching parentheses rather than by line, because the call that
    matters here spans lines and a line-based read would miss the keyword sitting
    on the next one.
    """
    opened = max(source.rfind("print(", 0, at), source.rfind("_say(", 0, at))
    if opened == -1:
        return None
    depth, cursor = 0, source.index("(", opened)
    for index in range(cursor, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                return source[opened:index + 1]
    return None


def test_every_line_the_gate_demands_is_FLUSHED_because_the_engine_is_killed(
        bare_run, double_click_path):
    """A WORKING FIRST RUN IS KILLED, SO AN UNFLUSHED LINE IS NEVER WRITTEN.

    This is not a style point, and it very nearly shipped as a gate that failed
    every GOOD release. `_first_run` never returns — the window being open is the
    same fact as the engine being up — so the release step bounds it with
    `timeout` and reads the output. Python block-buffers stdout when it is a pipe,
    which is exactly what `spoke=$(...)` makes it, and a killed process never
    flushes. Measured on the source, on a server that had started perfectly:

        timeout 20 python -m scrapex.cli ui --no-open --port 8131 2>&1
        -> ZERO BYTES captured

    The same command with `flush=True` on that one line returns it. So the
    property a demanded line must have is not "something prints it" but
    "something prints it AND flushes" — `packaging/engine_entry.py:_say` exists
    for this and says so; anything outside it has to ask.
    """
    demanded = [m.group("pattern") for m in GREPPED.finditer(bare_run)]
    assert "flush=True" in ENTRY.read_text(encoding="utf-8"), (
        "packaging/engine_entry.py:_say no longer flushes, and every line the "
        "release gate demands of a double-click goes through it"
    )
    unflushed = []
    for line in demanded:
        found = [
            statement
            for index in _occurrences(double_click_path, line)
            if (statement := _printing_statement(double_click_path, index))
        ]
        if not any("_say(" in s or "flush=True" in s for s in found):
            unflushed.append(line)
    assert not unflushed, (
        f"the release demands {unflushed} of the built engine, and nothing on the "
        "double-click path prints them with a flush. A working first run is KILLED "
        "by `timeout` rather than allowed to exit, so a block-buffered line is "
        "never written to the pipe and this gate would refuse every good release"
    )


def _occurrences(source: str, needle: str) -> list[int]:
    found, at = [], source.find(needle)
    while at != -1:
        found.append(at)
        at = source.find(needle, at + 1)
    return found


# ---- the gate that asks for a page ------------------------------------------
# `OP-69`. Everything above judges what the engine PRINTED. An engine missing
# `scrapex/webui/templates` prints all of it and cannot render one page, because
# `Jinja2Templates` does not check its directory at construction the way
# `StaticFiles` does -- which is the only reason the 0.3.0 defect was loud.

#: The template every page extends. The marker the workflow greps for has to be
#: in HERE, or the grep is unfalsifiable and the gate is decoration.
BASE_TEMPLATE = ROOT / "scrapex" / "webui" / "templates" / "base.html"


def test_the_release_asks_the_built_engine_for_a_page(serve_run):
    """THE QUESTION THE OWNER ASKS THE ENGINE, asked by the release first.

    `curl -f` is the point rather than a flag: without it curl exits 0 on a 500
    and writes the error body to the file, so every content check below would run
    against an error page and could still pass.
    """
    # EVERY curl, not "a curl somewhere in the step". Found by mutation: dropping
    # `-f` from the PAGE fetch left `-f` on the ASSET fetch, and a substring test
    # passed while an HTTP 500 had become a release-passing answer.
    fetches = [c for c in CURL.finditer(_commands(serve_run))]
    assert fetches, "the step never fetches anything"
    unguarded = [c.group(0).strip() for c in fetches if not FAIL_ON_ERROR.search(c.group("flags"))]
    assert not unguarded, (
        f"these fetches do not use `curl -f`: {unguarded}. Without it curl exits "
        "0 on a 500 and writes the error body to the output file, so every "
        "content check below runs against an error page and can still pass"
    )
    # THE ROOT, specifically, and not merely "some URL on that port". Found by
    # mutation: deleting the page fetch while keeping the asset fetch left a curl
    # at `127.0.0.1:8000/static/tokens.css`, which satisfied a check for the port
    # and left the gate greping a `page.html` nothing had written. The root is the
    # page a person opens, and it is the one that proves a TEMPLATE rendered.
    assert any(re.search(r"127\.0\.0\.1:8000/[\"'\s]", c.group(0)) for c in fetches), (
        "nothing fetches http://127.0.0.1:8000/ itself. A static asset is served "
        "by StaticFiles and proves nothing about Jinja2 — only the root proves a "
        "template rendered, which is the entire hole this step exists to close"
    )


def test_a_200_is_not_enough_and_the_step_knows_it(serve_run):
    """AN ERROR PAGE IS A 200. So the gate must look at what came back.

    This is the same lesson as `test_a_silent_first_run_is_refused` one layer on:
    there, an exit code could not tell a working engine from a black window; here,
    a status code cannot tell a rendered app from a stack trace.
    """
    demanded = [m.group("pattern") for m in GREPPED.finditer(serve_run)]
    assert demanded, (
        "the step accepts any 200 at all. A `TemplateNotFound` page, a redirect "
        "notice and the app shell are all 200s, and only one of them means the "
        "engine works"
    )


def test_every_marker_it_demands_is_really_in_the_template(serve_run):
    """THE GUARD MUST NOT DRIFT FROM THE THING IT GUARDS.

    A marker nobody renders fails every release for a reason that has nothing to
    do with the engine; a marker loosened to something trivially true stops
    guarding anything. Both kinds of drift become this one failure -- the same
    shape as `test_every_line_it_demands_is_one_the_double_click_actually_prints`,
    pointed at the template instead of at the print statements.
    """
    assert BASE_TEMPLATE.is_file(), (
        f"{BASE_TEMPLATE} is gone; the release greps a page for a marker that "
        "was supposed to come from it"
    )
    shell = BASE_TEMPLATE.read_text(encoding="utf-8")
    demanded = [m.group("pattern") for m in GREPPED.finditer(serve_run)]
    missing = [marker for marker in demanded if marker not in shell]
    assert not missing, (
        f"the release demands {missing} of the page the engine serves, and "
        f"nothing in {BASE_TEMPLATE.name} renders it. Either the template was "
        "renamed and this gate now fails every good release, or the marker was "
        "loosened and it no longer proves a template rendered at all"
    )


def test_it_proves_the_static_mount_carries_BYTES_not_just_a_directory(serve_run):
    """`StaticFiles` is satisfied by an empty directory. The panel is not.

    The 0.3.0 defect was a missing directory, which raised. A directory present
    and empty raises nothing at all: the engine starts, `/static/...` answers 404
    per file, and every page renders unstyled. Asking for one real asset and
    requiring real bytes is what separates the two.
    """
    # A FETCH, not a mention. Found by mutation: deleting the asset fetch left the
    # words `/static/tokens.css` behind in the REFUSED message below it, and a
    # substring test read that as the check still being there.
    assert any("/static/" in c.group(0) for c in CURL.finditer(_commands(serve_run))), (
        "nothing FETCHES a static asset — naming one in an error message is not "
        "asking for it — so a bundle whose static directory exists and is empty "
        "passes the whole release"
    )
    assert re.search(r"-lt\s+\d+", serve_run), (
        "the static asset is fetched and its size is never judged, so a "
        "zero-byte or truncated file is a pass"
    )


def test_the_page_gate_bounds_itself_and_makes_its_own_warehouse(serve_run):
    """The same two disciplines the double-click step already carries.

    BOUNDED, because this step starts an engine that never returns on purpose and
    must not hang the release; the `timeout` sits inside the background job so the
    engine dies on its own even if the kill fails.

    ITS OWN DATA ROOT, because a first run CREATES and MIGRATES a database. This
    step is also what a person reaches for when reproducing a release locally, and
    there it would open the owner's real warehouse.
    """
    assert "timeout " in _commands(serve_run), (
        "nothing bounds the served engine; a first run that works never returns, "
        "so this step would hang the release rather than gate it"
    )
    assert re.search(r"SCRAPEX_DATA_ROOT\s*=", _commands(serve_run)), (
        "the page gate runs against the default data root, so it opens — and "
        "migrates — whatever warehouse the machine already has"
    )
    # ASKED OF THE CODE, NOT OF THE PROSE. Found by mutation, and it is the third
    # time in this one change that a substring belonging to a comment satisfied a
    # check about a command: deleting the `kill` left the words "even if the kill
    # below fails" in the comment above it, and `kill\s` matched that happily.
    assert re.search(r"kill\s", _commands(serve_run)), (
        "the engine is never stopped; the runner would carry a listening engine "
        "into every later step, which is a release job leaking a server"
    )


def test_the_two_gates_cannot_be_collapsed_into_one(bare_run, serve_run):
    """They are separate for a MECHANICAL reason, not a stylistic one.

    Reading a process's output means waiting for it to end. Talking to it over
    HTTP means it must still be running. One step cannot do both to one process —
    and a session tidying the workflow by merging them would silently lose
    whichever half it wrote second.
    """
    assert bare_run != serve_run
    assert "$(" in bare_run, (
        "the double-click step no longer CAPTURES the engine's output, which is "
        "the only evidence separating a working engine from a black window"
    )
    assert serve_run.rstrip().count("&\n") or "&" in serve_run, (
        "the page gate does not background the engine, so it cannot be running "
        "while the fetch happens"
    )
