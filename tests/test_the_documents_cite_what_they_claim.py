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
    "CLAUDE.md",
    "ENGINEERING.md",
    "docs/STATE.md",
    "docs/REQUESTS.md",
    "docs/RULINGS.md",
    "docs/BACKLOG.md",
    "docs/LESSONS.md",
    "docs/APPROACHES.md",
    "docs/ORCHESTRATION.md",
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
    ("docs/STATE.md", "scrapex/version.py", 517, '"latest_extension_version": VERSION'),
    ("docs/STATE.md", "scrapex/webui/app.py", 1761, '"latest_extension_version": VERSION'),
    ("docs/STATE.md", "extension/app.js", 612, "latest_extension_version"),
    ("docs/STATE.md", "scrapex/version.py", 76, 'VERSION = "'),
    ("docs/RULINGS.md", "scrapex/webui/app.py", 1761, '"latest_extension_version": VERSION'),
    ("docs/RULINGS.md", "scrapex/version.py", 517, '"latest_extension_version": VERSION'),
    # The two flags whose condition is met and whose lighting is the owner's call.
    ("docs/STATE.md", "scrapex/features.py", 54, "True"),
    ("docs/STATE.md", "scrapex/features.py", 65, "True"),
    # B2 step 2 -- "do not write a second one". The instruction is to EXTRACT
    # these two, so a reader sent to the wrong line writes the duplicate instead.
    ("docs/STATE.md", "extension/app.js", 1583, "async function loadSourceColumns("),
    ("docs/APPROACHES.md", "extension/app.js", 1583, "async function loadSourceColumns("),
    ("docs/APPROACHES.md", "extension/app.js", 1622, "async function saveSourceColumns("),
    # The guards the documents claim exist. A rule that cites a dead guard is a
    # rule with nothing behind it -- which is how W4 came to be believed.
    ("docs/RULINGS.md", "tests/test_version.py", 536,
     'assert.equal(manifest.version, VECTORS.version)'),
    ("docs/LESSONS.md", "tests/test_version.py", 536,
     'assert.equal(manifest.version, VECTORS.version)'),
    ("docs/RULINGS.md", "tests/test_version.py", 79, "pyproject"),
    # OP-2's two worker_alive computations, one of which the fix never reached.
    #
    # BOTH RE-READ 2026-08-23, and this pair is the one where reading matters most:
    # `"worker_alive"` appears TWICE in `app.py` and the two rows below are exactly
    # those two occurrences, so arithmetic on a diff cannot tell them apart. The
    # first is in `/api/health`, three lines under `latest_extension_version`; the
    # second is inside `_about`. Identified by reading the enclosing function, not
    # by adding a delta -- and the two deltas differed anyway, because the branch
    # that moved them edited `app.py` in two separate places.
    #
    # RE-READ AGAIN after rebasing onto #261, which also inserted into `app.py`.
    # Both sides of the rebase had CHANGED these two numbers -- main said 1554/2598,
    # this branch said 1673/2666, and the answer after both diffs is neither. That is
    # the case for reading over resolving: taking either side of the conflict would
    # have produced a confidently wrong pin.
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 1772, '"worker_alive"'),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 2842, "def _about("),
    ("docs/BACKLOG.md", "scrapex/webui/templates/settings.html", 151, "about.worker_alive"),
    # BV-3's chain, end to end: the panel posts it, capture reads it.
    ("docs/BACKLOG.md", "extension/app.js", 853, "crawl_honour_delay:"),
    ("docs/BACKLOG.md", "scrapex/capture.py", 95, "crawl_honour_delay"),
    # OP-21 · the resume that saves the write and none of the requests. This is a
    # citation of a DEFECT at an exact line, so it is the kind that must not drift:
    # a reader sent one line off reads `store`'s docstring, agrees with it, and
    # concludes the entry is wrong. If someone moves this check into the walk, the
    # entry is answered and this row should go with it.
    ("docs/BACKLOG.md", "scrapex/snapshotcrawl.py", 180, "if page.url in seen:"),
    ("docs/LESSONS.md", "scrapex/snapshotcrawl.py", 180, "if page.url in seen:"),
    # OP-22 / LESSONS §2 · one database, and where it is. That section described
    # the pre-collapse split layout in the present tense until 2026-08-20, so the
    # line naming the single file is worth holding still.
    ("docs/LESSONS.md", "scrapex/databases/registry.py", 33, "DEFAULT_ENGINE_PATH"),
    # The partition crawl's shared vocabulary. STATE.md sends a reader here to
    # learn what a cell IS before reading how one is witnessed.
    ("docs/STATE.md", "scrapex/pagesource.py", 67, "class Cell:"),
    # The `0058` row was removed on 2026-08-29 with the stream that held the file. It is
    # not a pin that stopped mattering -- the file it pinned no longer exists, and a pin
    # on a deleted file can only ever fail. `PINNED_FLOOR` is what stops this becoming a
    # way to make a red build green.
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
    ("docs/BACKLOG.md", "extension/app.js", 3405, 'text: "Not detected"'),
    # OP-34 · why a black window leaves no trace. The whole finding is that this
    # function DELIBERATELY does nothing when it has real streams, which is the
    # double-click case -- so the log is not evidence about a failed launch.
    ("docs/BACKLOG.md", "scrapex/cli.py", 988, "def _bind_log_streams("),
    # OP-49's evidence is a SENTENCE of prose, and it drifted twice inside one
    # branch: 611 -> 691 -> 755, each time landing on a real, non-blank line
    # that tier 1 and tier 2 both accepted. A citation of prose needs pinning more
    # than a citation of code does -- code has a symbol a reader can grep for, and a
    # paragraph about palette tokens reads exactly as plausibly as one about layers.
    ("docs/BACKLOG.md", "docs/LESSONS.md", 840, "The extension's layers are three"),
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
    # THE `app.js` LINE THIS ROW HELD IS GONE, and it went with the defect rather
    # than being loosened to keep passing — the same call `OP-36` records above.
    # `return ""` for a dataset is what OP-42 was about; the pin follows the
    # argument to the filter that replaced it.
    ("docs/BACKLOG.md", "extension/app.js", 4775,
     "SOURCE_ACTIONS.filter((item) => item.proof === RESOLVES_A_DATASET)"),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 757, '"kind": "dataset",'),
    # 2710 -> 2725 -> 2787 -> 2911, and the fourth move is the same story as the
    # first three.
    # #252 measured this line on `main` at 4615a14, #251 landed first and added 15
    # lines to `app.py` above it, and `main` was red between the second merge and
    # the fix. #255 then inserted above it again, and the REQ-37 branch inserted
    # `_dataset_listing` above it after that. Five pull requests, none wrong on
    # its own base -- which is why the number is re-read out of the file on every
    # rebase and never adjusted by arithmetic. This rebase re-read all four.
    #
    # AND THIS ONE ALSO HAS TWO OCCURRENCES, which is why "re-read" is not a slogan.
    # `if source_key not in known:` sits in `api_rename_source` as well. The one
    # this row means is the export route -- the document's claim beside it is that
    # `/api/export/{key}` "validates the key against `manifest.sources` and answers
    # 404 for anything else" -- and only reading the enclosing function separates
    # them. A delta applied to the old number would have picked the right line here
    # by luck and the wrong one the first time the two moved apart.
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 3212, "if source_key not in known:"),
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 1234,
     "A GENERIC DATASET IS A TABLE LIKE ANY OTHER TABLE"),
    # OP-44 · the dataset card that said "no successful crawl yet" over 17,304
    # crawled rows. Four citations carry the whole argument, and a reader sent one
    # line off would conclude the entry is wrong about each of them in turn.
    #
    # The sentence itself, so it is clear the card reads a MISSING key and not a
    # missing crawl -- which is why writing a `crawl_run` row would not have moved
    # this line at all.
    ("docs/BACKLOG.md", "extension/app.js", 4647, "const last = s.last_success;"),
    # Why the row could not honestly be written: the column is NOT NULL into
    # source_site, and muqawil is in source_site.
    # 122 -> 91 WITH THE SUBJECT MADE UNIQUE. `REFERENCES source_site(source_id)`
    # matched one line when this row was written and matches SEVEN in the squashed
    # baseline, so tier 2 could no longer tell which line it meant -- a pinned
    # subject has to be as unique as the line it guards. Recovered from the
    # pre-squash file rather than guessed: it is `crawl_run`'s NOT NULL foreign
    # key, which is `OP-44`'s argument.
    ("docs/BACKLOG.md", "db/engine/schema.sql", 91,
     "source_id           INTEGER NOT NULL REFERENCES source_site(source_id)"),
    # The index that is worth 390x and had no reader. The entry's claim is about
    # its COLUMN ORDER, so it has to be read where the order is written.
    ("docs/BACKLOG.md", "db/engine/schema.sql", 1191,
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
    ("docs/BACKLOG.md", "extension/app.js", 3551, "latest.version"),
    # 488, and it was 379, 352, and 344 before that. THREE times now the same
    # pull request
    # has added comment lines above it and had to correct the number it had just
    # written down — the guard catching its author, in the exact shape LESSONS §7
    # describes. The third move was the 0.3.0 packaging fix, which explained the
    # new `ScrapeX UI` demand in twenty-seven lines of comment directly above.
    # REPOINTED 540 -> 553 on 2026-09-02: `OP-122` inserted thirteen lines into
    # `ceiling()` above it, so the subject moved and the citation had to follow. A
    # legitimate repoint -- the symbol still exists and this row's whole job is to
    # sit beside it -- unlike the two `LESSONS` entries whose numbers were the
    # RECORD and were destroyed by being repointed.
    #
    # AND THE DOCUMENT SIDE OF THIS ROW IS GONE. `docs/BACKLOG.md` contains no
    # citation to this file at any line: measured, `grep -n "release-engine.yml[#:]"`
    # over every document returns nothing. So this row asserts that the workflow
    # still holds `"version": VERSION`, which is true and worth asserting, but it is
    # not what tier 2 is for -- and nothing here can tell the difference, because no
    # test checks that a pinned row's DOCUMENT still cites it. It also counts toward
    # `PINNED_FLOOR`. Left in place rather than deleted, because removing rows is
    # exactly what that floor exists to refuse; recorded in `OP-122`.
    ("docs/BACKLOG.md", ".github/workflows/release-engine.yml", 553, '"version": VERSION'),
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
    # LESSONS §13 · a test named in a docstring is a citation. All four of these are
    # the section's ARGUMENT rather than decoration, and each fails differently if a
    # reader lands off it. The clamp is the section's whole point about citing a live
    # rule instead of a test that measured it -- land off that and the advice reads as
    # unsupported. `settle_view` is the case that proves the class, and the other two
    # are the mechanism the section says replaced deciding honesty by adjacency: the
    # declared allowlist, and the check that a row is READABLE where it claims.
    ("docs/LESSONS.md", "design/components.css", 380,
     "min-height: var(--control-height)"),
    ("docs/LESSONS.md", "tests/test_panel_dom.py", 160, "def settle_view("),
    ("docs/LESSONS.md", "tests/test_the_tests_name_tests_that_exist.py", 86,
     "HISTORICAL = {"),
    ("docs/LESSONS.md", "tests/test_the_tests_name_tests_that_exist.py", 160,
     "def test_a_historical_test_is_still_readable_where_the_row_says("),
    # OP-46 · THE CONDITION BELOW FIRED, AND THESE TWO ROWS ARE ITS DISCHARGE.
    #
    # The condition, written here on 2026-08-22 and kept for the record: `OP-46` cites
    # seven lines in `extension/app.js` and pinned none of them, because that file was
    # under concurrent edit when the entry was written -- pinning a line another branch
    # is moving is how `scrapex/webui/app.py:2710` above became 2725 and then 2787. It
    # said: pin those two symbols the next time you add a row here AND
    # `extension/app.js` is quiet.
    #
    # It was written beside the mechanism rather than in `OP-46` because this table is
    # re-read whenever someone adds a row, while a BACKLOG entry is read only when
    # someone goes looking for work -- so the instruction had to fire while its reader
    # was doing something else. IT DID, TWICE: once refusing to pin while #258 was open
    # against that file, and once here, releasing.
    #
    # Discharged at `d10e974`, after #258 landed, having checked BOTH halves rather than
    # assuming either: no open pull request's own diff touches `extension/app.js`, and
    # all four of `OP-46`'s citations into it still name their symbols after #258 moved
    # that file. The remaining five citations in that entry stay unpinned on purpose --
    # they are the measured numbers, not the two symbols the argument rests on.
    ("docs/BACKLOG.md", "extension/app.js", 945,
     "function setupFinanceConverterSelect("),
    ("docs/BACKLOG.md", "extension/app.js", 1997, "function setupRunModeSelect("),
    # AND THE ONE CITATION THE ANCHOR SWEEP FOUND ACTUALLY FALSE. `docs/BACKLOG.md`
    # quotes this docstring as the reason the panel hides Update/Wipe/Rename on a
    # dataset row, and it read `app.py:706` under `#L697` -- two different wrong
    # numbers, while the subject sat at 665. Tier 1 could not see it: 706 is a real,
    # non-blank line of the same function. Pinned because the argument in that entry
    # rests on the quote, and a quote whose line has drifted is a quote a reader
    # cannot check. Its six neighbours were only stale HREFS under correct labels and
    # stay unpinned -- the new label/anchor test is the guard they needed.
    ("docs/BACKLOG.md", "scrapex/webui/app.py", 715,
     "the row menu offers Update,"),
    # `OP-66`'s account of R-51 rests on WHICH array `merge_locales` reads, and the
    # citation for it was false in both halves once before: it named :1589, R-51
    # pushed ninety lines above it, and it landed on another function's docstring
    # while the claim itself had also changed. Repaired to :1702 and PINNED here,
    # because a citation whose whole job is to show the reader the shifted index is
    # a citation that has to be ON that line. Tier 1 alone would not notice again.
    # AND IT DRIFTED AGAIN BEFORE THE INK WAS DRY, thirteen lines, from correcting
    # the module header above it in the same commit -- which is the whole argument
    # for pinning it rather than trusting a number in prose.
    ("docs/BACKLOG.md", "scrapex/extract/muqawil.py", 1818,
     "arabic_value = arabic.values[arabic_index]"),
    # EVERY `extract/service.py` CITATION IN THE GUARDED DOCUMENTS, pinned together on
    # 2026-08-29 after nine of them drifted at once and NOTHING here noticed.
    #
    # `#281` inserted `_confirm_seen` at line 303 -- 53 lines above all of them. Tier 1
    # passed because the file is long enough; `test_no_citation_lands_on_a_blank_line`
    # passed because a 53-line shift in a file this dense lands on CODE, not on a gap;
    # and tier 2 never looked, because none of the nine was here. So `BACKLOG.md` sent a
    # reader to `return dataset_id, fields` for a sentence about pagination, and the
    # build stayed green through two pull requests.
    #
    # The lesson the file already states -- "writing a citation that matters means adding
    # a row here" -- is now applied to the whole family rather than to whichever one
    # happened to break last.
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 561,
     'and recovered["schema_hash"] == schema_hash'),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 667,
     "last_seen_at=strftime"),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 978,
     "Pagination is what saves the render"),
    ("docs/LESSONS.md", "scrapex/extract/service.py", 978,
     "Pagination is what saves the render"),
    # THESE TWO WERE REPLACED, NOT DELETED, on 2026-08-29. They pinned
    # `WHEN THE MOST RECENT CRAWL SAW ANYTHING` and `newest = conn.execute(` -- the
    # `MAX(last_seen_at)` comparison `R-54` was written against. Its second half removed
    # both from the codebase, so the pins move to what took their place rather than
    # leaving the new mechanism unpinned; deleting a row to make a red build green is
    # what `PINNED_FLOOR` exists to refuse.
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1003,
     "WHICH RUN LAST WROTE INTO THIS DATASET"),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1065,
     "latest_run = runs.latest_run_for("),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1075,
     "for key, seen, absent in conn.execute("),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1174,
     'presentation.get(row["field_key"])'),
    ("docs/BACKLOG.md", "scrapex/extract/service.py", 1177,
     "His ORDER only once he has actually arranged"),
    # NOT REMAPPED, AND THAT IS THE POINT OF READING EACH ONE. Before `#281` this pointed
    # at the closing `\"\"\"` of the docstring; the +53 shift landed it on the `def` that
    # `STATE.md`'s sentence actually names. Applying difflib blindly would have put it
    # back on the quote -- a repair that made the citation worse.
    ("docs/STATE.md", "scrapex/extract/service.py", 927,
     "def dataset_table_payload"),
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
#: The floor may only be RAISED. Raised from 7 to 23 on 2026-09-04 by the entries
#: `OP-133`..`OP-142`, measured with `_quoted_subjects()` rather than counted by
#: hand -- the same way the 7 was arrived at, and for the same reason: a floor
#: written from memory is a floor that means nothing.
#:
#: It fails when the count drops, so a labelled block cannot be quietly unlabelled to
#: silence a red; it does NOT fail when a new unlabelled block appears, because
#: reddening a correct record is the direction this design refuses to be wrong in.
#: That turns "somebody forgot to label" from invisible into merely known, which is the
#: most a declaration can offer.
FENCE_FLOOR = 23


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


def test_the_orphan_set_only_ever_shrinks(index):
    """A ratchet, not an exemption list.

    Every row named there must STILL be an orphan. When somebody repairs one -- by
    citing the line, or by pinning the line the document actually cites -- this fails
    and makes them delete the row, so the set cannot quietly become a place where
    fixed things are still excused. That is the failure `PINNED_FLOOR` itself was
    written against, one level up.
    """
    orphans = set(_pinned_orphans(index))
    repaired = sorted(set(PINNED_WITHOUT_A_CITATION) - orphans)

    assert not repaired, "\n  ".join([
        "these rows are named as having no citation, and they have one now. Delete "
        "them from PINNED_WITHOUT_A_CITATION -- the set is a count coming down, and "
        "a stale entry in it is one more row that guards nothing while looking "
        "accounted for:", *(f"    {row}" for row in repaired)])


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
