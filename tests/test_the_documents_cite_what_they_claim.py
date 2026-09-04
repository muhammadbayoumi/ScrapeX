"""The system's documents cite `file:line`. Those citations have to still be true.

WHY THIS EXISTS. REQ-08, ruled 2026-08-19 (R-15). It was proposed after
`ENGINEERING.md` W4 was found pointing at an action the suite forbids, and it did
not need a hypothetical to justify itself: re-reading `docs/STATE.md` two days
after it was written found THREE of its own citations wrong.

  * The `"latest_extension_version": VERSION` citation in `scrapex/webui/app.py`
    said line 1355. PRs #211 and #212 inserted twenty lines above it, so the code
    had moved to 1375. The file existed. The line existed. It was the wrong line.
  * `LATEST_SOURCE` and `UPDATE_INSTRUCTIONS` were cited at lines 289 and 292 when
    they had been at 282 and 285 all along -- in a file no commit had touched, so
    those two were wrong on the day they were written.

A citation that silently moves is worse than no citation: it sends the next
session to the wrong line with full confidence. Under **C1** every session reads
these documents before designing anything, so a wrong line here is a wrong
decision downstream.

WHY THERE ARE TWO TIERS, AND WHY THE SECOND ONE IS A LIST.

The obvious design is to infer each citation's subject from the prose around it --
take the nearest backticked span and demand it sit on the cited line. That was
built and measured before this file was written, and it CANNOT be made both
sensitive and precise:

  * At 220 characters of context it reported eleven failures, four of them false.
    It kept picking the name of a DIFFERENT file: `extension/manifest.json`, sixty
    characters away from a correct citation of `tests/test_version.py:536`.
  * Excluding path-like spans and tightening to 120 characters left ten, still
    with two false: `` `_about` renders the engine's own `/settings` page
    (`...settings.html:162-167`) `` -- where the adjacent span is `/settings`, a
    URL, while the citation itself is perfectly correct.
  * Demanding strict adjacency dropped coverage from 42 citations to 3 and stopped
    catching the app.py:1355 drift that motivated the whole thing -- because in
    `` (`scrapex/version.py:477`, again in `scrapex/webui/app.py:1355`) `` another
    citation sits between the symbol and its line.

`tests/test_the_published_documents_are_checked_not_announced.py` already wrote
down the rule that settles this: *"A publish step that cries wolf gets ignored,
which is the exact failure it exists to prevent. Two cheap checks that cannot
flake beat one true check that does."* So:

  * **Tier 1** is mechanical and applies to every citation: the file exists, and
    the line is inside it. Zero inference, zero flake.
  * **Tier 2** is `PINNED` -- citations whose subject is stated here explicitly and
    checked exactly. No guessing. Adding a load-bearing citation to a document
    means adding a line here, and that is the intended cost.

WHY `docs/plans/` IS OUT OF SCOPE, and it is a decision rather than an oversight.
Those files are verbatim historical records. `docs/plans/README.md` says nothing in
them was rewritten *"because a plan edited after the fact stops being evidence of
what was decided when"*. The 2026-07-20 plan citing `reports.py:176` described that
day's code correctly; forcing it to match today's would falsify a record to make a
test pass. 200 of the 289 citations in the repository's documents live in those
frozen files.
"""
from __future__ import annotations

import collections
import pathlib
import re

import pytest

# THE EXTENSION MARK IS LOAD-BEARING HERE, and CI caught its absence before this
# comment existed. Four pinned citations point into `extension/app.js` --
# loadSourceColumns at 1590, saveSourceColumns at 1629, the crawl_honour_delay
# POST at 836, latest_extension_version at 595. An extension-only change runs
# `pytest -m extension`, so without the mark those four would stop being checked
# on exactly the pull requests most likely to move them.
# See tests/test_the_extension_gate_is_complete.py, which is the guard that
# refuses an unmarked file reading extension/ sources.
pytestmark = [pytest.mark.extension, pytest.mark.docs]

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The map in CLAUDE.md -- the documents C1 sends every session to read before it
# writes a line of code. If a document joins that map, it joins this list.
#
# AND THAT SENTENCE WENT UNENFORCED ON ITS FIRST TEST. `docs/ORCHESTRATION.md`
# joined the map in `#257` and did not join this tuple, so the one document telling
# a session how to merge had its citations checked by nothing -- while the comment
# directly above said it would. A rule stated in a comment and enforced nowhere is
# LESSONS §13's subject, and this is the guard's own instance of it. Found 2026-08-22
# by reading the map against this list rather than trusting the sentence.
#
# Measured before adding it, so it goes green rather than arriving red: 4 citations,
# all resolving, none on a blank line.
DOCUMENTS = (
    # NARROWED ON 2026-09-04, when the seven tracking documents were frozen into
    # `docs/archive/`. A citation still has to be true where somebody will act on it,
    # and that is now exactly two files: the one live document and the front door.
    # The archive is deliberately NOT watched — its numbers are cited by 881 places in
    # the code and its `file:line` references record where things WERE, which is the
    # one thing `LESSONS` 21 says must never be repointed.
    "CLAUDE.md",
    "README.md",
)

