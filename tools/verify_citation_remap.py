"""Verify a `file:line` remap was applied ONCE, by pairing rather than comparing.

WHAT THIS EXISTS FOR, MEASURED. Six lines added to `extension/app.js` slid every citation
below them. Ten rows were repaired by re-deriving each from the finished tree. A second,
wider pass then remapped every `app.js` citation across `docs/` -- and remapped those ten
A SECOND TIME, turning `848 -> 853` into `848 -> 853 -> 861`.

WHY THE CHECK IN PLACE COULD NOT SEE IT. Every rewrite was verified as
`origin/main[old] == finished[new]`. That is the right check and IT PASSES AT BOTH HOPS:
the shift is uniform, so the content at line 853 of the old file equals the content at
line 861 of the new one just as truly as it did one hop earlier.

    Content-equality proves a mapping is CONSISTENT.
    It cannot prove the mapping was applied ONCE.

THE STRONGER CLAIM NEEDS A DIFFERENT KIND OF CHECK, not a stricter version of the same
one -- which is the reusable half of this. It is the same mistake as reading
`s.count(old) == 1` as proof of LOCATION: a true assertion (the anchor is unique)
mistaken for a stronger one (the anchor is in the right place).

SO THIS PAIRS. Read the citation list of the document before and after, zip them in
order, and demand `moved[old] == new` for every pair that changed. A double application
fails by construction, because `moved` holds one hop and the document shows two.

Run over the real repair it paired and checked 52 citations and found nothing wrong,
which is what makes it a tool rather than a one-off.

    python tools/verify_citation_remap.py --was <old-tree> --mapping app.js=848:853,...

`--was` is a git revision or a directory. Nothing is written; the exit code is the
verdict.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: THE SAME SHAPE THE GUARD USES, and deliberately the same string: a second citation
#: pattern in a second file is two definitions of what a citation IS, and the day they
#: disagree the tool blesses a document the guard rejects.
SUFFIXES = "py|js|css|html|json|yml|yaml|sh|md|toml|sql"
CITATION = re.compile(
    r"(?<![\w/.\-])((?:[\w.\-]+/)*[\w.\-]+\.(?:" + SUFFIXES + r")):(\d+)(?:-(\d+))?\b")

#: NEVER REMAPPED, AND THIS IS THE HALF THAT COSTS ROWS RATHER THAN MINUTES. Both files
#: are snapshots -- their own headers say to check their citations against a named commit
#: and never against `HEAD` -- so rewriting a reference inside one makes the snapshot say
#: something it did not say. Eleven references inside them were rewritten by the wider
#: pass and had to be restored, and a previous session had already made and reverted
#: exactly that mistake.
SNAPSHOTS = (
    "docs/ENGINE-ROLE-MEASURED.md",      # pinned at 31c369e
    "docs/MUQAWIL-AUDIT-2026-08-26.md",  # pinned at 5722b6f
)


def blank_fences(text: str) -> str:
    """The document with fenced code blocks blanked, LINE COUNT PRESERVED.

    A fence holds `path.py:120` in example output often enough to matter, and those are
    not citations. Removing the block is the obvious move and it is wrong: every line
    number after the first fence shifts, so the tool then reports positions that do not
    exist in the file it is checking. Blanked to lines of EQUAL COUNT, never removed --
    paid for in one afternoon by two different sessions.
    """
    out, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            out.append("")
            continue
        out.append("" if inside else line)
    return "\n".join(out)


def strip_inline_code(text: str) -> str:
    """Backtick spans blanked, across newlines, line count preserved.

    AN INLINE BACKTICK SPAN CAN CROSS A NEWLINE, so a single-line matcher sees two spans
    where there are none and then reads the text between them as prose. Matched over the
    whole document with the newlines kept, so positions survive.
    """
    def blank(match: re.Match[str]) -> str:
        return "`" + "".join("\n" if ch == "\n" else " "
                             for ch in match.group(1)) + "`"

    return re.sub(r"`([^`]*)`", blank, text, flags=re.DOTALL)


def citations(text: str) -> list[tuple[str, str]]:
    """`(path, line)` for every citation in prose, in document order.

    ORDER IS THE WHOLE MECHANISM. The pairing below zips the before and after lists, so
    a tool that sorted or de-duplicated them would destroy the one property being
    checked.
    """
    body = strip_inline_code(blank_fences(text))
    return [(match.group(1), match.group(2)) for match in CITATION.finditer(body)]


def _read(revision_or_dir: str, relative: str) -> str:
    """The document as it was, from a git revision or a directory."""
    candidate = Path(revision_or_dir)
    if candidate.is_dir():
        return (candidate / relative).read_text(encoding="utf-8")
    done = subprocess.run(["git", "show", f"{revision_or_dir}:{relative}"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise SystemExit(f"cannot read {relative} at {revision_or_dir}: "
                         f"{done.stderr.strip()}")
    return done.stdout


def verify(was: str, now: Path, relative: str,
           moved: dict[tuple[str, str], str]) -> list[str]:
    """Complaints about this document, empty when the remap was one hop.

    `moved` is keyed `(path, old_line) -> new_line`, which is one hop by construction.
    """
    if relative.replace("\\", "/") in SNAPSHOTS:
        return [f"{relative} is a snapshot and must not be remapped at all: its header "
                "pins it to a commit, and rewriting a reference inside it makes the "
                "snapshot say something it did not say"]
    before = citations(_read(was, relative))
    after = citations((now / relative).read_text(encoding="utf-8"))
    if len(before) != len(after):
        # NOT A REMAP AT ALL. A remap changes numbers and never the number OF citations,
        # so this is a different edit wearing a remap's name and the pairing below
        # cannot mean anything over it.
        return [f"{relative} has {len(before)} citation(s) before and {len(after)} "
                "after: a remap changes line numbers, never how many citations there "
                "are, so this pairing cannot be trusted"]
    complaints = []
    for (old_path, old_line), (new_path, new_line) in zip(before, after, strict=True):
        if old_path != new_path:
            complaints.append(
                f"{relative}: citation order changed -- {old_path} became {new_path}")
            continue
        if old_line == new_line:
            continue
        expected = moved.get((old_path, old_line))
        if expected is None:
            complaints.append(
                f"{relative}: {old_path}:{old_line} became :{new_line}, and the mapping "
                "does not mention it -- so something moved it that was not this remap")
        elif expected != new_line:
            # THE DOUBLE APPLICATION, CAUGHT. `848 -> 853` applied twice shows as
            # `848 -> 861` in the document while the mapping still says 853.
            complaints.append(
                f"{relative}: {old_path}:{old_line} became :{new_line}, but the mapping "
                f"says :{expected} -- applied more than once")
    return complaints


def parse_mapping(raw: str) -> dict[tuple[str, str], str]:
    """`path=old:new,old:new` pairs, one hop each."""
    moved: dict[tuple[str, str], str] = {}
    for raw_chunk in raw.split(";"):
        chunk = raw_chunk.strip()
        if not chunk:
            continue
        path, _, pairs = chunk.partition("=")
        if not pairs:
            raise SystemExit(f"mapping needs `path=old:new,...`: {chunk!r}")
        for pair in pairs.split(","):
            old, _, new = pair.strip().partition(":")
            if not (old.isdigit() and new.isdigit()):
                raise SystemExit(f"mapping pair must be `old:new` digits: {pair!r}")
            moved[(path.strip(), old)] = new
    return moved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--was", required=True,
                        help="git revision or directory holding the documents before")
    parser.add_argument("--mapping", required=True,
                        help="`path=old:new,old:new; path=...` -- ONE hop per entry")
    parser.add_argument("--docs", default="docs",
                        help="folder of documents to check (default: docs)")
    args = parser.parse_args(argv)

    moved = parse_mapping(args.mapping)
    complaints, checked = [], 0
    for path in sorted((ROOT / args.docs).rglob("*.md")):
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        if relative in SNAPSHOTS:
            # SKIPPED RATHER THAN COMPLAINED ABOUT when nothing asked for it: the
            # refusal in `verify` is for a caller that names one explicitly.
            continue
        found = verify(args.was, ROOT, relative, moved)
        checked += len(citations(path.read_text(encoding="utf-8")))
        complaints.extend(found)

    for line in complaints:
        print(line, file=sys.stderr)
    print(f"paired and checked {checked} citation(s) across {args.docs}")
    if complaints:
        print(f"{len(complaints)} problem(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
