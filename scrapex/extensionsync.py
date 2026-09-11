"""Keep the locally loaded (unpacked) extension/ folder in step with GitHub main.

WHY THIS EXISTS: "Load unpacked" points Chrome straight at `extension/` inside
this checkout, and nothing updates that folder but a manual `git pull` followed
by a manual Reload in `chrome://extensions` — the owner never opens a terminal
(CLAUDE.md), so that pull only ever happened when a session ran it for him. The
five-step manual routine this replaces is written out in
`docs/plans/2026-07-29-sync-green-main-and-merge.md`, step 5 of its first phase.

SCOPE IS `extension/`, NOT THE WHOLE REPOSITORY. The owner asked to keep the
extension's own files current, not to fast-forward every engine file the moment
some unrelated session merges something — the engine's own staleness already
has its own detector (`scrapex/provenance.py`, the "Restart needed" badge).
`check()` only reports on commits that touch `extension/`.

WHY A FULL FAST-FORWARD MERGE AND NOT A SPARSE `git checkout origin/main --
extension`: a sparse checkout of one subtree leaves HEAD where it was, so the
very next check would see `extension/` as dirty against its own HEAD forever —
it would apply an update once and then refuse every update after. `git merge
--ff-only` moves HEAD, so the tree stays internally consistent and the next
check starts from a true baseline. It touches the working directory only when
`extension/` actually changed, and git itself refuses — loudly, never silently —
the instant any local edit anywhere would be overwritten.

NEVER TOUCHES A DIRTY TREE. `check()` reports "dirty" and `apply()` refuses if
`extension/` itself carries uncommitted edits — the owner's decision
(2026-09-11): local edits are reported, never discarded, never stashed for him.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = "extension"
_TIMEOUT_S = 20


def _git(*args: str) -> tuple[int, str, str]:
    """Run git in the repo root. Never raises — a failed process is data here,
    not an exception, because every caller turns a nonzero code into a state a
    reader can act on rather than a stack trace they cannot."""
    git = shutil.which("git")
    if git is None:
        return 127, "", "git is not on PATH"
    try:
        proc = subprocess.run(
            [git, *args], cwd=str(REPO_ROOT), capture_output=True,
            text=True, timeout=_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "git timed out"
    return proc.returncode, proc.stdout, proc.stderr


def check() -> dict:
    """Where `extension/` in this checkout stands against `origin/main`.

    `state` is one of: no_git, error, not_main, offline, dirty, up_to_date,
    behind. Every branch is a different sentence because "cannot say" has
    several causes and only one of them ("dirty") is the owner's to fix.
    """
    if not (REPO_ROOT / ".git").exists():
        return {"ok": True, "state": "no_git",
                "detail": "This install is not a git checkout; there is nothing to sync."}

    code, branch_out, _ = _git("rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        return {"ok": True, "state": "error",
                "detail": "Could not read the current branch."}
    branch = branch_out.strip()
    if branch != "main":
        return {"ok": True, "state": "not_main",
                "detail": f"This checkout is on '{branch}', not main. Sync only follows main."}

    code, _, fetch_err = _git("fetch", "origin", "main")
    if code != 0:
        return {"ok": True, "state": "offline",
                "detail": f"Could not reach GitHub: {fetch_err.strip() or 'fetch failed'}"}

    _, dirty_out, _ = _git("status", "--porcelain", "--", EXTENSION_DIR)
    if dirty_out.strip():
        return {"ok": True, "state": "dirty",
                "detail": "extension/ has uncommitted local changes. Commit, stash, or "
                          "discard them yourself before sync can run."}

    _, count_out, _ = _git("rev-list", "--count", "HEAD..origin/main", "--", EXTENSION_DIR)
    behind = int((count_out or "0").strip() or 0)
    if behind == 0:
        return {"ok": True, "state": "up_to_date"}

    _, log_out, _ = _git("log", "--oneline", "HEAD..origin/main", "--", EXTENSION_DIR)
    summary = [line for line in log_out.strip().splitlines() if line]
    return {"ok": True, "state": "behind", "commits_behind": behind,
            "summary": summary[:5]}


def apply() -> dict:
    """Fast-forward this checkout to `origin/main` and report the result.

    Re-runs `check()` first rather than trusting a caller's cached state — the
    tree can go dirty, or the remote can move, in the time between a panel
    showing "behind" and the owner pressing the button.
    """
    state = check()
    if state.get("state") != "behind":
        return state

    code, out, err = _git("merge", "--ff-only", "origin/main")
    if code != 0:
        text = (err or out).strip()
        lowered = text.lower()
        if "would be overwritten" in lowered or "please commit your changes" in lowered:
            return {"ok": True, "state": "dirty",
                     "detail": "Local changes would be overwritten by the update; "
                               "nothing was touched.",
                     "git_detail": text}
        if "not possible to fast-forward" in lowered:
            return {"ok": True, "state": "diverged",
                     "detail": "This checkout has local commits origin/main does not; "
                               "sync only fast-forwards and will not merge or rebase.",
                     "git_detail": text}
        return {"ok": False, "error": "merge_failed",
                "detail": text or "git merge --ff-only failed"}

    _, head_out, _ = _git("rev-parse", "--short", "HEAD")
    return {"ok": True, "state": "applied", "head": head_out.strip(),
            "detail": "extension/ now matches origin/main."}