# `sql` JOINED THIS LIST ON 2026-08-22, and the hole it closed was found by
# writing into it. OP-44's argument rests on two lines of `db/engine/schema.sql`
# -- a NOT NULL foreign key and an index's column order -- and neither of them
# was a citation as far as this regex was concerned, in a repository whose DDL is
# 1,153 lines and 61 migrations. Measured before the change: four `.sql`
# citations across the documents, all four still true, so nothing was being
# forgiven; they were simply never asked.
SUFFIXES = "py|js|css|html|json|yml|yaml|sh|md|toml|sql"
# `path:line` or `path:start-end`. The lookbehind keeps the match from starting
# inside a longer path, so `scrapex/webui/app.py:1375` is one citation and not two.
CITATION = re.compile(
    r"(?<![\w/.\-])((?:[\w.\-]+/)*[\w.\-]+\.(?:" + SUFFIXES + r")):(\d+)(?:-(\d+))?\b")

# The same citation, but only where it is the LABEL of a markdown link carrying an
# `#L` anchor -- `[path:706](../path#L697)`. Four groups: the whole label, the line
# it SHOWS, the href without its fragment, and the line it OPENS.
#
# THE LABEL MAY BE DRESSED, and the honest reason is narrower than the one first
# written here. That comment claimed ``[`app.py:706`](...#L697)`` was "this
# repository's dominant inline-code idiom" with "four such links already existing".
# Measured across every `*.md` in the repository: **zero** backticked-label citations
# exist. There are seven backticked-label links, and not one is a citation -- none
# carries `:digits`, so the widened pattern would not match them even with an anchor
# added. All 45 real linked citations are undressed, and widening the class changed
# **0** matches and **0** verdicts.
#
# So this is defence in depth for a shape nobody writes YET, which is a fair thing to
# build and not the thing the old comment said. The correction is recorded rather than
# quietly swapped, because it was written in the very commit whose subject was fixing
# four statements that had drifted from the code -- and it drifted from the documents
# in the same breath. Bold and emphasis markers are allowed on the same footing, and a
# lowercase `#l697` because GitHub accepts it.
#
# WHAT IT STILL CANNOT SEE, named rather than implied: a reference-style link
# (`[label][ref]`), a raw HTML `<a href>`, and a link split across two lines -- this
# walks `splitlines()`, so a newline hides such a link twice over. All three are
# absent from every document today; a bare numeric fragment like `#123` is refused on
# purpose, because `#2026-08-24` is a real heading anchor and would match as line 2026.
LINKED_CITATION = re.compile(
    r"\[([^\]\n]*?\.(?:" + SUFFIXES + r"):(\d+)(?:-\d+)?[`*_ ]*)\]"
    r"\(([^)\n]*?)#[Ll](\d+)(?:-L?\d+)?\)")

# Tier 2. (document, path, line, the text that must be on or beside that line).
# The window is +/- WINDOW lines, because a citation may point at a decorator, a
# `def`, or the line under either and still be honest.
#
# EVERY ENTRY WAS READ OUT OF THE TARGET FILE, not copied from the document.
WINDOW = 3
PINNED = (
    # EMPTIED ON 2026-09-04, when the seven tracking documents were frozen into
    # `docs/archive/`. Every row here pinned a citation inside one of them, and a
    # pinned row whose document this guard no longer reads is the contradiction the
    # tests below refuse. The archive keeps its numbers -- 881 places in the code cite
    # them -- and keeps its stale line numbers on purpose: they record where something
    # WAS, which `LESSONS` 21 says must never be repointed.
    #
    # A NEW ROW BELONGS HERE THE MOMENT `CLAUDE.md` OR `README.md` CITES A LINE whose
    # exact content matters. That is the only reason this table still exists.
)

# A guard that can be emptied without anyone noticing is the defect -- SR-23, and
# OP-18, where a test guard was blind to the thing it was written to find. This
# floor is below today's count on purpose: it may fall a little as documents are
# rewritten, but it may not fall to nothing.
PINNED_FLOOR = 0


