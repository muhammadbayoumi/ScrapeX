"""Two sessions cannot take the same register number without the build going red.

WHAT HAPPENED ON 2026-08-21. Two branches were open at once. `#244` recorded `R-36` and
`R-37`; this session recorded `R-36`, `R-37`, `R-38` and `R-39` for four rulings of his.
Both were green. Both were mergeable. Merging them produced **two `R-36` and two
`R-37`**, which makes every citation to either one ambiguous.

NEITHER PROCESS RULE WOULD HAVE CAUGHT IT.
[R-18](../docs/RULINGS.md) — *merge it when it is green* — sees two green branches.
[R-37](../docs/RULINGS.md) — *the agent does not merge* — catches it only if a person
reads both diffs, which is what actually happened and happened by luck: the collision was
found because he asked for a conflict check. Branch protection would not catch it either;
both branches were green and up to date. **Git cannot see a semantic conflict, and this
one is semantic.**

So it becomes a test, which is what `R-15` already says about this documentation system:
*"the documents are guarded by a test, not by good intentions."*

TWO ASSERTIONS, AND THE SECOND IS THE USEFUL ONE.

  * **No duplicates** — the collision itself.
  * **No gaps** — which is a stronger signal than it looks. `C4` says a superseded ruling
    **stays** in place rather than being deleted, so a register is contiguous by
    construction and a hole means one of two things: a number was skipped, or *this
    branch does not yet have another session's entries*. The second is exactly the state
    in which a collision is about to be created. Measured while writing this: on this
    branch `R` had holes at 36 and 37 — the two numbers `#244` had taken and this branch
    had not yet seen.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: THIS GUARD BELONGS IN THE DOCS TIER, and unlike the extension case the marker costs
#: nothing here. A register collision is created by editing a document, so a
#: documentation-only change is precisely when this must run — the tier and the subject
#: agree. `test_the_docs_gate_is_complete` asked for it and it is right to.
pytestmark = pytest.mark.docs

#: The four registers whose entries are `###` headings, which is what makes them
#: countable. `Q-nn` is deliberately absent: it is written in bold rather than as a
#: heading, and `Q-14` legitimately appears twice — once as asked and once as answered —
#: so guarding it would produce a failure that is not a defect.
REGISTERS = (
    ("docs/RULINGS.md", "R", "a decision the owner has taken"),
    ("docs/REQUESTS.md", "REQ", "something the owner asked for"),
    ("docs/BACKLOG.md", "OP", "an open problem we found"),
    ("docs/BACKLOG.md", "DEC", "a decision we owe"),
)


def _numbers(document: str, prefix: str) -> list[int]:
    """Every number this register uses, in the order the file lists them.

    THE PATTERN IS ANCHORED TO A HEADING, not to the bare token. `RULINGS.md` mentions
    `R-19` dozens of times in prose and links; only a `### R-19 · …` line declares it. A
    test that counted mentions would report every cross-reference as a duplicate.
    """
    text = (ROOT / document).read_text(encoding="utf-8")
    return [int(found) for found in
            re.findall(rf"^#{{2,4}} +{prefix}-0*(\d+)", text, re.MULTILINE)]


@pytest.mark.parametrize(("document", "prefix", "what"), REGISTERS,
                         ids=[f"{prefix}-in-{Path(doc).name}"
                              for doc, prefix, _ in REGISTERS])
def test_no_two_entries_share_a_number(document: str, prefix: str, what: str):
    """THE COLLISION GUARD. Whichever pull request merges second goes red."""
    numbers = _numbers(document, prefix)
    repeated = sorted({n for n in numbers if numbers.count(n) > 1})

    assert not repeated, (
        f"{document} declares {prefix}-{repeated[0]:02d} more than once "
        f"({len(repeated)} number(s) repeated: {repeated}). Two sessions took the same "
        f"number for {what}, so a citation to it now names two things. The next free "
        f"number is {prefix}-{max(numbers) + 1:02d}.")


#: NUMBERS THAT WERE DELETED AND WILL NEVER COME BACK, which is the OPPOSITE of a
#: reservation and must not share its table.
#:
#: A RESERVED row says "this hole is filled on another branch, delete the row when it
#: lands". A RETIRED row says "this hole is permanent, and here is what replaced it". Using
#: RESERVED for a deletion would be exactly the laundering its own comment warns about: a
#: row whose holder can never arrive, reading as deliberate for ever.
#:
#: A RETIRED NUMBER IS NEVER REUSED. `REQUESTS.md` states the convention the registers
#: share -- "IDs are stable and never reused" -- and a deleted entry does not release its
#: number, because every citation ever written to it would then point at something else.
#: That is the one property a deletion must not cost.
#:
#: THIS EXISTS BECAUSE `C4` WAS OVERRIDDEN BY THE OWNER, once, in writing. `C4` says a
#: superseded ruling STAYS, marked -- which is why the gap check could assume contiguity in
#: the first place. On 2026-08-30 he deleted the five version rulings outright: «احذف كل
#: الاحكام او القرارات الخاصة ب version» and «احذف الكل واكتبه فى بند واحد غير متناثرين»,
#: on the ground that five scattered entries were the cause of the failure `R-77` records --
#: two sessions reading the same two documents, reaching opposite conclusions, and neither
#: reaching the ruling that governed. The history is in `git log docs/RULINGS.md`; what this
#: table preserves is the POINTER, so a reader who follows a dead citation lands somewhere.
RETIRED: dict[str, dict[int, str]] = {
    "R": dict.fromkeys((5, 6, 7, 35, 61), "deleted 2026-08-30, replaced by R-77"),
}

#: NUMBERS AN OPEN PULL REQUEST ALREADY HOLDS, and why this list has to exist.
#:
#: Contiguity is a property of `main`, not of a branch. A branch that deliberately skips a
#: number to avoid colliding with another session's open pull request CANNOT be contiguous
#: — and the first version of this guard failed exactly that branch, correctly by its own
#: rule and unhelpfully in fact.
#:
#: So a reservation is DECLARED rather than tolerated, the way `PINNED` declares a citation
#: in the guard next door. Two things follow: the gap check knows the hole is deliberate,
#: and the next session reads WHOSE it is instead of reusing it. **Delete the row when that
#: pull request merges** — a reservation left behind is a permanent hole nobody owns.
#:
#: A ROW HERE IS A CLAIM ABOUT THE WORLD, AND IT ROTS LIKE A LINE CITATION DOES. It is
#: not merely stale when its holder disappears — it is actively worse than the hole it
#: covers, because **a reservation whose owner does not exist launders an orphan into a
#: passing test, and reads as deliberate.** The gap check then reports nothing while the
#: register has a permanent wart in it, which is the failure mode this whole file exists
#: to prevent, one level up.
#:
#: Hence: **name a holder a reader can VERIFY** — a branch ref or a pull request number,
#: never a description of a session. Two reasons, both met on 2026-08-22. Sessions do not
#: outlive their branches, so "the Drive session" is unresolvable six weeks later. And the
#: claim may be unverifiable from the repository at the time it is written: an unpushed
#: renumber is invisible on `origin` and still real, which is how the row for 44 below was
#: briefly attributed to the wrong branch. A ref can be checked with `git ls-remote`; a
#: description cannot be checked at all. **The row is only as fresh as the last person who
#: checked it, so re-check before trusting it.**
RESERVED: dict[str, dict[int, str]] = {
    # R-46 belongs to `claude/drive-without-a-server` (pushed at e00711d, no PR
    # yet), and this branch declares R-47 -- so 46 is a hole here that exists
    # elsewhere. Delete this row the day that branch merges.
    # R-80 belongs to `claude/scrapex-engine-consolidation-d69e0a` (pushed, PR #293,
    # unmerged), and this branch declares R-81 -- so 80 is a hole here that exists
    # elsewhere. VERIFIED against the ref, not taken from a message:
    #   git show claude/scrapex-engine-consolidation-d69e0a:docs/RULINGS.md | grep "### R-80"
    # Delete this row the day #293 merges.
    "R": {46: "branch claude/drive-without-a-server",
          80: "branch claude/scrapex-engine-consolidation-d69e0a, PR #293"},
    # DECLARED HOLES, not tolerated ones. Both numbers exist on other branches and
    # not on this one, which is the state this table is for -- and being handed a
    # number by another session is not enough on its own: the assignment that named
    # this guard without naming this mechanism nearly turned a sibling branch red.
    #
    # DELETE A ROW THE MOMENT ITS PR LANDS. A reservation left behind is a permanent
    # hole nobody owns, which is the rule the comment above already states.
    "REQ": {
        34: "branch claude/drive-without-a-server",
        # 50 is declared on `claude/scrapex-engine-consolidation-d69e0a` (PR #293,
        # pushed, unmerged) and this branch declares 51 over the top of it. VERIFIED
        # against the ref rather than taken from a message:
        #   git show claude/scrapex-engine-consolidation-d69e0a:docs/REQUESTS.md \n        #     | grep "^## REQ-50"
        # Delete this row the day #293 merges.
        50: "branch claude/scrapex-engine-consolidation-d69e0a, PR #293",
        # 43 belongs to `feat/organization-enrichment`, which is pushed and unmerged.
        # 41 and 42 were reserved to #267 and their rows are GONE because #267 has
        # landed -- which is the rule this table states about itself. Delete this row
        # the day that branch lands too.
        43: "branch feat/organization-enrichment",
        # 46 and 47 ADDED 2026-08-28 by `feat/the-supabase-appearance-is-a-design-system`,
        # which took REQ-48 over the top of them and so created the holes it declares.
        # Both are INVISIBLE claims -- the sweep run before taking 48 found neither number
        # declared as a heading in any of the 236 local and remote refs -- and both are
        # real, which is the exact state §3 of ORCHESTRATION.md says to step over rather
        # than trust the repository about.
        #
        # 46: `docs/STATE.md` records the dry-route work asking the primary for a REQ
        # number and noting 46 was free across all 419 refs on 2026-08-27. That work
        # merged as #274 WITHOUT taking one, so the claim outlived its pull request and
        # the number is still spoken for by a follow-up nobody has written yet. Verify by
        # reading the "Awaiting the primary" line in STATE.md, not by grepping REQUESTS.md
        # -- grepping is what would hand it out twice.
        46: "PR #274's follow-up, per docs/STATE.md 'Awaiting the primary'",
        # 47: `docs/BACKLOG.md`'s review row for `feat/organization-enrichment` instructs
        # that branch to renumber its colliding REQ-44 to REQ-47. The branch is pushed,
        # has no open PR, and still declares 43 and 44 on `origin` -- so the renumber is
        # recommended-and-unperformed, which is a claim on 47 either way.
        47: "branch feat/organization-enrichment, per docs/BACKLOG.md's renumber row",
    },
    # #246 merged on 2026-08-22 and brought its own 39 and 40, so the reservation is
    # gone with it — which is the rule the comment above states: a row left behind is a
    # permanent hole nobody owns.
    #
    # 45 is held by branch `claude/drive-without-a-server`, which also holds 49 and 50.
    # NOT verifiable from the repository, and the row says so on purpose: that branch's
    # renumber is unpushed, so `origin` shows it topping out at `OP-43`. The claim is real
    # and invisible, so this row rests on the assigning session's word rather than on a
    # ref anyone can read. Re-check it rather than inheriting it.
    #
    # WHO DELETES A ROW: the branch that CREATED the reservation, unless the branch that
    # fills it has already merged. So this row is deleted by whichever pull request
    # follows the Drive branch — not by this one, which merges before it and would leave a
    # real hole undeclared.
    #
    # 44's ROW WAS HERE AND IS GONE, which is the rule working rather than an omission.
    # #255 merged on 2026-08-22 (`bcb8f6e`) and brought `### OP-44 · A dataset card said
    # "no successful crawl yet" over 17,304 crawled rows`, so the number stopped being a
    # hole and became a heading. Leaving the row would have failed
    # `test_a_reserved_number_is_not_also_declared` — reserved AND declared at once — and
    # that failure was PREDICTED from the tree before #255 merged rather than discovered
    # from a red build afterwards.
    #
    # 44 was also briefly attributed to the wrong branch here, and that is worth keeping
    # now that the row is gone. The Drive branch held 44 and 45, then moved off 44
    # precisely BECAUSE #255 had it, and a message describing only what changed on the
    # Drive side read as 44 having been released. The row passed the gap check the whole
    # time it named a holder that no longer held it — exactly the laundering the paragraph
    # above describes. Nothing caught it; asking who holds 44 did.
    #
    # NOTE TO WHOEVER TAKES AN ASSIGNED NUMBER NEXT: being handed "take OP-46" is not
    # enough. If the numbers below yours are not in your branch, the hole check fails on
    # YOUR branch, and declaring them here is what satisfies it — that is what this table
    # is, and it was nearly missed on 2026-08-22 because the assignment named the guard
    # without naming the mechanism.
    # 49..52 ADDED 2026-08-22 by `feat/the-source-page-moves-into-the-extension`, which
    # took OP-53..59 over the top of them and so created the hole it is declaring. 51 and
    # 52 are verifiable — `#258` is open and its branch is on `origin`. 49 and 50 rest on
    # the same unpushed Drive renumber as 45 above, so re-check them rather than
    # inheriting them.
    #
    # Each row is deleted by whichever pull request follows its holder's merge, per the
    # rule above — NOT by this branch, which merges before both and would otherwise leave
    # a real hole undeclared.
    # 60 AND 61 WERE HERE AND ARE NOT ANY MORE. #265 created both rows, naming this
    # very branch as their holder, and #265 has merged — so by this file's own rule
    # ("delete a row the moment its PR lands... unless the branch that fills the
    # number has already merged") the branch that FILLS them deletes them, which is
    # this one. `OP-60` and `OP-61` are now DECLARED in docs/BACKLOG.md, and a number
    # that is reserved AND declared fails test_a_reserved_number_is_not_also_declared.
    # Nothing else was touched.
    "OP": {
        45: "branch claude/drive-without-a-server",
        # 101 THROUGH 110 WERE RESERVED HERE AND THE ROWS ARE GONE, which is this
        # table's own rule applied to itself: `claude/design-system-review-d6787a`
        # merged, so the numbers are declared on `main` and a reservation for a
        # declared number is a contradiction -- `test_a_reserved_number_is_not_also
        # _declared` says so, and it is what caught the rows on this rebase.
        #
        # WORTH KEEPING FROM THE HOUR THEY EXISTED: `git ls-remote` is the WRONG
        # check for whether a number is claimed, and it fails in the direction that
        # hurts. Every worktree under `.claude/worktrees/` shares one ref namespace
        # with the main checkout, so a sibling session's local-only branch shows up
        # in `git branch -a` and not in `ls-remote` at all. "Has it been pushed" is
        # a different question from "has it been claimed"; this table is about the
        # second, and that advice was given once on 2026-08-30 and would have
        # reported a held number as free.
        #
        # 111 IS NOT RESERVED EITHER, FOR THE SAME REASON, ONE MERGE LATER:
        # `claude/the-backup-that-uploaded-nothing` landed as #296 while this
        # branch was in flight, so OP-111 is declared on `main` and a row for it
        # would be the contradiction the paragraph above describes. Twice in one
        # day, caught both times by the same assertion.
        #
        # 112-114 REMAIN, and each names a ref that `git rev-parse --verify`
        # resolves, checked with `git show <ref>:docs/BACKLOG.md` rather than
        # taken from the message that allocated them.
        #
        # A RESERVATION MAY BE TAKEN BEFORE ITS HOLDER HAS COMMITTED ANYTHING,
        # which the rule above does not say and which cost an hour here. These
        # three were allocated by the primary session and declared by no ref
        # anywhere -- a search of refs/heads and refs/remotes found nothing -- so
        # the only holder that could be written was a session name, which is the
        # form the rule forbids, because sessions do not outlive their branches.
        # A row whose holder has no ref yet must SAY SO and be RE-CHECKED: it is
        # the orphan the comment above warns about, it just has not become one
        # yet. Re-checking is what turned these three into refs.
        112: "branch claude/scrapex-engine-consolidation-d69e0a",
        # 116 is `claude/the-guard-that-reads-half-the-product` (PR #297, pushed) --
        # VERIFIED with `git show <ref>:docs/BACKLOG.md | grep "^### OP-116"`.
        # 116's row is GONE: #297 merged, so the number is a heading and a reservation for
        # a declared number fails the assertion below -- the fourth time that guard has
        # noticed before a session did on 2026-08-30.
        #
        # 117 WAS CLAIMED BY MESSAGE ONLY for about an hour, and this row said so in
        # those words: allocated to the Drive session with no ref declaring it. It has
        # one now (PR #300), and the re-check the row asked for is what produced this
        # line. **The claimed-by-message state is real and short**, which is exactly why
        # a row in it must say which kind of claim it is holding rather than read like
        # a verified one.
        117: "branch claude/marketlens-is-gone, PR #300",
        113: "branch claude/scrapex-engine-consolidation-d69e0a",
        114: "branch claude/scrapex-engine-consolidation-d69e0a",
        #
        # AND 115 IS GONE TOO, ONE MERGE LATER AGAIN. `#295` landed while this
        # branch was in flight, so `OP-115` is declared and its row would be the
        # same contradiction. THREE TIMES IN ONE DAY, from three unrelated
        # merges, and every one was caught by
        # `test_a_reserved_number_is_not_also_declared` rather than by the
        # session doing the rebase.
        #
        # That is the whole argument of `LESSONS` 29's counterexample, measured
        # three times: this assertion compares two things that are maintained
        # SEPARATELY -- the reservations and the headings -- so it does not
        # matter which side moves, and nobody has to remember to look.
        #
        # 112-114 remain. Each names a ref that `git rev-parse --verify`
        # resolves, checked with `git show <ref>:docs/BACKLOG.md` rather than
        # taken from the message that allocated them. They spent about an hour
        # with no ref at all, when the only holder that could be written was a
        # session name -- the form this comment forbids. A row in that state
        # must SAY SO and be re-checked; re-checking is what turned them into
        # refs.
        112: "branch claude/scrapex-engine-consolidation-d69e0a",
        113: "branch claude/scrapex-engine-consolidation-d69e0a",
        114: "branch claude/scrapex-engine-consolidation-d69e0a",
        # 64 THROUGH 68 BELONG TO `docs/two-counts-and-the-gap-between-them` (PR #267,
        # open). They became holes HERE the moment this branch declared `OP-69`, because
        # the gap check runs from 1 to `max(numbers)`. #267 has an open pull request and
        # this branch's own claim came later, so #267 keeps them under the rule that an
        # open PR outranks a bare branch -- and the five rows are the cost of skipping
        # past them rather than arguing over them. Delete all five the day #267 merges.
        # 49 AND 50 ARE NEW ON THIS BRANCH AND NOT NEW IN THE WORLD. The Drive
        # branch has held all three of 45, 49 and 50 since before #255; they only
        # became holes HERE when this branch declared `OP-51` and `OP-52`, because
        # the gap check runs from 1 to `max(numbers)` and nothing below the maximum
        # may be missing. Same holder, same deletion rule as 45 above: the pull
        # request that follows the Drive branch removes all three together.
        49: "branch claude/drive-without-a-server",
        50: "branch claude/drive-without-a-server",
    },
    "DEC": {},
}


@pytest.mark.parametrize(("document", "prefix", "what"), REGISTERS,
                         ids=[f"{prefix}-in-{Path(doc).name}"
                              for doc, prefix, _ in REGISTERS])
def test_the_numbers_run_without_a_hole(document: str, prefix: str, what: str):
    """A HOLE MEANS A COLLISION IS COMING, most of the time.

    `C4` keeps a superseded entry in place and marks it, so nothing is ever removed and
    the sequence is contiguous by construction. A gap therefore means either a number was
    skipped — in which case the next session will reuse it and collide — or this branch is
    missing entries another branch has already merged, which is the state a collision is
    created from.

    Measured 2026-08-21: this branch showed holes at `R-36` and `R-37`, which were exactly
    the two numbers `#244` had taken and this branch had not yet rebased onto.
    """
    numbers = _numbers(document, prefix)
    assert numbers, f"{document} declares no {prefix}- entries at all"
    reserved = RESERVED.get(prefix, {})
    retired = RETIRED.get(prefix, {})
    missing = sorted(set(range(1, max(numbers) + 1))
                     - set(numbers) - set(reserved) - set(retired))

    assert not missing, (
        f"{document} has no {prefix}-{missing[0]:02d} but does have "
        f"{prefix}-{max(numbers):02d}. Missing: {missing}. Either a number was skipped — "
        f"and the next session will reuse it — or this branch has not got another "
        f"branch's entries yet, which is how two sessions end up writing the same one. "
        f"Rebase onto main before adding {prefix}-{max(numbers) + 1:02d}.")


def test_the_guard_reads_the_registers_it_claims_to():
    """A PARAMETERISED TEST THAT MATCHED NOTHING WOULD PASS EVERY CASE, which is how a
    guard becomes decoration. This asserts the patterns actually find entries, with
    floors low enough not to need editing every time one is added."""
    found = {prefix: len(_numbers(document, prefix))
             for document, prefix, _ in REGISTERS}

    assert found["R"] >= 39, found
    assert found["REQ"] >= 27, found
    assert found["OP"] >= 32, found
    assert found["DEC"] >= 12, found


def test_a_reserved_number_is_not_also_declared():
    """A RESERVATION AND A HEADING ARE CONTRADICTORY. If a number is both reserved for
    another branch and declared here, then the collision the reservation exists to avoid
    has already happened and the gap check is looking the other way."""
    for document, prefix, _what in REGISTERS:
        held = set(RESERVED.get(prefix, {}))
        assert held.isdisjoint(_numbers(document, prefix)), (
            f"{prefix}: {sorted(held & set(_numbers(document, prefix)))} is reserved for "
            f"another branch AND declared in {document}")


def test_a_retired_number_is_not_reserved_and_not_redeclared():
    """THE TWO TABLES MEAN OPPOSITE THINGS, so a number in both is a contradiction: it
    cannot be permanently gone and also arriving on someone's branch. And a RETIRED number
    that reappears as a heading is the reuse that breaks every citation written to it --
    `REQUESTS.md` says IDs are stable and never reused, and this is where that is enforced
    rather than hoped for."""
    for document, prefix, _what in REGISTERS:
        gone = set(RETIRED.get(prefix, {}))
        held = set(RESERVED.get(prefix, {}))
        assert gone.isdisjoint(held), (
            f"{prefix}: {sorted(gone & held)} is both retired and reserved -- one of the "
            "two rows is wrong, and they cannot both be right")
        assert gone.isdisjoint(_numbers(document, prefix)), (
            f"{prefix}: {sorted(gone & set(_numbers(document, prefix)))} was retired and "
            f"has been declared again in {document}. A retired number is never reused: "
            "every citation ever written to it would now name something else.")


def test_every_retired_number_names_what_replaced_it():
    """A RETIRED ROW WITHOUT A DESTINATION IS WORSE THAN THE HOLE. The whole reason the
    table exists is so a reader following a dead citation lands somewhere; a row saying
    only "deleted" sends them nowhere and reads as deliberate, which is the laundering the
    RESERVED comment warns about one table up."""
    for prefix, rows in RETIRED.items():
        for number, note in rows.items():
            assert re.search(r"\b(R|REQ|OP|DEC)-\d+", note), (
                f"{prefix}-{number:02d} is retired with the note {note!r}, which names no "
                "replacement. Say what took its place.")


def test_a_duplicate_would_actually_be_caught(tmp_path: Path):
    """THE GUARD, MUTATED BY HAND. `_numbers` is the whole of it, so a pattern that
    silently stopped matching headings would make both tests above vacuous — and this
    proves the counting distinguishes a real duplicate from a cross-reference.
    """
    document = tmp_path / "fake.md"
    document.write_text(
        "### R-01 · first\n"
        "prose citing R-01 and R-02 and R-99 in passing\n"
        "### R-02 · second\n"
        "### R-02 · a second session took the same number\n",
        encoding="utf-8")

    numbers = [int(found) for found in re.findall(
        r"^#{2,4} +R-0*(\d+)", document.read_text(encoding="utf-8"), re.MULTILINE)]

    assert numbers == [1, 2, 2], "headings only — the prose mentions must not count"
    assert sorted({n for n in numbers if numbers.count(n) > 1}) == [2]
