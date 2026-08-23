"""A drift guard that hashes `$(...)` output compares a file against itself and loses.

WHY THIS FILE EXISTS. `publish-docs.yml` checks that the chooser served to owners
is the file this repository tests -- the one part of ScrapeX served from a web
server, and the part that handles a Google access token. It did it like this:

    mine=$(sha256sum docs/picker/scrapex-picker.html | cut -d' ' -f1)
    served=$(curl -sL --max-time 20 "$PAGE" 2>/dev/null || true)
    theirs=$(printf '%s' "$served" | sha256sum | cut -d' ' -f1)

Command substitution **strips every trailing newline** from what it captures, and
`printf '%s'` puts none back -- while `sha256sum` of the file keeps the file's own.
So `theirs` could never equal `mine` for a file ending in a newline, which this one
does.

WHAT IT COST. The workflow failed on every scheduled run from at least 2026-08-16
to 2026-08-23 -- eight consecutive days -- while the served copy was **byte
identical**: 10,231 bytes, zero differing lines, hashing to exactly the value the
job printed as "repository". Nobody read it, for two reasons that are both worth
the test. The guard cannot fix what it finds, so its failure is normal-looking
noise on a schedule; and OP-20 had made every red check mean "unpaid", so a red
that meant "broken" was invisible. Recorded as OP-60.

The `echo "$var" | sha256sum` form is the same bug with a newline ADDED instead of
removed, so it is forbidden here too. The fix in both cases is the same and it is
not a workaround: **hash the bytes**. Write the body to a file and hash the file.

Twenty lines above the broken check, the documents loop does exactly that -- it
PIPES curl into `sha256sum` rather than capturing it -- and has never false-alarmed.
The asymmetry between two checks in one file is the whole of this bug.
"""
from __future__ import annotations

import pathlib
import re

WORKFLOWS = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows"

#: `printf ... "$var" | sha256sum` or `echo "$var" | sha256sum`, on one line.
#: Anchored on the pipe into the hasher so a `printf` used for anything else is
#: not caught -- the defect is specifically feeding a CAPTURED value to a hash.
HASHED_VARIABLE = re.compile(
    r"""\b(?:printf|echo)\b[^|\n]*\$[{(]?\w+[)}]?[^|\n]*\|\s*sha256sum""")


def test_no_workflow_feeds_a_captured_variable_into_sha256sum():
    """The bug is invisible in review and total in effect: the comparison simply
    never passes, and the message it prints names the right file for the wrong
    reason. A file path or a pipe straight from the producing command has no
    newline to lose."""
    offenders = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        for number, line in enumerate(
                workflow.read_text(encoding="utf-8").splitlines(), start=1):
            if HASHED_VARIABLE.search(line):
                offenders.append(f"{workflow.name}:{number}: {line.strip()}")

    assert not offenders, (
        "a shell variable is being hashed, and command substitution has already "
        "stripped its trailing newline — so this comparison can never pass:\n  "
        + "\n  ".join(offenders)
        + "\nHash the bytes instead: write them to a file and hash the file.")


def test_the_chooser_check_hashes_a_file_and_still_notices_an_empty_body():
    """The repair must not trade one silent failure for another.

    `[ -z "$served" ]` was the guard against the page having been deleted
    entirely, and it read a variable that no longer exists once the body goes to a
    file. Dropping it would turn a missing chooser — the panel's "Choose an
    existing one" button opening nothing — from a loud failure into a quiet pass,
    because two empty files hash alike."""
    text = (WORKFLOWS / "publish-docs.yml").read_text(encoding="utf-8")
    guard = text.split("scrapex-picker.html is the only part", 1)
    assert len(guard) == 2, "the chooser drift guard is no longer in this workflow"
    body = guard[1]

    assert "-o " in body and "sha256sum" in body, (
        "the chooser check no longer writes the served body to a file before "
        "hashing it")
    assert re.search(r"\[\s*!\s*-s\s", body), (
        "nothing checks that the served body is non-empty any more, so a deleted "
        "chooser would hash equal to another deleted chooser and pass")