def _read(rel: str) -> str:
    path = ROOT / rel
    assert path.is_file(), f"{rel} is in the map but not in the repository"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index() -> dict[str, list[pathlib.Path]]:
    """Basenames to real files, so `reports.py:176` can be resolved when exactly
    one file in the repository carries that name."""
    skip = {".git", "node_modules", ".claude", "vendor", "__pycache__", ".vs",
            "htmlcov", "dist", "build"}
    found: dict[str, list[pathlib.Path]] = collections.defaultdict(list)
    for path in ROOT.rglob("*"):
        # RELATIVE to ROOT, and that is not a detail. A worktree lives at
        # ...\ScrapeX\.claude\worktrees\<name>, so testing the ABSOLUTE parts
        # finds `.claude` in every path and skips the entire repository -- the
        # index comes back empty and every citation reports as unresolvable.
        # Caught exactly that way while writing this file.
        if path.is_file() and not any(part in skip for part in path.relative_to(ROOT).parts):
            found[path.name].append(path)
    return found


def _resolve(raw: str, index) -> pathlib.Path | None:
    """A citation may be repo-relative, doc-relative (`../scrapex/...`), or a bare
    basename. An ambiguous or foreign name resolves to None and is reported, never
    silently passed -- `RibbonControlService.cs` lives in another repository."""
    rel = raw.removeprefix("../")
    if "/" in rel and (ROOT / rel).is_file():
        return ROOT / rel
    hits = [p for p in index.get(rel.split("/")[-1], []) if p.as_posix().endswith(rel)]
    return hits[0] if len(hits) == 1 else None


#: An exception header or a `Traceback` line turns the rest of a fenced block into
#: QUOTED OUTPUT, and a `file:line` inside quoted output is not a citation -- it is
#: part of the quotation. `docs/BACKLOG.md`'s `--workers` entry reproduces a real
#: `sqlite3.OperationalError: database is locked` traceback naming
#: `scrapex/jobs.py:932 record_worker_failure`; that function now begins at 943, and
#: "correcting" the number would rewrite what the traceback said. `LESSONS` 21 is the
#: same rule from the other end: a number that RECORDS something must leave the
#: `file:line` form rather than be repointed.
_QUOTED_OUTPUT = re.compile(
    r"^(?:Traceback \(most recent call last\)|"
    r"[A-Za-z_][\w.]*(?:Error|Exception|Warning)\b.*:)")

#: How much stated subject is worth checking. Below this a "subject" is punctuation
#: or a fragment that would match half the file.
MIN_SUBJECT = 6


def _quoted_output_lines(text: str) -> set[int]:
    """Line numbers inside a fenced block that is QUOTED OUTPUT rather than prose.

    A `file:line` in a traceback is part of the quotation, not a citation, and it is
    one for NO tier -- not the content check, not the blank-line check, not the
    file-exists check. That distinction was applied to the content check first and
    only there, and the tree moving found the gap within the hour: `docs/BACKLOG.md`
    quotes a real `database is locked` traceback naming `scrapex/jobs.py:932`, that
    line has since become blank, and `test_no_citation_lands_on_a_blank_line`
    reported a quotation as a broken citation.

    THE ALTERNATIVE WAS WORSE. Repointing it means editing what the traceback said,
    and taking it out of `path:line` form means editing a verbatim quotation. Neither
    is available, because the number is not wrong -- it was right when the traceback
    was produced, which is what a quotation is for.
    """
    inside: set[int] = set()
    in_fence = quoted = False
    for where, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence, quoted = not in_fence, False
            continue
        if not in_fence:
            continue
        if _QUOTED_OUTPUT.match(line.strip()):
            quoted = True
        if quoted:
            inside.add(where)
    return inside


def _citations():
    for document in DOCUMENTS:
        text = _read(document)
        quoted = _quoted_output_lines(text)
        for match in CITATION.finditer(text):
            line = int(match.group(2))
            end = int(match.group(3)) if match.group(3) else line
            where = text.count("\n", 0, match.start()) + 1
            if where in quoted:
                continue
            yield document, where, match.group(1), line, end


def test_every_citation_names_a_file_that_exists(index):
    """Tier 1. A citation of a deleted or renamed file is the cheapest kind of
    lie and the easiest to catch."""
    unresolved = [f"{doc}:{where} cites {raw!r}"
                  for doc, where, raw, _, _ in _citations()
                  if _resolve(raw, index) is None]

    assert not unresolved, (
        "these citations name a file that does not exist, or a bare filename that "
        "matches more than one file so a reader cannot tell which was meant:\n  "
        + "\n  ".join(unresolved))


