"""The four jobs main's ruleset requires cannot be switched off or hollowed out.

Ruleset 23994761 requires four check contexts on main -- `scope`, `lint`, `test`
and `contract-parity` -- and pins nothing but their NAMES. What each one runs is
decided by the pull request's own `ci.yml`, because a `pull_request` run executes
the workflow from the PR's merge commit, and a job skipped by a job-level `if:`
reports Success, which satisfies a required check (GitHub docs, "Using conditions
to control job execution").

MEASURED BEFORE THIS FILE EXISTED, BY MUTATION (#1132). `if: false` on any of the
four jobs, `ruff check scrapex/ --exit-zero`, eslint with `|| true`, the parity
gate or either `node --test` line replaced by `true`: every one of them left every
test that reads a workflow green.

THIS FILE RUNS IN TWO JOBS, AND THAT IS THE MECHANISM. A copy runs inside `test`
in every scope -- hence both marks below -- and a copy runs as the last step of
`lint`, which depends on nothing. A job-level `if: false` on `lint` is caught by
the copy in `test`; one on `scope` (which skips `test` with it), `test` or
`contract-parity` by the copy in `lint`. Switching both off takes two edits, and
the lint step is pinned below, so the first of those two fails on its own.

WHAT IT DOES NOT PIN, ON PURPOSE: the full step list or key set of any job. Steps
and `timeout-minutes` get added for reasons of their own, and a test that failed
on every one of them would be a test people learn to update without reading. It
pins what a one-line edit could use to make a required check report green while
checking nothing: a job-level `if` or `continue-on-error`, a step's
`continue-on-error`, a condition on a step that does the work, the command that
does it, the graph between the jobs, an environment that turns every pytest run
into a collection, a shell that ignores its script, and a second job claiming
one of the names.

IT NEEDS NOTHING BUT PYTEST AND PYYAML, because `lint` installs nothing else and
runs it with `--noconftest`. `yaml` is IMPORTED, not importorskip'd: a guard that
skipped when its parser was missing would report green in exactly the job that
exists to notice the others going quiet.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

# BOTH MARKS, AND BOTH CARRY WEIGHT. `docs` puts this file in every scope the
# `test` job can choose -- `-m docs`, `-m "extension or docs"` and the whole suite
# -- so the copy there runs whatever `scope` decided. `extension` because the file
# names extension/, and tests/test_the_extension_gate_is_complete.py requires the
# mark of every file that does.
pytestmark = [pytest.mark.extension, pytest.mark.docs]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"

#: THE FOUR CONTEXTS RULESET 23994761 REQUIRES ON main, by job id, held here once.
#: Renaming one leaves a context that never reports, and a required check that
#: never reports blocks every pull request -- the order a rename takes is in the
#: comment above `jobs:` in ci.yml.
REQUIRED_JOBS = ("scope", "lint", "test", "contract-parity")

#: The graph as it is today. `lint` depending on nothing is what lets its copy of
#: this file run when `scope` is switched off, and `test` reads the scope it runs
#: from `scope`'s output.
NEEDS = {"scope": [], "lint": [], "test": ["scope"], "contract-parity": []}

#: How `test` learns its scope: the `scope` job's output, written by the step with
#: this id. Skipped, that step writes nothing, every scoped step in `test` sees an
#: empty scope, all four skip, and the job reports green having run no suite.
SCOPE_STEP_ID = "scope"
SCOPE_OUTPUT = "${{ steps.scope.outputs.scope }}"

#: The steps `lint` and `contract-parity` exist to run, each compared WHOLE, line
#: by line with whitespace collapsed. Whole, because `ruff check scrapex/
#: --exit-zero` still contains `ruff check scrapex/`, and a substring was all the
#: lint gate's own test asked for until #1132.
RUFF = "ruff check scrapex/"
ESLINT = ("npx --yes eslint@9.39.0 extension scrapex/webui/static contract "
          "apps_script --no-warn-ignored")
THIS_FILE_IN_LINT = (
    "pip install pytest==9.1.1 pyyaml==6.0.3\n"
    f"python -m pytest --noconftest -p no:cacheprovider tests/{Path(__file__).name} -q")
PINNED_RUNS = {
    "lint": (RUFF, ESLINT, THIS_FILE_IN_LINT),
    "contract-parity": (
        "node contract/parity/parity.test.mjs",
        "node --test extension/tests/*.test.mjs",
        "node --test apps_script/tests/*.test.mjs",
    ),
}

#: `test`'s step-level conditions, each beside the pytest line of the step that
#: carries it, so that moving a condition to another step fails as surely as
#: deleting it. The LINE is compared rather than the whole step: the whole-suite
#: step also prints the runner's size, and the template step carries its own floor,
#: which tests/test_the_real_migration_stream_is_replayed_in_ci.py pins.
SCOPED_TEST_STEPS = (
    ("needs.scope.outputs.scope == 'docs'", "python -m pytest -m docs"),
    ("needs.scope.outputs.scope == 'extension'", 'python -m pytest -m "extension or docs"'),
    ("needs.scope.outputs.scope == 'full'", "python -m pytest -n 2 --dist loadfile"),
    ("needs.scope.outputs.scope == 'full'",
     "python -m pytest tests/test_fast_migrations.py --junitxml=/tmp/fast.xml"),
)

#: The one-token ways to make a failing command exit 0. A step compared whole
#: cannot carry one; this reaches the steps compared by a line and the steps not
#: pinned at all. `scope` is left out because its script uses `|| true` on
#: purpose: a failed `git fetch` there must fall through to the full suite.
NEUTRALISED = re.compile(
    r"--exit-zero|\|\|\s*(?:true\b|:(?![\w-]))|;\s*true\b"
    r"|\bset\s+\+[a-z]*e|\bset\s+\+o\s+errexit\b|\bexit\s+0\b")
NEUTRALISER_FREE_JOBS = ("lint", "test", "contract-parity")

#: One line of environment hollows every pytest run in the workflow at once, BOTH
#: copies of this file included: `PYTEST_ADDOPTS: --collect-only` runs nothing and
#: exits 0. Measured with pytest 9.1.1 on a test that always fails. (Not
#: PYTHONOPTIMIZE: pytest rewrites a test module's asserts into raises, and the
#: same probe still failed under it.)
HOLLOWING_ENV = "PYTEST_ADDOPTS"


def ci_workflow() -> dict:
    """ci.yml, parsed, or a failure that says the reader went blind."""
    parsed = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict) and isinstance(parsed.get("jobs"), dict), (
        "ci.yml no longer parses to a mapping with a `jobs:` mapping in it, so "
        "nothing below would be reading the workflow the ruleset relies on")
    return parsed


def ci_jobs() -> dict:
    return ci_workflow()["jobs"]


def steps_of(job: dict) -> list[dict]:
    steps = job.get("steps")
    assert isinstance(steps, list) and steps and all(isinstance(s, dict) for s in steps), (
        f"expected a non-empty list of step mappings, found {steps!r}")
    return steps


def lines(run: object) -> str:
    """A `run:` block, each line's whitespace collapsed, blank lines dropped.

    Line by line rather than one collapsed string, because a newline is a command
    separator in the shell and a space is not.
    """
    return "\n".join(" ".join(line.split())
                     for line in str(run or "").splitlines() if line.strip())


def runs_of(job: dict) -> list[str]:
    return [lines(step["run"]) for step in steps_of(job) if "run" in step]


def _condition(step: dict) -> str:
    return " ".join(str(step["if"]).split())


def _needs(job: dict) -> list[str]:
    needs = job.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


@pytest.fixture(scope="module")
def jobs() -> dict:
    return ci_jobs()


@pytest.mark.parametrize("name", REQUIRED_JOBS)
def test_each_required_job_exists_and_reports_under_its_own_name(jobs, name):
    """A missing job is a context that never reports; a `name:` renames it."""
    assert isinstance(jobs.get(name), dict), (
        f"ci.yml has no `{name}` job. Ruleset 23994761 requires that context, so "
        "it now never reports and every pull request waits on it. Renaming a "
        "required job goes in the order the comment above `jobs:` gives.")
    assert jobs[name].get("name", name) == name, (
        f"`{name}` carries `name: {jobs[name].get('name')}`, and a job reports "
        "under its name, not its id -- the required context is gone.")


@pytest.mark.parametrize("name", REQUIRED_JOBS)
def test_no_required_job_can_be_skipped_or_excused_as_a_whole(jobs, name):
    """A skipped job reports Success, and a required check accepts it."""
    for key in ("if", "continue-on-error"):
        assert key not in jobs[name], (
            f"`{name}` carries a job-level `{key}: {jobs[name][key]!r}`. A job "
            "skipped by `if` reports Success and `continue-on-error` turns its "
            "failure into one; either satisfies ruleset 23994761 while nothing "
            "in the job answers.")


@pytest.mark.parametrize("name", REQUIRED_JOBS)
def test_no_step_in_a_required_job_is_excused_from_failing(jobs, name):
    excused = [step.get("name") or step.get("uses") or step.get("run")
               for step in steps_of(jobs[name]) if "continue-on-error" in step]
    assert not excused, (
        f"these steps in `{name}` carry `continue-on-error`, so their failure "
        f"leaves the required check green: {excused}")


@pytest.mark.parametrize("name", REQUIRED_JOBS)
def test_the_graph_between_the_four_is_what_the_two_copies_rely_on(jobs, name):
    assert _needs(jobs[name]) == NEEDS[name], (
        f"`{name}` needs {_needs(jobs[name])}, and it needed {NEEDS[name]}. A "
        "skipped job skips everything that needs it, so a dependency added to "
        "`lint` would let one `if: false` switch off both copies of this file.")


def test_the_scope_reaches_test_from_a_step_that_always_runs(jobs):
    scope = jobs["scope"]
    assert (scope.get("outputs") or {}).get("scope") == SCOPE_OUTPUT, (
        f"the `scope` job's `scope` output is no longer {SCOPE_OUTPUT!r}, so "
        "`test` no longer runs the suite the change calls for")
    found = [step for step in steps_of(scope) if step.get("id") == SCOPE_STEP_ID]
    assert len(found) == 1, (
        f"expected exactly one step with `id: {SCOPE_STEP_ID}` in `scope`, found "
        f"{len(found)}")
    assert "if" not in found[0], (
        f"the step that writes the scope carries `if: {found[0]['if']!r}`. Skipped, "
        "it writes nothing, every scoped step in `test` skips, and `test` reports "
        "green having run no suite at all.")


@pytest.mark.parametrize("name,command", [
    (name, command) for name, commands in PINNED_RUNS.items() for command in commands])
def test_each_gate_runs_exactly_its_command_and_unconditionally(jobs, name, command):
    found = [step for step in steps_of(jobs[name]) if lines(step.get("run")) == command]
    assert len(found) == 1, (
        f"`{name}` should run, as one whole step, exactly:\n    "
        + command.replace("\n", "\n    ")
        + f"\nand {len(found)} steps do. Its runs are now:\n    "
        + "\n    ".join(r.replace("\n", " \\n ") for r in runs_of(jobs[name]))
        + "\nA command with `--exit-zero` or `|| true` on it, or replaced by "
          "`true`, still reports the required check green. If the command itself "
          "is meant to change, change it here in the same pull request.")
    assert "if" not in found[0], (
        f"the step in `{name}` that runs `{command.splitlines()[-1]}` carries "
        f"`if: {found[0]['if']!r}`; skipped, it leaves the job green")


def test_the_conditions_in_test_are_exactly_the_scope_tiers(jobs):
    """`if: false` on any step, or a tier's condition on a floor, fails here."""
    found = Counter(_condition(step) for step in steps_of(jobs["test"]) if "if" in step)
    expected = Counter(condition for condition, _ in SCOPED_TEST_STEPS)
    assert found == expected, (
        f"the step-level conditions in `test` are {dict(found)}, and they were "
        f"{dict(expected)}. A new condition is a step that can skip while the "
        "required check stays green.")


