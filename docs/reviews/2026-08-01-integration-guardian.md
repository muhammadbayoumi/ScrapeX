# Integration review — 2026-08-01, against main `322e205`

Run as the project's Senior Reviewer / Integration Guardian: every open PR merged
onto TODAY'S main first, then judged on the merged diff, not on the patch its
author submitted.

**Why this file exists.** The `integration-guardian` workflow did not fail — it was
still running when the previous Claude Code process exited, so no completion
record was written. Seven of its eleven agents finished; their full returns are
saved beside this file in `2026-08-01-integration-guardian-raw.json` (104 KB, the
verbatim structured output including every finding's evidence). Four never ran.

```
Workflow({scriptPath: "<session>/workflows/scripts/integration-guardian-wf_d8cf0fb1-b8d.js",
          resumeFromRunId: "wf_3a67ae8e-8d0"})
```

Completed agents replay from cache; only the four unrun ones cost anything.

---

## 1. The headline: a whole feature merged into a branch that had died five seconds earlier

| time | event |
|---|---|
| `2026-08-01T05:03:54Z` | **PR #48** `codex/fix-idle-ui-cpu` → **main**, squash-merged as `0c1571a`, carrying four files: `jobs.py`, `rates.py`, `tests/test_idle_cost.py`, `tests/test_rates.py`. |
| `2026-08-01T05:03:59Z` | **PR #51** `codex/google-finance-control` → **`codex/fix-idle-ui-cpu`** — *not* main. Merged into a branch that had been consumed five seconds earlier. |

GitHub reports #51 as MERGED, truthfully: it was merged into its stated base. That
base no longer fed anything. Sixteen files and 934 insertions went nowhere.

Proof main has none of it: `GET /api/rates/google-finance` 404, `GET
/data/google-finance` 404, `POST /api/rates/google-finance/refresh` 404, `POST
/api/settings` 400 `unknown setting 'google_finance_auto_refresh'`.

This explains three things at once: the owner's report that Google Finance is
missing from settings; PR #67's false premise that "its server half is on main";
and why `codex/fix-idle-ui-cpu` and `codex/google-finance-control` have identical
trees (#51's merge put the second inside the first).

Re-targeted as **PR #72**.

---

## 2. Verdicts

| PR | verdict | one-line reason |
|---|---|---|
| **#70** (new) | merge first | the rates window test had stopped testing the window |
| **#68** | approve | three real defects found in it by review, all corrected |
| **#72** (new) | approve, one conflict | the stranded feature of §1 — the owner's Google Finance item |
| **#66** | approve with conditions | update the branch from main first; display half missing |
| **#54** | approve with conditions | docs only; its red CI was never its fault |
| **#67** | **close** | superseded by #72, and carries three regressions #72 does not |
| **#63** | **rework** | a revert disguised as a feature, and two of three consumers do not move |

### #67 — close it

Seven findings, **all seven survived adversarial refutation** (2 blocking). Its
premise is false: `afb8df5` is not an ancestor of main and none of its fourteen
files landed, so restoring the extension two of them completes nothing — it ships
a settings section whose every control 404s. It also deletes two `<small>`
captions main added deliberately, resurrects the `opens-down` class `94a67b0`
removed, and ships 117 lines with **no test** (the suite is identically green with
the production half fully reverted: 1706 passed either way).

**Measured: #72 alone does none of this.** `opens-down` count 0, both `<small>`
captions kept, all five panel ids present, the `app.js` handler present, full
suite exit 0. #72 is a real three-way merge, so main's later edits win on lines
the branch never touched; #67 was a content restore from `afb8df5`, which
re-imposed the old file wholesale. Closing #67 also drops its second commit
`85ec935`, which is all of #63 — nothing is lost.

### #63 — send back with three requirements

1. **Use `*_level_columns()` inside the ordering block** instead of re-typing
   twenty tuples by hand. Commit `d9e6f7a` introduced that generator on purpose;
   this PR orphans it. **Measured**: raising `CATEGORY_LEVELS` 10 → 12 gives
   22 → 26 category columns on main and **22 → 22** on #63. The constant is inert
   and the file's own promise ("raising it further is one line") is now false.
2. **Move the order in `dataset_field.display_order` too.** Only the grid moves.
   The Choose-Columns panel and the Current-View export read `display_order`, and
   `ensure_fields` is documented never to rewrite an existing row — so on any
   warehouse whose sources have been opened once (the owner's included) they keep
   the OLD order. "The price sits in the same place in every table" is met in one
   surface out of three.
3. **Update `docs/data-page-schema.md`**, which calls itself "the ruling" and
   still states the order this PR reverses, plus the comment eighteen lines above
   the list.

The reorder itself is sound: same 50 keys, no label changed, per-source presence
gates (including the USD-estimate leak guard) provably unchanged, and `grid.js`
takes column order from the server payload.

### #66 — merge after bringing the branch up to date

Merges clean onto main despite being 16 behind; main never touched
`custom_json.py`. **Merged result: 1712 passed, 1 xfailed, exit 0.** Its red CI is
entirely the stale base. **Not** redundant with main's `8fe16e6`: that fixed the
INGEST gate, this fixes the CONNECTOR — complementary halves.

*Condition:* `stock_quantity` is invisible to a reader. Verified independently —
zero occurrences in `reports.py`, `grid.js` and `extension/`. The value is
captured (irreversibly good) but no column, export or panel shows it. Open a
follow-up; do not block the capture on it.

### #54 — re-run CI, then merge

Docs only. Its two red checks came from `tests/test_rates.py`, a file it does not
touch — see #70. Six non-blocking findings, notably: the new section specifies a
per-backend **settings surface without naming the extension as its home**
(contradicts the standing rule); it is grounded in Topology B, which the same
file's header records the owner rejecting; it renumbers Open Decisions 8 → 9 and
breaks two live cross-references in `docs/BACKLOG.md`; and §8.1 forbids
overloading the word "engine" while §8.5 names something "Engine Manager".
Merged result: 1704 passed / 1 xfailed / 0 failed.

### #68 — corrected

Review raised seven findings, two blocking. A second, adversarial pass downgraded
the three biggest to nit/minor/nit. **I verified them myself and fixed them
anyway**, because the fixes cost nothing and the defects were real: the `title`
was a strict prefix stopping at "UTC" and omitting `· 19,548 rows seen`, i.e.
exactly the tail the ellipsis removes; the test asserted `grid-row:1` on
`.dataset-choice > .source-identity-meta`, a selector matching no element (proved
by rendering a card — the badge is nested inside `.source-identity-footer`); and
the comment blamed the badge for occupying column 2, when nothing occupies it —
the card is `minmax(0,1fr) auto`, the caption was the only item in the `auto`
track, and column 1 paid for its width. Recorded as a disagreement, not a
correction: the refuter's severity call may be right, the defects were still real.

---

## 3. Branch inventory (branches with no PR)

Measured with `git merge-tree --write-tree origin/main <branch>` against main's
tree — the only test that answers "would merging this change anything at all".

**Ten branches are no-ops** — content already on main, safe to retire with nothing
lost: `claude/ecstatic-jang-dc20e8`, `claude/exciting-mclaren-7cb60e`,
`claude/happy-swartz-9ca21d`, `claude/sleepy-bun-0e0d1f`,
`codex/fix-windows-job-overlap-test`, `codex/remove-noop-jobrunner-wake`,
`codex/ui-split-button`, `docs/source-register-and-candidate-queue`,
`fix/the-lag-guard-compares-like-with-like`, `perf/tests-run-in-minutes-not-hours`.

**Three still carry genuinely new work:**

- `codex/google-finance-control` ≡ `codex/fix-idle-ui-cpu` (identical trees) → **PR #72**.
- `claude/angry-mendeleev-02e225` — heidelberg: 1,693 insertions, 467 lines of
  tests, a `CAPTURE.md` recon document and six fixtures. **Unreviewed, no PR.**
- `codex/workspace-overview-ui` — **never merge**. It moves the asset version
  `design-system-2 → 3` while main is at **design-system-45**: merging would serve
  a 42-version-stale stylesheet and grid script. Its actual fix (a spacer for the
  empty icon name that killed every three-dot menu) is already on main at
  `grid.js:620-624` with a fuller comment. Only
  `makeHeaderPopupButtonsAccessible()` (~10 lines of aria-label) is unmerged, and
  it needs re-deriving against today's header, not merging.

---

## 4. What changed during this review

| PR | what |
|---|---|
| **#70** | the rates window test had stopped testing the window |
| **#68** | the three corrections above |
| **#72** | re-targeted the stranded Google Finance feature |

**#70 in full.** The test stored the first rate with the REAL clock and asked
whether it was stale at a hard-coded `2026-08-01T00:00:00Z` — a bomb with a
six-hour fuse. CI for #54 ran at `2026-07-31T18:17Z`, 5h43m before the named
instant, inside the window: not due, red. Once real time passed that date the age
went **negative**, and `refresh_is_due` returns `not (0 <= age < REFRESH_AFTER_S)`,
which calls a negative age due — so it went green again while testing nothing.
**Measured: it still passed with `REFRESH_AFTER_S` set to ten years.** Now every
instant is stated: first fetch at `T`, not due at `T+5h59m59s`, due at exactly
`T+6h`. The negative-age branch that hid it is pinned in its own test.

---

## 5. Tests, on the actual merged results

| combination | result |
|---|---|
| main + #67 + #72 + #70 | pytest exit 0, 0 FAILED; parity 3/3; extension & apps_script exit 0; manifest OK |
| main + **#72 alone** | pytest exit 0, 0 FAILED; parity exit 0; extension exit 0 |
| main + #66 | 1712 passed, 1 xfailed |
| main + #54 | 1704 passed, 1 xfailed, 0 failed |
| main + #68 (corrected) | exit 0; both new guards proved to bite |

Duplication check after #67 + #72: every panel id appears **exactly once**.

**The repo has no linter and no type checker** — no ruff, mypy, flake8, black or
pyright, and no config for any. CI is six gates: `validate-manifest`, "the panel
suite must RUN not skip", `pytest`, contract parity, `node --test
extension/tests`, `node --test apps_script/tests`.

---

## 6. Merge order

1. **#70** — first. While that test is a bomb every red CI in the repo is suspect;
   it already misled us about #54. Merge, then re-run CI on every open PR.
2. **#68** — the dataset-list fix. Needs a hard refresh after merging.
3. **#72** — one conflict, `scrapex/rates.py` only, four hunks; the recommended
   resolution for each is in the PR body.
4. **#66** — after bringing the branch up to date. Follow-up for the display half.
5. **#54** — after re-running CI.
6. **Close #67.**  7. **Return #63** with the three requirements above.

---

## 7. Still to do

**Four workflow agents never ran** — resume with the command at the top:

- adversarial refutation of the #66 findings
- adversarial refutation of the #63 findings
- **cross-PR semantic conflict analysis** and a merge order derived from it
  (asset-version collisions, column-contract drift, the formatter monopoly #45
  claims, shared template regions)
- **stale-branch assessment** for #45 (16 behind, conflicts, 26 files), #40 (24
  behind, conflicts, 21 files), #39 (29 behind), #60 (10 behind) — the two
  conflicting drafts block the owner's timezone and version-management items
- **regression-gap hunt**: which load-bearing behaviours no test protects, and the
  tests to close them. Two gaps are already known: nothing guards an asset version
  being LOWERED (see `codex/workspace-overview-ui`), and nothing guards a template
  advertising an extension section that does not exist (the #51 accident).

**Also open:**

- `claude/angry-mendeleev-02e225` (heidelberg, 1,693 lines) is unreviewed.
- The ten no-op branches can be retired.
- **One decision for the owner:** in #72, hunk 4 replaces `refresh_if_due`'s body
  with `return refresh_now(...)`. `refresh_now` does preserve the
  commit-before-fetch ordering, but its two-line comment replaces main's long one
  recording why — a blocked quote page once became a request every half-second.
  Recommendation: keep main's comment inside `refresh_now`.
