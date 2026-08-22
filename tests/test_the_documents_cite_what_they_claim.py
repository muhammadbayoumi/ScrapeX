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

SUFFIXES = "py|js|css|html|json|yml|yaml|sh|md|toml"
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
    ("docs/STATE.md", "scrapex/webui/app.py", 1481, '"latest_extension_version": VERSION'),
    ("docs/STATE.md", "extension/app.js", 599, "latest_extension_version"),
    ("docs/STATE.md", "scrapex/version.py", 76, 'VERSION = "'),
    ("docs/RULINGS.md", "scrapex/webui/app.py", 1481, '"latest_extension_version": VERSION'),
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
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 1492, '"worker_alive"'),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 2480, "def _about("),
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
    ("docs/BACKLOG.md", "scrapex/cli.py", 1084, "def _bind_log_streams("),
    # AND THE FOUR THAT WERE NEVER PINNED HAD ALL DRIFTED, found 2026-08-22 when a
    # change to cli.py moved the row above. Three of the four were wrong BEFORE
    # that change -- `scrapex/cli.py:993` was `RUN_DUE_LOG.parent.mkdir(...)`,
    # `:1127` a parser help string, `:761` a blank line -- and the fourth
    # (`LESSONS.md`'s generator) has been wrong since the day it was written. Tier
    # 1 passed all four, every time, which is the whole argument for this table.
    ("docs/BACKLOG.md", "scrapex/cli.py", 152, "report = carry_over(plan"),
    ("docs/BACKLOG.md", "scrapex/cli.py", 1414, "except Exception as exc:"),
    ("docs/BACKLOG.md", "scrapex/cli.py", 975, "_upgrade_what_is_only_behind(registry, report)"),
    ("docs/LESSONS.md", "scrapex/cli.py", 459, "export-version"),
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
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 639, '"kind": "dataset",'),
    # 2710 UNTIL 2026-08-22, AND `main` IS RED ON IT AS THIS IS WRITTEN. #251
    # shifted app.py by fifteen lines and #252 merged after it carrying a row
    # written against the older file. Both were green alone. Corrected to 2725
    # here because a red guard on main is not this branch's to leave standing.
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 2725, "if source_key not in known:"),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 986,
     "A GENERIC DATASET IS A TABLE LIKE ANY OTHER TABLE"),
    # ---- the Drive track, 2026-08-22 (R-46, REQ-32) --------------------------
    # THE CORRECTION OF A WARNING IS THE MOST FRAGILE KIND OF CITATION, and this
    # is why: STATE.md and warehousemerge.py both said in capitals that
    # `drive-restore` REPLACES the live warehouse. It does not. A reader landing
    # one line off these two reads something else entirely and concludes the
    # correction was wrong -- which would put the false warning straight back.
    ("docs/STATE.md", "extension/app.js", 5881, "async function fetchFromDrive("),
    ("docs/RULINGS.md", "extension/app.js", 5881, "async function fetchFromDrive("),
    ("docs/STATE.md", "extension/app.html", 1892, 'id="drive-restore"'),
    ("docs/RULINGS.md", "extension/app.html", 1892, 'id="drive-restore"'),
    # The guard that replaced it. `restore-database` is the destructive control
    # and this literal is the whole of the interlock.
    ("docs/STATE.md", "scrapex/cli.py", 233, 'RESTORE_PHRASE = "replace my warehouse"'),
    ("docs/RULINGS.md", "scrapex/cli.py", 233, 'RESTORE_PHRASE = "replace my warehouse"'),
    # R-46's fourth item, and the only one of the four that was a live defect:
    # init-db migrated an existing warehouse and copied nothing, while two other
    # docstrings promised that could not happen. Three lines carry that argument
    # -- the fix, the false promise, and the migration it was false about -- and
    # the entry is unreadable standing at any other line.
    ("docs/RULINGS.md", "scrapex/cli.py", 54,
     "def _back_up_before_init_db_advances_a_schema("),
    ("docs/RULINGS.md", "scrapex/databases/registry.py", 130,
     "codebase may migrate an existing file."),
    ("docs/RULINGS.md", "scrapex/databases/domain.py", 206, "applied = self._migrate(conn)"),
    # ...and the two refusals that send him to that command in the first place.
    ("docs/RULINGS.md", "scrapex/databases/domain.py", 329, "init-db"),
    ("docs/RULINGS.md", "scrapex/warehousemerge.py", 229, "`scrapex init-db` on the older"),
    # The other two Phase 0 guards, both of which close a gap that reported
    # success: a checksum over a corrupt database, and a digest nobody compared.
    ("docs/RULINGS.md", "scrapex/bundle.py", 122, "def refuse_a_damaged_warehouse("),
    ("docs/RULINGS.md", "extension/drive.js", 346, "export async function verifyStored("),
    # OP-44's ENTIRE EVIDENCE is this line: the refusal names `--force` and no
    # such flag exists. A reader one line off sees an ordinary message and
    # closes the entry.
    ("docs/BACKLOG.md", "scrapex/warehousemerge.py", 140, "--force"),
    ("docs/BACKLOG.md", "scrapex/cli.py", 1248, '"--claim"'),
    # Q-20 is a choice between three merge operators, and this is the operator.
    ("docs/BACKLOG.md", "scrapex/warehousemerge.py", 329,
     "seen_count    = MAX(seen_count, excluded.seen_count)"),
    ("docs/STATE.md", "scrapex/warehousemerge.py", 329,
     "seen_count    = MAX(seen_count, excluded.seen_count)"),
    # ...and its consumer, which is why the choice matters rather than being taste.
    ("docs/BACKLOG.md", "scrapex/sightings.py", 589, "SELECT seen_count, COUNT(*)"),
    # "delete and rebuild everything derived" is impossible -- the delete is
    # refused by a trigger and what runs is this upsert. Both documents said the
    # opposite until 2026-08-22.
    ("docs/STATE.md", "scrapex/extract/service.py", 576,
     "ON CONFLICT(dataset_definition_id, record_key) DO UPDATE SET"),
    ("docs/RULINGS.md", "scrapex/extract/service.py", 576,
     "ON CONFLICT(dataset_definition_id, record_key) DO UPDATE SET"),
    # Q-22 · REQ-26 is not built and he believes it is. All three lines are the
    # evidence, and the third is a docstring saying so in its own words.
    ("docs/BACKLOG.md", "extension/accounts.js", 1,
     "The accounts this browser REMEMBERS"),
    ("docs/BACKLOG.md", "scrapex/databases/registry.py", 23, "DATABASE_ROOT = Path("),
    ("docs/BACKLOG.md", "scrapex/account.py", 9, "It does not yet put"),
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
