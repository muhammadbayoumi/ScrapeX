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
DOCUMENTS = (
    "CLAUDE.md",
    "ENGINEERING.md",
    "docs/STATE.md",
    "docs/REQUESTS.md",
    "docs/RULINGS.md",
    "docs/BACKLOG.md",
    "docs/LESSONS.md",
    "docs/APPROACHES.md",
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

# Tier 2. (document, path, line, the text that must be on or beside that line).
# The window is +/- WINDOW lines, because a citation may point at a decorator, a
# `def`, or the line under either and still be honest.
#
# EVERY ENTRY WAS READ OUT OF THE TARGET FILE, not copied from the document.
WINDOW = 3
PINNED = (
    # REQ-21's nested audit. The whole request is that `Sum N_child` is compared
    # against the PARENT, and these are the two lines that make it so -- one that
    # sizes the parent, one that refuses cells outside it before a request is spent.
    ("docs/REQUESTS.md", "scrapex/partitioncrawl.py", 1019,
     "whole = size_cell(fetch, partition, base_url, parent)"),
    ("docs/REQUESTS.md", "scrapex/partitioncrawl.py", 1012, "raise NotASubdivision("),
    ("docs/REQUESTS.md", "scrapex/pagesource.py", 146,
     "return set(other.params) <= set(self.params)"),
    # The version-gate blocker. Track 3 of STATE.md cannot be worked without
    # these three, and two of them are the citations that drifted.
    ("docs/STATE.md", "scrapex/version.py", 483, '"latest_extension_version": VERSION'),
    ("docs/STATE.md", "scrapex/webui/app.py", 1543, '"latest_extension_version": VERSION'),
    ("docs/STATE.md", "extension/app.js", 599, "latest_extension_version"),
    ("docs/STATE.md", "scrapex/version.py", 76, 'VERSION = "'),
    ("docs/RULINGS.md", "scrapex/webui/app.py", 1543, '"latest_extension_version": VERSION'),
    ("docs/RULINGS.md", "scrapex/version.py", 483, '"latest_extension_version": VERSION'),
    # The two flags whose condition is met and whose lighting is the owner's call.
    ("docs/STATE.md", "scrapex/features.py", 54, "True"),
    ("docs/STATE.md", "scrapex/features.py", 65, "True"),
    # B2 step 2 -- "do not write a second one". The instruction is to EXTRACT
    # these two, so a reader sent to the wrong line writes the duplicate instead.
    ("docs/STATE.md", "extension/app.js", 1594, "async function loadSourceColumns("),
    ("docs/APPROACHES.md", "extension/app.js", 1594, "async function loadSourceColumns("),
    ("docs/APPROACHES.md", "extension/app.js", 1633, "async function saveSourceColumns("),
    # The guards the documents claim exist. A rule that cites a dead guard is a
    # rule with nothing behind it -- which is how W4 came to be believed.
    ("docs/RULINGS.md", "tests/test_version.py", 536,
     'assert.equal(manifest.version, VECTORS.version)'),
    ("docs/LESSONS.md", "tests/test_version.py", 536,
     'assert.equal(manifest.version, VECTORS.version)'),
    ("docs/RULINGS.md", "tests/test_version.py", 79, "pyproject"),
    # OP-2's two worker_alive computations, one of which the fix never reached.
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 1554, '"worker_alive"'),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 2542, "def _about("),
    ("docs/BACKLOG.md", "scrapex/webui/templates/settings.html", 162, "about.worker_alive"),
    # BV-3's chain, end to end: the panel posts it, capture reads it.
    ("docs/BACKLOG.md", "extension/app.js", 840, "crawl_honour_delay:"),
    ("docs/BACKLOG.md", "scrapex/capture.py", 95, "crawl_honour_delay"),
    # OP-21 · the resume that saves the write and none of the requests. This is a
    # citation of a DEFECT at an exact line, so it is the kind that must not drift:
    # a reader sent one line off reads `store`'s docstring, agrees with it, and
    # concludes the entry is wrong. If someone moves this check into the walk, the
    # entry is answered and this row should go with it.
    ("docs/BACKLOG.md", "scrapex/snapshotcrawl.py", 164, "if page.url in seen:"),
    ("docs/LESSONS.md", "scrapex/snapshotcrawl.py", 164, "if page.url in seen:"),
    # OP-22 / LESSONS §2 · one database, and where it is. That section described
    # the pre-collapse split layout in the present tense until 2026-08-20, so the
    # line naming the single file is worth holding still.
    ("docs/LESSONS.md", "scrapex/databases/registry.py", 33, "DEFAULT_ENGINE_PATH"),
    # The partition crawl's shared vocabulary. STATE.md sends a reader here to
    # learn what a cell IS before reading how one is witnessed.
    ("docs/STATE.md", "scrapex/pagesource.py", 67, "class Cell:"),
    # OP-23 · the value `carry_over` must reuse rather than invent. The entry's
    # whole argument is that this literal already exists, so a reader landing on
    # the wrong line would conclude the fix needs a ruling about evidence when it
    # does not.
    ("docs/BACKLOG.md", "db/migrations/0058_a_unit_that_can_name_who_said_it.sql",
     90, "'legacy_unwitnessed'"),
    # OP-29. The `r` IS the fix, and a docstring quoting a Windows path is the
    # case that recurs -- so the prefix is pinned rather than remembered. Drop
    # it and 3.12 warns on an invalid escape while a later Python refuses the
    # file outright; this row turns that back into a failing test.
    ("docs/BACKLOG.md", "tests/test_relaunch_log.py", 85,
     'r"""Reproduced on the owner'),
    # OP-33 · the panel says "Not detected" about an engine that IS installed and
    # is refusing to start for a nameable reason. The entry's argument is that this
    # exact branch is the one a schema-ahead warehouse lands in, so a reader sent
    # to the wrong line reads the timeout branch and concludes the entry is wrong.
    ("docs/BACKLOG.md", "extension/app.js", 3416, 'text: "Not detected"'),
    # OP-34 · why a black window leaves no trace. The whole finding is that this
    # function DELIBERATELY does nothing when it has real streams, which is the
    # double-click case -- so the log is not evidence about a failed launch.
    ("docs/BACKLOG.md", "scrapex/cli.py", 976, "def _bind_log_streams("),
    # OP-35 · the hand-maintained command set that drifted to half the CLI.
    # The entry says "do not extend the literal, derive it", which only makes
    # sense standing at the literal.
    ("docs/BACKLOG.md", "packaging/engine_entry.py", 18, "def known_commands("),
    # OP-36 · THE PRECEDENT, and it is the only one of these that survived the fix.
    # Four rows here used to pin the `-m scrapex.cli` lines in relaunch.py,
    # native.py and autostart.py -- they were holding a DEFECT still, so that a
    # reader sent one line off would not conclude the entry was wrong. OP-36 is
    # fixed and those lines are gone, so the rows went with the citation rather
    # than being loosened to keep passing. This one stays because
    # `nativehost.py:57` is still there and is still the argument: the fix was
    # already written once in this repository, and the other four were given it.
    ("docs/BACKLOG.md", "scrapex/nativehost.py", 57, 'getattr(sys, "frozen", False)'),
    # And the module that generalised it, cited by OP-36's closing note.
    ("docs/BACKLOG.md", "scrapex/enginelaunch.py", 74, "def engine_argv("),
    # OP-42 · the muqawil cards carry no actions button. All four of these are the
    # entry's argument rather than colour, and the entry turns on the DIFFERENCE
    # between them: the first two are the deliberate hide and the marker it keys
    # on, the third is why five of the six entries must stay hidden, and the
    # fourth is why the sixth should not be. A reader landing one line off any of
    # them reads the entry as either a bug report about correct code or a licence
    # to unhide the five that answer 400.
    ("docs/BACKLOG.md", "extension/app.js", 4549,
     'if (source.kind === "dataset") return "";'),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 697, '"kind": "dataset",'),
    # 2710 -> 2725 -> 2787, and the third move is the same story as the first two.
    # #252 measured this line on `main` at 4615a14, #251 landed first and added 15
    # lines to `app.py` above it, and `main` was red between the second merge and
    # the fix. This branch then inserted above it again. Three pull requests, none
    # wrong on its own base -- which is why the number is re-read out of the file
    # on every rebase and never adjusted by arithmetic.
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 2787, "if source_key not in known:"),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 1048,
     "A GENERIC DATASET IS A TABLE LIKE ANY OTHER TABLE"),
    # OP-44 · the dataset card that said "no successful crawl yet" over 17,304
    # crawled rows. Four citations carry the whole argument, and a reader sent one
    # line off would conclude the entry is wrong about each of them in turn.
    #
    # The sentence itself, so it is clear the card reads a MISSING key and not a
    # missing crawl -- which is why writing a `crawl_run` row would not have moved
    # this line at all.
    ("docs/BACKLOG.md", "extension/app.js", 4489, "const last = s.last_success;"),
    # Why the row could not honestly be written: the column is NOT NULL into
    # source_site, and muqawil is in site_profile.
    ("docs/BACKLOG.md", "db/engine/schema.sql", 122,
     "REFERENCES source_site(source_id)"),
    # The index that is worth 390x and had no reader. The entry's claim is about
    # its COLUMN ORDER, so it has to be read where the order is written.
    ("docs/BACKLOG.md", "db/engine/schema.sql", 843,
     "CREATE INDEX ix_generic_page_snapshot_page"),
    # And the reason `max(page_snapshot_id)` is not a cheaper spelling: the merge
    # carries the other machine's captured_at under fresh local ids. LESSONS §2
    # generalises it past snapshots, so it is pinned in both documents -- the
    # generalisation is worth nothing if the one INSERT it rests on has moved.
    ("docs/BACKLOG.md", "scrapex/warehousemerge.py", 269,
     "INSERT INTO generic_page_snapshot "),
    ("docs/LESSONS.md", "scrapex/warehousemerge.py", 269,
     "INSERT INTO generic_page_snapshot "),
    # OP-32, second report · THE FOUR LINKS OF THE CHAIN THAT IS NOT BROKEN. The
    # entry's whole argument is that the panel, the manifest and the workflow all
    # agree and the release simply was not cut, so a reader sent to the wrong line
    # on any one of them would go hunting for a defect that is not there.
    ("docs/BACKLOG.md", "extension/releases.js", 32, "ScrapeX/json/version.json"),
    ("docs/BACKLOG.md", "extension/app.js", 3514, "latest.version"),
    # 352, and it was 344 until this same pull request added eight comment lines
    # above it — the guard catching its author, in the exact shape LESSONS §7
    # describes: one change moves a line, another wrote the number down.
    ("docs/BACKLOG.md", ".github/workflows/release-engine.yml", 352, '"version": VERSION'),
    ("docs/BACKLOG.md", "tests/test_the_two_release_paths.py", 276,
     'got["version"] == manifest["version"]'),
    # And the line whose VALUE went stale under a citation that stayed correct --
    # the defect this row exists to make visible next time. `VERSION = "` is what
    # can be pinned; the number on it is what six places copied and lost. That gap
    # is why tests/test_the_release_the_documents_ask_for_is_the_one_that_would_run.py
    # exists beside this file rather than as another row here.
    ("docs/BACKLOG.md", "scrapex/version.py", 76, 'VERSION = "'),
    # The second home of the number, cited by LESSONS §7's release-runbook line.
    # `pyproject.toml` is a mirror because setuptools cannot import the package, so
    # "bump both or neither" is a rule with a guard behind it rather than advice.
    ("docs/LESSONS.md", "tests/test_version.py", 73,
     "def test_the_installer_carries_the_same_number("),
    # DELIBERATELY ABSENT, AND THE ABSENCE IS RECORDED HERE RATHER THAN ONLY IN THE
    # ENTRY THAT WANTS IT. `OP-46` cites seven lines in `extension/app.js` --
    # `setupFinanceConverterSelect` and `setupRunModeSelect` chief among them -- and
    # pins none of them, because that file was under concurrent edit by another
    # session when the entry was written. Pinning a line another branch is moving is
    # how `scrapex/webui/app.py:2710` above became 2725 and then 2787.
    #
    # A CONDITION, NOT A CHORE ASSIGNED TO NOBODY: pin those two symbols the next
    # time you add a row here AND `extension/app.js` is quiet. It is written beside
    # the mechanism instead of in `OP-46` because this table is re-read every time
    # someone adds a row, whereas a BACKLOG entry is read when someone goes looking
    # for work -- and this instruction has to fire while its reader is doing
    # something else.
)

