"""Every job in ci.yml gives up on its own, long before GitHub's six hours.

A job with no `timeout-minutes` runs until GitHub cancels it at 360 minutes. On main
the ruleset requires `scope`, `lint`, `test` and `contract-parity` to pass, strictly
up to date, with nobody on the bypass list -- so one hung required job holds its pull
request for six hours and nothing can merge past it. The engine suite spawns real
subprocesses and drives a real Chromium, and nothing else bounds either (#948).

WHY 1..60. A value that is not an integer cannot be read here, and `true` is refused
even though Python calls a bool an int. Zero bounds nothing. The ceiling is twice
`test`'s 30 and a sixth of the default: a job that needs more than an hour has changed
shape, and its cap is argued again rather than raised past the point where it still
bounds anything.

NO MARK, deliberately. The one subject is ci.yml, and a change to `.github/` always
takes the full scope (the `.github/` paragraph in ci.yml's `scope` job), so the docs
and extension tiers can never be the only run that sees ci.yml change.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

LEAST, MOST = 1, 60


def _jobs() -> dict:
    """ci.yml's `jobs:` mapping, with its shape asserted rather than assumed.

    A reader that finds no jobs makes the guard below pass over nothing, so an
    empty or missing mapping is a failure here, not an empty loop.
    """
    parsed = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"{CI.name} did not parse to a mapping: {parsed!r}"
    jobs = parsed.get("jobs")
    assert isinstance(jobs, dict) and jobs, f"{CI.name} has no `jobs:` mapping: {jobs!r}"
    for name, job in jobs.items():
        assert isinstance(job, dict), f"{CI.name} job {name!r} is not a mapping: {job!r}"
    return jobs


def _problem(job: dict) -> str | None:
    """What is wrong with this job's cap, or None if it bounds the job."""
    if "timeout-minutes" not in job:
        return "no timeout-minutes, so GitHub's default of 360 applies"
    value = job["timeout-minutes"]
    # `type() is`, not isinstance: YAML reads `true` as a bool, and a bool is an int.
    if type(value) is not int:
        return f"timeout-minutes is {value!r}, not an integer"
    if not LEAST <= value <= MOST:
        return f"timeout-minutes is {value}, outside {LEAST}..{MOST}"
    return None


def test_every_ci_job_declares_a_timeout_between_one_and_sixty_minutes():
    """THE GUARD. A missing, zero, non-integer or six-hour cap names its job."""
    wrong = [f"{name}: {problem}" for name, job in _jobs().items()
             if (problem := _problem(job))]

    assert not wrong, (
        f"every job in {CI.name} needs `timeout-minutes:` directly under its "
        f"`runs-on:`, an integer from {LEAST} to {MOST}, or a hung job holds its "
        "pull request until GitHub cancels it at six hours (#948):\n  "
        + "\n  ".join(wrong))


@pytest.mark.parametrize("job", [
    pytest.param({"runs-on": "ubuntu-latest"}, id="missing"),
    pytest.param({"timeout-minutes": None}, id="empty"),
    pytest.param({"timeout-minutes": 0}, id="zero"),
    pytest.param({"timeout-minutes": -5}, id="negative"),
    pytest.param({"timeout-minutes": MOST + 1}, id="one-past-the-ceiling"),
    pytest.param({"timeout-minutes": 360}, id="the-default"),
    pytest.param({"timeout-minutes": True}, id="a-bool"),
    pytest.param({"timeout-minutes": "30"}, id="a-string"),
    pytest.param({"timeout-minutes": "${{ inputs.minutes }}"}, id="an-expression"),
    pytest.param({"timeout-minutes": 30.0}, id="a-float"),
])
def test_a_cap_that_bounds_nothing_is_refused(job):
    """The error path of the guard, one shape at a time, so a check that stopped
    refusing one -- `isinstance` letting `True` through, a bound written `<` --
    fails here rather than waving a real one past."""
    assert _problem(job) is not None


@pytest.mark.parametrize("minutes", [LEAST, 5, 30, MOST])
def test_a_cap_inside_the_bounds_is_accepted(minutes):
    """And the happy path, including both edges, so the bounds are inclusive."""
    assert _problem({"runs-on": "ubuntu-latest", "timeout-minutes": minutes}) is None