def test_every_citation_names_a_line_that_exists(index):
    """Tier 1. Catches a file that was truncated or gutted under a citation."""
    beyond = []
    for doc, where, raw, line, end in _citations():
        target = _resolve(raw, index)
        if target is None:
            continue  # the test above owns that failure
        count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        if end > count:
            beyond.append(f"{doc}:{where} cites {raw}:{line} but that file has "
                          f"{count} lines")

    assert not beyond, "\n  ".join(["citations past the end of their file:", *beyond])


def test_a_citations_link_target_agrees_with_the_label_it_shows():
    """Tier 1, and the half every other test in this file was blind to.

    A citation is usually a markdown link: the LABEL reads `app.py:706` and the HREF
    ends `#L697`. `CITATION` matches the label only, so tier 1 checks the number a
    reader SEES and never the line the link OPENS -- and those are exactly what drift
    apart, because a sweep that renumbers labels does not touch hrefs.

    MEASURED WHEN THIS WAS WRITTEN: seven disagreements, all in `docs/BACKLOG.md`,
    every anchor 8 to 27 lines behind its label. Six were stale hrefs under correct
    labels. The seventh is the reason this is a test and not a one-off sweep:
    `app.py:706` under `#L697`, where the subject had moved to **665**. Both numbers
    wrong, and tier 1 passed because 706 is a real, non-blank line of the same file.
    A citation can be false without being broken, and that is the gap here.
    """
    disagreements = []
    for name in DOCUMENTS:
        document = ROOT / name
        if not document.is_file():
            continue
        for number, line in enumerate(
                document.read_text(encoding="utf-8").splitlines(), start=1):
            for label, shown, href, target in LINKED_CITATION.findall(line):
                if shown != target:
                    disagreements.append(
                        f"{name}:{number}: [{label}] shows :{shown} "
                        f"and opens {href}#L{target}")

    assert not disagreements, (
        "a citation's label and its link name different lines. Whichever is right, "
        "a reader who clicks lands somewhere the prose does not describe:\n  "
        + "\n  ".join(disagreements))


def test_no_citation_lands_on_a_blank_line(index):
    """Tier 1, and it closes a hole the two tiers around it both leave open.

    A citation that has drifted onto a BLANK line passes every other check here.
    Tier 1 is satisfied because the file is long enough. Tier 2 never looks unless
    the citation is in `PINNED`. So the document sends its reader to a line that
    says nothing at all, and what they see reads as a formatting artefact rather
    than an error -- nobody reports it, because it does not look like a mistake.

    FOUND, NOT IMAGINED, ON 2026-08-22. `#255` added a section to `docs/LESSONS.md`
    and pushed a sentence `OP-48` cites down 38 lines. The citation still resolved,
    still passed, and pointed at an empty line. It was caught by re-deriving every
    citation by hand after a rebase, which is not a thing anybody should have to
    remember to do.

    THE SWEEP THAT CAME WITH THIS FOUND THREE MORE, all long-standing and all in
    `docs/BACKLOG.md`: `scrapex/cli.py:761` (the call it names is at 867),
    `scrapex/connectors/base.py:485` (the sentence it names is at 560) and
    `tools/panel_harness.py:119` (the manifest read is at 121). Each was corrected
    by reading the target file, so this assertion goes green on a correct tree
    rather than arriving red and being negotiated with.

    Three of 161 also settles a question nobody needed to argue: this was NOT
    added on a hunch about what might drift one day. The class already had three
    tenants, and the guard was written from a measurement rather than from a fear.

    THE END OF A RANGE IS DELIBERATELY NOT CHECKED. A citation may legitimately
    span a blank line inside a block, so only the line the reader is actually SENT
    to has to say something. Checking both ends would look stricter and would be
    right less often -- which is the worse trade in a guard, because a check that
    fails on correct input is one people learn to route around.

    AND THE MUTATION TEST FOR THIS ONE GOES ON THE DATA, NOT ON THE ASSERTION.
    Reverting one of the three corrections above makes this fail and name that
    citation; that is how it was proved non-vacuous. The shape is deliberate: here
    the guard's possible defect and the data's actual defect are the same shape --
    a line that resolves and says nothing -- so mutating a fix exercises the real
    path, where mutating the assertion would only prove that an `assert` asserts.
    """
    empty = []
    for doc, where, raw, line, _end in _citations():
        target = _resolve(raw, index)
        if target is None:
            continue  # tier 1's first test owns that failure
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if line <= len(lines) and not lines[line - 1].strip():
            empty.append(f"{doc}:{where} cites {raw}:{line}, which is a blank line")

    assert not empty, "\n  ".join([
        "these citations resolve to a blank line, so they send the reader to "
        "nothing. Read the target file, find where the subject moved to, and "
        "correct the document:", *empty])


