"""A job that runs pytest on a grafted clone turns two guards into silent skips.

WHY THIS FILE EXISTS, and it is the third time the same mistake has been made here.

Two tests in this suite ask git when something last really changed, and **both skip
rather than fail** when the clone has no history to ask:

  * `tests/test_the_privacy_policy_is_true.py:433` -- `_last_changed()` returns None
    on a shallow repository, so the "Last updated" staleness test skips. That guard
    was added on 2026-08-12 after the privacy policy was edited three times in one
    day while still advertising an older date, and the Chrome Web Store listing
    hangs on that document.
  * `tests/test_version.py:231` -- every capability's cited commit hash goes
    unchecked.

A skip is not a failure. Under `addopts = "-q --strict-markers"` a run full of them
reports **green**, so the loss is invisible in exactly the way a missing guard
always is.

THE HISTORY OF THIS MISTAKE:

  1. `publish-docs.yml` and `release-extension.yml` both ran this file at depth 1.
     Fixed, and the helper's own comment at
     `tests/test_the_privacy_policy_is_true.py:430` names them and says it "refuses
     to guess if one ever stops".
  2. `ci.yml`'s `test` job carried `fetch-depth: 0` -- but only because the scope
     diff needed it. When the scope computation moved into its own job on
     2026-08-19, the comment "Shallow is enough here now" went in with it and the
     history went away. An adversarial review caught it before it merged, by
     experiment: edit `docs/privacy-policy.md`, leave its date alone, and full
     history reports one failure while `--depth 1` reports green.

Nothing structural stopped (2) from happening after (1) was fixed, because the
reason lived in a comment on the file that NEEDED the history rather than on the
jobs that have to PROVIDE it. This test is that structure: it reads every workflow,
finds every job that runs pytest, and requires each one to fetch the whole history.
"""

from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

pytestmark = pytest.mark.docs

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _runs_pytest(job: dict) -> bool:
    return any("pytest" in str(step.get("run") or "")
               for step in (job.get("steps") or []))


def _checkout_depths(job: dict) -> list[object]:
    """`fetch-depth` from every actions/checkout step in this job.

    A job with no checkout has nothing to fetch and nothing to get wrong; a job
    with two checkouts has to get both right, so every one is reported.
    """
    depths = []
    for step in (job.get("steps") or []):
        if str(step.get("uses") or "").startswith("actions/checkout"):
            depths.append((step.get("with") or {}).get("fetch-depth", "<default>"))
    return depths


def _jobs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            continue
        for name, job in (parsed.get("jobs") or {}).items():
            if isinstance(job, dict):
                yield path.name, name, job


def test_every_job_that_runs_pytest_fetches_the_whole_history():
    """THE GUARD. `fetch-depth: 0`, or the two date guards skip and say nothing."""
    shallow = []
    for workflow, name, job in _jobs():
        if not _runs_pytest(job):
            continue
        for depth in _checkout_depths(job):
            if depth != 0:
                shallow.append(f"{workflow} :: {name} -- fetch-depth: {depth}")

    assert not shallow, (
        "these jobs run pytest on a clone with no history, so the guards at "
        "tests/test_the_privacy_policy_is_true.py:433 and tests/test_version.py:231 "
        "SKIP instead of running -- and a run full of skips reports green:\n  "
        + "\n  ".join(shallow)
        + "\n\nAdd to the checkout step:\n    with:\n      fetch-depth: 0")


def test_the_guards_this_protects_still_consult_git():
    """If they ever start FAILING on a shallow clone instead of skipping, this file
    is no longer load-bearing and should be re-argued rather than kept out of habit.
    If they stop consulting git at all, the same.

    A source check rather than a real shallow clone: making one inside a test costs
    seconds and a temp directory for a fact two lines of source state plainly.
    """
    for name in ("test_the_privacy_policy_is_true.py", "test_version.py"):
        source = (ROOT / "tests" / name).read_text(encoding="utf-8")
        assert "is-shallow-repository" in source, (
            f"{name} no longer asks whether the clone is shallow. Either it stopped "
            "consulting git history -- in which case this whole file can go -- or it "
            "now trusts a grafted clone, which is worse than skipping.")


def test_it_notices_a_job_that_runs_pytest_at_all():
    """A parser that silently matches nothing makes the guard above vacuous -- the
    failure mode this repository has hit more than once. `ci.yml` has jobs that run
    pytest by construction; if this finds none, the reader changed shape."""
    running = [f"{workflow}::{name}" for workflow, name, job in _jobs()
               if _runs_pytest(job)]

    assert len(running) >= 2, (
        f"only {len(running)} workflow jobs look like they run pytest ({running}). "
        "The step parser has probably stopped matching, which makes the guard above "
        "pass over nothing.")
