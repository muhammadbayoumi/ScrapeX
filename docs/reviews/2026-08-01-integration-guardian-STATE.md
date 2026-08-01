# Where the integration review stands — end of 2026-08-01

Read this first, then the full review in `2026-08-01-integration-guardian.md`.
That file describes the state at main `322e205`; **this file supersedes its
verdict tables**, because everything it recommended has since been done.

`main` is at **`fdc0367`** and **CI is green** on the last three commits
(`fdc0367`, `3991e6d`, `91526c4`).

---

## Done — merged in the recommended order

| # | PR | what it was |
|---|---|---|
| 1 | #70 | the rates window test had stopped testing the window — merged first so every other red CI became trustworthy |
| 2 | #68 | the dataset-list caption crushing the source name (owner item ②) |
| 3 | #73 | the review record itself |
| 4 | #72 | **Google Finance controls and dataset** — the feature PR #51 merged into a branch that had died five seconds earlier (owner item ③) |
| 5 | #66 | SIKAEGSHOP's stock count on the price row |
| 6 | #54 | the crawler-backend docs plan |

**#67 closed** — superseded by #72, which does the same job without three
regressions it carried (`opens-down` resurrected, two Appearance `<small>`
captions deleted, 117 lines with no test).

**#63 returned for rework** with three measured requirements — see below.

Verification after all merges, on `main` itself: `pytest` exit 0 / zero FAILED,
contract parity exit 0, `node --test extension/tests` exit 0, `node --test
apps_script/tests` exit 0, `validate-manifest` OK (11 sources). Google Finance is
now genuinely present: 27 references in `scrapex/webui/app.py`, 4 in
`extension/app.html`, 2 in `scrapex/settings.py` — all three were zero before.

### One semantic conflict, caught by a test rather than by git

Merging #72 failed `test_every_dataset_freshness_state_can_be_read_in_full`, a
guard that had landed with #68 an hour earlier. #72 adds a third dataset card for
the rates dataset, and its caption shipped with no `title`; #68 clamps everything
inside `.dataset-choice-detail` to one line, so "Ready - refresh after price data
is collected" (44 chars) became truncatable with no way back to it. Git reported
no conflict because there is no textual one. The third caption now follows the
same rule: built once, used for both the text and the title.

### One judgement call made without waiting for the owner

In #72 hunk 4, `refresh_if_due` delegates to the new `refresh_now`. **Main's long
comment was moved into `refresh_now`** rather than being replaced by the branch's
two-line summary. It records a real incident: an escaping `CrawlBlocked` rolled
the throttle stamp back and a blocked quote page became a request every half
second, each preceded by rebuilding the 1.3s HTTPS client. `refresh_now` does
preserve the commit-before-fetch ordering; the paragraph is what stops someone
reordering those statements later. Reverting is one line if the owner disagrees.

---

## Open — nothing here has been reviewed against today's main

Eight PRs, all drafts except #63. Measured at `fdc0367`:

| PR | state | behind | files | what |
|---|---|---|---|---|
| #63 | ready, CLEAN | 6 | 2 | the column reorder — **returned, see below** |
| #65 | draft, CLEAN | 6 | 5 | gallery: the picture the shop leads with |
| #64 | draft, CLEAN | 6 | 2 | compaction successor built as the warehouse's own kind |
| #43 | draft | 6 | 8 | images both SSR shops publish in markup but not JSON-LD |
| #45 | draft | 6 | 28 | **display-only time zone, one formatter** — blocks owner items ④⑤ |
| #60 | draft | 16 | 4 | restore ARAMCO's header, move Sika's note |
| #40 | draft, **DIRTY** | 30 | 21 | **Version Management** — blocks owner item ⑥ |
| #39 | draft, CLEAN | 35 | 27 | OPFS spike |

#40 conflicts with main and is 30 commits behind. #45 is the other item the owner
is waiting on. Neither has been assessed.

### #63 — the three requirements it was returned with

1. **Use `*_level_columns()` inside the ordering block** instead of re-typing
   twenty tuples. `d9e6f7a` introduced that generator deliberately; the PR
   orphans it. Measured, raising `CATEGORY_LEVELS` 10 → 12: main gives 22 → 26
   category columns, the PR gives **22 → 22**. The constant is inert and
   `reports.py:593` still promises "raising it further is one line".
2. **Move the order in `dataset_field.display_order` too.** Only the grid moves.
   The Choose-Columns panel and the Current-View export read `display_order`, and
   `ensure_fields` never rewrites an existing row — so on any warehouse whose
   sources have been opened once they keep the OLD order.
3. **Update `docs/data-page-schema.md`**, which calls itself "the ruling" and
   still states the order the PR reverses.

The reorder itself is sound: same 50 keys, no label changed, presence gates
unchanged, `grid.js` takes order from the server payload.

---

## Resume the review: four agents never ran

The `integration-guardian` workflow did not fail — it was still running when the
process exited. Seven of eleven agents finished; their verbatim returns are in
`2026-08-01-integration-guardian-raw.json`.

**Do not resume the old script verbatim.** Its PR list is now stale: #66, #72 and
#54 are merged and #67 is closed, so three of its five review agents would
analyse a world that no longer exists. Author the remaining work against
`fdc0367`:

1. **Adversarially refute #63's three requirements** — the reviewer may be wrong,
   and #63 is the only ready PR.
2. **#45** (28 files, blocks the timezone and date-format items) — merge onto
   today's main and assess. The owner's ruling stands: the selector lives in the
   extension, the web page displays only.
3. **#40** (DIRTY, 30 behind, 21 files, blocks version management) — name every
   conflicting hunk and say which side should win and why.
4. **Cross-PR semantic conflicts** across the eight open PRs: asset-version
   collisions, column-contract drift against #63, the formatter monopoly #45
   claims, shared template regions.
5. **Regression-gap hunt.** Two gaps are already known and unguarded:
   - nothing catches a static asset version being **lowered** (see
     `codex/workspace-overview-ui`, which would take `design-system-45` back to 3)
   - nothing catches a template advertising an extension section that does not
     exist — the exact shape of the #51 accident

---

## Also open

- **Issue #74** — SIKAEGSHOP's stock count is stored and no reader can see it.
  Zero occurrences of `stock_quantity` in `reports.py`, `grid.js` or `extension/`.
  Settle its column position together with #63.
- **`claude/angry-mendeleev-02e225`** — heidelberg: 1,693 insertions, 467 lines of
  tests, a `CAPTURE.md` recon document, six fixtures. No PR, unreviewed.
- **`codex/workspace-overview-ui`** — never merge. It moves the asset version
  `design-system-2 → 3` while main is at 45. Its actual fix is already on main at
  `grid.js:620-624` with a fuller comment. Only
  `makeHeaderPopupButtonsAccessible()` (~10 lines) is unmerged and needs
  re-deriving, not merging.
- **Ten branches are no-ops** and can be retired with nothing lost — listed in
  §3 of the main review file.
- **The repo has no linter and no type checker.** CI is six gates:
  `validate-manifest`, "the panel suite must RUN not skip", `pytest`, contract
  parity, `node --test extension/tests`, `node --test apps_script/tests`.