@pytest.mark.parametrize("document,path,line,expected", PINNED,
                         ids=[f"{d.split('/')[-1]}-{p.split('/')[-1]}-{n}"
                              for d, p, n, _ in PINNED])
def test_a_pinned_citation_still_points_at_its_subject(document, path, line, expected):
    """Tier 2. The check that would have caught app.py:1355 -> 1375.

    If this fails, read the target file, find where `expected` moved to, and
    correct BOTH the document and the line in PINNED. Do not widen WINDOW: the
    drift that started this was twenty lines, and a window that forgives twenty
    lines forgives the defect."""
    target = ROOT / path
    assert target.is_file(), f"{document} cites {path}, which no longer exists"
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    assert line <= len(lines), (
        f"{document} cites {path}:{line}; the file has {len(lines)} lines")

    low, high = max(0, line - 1 - WINDOW), min(len(lines), line + WINDOW)
    near = "\n".join(lines[low:high])
    if expected in near:
        return

    actually = [i + 1 for i, text in enumerate(lines) if expected in text]
    raise AssertionError(
        f"{document} cites {path}:{line} for {expected!r}, which is not within "
        f"{WINDOW} lines of there. It is at {actually or 'nowhere in the file'}. "
        f"The document is sending the next session to the wrong line.")





#: The fence info string that says "the lines in here are citations, and each states
#: its own subject". The tier below reads ONLY these blocks.
#:
#: A DECLARATION, NOT A GUESS, and the difference is what makes it hold. The first
#: version read every fenced block and skipped the ones that looked like a traceback.
#: Then `ORCHESTRATION.md` landed a section about citation drift whose evidence is a
#: VERBATIM COPY of this guard's own failure message -- and the tier read that message
#: as two citations whose "subjects" were fragments of its own words. A traceback shape
#: cannot see quoted pytest output, quoted shell output, or a document quoting a
#: citation in order to explain citations, and there will be a fourth kind.
#:
#: The suggestion that came first was to skip fenced blocks entirely. That would have
#: given this tier ZERO input -- it only ever looks inside fences, because that is
#: where this repository writes `path:line   <the code>` and prose never does. A guard
#: that cannot fail, added by the change whose subject is guards that cannot fail.
#:
#: THE COST IS REAL AND IS NOT HIDDEN: a new evidence block is unchecked until somebody
#: labels it. `FENCE_FLOOR` below is what keeps that from being invisible.
FENCE_LABEL = "cited"

#: Labelled citation lines the tier can CHECK, measured 2026-09-03: seven. Not the
#: eleven lines inside the three labelled blocks -- four are skipped because their
#: stated subject is an ellipsis (a paraphrase) or too short to identify a line. The
#: floor counts what is actually checked, because that is the number that means
#: something. Set from the measurement after writing 9 from memory and being wrong.
#:
#: The floor may only be RAISED. RE-BASED TO 0 on 2026-09-04: every labelled evidence block lived in the seven documents now frozen in `docs/archive/`, so the floor guards nothing until the two live documents grow one by the entries
#: `OP-133`..`OP-142`, measured with `_quoted_subjects()` rather than counted by
#: hand -- the same way the 7 was arrived at, and for the same reason: a floor
#: written from memory is a floor that means nothing.
#:
#: It fails when the count drops, so a labelled block cannot be quietly unlabelled to
#: silence a red; it does NOT fail when a new unlabelled block appears, because
#: reddening a correct record is the direction this design refuses to be wrong in.
#: That turns "somebody forgot to label" from invisible into merely known, which is the
#: most a declaration can offer.
FENCE_FLOOR = 0