@pytest.mark.parametrize("condition,command", SCOPED_TEST_STEPS)
def test_each_scope_tier_still_runs_its_suite(jobs, condition, command):
    found = [step for step in steps_of(jobs["test"])
             if "if" in step and _condition(step) == condition
             and command in lines(step.get("run")).splitlines()]
    assert len(found) == 1, (
        f"expected exactly one step in `test` under `if: {condition}` running "
        f"`{command}`, found {len(found)}. Replaced by `true`, or moved off its "
        "condition, the tier stops running that suite while `test` stays green.")


@pytest.mark.parametrize("name", NEUTRALISER_FREE_JOBS)
def test_no_step_turns_a_failure_into_exit_zero(jobs, name):
    neutralised = [run for run in runs_of(jobs[name]) if NEUTRALISED.search(run)]
    assert not neutralised, (
        f"these runs in `{name}` carry `--exit-zero`, `|| true`, `; true`, "
        "`set +e` or `exit 0`, so a failure inside them reports green:\n    "
        + "\n    ".join(neutralised))


def test_no_environment_turns_every_pytest_run_into_a_collection():
    workflow = ci_workflow()
    places = [("the workflow's `env`", workflow.get("env"))]
    for name in REQUIRED_JOBS:
        job = workflow["jobs"][name]
        places.append((f"`{name}`'s `env`", job.get("env")))
        for step in steps_of(job):
            label = step.get("name") or step.get("uses") or "a step"
            places.append((f"`{name}` :: {label} `env`", step.get("env")))
            # `run:` too, which is how `>> $GITHUB_ENV` or an inline assignment
            # would set it for every step after.
            places.append((f"`{name}` :: {label} `run`", step.get("run")))
    found = [where for where, value in places if HOLLOWING_ENV in str(value or "")]
    assert not found, (
        f"{HOLLOWING_ENV} is set in {found}. `{HOLLOWING_ENV}: --collect-only` "
        "turns every pytest run below it into a collection that exits 0, both "
        "copies of this file included.")


