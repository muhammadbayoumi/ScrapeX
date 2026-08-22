"""The release the documents tell him to cut must be the release that would run.

WHAT HAPPENED, and it is the whole reason this file exists. On 2026-08-22 the
Settings panel read *Latest version 0.2.1* while `scrapex/version.py:76` said
`VERSION = "0.3.0"`. Nothing was broken: the panel reads the published manifest
correctly, the manifest says 0.2.1 correctly, and `git tag` lists exactly one
engine tag — `engine-v0.2.1`. The release simply was never cut. `OP-32` in
`docs/BACKLOG.md` had recorded that on 2026-08-21 and named the way out:

    git tag engine-v0.2.2 && git push origin engine-v0.2.2

**And by then that command could not work.** `VERSION` moved to 0.2.2 at
`adf31b2`, then to 0.3.0 at `e963269`, and the first step of
`.github/workflows/release-engine.yml` is `test "$tag" = "$version"` — so the
release the repository was telling him to cut would be REFUSED before anything
was built. Six places said 0.2.2 — two the whole command to copy, three the
sentence telling him to cut it, one a note about a past failure. Nothing compared
any of them with the number in the source, so the instruction rotted the moment
`VERSION` moved, in the registers a session reads before it decides what to do
(**C1**).

THE RULE, and it is the narrowest one that catches this: **an engine release
NAMED AS AN INSTRUCTION must name `VERSION`.** Not every mention of a tag — a
document may say `engine-v0.2.1` shipped a black window as often as it likes,
because that is history and history does not move. What may not go stale is the
sentence a person acts on.

TWO SHAPES ARE ACTED ON, so both are matched: the command that gets copied
(`git tag engine-v…`) and the sentence that says to cut one (`cut engine-v…`).
A tag name in narrative prose is neither and is deliberately left alone.

WHY NOT ASK THE HUB, which is where "published" actually lives. A test that
fetched `ScrapeX/json/version.json` would be the most direct check imaginable and
this suite would then depend on somebody else's CDN: red on a train, red behind a
proxy, and — worse — GREEN AND VACUOUS wherever the fetch is skipped. This
repository has already paid for exactly that twice, in workflows that checked out
depth 1 and turned two date guards into permanent skips
(`tests/test_the_workflows_check_out_enough_history.py`). `git tag -l` was
rejected for the same reason: `actions/checkout@v4` fetches no tags by default,
so the docs tier would compare against an empty set and pass over anything.

So this reads two committed files and compares two strings. It cannot flake, and
it cannot pass by accident.

WHAT IT DOES NOT CLAIM. It cannot notice that no release has been cut — that is
the owner's decision, recorded as `OP-32` and `REQ-28`, and a test cannot make it
for him. What it guarantees is that when he acts on what the repository tells
him, the tag he pushes is the tag the workflow accepts.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scrapex.version import VERSION

# Reads the documents in CLAUDE.md's map, so it belongs to the docs tier — a
# documentation-only change is exactly the change that rots an instruction.
# See tests/test_the_docs_gate_is_complete.py.
pytestmark = pytest.mark.docs

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The documents C1 sends every session to read, plus the workflow whose own
#: header carries the command. The workflow is in scope because its comment is
#: copied by a person exactly like a document's is; being next to the check that
#: would refuse it does not stop it being read first.
#:
#: `docs/plans/` is OUT of scope for the reason the citation guard gives for
#: excluding it: those files are verbatim historical records, and a plan edited
#: after the fact stops being evidence of what was decided when.
INSTRUCTIONS_LIVE_IN = (
    "CLAUDE.md",
    "ENGINEERING.md",
    "docs/STATE.md",
    "docs/REQUESTS.md",
    "docs/RULINGS.md",
    "docs/BACKLOG.md",
    "docs/LESSONS.md",
    "docs/APPROACHES.md",
    ".github/workflows/release-engine.yml",
)

#: An engine release named as something to DO. The backtick is optional because
#: Markdown wraps the tag and the workflow's shell comment does not, and `\s+`
#: rather than a space because "cut\n`engine-v0.2.2`" is one instruction wrapped
#: across two lines — which is how one of the six copies was written, and a bare
#: space would have missed it.
INSTRUCTION = re.compile(
    r"(?:git\s+tag\s+|\bcut\s+`?)engine-v(\d+\.\d+\.\d+)", re.IGNORECASE)

#: The line in the release workflow that makes the rule above true rather than a
#: preference. Asserted here as well as in tests/test_the_two_release_paths.py
#: because this guard's entire justification is that a tag which disagrees with
#: VERSION is refused: delete that check and this file is measuring nothing.
TAG_MUST_EQUAL_VERSION = 'test "$tag" = "$version"'

RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-engine.yml"


def _named_releases() -> list[tuple[str, int, str]]:
    """Every instruction found, as (document, line, version)."""
    found = []
    for name in INSTRUCTIONS_LIVE_IN:
        text = (ROOT / name).read_text(encoding="utf-8")
        for match in INSTRUCTION.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((name, line, match.group(1)))
    return found


def test_the_documents_are_where_they_say_they_are():
    """A path that stopped existing would empty the search and pass over
    everything — the shape of vacuous green this whole file is arranged to
    avoid."""
    missing = [name for name in INSTRUCTIONS_LIVE_IN
               if not (ROOT / name).is_file()]
    assert not missing, f"these are named here and are not in the repository: {missing}"


def test_the_places_a_release_instruction_actually_lives_cannot_leave_the_scope():
    """The set can be shrunk one path at a time and every assertion above stays
    green, because the remaining paths still hold an instruction.

    Proved by mutation: dropping `docs/STATE.md` and `docs/BACKLOG.md` from the
    tuple left the whole file passing, and those are the two documents that
    carried four of the six stale copies. So the members that matter are named
    rather than counted — a floor would have to be lowered every time an entry is
    struck, and the number is not what makes this guard work.
    """
    for required in ("docs/STATE.md", "docs/BACKLOG.md", "docs/REQUESTS.md",
                     ".github/workflows/release-engine.yml"):
        assert required in INSTRUCTIONS_LIVE_IN, (
            f"{required} is out of scope, and it is one of the places a release "
            "instruction is actually written. Removing it does not fail anything "
            "else here")


def test_every_release_the_documents_ask_for_is_the_release_that_would_run():
    """THE GUARD. A documented tag that is not `VERSION` is a failed release.

    The failure is not subtle when it happens — the workflow stops at its first
    step — but it is completely invisible until somebody tries, and the person
    who tries is the owner, on the day he finally has time to ship.

    FINDING NOTHING IS A PASS, AND THAT IS A CORRECTION MADE ON EVIDENCE. This
    test used to `assert named` first, on the reasoning that a guard matching
    nothing is measuring nothing. Then `engine-v0.3.0` was released on
    2026-08-22, every documented instruction correctly became history, and the
    set went empty — so the assertion failed on the repository being in exactly
    the state it should be in. **No release is owed between a release and the next
    contract change, and a guard that demands one forces a document to carry a
    fake instruction to stay green.** Non-vacuity is proved instead by
    `test_a_tag_named_in_narrative_prose_is_left_alone`, which runs the pattern
    against known shapes and needs no live instruction to do it.
    """
    named = _named_releases()

    wrong = [(name, line, version) for name, line, version in named
             if version != VERSION]
    assert not wrong, (
        "these documents tell him to cut a release the workflow would refuse "
        f"before it built anything — scrapex/version.py says VERSION = {VERSION!r} "
        f"and {RELEASE_WORKFLOW.name} checks {TAG_MUST_EQUAL_VERSION}:\n  "
        + "\n  ".join(f"{name}:{line} says engine-v{version}"
                      for name, line, version in wrong)
        + "\n\nA tag name in narrative prose is fine and is not matched. This is "
          "an instruction: either update it to the version in the source, or "
          "write it as history rather than as something to do.")


def test_the_check_that_makes_this_rule_real_is_still_in_the_workflow():
    """Without it a documented tag could be any number and nothing would care,
    and this file would be enforcing a rule the release path no longer has."""
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert TAG_MUST_EQUAL_VERSION in workflow, (
        f"{RELEASE_WORKFLOW.name} no longer refuses a tag that disagrees with "
        "scrapex/version.py:VERSION, so a release can be cut under any number "
        "and the guard beside this one is enforcing nothing")


def test_a_tag_named_in_narrative_prose_is_left_alone():
    """The rule has to be narrow or it falsifies history to stay green.

    `engine-v0.2.1` shipped the black window, and every document that says so is
    correct for ever. A guard that demanded every tag name equal VERSION would
    force those sentences to be rewritten on each bump, which is how a test comes
    to be satisfied by a lie.

    AND THIS IS ALSO THE NON-VACUITY PROOF for the guard above, which is why it
    asserts both directions on fixed strings: the pattern must still match the
    shapes a person acts on even when no document currently holds one. A guard
    whose only evidence of working is a live instruction stops being checkable at
    the moment the work is done.
    """
    history = ("The black window shipped in engine-v0.2.1, and engine-v0.2.1 is "
               "commit 4386d25.")
    assert not INSTRUCTION.findall(history)

    for instruction in ("git tag engine-v9.9.9 && git push origin engine-v9.9.9",
                        "Cut `engine-v9.9.9`.",
                        "**Next action:** cut\n`engine-v9.9.9`, then swap."):
        assert INSTRUCTION.findall(instruction) == ["9.9.9"], (
            f"an instruction this guard must read is not matched: {instruction!r}")


def test_the_pattern_cannot_tell_the_tense_of_cut_apart():
    """A KNOWN LIMIT, asserted so it is a documented constraint and not a surprise.

    `cut engine-v0.3.0` is matched whether it means *"cut this"* or *"he cut
    this"*. English puts the imperative and the past tense of `cut` in the same
    letters, and no regex over prose recovers the difference.

    THIS COST A REWORDING RATHER THAN A DEFECT, which is the direction to err in:
    after the release, `Q-16` read *"Hours later he cut `engine-v0.3.0`"* — true,
    finished, and matched as though it were an instruction. It passed only because
    0.3.0 was still `VERSION`, and would have failed at the next contract change.
    It now reads *"he tagged"*.

    So the discipline, recorded here because the next person will hit it: **write a
    completed release with any verb but `cut`** — tagged, published, released, went
    out. A false positive costs one word; a false negative costs a stale
    instruction the release workflow refuses.
    """
    assert INSTRUCTION.findall("Hours later he cut `engine-v0.3.0`.") == ["0.3.0"]

    for finished in ("Hours later he tagged `engine-v0.3.0`.",
                     "`engine-v0.3.0` was published on 2026-08-22.",
                     "The release engine-v0.3.0 went out that afternoon."):
        assert not INSTRUCTION.findall(finished), (
            f"this is finished history and must not be read as an instruction: "
            f"{finished!r}")