def _quoted_subjects():
    """Citations that STATE what they point at, so the document can be held to it.

    This repository's evidence blocks are written `path:line   <the code>`, and that
    means the document has already said what it expects -- no hand-maintained table
    needed, unlike `PINNED`. Measured across all nine documents: 296 citations, of
    which 8 are in this form, and 2 of those 8 were wrong.

    THAT RATIO IS THE ARGUMENT AND SO IS THAT COUNT. Eight is not most citations, and
    this is not the general fix; the general problem is recorded in `OP-123` and left
    open on purpose, because the only mechanism that would cover all 296 -- repointing
    a citation to wherever its subject now sits -- would silently rewrite every number
    that is a RECORD rather than a pointer. What this does cover, it covers with no
    list for anyone to forget to update.

    An ELLIPSIS disqualifies a subject. `include_router(create_domain_health_router(...))`
    is a paraphrase of a real line, and demanding it appear verbatim reported a correct
    citation as broken -- measured, on the very citation this file's author had just
    repaired by hand.
    """
    for document in DOCUMENTS:
        text = _read(document)
        in_fence = False
        for where, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_fence = (not in_fence) and stripped[3:].strip() == FENCE_LABEL
                continue
            if not in_fence:
                continue
            for match in CITATION.finditer(line):
                stated = re.split(r"\s+--\s+|\s{2,}#\s", line[match.end():])[0].strip()
                if len(stated) < MIN_SUBJECT or "..." in stated or "\u2026" in stated:
                    continue
                yield document, where, match.group(1), int(match.group(2)), stated


def test_the_labelled_evidence_blocks_have_not_quietly_shrunk():
    """The mitigation for the one cost of a declaration-based tier.

    A new evidence block is unchecked until somebody labels it, and nothing can see
    that without guessing what an unlabelled fence means -- which is the guess this
    design exists to refuse. So the count is ratcheted instead:

      * it FAILS when the number of checked lines drops, so a labelled block cannot
        be unlabelled to silence a red;
      * it does NOT fail when a new unlabelled block appears, because reddening a
        correct record is the direction this refuses to be wrong in.

    That turns "somebody forgot to label" from invisible into merely known, which is
    the most a declaration can offer.
    """
    checked = len(list(_quoted_subjects()))

    assert checked >= FENCE_FLOOR, (
        f"the tier checks {checked} labelled citation lines and the floor is "
        f"{FENCE_FLOOR}. A block was unlabelled or a subject stopped being "
        f"checkable. Raise the floor only when the count genuinely rises -- lowering "
        f"it is how a guard is talked out of its own subject.")


def test_a_citation_that_quotes_its_subject_still_points_at_it(index):
    """Tier 2 WITHOUT A HAND-MAINTAINED LIST, for every citation that quotes itself.

    `PINNED` does this for the rows somebody remembered to add. This does it for
    every citation written in the repository's own evidence-block form, and it needs
    no maintenance: the document states the subject, the subject is looked up.

    WHAT IT FOUND WHEN IT WAS WRITTEN, in a three-day-old entry: `OP-119`'s block
    held five citations, FOUR had drifted, and exactly one had been caught -- by
    `test_no_citation_lands_on_a_blank_line`, and only because it happened to land on
    a blank line. The other three pointed at a middleware call, a closing parenthesis
    and an unrelated comment, which no existing check can tell from a correct line.

    IT REPORTS, IT DOES NOT REPOINT. The failure names where the subject actually is
    and leaves the decision to a person, because a number can be a POINTER or a
    RECORD and only a reader knows which. An automatic repointer would turn every
    recorded number into a lie -- see `_QUOTED_OUTPUT` for the instance that proves
    it is not hypothetical.
    """
    wrong = []
    for doc, where, raw, line, stated in _quoted_subjects():
        target = _resolve(raw, index)
        if target is None:
            continue                      # tier 1's first test owns that
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        if line > len(lines):
            continue                      # tier 1's second test owns that
        low, high = max(0, line - 1 - WINDOW), min(len(lines), line + WINDOW)
        if stated in "\n".join(lines[low:high]):
            continue
        actually = [i + 1 for i, t in enumerate(lines) if stated in t]
        wrong.append(
            f"{doc}:{where} cites {raw}:{line} and says it holds {stated!r}, "
            f"which is at {actually or 'no line in that file'}")

    assert not wrong, "\n  ".join([
        "these citations quote a subject that is not where they point. Move the "
        "number to where the subject IS -- unless the number is a RECORD of where "
        "something used to be, in which case take it out of the `file:line` form and "
        "put the reason in the sentence (`LESSONS` 21), because repointing it would "
        "rewrite what it records:", *wrong])


