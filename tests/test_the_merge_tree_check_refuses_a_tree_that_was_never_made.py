"""The merge-tree check's own failure modes, which are the reason it is a tool.

`tools/merge_tree_check.py` exists because two green, individually-mergeable branches
were red together on 2026-09-03 and nothing in the merge protocol could see it. This
file guards the two things it does that running the commands by hand does not:

  1. **a real conflict is a distinct failure**, not a suite run against a tree git
     refused to make -- a pass about no tree at all is the same family as every other
     vacuous green this repository has recorded;
  2. **the failure COUNT is the verdict**, not the process exit code, because an exit
     code read from the wrong command has masked a red twice here.

BUILT ON A REAL REPOSITORY IN A TEMPORARY DIRECTORY, not on a mocked `subprocess`. A
mock would assert what this module believes about git rather than what git does, and
the whole subject is a disagreement between what a branch believes and what a merge
produces.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import merge_tree_check


def _git(folder: Path, *args: str) -> None:
    done = subprocess.run(["git", *args], cwd=str(folder), capture_output=True)
    assert done.returncode == 0, (
        f"git {' '.join(args)}: {done.stderr.decode('utf-8', 'replace')[:200]}")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    """A repository with a base and two branches, both editing the same line."""
    folder = tmp_path / "repo"
    folder.mkdir()
    _git(folder, "init", "--quiet")
    _git(folder, "config", "user.email", "t@example.invalid")
    _git(folder, "config", "user.name", "t")
    (folder / "a.txt").write_text("one\n", encoding="utf-8")
    _git(folder, "add", "a.txt")
    _git(folder, "commit", "--quiet", "-m", "base")
    _git(folder, "branch", "base")

    _git(folder, "checkout", "--quiet", "-b", "left")
    (folder / "a.txt").write_text("left\n", encoding="utf-8")
    _git(folder, "commit", "--quiet", "-am", "left")

    _git(folder, "checkout", "--quiet", "base")
    _git(folder, "checkout", "--quiet", "-b", "right")
    (folder / "a.txt").write_text("right\n", encoding="utf-8")
    _git(folder, "commit", "--quiet", "-am", "right")

    monkeypatch.setattr(merge_tree_check, "ROOT", folder)
    return folder


def test_a_real_conflict_is_a_distinct_failure_and_not_a_tree(repo):
    """The property that stops a green about nothing.

    Both branches rewrote the same line, so there is no tree to run anything against.
    A hand-run check would take `merge-tree`'s non-zero exit, carry on, and report a
    suite result about the branch it was already standing in.

    THE PAIR HAS TO BE DIVERGENT, and the first version of this test was not.
    `base`..`left` is a fast-forward -- `base` is `left`'s ancestor -- so git merges it
    cleanly and exits 0, and the test failed with DID NOT RAISE. Measured before
    correcting it: `merge-tree --write-tree base left` exits 0, and
    `merge-tree --write-tree left right` exits 1 and names the conflicted path. **The
    tool's premise was right and the scenario was wrong**, which is the same mistake as
    a guard whose subject is not what it thinks.
    """
    with pytest.raises(merge_tree_check.GitError, match="CONFLICT"):
        merge_tree_check.merge_tree("left", "right")

    # And it names both sides, so the reader knows what to rebase.
    try:
        merge_tree_check.merge_tree("left", "right")
    except merge_tree_check.GitError as exc:
        assert "left" in str(exc) and "right" in str(exc)


def test_a_clean_merge_yields_a_tree_that_is_not_either_branch(repo):
    """The tree is the SUBJECT: it is what will exist and neither branch is it."""
    (repo / "b.txt").write_text("added on the right\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "--quiet", "-m", "right adds another file")

    tree = merge_tree_check.merge_tree("base", "right")

    assert len(tree) == 40, f"expected a tree id, got {tree!r}"
    for ref in ("base", "right"):
        rev = subprocess.run(["git", "rev-parse", f"{ref}^{{tree}}"], cwd=str(repo),
                             capture_output=True).stdout.decode().strip()
        if ref == "base":
            assert tree != rev, "the merge tree equals the base's tree"


def test_the_verdict_is_what_the_merge_CAUSED_and_not_a_raw_failure_count():
    """The tool answers one question: what does the MERGE break?

    Read off the module rather than demonstrated, because a demonstration would need
    two branches whose combination is semantically broken -- which is the thing that
    took two sessions and a day to produce by accident.

    IT SUBTRACTS THE BRANCH'S OWN FAILURES, and that mechanism is for a branch that
    is genuinely red on its own -- NOT for excusing this tool's materialisation.

    THE DISTINCTION COST SOMETHING TO LEARN. The first version reported three failures
    that were its own: a hook whose executable bit `checkout-index` had dropped, and two
    documents that `_last_changed` reported stale. The first was fixed by checking the
    tree out through a worktree. **The other two were called "artefacts of materialising
    a tree" and subtracted, and that was wrong** -- they pass on `main`, and the real
    cause was that `commit-tree` was given NO PARENTS, so nothing in the worktree could
    walk history. With both parents they pass and nothing is subtracted at all.

    **A permanent subtraction is a permanent blind spot**, and those two tests guard a
    date nobody maintains: the first time a policy really went stale the tool would have
    subtracted the finding and reported "caused by the merge: 0". Two checks that cannot
    fail, inside the tool that verifies the branch whose subject is checks that cannot
    fail.

    AND THE EXIT CODE IS NOT THE VERDICT. An exit code taken from the wrong command
    has masked a red twice in this repository -- once through a pipe, once through
    `&&`.
    """
    source = Path(merge_tree_check.__file__).read_text(encoding="utf-8")
    assert '"-p", base, "-p", branch' in source, (
        "the materialised commit no longer carries both parents, so any guard that "
        "asks git about history answers confidently and wrongly -- which is the "
        "outcome those guards are built to refuse")
    assert "caused = sorted(merged_failed - branch_failed)" in source, (
        "the tool no longer subtracts the branch's own failures, so it reports its "
        "own materialisation artefacts as merge damage")
    assert "return 1 if caused else 0" in source, (
        "the verdict is no longer what the merge CAUSED")
    assert "CAUSED BY THE MERGE" in source, (
        "the output no longer labels the one number that is the answer")


def test_the_base_is_refreshed_unless_refusing_is_asked_for():
    """A stale base is this check's OWN failure mode, so refreshing is the default
    and skipping it has to be asked for by name."""
    parser_source = Path(merge_tree_check.__file__).read_text(encoding="utf-8")
    assert '"--no-fetch"' in parser_source
    assert 'default="origin/main"' in parser_source
    assert '_git("fetch", "origin", "--quiet")' in parser_source, (
        "the tool no longer refreshes its base, so it can be run against a stale "
        "one -- which is the failure mode it exists to remove")
