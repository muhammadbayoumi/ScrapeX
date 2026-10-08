"""Check out Supabase's repository at the pinned commit, only the paths a design study reads.

WHY A CHECKOUT AND NOT `gh api`. The other `read_supabase_*` tools fetch one file at a time,
which suits a fixture. A design study does something else: it greps. "Where does Studio
draw a job's status?" is answered by searching `apps/studio` for it, and a search needs
the files on disk. Without this tool every session built that checkout by hand, from
memory, at whatever commit it happened to type.

WHAT IT FETCHES. A blobless, sparse, single-commit fetch: only the commit design/
supabase.NOTICE.txt pins, and only the paths below. The full repository is several hundred
megabytes; these paths are a few. Run it again and it re-uses the directory, so it is cheap
to call at the start of every study.

    python tools/checkout_supabase_pin.py                  # prints the directory
    python tools/checkout_supabase_pin.py --path apps/studio/components/grid

It needs the network and `git`, so CI does not run it against GitHub. The test drives it
against a local repository instead.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.read_supabase_tokens import pinned_commit  # noqa: E402

REMOTE = "https://github.com/supabase/supabase.git"

#: What a design study reads, in the order docs/DESIGN-SYSTEM-SOURCES.md ranks them:
#: the documentation, the registry, the atoms and patterns, then Studio's production
#: composition. `--path` adds more for one run.
STUDY_PATHS = (
    "apps/design-system/content/docs",
    "apps/design-system/registry",
    "packages/ui/src/components",
    "packages/ui/build/css",
    "packages/ui-patterns/src",
    "packages/config",
    "apps/studio/components",
    "apps/studio/styles",
)


def default_destination(commit: str) -> Path:
    """Outside the repository, so a checkout can never be committed by accident."""
    base = os.environ.get("SCRAPEX_SUPABASE_CACHE") or (Path.home() / ".cache" / "scrapex")
    return Path(base) / f"supabase-{commit[:12]}"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _must(result: subprocess.CompletedProcess, what: str) -> None:
    if result.returncode != 0:
        sys.exit(f"{what} failed: {(result.stderr or result.stdout).strip()}")


def checkout(commit: str, destination: Path, paths: list[str], remote: str = REMOTE) -> Path:
    """Fetch `commit` from `remote` into `destination`, holding only `paths`.

    A directory already at `commit` is re-used: only the sparse set is widened, so asking
    for one more path costs that path and nothing else.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        sys.exit(f"{commit!r} is not a full 40-character commit SHA; a branch or tag "
                 "moves, so a study must read at a commit")
    destination.mkdir(parents=True, exist_ok=True)
    head = _git("rev-parse", "HEAD", cwd=destination)
    reuse = (destination / ".git").is_dir() and head.returncode == 0 \
        and head.stdout.strip() == commit
    if not reuse:
        if (destination / ".git").exists():
            sys.exit(f"{destination} holds a checkout at another commit "
                     f"({head.stdout.strip()[:12] or 'none'}); remove it or pass --dest")
        _must(_git("init", "-q", cwd=destination), "git init")
        _must(_git("remote", "add", "origin", remote, cwd=destination), "git remote add")
    _must(_git("sparse-checkout", "set", "--no-cone", *[f"/{p.strip('/')}/" for p in paths],
               cwd=destination), "git sparse-checkout")
    if not reuse:
        _must(_git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", commit,
                   cwd=destination), f"fetching {commit[:12]}")
    _must(_git("checkout", "-q", commit, cwd=destination), f"checking out {commit[:12]}")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--commit", help="default: the commit design/supabase.NOTICE.txt pins")
    parser.add_argument("--dest", type=Path, help="default: ~/.cache/scrapex/supabase-<sha>")
    parser.add_argument("--path", action="append", default=[],
                        help="a further repository path to include (repeatable)")
    parser.add_argument("--remote", default=REMOTE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    commit = args.commit or pinned_commit()
    destination = args.dest or default_destination(commit)
    done = checkout(commit, destination, [*STUDY_PATHS, *args.path], remote=args.remote)
    print(done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
