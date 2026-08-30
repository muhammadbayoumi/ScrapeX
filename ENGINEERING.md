# Engineering Rules — ScrapeX Ecosystem (v1)

> Derived from the owner's review protocol and adversarially verified (traceability critic + project-fit critic, 29 findings incorporated). Every rule exists so the code **passes the corresponding review section by construction**. Rules marked *(operational)* are owner-approved additions beyond the protocol. Code/comments/docs language: English (repo convention).

**The five meta-principles (owner preferences):**
**P1** DRY-aggressive · **P2** tests non-negotiable (too many > too few) · **P3** engineered-enough (no hacks AND no premature abstraction) · **P4** edge-cases-first, thoughtfulness > speed · **P5** explicit over clever.

---

## 1. Architecture (→ review §1)

- **A1 The dependency map matches ALL real flows.** `{connectors, extension} → funnel-client → [Apps Script] → staging sheet → ingest → warehouse → publish → SYS TSV`, **plus** the curation loop (`warehouse → decision tabs → apply-decisions → warehouse`). One-way imports per edge; connectors never import each other; no undrawn edges.
- **A2 Typed DTOs at every boundary** (pydantic: `ScrapedTable`, `ObservationBatch`, `SourceConfig`) — never raw dicts across layers.
- **A3 Families only when proven.** A base class exists only after ≥1 live probed member. *Carve-out:* owner-decided infrastructure recorded in the plan is exempt (currently: `BrowserFetcher`/Playwright). `TBD-probe` sources get no family class until probed.
- **A4 Secrets never in code.** `.env` local / GitHub Secrets CI / `chrome.storage` extension. CI runs **gitleaks** (default config) — no hand-rolled secret regexes.
- **A5 Five explicit gates, each its own module + tests:** funnel token (*write*), manifest scope guard (*contract*), `curation_status` (*curation*), match review (*match* — no confidence auto-approves), feed selection (*publish*). `scope: census` is a temporary, explicit opening of the contract gate — restored to targeted after owner decisions.
- **A6 The funnel is the SPOF — durability per environment.** Local/interactive runs: persistent outbox spool + drain with retry/backoff (TelemetryOutbox pattern) + outbox size alarm. CI runs (ephemeral): in-run retry with backoff; on final failure upload the undelivered batch as a workflow artifact **and fail the job red**. Every hop has an explicit max batch size derived from platform quotas.
- **A7 Append-only is structural, enforced in the schema.** `price_observation` carries `BEFORE UPDATE`/`BEFORE DELETE` triggers that `RAISE(ABORT)`. Everywhere else retirement = `valid_to`, never deletion. *(Provenance: §1 data flow + the owner's data-safety decision: observations are immutable history.)*
- **A8 Growth is explicit.** Every query path has a covering index noted in `schema.sql`; every read of an unbounded table (`price_observation`, `crawl_run`) is paginated or capped; expected volume per table documented in the `schema.sql` header; snapshots gzip-compressed and deduped by `content_hash` (disk growth is a scaling concern).
- **A9 All SQL is parameterized; scraped content is untrusted input.** String-built SQL with interpolated values fails review. Remote content never reaches SQL, file paths, or shell un-parameterized, and is sanitized before publish.
- **A10 Single-writer topology for `harvest.db`.** CI legs END at the funnel (scrape → POST only, never touch the DB). `ingest`/`census`/`apply-decisions`/`publish` run ONLY on the owner's machine where `harvest.db` lives; the staging sheet is the buffer between the two worlds. Locally: WAL mode + `busy_timeout` + a CLI lock file so two `scrapex` commands cannot interleave writes.
- **A11 Backups are law** *(operational)*. Post-ingest rotating copy of `harvest.db` (7 daily + 4 weekly) to a second, cloud-synced location — observations can never be re-observed.

## 2. Code quality (→ review §2)

- **Q1 Single source of truth per concept.** Enums/status vocab in one module; DDL only in `schema.sql`; contracts only in `sources.yaml`; anything needed twice is generated from the one source.
- **Q1b A generated file says so, in its own first lines.** Every copy written by a generator carries `AUTHORED IN <source>` and the words `GENERATED COPY` — enforced by `tests/test_design_system.py::test_every_generated_copy_says_it_is_one`. A staleness check is not enough on its own: it fails when a copy has *drifted*, and the sync run that erases a hand-edit is the run that makes them agree again. *(2026-08-11: an engine-poll backoff was written into `extension/appearance.js`, a generated copy — correct, reviewed, merged, and one sync away from vanishing with no diff and no red test. Caught by a second reader, not by the repository.)*
- **Q1c One duplication rule for one boundary.** Where the same file must exist on both sides of the extension/engine line, it is generated from `design/` — never two hand-maintained copies held equal by a comparison. A byte-equality test can say the two have *drifted*; it cannot say **which** is right, and a reader who follows "copy one over the other" in the wrong direction reverts a fix as silently as no test would. *(2026-08-11: `timezone.js` was the one file of five following the second arrangement; it is now generated like the other four, and the comparison test is kept as a direct guard on the property.)*
- **Q2 Shared parsing mandatory, local parsing forbidden.** Money/units/ar-en digits/VAT normalization live in ONE `normalize` module — a connector parsing prices locally fails review. *(The add-in's SmartConverter lesson: one parser or producers/consumers drift.)*
- **Q3 No silent failures — ever.** No bare `except`; every caught error → structured record (`crawl_run.errors_count` + `_RUNS` detail). Per-source isolation: one source's failure never kills the run, but is always loudly visible. *(Counter-example: the add-in's BulkInsert-swallowing bug.)*
- **Q4 Every parse asserts its shape** with diagnostic messages (GPP: `len(labels)==len(values)`; Magento: required `jsonConfig` keys). Site changes fail LOUD at the parse, never as silently-wrong data.
- **Q5 Explicitness standards.** Type hints everywhere; enums not magic strings; named constants; timezone-aware UTC only; **no locale-dependent parsing** (invariant rules — the ar-SA bug is the counter-example); comprehensions ≤2 clauses; no dynamic attribute tricks.
- **Q6 One concern per file;** >~400 lines is a split signal.
- **Q7 Debt is visible and concentrations surface.** `TODO(<ref>)` only with tracking ref; no commented-out code; a file collecting its **3rd** TODO triggers a consolidation decision at the next review checkpoint.
- **Q8 No hacks.** A known workaround ships only with a `TODO(<ref>)` **and** a test pinning current behavior; copy-paste-and-tweak is a DRY defect (Q1), not a shortcut.

## 3. Testing (→ review §3)

- **T1 No module without its test file** (`tests/` mirrors package paths). *Exemption, narrowed:* Apps Script (see S1) leans on the golden contract fixtures (T8) for what it PARSES — but a fixture cannot say whether the sheet accepts or refuses a batch, and that refusal was what cost the owner a re-paste. `apps_script/tests/staging_gate.test.mjs` runs the real `StagingAppScript.txt` under a fake spreadsheet for exactly that.
- **T2 Fixture-first connector tests.** Recorded REAL responses + a re-record script; assertions EXACT (`price == 168.78`, `variant_id == "4671"`), never just non-null.
- **T3 Error-path parity.** Each happy path pairs with ≥1 failure mode: timeout, 4xx/5xx, malformed payload, empty catalog, truncated page, unexpected shape.
- **T4 Idempotency is tested:** same-run `ingest` twice → zero new observations; `apply-decisions` twice → no-op.
- **T5 Integration tests run the REAL `schema.sql`** on in-memory SQLite (incl. the A7 triggers) — schema/code drift impossible. Migrations included: apply all migrations to the previous release's fixture DB and diff against a fresh `schema.sql` build (two-way drift check).
- **T6 Gates are table-driven matrices:** scope-guard rejections; feed precedence (fresh/stale × priority × wildcards); census-mode open-then-restore; ignored-stays-ignored across re-crawl; confidence-never-auto-approves; **GPP `latest_only` rejects any historical-series row** (a license obligation, tested).
- **T7 One parametrized E2E harness** (fixture → funnel mock → ingest → asserted observation row); each family is a table entry — family #10 = one row + one fixture, not a new script.
- **T8 One versioned funnel payload contract, versioned by TWO numbers.** Single JSON Schema with golden fixture vectors in ONE directory, consumed by pytest (Python producer), vitest (extension producer), and standing as the GAS consumer's contract test. Every contract change bumps `PAYLOAD_VERSION` — the CONTENT stamp — and updates schema + fixtures in the same commit. Only a change to what a column MEANS (renamed, removed, re-united, required↔optional) bumps `PAYLOAD_COMPAT_VERSION`, and **only that number is ever gated on**: consumers accept a range of generations and never refuse a payload for carrying a newer content version. One number doing both jobs meant every added column cost the owner a hand re-paste of the Apps Script. A generation is named after the version at which it began, and `payload.GENERATION_OF_VERSION` is the ledger saying which version belongs to which. A rename is the dangerous case for a header-driven consumer, so `contracts/header-baseline.json` pins every column the current generation guarantees and the build fails if one disappears without the generation moving (`tests/test_payload_compat.py`).

## 4. Performance & scale (→ review §4)

- **F1 Batched writes in explicit transactions** (`executemany`); never row-by-row commits.
- **F2 No N+1:** ingest preloads lookup maps or uses single JOINs.
- **F3 Stream, never materialize** — catalogs iterate as generators.
- **F4 Short-circuit on hashes** (`record_hash`/`content_hash`) before heavy work; honor `ETag`/`Last-Modified` where supported.
- **F5 Politeness budget** *(operational — grounded in availability: bans/blocks are an SPOF failure)*: ≤1 req/s default, honor `crawl-delay` (elburoj 10s), request counts logged per `crawl_run`.
- **F6 Volume-sanity canary on every source:** optional manifest keys `min_expected_rows` / `max_drop_pct` vs previous run; breach or zero rows → `_RUNS` alert + non-zero exit for that source. *(The samehgabriel canary, generalized.)*
- **F7 Hot paths are linear:** loops over catalog/observation collections use dict/set lookups, no nested scans; exceptions need a justifying comment. Per-phase wall-time recorded in `crawl_run` — regressions visible in data, not vibes.

## 5. Surface-specific rules

- **S1 GAS stays dumb.** `doPost` = token check + append one chunk row + ack — zero parsing/reassembly (reassembly happens in Python at ingest, where it's testable). `LockService` around every append; chunk ≤ 40KB (clears the 50k-char cell limit with margin); total GAS logic stays under ~50 lines so the T8 contract fixtures suffice as its tests.
- **S2 Extension parsing is pure and tested.** All parsing/normalization in pure JS modules tested against fixture DOM/JSON (vitest); `chrome.*` glue stays thin and untested. The extension emits the SAME versioned payload (T8) — **no privileged path into the warehouse**; captures carry a `source_key`.
- **S3 Sheets IO is batched and bounded.** All reads/writes via `batchGet`/`batchUpdate` with exponential backoff on 429; tab regeneration writes one full replacement, never row-by-row. `RAW_*` rows are purged/archived after successful ingest — the staging sheet is a buffer, not a store.
- **S4 Decision tabs are parsed defensively.** Columns resolved by header NAME never position; enums compared case/whitespace-insensitively; unparseable rows rejected with reason → `VALIDATION_ERROR` cell, never a crash mid-tab; `ACTION` columns get DataValidation dropdowns at generation time. One "sabotaged tab" test fixture (reordered columns, bad ACTION, stale row).
- **S5 Manifest is CI-validated.** pydantic-validate `sources.yaml` on every push (known family, unique `source_key`, cadence/kind/region/authority vocab) + run the feeds cross-checks (`OUT_OF_CONTRACT`, orphaned assignments) in CI — a broken contract cannot merge.
- **S6 Migrations are numbered.** `PRAGMA user_version` + sequential migration files applied by `scrapex` on startup; tested per T5.
- **S7 Playwright flakiness policy.** 2 retries with backoff; final failure dumps screenshot+HTML into run artifacts + per-source error (Q3 isolation); no fixed sleeps — selector/network-idle waits only; chromium version pinned in CI.
- **S8 Alerts must reach the owner.** Any alert-class condition (`STALE_FEED`, `NO_FEED`, `DIVERGENCE`, volume canary) or `errors_count>0` fails the CI job — the red-run email IS the notification. The manual path (`scrapex status` / `publish`) prints per-source last-successful-run age with warning thresholds — a watchdog that survives cron death (GitHub disables idle crons after 60 days).

## 6. Process (→ review workflow)

- **W1 Small reviewable increments.** One slice per phase. After each: present what was built + top issues, then ASK before proceeding.
- **W2 Never assume priorities.** Timeline/scale/scope questions go to the owner.
- **W3 Every finding = concrete description with `file:line` refs + 2–3 options ALWAYS including do-nothing + effort/risk/impact/maintenance per option + a recommendation mapped to P1–P5 + an explicit structured question.** Never prose-only, never auto-proceed on an owner decision.
- **W4 ONE product version, and it is the EXTENSION'S.** The extension is the product a person
  sees and Chrome pushes it to every user automatically; its number is the only one that
  means anything to them. **The engine carries no version at all** — it carries a `protocol`
  number in `contracts/contract-baseline.json`, which is what compatibility is asked against,
  and the commit SHA it was built from, which is what identity is asked against. A version
  comparison is the wrong tool for compatibility because it couples the release cadence to the
  wire contract, and those are independent: the engine can ship fifty times without the wire
  moving, and break it in one line. **Nothing bumps per pull request** — the SHA is already
  exact, so "does this change deserve a bump?" is not a question anyone has to answer, and the
  five-file bump dance is gone with it. The **capability ledger stays**: "which build has X" is
  a real question and `version.CAPABILITIES` answers it, attached to the extension's version
  and the protocol rather than to an engine release number. `extension/manifest.json` is NOT a
  mirror of anything and pinning it to another number is a regression, not a tidy-up — the two
  release paths were unwelded on 2026-08-05 (PLATFORM-PLAN Decision 21, PR #112) because
  Google reviews and pushes the extension while the engine is tagged separately and installed
  only when the owner accepts. `tests/test_version.py` therefore requires both to be real
  versions and deliberately does **not** compare them. *(Ruling: [R-77](RULINGS.md#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build). Provenance:
  the trigger was rewritten five times in eleven days — every merged PR, a user-visible
  capability, a contract change, a new endpoint — because ONE number was being asked three
  unrelated questions: which build is this, can the two halves talk, and what can the product
  do. On 2026-08-29 two sessions read this rule and the comment in `scrapex/version.py`,
  reached OPPOSITE conclusions, and neither found the ruling that then governed. This section
  is the one that misled them: it cited three rulings and not the one in force. Splitting the
  three questions is what makes the rule statable in one place.)*

- **W5 `main` moves only through a pull request with green CI.** No direct pushes, including one-line and "obviously safe" ones: CI runs `on: push` as well, so a direct push does not skip the checks, it only moves them to AFTER the breakage is on the branch everyone else builds on. Read the checks as a COMPLETE set before merging — zero pending, zero failed — because an exit code describes the last thing that ran, not the set you care about (`gh pr checks --watch` returns 0 on an incomplete set, and a command ending in `echo` reports the echo's success, not the test run's). S5 already assumed this gate existed; this is the rule it was assuming. *(Provenance: `ac3a5af` was pushed straight to `main` on 2026-08-18 with no PR. It wrote a colour literal into `extension/app.css`, which `test_ui_colour_literals_live_only_in_the_canonical_colour_system` forbids, so `main` was red for ~22 hours and every pull request opened in that window inherited the failure. Every neighbouring commit went through a PR; the norm existed, it just was not written down.)*
