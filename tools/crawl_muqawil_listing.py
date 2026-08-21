"""The contractor crawl, which now lives in the package. This is a pointer.

WHY THIS FILE IS FOUR LINES INSTEAD OF FOUR HUNDRED. It used to hold the whole
implementation, and that was the defect: `pyproject.toml` ships
`include = ["scrapex*"]`, so nothing under `tools/` reaches an installed user.
Measured 2026-08-21 — `scrapex crawl` takes a `source_key from sources.yaml`,
muqawil is not in `sources.yaml`, and `cli.py` had **zero** references to
`muqawil`, `partitioncrawl`, `snapshotcrawl` or `generic_record`. Everything built
for the directory was reachable only by cloning the repository and running this
script from a terminal, which is why the owner's panel reported the Engine as "not
detected" while a crawl was running: the crawl never went near it.

It is kept rather than deleted because six documents and one running command name
this path, and a file that answers "no such file" teaches nothing. It delegates,
so the two can never disagree.

    scrapex contractors --plan                  # what a user has after pip install
    python -m scrapex.contractors --plan        # the same thing, without one
"""
import sys
from pathlib import Path

# The worktree, not the checkout `scrapex` is installed from — `CLAUDE.md`'s first
# trap. Only this shim needs it: the package it points at is imported normally.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapex.contractors import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
