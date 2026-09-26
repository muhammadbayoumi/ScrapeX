"""Does a pull request carry the VERSION its body says it does? (#1086)

A rebase drops a VERSION commit without a word when main already carries the same
change: `git rebase` prints "dropping <sha> ... patch contents already upstream",
reports success, and every version guard stays green, because the branch now agrees
with main. It happened to #1042 on 2026-09-24. A server-side update-branch ends the
same way. The one record of what the author meant is the pull request's body, which
no rebase touches -- so the body says it, and this compares.

THE LINE, a line of its own anywhere in the pull request body, exactly one of:

    VERSION: 0.4.23
    VERSION: unchanged

The first says the pull request raises VERSION to 0.4.23, the second that it leaves
VERSION alone. No line also means unchanged, so such a pull request needs nothing.

NOTHING ELSE MAY LOOK LIKE ONE. Any other line whose first word is VERSION -- a
heading, bold, a quote, a list item, trailing words, "Version:" -- is refused by name
rather than read as unchanged, because reading it as unchanged is the false pass
#1086 is about. That holds inside code blocks too: write examples mid-line. Two
declarations that disagree are refused rather than resolved. A byte-order mark at the
very start of the body is dropped first; GitHub has delivered one.

THE RULE, with H the pull request's VERSION and M main's:

    unchanged   H == M
    X           X is newer than M, and H == X

Run by `.github/workflows/version-intent.yml`, which hands the body over in the
PR_BODY environment variable and never splices it into a command.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from itertools import count
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# The ordering of versions is scrapex/version.py's knowledge, not a second copy here.
from scrapex.version import parse_version  # noqa: E402

UNCHANGED = "unchanged"
DECLARATION = re.compile(r"^VERSION:[ \t]*(\S+)[ \t]*$")
# A line whose first word, past any Markdown decoration or invisible space, is
# VERSION, or "version:" in any case. Every such line must BE a declaration.
LOOKS_LIKE_ONE = re.compile(r"^[\s\ufeff>#*`_~|\d.)-]*(?:VERSION\b|(?i:version)\s*:)")

_module_names = count()


def declared(body: str | None) -> str:
    """The body's VERSION line: a version, or UNCHANGED when there is none."""
    found: list[str] = []
    refused: list[str] = []
    for line in (body or "").removeprefix("\ufeff").splitlines():
        match = DECLARATION.match(line)
        if match:
            found.append(match.group(1))
        elif LOOKS_LIKE_ONE.match(line):
            refused.append(line)
    if refused:
        shown = "; ".join(repr(line[:80]) for line in refused[:3])
        more = f" and {len(refused) - 3} more" if len(refused) > 3 else ""
        raise ValueError(
            f"the pull request body has a line that names VERSION but is not a "
            f"declaration ({shown}{more}). Make it a line of its own reading exactly "
            f"`VERSION: <version>` or `VERSION: {UNCHANGED}`, or reword it so it does "
            "not start with VERSION")
    if not found:
        return UNCHANGED
    if len(set(found)) > 1:
        raise ValueError(
            "the pull request body declares VERSION more than once, and the lines "
            f"disagree ({', '.join(found)}); keep one")
    value = found[0]
    if value != UNCHANGED:
        try:
            parse_version(value)
        except ValueError as exc:
            raise ValueError(
                f"the pull request body says VERSION: {value}, which is neither "
                f"'{UNCHANGED}' nor a version ({exc})") from exc
    return value


def version_in(path: Path) -> str:
    """VERSION as a copy of scrapex/version.py defines it, read by running that copy.

    Loaded from its path rather than imported, because the two copies compared --
    this branch's and main's -- are the same module at two commits. The module
    imports only the standard library, so this needs nothing installed.
    """
    name = f"_version_intent_copy_{next(_module_names)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{path} cannot be loaded as a Python module")
    module = importlib.util.module_from_spec(spec)
    # dataclasses look their module up in sys.modules while the class is built.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    value = getattr(module, "VERSION", None)
    if not isinstance(value, str):
        raise ValueError(f"{path} defines no VERSION string")
    parse_version(value)
    return value


def problem(declaration: str, head: str, main: str) -> str:
    """The sentence that fails the check, or "" when the pull request is what it says."""
    if declaration == UNCHANGED:
        if head == main:
            return ""
        if parse_version(head) > parse_version(main):
            return (f"scrapex/version.py moves VERSION from {main} to {head}, and the "
                    "pull request body does not say so. Add the line "
                    f"`VERSION: {head}` to the body, at the start of a line and "
                    "outside any code block.")
        return (f"main is at VERSION {main} and this branch's scrapex/version.py says "
                f"{head}. Rebase onto main.")
    if parse_version(declaration) <= parse_version(main):
        return (f"main is already at VERSION {main}, so `VERSION: {declaration}` is not "
                f"a raise. Take a number after {main}, set it in scrapex/version.py and "
                "pyproject.toml, run `python -m scrapex.cli export-version`, and change "
                "the line in the body to match.")
    if head == declaration:
        return ""
    if head == main:
        return (f"the body says `VERSION: {declaration}`, but scrapex/version.py says "
                f"{head}, which is main's: the raise is not on this branch. A rebase "
                "drops it without a word when main carries the same change (#1086). Set "
                f"{declaration} in scrapex/version.py and pyproject.toml again and run "
                "`python -m scrapex.cli export-version`.")
    return (f"scrapex/version.py says {head} and the body says `VERSION: {declaration}`; "
            "make them agree.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--head", type=Path, required=True,
                        help="this branch's scrapex/version.py")
    parser.add_argument("--main", type=Path, required=True,
                        help="main's scrapex/version.py")
    args = parser.parse_args(argv)
    try:
        declaration = declared(os.environ.get("PR_BODY", ""))
        head = version_in(args.head)
        main_version = version_in(args.main)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sentence = problem(declaration, head, main_version)
    if sentence:
        print(sentence, file=sys.stderr)
        return 1
    print(f"VERSION {head} on this branch, {main_version} on main, and the body says "
          f"{declaration}: consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