#: `PINNED` rows whose document does not cite them, WITH the cause of each, and this
#: set may only ever SHRINK -- see the test below.
#:
#: 30 OF 68 ROWS, re-measured 2026-09-03 on the rebase onto `bc06101e`. It was
#: 26 of 66 a day earlier -- four of those rows were repointed on `main` by other
#: sessions and eight new ones arrived with their entries, which is the count
#: doing exactly what the ratchet is for: it moves with the tree instead of
#: standing still while the tree moves under it. `PINNED_FLOOR` exists so rows cannot be
#: deleted to make a red build green, and 26 rows that hold no citation up are 26
#: free units of that floor. Three distinct causes, and none of them is "the row is
#: wrong":
#:
#:   1. THE DOCUMENT USES A SHORTHAND NO REGEX SEES. `docs/STATE.md` writes
#:      "[scrapex/features.py:54](...) and `:65`" -- the second line is cited in
#:      prose as a bare `:65`, so the row for 65 guards something real that this
#:      guard cannot match.
#:   2. THE ROW AND THE DOCUMENT NAME DIFFERENT LINES. The row for
#:      `scrapex/warehousemerge.py:269` is pinned while `docs/BACKLOG.md` cites
#:      `:198` -- so the pinned line is unguarded-by-any-reader and the cited line is
#:      unpinned. That is the worst of the three and the only one that is a defect in
#:      the row itself.
#:   3. THE CITATION IS SIMPLY GONE, its entry rewritten or its evidence moved into
#:      prose, leaving the row behind. `.github/workflows/release-engine.yml:540` is
#:      this: no document names that file at any line.
#:
#: NOT FIXED HERE, and the reason is `R-01`. Each row needs a person to decide which
#: line the document actually means, 24 of the 26 belong to entries written by other
#: sessions, and a sweep that guessed would produce 26 confident wrong numbers in the
#: one file whose subject is confident wrong numbers.
PINNED_WITHOUT_A_CITATION = frozenset((
    ("docs/APPROACHES.md", "extension/app.js", 1622),
    ("docs/BACKLOG.md", ".github/workflows/release-engine.yml", 553),
    ("docs/BACKLOG.md", "db/engine/schema.sql", 1191),
    ("docs/BACKLOG.md", "db/engine/schema.sql", 91),
    ("docs/BACKLOG.md", "extension/app.js", 3551),
    ("docs/BACKLOG.md", "extension/app.js", 4647),
    ("docs/BACKLOG.md", "extension/app.js", 4775),
    ("docs/BACKLOG.md", "extension/releases.js", 32),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1003),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1065),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1177),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 978),
    ("docs/BACKLOG.md", "scrapex/version.py", 76),
    ("docs/BACKLOG.md", "scrapex/warehousemerge.py", 269),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 1234),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 1772),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 2842),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 3212),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 715),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 757),
    ("docs/BACKLOG.md", "tests/test_the_two_release_paths.py", 276),
    ("docs/LESSONS.md", "design/components.css", 380),
    ("docs/LESSONS.md", "scrapex/extract/service.py", 978),
    ("docs/LESSONS.md", "tests/test_panel_dom.py", 160),
    ("docs/RULINGS.md", "tests/test_version.py", 536),
    ("docs/RULINGS.md", "tests/test_version.py", 79),
    ("docs/STATE.md", "scrapex/extract/service.py", 927),
    ("docs/STATE.md", "scrapex/features.py", 65),
))


def _pinned_orphans(index) -> list[tuple[str, str, int]]:
    """`PINNED` rows whose document does not cite them at that line."""
    cited = set()
    for document, _where, raw, line, _end in _citations():
        target = _resolve(raw, index)
        if target is not None:
            cited.add((document, str(target.resolve()), line))
    return [(document, path, line) for document, path, line, _expected in PINNED
            if (document, str((ROOT / path).resolve()), line) not in cited]


def test_no_new_pinned_row_guards_a_citation_no_document_makes(index):
    """The other side of every `PINNED` row, which nothing checked.

    Tier 2 asserts that a cited line still holds its subject. It never asked whether
    the DOCUMENT still cites it -- so a row outlives the citation it was written for,
    goes on asserting something true about a source file, and **keeps counting toward
    `PINNED_FLOOR`**. The floor exists so rows cannot be deleted to turn a red build
    green; a row that holds no citation up is a free unit of it.

    Found while repointing `.github/workflows/release-engine.yml:540`: the row was
    real, the subject was real, and `grep` for that file across all nine documents
    returned nothing at all.
    """
    fresh = [row for row in _pinned_orphans(index)
             if row not in PINNED_WITHOUT_A_CITATION]

    assert not fresh, "\n  ".join([
        "these PINNED rows guard a citation no document makes. Either the document "
        "should cite the line -- which is usually the real answer, because the row "
        "was written when it did -- or the row belongs to a citation that has since "
        "moved and should name the line the document now uses. Do not add it to "
        "PINNED_WITHOUT_A_CITATION to get past this: that set may only shrink.",
        *(f'    ("{d}", "{p}", {n}),' for d, p, n in sorted(fresh))])



