"""The extension tier runs in the full suite's worker shape, taken from one value.

`XDIST_ARGS`, on ci.yml's `test` job, is how a tier that runs the browser suites
spreads over the runner. The full suite and the extension tier both read it, so the
tier a panel change waits on cannot slide back to serial -- where it sat, written
before xdist existed and never revisited -- or onto a worker count the suite has
stopped using.

WHAT THIS FILE PINS. Each was broken on purpose and went red before it was trusted:

  1. the extension step drops `$XDIST_ARGS`          -- it runs serial again
  2. the extension step writes its own `-n`          -- a second copy that drifts
  3. the whole-suite step drops `$XDIST_ARGS`        -- the suite runs serial
  4. a step sets its own `XDIST_ARGS` in `env:`      -- it silently runs another shape
  5. `XDIST_ARGS` loses its count, goes `auto`, or loses `--dist loadfile`

IT PINS THE SHAPE, NOT THE NUMBER. Asserting `-n 3` here would make this file a
second copy of the value it guards, and the next change to the runner would have
to be made twice. The count is `ci.yml`'s decision; this file only asserts that
there is exactly one place making it.

The docs tier is deliberately not held to it: it runs in seconds, and the most anyone
has measured for parallelising it is a few of them (#943).
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

from tests.test_the_real_migration_stream_is_replayed_in_ci import (
    _pytest_args,
    _whole_suite_step,
)

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
VAR = "XDIST_ARGS"
# `$XDIST_ARGS`, `${XDIST_ARGS}` in the shell, or `${{ env.XDIST_ARGS }}` from Actions.
REFERENCE = re.compile(
    r"\$\{\{\s*env\.XDIST_ARGS\s*\}\}|\$\{XDIST_ARGS\}|\$XDIST_ARGS(?![A-Za-z0-9_])")
# Every spelling pytest-xdist accepts for the two options this value owns.
OWN_OPTIONS = re.compile(r"(?<!\S)(-n\S*|--numprocesses\S*|--dist\S*|-d)(?=\s|$)")


@pytest.fixture(scope="module")
def job() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["test"]


def _first_command(args: str) -> str:
    """The first logical line after `pytest`, with backslash continuations joined.

    NOT THE FIRST PHYSICAL LINE: the pre-squash step's command ends its first line
    with `\\`, and `shlex` refuses a dangling escape -- which is how the first
    version of this reader failed on a step it had no business parsing.
    """
    joined = re.sub(r"\\\r?\n", " ", args.strip())
    return joined.splitlines()[0] if joined else ""


def _extension_tier_step(job: dict) -> dict:
    """The step that RUNS the extension-marked tests, not the ones that count them.

    `ci.yml` also runs `-m extension --collect-only` to prove the set has not
    emptied; that one collects and runs nothing, so it has no workers to spread.
    """
    found = []
    for step in job["steps"]:
        args = _pytest_args(step)
        if args is None or "--collect-only" in args:
            continue
        command = _first_command(args)
        if not re.search(r"(?<!\S)-m(?=[ =])", command):
            continue
        tokens = shlex.split(command)
        expressions = [tokens[i + 1] for i, token in enumerate(tokens[:-1])
                       if token == "-m"]
        if any(re.search(r"\bextension\b", expression) for expression in expressions):
            found.append(step)
    assert len(found) == 1, (
        f"expected exactly one step in ci.yml's `test` job that runs the extension "
        f"tier, found {len(found)}: {[s.get('name') for s in found]}. A reader "
        "that matches nothing would make every assertion below vacuous.")
    return found[0]


def _shape(value: str) -> tuple[int, str]:
    """`-n 3 --dist loadfile` -> (3, "loadfile"), whichever spelling is used."""
    tokens = shlex.split(value)
    count = mode = None
    for i, token in enumerate(tokens):
        following = tokens[i + 1] if i + 1 < len(tokens) else None
        if token in ("-n", "--numprocesses"):
            count = following
        elif token.startswith("--numprocesses="):
            count = token.split("=", 1)[1]
        elif token.startswith("-n") and len(token) > 2:
            count = token[2:]
        elif token in ("--dist", "-d"):
            mode = following
        elif token.startswith("--dist="):
            mode = token.split("=", 1)[1]
    assert count is not None, f"{VAR}={value!r} names no worker count at all"
    assert count.isdigit(), (
        f"{VAR}={value!r} asks for {count!r} workers. It must be a number: `auto` "
        "follows the machine, so a contributor on 24 cores would run a shape CI "
        "never runs and meet failures nobody else can reproduce.")
    return int(count), mode


def test_the_job_holds_one_worker_shape(job):
    """Mutation 5: the value itself stops describing a parallel, file-whole run."""
    value = (job.get("env") or {}).get(VAR)
    assert value, (
        f"ci.yml's `test` job no longer defines {VAR}, so the steps that read it "
        "run with no workers and no dist mode -- serial, with nothing in either "
        "step's text to say so.")

    count, mode = _shape(str(value))
    assert count >= 2, (
        f"{VAR} asks for {count} worker(s). One worker is the serial suite with "
        "xdist's startup cost added on top.")
    assert mode == "loadfile", (
        f"{VAR} uses `--dist {mode}`. `loadfile` keeps a file in one worker, so a "
        "module-scoped Chromium is launched once per file rather than once per "
        "worker -- the browser suites are built on that.")


@pytest.mark.parametrize("which", ["the extension tier", "the whole suite"])
def test_both_tiers_take_their_shape_from_it_and_nowhere_else(job, which):
    """Mutations 1 to 4, for each of the two steps that must share one shape."""
    step = (_extension_tier_step(job) if which == "the extension tier"
            else _whole_suite_step(job))
    args = _first_command(_pytest_args(step))

    assert REFERENCE.search(args), (
        f"the step running {which} ({step.get('name')!r}) does not pass "
        f"${VAR}, so it runs serial -- `pytest {args.strip()}`.")

    written_here = OWN_OPTIONS.findall(REFERENCE.sub(" ", args))
    assert not written_here, (
        f"the step running {which} writes {written_here} itself beside ${VAR}. "
        "That is a second copy of the worker shape: the next change to the runner "
        "gets made in one place and not the other.")

    assert VAR not in (step.get("env") or {}), (
        f"the step running {which} sets its own {VAR} in `env:`, so it runs a "
        "shape the job does not declare and nothing in the job's comment explains.")
