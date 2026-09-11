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


def test_this_checkout_has_not_grafted_itself():
    """The tests above make CI PROVIDE the history. This one says so when the machine
    running the suite has thrown it away, which CI can never see.

    A SHALLOW FETCH IS REPO-WIDE. `.git/shallow` sits beside the object store, and
    every worktree under `.claude/worktrees/` shares that store -- so one session
    fetching at depth 1, to see what a grafted clone does, grafts every other session
    too. Restoring the files it touched restores nothing: `git status` stays clean
    while `git rev-list --count HEAD` has collapsed.

    Measured 2026-09-10, after a review agent did exactly that. The branch fell from
    669 commits to 6, `git merge-base origin/main HEAD` answered nothing, and
    `git merge-tree` refused with "unrelated histories" -- a merge that needed
    `git fetch --unshallow` and a rebase to land. The two guards this file exists for
    went quiet in the same run: 23 skips where there had been 21, and both extra ones
    were "no git history here -- the comparison cannot be made".

    NOT A GIT REPOSITORY IS NOT THE SAME FAULT. A source export -- `git archive`, or a
    zip of the tree -- has no `.git` and no history to lose, so that skips. (Not a pip
    install: `pyproject.toml` includes only `scrapex*` and there is no MANIFEST.in, so
    no wheel or sdist carries this file at all.) A repository that HAS a graft is the
    one this catches, and it fails rather than skipping for the reason the docstring
    at the top of this file gives: a skip reports green.
    """
    import subprocess

    asked = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                           cwd=ROOT, capture_output=True, text=True)
    answer = asked.stdout.strip()

    # GIT SAYS WHY, SO SAY WHAT GIT SAID. This branch used to relabel every
    # non-zero exit "not a git checkout" while git's own sentence sat unread in
    # `asked.stderr`. Measured: `GIT_TEST_ASSUME_DIFFERENT_OWNER=1` makes this
    # very checkout exit 128 with "detected dubious ownership", and the skip then
    # claimed it was not a repository. A guard added to stop a skip reporting
    # green must not itself skip for a reason it never checked.
    if asked.returncode != 0:
        pytest.skip(f"git could not answer: {asked.stderr.strip() or asked.returncode}")

    # AND rc 0 IS NOT A YES. `git rev-parse` ECHOES an unrecognised flag and exits
    # 0 -- measured: `--is-shallow-repositoryZZZ` prints itself, rc 0 -- so if the
    # flag is ever renamed this reader stops asking what it believes it asks, and
    # the assertion below would blame the checkout for it.
    assert answer in ("true", "false"), (
        f"git answered {answer!r}, which is neither `true` nor `false`. This reader "
        "has stopped asking what it thinks it asks -- most likely the flag was "
        "renamed and git echoed it back. Fix the reader; this says nothing about "
        "whether the checkout is grafted.")

    assert answer == "false", (
        "this checkout is grafted: `.git/shallow` is set, so the two guards named at "
        "the top of this file will SKIP and report green, and a merge base with main "
        "may not exist at all. Run `git fetch --unshallow`. If a session shallowed it "
        "deliberately, restoring the working tree was not enough -- .git is shared "
        "with every worktree under .claude/worktrees/.")
