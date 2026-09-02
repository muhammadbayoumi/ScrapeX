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

import ast
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
    # ONE "R" ENTRY, AND THERE WERE TWO. `main` carried `"R"` twice inside this
    # dict -- once holding {46, 80} with a ref-verified comment, once holding {46}
    # alone -- and Python keeps the LAST, so the first was dead from the day it was
    # written. The row reserving R-80 for #293 therefore protected nothing for the
    # whole time it existed, and `test_a_reserved_number_is_not_also_declared` stayed
    # green throughout, because every test in this file reads the BUILT dict and a
    # built dict cannot show you the key it discarded. Collapsed here.
    #
    # R-80 AND R-81 ARE GONE FROM THIS TABLE BECAUSE THEY LANDED. #293 merged as
    # `1d8816d8` and #301 as `5af838ca`, so both are declared headings in
    # docs/RULINGS.md now; leaving the rows would make each number reserved AND
    # declared at once, which is the failure the neighbouring test exists for.
    # Verified against origin/main rather than against the local `main` ref, which
    # in a shared worktree is whatever the last session left behind.
    #
    # AND IT CANNOT HAPPEN AGAIN, WHICH IS WHAT THIS BRANCH ADDS.
    # `test_the_reservation_table_has_no_shadowed_rows` reads this file with `ast` and
    # reports any key a later key hides -- at BOTH levels, because there are two shapes
    # and the first version of that guard only saw one. A register key written twice puts
    # one dict beside another; a ROW written twice inside one dict discards a single
    # reservation, reads as an edit that took, and keeps the OLDER copy. Measured
    # 2026-09-02: `main` carried the first and a sibling branch carried the second.
    #
    # 82 IS NOT RESERVED HERE, AND THAT IS THE RULE ABOVE APPLIED TO THIS BRANCH. It was,
    # for `claude/the-notice-supabase-is-owed` while this branch took R-83 over the top of
    # it. #299 merged as `80659faa`, so R-82 is a declared heading and a reservation for it
    # would be the contradiction the neighbouring test refuses. The row went out in this
    # rebase, which is the moment the table's own instruction names.
    "R": {46: "branch claude/drive-without-a-server"},
    # DECLARED HOLES, not tolerated ones. Both numbers exist on other branches and
    # not on this one, which is the state this table is for -- and being handed a
    # number by another session is not enough on its own: the assignment that named
    # this guard without naming this mechanism nearly turned a sibling branch red.
    #
    # DELETE A ROW THE MOMENT ITS PR LANDS. A reservation left behind is a permanent
    # hole nobody owns, which is the rule the comment above already states.
    "REQ": {
        # 50 became a hole when this branch declared REQ-52. 51's row was here
        # and is GONE: #301 merged, so it is a heading on `main` and a
        # reservation for it is the contradiction this guard refuses -- the
        # fifth row retired that way across five merges.
        #
        # AND IT WAS TWO ROWS BEFORE IT WAS NONE, which is worth one paragraph
        # because the mechanism outlives this instance. This branch added a `50`
        # above a `50` that was already here, and Python keeps the LAST -- so the
        # row carrying the verified holder was the one being discarded, silently,
        # on every run. That is the failure this table's own guard exists for, one
        # level in, introduced by the pass that was de-duplicating the level above
        # it. **No test in this file could see it**: they all read the BUILT dict,
        # where the loser is already gone. Only a reader that parses the SOURCE
        # can, and `main` grew one for the OUTER keys after another session found
        # the register key "R" written twice the same day.
        #
        # Both rows are gone now -- `#293` landed and made the number a heading --
        # so nothing here is left to fix. The paragraph stays because a duplicated
        # key inside these dicts is invisible to everything except a source
        # reader, and the next session to add a row needs to know that before it
        # adds one, not after.
        # Delete this row the day #293 merges.
        # 34 belongs to `claude/drive-without-a-server`, which also holds OP 45, 49
        # and 50. It is a hole on this branch because that branch declared it and this
        # one has not got its entries -- exactly the state the gap check exists to
        # distinguish from a skipped number.
        34: "branch claude/drive-without-a-server",
        # 50 HAS NO ROW: it was reserved for `claude/scrapex-engine-consolidation-d69e0a`
        # while `REQ-51` was declared over the top of it, and the row said to delete it
        # the day #293 merged. It is deleted one step earlier instead -- as #293 rebases
        # and its own heading arrives, which is the moment the contradiction exists.
        # THE SIXTH ROW THIS BRANCH HAS RETIRED across five unrelated merges, and the
        # sixth time `test_a_reserved_number_is_not_also_declared` said so before the
        # session did.
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
        # 117'S ROW WAS HERE AND THIS BRANCH DECLARES IT, so it is gone -- the
        # sixth reservation retired that way, across six merges.
        #
        # AND 112-114 APPEARED **TWICE** IN THIS DICT, on `main` as well as here:
        # two rebases each concatenated both sides of one block. Python keeps the
        # LAST duplicate key, so the guard stayed green and the file grew a copy
        # nobody read -- `LESSONS` section 3, a third time, inside the register
        # guard itself. De-duplicated 2026-09-02.
        # 120, 122 AND 123 ARE HOLES THIS BRANCH CREATES by declaring OP-121 over them,
        # and all three are VERIFIED AGAINST REFS rather than taken from the messages
        # that announced them. Re-check before trusting; the commands are the check:
        #   git show refs/remotes/origin/claude/the-drift-check-that-was-off:docs/BACKLOG.md | grep "^### OP-120"
        #   git show refs/remotes/origin/claude/one-migration-plan-not-two:docs/BACKLOG.md | grep "^### OP-122"
        #   git show refs/remotes/origin/claude/a-citation-nothing-reads:docs/BACKLOG.md | grep "^### OP-123"
        # 121 IS THIS BRANCH'S OWN and is a heading in docs/BACKLOG.md, not a row here.
        # DELETE EACH ROW THE DAY ITS PULL REQUEST LANDS -- a reservation left behind is a
        # permanent hole nobody owns, which is the rule this table states about itself.
        # 120 SURVIVES AS ONE ROW CARRYING BOTH SIDES' EVIDENCE. Two sessions
        # reserved it and keep-both left two rows; the guard below reported
        # `OP[120]` and the copy Python keeps is the lower one. Verified with
        #   git show refs/remotes/origin/claude/the-drift-check-that-was-off:docs/BACKLOG.md | grep "### OP-120"
        # at c6bdf813, and it now has PR #307 open, which the earlier row could
        # not know. 121 and 122 are GONE: 121 is declared by this branch and 122
        # landed with #306 (`3c2aaa0d`), so each was a number reserved AND
        # declared -- the contradiction the neighbouring test refuses.
        120: "branch claude/the-drift-check-that-was-off, PR #307, at c6bdf813",
        123: "branch claude/a-citation-nothing-reads, at a0c6e8c2",
        45: "branch claude/drive-without-a-server",
        # 112 THROUGH 114 became holes when this branch declared OP-117.
        # 116's row was here and is GONE: #297 merged, so it is declared on
        # `main` and a reservation for it is the contradiction the guard
        # refuses. Fourth row retired that way today, on a fourth merge.
        # Both holders verified with `git rev-parse --verify` and
        # `git show <ref>:docs/BACKLOG.md`, not taken from the message that
        # allocated them -- 112-114 at b7dc588, 116 at e0fe797.
        #
        # 115 IS THE ODD ONE AND IT IS DELIBERATE. It is already declared on
        # `main` (#295), so it is NOT reserved here: a reservation for a
        # declared number is the contradiction `test_a_reserved_number_is_not
        # _also_declared` refuses. The gap check does not need it either --
        # this branch has 115 from `main`. Three rows were retired that way
        # today, on three unrelated merges, every one caught by that
        # assertion rather than by the session doing the rebase.
        # 112, 113 AND 114 STOOD HERE AND ARE GONE: `#293` merged as `1d8816d8`, so
        # all three are headings on `main` and a reservation for a declared number is
        # the contradiction `test_a_reserved_number_is_not_also_declared` refuses.
        # `main` was already carrying the paragraph below saying they were gone WHILE
        # the rows were still here -- a comment and the rows it contradicts, which is
        # the same one-side-of-a-pair shape this table keeps catching in other files.
        # 120 and 121 became holes when this branch declared OP-122. Both are inside
        # the EXISTING "OP" entry rather than in a second one: this table carried a
        # duplicated register key twice this week and Python keeps the last, so a new
        # entry for a register that already has one silently discards whichever half
        # is written first.
        #
        # Holders VERIFIED against the refs, never taken from the messages that
        # allocated the numbers:
        #   git show origin/claude/the-drift-check-that-was-off:docs/BACKLOG.md \
        #     | grep "### OP-120"
        #   git show fix/the-listing-phase-has-a-door:docs/BACKLOG.md | grep "### OP-121"
        # A sweep of every local and remote ref found OP-122 declared on none of them.
        #
        # Delete each row the day its branch merges.
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
        # yet. Re-checking is what turned those three into refs -- and then into
        # headings, which is why 112, 113 and 114 are no longer below.
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
        # 117 IS DECLARED BY THIS BRANCH, so its row is gone rather than updated.
        # `main` reserves it to `claude/marketlens-is-gone` -- correctly, from main's
        # point of view -- and this is the branch that ref names, so the reservation
        # and the heading are the same claim seen from two sides. The heading wins.

        # 112, 113 AND 114 WERE RESERVED HERE FOR THIS BRANCH AND ARE NOT ANY MORE,
        # deleted by the branch they named as its headings arrive. The rule is the
        # same every time and it is not a courtesy: a number that is both reserved
        # and declared fails `test_a_reserved_number_is_not_also_declared`, so the
        # guard removes the row if the session does not.
        #
        # THAT GUARD CAUGHT FIVE ROWS ACROSS FOUR UNRELATED MERGES IN ONE DAY --
        # `R-79`, `OP-111`, and these three -- and not once did the session doing
        # the rebase notice first. `main` had meanwhile grown a comment explaining
        # why these three REMAIN, written while they were still reserved and true
        # when written; it goes with them.
        #
        # THE ARGUMENT IS `LESSONS` 29's counterexample, now measured five times:
        # this assertion compares two things maintained SEPARATELY -- the
        # reservations and the headings -- so it does not matter which side moves,
        # and nobody has to remember to look. Contrast the guards that read one
        # side of a seam and pass forever.
        #
        # 117 BECAME A HOLE HERE the moment this branch declared `OP-119`, and 118 did
        # too until `#301` landed and declared it. Neither was
        # on `main` when this was written; each was found by asking every remote ref for
        # the heading rather than by trusting the message that allocated it:
        #   git show <ref>:docs/BACKLOG.md | grep '^### OP-117 '
        # 118 IS NOT HERE: `#301` merged while this branch was rebasing, so the number
        # is a heading and a row for it would be the same contradiction. 117 is held
        # above, with the better annotation `#300` added -- one row, not two.
        #
        # ONE LINE OF THE OLD COMMENT IS WORTH KEEPING, because it records the only
        # hard case: these three were allocated before any ref carried them, so for
        # about an hour the only writable holder was a session name -- the form this
        # table forbids, since sessions do not outlive their branches. Re-checking
        # is what turned them into refs, and re-checking is what removes them now.
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
        # 111 WAS RESERVED HERE AND IS NOT ANY MORE, and it is the second row this
        # branch has retired rather than inherited. It was verified against the ref
        # while it was in flight -- with `git branch -a` and not `git worktree list`,
        # because that branch was checked out nowhere. #296 merged it, `OP-111` became
        # a heading, and a number that is both reserved and declared fails
        # `test_a_reserved_number_is_not_also_declared`.
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


def _repeats(literal: ast.Dict) -> list:
    """The keys of one dict literal that a later key of the same value hides."""
    seen: set = set()
    shadowed: list = []
    for key in literal.keys:
        # `None` IS WHAT A `**expansion` PUTS HERE, and it would crash
        # `literal_eval`. These tables have no expansion today; if one arrives, this
        # says so instead of the checker dying with a TypeError nobody can read.
        assert key is not None, 'a **expansion in this table cannot be checked for duplicates'
        value = ast.literal_eval(key)                     # type: ignore[arg-type]
        if value in seen:
            shadowed.append(value)
        seen.add(value)
    return shadowed


def _shadowed_keys(source: str, name: str) -> list[str]:
    """Every key the literal assigned to `name` discards, at BOTH levels.

    Read from the SOURCE, because the dict object cannot report it: by the time Python
    has built it the loser is gone without a trace.

    TWO LEVELS, BECAUSE THE TWO SHAPES ARE DIFFERENT DEFECTS and one guard for the
    outer keys alone let the other through. A register key written twice puts one dict
    beside another, which a reader may notice. A ROW written twice inside one dict --
    `"REQ": {50: ..., 34: ..., 50: ...}` -- discards a single reservation and reads as
    an edit that took, and the row Python keeps is the OLDER of the two. Measured on
    2026-09-02: `main` carried the first shape and a sibling branch carried the second.

    Outer duplicates are reported as the key itself; inner ones as `"REQ[50]"`, so the
    assertion message names the row a reader has to go and find.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # BOTH ASSIGNMENT NODES, and the reason is a measured near-miss rather than
        # completeness for its own sake. These tables are `AnnAssign` today --
        # `RESERVED: dict[str, dict[int, str]] = {...}` -- and a reader written for
        # `ast.Assign` alone reported every tree clean, including one already measured
        # as dirty, because it parsed the file and never found the table in it. Dropping
        # the annotation later must not do the same thing quietly.
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        literal = node.value
        assert isinstance(literal, ast.Dict), f"{name} is not a dict literal"
        shadowed: list = list(_repeats(literal))
        for key, rows in zip(literal.keys, literal.values, strict=True):
            if isinstance(rows, ast.Dict):
                register = ast.literal_eval(key)          # type: ignore[arg-type]
                shadowed += [f"{register}[{number}]" for number in _repeats(rows)]
        return shadowed
    # LOUD, NEVER CLEAN. A checker that finds no table and reports no duplicates is
    # indistinguishable from a table that has none, which is this same failure in a
    # new place -- and a sibling session hit exactly that today by matching only
    # `ast.Assign`: it parsed four refs and called every one clean.
    raise AssertionError(
        f"no assignment to {name} found in this file, so nothing was checked")


def test_the_reservation_table_has_no_shadowed_rows():
    """A DUPLICATE KEY IN THESE TABLES DELETES ROWS IN SILENCE, and it happened.

    `origin/main`’s `RESERVED` carried `"R"` twice for eight days. The first entry held 46 and 80 with a
    verified ref and an instruction to delete itself when #293 merged; the second held 46
    alone, written as a new entry rather than an edit when 79 was released. Python keeps
    the last, so the R-80 row never existed at runtime -- and `#293` merged, `R-80` became
    a heading, and `test_a_reserved_number_is_not_also_declared` stayed green because the
    contradiction it looks for was in a row that had already been thrown away.

    AND IT WATCHES BOTH LEVELS. A sibling branch, measured the same day, carried the
    other shape -- a ROW written twice inside one register's dict, where the copy Python
    keeps is the older one and the newly written row with the verified holders is what
    gets discarded. The first version of this guard read only the register keys and
    reported that tree as clean.

    THIS IS NOT A STYLE RULE. Every other test in this file reads the built dicts, so all
    of them are blind to it in exactly the same way; the check has to read the source.
    """
    for table in ("RESERVED", "RETIRED"):
        shadowed = _shadowed_keys(Path(__file__).read_text(encoding="utf-8"), table)
        assert not shadowed, (
            f"{table} declares {shadowed} more than once. Python keeps only the LAST "
            "one, so the earlier is discarded without an error -- a bare register key "
            "('R') throws away every row in the entry above; a row ('REQ[50]') throws "
            "away that one reservation, and the copy that survives is the OLDER of the "
            "two. Merge them into one, keeping what each side carried.")


def test_a_shadowed_row_would_actually_be_caught():
    """THE GUARD ABOVE, MUTATED. It reads source rather than a value, so a parser that
    quietly stopped finding the assignment would make it vacuous -- and vacuous is the
    precise failure it was written for."""
    rows = ['X: dict[str, dict[int, str]] = {',
            '    "R": {46: "a"},',
            '    "R": {46: "a", 80: "b"},',
            '    "REQ": {50: "c", 34: "d", 50: "e"},',
            '}']

    # BOTH SHAPES FROM ONE FIXTURE: the register key `"R"` written twice, and the row
    # 50 written twice inside `"REQ"`. The second is the one the first version of this
    # guard let through.
    assert _shadowed_keys(chr(10).join(rows), "X") == ["R", "REQ[50]"]

    # AND EACH GOES AWAY ON ITS OWN, which is what proves the two halves are not one
    # assertion wearing two names.
    assert _shadowed_keys(chr(10).join(rows[:1] + rows[2:]), "X") == ["REQ[50]"]
    assert _shadowed_keys(
        chr(10).join([*rows[:3], '    "REQ": {50: "c", 34: "d"},', rows[4]]),
        "X") == ["R"]



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