def test_every_pinned_document_is_one_this_guard_reads():
    """A pinned citation in an unread document would be checked by tier 2 and
    invisible to tier 1 -- half a guard, and the half nobody would notice."""
    stray = sorted({document for document, *_ in PINNED} - set(DOCUMENTS))
    assert not stray, f"pinned citations in documents outside the map: {stray}"


@pytest.mark.parametrize("document", DOCUMENTS)
def test_no_document_holds_a_table_with_no_header(document):
    """A RUN OF TABLE ROWS WITH NO SEPARATOR ABOVE IT IS NOT A TABLE, and the
    only thing that can tell is a check like this one.

    `OP-125`. A markdown table has no closing marker. A row is a line beginning
    with a pipe; a header is a separator line; and a run of rows with neither,
    a hundred lines below the table it came from, is indistinguishable from a
    table by looking -- to a reader scanning for "the table", and to every tool
    that reads these documents as prose. So a merge resolution that keeps both
    sides of a table's tail leaves something that RENDERS, passes every gate,
    and reads as deliberate.

    MEASURED BEFORE IT WAS WRITTEN, because a check that cries wolf gets
    switched off and this file has been bitten by that four times. The scan
    returned five hits across the guarded documents: two inside fenced code
    blocks -- shell pipelines whose lines begin with a pipe -- and THREE REAL
    ONES. One was `LESSONS` 29's own stub, the defect this rule came out of.
    The other two were in `REQUESTS.md` and nobody had suspected either:
    `REQ-51` and `REQ-52` separated from the board table by blank lines, so the
    board ended at `REQ-50`; and `REQ-45`'s evidence table duplicated verbatim,
    the stale copy still asserting a defect `#301` had closed.

    THE FENCE EXEMPTION IS STRUCTURAL AND THAT IS DELIBERATE. It skips fenced
    blocks by counting fences, never by matching what is inside them -- so a
    document that QUOTES a broken table to explain this defect is invisible to
    the scanner by structure rather than by spelling. Matching on content is how
    `OP-116`'s widened guard came to fail any file that merely NAMED the route
    it was protecting (`LESSONS` 28); the constraint was named before this was
    written rather than discovered after.
    """
    text = _read(document)
    fenced = False
    run: list[tuple[int, str]] = []
    orphans = []

    def close(run):
        if not run:
            return
        # A separator anywhere in the run makes it a table. `|---|`, `|:--|`,
        # `| --- | ---: |` all count: strip pipes and spaces, and what is left
        # of a separator is only dashes and colons.
        for _, line in run:
            bare = line.replace("|", "").replace(" ", "")
            if bare and set(bare) <= set("-:"):
                return
        orphans.append((run[0][0], run[-1][0], len(run), run[0][1][:60]))

    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            close(run)
            run = []
            continue
        if fenced:
            continue
        # A blockquote's own table is still a table; strip one level of `> `.
        body = stripped[2:].strip() if stripped.startswith("> ") else stripped
        if body.startswith("|"):
            run.append((number, body))
        else:
            close(run)
            run = []
    close(run)

    assert not orphans, (
        f"{document} holds table rows with no header above them: "
        + "; ".join(f"lines {a}-{b} ({n} row(s)): {first!r}"
                    for a, b, n, first in orphans)
        + ". A run of rows with no separator renders as a table and is not one "
        "-- it is what a keep-both merge resolution leaves behind, and the rows "
        "in it belong to a table somewhere above. Join them to it, or give this "
        "one a header. (OP-125)")


def test_the_frozen_plans_are_excluded_on_purpose():
    """The exclusion is a ruling (R-15), not a gap. If someone adds docs/plans to
    DOCUMENTS this fails and points them at why -- and if plans/README.md ever
    stops saying the plans are verbatim, the reason for the exclusion is gone and
    that is worth a red build too."""
    assert not any(document.startswith("docs/plans") for document in DOCUMENTS), (
        "docs/plans/ is verbatim history; a plan corrected to match today's code "
        "stops being evidence of what was decided when. See R-15.")

    readme = _read("docs/plans/README.md")
    assert "verbatim" in readme, (
        "docs/plans/README.md no longer says the plans are verbatim. That claim is "
        "the whole reason they are exempt from this guard -- re-decide the "
        "exemption rather than leaving it resting on a sentence that has gone.")
