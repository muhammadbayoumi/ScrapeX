"""Regenerate tests/fixtures/supabase-linked-paths.json: every path in Supabase's repository
that the design documents link, and whether the pinned commit holds it.

WHY A FIXTURE. A link can name the pin and still point at nothing. `AGENTS.md` and
`apps/studio/AGENTS.md` were linked on master, and pinning them would have produced two
dead links, because at the pin those instructions are `.claude/CLAUDE.md` and
`apps/studio/CLAUDE.md`. CI has no business calling GitHub on every run, so this reads the
pinned tree once and writes down what it holds. The test holds the documents to that.

RUN IT WHEN THE PIN MOVES, OR WHEN A DOCUMENT GAINS A LINK INTO SUPABASE, and only then:

    python tools/read_supabase_linked_paths.py              # rewrite the fixture
    python tools/read_supabase_linked_paths.py --check      # exit 1 if it WOULD change

Like tools/read_supabase_tokens.py it needs the network and the `gh` CLI, so CI does not
run it. The fixture stores GitHub's object id for every path it found, so an entry typed
in by hand has to invent a hash, and `--check` refuses it the next time it runs.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.read_supabase_tokens import pinned_commit  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "supabase-linked-paths.json"
DESIGN_DOCS = ("docs/DESIGN-SYSTEM.md", "docs/UI-KIT.md", "docs/DESIGN-SYSTEM-SOURCES.md")

# A link into Supabase's repository, on either host that serves its files. The trailing
# slash is the point: `github.com/supabase/supabase-ui-web` is a different, deprecated
# repository, and the repository root with no path names no file. GitHub reads the host,
# the owner and the repository case-insensitively, so this does too.
REPO_LINK = re.compile(
    r"(?:https?://)?(?:www\.)?(?P<host>github\.com|raw\.githubusercontent\.com)"
    r"/supabase/supabase/(?P<rest>[^\s)\]>\"'`]*)",
    re.I,
)


def pinned_path(match: re.Match, pin: str) -> tuple[str, str] | None:
    """(kind, path) when the link names the pin, else None.

    `github.com` puts `tree/` or `blob/` before the commit; `raw.githubusercontent.com`
    puts the commit straight after the repository and serves only files. A fragment or a
    query (`#L12`, `?plain=1`) and a trailing slash do not change which path is named.
    """
    rest = match.group("rest")
    raw = match.group("host").lower() == "raw.githubusercontent.com"
    if raw:
        found = re.match(rf"{pin}(?:/(?P<path>[^#?]*))?(?:[#?]|$)", rest)
        kind = "blob"
    else:
        found = re.match(rf"(?P<kind>tree|blob)/{pin}(?:/(?P<path>[^#?]*))?(?:[#?]|$)", rest)
        kind = found.group("kind") if found else ""
    if not found:
        return None
    path = (found.group("path") or "").rstrip("/")
    # A raw link that names no file names nothing: that host serves files only.
    if raw and not path:
        return None
    return kind, path


def linked_paths(pin: str) -> dict[str, set[str]]:
    """Every pinned path the documents link, with every kind it is linked as: "tree", "blob".

    A set, not the last kind seen, because a path linked twice is checked twice: a wrong
    `blob/` link must not hide behind a right `tree/` link to the same directory.
    """
    paths: dict[str, set[str]] = {}
    for relative in DESIGN_DOCS:
        for line in (ROOT / relative).read_text(encoding="utf-8").splitlines():
            for match in REPO_LINK.finditer(line):
                pinned = pinned_path(match, pin)
                if pinned and pinned[1]:
                    paths.setdefault(pinned[1], set()).add(pinned[0])
    return paths


def read(pin: str) -> dict:
    """One call for the whole pinned tree, then the linked paths looked up in it."""
    result = subprocess.run(
        ["gh", "api", f"repos/supabase/supabase/git/trees/{pin}?recursive=1"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        sys.exit(f"could not read the tree at {pin[:8]}: {result.stderr.strip()}")
    tree = json.loads(result.stdout)
    if tree.get("truncated"):
        sys.exit(f"GitHub truncated the tree at {pin[:8]}; an absent path would be a guess")
    held = {entry["path"]: [entry["type"], entry["sha"]] for entry in tree["tree"]}

    linked = linked_paths(pin)
    # Zero would write a fixture that checks nothing, and the test that asked for this run
    # would then pass. The documents link 28 paths today.
    if not linked:
        sys.exit("the design documents link no pinned path into Supabase's repository; "
                 "the pattern is reading the wrong thing, so no fixture is written")
    present, absent = {}, []
    for path in sorted(linked):
        if path in held:
            present[path] = held[path]
        else:
            absent.append(path)
    return {"commit": pin, "present": present, "absent": absent}


def rendered(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if regenerating would change the fixture, and write nothing")
    args = parser.parse_args()
    pin = pinned_commit()
    data = read(pin)
    text = rendered(data)
    print(f"\n  {len(data['present'])} linked paths held at {pin[:8]}, {len(data['absent'])} absent"
          + (f": {', '.join(data['absent'])}" if data["absent"] else ""))

    if args.check:
        current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
        if current == text:
            print(f"  {FIXTURE.relative_to(ROOT)} is up to date")
            return
        sys.exit(f"  {FIXTURE.relative_to(ROOT)} is STALE at {pin[:8]}. "
                 "Run `python tools/read_supabase_linked_paths.py`.")

    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"  wrote {FIXTURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