# A guard that can be emptied without anyone noticing is the defect -- SR-23, and
# OP-18, where a test guard was blind to the thing it was written to find. This
# floor is below today's count on purpose: it may fall a little as documents are
# rewritten, but it may not fall to nothing.
PINNED_FLOOR = 15


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


def _citations():
    for document in DOCUMENTS:
        text = _read(document)
        for match in CITATION.finditer(text):
            line = int(match.group(2))
            end = int(match.group(3)) if match.group(3) else line
            where = text.count("\n", 0, match.start()) + 1
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

    The end of a range is not checked: a citation may legitimately span a blank
    line inside a block. Only the line the reader is actually sent to must say
    something.
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


def test_the_pinned_list_cannot_be_quietly_emptied():
    """SR-23's lesson and OP-18's: a guard that can vanish without anyone noticing
    is itself the defect. Deleting rows from PINNED to make a red build green is
    the failure this asserts against."""
    assert len(PINNED) >= PINNED_FLOOR, (
        f"PINNED is down to {len(PINNED)} citations from a floor of "
        f"{PINNED_FLOOR}. Rows are removed when the CITATION goes, never to "
        "silence a failure.")


def test_every_pinned_document_is_one_this_guard_reads():
    """A pinned citation in an unread document would be checked by tier 2 and
    invisible to tier 1 -- half a guard, and the half nobody would notice."""
    stray = sorted({document for document, *_ in PINNED} - set(DOCUMENTS))
    assert not stray, f"pinned citations in documents outside the map: {stray}"


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