def test_no_shell_is_chosen_for_the_steps_that_do_the_work():
    """A custom shell decides what a `run:` block is handed to, and `true {0}` is one.

    GitHub runs the first word of a `shell:` template with the script's path at
    `{0}` (docs, "Workflow syntax", custom shell), so `shell: true {0}` exits 0
    without reading the script, and under `defaults:` at workflow level it does so
    for every step of every job, both copies of this file included. None of the
    four sets a shell today; every step gets the runner's default.
    """
    workflow = ci_workflow()
    found = ["the workflow"] if "defaults" in workflow else []
    for name in REQUIRED_JOBS:
        job = workflow["jobs"][name]
        found += [f"`{name}`"] if "defaults" in job else []
        found += [f"`{name}` :: {step.get('name') or step.get('run')}"
                  for step in steps_of(job) if "shell" in step]
    assert not found, (
        f"a `defaults:` or `shell:` is set on {found}. It chooses what every `run:` "
        "under it is handed to, and a shell that ignores its script reports each "
        "step green without running it.")


def test_no_other_job_answers_to_a_required_name():
    """A second check run with a required name can report in the real one's place."""
    files = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    # A reader that finds no workflows passes over nothing -- absence is asserted.
    assert CI in files and len(files) >= 2, (
        f"expected ci.yml and the other workflows under {WORKFLOWS}, found "
        f"{[p.name for p in files]}")

    claims = []
    for path in files:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict) and isinstance(parsed.get("jobs"), dict), (
            f"{path.name} does not parse to a workflow with a `jobs:` mapping")
        for job_id, job in parsed["jobs"].items():
            if path == CI and job_id in REQUIRED_JOBS:
                continue    # the four themselves, whose names the first test pins
            name = job.get("name") if isinstance(job, dict) else None
            for claimed in {job_id, name} & set(REQUIRED_JOBS):
                claims.append(f"{path.name} :: {job_id} answers to {claimed!r}")

    assert not claims, (
        "these jobs report under a context ruleset 23994761 requires, so either "
        "one can satisfy it for the other:\n  " + "\n  ".join(claims))
