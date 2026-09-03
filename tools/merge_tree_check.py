"""Run a suite against the tree the MERGE would produce, not against the branch.

    python -m tools.merge_tree_check <branch> [-- pytest args...]

WHY THIS EXISTS, and it is a defect that reached a merge queue on 2026-09-03 rather
than a precaution. Two pull requests were each green, each `MERGEABLE`, and **red
together**:

    #314  shortened scrapex/cli.py by four lines (a function moved out of it)
    #309  added a tier that checks a citation still holds the subject it quotes

`docs/BACKLOG.md` cited `scrapex/cli.py:856` for a line that `#314` moved to 852. Git
reported no conflict at all -- the two changes sit in different regions of the same two
files -- and **neither branch's CI could have seen it**: `#309`'s ran while `cli.py` was
still four lines longer, and `#314`'s ran before the tier that checks quoted subjects
existed.

EVERY OTHER CHECK IN THE MERGE PROTOCOL IS PER BRANCH:

    two identical settled reads    per branch
    the row count                  per branch
    the head named at both ends    per branch
    both run modes locally         per branch

**Not one of them can see a semantic conflict BETWEEN branches.** The only thing that
reads what will actually exist is the merge tree.

AND IT MUST BE THE LAST THING BEFORE THE MERGE, NOT PART OF PREPARING THE BRANCH. The
result is only meaningful against the head that is actually about to merge; in the
incident above the two branches' checks ran hours apart, and **that gap is where the
defect lived**. No amount of per-branch rigour closes it.

TWO THINGS THIS DOES THAT RUNNING THE COMMANDS BY HAND DOES NOT:

  1. **It fails distinctly when git reports a real conflict**, instead of running a
     suite against a tree that was never produced. A pass about no tree at all is the
     same family as every other vacuous green -- see `docs/LESSONS.md` on discarded
     greens.
  2. **It re-reads `origin/main` every time**, so it cannot be run against a stale
     base. That is the failure mode of the check ITSELF, and a hand-run version has it
     by default: the first hand-run of this check reported a failure that was an
     artefact of testing the branch tree instead of the merge tree.

IT IS NOT A RITUAL. Run before one merge it paid nothing; run before the next it caught
a red `main`. A check that fires rarely and for real is the opposite of the guards this
repository spent 2026-09-02 and 2026-09-03 finding -- the ones that never fired at all.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GitError(RuntimeError):
    """A git command this tool depends on did not succeed."""


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    """Run git and return stdout as text.

    NOT `text=True`: that decodes with the locale codec, which on this machine is
    cp1252 and mangles every character outside Latin-1. This repository's commits and
    documents carry Arabic, so the bytes are decoded explicitly.
    """
    done = subprocess.run(["git", *args], cwd=str(cwd or ROOT),
                          capture_output=True)
    out = done.stdout.decode("utf-8", errors="replace")
    if check and done.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({done.returncode}): "
            f"{done.stderr.decode('utf-8', errors='replace').strip()[:300]}")
    return out


def merge_tree(base: str, branch: str) -> str:
    """The tree id merging `branch` into `base` would produce.

    Raises `GitError` on a real conflict rather than returning something to run a
    suite against, because a suite that passes over a tree git refused to make is a
    green about nothing.
    """
    done = subprocess.run(
        ["git", "merge-tree", "--write-tree", base, branch],
        cwd=str(ROOT), capture_output=True)
    out = done.stdout.decode("utf-8", errors="replace")
    if done.returncode != 0:
        raise GitError(
            f"git reports a CONFLICT merging {branch} into {base}; rebase before "
            f"anything else:\n{out.strip()[:600]}")
    tree = out.strip().splitlines()[0].strip() if out.strip() else ""
    if not tree:
        raise GitError(f"git merge-tree wrote no tree for {branch} into {base}")
    return tree


def run_against(tree: str, base: str, branch: str,
                pytest_args: list[str]) -> tuple[int, set, str]:
    """Materialise `tree` in a real worktree and run pytest inside it.

    A COMMIT AND A WORKTREE, NOT `read-tree` + `checkout-index`. Measured on Windows:
    `checkout-index` does not carry the executable bit, so a test asserting a hook is
    executable failed in every merge tree -- a false red from the checking tool, which
    is the one result that makes a check get ignored.

    AND THE COMMIT MUST CARRY BOTH PARENTS, which the first version did not, and that
    was a worse defect than the mode bit because it made the tool answer confidently
    and wrongly. Measured: an orphan `commit-tree` leaves **1** commit reachable; with
    `-p base -p branch` it leaves **607**.

    Guards that ASK GIT ABOUT HISTORY then have nothing to walk.
    `tests/test_the_privacy_policy_is_true.py` is the instance: `_last_changed` walks
    PAST commits whose only effect on a file is its own `Last updated` line, because
    correcting a date is itself a change and a naive guard would demand the date move
    forever. Without history that walk cannot happen, so it answered `2026-08-12`
    where the truth is `2026-08-08` and reported two documents as stale. **Its own
    docstring names this outcome as the thing it is built to avoid** -- *"a shallow
    clone answers confidently and wrongly, which is worse than not answering"* -- and
    it defends itself by returning None and skipping. A parentless materialisation
    defeats that defence.

    A real merge commit has two parents. So does this one.

    The commit is unreferenced, so git garbage-collects it; the worktree is removed in
    the `finally`, including when the suite raises.
    """
    commit = _git("commit-tree", tree, "-p", base, "-p", branch,
                  "-m", "merge-tree check (unreferenced)").strip()
    scratch = Path(tempfile.mkdtemp(prefix="mergetree-")) / "tree"
    try:
        _git("worktree", "add", "--quiet", "--detach", str(scratch), commit)
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             *pytest_args],
            cwd=str(scratch), capture_output=True)
        out = done.stdout.decode("utf-8", errors="replace")
        # `FAILED tests/x.py::test_y - AssertionError: ...` -> `tests/x.py::test_y`.
        # The first draft split on the leading word and compared the string "FAILED"
        # for every line, so every failure looked like the same one and the two runs
        # always agreed. Caught by running it: three distinct failures reported as one.
        failed = set()
        for line in out.splitlines():
            if not line.startswith(("FAILED", "ERROR")):
                continue
            parts = line.split(None, 2)
            failed.add(parts[1] if len(parts) > 1 else line)
        return done.returncode, failed, out
    finally:
        _git("worktree", "remove", "--force", str(scratch), check=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a suite against the tree a merge would produce.")
    parser.add_argument("branch", help="the branch about to be merged")
    parser.add_argument("--base", default="origin/main",
                        help="what it merges into (default: origin/main)")
    parser.add_argument("--no-fetch", action="store_true",
                        help="skip refreshing the base; only for an offline check, "
                             "because a stale base is this check's own failure mode")
    parser.add_argument("pytest_args", nargs="*",
                        help="arguments passed to pytest, e.g. -m docs")
    args = parser.parse_args()

    try:
        if not args.no_fetch:
            _git("fetch", "origin", "--quiet")
        base_sha = _git("rev-parse", "--short", args.base).strip()
        head_sha = _git("rev-parse", "--short", args.branch).strip()
        print(f"base   {args.base}  {base_sha}")
        print(f"branch {args.branch}  {head_sha}")
        tree = merge_tree(args.base, args.branch)
    except GitError as exc:
        print(f"MERGE-TREE: {exc}")
        return 2
    print(f"merge tree {tree[:12]} (git merges it cleanly)")

    # TWO RUNS, AND THE ANSWER IS THE DIFFERENCE. A failure that is present on the
    # BRANCH as well was not caused by the merge, and reporting it makes this tool
    # answer a question nobody asked. Two classes showed up the first time it ran for
    # real, both artefacts of materialising a tree rather than findings:
    #
    #   * a test asserting a hook is executable -- `checkout-index` dropped the mode
    #     bit on Windows (fixed by checking the tree out through a worktree instead);
    #   * two tests comparing a document's Last-updated line against its FILE MTIME,
    #     which in any fresh checkout is the moment of checkout.
    #
    # Neither is about the merge. A checking tool that reports either is a tool people
    # stop running, which costs more than the check is worth.
    print("running the merge tree...")
    merged_code, merged_failed, _merged_out = run_against(
        tree, args.base, args.branch, args.pytest_args)
    print("running the branch, to subtract what the merge did not cause...")
    branch_tree = _git("rev-parse", f"{args.branch}^{{tree}}").strip()
    _branch_code, branch_failed, _branch_out = run_against(
        branch_tree, args.branch, args.branch, args.pytest_args)

    caused = sorted(merged_failed - branch_failed)
    shared = sorted(merged_failed & branch_failed)
    print(f"MERGE-TREE RUN exit={merged_code}  "
          f"failures in the merge tree: {len(merged_failed)}  "
          f"already failing on the branch: {len(shared)}")
    print(f"CAUSED BY THE MERGE: {len(caused)}")
    for name in caused:
        print(f"  {name}")
    if shared:
        print("  (pre-existing on the branch, not reported as merge damage:)")
        for name in shared:
            print(f"    {name}")
    if not caused and merged_failed:
        print("  nothing the merge caused; the failures above are the branch's own "
              "or artefacts of materialising a tree")
    # The COUNT is the verdict, not the exit code: an exit code read from the wrong
    # command has masked a red twice in this repository.
    return 1 if caused else 0


if __name__ == "__main__":
    raise SystemExit(main())
