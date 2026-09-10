"""CI must replay the real migration stream, and exactly one step must not.

`#645` deleted the `migration-authority` job, which existed only to run the whole
suite a second time with `SCRAPEX_FULL_MIGRATIONS=1`. The guarantee did not go with
it: the flag moved onto the surviving suite step, so every pull request now
exercises the real stream instead of one job in two.

WHAT THIS FILE PINS, AND WHY NOTHING ELSE DOES. Three edits to `ci.yml` undo that
change and nothing goes red — measured, all three green across the 190 tests that
read a workflow:

  1. move the `env:` from the step to the job -- the seven tests in
     `tests/test_fast_migrations.py` then skip, because they are the tests of the
     TEMPLATE and the flag turns the template off. Their step's floor catches it in
     CI; this catches it at the edit.
  2. delete the template step -- those seven tests then run nowhere at all.
  3. delete the flag entirely -- CI silently goes back to testing against
     `tests/conftest.py`'s schema template and never replays the real stream again.
     This is the one that costs the most and shows the least.

`tests/test_the_two_release_paths.py:511` already holds the same knowledge for
`release-engine.yml`, as a substring check. A substring survives mutation 1, which
is the mutation `ci.yml`'s own comment calls load-bearing, so this reads the YAML.

KEYED ON SHAPE, NOT ON A COMMAND STRING. `#654` proposes `-n` for xdist and the
template step already carries `--junitxml`, so a test matching a literal `run:` line
would fail on an edit that changed nothing about the stream. The suite step is
identified as "the pytest invocation with no path and no marker filter", and asserted
to be unique -- a parser that matches nothing is the failure this repository keeps
finding, so absence is an assertion here rather than an empty loop.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

FLAG = "SCRAPEX_FULL_MIGRATIONS"
CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _run(step: dict) -> str:
    return str(step.get("run") or "")


def _effective_env(workflow: dict, job: dict, step: dict) -> dict:
    """What the step actually sees: workflow env, then job env, then step env."""
    env: dict = {}
    for scope in (workflow.get("env"), job.get("env"), step.get("env")):
        env.update(scope or {})
    return env


def _pytest_args(step: dict) -> str | None:
    """Everything after the first `pytest` in the step, or None if it runs none.

    Taken from AFTER the word `pytest` on purpose: `python -m pytest` carries a
    `-m` of its own, and a marker-filter check that reads the whole line matches
    that and excludes the whole suite -- which made every assertion in this file
    vacuous on the first attempt, and was found by printing the matches rather
    than by reading them.
    """
    found = re.search(r"\bpytest\b(.*)", _run(step), re.S)
    return found.group(1) if found else None


def _whole_suite_step(job: dict) -> dict:
    """The step that runs EVERY test: pytest, no path argument, no `-m` filter."""
    found = [s for s in job["steps"]
             if (args := _pytest_args(s)) is not None
             and "tests/" not in args
             and not re.search(r"(?<!\S)-m(?=[ =])", args)]
    assert len(found) == 1, (
        f"expected exactly one whole-suite pytest step in ci.yml's `test` job, "
        f"found {len(found)}: {[s.get('name') for s in found]}. Either the suite "
        "stopped running or this reader no longer describes the job -- and a "
        "reader that matches nothing would make every assertion below vacuous.")
    return found[0]


def _template_step(job: dict) -> dict:
    found = [s for s in job["steps"] if "test_fast_migrations.py" in _run(s)]
    assert len(found) == 1, (
        f"expected exactly one step running tests/test_fast_migrations.py, found "
        f"{len(found)}. Those seven tests are the only thing pinning the schema "
        "template, and they SKIP in the suite step because the flag is set there, "
        "so without this step they run nowhere.")
    return found[0]


def test_the_whole_suite_replays_the_real_migration_stream(workflow):
    """Mutation 3: delete the flag and CI tests against the template forever."""
    job = workflow["jobs"]["test"]
    step = _whole_suite_step(job)

    assert _effective_env(workflow, job, step).get(FLAG) == "1", (
        f"ci.yml's whole-suite step does not set {FLAG}=1, so CI runs against "
        "tests/conftest.py's schema template and never replays the real migration "
        "stream. That stream is what #645 kept when it deleted the job that used "
        "to replay it; without this the deletion is a coverage loss.")


def test_the_flag_is_scoped_to_that_step_and_no_wider(workflow):
    """Mutation 1: a job- or workflow-level env reaches the template step too."""
    job = workflow["jobs"]["test"]

    for where, env in (("workflow", workflow.get("env")), ("the `test` job", job.get("env"))):
        assert FLAG not in (env or {}), (
            f"{FLAG} is set at {where} level. It reaches every step, including the "
            "one that runs tests/test_fast_migrations.py, whose seven tests skip "
            "when it is set -- and `addopts` carries `-q`, so they would skip "
            "silently. The flag belongs on the whole-suite step alone.")


def test_something_still_runs_the_template_suite_without_the_flag(workflow):
    """Mutation 2: delete the template step and seven tests run nowhere."""
    job = workflow["jobs"]["test"]
    step = _template_step(job)

    assert FLAG not in _effective_env(workflow, job, step), (
        "the step that runs tests/test_fast_migrations.py sees "
        f"{FLAG}, so all seven of its tests skip and the schema template is "
        "pinned by nothing.")


def test_that_step_would_fail_rather_than_skip_quietly(workflow):
    """A step that reports green whether it ran or skipped is the #644 shape.

    Not a style point: the flag reaching this step is exactly what the test above
    forbids, and this is what notices if it happens anyway -- through `$GITHUB_ENV`,
    or a skip guard added to the file for some other reason.
    """
    step = _template_step(workflow["jobs"]["test"])
    run = _run(step)

    assert "--junitxml" in run, (
        "the template step trusts pytest's exit code, and pytest exits 0 when all "
        "seven tests skip. It needs the run's skip count, which means --junitxml.")
    assert "skipped" in run, (
        "the template step reads its JUnit XML but does not look at the skip count, "
        "which is the only thing that distinguishes seven passes from seven skips.")
    assert "assert " not in run, (
        "the floor is enforced with `assert`, which PYTHONOPTIMIZE strips -- see "
        "#833. Use `raise SystemExit` or shell `test`.")
