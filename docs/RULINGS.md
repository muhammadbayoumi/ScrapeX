# Rulings — what the owner has decided

Every decision the owner has made about ScrapeX, with the date, the reason, and
the evidence that produced it. Governed by **C3** and **C4** in
[../CLAUDE.md](../CLAUDE.md):

- A ruling is recorded here, not left in a commit message or a conversation.
- **A superseded ruling stays.** It is marked, it points to what replaced it, and
  it says what changed. The owner's view is expected to move as evidence
  arrives; the history of a decision is part of the decision.

Rulings are numbered `R-nn` in the order they were recorded. The number never
changes and is never reused.

> **Format.** Each entry states the ruling, the date, what he actually said where
> that is on record, and — where one exists — the measurement that decided it.

---

## Active

### R-01 · Diagnose, confirm, then fix — one step at a time
**2026-07-21 · process**

Explain the problem first, agree the cause, then solve it step by step. Not a fix
delivered on first contact.

> «عندى مشاكل عاوز اشرحها وبعد فهمها نحاول نحلها خطوة خطوة»

**Why:** he is the author and reasons about his own system. A fix landed before
the cause is agreed removes the evidence he needs to judge it. Prefer read-only
inspection while diagnosing — during one such session a plain `sqlite3.connect()`
created a stray `harvest.db` and destroyed the state being diagnosed.

**Apply:** present the proven root cause with `file:line` evidence, then ask
before editing.

---

### R-02 · An un-computable mapping is the owner's call, and studies come first
**2026-07-30 · process**

Where a correspondence cannot be computed from the source data, he decides — and
he may refuse to decide until the supporting facts are measured.

Asked where the `Bagged` packaging type belonged, he did not pick:

> «اريد فحص اكتر هل هناك فرق فى السعر ام لا … وكمان اريد دراسة وضع السعر الى اكتر
> من ٣٠ طن فى price trade … اريد دراسة الامرين»

**Apply:** offer options with the *measured* consequence of each. Answer a study
with counts from live data. Build everything that does not depend on the open
ruling, and leave the undecided fact flowing through the unrecognised-code path
so the question stays visible instead of being absorbed by a default. This is the
standing `ASK` rule in `scrapex/vocab.py`.

---

### R-03 · `Bagged` packaging is filed under **Store**
**2026-07-30 · data model · decided by R-02's studies**

Both studies came in first, and they are what decided it: the corporate site
publishes the same CEM II cement as available in bags *and* in bulk, and
packaging carries **no price signal at all** in that source. So packaging is how
the store supplies the goods, not a property of them — his own
Specifications / More-information / Store boundary, applied to evidence.

---

### R-04 · All ten web-only settings move into the extension
**2026-08-01 · scope**

Offered three options — move Excel and Sheets only, record an explicit exemption,
or move them all — he chose to move them all. He did **not** take the storage
exemption offered, so `backup_folder` moves too. Only `runtime-restart` and
`runtime-upgrade` stay exempt.

The ten: `excel_folder`, `excel_workbook`, `excel_schema`, `excel_structure`,
`excel_update`, `funnel_url`, `funnel_token`, `google_folder`, `google_workbook`,
`backup_folder` — saved from `templates/excel.html`, `templates/sync.html` and
`templates/_storage.html`, each POSTing `/api/settings`.

**Why:** his standing rule SR-10 says every setting lives in the extension, and
it was true for exactly one page. The guard read `templates/settings.html` and
nothing else, so ten settings sat outside a rule that looked enforced.

**Apply:** the guard is the deliverable, not just the move — it must read **every**
template under `scrapex/webui/templates/`, keeping the named runtime-repair
exemption. The web page must keep **displaying** every value it stops editing
(SR-10's second half).

---

### R-08 · The plan and the state live in the repository
**2026-08-15 · process · generalised by [R-09](#r-09--one-documentation-system-in-the-repository-all-english)**

The owner works from two machines. A plan on one of them does not exist on the
other. `docs/MIGRATION-PLAN.md` was moved out of `~/.claude/plans/` on this
ruling, and `docs/HANDOFF-resume-the-migration.md` was created as its living
state.

---

### R-09 · One documentation system, in the repository, all English
**2026-08-17 · process · generalises R-08**

> «اريد نظام موحد للمعلومات حيث اننى اعمل من جهازين مختلفين الصبح فى العمل والليل
> فى البيت» · «واجعله كله بالانجلليزى» · «وضيف فيه كل الخبرات التى اكتسبتها اثناء
> عملك على المشروع» · «وضع شرط انه يتطور مع الوقت وان لا تطوير يحدث فى الكود دون
> الرجوع اليه واى تغير منى يتم توثيقه حتى لو اختلف راى فراى ديناميكى يعدل ويطور
> مع الوقت»

**What forced it:** R-08 moved one plan and stopped there. On 2026-08-17 he opened
the second machine — a **different user account** — and could not continue. Two
things were true at once: thirteen memory files and seven plans lived under one
account's home directory, and the repository held no `CLAUDE.md` at all, so a
fresh session there had no pointer to the good documents that *were* committed.

**The system:** `CLAUDE.md` → `docs/STATE.md` → `docs/RULINGS.md` →
`docs/LESSONS.md` → `docs/plans/`. Its five governing rules are **C1–C5** in
[../CLAUDE.md](../CLAUDE.md).

---

### R-10 · The contractor directory — three rulings
**2026-08-16 · muqawil.org source**

1. **A muqawil-specific parser first**, generalised to a card detector later.
2. **`LISTING_ONLY` first**, then widen to profiles.
3. **The missing bilingual toggle belongs to the paused B1 work**, not to this
   source: «اشياء كثيرة مفقودة لذلك توقفت عند b1 … ومنها ايضا هذه المشكلة».

Recorded in [plans/2026-08-26-what-remains-of-muqawil.md](plans/2026-08-26-what-remains-of-muqawil.md) (the 2026-08-16 build plan it replaced was folded 2026-08-27 — `git show d6f4967:docs/plans/2026-08-16-muqawil-contractor-source.md`).

---

### R-11 · A contractor directory is a separate table, and a table like any other
**2026-08-17 · data model**

Two statements, given at different moments, that together shaped PR #211:

> «جدول منفصل تماما عن جداول المنتجات» — a table entirely separate from the
> product tables.

> «صفحة المقاولين هى جدول سيظهر كاى جدول لدينا» — the contractors page is a table
> that will appear like any of our tables.

**Separate in storage, identical as a surface.** That framing is what made the
work small: `grid.js` never asks where a payload came from, so
`dataset_table_payload` fills the same keys from `generic_record` that
`reports.table_payload` fills from `price_observation`, and not one line of the
page changed.

---

### R-12 · One row, with a button that flips it
**2026-08-17 · UI**

> «فى النهاية اريد رؤوية جدول اقدر ابدل بين عربى وانجليزى»

The Arabic and English halves land in **one** row, merged **by contractor id,
never by position** — the listing reorders every thirty seconds (measured: 4,556
of 11,059 contractors appeared on more than one page in a single pass), so
zipping two pages row-by-row would attach one company's Arabic name to another's
English one and look perfectly reasonable on screen.

---

### R-13 · Sign out of all accounts must really sign out all of them
**2026-08-16 · extension**

`Sign out of all accounts` pressed the top `#signout`, which revokes only the
current account's grant; every other account kept the standing Google grant that
makes a silent mint succeed. The ruling: a real sign-out — mint a token for each
other account silently (`login_hint` + `prompt=none`), revoke **that** token, and
press `#signout` last, because signing out the current account clears
`state.token`.

**The lockout it would otherwise have been:** the panel holds exactly one token
and it belongs to the *current* account. Handing `state.token` to `revokeToken`
ends the wrong grant — press Sign out on somebody else's row and be signed out of
your own. Guarded by `tests/test_signing_out_really_signs_out.py`.

---

### R-14 · Requests are captured when made, then planned, then executed
**2026-08-17 · process**

> «كل طلب او اضافة او اى شى اذكره ونقرر انه فى المستقبل نحطه … علشان مننساش، ولما
> نوصله نعمله خطه ونفذها» · «عاوز ادارة لطلباتى بحيث توثق وتحفظ ومنها نعمل خطة
> ومنها ننفذ الخطة»

Every request goes into [REQUESTS.md](REQUESTS.md) as `REQ-nn` in the session it
is made, quoted in his own words, and moves **Captured → Ruled → Planned → In
flight → Done**. Done and dropped requests are kept, never deleted.

**Why, with the evidence:** [R-04](#r-04--all-ten-web-only-settings-move-into-the-extension)
was ruled on 2026-08-01, after he was offered three options and chose the most
thorough. Sixteen days later nothing had been built and it had dropped out of
sight entirely — it survived only because a memory file happened to mention SR-10.

**He asked whether `CHECKLIST` was the right name, and it was not.** A checklist is
ticked and discarded: no state, no evidence, no history. What he described is a
five-state pipeline. `REQUESTS.md` was recommended and adopted; `ROADMAP` was
rejected for promising an order he has not set.

**And the boundary rule that came with it**, because building it exposed a
duplication: **he asked → `REQUESTS.md`; we found it → `BACKLOG.md`; a decision
was taken → `RULINGS.md`.** See
[REQ-09](REQUESTS.md#req-09--one-home-for-rulings-not-two) — this file was written
without reading `BACKLOG.md`, which had held 23 standing rules since 2026-07-29.
**He ruled on that on 2026-08-19:** the `SR-` rules moved here
([R-16](#r-16--one-home-for-rulings-and-it-is-this-file)).

---

### R-15 · The documents are guarded by a test, not by good intentions

**2026-08-19 · active · [REQ-08](REQUESTS.md#req-08--a-guard-against-the-documents-going-stale)**

> «نفذ توصيتك فى REQ-08 و REQ-09» — *carry out your recommendation on REQ-08 and
> REQ-09.*

He was offered three options and took the recommendation: **(b)** — a test that
every `file:line` citation in the system's documents still points at the symbol
quoted beside it. Not (a), which would have made the prose machine-generated, and
not (c), which was **C2** and good intentions.

**What decided it was not an argument, it was three failures.** Re-reading
`STATE.md` two days after it was written found the `"latest_extension_version"`
citation in `scrapex/webui/app.py` still pointing at line 1355 when the code had
moved to 1375 — #211 and #212 inserted twenty lines above it — and
`LATEST_SOURCE`/`UPDATE_INSTRUCTIONS` cited at lines 289 and 292 when they had
been at 282 and 285 all along, in a file no commit had touched. A citation that
silently moves is worse than no citation: it sends the next session to the wrong
line with full confidence.

**The scope is the map in [../CLAUDE.md](../CLAUDE.md), and the exclusion is
deliberate.** The guard reads the documents C1 tells every session to read.
`docs/plans/` is **excluded**: those are verbatim historical records, and
[plans/README.md](plans/README.md) says nothing in them was rewritten, *"because a
plan edited after the fact stops being evidence of what was decided when"*. A plan
from 2026-07-20 citing `reports.py:176` described that day's code correctly.
Forcing it to match today's would be falsifying a record to make a test pass.

Enforced by `tests/test_the_documents_cite_what_they_claim.py`.

### R-16 · One home for rulings, and it is this file

**2026-08-19 · active · [REQ-09](REQUESTS.md#req-09--one-home-for-rulings-not-two)**

Recommendation **(a)**, taken: `SR-1`–`SR-23` move out of `BACKLOG.md` §1 and into
this file, each keeping its number. `BACKLOG.md` §1 becomes a pointer, and that file
keeps what it is genuinely best at — `OP-`, `DEC-`, `BV-`, `DEBT-`, `Q-`.

**The defect was mine, and it is recorded rather than quietly repaired.** This file
was written on 2026-08-17 without reading `BACKLOG.md`, which had held 23 standing
rules since 2026-07-29 and called itself *"the one tracking document"*. His rulings
then lived in two registers — barely overlapping in content, completely overlapping
in kind. That is the same defect the migration plan warns about at B2 step 2: *"do
not write a second one."*

Option (b) — folding `R-01`–`R-14` back into BACKLOG.md — was rejected because
**C1** requires every session to read the rulings before designing anything, and a
1,151-line document does not get read before every design decision. Option (c), a
documented split by subject, was rejected because a boundary nobody can state in
one sentence will not hold.

---

### R-17 · A fix is adversarially reviewed before it is written
**2026-08-20 · process**

> «مراجعة عدائية اولا على 3 اصلاحات»

Three drifts had been reported and he asked for them to be **attacked** before
being written — not checked, refuted. Then «نفذ».

**It earned its keep on the first pass, against the reviewer's own findings:**

| the review did | to what |
|---|---|
| **refuted one** | "`RULINGS.md` says 58 commits and the truth is 64" — the line reads *"(As of 2026-08-17 the gap is 58 commits.)"*. Dated, therefore history. The finding was withdrawn |
| **widened another** | "16 days" had a second copy in `STATE.md` and a third spelled out as "sixteen days ago" |
| **replaced the remedy** | fixing `STATE.md`'s "#215 in flight" was a symptom; #215 had merged eighteen hours *before* the PR carrying that sentence, so the sentence reached `main` already false |
| **found three the fixes had missed** | the board has no generator, so it must drift; `REQ-05` read `Done` while O-1..O-4 stayed open; and the pipeline's *"may not skip one"* was obeyed by **no entry at all** |

**And it works against an implementation too, which is the part worth keeping.**
The rule that came out of the review — *no elapsed durations* — was then written
over the registers' free prose, run, and **withdrawn**: it flagged twelve lines and
essentially every one was honest history ("no one noticed for eleven days",
"Sixteen days later nothing had been built"). A closed past interval does not rot;
an open count against today does; no regex over prose separates them. The rule
now lives on the parsed state fields, where it is exact. See
[LESSONS.md](LESSONS.md) and [REQ-10](REQUESTS.md#req-10--adversarially-review-the-fixes-then-execute).

**How to apply.** Attack each proposed fix on three questions before writing it:
*is the finding even true*, *is the scope right in both directions*, and *does the
fix address the cause or the symptom*. [APPROACHES.md](APPROACHES.md) **A5** is the
method; this ruling makes it the default for a fix rather than an option, and the
limit is stated there too — a review by the same author who proposed the fix is
weaker than independent critics, and finding five things is evidence it worked, not
proof it was enough.

---

## Standing rules — the data, product and process policy (`SR-1`–`SR-23`)

**Migrated here from [BACKLOG.md](BACKLOG.md) §1 on 2026-08-19, on the owner's
ruling ([R-16](#r-16--one-home-for-rulings-and-it-is-this-file)).** Every number is
unchanged: `SR-7` is still `SR-7` everywhere it is cited. The table is moved
**verbatim** — not one of his words was rewritten in the move, because a ruling
paraphrased is a ruling weakened.

They stay `SR-` rather than becoming `R-` for the same reason: an ID cited across
eleven documents and two test suites is renumbered only by someone who wants to
break every citation at once. **Two prefixes, one home** — and the home is the file
**C1** sends every session to read.

`SR-` rules are his settled *policy*: what may be collected, what may never be
edited, how a price behaves, how work is committed. `R-` rules are the *decisions*
he has taken, dated, each with the evidence that produced it. Re-proposing an `SR-`
rule wastes a session.

| ID | Rule | Why | Evidence |
|---|---|---|---|
| **SR-1** | **Source truth is never edited.** What the site publishes is the record, typos included. Rules decide *where* a fact is shown, never *what* it says. | A cleaning rule silently forks the warehouse from the source; the next crawl can no longer tell "the shop fixed it" from "our rule stopped firing". | Owner 2026-07-28: «مصدر الحقيقة هو ما ينشره الموقع حتى لو كان فيه خطأ بشرى… القواعد فقط لمعلومة تُعرض أين، ولكن لا لتغييرها» — *the source of truth is what the site publishes even if it contains a human error; rules only decide where a fact is shown, never change it.* memory `source-truth-never-edited.md` |
| **SR-2** | **Bilingual capture.** Anything a site publishes in AR *and* EN is captured in both — names, category levels, attribute labels *and* values, descriptions, units. A missing translation the site does publish is a **defect**, not a nicety. | The owner reads and reports in both languages and refuses to re-extract to see the other one. | Owner 2026-07-23: «أى محتوى أجيبه من أى موقع متوفر باللغة الإنجليزية والعربية أريد أن أجيبه باللغتين» — *any content available in both English and Arabic, I want in both.* memory `bilingual-capture-rule.md` |
| **SR-3** | **A price is never converted.** A converted number is never shown without the rate that produced it *and* that rate's date. Google Finance is the rate authority. | The one time this was broken it put 3,312 figures in the warehouse that no page had ever printed. | Owner 2026-07-26; `scrapex/config.py:74`, `scrapex/rates.py:5`, `grid.js:1382` |
| **SR-4** | **Authority first, then recency, for exchange rates.** A rate *provider* always outranks a shop's own published rate; among providers the newest wins. A shop's rate is still used where no provider published one. | advancedcastle publishes a SAR/EGP ratio of 13.46 while pricing its own Egyptian pages at 11.768. On recency alone that number would have converted every EGP-priced row in the warehouse. | `69e986c`, migration `0054` |
| **SR-5** | **Retention never deletes a price observation.** Space is reclaimed by *building* a new database and switching a pointer; the predecessor is sealed beside it and never removed. The UI may never say "recovered space" (a test fails if that phrase appears). | Observations can never be re-observed. | memory `scrapex-phase5-integrations.md`; append-only enforced by SQLite triggers (ENGINEERING A7) |
| **SR-6** | **An unchanged price is confirmed, not appended.** History is a timeline of real changes. Availability and stock have no history at all — latest state only. | A year of unchanged diesel used to be 52 identical "history" rows. | memory `scrapex-price-semantics.md` |
| **SR-7** | **Development beats crawling.** A migration blocked by a running crawl → pause the crawl (never cancel), back up, apply via `init-db`, restart, resume. Do not ask again. | A crawl is repeatable and resumable; a half-applied change is not. | Owner 2026-07-29: «وقف الزحفة … التطوير اهم من الزحف» — *stop the crawl; development matters more than crawling.* memory `development-beats-crawling.md` |
| **SR-8** | **robots.txt: `Crawl-delay` honoured automatically; `Disallow` NEVER enforced and never a warning** — one info-level job-log line only where a disallowed path intersects one we crawl. | The owner wants uninterrupted crawling, but wants a future block to have a traceable cause. | Owner 2026-07-22, `docs/robots-policy.md` |
| **SR-9** | **Silence is never permission to go faster.** Absent config reads as *honour the delay* at every layer. Turning it off announces the number it is overriding. | A crawler that outpaces a site by default gets its owner blocked without him choosing it. | `c63ec21` |
| **SR-10** | **Every setting lives in the extension; the web page is display-only** — but display-only is not blank: the page must still show every value it stopped editing. | A setting that exists only on the web page is a setting the owner does not have — proven: crawl pace was built, plumbed to `HttpFetcher`, and he asked for it as if it did not exist. | Owner 2026-07-29: «لا اريد اى اعدادت على صفحة الويب الاعدادت كلها على extension بينما صفحة الويب للعرض فقط». Enforced by `tests/test_settings_live_in_the_extension.py` (`2253308`), not by memory |
| **SR-11** | **Delete is two actions, never one.** *Stop tracking* keeps every row ever collected; *Erase collected data* keeps the registration. Both confirmed by typing, not by an OK. | Removing an entry is not a claim that none of the data happened. | Owner 2026-07-28, `412785b` |
| **SR-12** | **A rename moves the data with the name** — all nine tables in ONE transaction, manifest rewritten only after the rows have moved. | Renaming the manifest alone would not rename a source, it would orphan one. | `412785b`, `scrapex/sources_admin.py:11` |
| **SR-13** | **Nothing is collected that is not DECLARED.** A declaration is an extraction contract with a scope guard that rejects out-of-contract rows — and since [R-78](#r-78--the-scheduler-reads-the-registry-not-a-file-and-a-new-source-needs-no-new-code) the declaration lives in `source_site`, not in `sources.yaml`. **The principle is unchanged and the file was never the point**: his words are «له أساس ليس جمعاً عشوائياً», which is a rule about basis, not about YAML. | Owner principle: «له أساس ليس جمعاً عشوائياً» — *it has a basis, it is not random collection.* | `sources.yaml:1-18` |
| **SR-14** | **GPP: the latest published price only, never their paid historical series.** Our history accumulates from our own weekly observations. | A licence obligation, and it is tested (ENGINEERING T6). | `sources.yaml:436`, memory `scraper-ecosystem-design.md` |
| **SR-15** | **Names state their language: unmarked = English, `_ar` = Arabic; the key and the label are the same word.** A monolingual Arabic source fills `product_name_ar` and leaves `product_name` **empty** — never "helpfully" carry Arabic into the unmarked column. | The reader had to learn a private vocabulary to use his own spreadsheet. | `docs/column-vocabulary.md`, migrations `0038`–`0042`, `PAYLOAD_VERSION 2` |
| **SR-16** | **Column presence is per source.** Every gate in `reports.column_presence` asks *this* source's own rows, never a global table. | A global `currency_rate` count once put fuel-implied USD estimates on every shop. | memory `scrapex-columns-classification.md` |
| **SR-17** | **Detail groups are a closed vocabulary of seven, and a code the map has never seen goes to the owner before it gets a group.** | A silently widened catch-all misinforms every later reader. | Owner 2026-07-28, migration `0046`, `scrapex/vocab.py` `_DETAIL_GROUP_BY_CODE` |
| **SR-18** | **Commit and push after each plan step; do not batch, and do not end a step asking "shall I continue?".** | The owner works across parallel sessions and worktrees; unpushed commits are invisible to them — that is how a duplicate `0012` migration happened. | Owner, repeated. memory `commit-and-push-each-step.md` |
| **SR-19** | **Never `git add .` or stage a path list — read the whole cached diff before committing.** | Twice this swept another session's half-finished work into a commit and broke `main` from a clean checkout. | `e2573e1` ("I staged that file after reading only `--stat`. Reading the whole cached diff is the rule that would have caught it, and it is the rule I agreed to"), `0a2209c` |
| **SR-20** | **Commit messages carry no double-quote characters** (PowerShell here-strings break on them). | Mechanical, but it costs a retry every time. | memory `git-commit-heredoc-quotes.md` |
| **SR-21** | **Every worker other than me produces drafts.** `codex/*` branches and other sessions are pull requests awaiting review with `file:line` evidence, never work to build on. | The owner said plainly he does not trust anyone else in the code; the arrangement only survives because the audits catch things (17 real defects past 527 green tests). | memory `scrapex-review-gate.md` |
| **SR-22** | **Build, don't stop to review** — write code that already satisfies the review rules; pause only for genuinely forking product decisions. | Owner 2026-07-16: «انا مش عاوز اراجع حاجة دلوقتى انا عاوز ابنى ولكن بكود يحترم المراجعة» — *I don't want to review anything now, I want to build, but with code that respects the review.* | memory `build-not-review-bake-rules-in.md`, `ENGINEERING.md` |
| **SR-23** | **CI must be green on every push.** `.github/workflows/ci.yml` runs on `push` and `pull_request`: manifest validation, a floor of ≥40 collected panel tests, the full pytest suite, the JS↔Python contract-parity gate, and the extension `node:test` suite. | A guard that can vanish quietly is the defect — the panel suite silently skipped for months. | `.github/workflows/ci.yml`, `48ec48b`. *(The "must be green" phrasing is the observed convention across every commit message, which reports the suite total — **inferred** as a rule, not stated by the owner in those words.)* |

---

### R-37 · The agent does not merge. The main programmer does

**2026-08-21 · process · ~~active~~ SUPERSEDED the same day by [R-42](#r-42--one-primary-session-merges-every-other-session-is-secondary-and-asks)**

> **Kept in full because its DIAGNOSIS is what R-42 is built on.** Merge order
> across parallel sessions really is invisible to a single session. What R-42
> changes is the remedy: name the one session that can see it, rather than
> blinding all of them. Everything below about what a report must say still
> governs a SECONDARY session.

**supersedes [R-18](#r-18--merge-it-when-it-is-green)**

> «واترك الدمج للمبرمج الرئيسيى»

**Said in the same message that authorised two fixes**, which is what makes it a
process rule rather than an instruction about one pull request: he asked for
`OP-36` and `OP-35` to be built and pushed to one tree, and for the merge to stay
with him. A session that read that as "this once" would be back to guessing next
time, which is the ambiguity `R-18` itself was written to end.

**WHAT CHANGED FROM `R-18`, AND WHY IT IS NOT A REVERSAL.** `R-18` was given on
2026-08-20 while four ready pull requests sat waiting for a separate instruction
each, and it fixed a real cost — a merge-ready branch idling for a day. Between
then and now the reason for the delegation weakened and the reason against it grew:

| | |
|---|---|
| **`main` still has no branch protection** — 404 on the protection endpoint | Under `R-18` the agent's judgement was the *entire* gate. Under this ruling a person is |
| **Several sessions now run at once** | On 2026-08-21 `#243` merged while this branch was open, took `OP-30`/`OP-31`, and closed two findings out from under it. Merge order across parallel sessions is not a thing any single session can see |
| **`ac3a5af` reached `main` with no pull request** and left it red for two days | Recorded in `STATE.md`. The cost of one bad merge here is measured in days, not minutes |

**How to apply.** Build it, push it, wait for the checks to conclude, and then
**report** — naming every check, every failure, and whether each failure ran at
all. Then stop. Do not merge, do not squash, do not close a pull request as
superseded. `R-18`'s reading of *green* still governs the report: a `SKIPPED`
required check is not satisfied, an absent run is not a red one, and a tick from
before the last push describes a tree nobody is merging.

**This does not make a red branch acceptable.** The obligation to arrive green is
unchanged (`R-22` still requires the full suite before a pull request opens); what
moves is only the last step.

---

### R-18 · Merge it when it is green

**2026-08-20 · process · ~~active~~ SUPERSEDED 2026-08-21 by [R-37](#r-37--the-agent-does-not-merge-the-main-programmer-does)**

> **Kept in full because the three traps below did not go away.** What `R-37`
> removes is *who presses the button*, not one word of what green means. A
> session must still establish that every check concluded, that a failure ran
> at all, and that the tick describes the tree in front of it — and then say
> so and stop. Everything under "How to apply" is now the report, not the
> action.

> «ادمج لما يخضر»

Said while four pull requests sat waiting on checks that had only just started
working again. It ends a standing ambiguity: before this, green was reported to him
and each merge waited for a separate instruction, which meant a ready pull request
could sit for a day for no reason anyone could name.

**Green means the checks that ran, not the checks that exist.** Three things had to
be settled before this ruling could be safely obeyed, and all three are why it is
written down rather than assumed:

| trap | what it means for this rule |
|---|---|
| **`main` has no branch protection at all** — `gh api .../branches/main/protection` answers 404 | Nothing mechanical stops a red merge. This ruling is the whole gate, so it has to be read literally |
| **A run that never started reports failure** | The 2026-08-19 outage failed every job with *"the job was not started because recent account payments have failed"* and no step executed. That is not red, it is absent — read the annotation before believing a failure |
| **A green tick can belong to a different tree** | #217's `pull_request` run passed while its `push` run failed on the same commit: the merge ref carried `main`'s revert, the branch alone did not. A tick from before the last rebase is evidence about a tree nobody is merging |

**How to apply.** When every check on a pull request has *concluded* and every
conclusion is success, merge it — squash, and no further instruction needed. Do not
merge while anything is `IN_PROGRESS`, `SKIPPED` or `QUEUED`; a skipped required
check reads as satisfied, which is the silent-skip failure this repository has now
recorded three times. If a check is red, establish whether it ran at all before
touching the code. And if the branch has been rebased since the tick, wait for the
new run — the old one described a tree that no longer exists.

This does not override the ordering a stack imposes: a pull request whose premise is
another's still waits for it, green or not.

---

### R-19 · The five multi-valued contractor groups go in CHILD TABLES, not JSON

**2026-08-20 · data model · answers [O-1](#open--awaiting-the-owners-ruling)**

> «جداول أبناء للخمس كلّها»

Interests, Licensed Activities, Qualification Programs, Balady Services and the
contractor relations each get a real child table. Not a JSON blob inside
`data_json`.

**AND THIS OVERRULES THE DESIGN DOCUMENT, which is why it is written here rather
than quietly applied.** [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) states flatly
that the five hierarchical groups go in JSON inside `data_json`. He was offered
that, with JSON as the recommendation, and chose child tables. The document is
corrected in the same pull request as this ruling — **C2** — and its previous
position is left visible rather than deleted, per **C4**.

**HE ASKED WHETHER HIS OWN DECISION WAS WRONG — «ربما يكون قرار خاطى» — so it was
measured rather than deferred to, and the measurement supports him.**

One real profile was fetched and parsed (شركة عبر المملكة سبك, membership 10001274,
the contractor whose absence from the warehouse started this):

| group | what the page actually holds |
|---|---|
| Interests / activities | **30 values across 6 groups, and they are HIERARCHICAL** — a parent category with children: building construction 6, roads 4, electrical 5, lifts 5, landscaping 7, sewage 3 |
| Licensed activities | a table with **one row — the header only.** Empty for this contractor |
| Main / sub contractors | two tables, **one row each.** Empty, which agrees with the card counts: `0` for 11,057 of 11,059 records |

**So the arithmetic is roughly 30 hierarchical values x 17,283 contractors — about
half a million rows.** In an indexed child table that is nothing for SQLite and it
answers *"which contractors operate sewage networks"* instantly. As JSON it stores
just as easily but the same question means scanning eleven thousand blobs.

**AND THE ARGUMENT MADE FOR JSON DID NOT ACTUALLY DISTINGUISH THE TWO.** The
recommendation leaned on the grid being one flat table — but the grid cannot render
a nested JSON array either. Both shapes need new payload work; only one of them
also gives the query. The design picked JSON before anyone had counted those thirty
values.

**The limit of this evidence, stated plainly: one contractor.** Generalising needs a
handful more profiles, which the crawl study will produce. But the direction is
unambiguous and nothing in it favours JSON.

> **MEASURED 2026-08-21, at his instruction to test this ruling before building it.**
> [R19-CHILD-TABLES-MEASURED.md](R19-CHILD-TABLES-MEASURED.md) puts 5 shapes against
> 11 criteria at 518,490 rows. **This ruling is upheld and by a wider margin than it
> claimed** — JSON costs 1,168 ms on the query named above against 0.6 ms for the
> best shape.
>
> Two corrections to the evidence above, kept visible per **C4**: the
> licensed-activities table is **not** generally empty — the committed fixture for a
> different contractor has **six rows**, so "empty for this contractor" was exactly
> that. And the value is not a flat string but a **two-level bilingual path** whose
> parent repeats three times inside one contractor's six activities.
>
> The study proposes a refinement of *how* — child **datasets** referencing
> `classification_node` rather than five bespoke tables — which is **his to rule on**,
> recorded as `Q-13`. Nothing has been built.

> **MEASURED AGAIN 2026-08-22, over 2,419 real profile pairs instead of one profile,
> and this is the reading that lifts the evidence limit stated above.** He warned that
> the pages differ — «المعلومات غير ثابته ولا متفقثة بين الصفح» — and he was right. The
> original text and the 2026-08-21 correction both stay, per **C4**; what follows
> replaces neither. It finally counts them.
>
> | group | pages | rows | verdict |
> |---|---|---|---|
> | Interests | 2,419 of 2,419 | 211 English paths, 214 Arabic | a taxonomy — **built** |
> | Licensed activities | 2,419, rows on 228 | 1,685 rows, **22 distinct activities** | a taxonomy — **built 2026-08-22** |
> | Main contractors | 2,419 carry the table | rows on **0** | declared, not built |
> | Sub contractors | 2,419 carry the table | rows on **2** | declared, not built |
> | Contract counts | 92 | one row of two numbers | **two columns**, not a group |
>
> **THREE THINGS THIS RULING NAMES ARE NOT ON THE PROFILE PAGE AT ALL,** and the
> measurement is now large enough to say so rather than suspect it. `Balady Services`
> appears on **0 of 2,419** pages. `Qualification Programs` appears on 2,419 of 2,419
> — **in the site's navigation JSON-LD**, not as a section of any contractor, which is
> exactly the false positive a marker test produces when the marker lives in the
> 119 KB of page chrome. And the **technical rating** is not a table at all:
> `contractor-tab4` holds zero tables in its DOM subtree on 2,360 of 2,360 pages. The
> tab button is a label over an empty pane.
>
> **AND THE FIFTH TABLE IS A PRICE, which no document here had named.** The card titled
> `العقود سعر البناء (برنامج البناء الذاتي)` publishes a **self-build price per square
> metre** in three award tiers — 713 of 2,419 pages carry the card and 163 carry
> values, all numeric. In a price-tracking warehouse that is the most valuable thing on
> the page, and it was invisible because a regex had attributed it to the empty tab.
> See [LESSONS.md](LESSONS.md) §11.
>
> **What is left for him** is narrower than five groups: `Q-17` — the readiness level,
> and the three activities whose English the site publishes wrongly — and `Q-18`, do
> the two relation groups still get tables at 2 rows in 2,419 pages.

**What it costs.** Five tables and their migration; a read path per table; and the
dataset payload has to carry them, which today it cannot. That last part is the real
work and it is not yet designed — and it would have been needed for JSON too.

**What is already true and helps.** `dataset_relationship` and
`relationship_field_pair` exist (`0013_generic_dataset_catalog.sql`, in the stream retired on 2026-08-29 — `git show 8901a2a:db⁠/migrations/0013_generic_dataset_catalog.sql`),
with a propose/list API and tests. They hold **0 rows**. So the machinery for the
relations half exists and has never had a tenant.

---

### R-20 · An unchanged contractor is confirmed, not re-recorded

**2026-08-20 · data model · answers [O-3](#open--awaiting-the-owners-ruling) and [O-4](#open--awaiting-the-owners-ruling)**

> «مراجعة عند التغير فقط»

A second crawl that finds a contractor unchanged **updates `last_seen_at` and
writes no revision**. History is kept — a revision per real change, which is what
makes "when did this classification change" answerable.

**This is `SR-6` applied to a directory instead of a price** — *"an unchanged price
is confirmed, not appended"* — and the reasoning transfers exactly: history is a
timeline of real changes, and a year of identical rows is not history.

**MEASURED, AND IT IS NOT WHAT THE CODE DOES TODAY.** `content_hash` exists on
`generic_record` and is **not consulted on ingest**: the warehouse holds **34,550
revisions for 11,059 contractors** — roughly three apiece, from two crawls of a
directory that barely changed. Under this ruling that number should have been close
to 11,059. So the ruling is a change to the write path, not a description of it.

**And it compounds with the storage question.** Every re-crawl currently grows the
revision table linearly whether anything changed or not, which is part of the
volume [DEC-9](BACKLOG.md) is arguing about. Consulting the hash is the cheapest
line in that argument.

---

### R-21 · One source owns every outbound request, and paces itself per site and per connection

**2026-08-20 · architecture**

> «التوازى يجب ان يكون مصدر واحد يدير اى استعلام او اتصال بالانترنت ويوازى على حسب
> سرعة الانترنت وسرعة الاستجابة من كل موقع… مواقع تقبل 10 طلبات ومواقع لا تقبل سوى
> طلب واحد وسرعة الانترنت تستحمل طلبان فقط»

Every outbound request goes through **one** component. It decides how many may be
in flight, adapting on two axes at once: **what each site tolerates**, learned per
host, and **what the local connection can carry**, measured.

**HALF OF THIS IS ALREADY BUILT, AND NONE OF IT IS USED.**
[scrapex/pacegovernor.py](../scrapex/pacegovernor.py) already keeps a `HostPace`
per host — *"one per host, never shared"* — carrying a `concurrency` that starts at
1 and is raised toward a ceiling of 4 only while the host stays clean. It learns
the uncontended latency at concurrency 1 and only there, and it carries the Scrapy
one-way ratchet from #210.

**But `grep` for `concurrency(` outside that file returns nothing, and the only
code that constructs a `PaceGovernor` is its own test suite.** The governor
computes a number no crawl reads.

**So the work this ruling names is not building a governor. It is three things:**

1. **Wire the existing governor into the fetch loop** — the crawl is sequential by
   construction today, so nothing consumes the learned concurrency.
2. **Add the global cap he asked for**, which does not exist: the governor is
   per-host and nothing bounds the *total* in flight by measured local bandwidth.
   Two sites at 4 each is 8 in flight on a connection that may carry 2.
3. **Make it the single owner.** Outbound requests are issued from more than one
   place today; this ruling makes that a defect.

**The measurement that justifies it**, recorded in the governor's own header from
2026-08-16 against muqawil.org: a page costs **5.84s, of which 5.69s is the server
thinking**. Compression was already on, HTTP/2 changed nothing, there is no `ETag`
— **nothing client-side touches the cost**. Four in flight took **9.5s where four
in series took 26.4s: a 2.8x gain**, every answer a 200.

**And the price, which is why the cap is per-site and adaptive rather than a
constant:** per-request latency rose from ~6.6s to ~9.2s under those four, a 40%
rise, with no 429 and no refused connection. The file's own words: *"That is a
server saying it is hurting in the only language it has"* — and a crawler that
waits for a 429 before easing off has ignored the polite warning to wait for the
rude one.


### R-22 · The full suite finishes before the pull request opens

**2026-08-20 · process**

> «لا بعد ان تنتهى» — then «حافظ على المبدا»

A pull request is opened after `python -m pytest -q` has **finished**, not while it
is running. Not at 24%, not at 48%, however clean the output looks so far.

**RECORDED BECAUSE I BROKE IT FIVE MINUTES AFTER SAYING IT MYSELF.** On this very
branch I wrote *"أفتح PR بعد أن تنتهي السويت — لا قبلها هذه المرّة"* and then opened
#227 at 48%. He corrected it, and let that one stand — «طالما فتحت خلاص هذه المرة» —
which is exactly why the rule goes in a file rather than in my intention. A practice
I could not keep for five minutes is not a practice.

**And it is not fussiness. It failed three times in one day:**

| | |
|---|---|
| #221 | opened on `tests/test_features.py` alone, six green. The full suite found **four** other things asserting on the feature manifest |
| #217 | the panel suite was run without the guard that watches the *shape* of the suite — the extension gate caught a missing mark after the PR was open |
| #216 | its own new docs gate failed on a file that had landed on `main` in #219, found only by running everything |

Each was found **after** the pull request existed, which is the expensive order: a red
PR is a claim already published.

**How to apply.** Run the suite, read its last line, then open. A slow suite is not a
reason to skip this — it is the reason **`OP-19`** is known to be a flake rather than
suspected of being one, and the reason the 2,656-test run is worth having at all. If
the wait is genuinely blocking, open it as a **draft** and mark it ready when the run
lands; that is what happened here after the fact, and it is the right shape done in
the right order.

---

### R-23 · ScrapeX is a multi-user product, so a warehouse is per installation

**2026-08-20 · architecture, and it corrects a framing of mine**

> «هو فعلا غير موجود ولكن الاداة مصممة انها تعمل لكذا مستخدم وليس لمستخدم واحد فقط
> اذا سنشغل crawl لهذا الجهاز — المقارنة ان تمت ستكون للتطوير وليس للجمع»

**The question he was answering.** The home machine has no engine database and a
pre-collapse pointer, so the 11,059 rows, the 1,728 snapshots and the sweep's
17,283-id sighting ledger existed on the work machine only. I put it to him as
[O-6](#open--awaiting-the-owners-ruling) — carry the file across, run only where the
data is, or keep two warehouses and reconcile them — and recommended the first two.

**His ruling is none of the three, because the premise was wrong.** ScrapeX is a
tool **many people install**, not one installation that happens to live on two
machines. Every user's warehouse is their own and starts empty; a machine with no
database is therefore the **normal first-run state of the product**, not a fault to
be repaired by copying a file. So: create a warehouse here and run the crawl into it.

**What this changes, and it is more than where a command runs:**

- **A coverage number is a fact about ONE installation.** "11,059 of 17,403" is not a
  project-wide truth and must never be written as one. The claim
  `docs/BACKLOG.md` DEC-11 already insists on — *"every contractor findable in the
  muqawil.org listing as of «timestamp»"* — needs *"in this installation"* beside it.
- **Comparing two machines' data is a DEVELOPMENT activity**, «للتطوير وليس للجمع».
  It can validate that the method is reproducible — two installations crawling the
  same live listing should converge on the same ids — and it is not a way of
  assembling one larger dataset.
- **`OP-22`'s framing was mine and it was wrong.** I called it "`CLAUDE.md`'s founding
  failure in the one place the repository cannot follow it". The repository rule is
  about **decisions and knowledge**, which do travel and are committed; a user's
  collected DATA was never meant to. Kept and corrected rather than deleted, per
  **C4/C5**.
- **What still travels is the code and the method.** A crawl that could only be run
  on the machine that happened to hold the data was a defect regardless — which is
  why `tools/crawl_muqawil_listing.py` had to exist either way.

**How to apply.** On an installation with no warehouse, create one — `scrapex
carry-over` where a pre-collapse pointer names old files (it opens them read-only,
verifies row counts, and rewrites the pointer only if they match), `scrapex init-db`
where there is nothing to carry. Then crawl. Do **not** copy another installation's
database in order to make a number match.

---

### R-24 · A database is UPGRADED, never replaced — the user's data survives the schema

**2026-08-20 · architecture. He is correcting something I did, and the correction is
the more important half of the ruling.**

> «انت ليه عملت قاعدة بيانات جديدة؟ فاعدة البيانات الى كانت موجودة قديمة كان ممكن
> تسال تطورها لتطابق تطوير الكود او تحذفها وتنشى واحده جديدة مطابقة لاخر نسخة من
> الكود. طبعا الافضل تطويرها لان عند نشر الاداة المفروض نحافظ على بيانات المستخدمين
> وقاعدة البيانات تتطور ويظل بياناتهم محفوظة»

**What I did.** [R-23](#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)
said to create a warehouse on this installation. `scrapex carry-over` refused —
[OP-23](BACKLOG.md) — so I set `SCRAPEX_DATA_ROOT` to a second location, ran
`init-db`, and crawled into that. His 3,739 price observations stayed behind a
pointer nothing opens, with an empty database beside them.

**`registry.py` says not to do that, in words, and I had quoted those words an hour
earlier:** *"NOT `init-db`… On an installation with data in them it produces an empty
warehouse beside a full one that nothing will open again."* A different data root
does not change the outcome; it only moves where the empty file sits.

**The ruling.** Two options existed — upgrade the old database so it matches the
code, or delete it and create a new one — and **upgrading is the one that ships**:
when the tool is published, a user's data must survive the schema evolving. That
makes the migration path a **product feature**, not maintenance. Concretely:

- **A carry-over or migration that refuses on real data is a release blocker**, not a
  backlog entry to route around. Routing around it is how it stays broken, because
  the only installations that exercise it are real ones.
- **Never create a second warehouse to get past a failing upgrade.** Fix the upgrade.
  If it truly cannot be fixed in the moment, stop and say so rather than leaving two
  databases and choosing the empty one.
- **`init-db` is for an installation with nothing to lose.** Everywhere else it is the
  trap `registry.py` names.
- **A value the upgrade supplies is reported**, and is reused from the migration that
  introduced the column rather than invented (see `Backfill` in
  `scrapex/databases/carry_over.py`). Inventing one would put a fact in the user's
  data that their source never said.

**Done under it, 2026-08-20:** `carry_over` fixed and the real installation upgraded
in place — 3,739 offers, 3,739 observations, 17,111 attributes, 7,410 change events,
**not one row short**, the 261 pre-0058 offers marked `legacy_unwitnessed`, the 3,478
without a unit untouched, and the old files still where they were, read-only.
Guarded by `tests/test_a_carry_over_upgrades_rather_than_starting_over.py`, six
mutations killed.

---

### R-25 · The crawl method is settled first; the schema and retention questions come last

**2026-08-21 · sequencing, and it decides what several open questions are waiting for**

> «صعب حسم هذا الامر الان سنتركه النهاية بعد معالجة كل مشاكل مقاول والاستقرار على
> افضل طرق ومسارت عمل crawl الخاصة به»

**What he was asked.** Two decisions were put to him together: which route
[OP-25](BACKLOG.md) should take (the parser's schema had refused 823 of 897 pages),
and `STORAGE.md` §5 — is a snapshot evidence or only a parse cache. He declined to
settle either **now**, and gave the order instead: finish muqawil's problems and
settle **the best methods and work-paths for its crawl**, then decide these.

**And the sequencing is right for a reason worth writing down.** Both deferred
questions are about **interpreting** stored pages; neither changes what is on disk.
`docs/GENERIC-FETCH-SEAM.md`'s central rule is that one page in gives one snapshot
out, unparsed, so interpretation can be re-run against the evidence at any time. That
was demonstrated twice on 2026-08-21: the 897 stored page-pairs were re-interpreted
**from disk, twice, with not one network request** — a wrong schema cost 20 minutes
where a re-crawl is two hours. So deferring an interpretation decision costs nothing,
while deferring a **collection** decision costs a re-crawl. Collection first is the
cheaper order, not merely the one he chose.

**How to apply.** Until he settles them:

- **Do not force either question to be answered by a default.** OP-25's three routes
  and §5's two readings stay open and stay written down.
- **Coverage stays at whatever the current schema admits** — 1,172 records tonight —
  and that number must be reported as *"limited by an unresolved schema decision"*
  rather than as the crawl's coverage. The crawl's own result is the **13,727 sighted
  ids and 1,982 stored pages**, which is complete and independent of it.
- **Work the crawl:** the 3,690 deficit, the counting proof, the `city_id`
  subdivision, per-cell re-sizing. That is what "أفضل طرق ومسارات عمل crawl" names.
- Anything needed by **all** routes may still be built — the `CARD_FIELDS`
  declaration is, because none of the three routes works without it.

---

### R-26 · The residual crawl runs in the background while development continues, and must be stoppable

**2026-08-21 · process, and it settles a cost question I had put to him**

> «لا مشكلة من تشغيل الزحف فى الخلفية أثناء التطوير وكلما يعود بنتيجة نفحصها ونطور
> اكتر المهم يكون قابل للايقاف والاستكمال»

I priced closing the 3,690 deficit at **~8,000 requests and about 5.5 hours** and put
it to him as a cost decision — close it all, or only the cheap part. He declined the
framing: **run it in the background while development continues**, examine each result
as it comes back, and keep improving. The condition is the whole ruling: **stoppable
and resumable.**

**What that requires, and it is not automatic:**

- **Stoppable at any moment without losing what it read.** `snapshotcrawl` commits
  every page as it arrives and `crawl_partition` writes sightings per attempt, so a
  killed crawl keeps every page and every id it saw. That much is already true and was
  demonstrated on 2026-08-20, when a crawl stopped after six cells kept all six.
- **Resumable without paying for what is on disk.** The same `--run-ref` again skips
  the pages that ref already stored and reads their ids back off the evidence rather
  than off the wire. **Sizing is NOT resumable** — a resumed run re-pays ~112 requests,
  about 5.7% of a full pass. That is stated rather than hidden, and `--plan` exists so
  it can be paid deliberately.
- **Restartable in pieces**, which is what makes "examine each result and improve"
  possible at all: a crawl that can only run all 56 cells re-reads 47 proven ones to
  reach the 9 that are not. The residual has to be addressable on its own.

**How to apply.** A long crawl is started detached, never inside a tool call that can
time out — the 10-minute limit killed one already, and the fix is `Start-Process` with
its output redirected to a log, not a shorter crawl. Report what it found when it
returns; do not wait on it.

Kept per **C4**. Do not follow these; they are here so the current rule can be
understood.

### R-36 · The engine updates itself; the panel only asks. And a published SHA-256 over HTTPS is enough to trust a download

**2026-08-21 · install & update · answers `REQ-29`, and supersedes nothing**

> «اوافق على اقتراحاتك وتوصياتك»

**WHAT HE APPROVED WAS A RECOMMENDATION, AND THE RECOMMENDATION IS RECORDED HERE
RATHER THAN IN A CONVERSATION** — because he approved it in general terms and this
file is where the specific version has to live, so he can correct any part of it.
The four parts, in the order they were put to him:

**1. The panel can never be the installer, and this is a limit rather than a
backlog item.** Measured 2026-08-21: `extension/manifest.json` grants
`activeTab, identity, nativeMessaging, sidePanel, storage, tabs` and **no
`downloads`**, so `extension/app.js:3620` is `window.open(installer.url)` — it hands
a URL to the browser and lets go. Chrome will not let an extension show download
progress it does not own, read a file off disk to hash it, or launch a process.
**No amount of UI work changes any of those three.**

**2. So the division is: first install through the browser, every update through
the engine.** The first install has no choice — nothing is installed yet. After
that the engine is a local process with a filesystem and a network stack, and it
can do the whole job: download, verify, swap, relaunch, report. The panel's role
shrinks to what it is good at — showing the state and the verdict, and asking.

**3. A `sha256` published in the release manifest, fetched over HTTPS from
`raw.githubusercontent.com`, and checked before the swap, IS enough to trust a
download.** This is the part with real consequences, so it is stated at its
narrowest. `packaging/build_engine.py` refused to guess and said so: *"shipping an
updater that fetches and executes unsigned code would be worse than none."* The
chain now available is not nothing — the manifest is written by the release
workflow from the artifact it just built, served over TLS from a host the panel
already declares, and the digest is compared to the bytes on disk before anything
is executed. **It is NOT code signing and does not replace it**: SmartScreen will
still warn on first install until a certificate exists, which only he can supply
(`Decision 22` already accepts an unsigned binary). What this ruling buys is that
an updater may exist *before* signing does.

**4. Two defects come first, because an Update button on top of them would lie.**
`OP-36` — a frozen engine cannot restart itself at all today. `OP-35` — twelve of
the CLI's twenty-four subcommands are unreachable from the shipped binary. An
updater built before those is a button that reports success and changes nothing.

**And the cheap slice was approved with it:** add the `downloads` permission and
replace `window.open` with `chrome.downloads.download()` + `show()`, so the first
install becomes a progress bar and a file handed over. It does **not** solve the
checksum — an extension cannot read a downloaded file — so the SHA-256 now on
screen either becomes the engine's job to verify after the fact, or stops being
displayed. **A number nothing checks is worse than no number.**

**If any of the four is not what he meant, this entry is the one to correct** — in
particular part 3, which is the only one with a security consequence.

### R-38 · `R-19`'s five groups are a TAXONOMY plus a link table, not five datasets — shape D

**2026-08-21 · data model · refines [R-19](#r-19--the-five-multi-valued-contractor-groups-go-in-child-tables-not-json), and overrules the study's own recommendation**

> «شكل تخزين مجموعات R-19 الخمس … أيّها؟» → **«D — تصنيف خالص + جدول ربط مخصَّص»**

`R-19` ruled child tables over JSON and every measurement upheld it. What it did not
settle was *how* — [the study](R19-CHILD-TABLES-MEASURED.md) put five shapes side by side
and recommended **F**, a child dataset per group inside `generic_record` whose value
references `classification_node`. **He chose D**: the taxonomy plus a bespoke link table.

**He is right, and the recommendation was wrong for a reason worth writing down.** F's
headline argument was that it reuses machinery the warehouse already contains. Measured
on the live warehouse the same day:

| the machinery F would be the first tenant of | rows |
|---|---|
| `classification_node` | **0** |
| `classification_scheme` | **0** |
| `dataset_relationship` | **0** |
| `relationship_field_pair` | **0** |

**Existing machinery that has never carried a row is not an asset.** This one session
proved that three times: `is_enabled` called itself *"the gate navigation must call"* and
had zero callers; `record_absences` had zero callers; and the slice scope was *"built,
tested, and never used"* and turned out to be **wrong** — 17 cards paired against 34
URLs. The recommendation weighed whether the machinery EXISTED. What matters is whether
it RUNS.

**And F pays a full record's overhead for a two-integer join row.** Measured per row of
`generic_record`: `data_json` averages **1,049 bytes**, `record_key` is a 64-character
SHA-256, `content_hash` another 64, plus two timestamps, a status and four foreign keys.
A membership fact — *this contractor holds this node* — is two integers. At the study's
~500K rows that is the measured 4.7×, and it is conservative.

**"It inherits the lifecycle" was not true either:**

    retention.py     16 references to price_observation, 0 to generic_record
    compaction.py     7 references to price_observation, 0 to generic_record

The contractor dataset has no retention today. F would have added five more datasets to
that same gap rather than inheriting a solution.

**A fourth reason, which crosses [R-40](#r-40--dec-10-is-built-before-the-profile-crawl-not-after-it):**
F routes five groups through `approve_candidate`, the function that answers
`recovered=True` and writes nothing. D writes directly, so idempotency is one constraint
— `UNIQUE (contractor, node)` — correct by construction instead of by later repair.

**WHAT D MUST NOT LOSE, and it is one line.** F's one surviving advantage was that
`generic_record.source_snapshot_id NOT NULL` makes provenance **enforced by the schema**
rather than remembered. The link table carries the same column under the same constraint.
Then D is 4.7× smaller *and* provenance is still enforced.

**What D genuinely costs:** bespoke work in the export, the API, the panel and the CLI,
because a link table is not a dataset and nothing reads it for free. Noted rather than
discounted — and `O-2`, whether the contractor entity belongs in the mbiX workbook at
all, is parked by him, so the export half of that cost is not owed yet.

---

### R-39 · muqawil is registered `listing_plus_slice`, and one city is crawled before eleven hours are spent

**2026-08-21 · crawl scope · answers the registration `PLATFORM-PLAN` Decision 23 left to him**

> «نطاق زحف مقاول مسجَّل listing_only … ماذا أُسجِّل؟» → **«listing_plus_slice لمدينة واحدة أوّلاً»**

The profile pages carry the ~28 columns the listing does not, and the full crawl is
**34,834 pages — 11.1 hours**, measured over 87 minutes of real six-worker crawling at
52.5 pages a minute. He chose to see one city first.

> **AMENDED 2026-08-22, and the figure above is kept because the correction is about
> WHAT IT WAS MEASURED ON.** 52.5 pages a minute was the **listing** crawl, at six
> workers. `--details` had no workers at all — it was one page at a time — and its own
> measured rate on the Dammam run was **9.03 s a page**, which is 6.65 pages a minute
> and **87 hours**, not 11.1. So the ruling was right about the destination and wrong
> about the vehicle: it priced a journey using another command's speed.
>
> He caught it himself — «ولاحظ أنّ R-39 يسجل 11.1 وهو رقم خاطئ». `--details` now takes
> `--workers`, which is what makes the original number reachable again: **11–14 hours**
> depending on whether profiles overlap as well as listings did. The lesson is narrower
> than "check your arithmetic": **a rate measured on one command is not a rate.**

**The city is read off the listing card, so a slice costs nothing to select.** Measured
from the live warehouse, the cities that a first slice could be:

| city | contractors | profile pages | at 1.14 s a page |
|---|---|---|---|
| RIYADH | 5,406 | 10,812 | ~3.4 h |
| JEDDAH | 2,206 | 4,412 | ~1.4 h |
| DAMMAM | 739 | 1,478 | ~28 min |
| AL MADINAH AL MUNAWWARAH | 499 | 998 | ~19 min |
| TABUK | 191 | 382 | ~7 min |

**A DEFECT THIS RULING EXPOSED BEFORE IT WAS IMPLEMENTED.** A slice is named in the
language of the page — `MuqawilPageSource.belongs_to_slice` says so — and measured
against the committed fixtures:

    en page, slice 'RIYADH'  → 3 of 4 cards match
    en page, slice 'الرياض'  → 0 of 4
    ar page, slice 'RIYADH'  → 0 of 4
    ar page, slice 'الرياض'  → 3 of 4

So a single `crawl_slice` value matches **one locale's pages only**. The frontier still
comes out correct, because `detail_rows` yields both locales' profile URLs for a matched
row — but every Arabic listing row is counted as *outside the slice*, which makes the
report a lie, and the whole slice would depend on the English pages happening to be on
disk. The frontier scan is therefore restricted to the locale the slice is named in, and
the report says which.

---

### R-40 · DEC-10 is built BEFORE the profile crawl, not after it

**2026-08-21 · idempotency · closes [DEC-10](BACKLOG.md) as a decision**

> «هل نبنيه قبل زحفة الملفّات؟» → **«نعم، قبل الزحفة»**

`approve_candidate`'s idempotency key is `(snapshot, locator)` plus the schema hash, so a
**corrected** parser re-run over stored pages returns `recovered=True` and changes not one
row. On the listing that was survivable — the pages are cheap to re-read. On 34,834
profile pages it is not: a parser defect found after the crawl costs **11 hours of
re-fetching** to fix what should be minutes of re-parsing.

**That is a direct contradiction of why the seam exists.**
`docs/GENERIC-FETCH-SEAM.md` separates fetching from interpreting precisely so that a
wrong parse costs minutes; an idempotency key that refuses to rewrite a corrected row
hands the cost straight back.

**It is also the one open item that changes the COST of the remaining work rather than
its scope**, which is why building it first is not sequencing preference. `R-38`'s link
table depends on it twice over: the five groups are parsed from the same profile pages,
and a first parse of a five-level taxonomy is unlikely to be the last.

The route already proven on live data — wipe and re-approve from disk, which took
`generic_record` from 1,172 to 13,892 with zero network on 2026-08-21 — stays available.
It works and it destroys history every time, which is what a row-aware key replaces.

---

### R-44 · No sync server and no backup encryption for now, and the sync work is deferred behind muqawil

**2026-08-22 · scope · answers the audit `R-43` made possible**

> «لن ابنى خادم الان (لا اعرف وجه الاستفادة اصلا منه)» ·
> «لا تشفر الان اصلا الداتا لن تنتقل من المستخدم الى اى حد اخر فهى تخص المستخدم فقط لا
> داعى للتشفير ربما خطة مستقبلية» ·
> «أرجئ كلّ شىء — أكمل مقاول»

He commissioned a full offline-first multi-device audit against eight requirements,
read it, and ruled on all of it in one sitting. **Four decisions, and they are recorded
together because they only make sense together.**

**1 · No server.** He asked the right question first — *what would it even buy me?* —
and the honest answer is three things: automation (no manual upload/download/merge
dance), a third device, and **the ability to publish the tool to other people**, who
cannot be taught a merge ritual. None of those is worth a server today, for one owner
and two machines.

**2 · No backup encryption yet.** His reasoning: the data never leaves the user, so it
is the user's own. **The one fact recorded against it, without argument:** a compromised
Drive account today means the whole warehouse is readable, because
`bundle.py`/`archive.py`/`drive.js` contain no encryption at all. He called it a future
plan and that is what it is.

**3 · Solo now, published later.** Which is what makes decisions 1 and 2 revisitable
rather than permanent.

**4 · All of it waits for muqawil.**

### And three of his own questions sharpened the audit, so they are recorded too

He did not accept the conflict table as written, and he was right twice:

- **«الزحف اعتقد انه لن يتعارض ابدا»** — correct, and *provably* so, not merely likely.
  `generic_page_snapshot` is immutable by trigger and keyed on
  `(source_url, content_hash)`; `dataset_sighting` merges by `MIN`/`MAX` on dates;
  everything derived is recomputed. **One exception in everything the crawl produces:**
  `seen_count`, where `MAX` under-counts two devices that each saw a contractor.
- **«tax … قرار يوضع فى الكود … لكن ليس مينفعش مستخدم ياخد قرارين مختلفين فيها»** —
  right, and better than he thought. `tax.py` records *"what the source SAYS about tax,
  and where it says it"* in three states, and `currency_rate` is fetched with an
  `as_of`. **They are not decisions at all — they are observations**, which puts them in
  the evidence population where nothing ever conflicts. The audit had them as
  "server-authoritative, client proposes"; that premise was wrong, because nobody
  proposes.
- **«القاعدة تتغير باستمرار … هل هذا فى الحسبان؟»** — yes, and with a bite worth
  knowing: `warehousemerge._same_shape` refuses to merge across schema versions, so
  **`git pull` on both machines is a precondition of every transfer**, not tidiness. It
  would have blocked him on 2026-08-22, when the installed CLI was 0.2.2 and the
  arriving bundle was v9.

**So the conflict surface is much smaller than the audit first drew it**: only data a
person edits by hand and could edit twice — retention policy and pins, `site_profile`
and `dataset_definition` (which is how a new source is added), schedules and feeds,
saved views and settings. Everything else is evidence, derived, or a release.

### Two findings that are true whatever he decides later

Recorded here because deferring them costs more than deferring the rest:

- **`REQ-26` is not built and he believes it is.** `extension/accounts.js` remembers
  several accounts and writes nothing to disk; `databases/registry.py` has one
  `DATABASE_ROOT`; `account.py` says in its own docstring that it does not use
  per-account directories and does not refuse another owner's warehouse. **Two accounts
  on one machine open the same file.** The moment a second person uses the tool, their
  data mixes with his.
- **48 of 48 primary keys are autoincrement integers.** A tool published to other people
  with integer keys can never sync, and adding a client-generated key after users hold
  data is a painful migration. Today it is an `ALTER TABLE`.

### And the design answer he asked for, kept for when he returns

Automatic sync **is** achievable with no server: Drive as an append-only log of small
immutable per-device files — **never the SQLite file itself**, because WAL plus partial
sync corrupts a database. The price is that **Hybrid Logical Clocks become necessary**,
where a server would have made them pointless, and that **nothing can reject an
operation** — so retention policy, which destroys data, would need an automatic rule
instead of a human decision. For a published tool, Drive-per-user also solves user
isolation for free.

---

### R-45 · The site is the only source of truth, and a field the table does not need goes in the ROW'S CARD

**2026-08-22 · data model + surface · answers `Q-17`, and rejects both options it offered**

> «ما يقوله الموقع هو مصدر الحقيقة الوحيد لا نعدل عليه»
>
> «فى كاتوجرى المنتجات كنا مثبتين اعمدة محددة فى الجدول واى معلومة زيادة عند الضغط على
> الصف يظهر كارد تحتها ونضع فيه المعلومة · نفس الشى اريده فى كاتوجرى المقاولون · لان
> المقاولون سيكون هناك عدة مصادر له فى المستقبل · الفائدة اى ان معلومة مثل مستوى
> الجاهزيّة لا داعى لوضعها فى عمود خاص فى الجدول ولكن عند الضغط على صف معين وهو يحملها
> تظهر فى الكارد الخاص بالمقاول»

`Q-17` asked two questions and he answered both by refusing the way they were framed.

**1 · WE NEVER TRANSLATE. The site's words are the record.** The question offered
"write our own English" as an option for the three licensed activities whose English
half muqawil publishes truncated or simply wrong. **Refused, and on the principle
rather than on the case.** Where the site publishes no usable English name, the node
keeps its Arabic identity and **no English name at all** — which is what
`contractors._licence_paths` already does, and now it does it because it was ruled
rather than because it was the cautious default.

This is `SR-1` — *the source of truth is what the site publishes* — reaching the
extraction layer, and it settles a class of question rather than one field. A mapping
we invent is our claim dressed as the site's data, and no column here may carry one.

**2 · A FIELD IS NOT A COLUMN. Fixed columns, and everything else in the row's own
card.** The question offered "a migration for a column" or "read but do not store",
and both were wrong. The readiness level is **stored** — it is a real fact the site
publishes on 10 of 1,500 rows — and it is simply not a **column**.

**His reason is the load-bearing part, and it is about the future rather than about
this field:** *"because contractors will have several sources in the future."* A
column is a promise every source must keep. `المقاولون` is a **category**, and Balady,
the UAE registries and the Gulf sources queued in `docs/STATE.md` will each publish
their own extras. A table whose columns are the union of every source's fields grows a
column per source and a NULL per row — which is exactly the shape
[`OP-43`](BACKLOG.md) found on the products side, where madar reached 59 variation
axes and 33 of them were non-empty on under 1% of rows, and he asked three times to
have them moved.

**WHAT THIS MEANS IS WORK, NOT A NOTE, AND THE HONEST PART IS THAT THE CARD DOES NOT
EXIST YET.** Measured 2026-08-22 across `extension/` and `scrapex/webui/`:

| piece | state |
|---|---|
| a per-row card shown under a clicked row | **does not exist**, on either surface. No `rowFormatter`, no expansion handler, nothing |
| "which fields are columns" for PRODUCTS | **built** — `/api/promotable/{source_key}`, `fields.promotable_attributes` / `set_promotion`, backed by `source_product_attribute` |
| "which fields are columns" for DATASETS | **not built.** `field_definition` is where it would live |
| the grid both surfaces already ship | **Tabulator**, which supports row expansion natively — so this is a feature to use, not a library to add |
| the extras themselves, for contractors | **already stored.** The dataset path keeps the row in `generic_record.data_json`, so nothing has to be re-crawled to show them |

So the products category has the *fixed columns* half and no card; the contractors
category has neither, and its data is already on disk. **Nothing about this is
blocked** — and note what it does to the readiness level: it stops being a schema
question at all. It is one more value in a card that has to be built anyway.

**Recorded as its own track**, because it is a surface feature with a data-model half
and it is larger than the field that raised it: `REQ-32`.

> **CORRECTED 2026-08-22, SAME DAY, AND THE TABLE ABOVE IS WRONG IN ITS FIRST ROW.**
> Kept in place per **C4** because the error is more instructive than the fix.
>
> That row says a per-row card *"does not exist, on either surface — no `rowFormatter`,
> no expansion handler, nothing."* **A record card has shipped on the engine since
> 2026-07-22** (`6f99a93`, redesigned `bac9c94` on 07-26) — a month before this ruling
> was written. It is 967 lines, about 30% of `grid.js`, and it carries an image gallery,
> spec lists, AR/EN pairing, a price timeline, a changes feed, and a **"Moved out of the
> table"** card fed by `payload.moved_to_details`. `scrapex/reports.py` builds that list
> and its own comment reads *"the owner's ask, using the mechanism that already
> exists."*
>
> **It is opened by row SELECTION, not by `rowFormatter`** — `grid.js` binds
> `table.on("rowSelectionChanged")` → `openOfferPanel` → `GET /api/offer/{key}/{id}` →
> `renderOfferPanel` into `#offer-panel`, and the container's own comment in
> `scrapex/webui/templates/source.html` says *"ONE container under the table, opened by
> SELECTING a row (the owner's ruling)"*.
>
> **WHY THE MEASUREMENT FAILED, because that is the transferable part.** It searched for
> `rowFormatter`, `row-detail`, `expandRow` and `detailsDrawer`, found none, and
> concluded the feature was absent. **A false negative from searching for one symbol** —
> the third instance in a single day of the instrument deciding the answer:
> `sqlite_master` asked for `UNIQUE` cannot see an auto-index from a table constraint,
> and a card census asking for `h3.card-title` cannot see a card titled with an `h4`.
> The lesson is `LESSONS.md` §9's, arriving through a third door: **a search for one
> spelling of a feature is not a measurement of the feature.**
>
> **AND IT CHANGES WHAT HE ASKED FOR. He was not misremembering.** This ruling and
> `REQ-32` both read as though he half-recalled something that was never built. The
> truth is that it is **fully built for products, on the engine**, and his complaint was
> precisely that the contractors category lacks it — which is what he said: «نفس الشى
> اريده فى كاتوجرى المقاولون». `REQ-32`'s step 3, *"the same card for the products
> category"*, was already done before it was written.
>
> **The ruling itself stands unchanged**, and this correction strengthens rather than
> weakens it: a field is not a column, and the row's card is where the extras go. What
> changes is the cost and the shape of the work — the shell exists and is a **port**,
> while the contractors body is **new engine work**, because four of the five endpoints
> the engine's data page consumes run against the price warehouse and there is no
> dataset equivalent of `/api/offer`.
>
> Two further measurements from the same session, both worse than this ruling assumed:
> `dataset_field` holds **11 rows for `source_key='contractors'` and every one is a
> price-path key** (`price`, `tax`, `stock_quantity`, `curation`) — opening the chooser
> on the contractors table registered the *price* header against the dataset — and
> `dataset_table_payload` **never reads `dataset_field` at all**, so hiding, renaming
> and reordering a dataset's columns are silent no-ops. The chooser does not merely
> lack a dataset branch; it lies in both directions.

---

### R-47 · muqawil is ONE card with TWO crawls, and the two stored datasets stay two

**2026-08-22 · surface + data model · answers the question `REQ-37` put to him**

> «زحفين لمجموعة واحدة»

`REQ-37` asked whether the panel should show the two muqawil datasets as *two crawls of
one dataset* or *two datasets of one site*. He chose the first, and the warehouse already
agreed with him: `dataset_relationship` records `contractor_profiles` against
`contractors` as `one_to_one`, **confirmed** — on his own earlier instruction, «اربطهم فى
dataset_relationship». The panel was the only place still saying otherwise.

**WHAT THIS CHANGES, AND IT IS THE LISTING RATHER THAN THE SCHEMA.** Three things:

1. **One card per site.** `_dataset_rows` in `scrapex/webui/app.py` ends
   `GROUP BY d.dataset_definition_id` — one row per dataset, with `dataset_key` standing
   in as `source_key`. It groups by the site instead.
2. **One row count, and the second number becomes COVERAGE.** Today the cards read
   `17,304` and `704` as if they were two populations. They are one: 17,304 contractors,
   of whom 704 have an approved profile. So the card says the population once and reports
   the profile crawl as *how much of it has been fetched* — which is the number he
   actually wants, and the one `--coverage` already computes.
3. **Two crawl options on the card**, because they really are two: the listing sweep is a
   56-cell partition and the profile sweep is 34,834 pages, and they run, resume and
   approve separately. That is what «اختيارات الزحف» means here, and it is the one place
   the GPP comparison he made does *not* transfer — GPP's four energy types across 169
   countries are **one** crawl producing many rows.

**AND WHAT IT MUST NOT CHANGE: the two `dataset_definition` rows stay two.** This is not
a hedge, it is a constraint already recorded in the code. `contractors._approval` says it
in its own words:

> *"A PROFILE IS ITS OWN DATASET… Two documents with two declared field sets — 21 against
> 28 — cannot share one approved schema: every profile would read as a subset of the
> listing's and `R-31` refuses a subset, on purpose, because that is what a broken parser
> looks like."*

Since #254 the profile declares **27** fields against the listing's 28, which makes the
subset closer and the refusal no less correct. Merging the two datasets would either be
refused at approval or — worse — retire the listing's live schema version and drop columns
the site still publishes. **So one card over two datasets, joined by a relationship that
is already confirmed.** The join is the thing that makes the single card honest rather
than a label over two unrelated tables.

**The precedent this sets, and it is why the ruling is worth recording rather than just
building:** a *site* is now a first-class thing in the listing, above the dataset. Track 5
queues Balady, the UAE registries and the Gulf and Egypt sources, and several of those
will publish a directory and its detail pages exactly as muqawil does. Deciding it once,
here, is cheaper than deciding it per source — and it is the same argument he made for
`R-45`: a column is a promise every source in the category must keep.

**Sequenced behind [REQ-36](REQUESTS.md#req-36--the-three-dots-are-missing-on-a-contractor-card-and-unprofessional-on-the-others)**,
which gives a dataset card the `⋮` menu it can use. This ruling asks that menu for
per-dataset actions under one card, so building them apart would mean writing the menu
twice — and a branch is inside `sourceMenu` as this is written.

> **CORRECTED 2026-08-23, WHILE BUILDING IT. THE RULING STANDS; ONE SENTENCE IN IT IS
> FALSE.** Kept in place per **C4**, and recorded per **C5** — an unwritten objection
> helps no one on the other machine.
>
> Point 2 above ends: *"which is the number he actually wants, and the one `--coverage`
> already computes."* **`--coverage` does not compute it.** Measured read-only on his
> warehouse, 2026-08-23:
>
> | asked | answered |
> |---|---|
> | `coverage("contractor_profiles")` | *"nothing has been sighted, so coverage cannot be stated"* — `dataset_sighting` holds **zero** rows for that key |
> | `coverage("contractors")` | *"17,269 stored of 17,417 sighted — 148 seen and never fetched (99.2%)"* |
> | the card's figure | **704 of 17,304 (4.1%)** |
>
> Three different numbers, because `sightings.coverage` answers a different question:
> **stored-of-sighted WITHIN ONE dataset**, from `dataset_sighting`. It has nothing to
> say about how much of the listing the profile crawl has reached, and the profile
> crawl never wrote a sighting at all. Its own docstring is the tell — *"SIGHTED **AND**
> HELD, which is not the same as the number of rows"*.
>
> **THE SHAPE HE RULED IS UNAFFECTED, and the source of the number is the thing that
> was wrong.** 704 of 17,304 comes from the `dataset_relationship` row he had already
> asked for by name — «اربطهم فى dataset_relationship» — which is `confirmed`,
> `one_to_one`, and is the same join this ruling calls *"the thing that makes the
> single card honest"*. So the figure is computed from the relationship and the two
> row counts, which the listing query already has, and no sighting is consulted.
>
> **WHY IT IS WORTH THE SPACE RATHER THAN A QUIET FIX.** "The mechanism already exists"
> is the most expensive kind of wrong sentence in a ruling: it turns a design decision
> into a wiring job and the next session sizes the work off it. This is the same family
> as the correction under `R-45` — there a capability was said to be missing and had
> shipped a month earlier; here one was said to exist and does not. Both were settled by
> running the thing instead of reading about it.
---

### R-48 · The extension is the control room and the only interface; the engine executes and reports

**2026-08-22 · architecture · records a decision of his that was never in this register**

> «اصلا كان هناك خطة بفصل المحرك عن extension وتم تحديد دور كل منهم وتم اعتماد ان
> extension هى المتحكم الرئيسى وان المحرك له مهام محددة فقط · راجع هذه النقطة لزيادة
> التوثيق»

**He is right on every count and the review found the gap is not the decision — it is
where the decision lives.** [PLATFORM-PLAN.md](PLATFORM-PLAN.md) states it plainly and has
since it was written:

> *ScrapeX (extension) — the control room, and the only interface*

and Decision 9 of that plan: *"Databases are **managed only through ScrapeX** — location,
backup, restore, migration. **The controls live in the extension; Engine executes
them.**"* The transports are separated too — control over native messaging, data over
HTTP on `127.0.0.1` — and four rules are derived from it there.

**SO WHY RECORD IT AGAIN HERE. Because `CLAUDE.md` sends every session to
`docs/RULINGS.md` "before designing anything", and this decision was not in it.**
`PLATFORM-PLAN.md` is a plan, indexed from `STATE.md` under its track, and `CLAUDE.md`'s
map does not name it. A session designing a feature therefore never met the one decision
that governs which side of the wire that feature belongs on. That is a filing defect of
exactly the kind `C7` exists to prevent, one register over — and its cost is measurable.

### Five requests of 2026-08-22 are one architectural debt, and none was recognised as such

Every one of these was raised, measured and filed **as its own defect** before anyone
noticed they are the same defect:

| request | what it is, as a boundary violation |
|---|---|
| `REQ-38` | The panel sets a **10,000 ms** deadline on `POST /api/bundle`. The build measured **73 seconds**. The controller is sizing work only the executor can size — and the abort does not stop the engine, so it writes 314 MB and reports failure |
| `REQ-39` | The extension holds the **only** Drive token and stores no answer. Nothing else can ask what Drive holds, so `R-43`'s "Drive is the source of truth for DATA" is unqueryable |
| `REQ-35` | The panel **guesses** how the engine was started, from an empty version string. The engine knows and is never asked, so "running from source" renders as "Not detected" |
| `REQ-32` / `R-45` | The row's record card — 967 lines — runs on the **engine's** HTML page and not in the panel. "The only interface" is not the only interface |
| `REQ-07` / `DEC-8` | The engine still serves a complete data UI at `/source/{key}`. This is the migration that exists to end it, open since 2026-08-12 |

**The pattern is one sentence: the boundary is decided and not enforced, and every
violation costs him something he can see** — a button that cannot work, a healthy engine
reported absent, a backup nobody can confirm, a feature that exists on the wrong side.

### The rules that follow, stated so they can be tested

`PLATFORM-PLAN.md`'s four rules are about data and transports. These four are about
**authority**, which is what today's five violations each got wrong:

1. **The engine is the authority on itself.** Its version, its run mode, its schema, its
   health. The panel **reads** these; it never infers them from an absence. A guess is how
   "running from source" became "Not detected".
2. **Only the side doing the work may bound the work.** A deadline, a page size, a row cap
   or a chunk size is the engine's to state and the panel's to respect — because only the
   engine knows what a 1.18 GB warehouse costs. Where the panel must set one, it takes the
   number from the engine.
3. **Whoever holds the credential owes a report.** The extension alone can reach Drive, so
   the extension alone can say what Drive holds — and it must record that where the engine
   can read it, or the state dies with the panel.
4. **A user-facing surface belongs in the extension.** The engine may keep pages for
   development and for local tools; it may not be the place a capability *only* exists.
   Every such page is a migration owed, and `REQ-07` is the standing one.

### What this ruling does not do

**It does not deprecate the engine's web UI**, and it must not be read that way. `DEC-8`
measured that page as the SOURCE of the port — 3,212 lines of `grid.js`, of which about
forty are data work — so it is the asset the migration spends, not debt to delete. The
rule is that a capability may not live *only* there.

**And it does not settle who runs a crawl.** Control is the extension's, execution the
engine's, and the crawl is execution — but which registry a generic crawl belongs in is
still open (`REQ-25`, and the question at the foot of `GENERIC-FETCH-SEAM.md`). This
ruling narrows nothing that was open.

**Filed with `CLAUDE.md`'s map corrected in the same commit**, per **C2**, so the next
session meets the boundary in the register it is told to read rather than in a plan it is
not told about.

---

### R-49 · `MIGRATION-PLAN.md` is the base plan, and its date is the test

**2026-08-23 · architecture · settles seven recorded contradictions at once**

> «دى الخطة الاساسية واى تعارض معاها قبل هذا التاريخ فهو تغير بعد هذا التاريخ اسالنى
> عنه · التاريخ المقصود هو تاريخ الخطة»

**The rule, stated so a session can apply it without him:**

[MIGRATION-PLAN.md](MIGRATION-PLAN.md) is **the base plan**. Its date is
**2026-08-12** — *"Drafted 2026-08-12. Every number here was measured today, not
recalled."* (`MIGRATION-PLAN.md:22`; it reached the repository on 2026-08-15, and the
drafting date is the one that counts).

| the contradicting text is dated | what a session does |
|---|---|
| **before 2026-08-12** | **the plan wins.** Mark the older text superseded per `C4` and move on. Do not ask |
| **after 2026-08-12** | **ask him.** Do not resolve it, do not pick the newer one by default |

**Why this is worth a ruling rather than a note.** Two studies on 2026-08-23 returned
**twenty recorded contradictions** about which side of the wire a responsibility belongs
on, and every one of them was unanswerable by a session, because the repository holds
several documents that each state a division of labour and **none of them cites or
supersedes another**. This ruling makes the answerable ones answerable and leaves only
the genuinely open ones on his desk. It is the same move as `R-02` — an un-computable
mapping is his — applied to a pile rather than to one field.

### Applying it, measured at LINE level rather than file level

The dates below are **the age of the contradicting sentence**, not of the file that
holds it. That distinction is the whole exercise: the first study dated text by each
file's last commit and thereby **inverted the seniority** of two documents in its own
headline finding, which its verifiers caught (`LESSONS.md` §7, the fourth shape).

| contradicting text | dated | verdict |
|---|---|---|
| `PLATFORM-PLAN.md` §4's `fetch ─→ extract ─→ domain ─→ store`, all inside the engine | **2026-08-05** (file last touched 08-08) | **superseded** on the division of labour |
| `PLATFORM-PLAN.md` Decision 25 — *"The second group is dead on a device with no engine installed"* | **2026-08-05** | **superseded**; also factually false for Data since 2026-08-12 (`REQ-40`) |
| `PLATFORM-PLAN.md` Decision 9 — *"A browser extension cannot create a SQLite file"* | **2026-08-05** | **superseded** as a flat claim. The plan's own `C1` names `wa-sqlite + OPFS` as the thing that removes `127.0.0.1`, and the repository's spike then built the whole schema in OPFS |
| `MASTER-PLAN.md` **Topology A** — the browser-native TS/MV3 extension as the public product, warehouse in `wa-sqlite` | **2026-07-18** (his own decision; file 07-19 → 08-05) | **superseded.** This closes `Q-6`, open since 2026-08-16, without asking him again |
| `COMPATIBILITY.md:20-22` — *"A crawl job belongs to the Local Runtime, not to the Side Panel lifecycle"* | **2026-07-19** (single commit) | **not a conflict.** The plan agrees — *"Jobs stay in the engine"* (`:61`) — so the older text stands where it does not contradict |
| `GENERIC-FETCH-SEAM.md:11-12` — the HTML is handed in *"by the panel capturing the page the user is looking at"*, i.e. **fetch on the panel** | **2026-08-09** | **superseded.** The plan keeps *fetching* in the engine. Its `extract`-is-the-engine's half is untouched |
| `ENGINEERING.md:61` (S2) — *"All parsing/normalization in pure JS modules"*, i.e. extract on the extension | **2026-07-18**, the initial commit | **superseded.** And note: the first study called this the *newer* text and built a headline on it. It is the oldest line in the comparison |
| `./README.md:121` — the engine's read-only browse UI, documented as a feature | **2026-07-18** | **superseded** as a statement of where the interface belongs; still true as a description of what exists |
| `./README.md:107` — *"The owner ruled on 2026-08-11 that the engine fetches data and saves it locally"* | **2026-08-12** (`8272bf3`, #165) | **not a conflict — it agrees**, and it is the same day. This is the text closest to «المحرك مهمته fetch» |

**Nine items, and not one of them needed him.** Eight are superseded by his rule; one
was never a conflict. That is what the ruling bought.

### The one thing it does NOT settle, and it is now the only open question of the set

`R-48`'s rule 4 is dated **2026-08-22**, which is **after** the base plan:

> *"A user-facing surface belongs in the extension. The engine may keep pages for
> development and for local tools; **it may not be the place a capability only
> exists.**"*

Against the base plan's own decision table (`MIGRATION-PLAN.md:60`):

> *"Export stays in the engine — it is SQL over SQLite, not a file move."*

**Export is a user-facing capability that exists only in the engine today**
(`scrapex/webui/app.py:1329`, `@app.get("/export/{source_key}.xlsx")`). Both statements
are his, the newer one contradicts the older, and **the rule says a newer conflict is
his to settle.** So it goes to him rather than being resolved here. `Jobs stay in the
engine` (`:61`) is the same shape and rides with it.

### What this ruling does not do

**It does not make the base plan correct about facts.** The plan's own banner records
two of its statements that measurement overturned, and `REQ-40` records a third: its
`C1` points at `wa-sqlite`, the library the repository's own OPFS spike calls *"the one
part that is simply the wrong choice."* **Seniority settles a conflict of intent; it
never settles a question of measurement** — a newer number beats an older number
regardless of which document holds it, and that is not what this ruling is about.

**And it does not retire the older documents.** Per `C4` the superseded text stays in
place, marked, pointing here. A reader needs to see that the four-stage diagram was
once the plan in order to understand why the code still looks like it.

---

### R-50 · The engine is a helper to the extension, and any task the extension CAN do moves to it

**2026-08-23 · architecture · gives the boundary a test, and supersedes part of the base plan**

> «قاعدة البيانات موجودة على الجهاز والمحرك معطوب افشل فى التصدير هذا غير مقبول · ثانيا
> قاعدة البيانات موجودة وانا مش عارف اتصفح ايضا مرفوض · ولذلك هذه الادوات تنقل الى الاداة
> طالما يمكن استخدامها · المحرك اداة مساعدة للاداة وليس الشى الرئيسى اذا اى مهمة تستطيع
> تنفيذها الاداة تنقل لها»

**He was asked one question and answered a larger one.** The question was narrow: `R-48`'s
rule 4 (*"it may not be the place a capability only exists"*, 2026-08-22) contradicts the
base plan's *"Export stays in the engine"* (`MIGRATION-PLAN.md:60`, 2026-08-12), and
[R-49](#r-49--migration-planmd-is-the-base-plan-and-its-date-is-the-test) sends a
post-dated conflict to him. **This is the answer, and it is the general rule two studies
and thirty-eight measured responsibilities had failed to produce.**

### The rule

> **The engine is a helper to the extension, not the main thing. Any task the extension
> CAN perform, moves to it.**

**The test is CAPABILITY, not category.** Every previous attempt at this boundary asked
*which layer does this belong to* — control against execution, interface against data,
fetch against display — and every one of them produced a table that contradicted another
table. His test asks one question of each responsibility: **can the extension do this?**
If yes, it moves. If no, the engine keeps it and that is the *only* reason the engine
keeps anything.

### The two failures he named, in his own words, and they are the whole justification

| what he said | why it settles the question |
|---|---|
| *"the database is on the machine and the engine is broken, so I fail to export — **this is unacceptable**"* | Export is a read of a file that is sitting on his disk. A broken helper must not stand between him and his own data |
| *"the database is there and I cannot browse — **also refused**"* | Same shape, and it is `REQ-40`'s premise stated as a verdict rather than a request |

**Both were live on 2026-08-23 when he said it.** The engine he had installed could not
serve a page at all — `packaging/build_engine.py` bundled two data directories and the
runtime opens five — so *"the engine is broken and I cannot export"* was not hypothetical.
He was describing his own machine.

### What it supersedes, per C4

**`MIGRATION-PLAN.md:60` — *"Export stays in the engine — it is SQL over SQLite, not a
file move"* — is superseded as a statement of WHERE THE CAPABILITY LIVES.** Its
engineering observation stays true: export *is* SQL over SQLite. What no longer follows is
that the engine may be the only place it exists.

**And the reasoning that produced it is the trap this ruling closes.** *"It is SQL over
SQLite, not a file move"* is an argument about **implementation**, and it was used to
answer a question about **ownership**. Under `R-50` those are separate: the engine may
still execute the query, and the capability may not live only there. `Jobs stay in the
engine` (`MIGRATION-PLAN.md:61`) is the same shape and is now open to the same test —
**but it was deferred by him personally, so it needs his word and not this rule's.**

### How a session applies it, and what it costs

Ask of each responsibility, in this order:

1. **Can the extension do it at all?** Not *should* — *can*. Answer with a measurement,
   not an opinion: the repository's own OPFS spike (`spikes/opfs-sqlite/FINDINGS.md`) is
   what that kind of answer looks like.
2. **If it cannot, the engine keeps it** — and the reason is recorded as a technical
   limit, so the day the limit lifts the row is revisited rather than inherited.
3. **If it can, it moves** — and until it has moved, the engine's copy is a **migration
   owed** and is named as one (`R-48` rule 4).

**This reverses the direction of the whole inventory.** The thirty-eight-responsibility
table produced on 2026-08-23 assigned twenty-two to the engine, and it assigned them by
asking where each one *belongs*. Every one of those twenty-two must now be re-asked as
*can the extension do this*, and the answer for many of them is a measurement nobody has
taken.

### What this ruling does NOT say

**It does not say the engine stops doing these things.** A helper that does the work is
still the helper doing the work. What it forbids is the engine being the **only** place a
capability exists — which is `R-48` rule 4, now with a test attached.

**It does not settle the fetch boundary.** The engine reaches sites the extension has no
host permission for, and that is a genuine *cannot*. `R-50` is why it stays, and gives it
a better reason than seniority.

**And it is NOT discharged by making the engine start.** The session that found the
packaging defect said so itself, unprompted, and it is the sharpest reading of this ruling
anyone has offered: *"I made the engine start. My change removes today's cause; it does not
remove the coupling."* `engine-v0.3.1` fixes **why** the engine was broken this morning. It
does not touch the fact that **a broken engine takes the export down with it**, which is the
thing he called unacceptable. A session reading this ruling beside that merge could easily
conclude the matter is closed. **It is not, and the distinction is cause against coupling.**

**And it does not license a rebuild.** `DEC-8` measured the engine's data page as the
SOURCE of the port — 3,212 lines of `grid.js`, about forty of them data work — so moving a
capability means **porting the asset**, not writing a second one. `R-50` decides *where*,
never *how*.

### The mechanism that produced this ruling, recorded because it worked

`R-49` was written an hour before this one and its whole content is a routing rule: older
conflicts are superseded, newer ones go to him. **It routed exactly one question out of
twenty, he answered it, and the answer turned out to be the general rule.** That is the
argument for `R-49` and for `C3` together — the pile was unanswerable until the one
genuinely open item in it was isolated and put in front of him alone.

### R-43 · Drive is the single source of truth for DATA; the repository stays it for CODE

**2026-08-22 · two machines · extends `CLAUDE.md`'s founding rule to the warehouse**

> «الفكرة انى اريد توحيد او دمج قواعد البيانات … افضل طريقة هى حفظها على drive وقبل
> التطوير فى الجهاز الاخر ينزلها ويدمجها معه من ثم يحفظها … وعند العودة لك مرة اخرى
> سيكون هناك مصدر واحد للحقيقة هو drive»

`CLAUDE.md` exists because everything saying *where the work stood* lived under one
machine's home directory. It fixed that for code, decisions and state — **and said nothing
about the data**, which is the half that cannot be committed. This is that half.

**BOTH MACHINES HAVE DEVELOPED muqawil**, which is what rules out the obvious answer:
neither file may be copied over the other, because each holds work the other does not.
`R-24` already says upgrade rather than replace; this is the same rule between two
machines instead of two versions.

### What made it buildable, and it was not obvious

*"Merge them"* is not an operation on two SQLite files. Every primary key is an
autoincrement, so **both machines hold a `page_snapshot_id = 1` for a different page** —
merging naively means remapping every key and every foreign key pointing at one, which is
[OP-30](BACKLOG.md) at a far larger scale. Measured 2026-08-22, three natural keys exist and
that is what changes the answer:

| table | natural key | measured |
|---|---|---|
| `generic_page_snapshot` | `(source_url, content_hash)` | 20,379 rows, **20,379 distinct** |
| `dataset_sighting` | `(dataset_key, external_id)` | UNIQUE in the schema |
| `generic_record` | `(dataset_definition_id, record_key)` | UNIQUE in the schema |

**ONLY THE EVIDENCE TRAVELS, AND THAT IS THE WHOLE DESIGN.** A snapshot is a page as it was
fetched and a sighting is what the site showed and when — neither can be recomputed.
Everything else is rebuilt by `--approve` with **no network**: records, revisions,
ingestions, the taxonomy and its 15,559 memberships. So nothing that carries a primary key
ever crosses, and no id is ever remapped.

**EVERY COLUMN MERGES WITH `min` OR `max` AND NONE WITH `+`.** The first implementation
summed `seen_count`, and three merges of the same file took one id from **4 to 8 to 12 to
16** while the module's own docstring called the operation idempotent — caught because a
test looked at the value instead of the row count. Summing is wrong on the *first* merge
too: two machines crawling the same listing observe the same site state, so their counts are
two observations of one fact.

### The lock, which his plan was missing

Download → work → upload has nothing stopping both machines doing it on the same day, and
**the second upload silently wins**; Drive keeps versions but cannot merge them. That is
`R-37`'s parallel-session problem one level down, and worse, because no CI sees it.

So a warehouse records which machine holds it — `scrapex_meta.checkout_holder`, beside the
`account_owner` that `R-34` already put there, so no migration — and `scrapex
merge-warehouse` refuses to write into a copy somebody else holds. Re-claiming your own is
allowed, because a session that died mid-merge has to pick the same copy back up.

**A SHIPPED COMMAND, NOT A SCRIPT.** `scrapex merge-warehouse --status / --machine /
--release / --from`. `contractors.py` exists because every piece of the first warehouse's
pipeline was committed with no invocation, so the other machine could read how it worked
and could not run it. Seventeen tests, and the one that matters most asserts that merging
three times changes no VALUE.

---

### R-42 · One PRIMARY session merges; every other session is SECONDARY and asks

**2026-08-21 · process · supersedes [R-37](#r-37--the-agent-does-not-merge-the-main-programmer-does)**

> «اريد تعديل القاعدة بحيث ان هناك جلسة اساسية وجلسات فرعية · الجلسة الاساسية هى الجلسة
> التى تستطيع الدمج بينما الجلسات الفرعية لا · يمكن ان تسالنى اذا كنت جلسة اساسية ام
> فرعية لتحدد هذا الامر»

`R-37` removed the merge from every session because **merge order across parallel
sessions is not a thing any single session can see**. That diagnosis was right and
nothing here contradicts it. What it got wrong is the remedy: it solved a problem of
COORDINATION by removing a CAPABILITY, so the cost R-18 was written against came
straight back — a green branch idles until he happens to be at a keyboard.

**THE FIX IS TO NAME WHO COORDINATES.** Exactly one session is PRIMARY and may merge.
Every other session is SECONDARY: it builds, pushes, reports, and stops. The blindness
`R-37` identified is real, so it is answered by making one session the one that can see
— not by blinding all of them.

### How a session knows, and it is the whole of the rule

**IT ASKS. IT NEVER INFERS, AND IT NEVER ASSUMES.** He named the mechanism himself:
*«يمكن ان تسالنى اذا كنت جلسة اساسية ام فرعية»*. There is no other source — being
first, being busy, holding the open pull request, or having merged earlier in the same
session prove nothing about which session he is treating as primary right now.

**AND THE DEFAULT IS SECONDARY.** Until he answers, a session is secondary. That is the
only safe direction: a secondary session that was really primary costs one message,
while a primary session that was really secondary is the bad merge `R-37` was written
about — and `main` has no branch protection, so nothing downstream would catch it.

**ONE, NOT "AT MOST ONE PER MACHINE".** He works from two machines and two accounts
(`CLAUDE.md`), and two primaries on two machines is exactly the parallel-merge problem
under a new name.

**THE ANSWER IS PER SESSION AND IS NOT A REPOSITORY FACT.** It cannot be committed —
which session is primary changes with the day and is not true of the code. So it is
asked in the session that needs it, and it does not carry to the next one. A session
resuming from a summary that does not record the answer asks again.

### What does not change

`R-37`'s reading of the report stands in full for a secondary session: name every check,
every failure, and **whether each failure ran at all**. `R-18`'s reading of *green*
stands for the primary one — a `SKIPPED` required check is not satisfied, an absent run
is not a red one, and a tick from before the last push describes a tree nobody is
merging. `R-22` still requires the full suite before a pull request opens.

**AND THE GUARD MATTERS MORE NOW, NOT LESS.** Returning the merge to a session returns
its judgement to the gate, so the failures a person should not have to hunt for must be
mechanical. `tests/test_the_registers_cannot_collide.py` was built the same day and
immediately caught two real collisions between `#244` and the branch beside it — `R-36`
and `R-37` claimed twice, and `OP-32` claimed twice — every one of them green,
mergeable, and invisible to git. Branch protection on `main` is still absent and still
his to switch on.

---

### R-41 · A multi-valued group is named by a DECLARED per-site map, never by position or by its heading

**2026-08-21 · extraction · answers a question the measurement raised**

> «كيف تُسمّى المجموعات الخمس؟» → **«خريطة مُعلَنة لكل موقع»**

`R-38` needs to know which group a row belongs to, and neither obvious answer works.
Measured against the committed profile:

| candidate rule | why it fails |
|---|---|
| the detector's own name | it returns `Table 1` … `Table 5` — position, which moves when a section does |
| the nearest heading | **three of the five tables sit under one heading** |
| the column signature | two tables carry the same `الإسم / القيمة` pair, and three are **empty** for this contractor, so there are no columns to read |

So each site declares it, the way `CARD_FIELDS` and `PROFILE_FIELD_ORDER` already declare
what a listing and a profile publish. Explicit, tested against a committed fixture, and
unchanged when the site moves a section.

**And the heading rule fails for a second reason that would have been worse.** The
interests card is titled `Interests` in English and **`الأنشطة`** — "Activities" — in
Arabic. Not a translation. A heading-based rule read 25 nodes from the English profile and
**0 from the Arabic**, which is `DSN-05`'s failure again: a locale-dependent selector that
silently produces nothing for half the data.

**The price, stated:** one declaration per group per site. That is the cost of a rule that
cannot drift, and this file already records what the alternative costs.

> **AMENDED 2026-08-22 — the rule holds and TWO OF ITS OWN OBSERVATIONS were wrong.
> Both kept visible per C4.** Measured over 2,419 profile pairs rather than the one
> committed fixture:
>
> - *"two tables carry the same `الإسم / القيمة` pair"* — only one does, and it now has
>   a name: it is the **self-build price** table, in a `section-card` of its own. The
>   second sighting came from a regex chunk that ran past an empty tab pane into the
>   next card.
> - *"three are empty for this contractor"* — for the two relation tables that is not
>   this contractor, it is the site. `contractor-tab3` carries rows on **0** of 2,419
>   pages and `contractor-tab2` on **2**.
>
> **The rule gains a companion in its own shape.** A declared map names the groups; a
> declared map now also names the **cards** — `PROFILE_CARDS` in
> `scrapex/extract/muqawil.py`, with `undeclared_cards()` reporting any data-carrying
> card that is not in it. `R-41` argues that a name must be declared rather than
> inferred; the card census is that argument applied one level up, to *which sections
> exist at all* — the question two fixtures could not answer, and the one that hid a
> price for months.

---

### R-34 · An account is the signed-in address, and a warehouse records whose it is

**2026-08-21 · architecture · answers [Q-14](BACKLOG.md), unblocks [REQ-26](REQUESTS.md)**

> «ايضا databse الموجودة حاليا اجعلها تخص حساب muhammad.bayoumi.ali@gmail.com»

`Q-14` asked what identifies an account, and it was put to him **without a
recommendation** because the Google address and the Chrome profile each fail exactly
one half of what he had described, and the answer decides where other people's data
lands. He settled it by naming one: **the signed-in address**, option (a).

**HIS OWN WAREHOUSE IS NOW CLAIMED BY IT** — `scrapex_meta.account_owner` reads
`muhammad.bayoumi.ali@gmail.com`.

| | |
|---|---|
| `scrapex_meta`, not a new table | it already holds exactly this kind of fact — `database_kind`, `migration_stream`, `contract_version`. One row, one truth about the file, **no migration** |
| the address is stored as he writes it | surrounding space is trimmed, and the **local part keeps its case**: email local parts are case-sensitive by specification, and folding them would quietly merge two addresses a provider considers different |
| re-claiming takes `force` | handing a warehouse from one account to another moves someone's data under another's name. `R-24`'s reasoning about a user's database, applied to its owner: deliberately, never behind his back |
| an unclaimed warehouse passes any account | every file that predates this is unclaimed, and none may stop working because a rule arrived after it (`R-23`) |

**WHAT IS DELIBERATELY NOT ENFORCED YET, and saying so is the point.**
`assert_owner` exists and **nothing calls it on the connect path**. `DATABASE_ROOT`
is still `~/.scrapex` — one directory per operating-system user — so a second account
on this machine has nowhere else to go, and refusing a warehouse claimed by someone
else *before* the per-account layout exists would lock him out of the only warehouse
there is. The rule has one definition ready for `REQ-26`; the layout is `REQ-26`.

**So this ruling answers the identity question and leaves the layout open** — the
half that was blocked on him is unblocked, and the half that is engineering is named.

---

### R-33 · The migration ledger is keyed on the migration's NAME, not its number

**2026-08-21 · data · answers [OP-30](BACKLOG.md), chosen from three options**

> «نفذ أ»

Found on his LIVE warehouse while upgrading it at his instruction, and it left the
file unopenable by any build — on `connect()` as well as on upgrade.
`database_migration` is `migration_number INTEGER PRIMARY KEY` — **one number
space** — and a warehouse carried over from the price database holds two streams
in it:

| number | name | whose |
|---|---|---|
| 6 | `0006_a_row_says_when_it_was_last_proved_absent.sql` | the engine's |
| 1006 | `0006_change_event.sql` | the price stream's, renumbered by the repair |

Engine migration `0006` was **the first number this stream had ever wanted**, so the
digests of two unrelated files were compared and it reported *"checksum changed;
restore the original migration file and retry"* — **with no file having changed.**

**THE NUMBER WAS ALREADY MEANINGLESS AND THE NAME NEVER WAS.** `migration_number`
claimed to say where in its stream a migration sits; with two streams sharing the
space it says only which row came first, and who holds a number is a question of
precedence rather than identity. A file's name is its identity, unique across both
streams, so a foreign row becomes invisible instead of fatal.

**WHAT `user_version` ALREADY GUARANTEED** is why this is safe: the ledger does not
decide what to apply — `PRAGMA user_version` does. It is purely a checksum record.

**WHAT THE FIX WAS NOT ALLOWED TO COST.** Two guards hold the line: a file whose
digest really differs is still refused, and a ledger missing a row for one of *our
own* migrations is still reported. Otherwise the fix would have turned a detectable
state into a silent one.

**AND WHY NOTHING CAUGHT IT, which is the part worth keeping.** A fresh `init-db`
writes only this stream's rows, so nothing collides — and **CI always starts from a
fresh database.** 273 tracked test files and the `migration-authority` job, which
runs the whole suite against the real migration stream, all passed while this sat
there. The collision needs a warehouse that **carried over**, and no fixture had
one. Same class of gap as [R-24](#r-24--a-users-database-is-upgraded-never-replaced):
the upgrade path is exercised only by a real user's file. There is a test that owns
it now.

**A `stream` column keyed `(stream, number)` is the model this deserves** and stays
in `OP-30` as the real fix: it is a migration, and it would have to run *before* the
verification that was failing.

---

### R-32 · ScrapeX is a collection platform. Price is ONE category, and filing it as the whole thing was a mistake

**2026-08-21 · architecture · corrects `pyproject.toml`, `CLAUDE.md` and `README.md`**

> «الاداة فى المقام الاول scrape او crawl · تسميتها او ادراجها تحت بند واحد الا وهو
> متابعة الاسعار دا خطا تماما» · «ونعمل category للمصادر لدينا الان 2 منتجات ومقاولين»

The tool is **collection first**. Price tracking was the first category, not the
category. His categories, in his words: **`products`** and **`contractors`** today,
with `jobs` and `tenders` named as coming.

**`products`, NOT `prices`, and the distinction is load-bearing.** A price is an
attribute of a product observed at a time. Naming the category "prices" would repeat
this very mistake one level down.

**THIS IS NOT A RENAME, AND THE MEASUREMENTS ARE WHY.** The framing is built in, and
it shows up as missing function:

| where | what the framing did |
|---|---|
| `retention.py`, `compaction.py` | measured: they touch **`price_observation` only**. The contractor dataset — 16,761 sighted ids — has no retention policy and no compaction, because nothing generic was ever written |
| two source registries | `source_site` holds 4 price sources, `site_profile` holds `muqawil_org`, and **muqawil is not in `sources.yaml` at all** — so a source lands in one or the other by accident of pipeline |
| `ConnectorFamily` | every value is a shop or price shape (`shopify-json`, `salla-html`, `heidelberg-price-matrix`). A directory, a tender board or a job board cannot be named in it |
| `pyproject.toml` | *"into a SQLite **price-tracking** warehouse"*, repeated in `CLAUDE.md` and `README.md` |

**WHY THE DESCRIPTION MATTERS MORE HERE THAN IT WOULD ELSEWHERE.** `CLAUDE.md` exists
because the repository is the only memory between two machines. A session that reads
*"price-tracking warehouse"* builds one. This framing is self-perpetuating in a way a
wrong comment is not — which is why correcting it is first in the plan and not last.

**What this settles, and what it does not.** Settled: price is a category, a source
names its category, and the platform's own documents say so. **Not** settled: whether
`source_site` and `site_profile` merge, whether `ConnectorFamily` grows or splits, and
what identifies an account (`Q-14`). Those are
[the plan](plans/2026-08-21-the-platform-not-a-price-tracker.md), and none of it is
built.
### R-31 · The warehouse records WHICH field changed, and a new field is a version, not a refusal

**2026-08-21 · data model · extends [R-30](#r-30--r-19-is-built-as-child-datasets-whose-value-references-a-taxonomy)**

> «اريد الافضل على الاطلاق ليس الاسهل فى التنفيذ فى المرحلة الحالية» · «نعم وسع النطاق ونفذ الأفضل»

He asked four things of `R-30`'s shape: is it dynamic when most contractors leave
most values empty, what happens when the site adds a field, is everything kept in
the database, and can a change be **written down** as "this field was updated"
rather than worked out afterwards. Measured, two were already true and **two were
not**, and the two that were not are independent of the (b)/(c) choice entirely.

**1 · A NEW FIELD IS REFUSED TODAY, NOT VERSIONED.**
`extract/service.py` raises `ExtractionConflict` when the field set differs from the
approved one, and its own message points at *"schema-drift review support"* that does
not exist. The machinery is all there — `version_number`, `status`, `valid_to` — and
**v2 is unreachable**: reaching it requires `valid_to` to be set, and measured, all
five references to `valid_to` in the code are **reads**. Nothing has ever written it.

**The rule is DIRECTIONAL, and that is what makes it safe.** A superset — every
approved field still present, new ones added — retires the active version and opens
v2. A subset, a rename or a retype is still **refused**. That distinction is not
invented for this ruling: it is exactly what happened in #234, where `region_id=0`'s
pages carried 21 of the declared 22 fields and were correctly refused. Auto-versioning
any drift would have accepted a parser that silently lost a column.

**2 · A REVISION RECORDS THE WHOLE ROW, SO "WHICH FIELD CHANGED" IS DERIVED.**
`generic_record_revision.data_json` holds the entire object. The answer to "when did
this contractor's readiness change" is computable by diffing two revisions and is
**written down nowhere**. So a field-level change log is added: the row, the field,
the value before, the value after, when, and the snapshot that proves it.

**IT IS LIGHTER THAN WHAT IT SUPPLEMENTS, WHICH IS THE PART WORTH KNOWING.** A
revision copies all 21 fields — roughly 2.5 KB — to record one field moving. A
field-change row is on the order of 100 bytes. **It does not replace the revision**:
the revision is the row as it stood, which is the thing an audit needs; the log is
the question anyone actually asks.

**3 · SPARSENESS WAS ALREADY TRUE, AND IS NOT A REASON TO PREFER (b).**
A child row exists per value held, so a contractor with no activities costs zero rows
and zero NULLs. That is true of (c) equally. Recorded because he asked, and because
the honest answer is that it does not distinguish the options.

**4 · EVERYTHING IS ALREADY IN THE DATABASE.** `data_json` plus the compressed page
in `generic_page_snapshot`, linked by `source_snapshot_id NOT NULL`. Nothing is
discarded. **But JSON's flexibility is partly an illusion and he should know it:** an
undeclared key is stored and is **invisible to the user**, because the payload's
columns come from the declared fields in `schema_version_field`. Flexibility in
storage is not flexibility in the product; that is what point 1 is for.

**What this costs.** `OP-25` route (c) — which he passed over on timing — is now in
scope, and there is one new table. He was told both before ruling.

---

### R-30 · R-19 is built as child DATASETS whose value references a taxonomy

> **EXTENDED, NOT REPLACED, by [R-31](#r-31--the-warehouse-records-which-field-changed-and-a-new-field-is-a-version-not-a-refusal) on 2026-08-21.** Everything below stands. He then asked whether (b) is dynamic for sparse and future fields, and whether a field change can be recorded rather than derived — and two of those answers were no. He widened the scope: «نعم وسع النطاق ونفذ الأفضل».

**2026-08-21 · data model · answers [Q-13](BACKLOG.md), refines [R-19](#r-19--the-five-multi-valued-contractor-groups-go-in-child-tables-not-json)**

> «نفذ ب» — option (b), chosen after asking for the three to be compared on time

He asked for his own ruling to be tested ([REQ-23](REQUESTS.md)), then for the three
implementations to be compared **on time specifically**, and chose (b). So `R-19`
stands and its implementation is settled:

| | |
|---|---|
| **where the child rows live** | a child **dataset** in `generic_record` — no new table, no migration for the rows themselves |
| **how the value is stored** | a reference to a `classification_node`, so the ~120-character bilingual path is stored **once** and referenced by integer |
| **how it is queried** | a **partial expression index** on `json_extract(data_json,'$.node_id')`, scoped by `dataset_definition_id` |
| **how it reaches the sheet** | one export tab per child dataset, driven by `dataset_relationship` |

**Why (b) and not (c), in his own terms — time.** (c) is 7x faster to load once
(3.9 s against 27.6 s) and (b) is **40x faster on the question that gets asked**
(0.6 ms against 20.2 ms) and **3.8x** on the per-value counts. The load happens once
per full re-extraction; the question happens whenever anyone asks it.

**And (a) — `R-19` read literally — is fastest at nothing measured fairly.** Its one
apparent win, the parent roll-up at 612 ms against 1,320 ms, is not the same query:
it matches a string **prefix** with `LIKE`, and the fixture's own separators are
inconsistent (`-` and `–` both appear), so that match fails silently on some values.
It also rewrites **103,698 rows in 5.9 s** when the site relabels a category, against
one row in 0.1 ms.

**Nothing writes `classification_node` today** — measured, `grep` finds no
`INSERT INTO classification` anywhere in the repository, and `reports.py` only names
the table in a glossary. The taxonomy writer is therefore the first thing (b) needs,
not a detail of it.

---

### R-28 · The 74 approved pages are wiped and re-approved from disk

**2026-08-21 · data · answers [OP-25](BACKLOG.md)**

> «امسح وأعِد الاعتماد من القرص» — chosen from three options

> **THE WIPE TURNED OUT TO BE UNNECESSARY, and it was his own later ruling that
> made it so.** `R-31`'s directional versioning landed after this, and measured on
> 2026-08-21 the parser emits **28 fields against the stored 21, a strict superset
> losing nothing** — so re-approving RETIRES v1 and opens v2 instead of needing the
> dataset destroyed. The re-approval was run without the wipe and took
> `generic_record` from **1,172 to 8,936** with v1 kept as history: the 823 pages
> the old schema refused landed, and nothing was thrown away.
>
> **This ruling is not withdrawn** — it decided correctly on what was known, and
> route (a) is still the answer if a genuine schema conflict ever needs it. Recorded
> per **C4**: the decision stands, and what changed is what it implies.

`region_id=0`'s 74 pages taught a 21-field schema, so every page declaring the
declared 22 is refused. The `contractors` dataset is **wiped and re-approved from the
stored snapshots**, which costs ~20 minutes and **not one network request** — the
snapshots are on disk, and that is the entire economics of
[GENERIC-FETCH-SEAM.md](GENERIC-FETCH-SEAM.md).

**It destroys 1,172 rows, and that is the reason it is cheap rather than a cost.**
Those rows are rebuilt from the same disk immediately, and the alternative kept them
at the price of two datasets describing one directory — which `R-11` would not accept.

**What this unblocks is the whole point.** The ledger holds **15,782 distinct ids of
the listing's 17,414** and the warehouse holds 1,172 records. The gap is not missing
evidence, it is unapproved evidence.

The third option — building schema-drift review, which the error message itself points
at — was **not rejected on merit**: it is the largest, it would serve every future
source, and it is now the only remaining part of `OP-25`. It was not chosen because it
would keep this crawl unextracted while it was built.

---

### R-29 · A contractor the site stops showing is `unavailable`, not `retired`

**2026-08-21 · data model · answers [OP-26](BACKLOG.md), completes [R-27](#r-27--a-row-never-disappears-from-the-users-view-its-state-becomes-a-column)**

> «unavailable» — chosen over `retired` and over a rule combining both

`generic_record.status` has accepted `active`, `unavailable` and `retired` since the
table existed, and **nothing has ever written either of the last two**. Detection was
built with `sightings.departures`; this ruling is what lets it write.

**`unavailable` means "the site is not showing this contractor right now" — and the
reversibility is the whole reason.** A crawl that ended early, a cell that failed to
size, a filter the site changed: any of those makes a standing contractor look absent.
Under `retired` that row becomes history with no way back. Under `unavailable` it
returns on the next crawl that sees it, which is exactly what the `returned` state and
`last_absent_at` — shipped in #235 — were built to express.

**`retired` is not thereby unusable.** It remains the honest answer for a contractor the
site states is gone rather than merely stops listing. Nothing writes it yet, and
nothing should until the site gives us that statement to read.

---

### R-27 · A row never disappears from the user's view; its state becomes a column

**2026-08-21 · data model and UI, and it answers a question I had put to him**

> «يجب ان يظل الصف ظاهر للمستخدم مهما اختلف حالة الرصد بينما يكون واضح فى عمود اخر
> مرة تم رؤيته اول مرة تم رؤيته هل اختفى فى اخر زحفة هل ظهر صف جديد لكنه يظل ظاهر
> للمستخدم»

**A contractor's row stays on screen whatever the crawl did or did not see.** What
changes is not its visibility but four facts, each of which is a COLUMN:

| | |
|---|---|
| **first seen** | when this contractor first appeared |
| **last seen** | when a crawl last showed us this contractor |
| **disappeared in the last crawl?** | the site has stopped showing it |
| **is this row new?** | it appeared in the most recent crawl |

**AND IT SETTLES A QUESTION I HAD RAISED.** I had asked him to choose between
`unavailable` and `retired` for a delisted contractor — the two values
`generic_record.status` offers. Under this ruling the choice matters far less, because
**status is informational and never a filter**: whichever value a departed row
carries, the row is still there and the column says what happened. A schema that can
express "gone" must not be wired to a reader that means "hidden".

**MEASURED THE SAME DAY, and the answer was no.** Two readers disagree, and the one
behind the user's grid is the wrong one:

- `browse_records` already returns `status`, `first_seen_at` and `last_seen_at` and
  filters on none of them. Correct by this ruling.
- `dataset_table_payload` — what the grid actually renders — filters
  **`AND status = 'active'`** on both the count and the rows, and builds each row from
  `data_json` alone, so all three facts are dropped. **A row that ever stopped being
  `active` would simply vanish from his screen**, which is what he is ruling out, and
  the two "did it change" columns exist nowhere at all.

**How to apply.**

- **Never filter a reader on `status`** to decide visibility. A caller that wants only
  the present rows filters explicitly and says so on screen.
- **Carry the record's own metadata into the payload**, beside the schema's fields.
  It is not part of the approved schema and must **not** be merged into `data_json`: a
  fact about our OBSERVATION is not a fact the site published, and this project does
  not edit source truth.
- **"New" and "disappeared" are DERIVED, not stored.** Both are a comparison against
  the most recent crawl, so they are computed for display rather than written into the
  row, where they would be stale the moment the next crawl ran.

---

## Open — awaiting the owner's ruling

Recorded rather than defaulted, per **R-02**.

| # | question | context |
|---|---|---|
| **O-2** | **Does the contractor entity belong in the mbiXaddin workbook** — a `1.TableDefinition` row and its `2.SchemaRule` columns — or is it engine-only until it has proved itself? **HELD 2026-08-21:** put to him with a recommendation and he answered «اترك هذا الامر الان» — leave it for now. Do not define a workbook table for contractors, and do not re-ask until `Q-13` is settled: `R-19` changes how many tabs the export has, which is the shape the workbook would be committing to. | [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| **O-5** | **B1 lists `DELETE /api/views/{id}` among nine dead routes to delete — but building saved views revives it.** Either B1 loses that line, or the new Data page cannot delete a saved view. **HELD 2026-08-16:** he has comments on B1 itself and will raise them first. Do not start B2 step 3 until he has. | [HANDOFF-resume-the-migration.md](HANDOFF-resume-the-migration.md) |
| ~~**O-6**~~ | **ANSWERED 2026-08-20, and none of the three options was the answer.** I asked which machine holds the warehouse, given the home machine has none. He ruled that the premise was wrong: ScrapeX is a tool many people install, so an empty installation is the product's normal first-run state and a warehouse is **per installation**. Create one here and crawl into it; comparing two machines is development, not collection. → **[R-23](#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)** | [OP-22](BACKLOG.md) |

> **O-3 and O-4 may already be answered in practice** by what PR #211 implemented
> — `content_hash` over the normalised `data_json` as the change detector, an
> unchanged contractor moving `last_seen_at` and writing no revision, and history
> kept via `generic_record_revision`. Confirming that is his call to make
> explicit, not ours to assume.

---

### R-51 · The two locales are lined up around a missing box, and no Arabic label is ever read

**Ruled 2026-08-24.** Asked whether another crawl was needed, told no and shown why, he
was offered two options and chose the second: **«نفذ ب»** — build the canonical-position
pairing.

**What he was choosing between.** `merge_locales` refused any pair whose box counts
differed, which held **129 contractors** out of the warehouse with both their pages
already on disk. Option A was to leave them described in `OP-66`. Option B was to line
the two locales up around the missing box.

**The evidence he ruled on, measured over the whole stored corpus:**

| | |
|---|---|
| profile snapshots on disk | 36,358, covering **17,452 distinct ids — the whole union, nothing left to fetch** |
| listing rows with no profile row | **188** — every one with its snapshot stored |
| of those, refused by layer 1 (`OP-64`, the id is dead) | **59** — no crawl can ever fix these |
| refused by `merge_locales` | **129** |
| would approve without a code change | **0** |

**And the option he did NOT get offered, because it was measured and rejected first.**
The obvious repair — tolerate a trailing extra box — is wrong on **24** of the 129. On
those the Arabic page's extra box sits *between* `Region` and `Activity`, so zipping to
the shorter list would have written an Arabic **address** into `activity_ar`. Contractor
`20000713`:

```
    8   EN Region              AR المنطقه
    9   EN Activity            AR عنوان        <-- diverges here, in the MIDDLE
   10   EN     --              AR الخدمة
```

**The ruling, in one line: locate the gap from the English side, never from an Arabic
label.** `PROFILE_FIELDS` is written in the order the page prints its boxes, so an
English label's position in it IS that box's canonical position — and when English omits
a box, which one and where is therefore known without asking what the Arabic box is
called.

**Why that property is load-bearing and not stylistic.** The site spells `المنطقه` with
`ه` where `ة` belongs. A hand-written Arabic vocabulary would have to carry the site's
own typo and would break the day they fix it. `merge_locales` reads Arabic **values**
only, exactly as before.

**What it yields, and what it does not.** 121 of the 129 align; **24 of them also gain
their address**, a field the English page cannot supply for anyone. The other 97 recover
as rows without the extra box's value, because English omits *two* boxes there and which
one Arabic carries cannot be told apart — so it is dropped rather than filed under a
guess. **Eight stayed refused in this implementation**: Arabic is the shorter side, and
which box *Arabic* dropped is precisely what reading no Arabic label leaves unknowable.
**R-83 supersedes only that final-eight case** with a strict observed-label fallback after
the eight pages themselves made the omission measurable.

**Guarded by** `tests/test_the_two_locales_line_up_around_a_missing_box.py`, on two real
page pairs committed as fixtures, and mutation-tested on eleven branches — including each
half of the order/duplicate check separately, because the first version of that test
passed for the wrong reason and a mutant proved it.

**Superseding nothing.** The refusal `R-51` replaces was correct as written; what was
wrong was the conclusion, recorded and then corrected in `OP-66`, that no repair existed.
That first study compared `Reading.fields` — a dict whose order is not the page's — and
reported a gap of +2 and "121 of 121 misaligned". Against the arrays `merge_locales`
actually reads the gap is ±1 on all 129 and nothing is misaligned. `LESSONS` §9 is about
that class of error and this is an instance of it.

---

### R-52 · A generic crawl is a RUN with an identity, not the maximum of a timestamp column

> **SUPERSEDED IN PART on 2026-08-29 by [R-75](#r-75--one-run-table-for-everything-and-a-row-is-read-against-the-run-that-wrote-it),
> and the part that stands is the larger part.** Its principle -- a run has an IDENTITY and a
> maximum timestamp is not one -- is what `R-75` executes. What expired is its *table*
> choice, and it expired on a measurement rather than a change of mind: `crawl_run.source_id`
> pointed at `source_site`, where muqawil did not exist, so a second table was the only way
> to have run identity at all. `R-62`'s merge (`0014`) put `muqawil_org` into `source_site`
> on 2026-08-29, and a second run table became two concepts for one thing -- `R-72`.

**Ruled 2026-08-24.** Shown that three of the eight row states rest on `newest` — the
maximum of `generic_record.last_seen_at` — and offered three ways out, he chose the
second: **«نفذ ب»**, a generic crawl-run table.

**What he was choosing between**, and the measured reason a choice was needed at all
([OP-68](BACKLOG.md#op-68--the-last-crawl-is-a-timestamp-so-17256-of-17304-contractors-are-shown-as-having-disappeared)):

| | change | what it buys |
|---|---|---|
| A | `dataset_sighting` gains `last_run_ref`, and a crawl stamps it | an exact answer for all three states; one migration |
| **B — ruled** | **a generic crawl-run table, started and finished** | the same, **plus a real progress denominator and history** |
| C | leave `new` / `updated` blank until A or B | no false state, and two columns that say nothing |

**The defect this answers.** `newest` is a timestamp to the second and a crawl writes its
rows over half an hour, so only rows written in the final second compare equal to it.
Measured on the live warehouse: **17,256 of 17,304** contractors read `absent` after a
crawl that read every one of them, and **one** profile row read `new` where **121** had
arrived that day. The false sentence is not confined to the screen — `publish.py` turns
every payload column into a workbook column, so *"The most recent crawl did not show this
row"* is written into the Google Sheet the mbiX add-in reads.

**Why nothing stored could answer it.** `crawl_run` is the price path alone — 159 rows,
`source_id` pointing at a price source, nothing for a dataset. `dataset_sighting` carries
`first_run_ref` and `last_absent_run_ref` and no `last_run_ref`. A partitioned listing
crawl is **93 run refs** sharing only a prefix. And `first_seen_at` is an APPROVAL time
while `generic_page_snapshot.captured_at` is a FETCH time — the `R-51` recovery approved
pages fetched two days earlier, so comparing the two would call a two-day-old page new.

**AND `0006` ALREADY REJECTED A TABLE HERE, WHICH IS WHY THIS ONE IS NOT THAT TABLE.**
`db/engine/migrations/0006_a_row_says_when_it_was_last_proved_absent.sql` weighed *"a
`(dataset_key, external_id, run_ref)` table"* — the full attendance register — and refused
it at **17,403 rows per crawl**. What `R-52` adds is **one row per crawl**, not one per
contractor per crawl: three orders of magnitude cheaper, and it answers a different
question. The attendance register stays rejected.

**What it must carry, and why each field is load-bearing rather than nice to have:** the
dataset it crawled, the run ref the operator typed, when it started, when it finished, and
whether it finished at all. `started_at` is what `absent` needs — a row not seen since
before the last run began was not seen by it — and `finished_at` is what makes the answer
honest, because a run still in flight has not failed to see anybody yet. A crawl that
never finished must not be able to declare 17,000 departures.

**And the progress denominator is not a bonus, it is a standing complaint being paid off.**
`docs/STATE.md` records that a generic crawl has no real denominator, so
`declare_frontier` has nothing to divide by. The same table that says when a run began can
say how many pages it expected.

**The half that needed no ruling was fixed under `OP-68` regardless:** `absent` now rests
on the sighting ledger's own `last_absent_at`, which `mark_unavailable` exists to write and
which step 5 already read for `returned`. Measured, the ledger said **0** absent while the
timestamp comparison said 17,256 — so that half was a defect with a right answer, not a
decision, and waiting for a schema to carry it would have left the published lie standing.

---

### R-53 · The profile schema is re-approved onto a clean version, not reopened

**2026-08-26 · data model · he chose option (b) of three measured**

**The state he ruled on**, measured read-only and re-measured independently by a second
pass:

| | |
|---|---|
| live `contractor_profiles` rows bound to schema version 2, marked `retired` | **17,371 of 17,371** |
| ingestions behind the **approved** version 3 | **14** — the impostor pages `OP-64` retired |
| fields the approved version declares | **39** |
| of those, empty on every live row | **12**, every one an `x_*` **listing** key |

So the published contract described fourteen pages while seventeen thousand real ones were
bound to a version marked dead, and **the next field muqawil publishes would have made the
whole page refused rather than recorded** — `R-31`'s subset rule.

**HIS CHOICE: re-approve all 17,371 rows onto a clean 27-field v4.** He was offered the
cheaper route — reopen v2 as approved and retire v3 — and did not take it.

**What the choice buys over the cheap one.** Both remove the 12 phantom columns from the
grid and the workbook and lift the refusal. Only this one leaves a **correct version
history**: no live row on a dead version, and the 14 retired impostor rows do not silently
lose the columns they were approved under. It writes 17,371 rows and 17,371 revisions and
needs **no network** — every snapshot is on disk.

**Why it was ruled first of the four.** It is the only defect in the muqawil set whose cost
grows while attention is elsewhere. Every other one is wrong today and stays equally wrong;
this one waits for muqawil to publish a field, and **muqawil sets that date.**

---

### R-54 · The state column is fixed at its root first: a confirmation moves `last_seen_at`

**2026-08-26 · data model · AMENDS the method of [R-52](#r-52--a-generic-crawl-is-a-run-with-an-identity-and-the-plan-for-it), which stands**

**`R-52` stands. Its plan does not, and this is the `C5` disagreement it was owed** — the
evidence contradicted a ruling, so it is recorded rather than quietly worked around, and
`R-52` is amended rather than erased (`C4`).

**What the audit found and this session re-measured with its own queries:**

| | |
|---|---|
| profile records whose `last_seen_at` reads `2026-08-23` | **17,250** |
| records reading `2026-08-24` | 121 |
| **their memberships** dated `2026-08-24` | **397,526 — every one** |
| **records OLDER than their own memberships** | **17,259** |

The same pass refreshed a row's memberships and never moved the row's own `last_seen_at`,
because `approve_candidate` returns before the upsert when a row is merely confirmed.

**So filling the sighting ledger — which is what `R-52` planned — would have made those
17,250 rows compare an August 23 timestamp against an August 24 run and read `absent`
instead of `unsighted`.** One false state for another, the work spent, the defect surviving,
and **the result looking finished.**

**And the second state is worse than the first, which is why this could not be deferred.**
`unsighted` says *"stored before the ledger existed"* — confusing, and it claims nothing
about the site. **`absent` says the site stopped publishing this contractor**, which is a
false claim about a real company's standing, on 17,250 of them, and `publish.py` carries
every payload column into the Google Sheet the add-in reads.

**HIS CHOICE: the root first.** A confirming pass moves `last_seen_at` on the record; then
state is computed against the **run** that wrote the row rather than against
`MAX(last_seen_at)`. He was offered the ledger-first route with its cost stated and did not
take it.

**Why the root and not the ledger.** `newest` is `MAX(last_seen_at)` to the *second* while a
crawl writes for half an hour, so only the final second ever survived the comparison — and
the reasoning that fixes it was already eight lines below the defect, where `last_absent_at`
uses `>=` *"because both timestamps are `strftime(…,'now')` at SECOND resolution"*. **Any fix
starting from the ledger builds on a field that does not move.**

`R-52`'s own contribution is untouched and is what makes this buildable: a run has an
identity, so *"was this row seen by the last crawl?"* becomes answerable without comparing
timestamps at all.

---

### R-55 · Absence is more honest than a placeholder, and one ruling covers both fields

**2026-08-26 · data and `R-45`'s boundary · he chose one ruling over two**

Two fields store a value the site emits for *everyone*, so the column reports coverage it
does not have:

| field | measured |
|---|---|
| `latitude` / `longitude` | **14,621 of 17,371 (84.2%)** carry the identical pair `24.4493518, 46.6220053` — Riyadh's centre, the site's default pin. It places all of Jizan and Tabuk at one point |
| `logo_url` | **100% non-empty**, and **13,042 of 17,304 (75.4%)** is a directory with no filename |

**Neither is rendered by any consumer**, so this was never about something he sees. It is
about whether a metric tells the truth: a test asking *"is this column populated?"* passes
forever on both.

**HIS CHOICE: one ruling for both — store absence.** NULL for the filename-less directory
and for the default coordinate pair. Coverage becomes an honest **24%** on the logo and
**16%** on coordinates, against 100% and 99.89%.

**This is an extension, not an exception** — and the document that already asked for it
names the wrong string, which is worth knowing before anyone writes the guard.
`CONTRACTOR-SOURCE.md:560` says the site *"falls back to `default.jpg`, which must be stored
as NULL and never as the placeholder"*. **The principle is exactly this ruling. The string is
not in the data: measured 2026-08-26, `default.jpg` appears in ZERO of 17,304 values.** The
real placeholder is the bare directory `https://muqawil.org/public/contractor/companyLogo/`
on **13,042** rows, and the other 4,262 values are 4,262 distinct filenames. **So a guard
written against the documented string would never fire once** — which is the same shape as
everything else in `LESSONS.md` §7: a check that passes because its subject is not what it
is looking for.

The repository has also already applied *absent rather than corrected* to the `lng: 0` case
on 19 rows, so the reasoning has a precedent as well as a document. **`R-45` is not overridden:
we still never edit what the site published about a contractor.** A value the site emits
identically for everyone carries no information about anyone, and recording *"we do not
know"* is not a correction of the site — it is a refusal to claim knowledge we never had.

**The boundary this draws, for the next field like it.** A site-wide constant dressed as a
per-record value is an ABSENCE. A value that differs between records is DATA, however
strange it looks — which is why the nine impossible-but-genuine values in the audit's §4
stay exactly as the site published them.

---

### R-56 · The 263 stranded listing rows are fixed by a fresh listing crawl

> **NOT WAITING ON HIM, and it was filed that way for four days.** Corrected 2026-08-30:
> this crawl has no control in the panel, and [R-81](RULINGS.md#r-81--a-command-line-answer-is-not-an-answer-the-panel-is-the-only-door) records that he never uses a
> terminal. **It waits on `REQ-45`, not on his decision** -- which he made on 2026-08-26.

**2026-08-26 · collection · he chose (c) of four priced options**

**The 263** are active listing rows frozen on retired schema **v1**, missing six keys
including `profile_url`, and **the only rows in the table that never received the
City/Region split** — so `DSN-05` is unmet for precisely these and met for the other
15,577, which partition on `' - '` with **0 anomalies**.

**HIS CHOICE: a fresh listing crawl** — priced at **58 minutes at concurrency 4**, or 2.7
hours serial. It lands all 263 on v2 with their `profile_url` and the split.

**What it buys over the cheaper routes, and the cheaper ones were offered.** Deriving the
six values in place costs zero network and zero refusal — and **leaves the 263 frozen at a
`last_seen_at` of 2026-08-20 while the sighting ledger says the 21st**, which under `R-54`
is exactly the skew we have just ruled must not exist. A crawl refreshes the timestamp as a
side effect of doing the work honestly. Wipe-and-re-approve works in ~20 minutes and
`R-40` says it *"destroys history every time"*.

**And one route must not be attempted:** re-approving the 228 stored snapshots is
**refused** by `ExtractionConflict` and writes nothing, because the parse would add columns.
It is measured, it is in the audit's §7-5, and a session should not spend an afternoon
rediscovering it.
---

### R-57 · A document carries what is needed and consequential, and nothing else

**2026-08-26 · how this system is written**

> «لازم نقلل عدد السطور فى doc ونكتب الى نحتاجه فقط ومؤثر مش حشو على الفادى يستهلك وقت بدون فائدة»

**Measured when he said it:** 73 markdown files, **39,676 lines**, **+7,251 in four days** —
18% of the corpus in four days, most of it this session's. He is the only reader, and he said
it had become hard to review and track.

**The rule.** An entry carries the quote, the number, the choice and the consequence. **Not
the argument defending them.** Prefer a table to a paragraph and a number to an adjective —
then delete the sentence introducing the table. Never state one fact in two documents; cite
the one that owns it.

**The test:** would he act differently if this sentence were deleted? If not, delete it.

**What this does NOT relax.** `C3` and `C7` still compel the entries themselves — brevity
applies to the prose inside a record, never to whether the record exists. `R-15`'s citations
stay. Superseded text stays under `C4`.

**First application is this entry**, at a third of the length the four before it ran to.

---

### R-58 · Drive is the second plan: muqawil finishes first, and its problems with it

**2026-08-26 · sequencing · answers "which plan is live"**

> «هناك خطة drive هى الخطة الثانية بعد الانتهاء من مقاول وحل كل المشاكل»

**One plan is live at a time.** Muqawil is first and is not finished when the crawl ends — it
finishes when the problems the audit found are solved. Then Drive.

| # | plan |
|---|---|
| **1 · LIVE** | muqawil — [2026-08-26-what-remains-of-muqawil.md](plans/2026-08-26-what-remains-of-muqawil.md), whose steps 1–5 are his rulings and 6–10 are not |
| **2** | Drive — branch `claude/drive-without-a-server` at `e00711d`, pushed, **no PR since 2026-08-22** |
| 3+ | the rest, ordered rather than all marked `LIVE`. Seven were `LIVE` at once when he ruled, which meant none of them was the plan |

---

### R-59 · The palette registry: `brand` is default, `alternatives` is extensible, teal is debt

**2026-08-09 · design system · rescued 2026-08-27 from a file nothing linked ·
decision 1 ~~active~~ SUPERSEDED 2026-08-28 by [R-73](#r-73--an-appearance-is-a-whole-design-system-and-supabase-is-the-default-one)**

**Decision 1 only.** `brand` is no longer the default palette — `supabase` is. Decisions
2–6 are untouched and still govern: teal is still debt, the aliases still stand, components
still consume roles, and `R-73` builds the extensible `alternatives` collection that
decision 1 asked for rather than abandoning it. Per **C4** the original text below stays
exactly as it was recorded.

Six decisions of his lived **only** in `docs/design-system/SCRAPEX_GLOBAL_MAPPING.md` —
zero in-links, and not one of them named in `RULINGS`, `BACKLOG` or `LESSONS`. That breaks
`C3`, so they are recorded here and the file is deleted.

1. **`brand` is the default palette.** `alternatives` is an extensible collection, `blue` is
   its first entry, every palette carries `light` and `dark`. **Device/System picks the
   scheme; it is not a palette.**
2. **Teal is deprecated** — legacy colour residue and migration debt, not brand and not a
   future palette.
3. **`whatsapp` and `github` are legacy compatibility aliases** for `brand` and `blue`.
4. **Components consume semantic roles** — `accent`, `on-accent`, `surface`, `on-surface` —
   and never a palette identifier.
5. **Shared inside ScrapeX is not a global mbiX contract.** Copied CSS/JS and ScrapeX
   endpoints are an internal layer; only what is reusable beyond ScrapeX is a candidate.
6. **The FastAPI/Jinja surfaces are an explicit LOCAL-WEB profile.**

**Decisions 1 and 3 were half-built for nineteen days:** `scrapex/webui/app.py` refused any
palette outside `{"whatsapp", "github"}` — the aliases were enforced and the registry they
alias did not exist. Registered as `OP-82`, **and built on 2026-08-28 by
[R-73](#r-73--an-appearance-is-a-whole-design-system-and-supabase-is-the-default-one)**,
which closed `OP-82`. The keys are `brand`, `blue` and `supabase`; the two legacy names are
resolved in `normalize()` and canonicalised server-side, and a test compares the two
surfaces' registries because a divergence between them is silent.

**Not carried:** that file's §11 listed ten questions pending the *other* products' audits.
They are mbiXaddin's and mbiXsite's to answer, not this repository's. `git show
d6f4967:docs/design-system/SCRAPEX_GLOBAL_MAPPING.md` has them.

---

### R-60 · A finished document leaves the tree, and git is the archive

**2026-08-27 · documentation · four answers in one sitting, and one earlier instruction lifted**

> «اريد منك مراجعة ملفات md ملف تلو الاخر بحيث نقلص عدد السطور ونحذف ما تم او نشيل الملفات المتعارضة»

**The rule.** A document stays in the working tree only if a session will open it. What is
finished is retrievable with `git show <commit>:<path>`, and the register entry that cited it
names the commit. **An `archive/` folder is not an archive** — it still ships, still greps,
still appears in every inventory, and still asks the reader to decide whether it matters.

| his answer | what it settles |
|---|---|
| **cut `MASTER-PLAN.md` to §8.3** | it cannot be deleted — §8.3 is cited from `extension/app.html`, `app.js`, `releases.js` and `tests/test_panel_dom.py`. 523 → 39 lines, that section verbatim |
| **delete the archived 2026-08-05 plan** | **this lifts his own earlier instruction** to archive rather than delete it. `PLATFORM-PLAN.md` §2 and §7 record what replaced it; 965 lines left the tree |
| **read the eight `LIVE` plans and fold the older muqawil ones** | `plans/README.md` said *"one plan is live at a time"* three lines above a table marking **eight** |
| **delete `PLAN.md`, `plan-closing-the-gaps.md`, `REVIEW-2026-07-28.md`** | conditional on proving their live items survive: all twelve do, by number |

**Two limits this ruling does not cross.** `C4` still keeps a superseded ruling in place, and
`C7` still keeps a Done request on the board — **brevity applies to the prose inside an entry,
never to whether the entry exists** ([R-57](#r-57--a-document-carries-what-is-consequential-and-nothing-else)).
And a document that shipping code or a test reads is not prose: `docs/reviews/mbiXaddin-config-contract-20260812.md`
is 1,709 lines and stays, because `contract/addin-contract.json`, four `extension/*-rules.js`
files and `tests/test_the_addin_contract_cannot_drift.py` read it. **The test is whether
something reads it, not how long it is.**

---

### R-62 · One source registry: `site_profile` merges into `source_site` — and `Q-24` is answered by that migration

**2026-08-27 · data model · he chose the merge over teaching `POST /api/jobs` two registries, which is what I recommended · answers [REQ-25](REQUESTS.md#req-25--one-source-registry-with-a-category-visible-to-every-user) and `Q-24`**

**The defect it closes:** `POST /api/jobs` validates a key against `sources.yaml` — 12 price
sources — and muqawil lives in `site_profile`, so the crawl button answers 404 and the panel
hides it. **Every read route already resolves both**: `/api/table`, `/api/fields`, and now
`/api/dry/{source_key}`.

**HIS CHOICE: one registry.** I recommended teaching `POST /api/jobs` the other two, riding
on `R-52`'s `dataset_crawl`; he took the migration instead.

**And measuring it for this entry showed my cost estimate was too high, which is worth
recording because it changes the schedule:**

| | |
|---|---|
| rows to move | **2** — `site_profile` holds two, `source_site` twelve |
| tables pointing at `site_profile` | **2** — `dataset_definition.site_profile_id`, `dataset_relationship.site_profile_id` |
| rows to repoint | **3** in `dataset_definition`, plus `dataset_relationship` |
| columns to carry across | `crawl_scope`, `crawl_slice` (migration `0003`), `price_source_key`, `lifecycle` |
| **`price_observation`** | **untouched — 94,664 rows and it does not reference `source_site`** |

I had said it *"touches the working price path"*. It does not: `crawl_run`,
`feed_assignment` and `source_product` reference `source_site` and none of them gains or
loses a row by adding two.

**`Q-24` is answered inside it: id 1 (`muqawil`) closes, id 2 (`muqawil_org`) survives.** The
data is on id 2 — 34,675 active rows against zero — `scrapex contractors` names it, and
`#274`'s dry route resolves it. Closed with `valid_to`, never deleted.

**One fact the merge must carry, found while measuring:** both rows read
`lifecycle = 'draft'`. **Neither registry row is `active`**, so whatever the merge writes must
decide that too rather than copying `draft` into the new table and calling it done.

---

### R-63 · A dataset's overview shows the tiles its kind has

**2026-08-27 · surface · answers `Q-26`, and he took the recommendation**

`/source/contractors` prints `Products 4 · Variants 0 · Data rows 4 · Matched 0` — measured on
a real render. **Three of the four are price-path concepts a company has none of, and the
fourth repeats the first.**

**HIS CHOICE: the tile SET follows the kind.** A dataset shows its row count and how much has
been fetched; a price source keeps all four. Half a day.

**Why not the one-line rename, which was offered:** `Products` → `Rows` reads as finished and
leaves two wrong tiles standing. **And `0` is the specific harm** — it reads as a measured
zero rather than *"not a thing this source has"*, which is the distinction
`last_successful_run` already documents for a crawl that never ran.

`CLAUDE.md` names two more categories coming (`jobs`, `tenders`), so a set that follows the
kind is not a premature abstraction.

---

### R-64 · A migration reaches his warehouse only after it is on `main`, and no tag is cut while his warehouse is ahead

**2026-08-27 · process · answers `Q-15`, open since it was asked · both guards approved**

**It happened twice before he ruled.** `0007`/`0008` on 2026-08-21 (`OP-33`) and `0011`/`0012`
today, both applied to his live warehouse from an unmerged branch. **Proved by running, not
by reading:**

```
$ python -m scrapex.cli database-status
"ok": false,
"status": "Needs a newer ScrapeX",
"action": "This database was written by a later version (schema v12; this build reads v10)."
```

**HIS RULING: no.** A migration reaches his warehouse only after it is on `main`. A session
testing one uses a copy.

**And a backup is not the protection**, which is why the weaker option was refused: the
`pre-ledger-repair` and `pre-reapprove` backups exist on disk from both incidents. **A backup
protects the data; it does nothing about the warehouse getting ahead of the engine.**

**HE APPROVED BOTH GUARDS**, because `OP-33` was closed by a merge and not by a guard, and
that is exactly why the class returned. **Both are BUILT, in #276:**

1. **In CI** — `release-engine.yml` asks GitHub for branches whose migration ceiling exceeds
   `main`'s and **refuses, naming them**. It is the only place that can see across branches,
   and the workflow already makes network calls. Mutation: a fake higher branch must turn it red.
2. **At runtime** — refuse to cut a tag while the local warehouse is ahead of the code. It
   catches the same fault late, on his machine, where CI cannot see.

**And the immediate consequence he ruled on:** `#274` merges, **no tag is cut** until
`0011`/`0012` are on `main`, and `feat/organization-enrichment` — 7,832 lines in 44 files,
no pull request ever opened, and it edits both the citation guard and the register-collision
guard — **is read and reported before anything of it merges.** Registered as `OP-84`.

---

### R-65 · Every open question is put to him with what he needs to decide, and the recommendation goes first

**2026-08-27 · process · his instruction**

> «انا اريد الرد على كل الاسئلة ولا اريد تعليق اسئلة مرة اخرى دائما اعرض عليا السؤال موضح
> بالتفاصيل اللازمة لاتخاذ القرار وضع الاختيار الموصى من وجهة نظرك اول اختيار»

**Three obligations, and the third is the one that was being failed:**

1. **No question is left hanging.** A question filed and not put to him is not asked. `REQ-04`
   sat ruled and unbuilt for sixteen days; `Q-15` was asked and unanswered while the thing it
   asks about happened **twice**.
2. **The question carries what the decision needs** — the measured numbers, the cost of each
   option, and what each one forecloses. Not a summary that makes him ask for the numbers.
3. **The recommendation is first, and it is mine, stated as mine.** He overruled two of four
   on the day he gave this instruction, which is the point: a recommendation he can reject is
   worth more than a neutral list, and it must be labelled so rejecting it is one word.

**This does not soften `R-02`:** an un-computable mapping is still his call, and he may refuse
to rule until studies are measured. What changes is that the asking is not optional and not
deferred.

---

### R-66 · Every outbound-request knob is a setting the user controls, and robots is one of them

**2026-08-27 · architecture · he refused all three options I offered and gave a wider rule**

> «اريد ربطهم باعدادات بحيث يكون المستخدم متحكم تحكما كاملا فى هذا النقطة بالاضافة الى
> robot.txt معهم · اريد توفير كل المفاتيح للمستخدم وولمستخدم القرار»

I asked *which component should own outbound requests* — accept the second owner, route it
through `pacegovernor`, or route both. **He answered a different question: it does not matter
who owns the request, it matters that the user owns the knob.** Which is `R-21` arriving from
the other side, and it is consistent with his standing rule that every setting moves to the
extension.

**The current state, measured — two owners, and they do not obey the same things:**

| | `HttpFetcher` (`connectors/base.py:216`) — prices **and** muqawil | the enrichment website provider |
|---|---|---|
| pace per host | `crawl_min_interval_s`, default **1.0 s** | `SCRAPEX_WEBSITE_MIN_INTERVAL_MS`, default **250 ms** — four times faster |
| reads his settings | **yes** | **no — environment variables only** |
| robots | `crawl_honour_delay`, `crawl_obey_disallow` | its own `RobotFileParser`, no setting |
| user agent | `crawl_user_agent` | not configurable |
| SSRF / private peers | **none** | refuses private peers, off-domain redirects, HTTPS downgrades |

**The ten keys his ruling names.** One exists and is hidden, three are environment variables,
and the rest are literals with no key at all:

| key | today | after |
|---|---|---|
| `crawl_obey_disallow` | **exists in code, no surface on either side** — `OP-86` | a setting |
| `SCRAPEX_WEBSITE_MIN_INTERVAL_MS` (250) | env var | a setting |
| `SCRAPEX_DNS_TIMEOUT_SECONDS` (3) | env var | a setting |
| `SCRAPEX_GOOGLE_PLACES_QPS` (5) | env var | a setting |
| `httpx.Timeout(12.0, connect=6.0)` | literal | a setting, or `crawl_timeout_s` |
| `max_bytes` 2,000,000 / 512,000 | literals | a setting |
| `max_keepalive_connections=0` | literal | a setting, or documented as fixed with its reason |
| `crawl_honour_delay` · `crawl_obey_disallow` · `crawl_user_agent` | the provider ignores all three | the provider reads them |

**Four are already surfaced on both sides** — `crawl_min_interval_s`, `crawl_honour_delay`,
`crawl_timeout_s`, `crawl_user_agent` — and `crawl_parallel_sources` in the extension only.
So the work is smaller than the rule sounds: **the shape exists, and the second owner is
outside it.**

**What this does NOT settle:** whether `pacegovernor.py` is ever wired. It is written in full
— `Strain`, `HostPace`, `pace_for`, `concurrency`, `owed_wait_s`, `record` — with **zero
callers in production**, so `R-21`'s adaptive half is still dead code and still owed. Binding
the knobs does not build the adaptive governor; it makes the fixed values honest first.

**And one thing a setting must not become:** a knob that lets a user turn politeness off
silently. `capture.py:88` already records the shape — *"absent reads as HONOUR — silence must
mean the polite thing"* — and every new key follows it. `SR-8` and `R-21` are not weakened by
being configurable; they are weakened by a default that is not the polite one.

---

### R-67 · `HttpFetcher` gains the SSRF protections the newer provider already has

**2026-08-27 · security · he took the recommendation**

**Measured, and it is the surprise that reframed the ownership question:** `HttpFetcher` —
the old owner, driving the price connectors and muqawil — has **zero** references to
`ipaddress`, `is_private` or a peer check. The enrichment provider has all of them, and its
live run refused **64** off-domain redirects and **10** HTTPS downgrades in 98 minutes.

**So unifying downward would have LOST protection**, which is why this is a separate ruling
rather than a consequence of the ownership one: the old owner is upgraded to the new one's
level whatever is decided about who owns the request.

**What ports across:** refuse a private or loopback peer, refuse a redirect that leaves the
target's own domain, refuse an HTTPS→HTTP downgrade, cap the response body.

**Why it is worth doing even though the price sources are known.** They are listed in
`sources.yaml` and low risk. **The risk is not the listed host — it is a link on a page the
crawl already fetched**, which is exactly how the enrichment provider found 64 of them.
`HttpFetcher` follows redirects for hosts it was pointed at by stored HTML, and nothing
checks where they land.

---

### R-68 · The two crawls reconcile themselves at the end of every crawl, in both directions

**2026-08-27 · collection · answers [REQ-41](REQUESTS.md#req-41--the-two-crawls-disagree-so-the-code-must-reconcile-them-itself), the last step that was waiting on him**

> «لازم الكود لو لاقى مقاول مش موجود فى profile **يجيبه**، مقاول مش فى listing **يجيبه**»

| | measured |
|---|---|
| have a profile, no listing row | **148 — zero network, their pages are on disk** |
| have a listing row, no profile | **35**, and up to 81 counting step 7's unsearched side |
| why they disagree at all | the listing **reorders under the crawl** — 4,556 contractors appeared on more than one page in a single pass |

**So the drift is structural, not a defect.** Any two passes separated in time read two
different arrangements of one site; ours were separated by two days. That is why he refused to
have the 183 fixed and asked for the reconciliation to live in the code.

**HIS CHOICE: automatic at the end of every crawl, both directions.** He was offered the split
— free side automatic, fetching side by command — and did not take it. **His words name the
fetch explicitly**, twice, and *"a command a person runs"* is the session doing it that he
objected to: *«كل مستخدم هيلاقى اختلافات»*, and no other user has a session.

**The one constraint the build must carry:** the fetching side is bounded and **reports what it
did inside the crawl's own report**, so a reconciliation can never become silent extra
requests. `R-21` and `SR-8` are not weakened by being automatic; they are weakened by being
unreported.

---

### R-69 · The build order for the four unblocked muqawil steps, and `0.4.1` stands

**2026-08-27 · sequencing · two answers recorded together because one is a consequence of the other**

**Order: step 1 → 2 → 5 → 3.** Step 1 first because it is the only defect in the set **whose
cost grows while attention is elsewhere** — the next field muqawil publishes makes the whole
page refused (`R-53`). Then the State column (`R-54`, the loudest false publication: 34,364 of
34,689 rows). Then the placeholder pair (`R-55`, zero network). **Step 3 last because it is the
only one that waits on a 58-minute crawl** (`R-56`).

He was offered the state column first, and the batch-of-three, and took neither. The
batch-of-three was offered with its own risk stated: three changes to the approval and state
paths in one pull request make a failing mutation harder to attribute, which is `OP-18`'s
lesson.

**And `0.4.1` stands on `main`** for migrations `0011`/`0012`. The gate proved the contract
includes the migration list, so `VERSION` had to move; PATCH describes it because the twelve
tables have **no reader on `main` at all**, so no capability became reachable. **It also leaves
`0.5.0` exactly where he put it** — on `feat/organization-enrichment` — rather than renumbering
his own ruling as a side effect of a fix. He was offered `0.5.0` here with `0.6.0` for the
branch and kept `0.4.1`.

### R-70 · `0013` reaches his warehouse through the engine's own upgrade path, and step 1 is applied after he reads the dry run

**2026-08-27 · two decisions recorded together because the second waited on the first**

**How the migration arrives: move the main checkout to `main`, then restart the engine.** He
was shown that his warehouse sat at `user_version 12` while `main` was at `13`, and was
offered three routes. He took the one that uses **his own designed path** — `scrapex ui` finds
a warehouse that is only *behind*, copies it first, then migrates
([cli.py:779](../scrapex/cli.py:779), his decision of 2026-08-05). It ran exactly as written:

```
backed up the engine database to scrapex-engine.pre-upgrade-20260827T125628Z.backup.db
  before upgrading
upgraded the engine database: applied [13]
```

He was offered, and refused, applying `0013` from a worktree by hand — because that leaves the
warehouse ahead of the checkout the engine reads, which is the same fault one version wider.

**What the offer got wrong, recorded per `C5`.** It said the main checkout was why the engine
could not restart. The engine was not reading the main checkout at all — it was serving from
an unmerged worktree (`OP-88`). Moving the checkout was still required for the next launch to
be correct, but the reason given for it was not the reason.

**Step 1: dry first, then `--repair`.** He read the dry run against his own warehouse — 12
`x_*` fields dropped, 17,371 records moving, 0 revisions — and then said run it. Applied and
verified on a second read-only connection: `v4` approved with 27 fields and 17,371 `active`
rows, **zero active rows on a retired version**, `OP-64`'s 14 impostors still on `v3` and still
`status='retired'`, 74,574 revisions unchanged, `foreign_key_check` clean.

### R-71 · The merged registry's shape — and the crawl button is not what the merge unblocks

**2026-08-29 · data model · three decisions taken while executing
[R-62](#r-62--one-source-registry-site_profile-merges-into-source_site--and-q-24-is-answered-by-that-migration),
plus the `C5` correction that measuring it produced**

`R-62` said merge; it did not say what the merged row looks like. Three questions had no
computable answer:

| question | his answer |
|---|---|
| `source_name_ar` is `NOT NULL` and neither muqawil row has an Arabic name anywhere | **«الهيئة السعودية للمقاولين»** |
| two ideas of state — `active` (0/1) and `lifecycle` (draft/active/paused) | **`lifecycle` alone.** `active = 0` cannot tell "never configured" from "you switched it off", and both muqawil rows were `draft` |
| the migration alone does not open the crawl button — what ships together? | **the migration and the rename now; the button in its own pull request** |

**AND `R-62` IS WRONG ABOUT TWO THINGS. The ruling stands; its measurements do not** (`C4` —
the old text stays):

1. **It priced the repointing at two tables. It is four.** `classification_scheme` was
   missed, and `organization_enrichment_definition` did not exist when the ruling was
   written. Eight rows, all pointing at `site_profile_id = 2`.
2. **"It is what unblocks `REQ-45`" is measured false.** `POST /api/jobs` validates against
   `load_manifest(sources.yaml)` — a FILE. And opening the route would be worse than leaving
   it shut: the worker is manifest-driven end to end, and `crawl_job.job_kind` is stored but
   **never read in `scrapex/jobs.py`**. A muqawil key would be accepted, queued, and fail
   inside the run. **A clear `404` replaced by a delayed failure is a regression**, so the
   button is `REQ-45`'s own work — `OP-92`.

### R-72 · Nothing is kept because deleting it is work

**2026-08-29 · process · his ruling, given while `0062` was being written**

> «انا اريد كود نظيف لا معكرونة اسبجتى تعيق التطوير بسبب المجهود المضاعف فى تطوير اشياء لا
> نحتاج اليها» — and the question that opened it: *why keep files this long if the decision
> already points at deleting them?*

**He was right about the specific thing in front of him.** `db/migrations/` had not moved
since **2026-08-04**, four days before `db/engine/` was created. Frozen, but alive enough
that the registry merge had to be written TWICE — `0014` for the engine and `0062` for it.
`0062` was an hour old when he ruled, and it was deleted with the stream it was written for.

**What went, and what the deletion cost:**

| | |
|---|---|
| `db/migrations/` | 61 files |
| `db/schema.sql` | 480 lines |
| a duplicate migration runner in `scrapex/db.py` | 47 lines |
| tests guarding deleted migrations | 5 tests, 134 lines |
| **test fixtures moved** | **none** — `db.migrate` DELEGATES to the engine runner rather than owning a stream |

**Why delegating rather than repointing.** The two runners were the same recipe with one
difference: the engine's writes the `database_migration` ledger and this one never did. A
database advanced by the old runner would carry `user_version = 15` and an empty ledger, and
`_verify_checksums` would refuse to open it — a database the product created and could not
read.

**What made the deletion safe was already in the repository.** `db/engine/schema.sql` was
DERIVED from both streams at the collapse, and `test_one_schema_carries_both_streams.py`
holds it against a frozen record of all 134 objects they produced. The proof that nothing
structural is lost was written the day the streams merged.

**Measured before deleting, because two real databases still use the old shape:**
`~/.scrapex/marketlens/marketlens.db` at `user_version 59` and `general.db` at 3. They can
no longer be UPGRADED — and they can still be read and imported: `carry_over.py` contains
zero references to the stream. His price data has been in the engine since the collapse
(94,664 observations, 9,270 products).

**AND THE DELETION FOUND THREE DEFECTS THAT THE DUPLICATION HAD BEEN HIDING**, all in
`LESSONS` §23. Every one was invisible because the tests were building the wrong database.
---

### R-73 · An appearance is a whole design system, and `supabase` is the default one
**2026-08-28 · design system · supersedes [R-59](#r-59--the-palette-registry-brand-is-default-alternatives-is-extensible-teal-is-debt) decision 1 only**

> «اريد عمل apperance جديد اسميه supbase ويصبح default · ولكن لن يكون الوان فقط بل design
> system كامل · https://supabase.com/design-system · على tree جديدة»
> — [REQ-48](REQUESTS.md#req-48--a-supabase-appearance-that-is-a-whole-design-system-and-the-default)

Four questions were put to him with the measurement behind each, because three of them
walked into something already decided. He answered all four.

#### 1 · The id is `supabase`, spelled correctly

He wrote `supbase` in the request and linked `supabase.com`; asked which spelling was
canonical, he chose **`supabase`**. It is not cosmetic — the id is written to
`localStorage`, sent over `POST /api/appearance`, validated server-side, set as
`data-palette` on the root element, and used in screenshot filenames, so a later correction
would break stored preferences. Recorded before it was typed anywhere.

#### 2 · «كامل» means the tokens AND the component rules

Measured and put to him: `THEME_PROPERTIES` in `design/appearance.js` is **36 entries and
all 36 are colours.** Radius, font, type scale, spacing, elevation, duration and easing live
in `design/tokens.css` as `:root` values that **no appearance choice can reach.** So *"not
colours only"* could not be satisfied by a third row in `PALETTES`.

Offered three depths — colour only, colour plus a new token axis, or both plus rewriting the
component rules — **he chose the deepest: «الكامل: التوكنز + قواعد المكونات».**

So the work is: a second axis on the appearance engine so an appearance carries shape,
typography, elevation, spacing and motion; **and** the component anatomy in
`design/components.css` restyled to match. Decision 4 of `R-59` is unaffected and binding
throughout — components consume semantic roles, never a palette identifier.

> **~~The axis~~ SUPERSEDED THE SAME DAY by
> [R-74](#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour).**
> A per-palette axis puts the design system in **one palette**, and measured on the engine
> this section produced, that is what it did: `supabase` got all nine design properties and
> `whatsapp`, `github` and device colours got none, falling back to the pre-Supabase 9px
> radius, 14px body and Segoe UI. Three of four colour choices. The design system belongs in
> `design/tokens.css`, where every choice reaches it. **The half of this section that stands
> is the component rules** — that work is untouched, and it is what lets the baseline reach
> anything at all.

#### 3 · Whether a new user actually SEES it is still his call

`DEFAULTS` is `{mode: "device", scheme: "light", palette: "github", deviceColors: true}`,
and `apply()` returns early on the `deviceColors` branch after `clearTheme(root)` — no
`data-palette`, no custom properties. **So `github` has never been the default anybody saw**,
and neither would `supabase` be from a rename alone. A fresh user gets `tokens.css`'s `:root`
teal — the residue `R-59` decision 2 calls debt — or the OS `AccentColor` where the browser
exposes one.

Asked whether to flip `deviceColors` to `false` so the default is real, **he asked for the
numbers first: «قوله لى بالأرقام الأول».** They were measured over `normalize()`'s own
precedence rather than estimated:

| | |
|---|---|
| stored states that change | **1 of 8** — only "no stored preference at all" |
| preserved | every state that ever expressed a choice, including a legacy `v1` record with neither key, which still derives from `mode` |
| migration | **none** — `normalize()` already resolves every stored shape |
| server | **none** — `_appearance_value` has no defaults, `GET` returns `null` when unset |
| tests pinning the old default | **one line.** The other nine `deviceColors` references in `tests/` all set the value explicitly |

**He then chose the flip**, so `DEFAULTS.deviceColors` is `false` and `supabase` is what a
fresh install paints. *"Device colours"* remains available and is one click away in the
panel — this changed which way the switch starts, not whether it exists.

**And it closes a second thing nobody asked about.** What a fresh user actually got was
`tokens.css`'s `:root` teal — the residue decision 2 above calls *"deprecated ... migration
debt"* — or the operating system's `AccentColor` where the browser exposes one. **The
deprecated colour was the shipped default, not a leftover.**

#### 4 · The conflict with `R-59` is removed rather than left standing

His instruction: **«امسح التعارض الغرض الحصول على تعديلات»** — clear the conflict; the point
is to get the change made.

So the code stops contradicting the register. `R-59` decision 3 made `whatsapp` and `github`
legacy aliases for `brand` and `blue`, and decision 1 made `alternatives` extensible; neither
was ever built, which is [OP-82](BACKLOG.md) — `scrapex/webui/app.py` refuses any palette
outside `{"whatsapp", "github"}`, enforcing a compatibility layer over a registry that does
not exist. **R-73 builds that registry and closes `OP-82`**, so adding an appearance after
this one costs nothing.

**One thing is deliberately NOT erased.** «امسح» is read as *clear the conflict*, not *delete
the ruling*: **C4** is his own rule and it says a superseded ruling stays, marked, pointing at
its replacement. `R-59` is therefore intact above with decision 1 struck and this entry named,
and decisions 2–6 still active. Erasing it would have hidden why `brand` was ever the default
from the next session to ask.

---

### R-74 · The design system is Supabase's, always, and a palette may change nothing but colour

> **THE COMMIT THAT SHIPPED THIS SAYS `R-72`.** `#283`'s merged title carries the wrong
> ruling number -- the branch was opened while `R-72` was the newest ruling and the title
> was never corrected before merge. The content is `R-73` and `R-74`. Recorded rather than
> rewritten: history stays as it happened, and a reader searching git for `R-74` who finds
> nothing needs to be told why.
**2026-08-28 · design system · GENERAL — «واى تعارض معاها يلغى» · amends
[R-73](#r-73--an-appearance-is-a-whole-design-system-and-supabase-is-the-default-one) §2 and
discharges [R-59](#r-59--the-palette-registry-brand-is-default-alternatives-is-extensible-teal-is-debt)
decision 2**

> «نقطة مهمة ضعها قرار واى تعارض معاها يلغى فهذا تحديث عام
> · اولا supabase design system هو default للبراندى اما واتساب وجيت هب فهى الوان يمكن
> اختيارها ولكنها لا تعبر عن brand
> · design system اعنيها كاملة بكل جوانبه وفروعه
> · whatsapp, github الوان theme يمكن اختيارها بواسطة المستخدم فتعدل على الالوان فقط لا تعدل
> على design system
> · يعنى design system هو supabase ولكن قد ضفنا له استثناء 3 palette الوان واتساب وجت هب و
> device»

**He labelled this himself: a general update, and anything that conflicts with it is
cancelled.** It is recorded before the code changes, because the code it corrects is code
this repository shipped hours earlier.

#### The rule, in four parts

1. **The Supabase design system is THE design system.** Not an option, not a palette, not one
   entry among three. It is the baseline every surface is drawn on — *«كاملة بكل جوانبه
   وفروعه»*: complete, in every aspect and every branch. Shape, typography, spacing,
   elevation, motion, focus geometry.
2. **The only thing a user chooses is COLOUR.** Four options, and `supabase` is the default:
   `supabase`, `whatsapp`, `github`, `device`.
3. **`whatsapp` and `github` are colour themes and do not represent the brand.** *«لا تعبر عن
   brand»*. They change colours. They **must not** change the design system.
4. **`device` is on the same footing** — it swaps colours for the operating system's, and the
   design system underneath it does not move.

#### What was wrong, measured before this was written

`R-73` built the opposite architecture: a **per-palette** design axis, where an appearance
*could* carry shape and typography. Because only `supabase` declared a `design` block, the
other three fell back to `design/tokens.css` — which still held the pre-Supabase shape and
type. Run against the built engine on 2026-08-28:

| colour choice | design properties applied |
|---|---|
| `supabase` | radius, fs, fw-regular, fw-heavy, font, shadow, dur, ease, focus-ring — **9 of 9** |
| `whatsapp` (`brand`) | **none** — fell back to the old 9px radius, 14px body, 400/700 weights, Segoe UI |
| `github` (`blue`) | **none** — same |
| **device colours** | **none** — same |

**Three of the four colour choices lost the design system entirely**, and device colours is
the one a fresh install would have used had the flip not landed. That is precisely what part
3 forbids, and it is why this ruling exists.

#### What it changes in the code

- **`design/tokens.css` becomes the Supabase design system.** Its `:root` carries Supabase's
  shape, typography, motion, focus geometry and elevation, and its dark blocks carry
  Supabase's dark elevation. Every colour choice — including `device`, which applies no
  palette at all — therefore sits on it.
- **`DESIGN_PROPERTIES` and `designFor()` are removed.** A mechanism whose entire purpose was
  *"a palette may carry a design system"* conflicts with part 3, and *«واى تعارض معاها يلغى»*
  cancels it. `R-73` §2's axis is amended, not the request behind it: *«لن يكون الوان فقط»*
  is satisfied **better** by putting the design system in the baseline than by letting each
  palette carry its own.
- **A guard replaces it, inverted.** Instead of a list of non-colour properties a palette
  *may* set, a test asserts a palette entry may contain **nothing but colour**. The ruling
  becomes unbreakable rather than merely documented.
- **The `supabase` palette entry stops duplicating the baseline.** Its colours *are* the
  `:root` colours, so it declares none and exists to be selectable and to name itself in
  `data-palette`. `brand` and `blue` stay exactly what they are: colour overrides.

#### And it discharges `R-59` decision 2

Decision 2 called the teal *"deprecated — legacy colour residue and migration debt, not brand
and not a future palette."* It survived because it was the `:root` fallback and therefore
what a fresh user actually saw. Under this ruling `:root` becomes Supabase, so **the teal is
deleted rather than deprecated.** The debt is paid, not re-registered.

#### What this ruling does NOT touch

The three Sign-in-with-Google values and that button's fixed type size stay outside every
appearance's reach — Google's branding rules, and their own guard. `--sp-*`,
`--control-height*` and `--touch-target` keep the panel's 48px floor. `R-59` decision 4 still
governs: components consume semantic roles, never a palette identifier.

### R-75 · One run table for everything, and a row is read against the run that wrote it

**2026-08-29 · data model · `R-54`'s second half, and the decision `R-52` made on a
measurement that has since expired**

`R-54` said state must be computed against the crawl that wrote a row, not against
`MAX(last_seen_at)` over the whole dataset. Its root half shipped in `#281`. This is the
other half, and it needed a field that did not exist. Three questions had no computable
answer and he ruled on each:

| question | his answer |
|---|---|
| a new run table for generic crawls, as `R-52` chose, or `crawl_run` | **«استعمِل crawl_run نفسَه — شوطٌ واحدٌ للكلّ»** — one run table for everything |
| what state does a row stored before run identity existed get | **`unsighted`** — a standing state meaning "stored before the ledger", not `absent` |
| the migration and the state column together, or separately | **one request** |

**`R-52` IS NOT WRONG; ITS MEASUREMENT EXPIRED** (`C4` — its text stays). Its own words
were *"`crawl_run` is the price path alone — its `source_id` points at a price source,
nothing for a dataset."* That was true on 2026-08-24. `R-62`'s registry merge (`0014`) put
`muqawil_org` into `source_site`, so `crawl_run.source_id` resolves for a dataset source
like any other — and a second run table would then be exactly what `R-72` forbids: two
concepts for one thing, which is what the duplicated migration stream cost all day.

**AND THE OBVIOUS SHORTCUT WAS MEASURED AND REFUSED.** `crawl_run_ref` already sits on
every snapshot and looks like a run identity. Measured on his warehouse before a line was
written: 141 distinct values across 55,313 snapshots, granularity **per partition cell**
for a listing crawl and **per crawl** for a profile crawl, one stored value literally
`'R'`, and **zero** of them join to `crawl_run` or `crawl_job`. Simulated against it, the
State column would have read `absent` on 17,030 of 17,304 listing rows and 17,384 of
17,385 profile rows — worse than the defect. `#282` recorded that; `0016` adds a typed
`run_id` beside the label rather than overloading it, and the label stays because
`--run-ref` is how an interrupted crawl resumes.

**THE LATEST RUN IS ASKED THROUGH THE ROWS, NOT OFF THE SOURCE**, and the difference is
load-bearing rather than stylistic. A listing sweep stores no profile page, so
`MAX(run_id)` for the source would call every profile row `absent` the moment a listing
crawl finished — while the site still lists every one of them. `runs.latest_run_for` asks
for the newest run among the snapshots this dataset's records actually point at.

### R-76 · The backup deadline is raised from a measurement, and the rebuild that would end it is deferred

**2026-08-29 · the panel/engine seam · `OP-100`**

He pressed "Back up to Drive", was told the request had exceeded a 10-second deadline, and
asked for the problem to be analysed. Shown the cause and three options, he chose **(b) and
(c) now** and **deferred (a)**:

| option | his call |
|---|---|
| **(a)** make the build asynchronous — `POST` returns at once, the panel polls for progress | **deferred** — named as the real fix, not done here |
| **(b)** a named deadline policy for `POST /api/bundle` | **now** |
| **(c)** a lock against concurrent builds, bounded local retention, orphan-staging sweep | **now** |

**THE DEFERRAL IS THE HALF THAT HAD TO BE WRITTEN DOWN** (`C4`, `C5`). A raised deadline on
a still-synchronous route reads like a solved problem, and the next session that finds a
named `bundleBuild` policy will assume it was sized correctly. It was sized from a
measurement **and that measurement expires**:

* 104 s measured at a 1,490 MB warehouse, 2026-08-29. `600000` is **5.8×** that, covering a
  warehouse near 8.5 GB — more than the machine has free, so the disk runs out before the
  deadline does.
* The warehouse grew **13× in 17 days**. Whatever number is chosen, the growth curve eats
  it; (b) is a stopgap with a computable shelf life, not a fix.
* **WHAT (b) ACTUALLY BUYS, said plainly: a false failure is replaced by a long silence.**
  The route yields no bytes until it is finished, so the panel can now sit blocked for ten
  minutes showing no progress. That is strictly better than telling him a backup failed
  when it succeeded — he can at least trust the answer — and it is not a good screen. This
  is the sharpest argument for (a): only an asynchronous build can report progress at all.

**Why (b) was still worth doing today rather than waiting for (a).** The panel was reporting
failure on a backup that had completed — the archive was closed 94 seconds after the abort,
whole. An owner who is told his backup failed has no way to know he has one, and the honest
reading of that screen is "ScrapeX cannot back up", which is false.

**The bound is deliberately narrow.** `/api/bundle/archive` and `/api/bundle/panel-pack`
stream a `FileResponse` whose headers arrive at once, so their existing 5-second bound is a
real guard on a fast route. The rule is written `(?:\?|$)` rather than the usual
`(?:[/?]|$)` precisely so the fix cannot take a guard off two routes while repairing one.

---

### R-77 · One number, one question: the extension carries the version, the engine carries a protocol and a build

**2026-08-30 · release · REPLACES and DELETES `R-05`, `R-06`, `R-07`, `R-35` and `R-61`**

> «احذف كل الاحكام او القرارات الخاصة ب version» · «احذف الكل واكتبه فى بند واحد غير متناثرين»
> · «المحرك ليس الاساسى الاساسى هو extension والمحرك فرعى»

**Five rulings in eleven days was not indecision. It was one number being asked three
questions that have nothing to do with each other**, so each ruling answered a different one
and read as a contradiction of the last:

| question | what answered it | which ruling was really about it |
|---|---|---|
| **which build am I running?** | `VERSION` | `R-06` — every merged pull request |
| **can the two halves talk?** | `VERSION` + `MINIMUM_EXTENSION_VERSION` | `R-35` — a contract change |
| **what can the product do?** | `VERSION` | `R-05`, `R-61` — a capability, an endpoint |

Each was right about its own question. None could be right about the other two, because a
release cadence, a compatibility boundary and a capability claim do not move together and
never will.

**THE COST IS MEASURED, not asserted.** On 2026-08-29 two sessions read
`ENGINEERING.md` W4 and the comment at `scrapex/version.py`, reached **opposite** conclusions
about whether to bump, and **neither reached `R-35`** — the ruling that governed. The prose
they read first cited `R-05`, `R-06` and `R-07` and did not mention `R-35` anywhere in the
file. A rule that needs five documents to state it is a rule nobody can follow.

---

## The decision: split the three, and let the architecture answer each

> **BUILT 2026-09-02 — clauses 1 and 2. Clause 3's last step needs `mbiX-hub`.** The
> engine now stamps `git rev-parse HEAD` into its bundle and reports it, and `Protocol` no
> longer asks whether the engine has a version. **What is not done is the cut**, and the
> reason is measured rather than chosen: the `Latest version` row feeds
> `engineReleaseVerdict`, whose `isOlder(installed, latest.version)` produces the download
> and install surface. With no engine version the check must compare COMMITS, and the
> published side of it is `mbiX-hub/ScrapeX/json/version.json` — a manual manifest in
> another repository. Cutting the rows first would leave him unable to install a new engine.
> `docs/STATE.md` carries the four steps and which two are behind us.

**1 · IDENTITY IS THE COMMIT, NOT A NUMBER.** The engine reports the SHA it was built from.
It is free, it cannot be wrong, and it needs no rule — which kills the question *"does this
pull request deserve a bump?"* outright. That question is the source of every conflict in this
entry's history, and of the five-file bump dance (`scrapex/version.py`, `pyproject.toml`,
and three generated files) that every session has to perform and can get wrong.

**2 · COMPATIBILITY IS A PROTOCOL NUMBER, NOT A VERSION COMPARISON.** Half of it already
exists: `contracts/contract-baseline.json` carries `protocol`. The extension asks *"do you
speak protocol N?"* — never *"is your version at least X?"* Comparing versions couples the
release cadence to the compatibility boundary, and they are independent facts: the engine can
ship fifty times without the wire changing, and can break the wire in one line.

**3 · THE PRODUCT VERSION IS THE EXTENSION'S, AND ONLY THE EXTENSION'S.** This follows from
his correction of 2026-08-30 — «المحرك ليس الاساسى الاساسى هو extension والمحرك فرعى» — and
from [R-48](#r-48--the-extension-is-the-control-room-and-the-only-interface-the-engine-executes-and-reports).
Chrome reviews the extension and pushes it to every user automatically; that number is the one
a person sees. **The engine gets no marketing version at all** — a protocol number and a build
SHA, both facts rather than judgements.

---

## What this dissolves, and one defect it dissolves by construction

**`R-07` ORDERED THE ADVERT REMOVED ON 2026-08-16 AND IT WAS NEVER BUILT.** Measured
2026-08-30, thirteen days later, still live in three places:

    scrapex/version.py:494      "latest_extension_version": VERSION
    scrapex/webui/app.py:1715   "latest_extension_version": VERSION
    extension/app.js:607, :641  drawn to the user as "Latest available extension"

The engine answers *"what is the newest extension available"* with **its own number**, which
is not an answer it has. `R-07` correctly said this is Chrome's fact, not the engine's. The
fix was ruled, recorded, cited in `ENGINEERING.md` as an open blocker on `R-06` — and thirteen
days of sessions read past it.

**Under this ruling it cannot come back**, and that is the point of preferring an architecture
to a rule: **an engine with no version has nothing to advertise.** The defect is not fixed,
it is made unrepresentable.

The same is true of the arguments that produced the other four:

| what stops being a question | why |
|---|---|
| "every merged PR, or only a functional change?" | nothing bumps per PR; the SHA is already exact |
| "is this a contract change?" | the protocol moves when the wire breaks, which is rare and obvious |
| "is a new endpoint MINOR or PATCH?" | the engine has no number to argue about |
| "did the advert get removed?" | there is no number to advertise |

---

## What must be built, and what stays

**Built:** the engine reports `build_sha` and stops reporting any version of the extension;
`protocol` in `contracts/contract-baseline.json` becomes the compatibility authority and
`MINIMUM_EXTENSION_VERSION` is replaced by a minimum protocol; `scrapex/version.py:VERSION`
stops being hand-edited.

**Kept, because it answers a real question:** the **capability ledger**. "Which build has X"
is worth answering and `version.CAPABILITIES` answers it. It attaches to the extension's
version and to the protocol, not to an engine release number.

**Deleted, not marked superseded** — and this is a deliberate exception to `C4`, made by him
in his own words, on the ground that five scattered entries are what caused the failure this
entry describes. **The history is not lost**: every deleted ruling is in `git log` for
`docs/RULINGS.md`, and `tests/test_the_registers_cannot_collide.py` carries a declared
`RETIRED` set naming all five and pointing here, so the five holes in the `R` sequence are
legible rather than mysterious.

---

### R-78 · The scheduler reads the REGISTRY, not a file — and a new source needs no new code

**2026-08-30 · architecture · «انا اريد الكود ديناميكى لا اعيد اختراع العجلة»**

He asked why the price crawl and the muqawil crawl take different paths when they have
different tables and different treatment. **Measured against the code rather than answered
from the design: they do not.**

| layer | price | muqawil | a real difference? |
|---|---|---|---|
| fetching | `HttpFetcher` | `HttpFetcher` ([contractors.py:49](../scrapex/contractors.py)) | **none** — one throttle, one robots policy, one retry |
| which page next | a connector per shop | 56 partition cells, then a profile frontier | **yes** — the listing reorders every thirty seconds, so partitioning is a necessity |
| interpreting | known schema → `price_observation` | discovered schema → approval, versions, `generic_record` | **yes** — the columns are not known before the page is read |
| **what runs it** | **a background worker reading `sources.yaml`** | **a command line, and nothing else** | **NO — and this is the whole defect** |

**THE FOURTH ROW IS HISTORY, NOT DESIGN.** Prices came first, so the scheduler was built
around their shape: *a source is an entry in a YAML file.* muqawil arrived as a source that
lives in the **database**, found no door, and took a command line instead. Measured
2026-08-30 on `3a745a9`:

    scrapex/jobs.py   17 references to the manifest
    scrapex/jobs.py    0 references to muqawil, contractors, partitioncrawl,
                       snapshotcrawl, generic_record or dataset
    POST /api/jobs     app.state.manifest.get(key) -> 404 unknown source_key

**THE DECISION: the scheduler resolves a source through `source_site`, and `sources.yaml`
stops being a registry.** `R-62` did half of this by merging `site_profile` into
`source_site`; this is the half that makes the merge worth having.

**WHAT THIS IS NOT.** It is not a crawl button for muqawil. A button built on a
manifest-driven worker would turn a clear `404` into a job that is accepted, queued and fails
inside the run — `R-71` measured that and it is why `OP-92` exists. **Build the resolution and
the button falls out**; build the button and the resolution never gets built.

**AND IT IS WHY THE THING GENERALISES.** `CLAUDE.md` says of `products` that *"a new shop
needs no new module"*. Prices earned that; muqawil never did, and neither will `jobs` or
`tenders` — the two categories he has named as coming — while the door is a file only a
developer edits. **A registry-driven scheduler is what makes the platform a platform rather
than three programs sharing a warehouse.** It is `R-72`'s reasoning again: a registry in a
file and a registry in a database are two concepts for one thing.

**`SR-13` IS NOT WEAKENED AND ITS TEXT IS AMENDED ABOVE, not deleted.** *"Nothing is
collected that is not declared"* is his principle — «له أساس ليس جمعاً عشوائياً» — and it is
about **basis**, not about YAML. A row in `source_site` is a declaration exactly as a manifest
entry is, made through the extension rather than by editing a file, which is `R-48`. The scope
guard that rejects out-of-contract rows stays where it is and keeps doing its job.

**Six passes, not one button.** The muqawil crawl is `--plan`, `--crawl`, `--details`,
`--approve`, `--coverage`, `--impostors`, and **four of the six make no network request at
all**. Whatever the panel offers must name the pass; *"Update now"* describes none of them.

---

### R-79 · Device colours reach the user, and the ink is derived rather than trusted
**§5's closing clause superseded-in-part 2026-08-31 by
[R-85](#r-85--the-system-is-supabases-exactly-and-supabase-is-the-only-colour-choice); the
device colour mode this ruling repaired was itself deleted by R-85. The measurements stand
and are the reason a future device mode must not repeat them — see the tombstone in
`design/tokens.css`.**

**2026-08-30 · design system · closes [OP-101](BACKLOG.md) and half of [OP-104](BACKLOG.md) ·
first of [REQ-49](REQUESTS.md#req-49--review-the-design-system-against-supabases)'s twelve
decisions**

**HE CHOSE FROM OPTIONS RATHER THAN DICTATING, and this entry records the choice and the
numbers that were in front of him when he made it** — not a quotation, because there is
none to quote. Asked what should follow the merged review, he was offered four routes: fix
device and contrast together, rule on all twelve decisions first, run the second wave of
twenty axes, or fix the twelve silent undeclared properties. **He took the first**, which
was the one labelled as the recommendation. Asked separately what to do about a contrast
assertion that a shipped surface does not render, he was offered four and **took "drop it
with the evidence"**, again the recommendation.

#### 1 · Device colours must reach the user in both schemes

`@supports` contributes **no specificity**. The device block's
`:root[data-color-mode="device"]` is therefore `(0,2,0)` — exactly what
`:root[data-theme="dark"]` and `:root:not([data-theme="light"])` are — and while it stood
above them in `design/tokens.css` they won on source order and redeclared all seven of its
properties. Measured in Chromium 149: device-dark resolved `--accent` to `rgb(62, 207, 142)`,
which is Supabase's own `#3ecf8e`, **while the panel's status text reported "Device
colours"**. One of the four choices `R-74` names by name, unreachable in half its states.

The block moves below both dark blocks. That is the whole fix, and
`test_device_colours_reach_the_user_in_both_schemes` asserts the property that broke —
device DIFFERS from the baseline in both schemes — rather than a value, because the accent
belongs to the machine and not to us.

#### 2 · The fix REVEALS the contrast failures. It does not cause them.

**This sentence exists so that a reader six weeks from now does not conclude the cascade fix
broke something.** Device-dark was passing 0 of 17 assertions because it was not device: it
was the default palette wearing device's name. Making it real exposed what the derivation
actually produces, and five pairs went red the moment they had something true to measure.

That is also why the coverage lands in the same change. Landing the cascade fix alone would
have closed a visible defect and left an invisible one, with the guard still unable to see
the mode it was now painting.

#### 3 · The operating system's own ink is not legible on its own accent

Chromium 149's `AccentColor` is `rgb(0, 117, 255)`. Its `AccentColorText` is **white**, which
is **4.21:1** — under the 4.5 floor this repository enforces. Black on the same accent is
**4.99:1**. The browser hands over the worse of the two, and it is the pair a user reads a
primary button through.

**Supabase's own mechanism picks the wrong one too**, which makes this the fifth departure
from the baseline and it is written at the value like the other four. Their on-colour is a
hard step on OKLCH lightness; for this accent it resolves to L 0.99, near-white, because
OKLCH lightness and WCAG relative luminance disagree about saturated blues.
`contrast-color()` asks the WCAG question directly and answers black.

**And one ink cannot serve both ends of an accent the operating system chooses.**
`--accent-hover` moves toward `--text`, so in light it darkens and converges on the black
ink: 3.766:1. Derived per surface, light picks white for the hover (5.576) and dark keeps
black (6.066). `--button-hover-text` already existed as a separate token; this is the system
anticipating the problem before it was measured.

#### 4 · A palette entry may carry only colour, and every value here does

Nothing in this ruling touches shape, typography, spacing, elevation or motion.
[R-74](#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour)
holds unchanged, and `tests/test_a_palette_may_change_nothing_but_colour.py` still passes.
The four device values that moved — the ink derivation, the hover ink, `--accent-ink` at 60%
instead of 78%, and the dark `--line-strong` base at `#787878` instead of `#707070` — are all
inside device-scoped blocks in `design/tokens.css`, and the three registered palettes are
untouched by them.

The dark `--line-strong` base is the one that deserves its own line: device surfaces are
tinted with the system accent and therefore **lighter** than the plain dark surface, so a
border that clears 3:1 on the plain one does not clear on this one. `#707070` measured
2.982:1 and stayed under the floor **across the entire mix range** — 2.982 at 26%, 2.994 at
20%, 3.002 at 14%, 2.994 at 8% — because line and surface are mixed with the same accent and
move together. That is a measured difference, not the silent drift recorded above it.

#### 5 · An assertion that no surface renders is removed, with its evidence

`("accentContrast", "accentHover")` is gone from the pair list. **`--accent-hover` has no
consumer anywhere outside `design/tokens.css`** — the only thing that reads it is
`--button-hover` — and the surface it becomes is inked with `--button-hover-text`, which
`("buttonHoverText", "buttonHover")` covers. While the two inks were the same token the pair
was a duplicate; once device derived them separately it became a duplicate that was also
false.

**Removing an assertion is the move this repository is most suspicious of**, and it was put
to him as its own question with the alternatives priced: keep it and flatten the hover to
94% of the accent, which passes at 4.489 and costs the hover its visible affordance; or
repoint it at the tokens that actually render, which reproduces a pair already in the list.
He chose removal with the evidence recorded. **No floor was lowered and no surface a reader
meets went uncovered.**

#### 6 · What the coverage now is, and the one thing it found that was not device

The matrix goes from **102 executions over 6 states to 168 over 8** — three palettes plus
device, two schemes each, 21 assertions apiece. Five pairs were added, all using tokens that
already exist, so `THEME_PROPERTIES` stays at 36 and no palette gained a cell.

**The deeper half of `device` having no coverage was never the parametrize.** The guard read
custom properties as declared, and `getComputedStyle` does not resolve them — so device's
`AccentColor` and `color-mix(...)` came back as the literal text `ACCENTCOLOR` and
`COLOR-MIX(IN SRGB, ...)` and nothing could score them. **Pointing the old reader at device
would have measured nothing.** It now resolves through a probe element, for every palette and
not only for device, so a palette that starts using `color-mix` cannot quietly fall out of
coverage either.

**And the five new pairs found their first defect in a shipped palette, not in device.**
`brand` light painted `--accent-ink` `#18864B`, which is **4.180:1** on that palette's own
`--accent-weak` — and was already marginal at 4.615 on white. `--accent-weak` cannot be
raised to meet it: even `#F0FEEE` only reaches 4.421, so the ink was the only side that could
move. It is `#147742` now, at 5.077 and 5.604. **Per this ruling a failing pair is a defect
in the palette, never a reason to lower a threshold.**

> **~~§5's closing clause~~ SUPERSEDED-IN-PART 2026-08-31 by
> [R-85](#r-85--the-system-is-supabases-exactly-and-supabase-is-the-only-colour-choice).**
> *"Never a reason to lower a threshold"* no longer holds without exception, and the exception
> is narrow: where a value is **Supabase's own** and «مطابق تماما» requires it, the threshold
> yields to the value. Two positions do this and no others —
> `--line-strong` at **1.542** light and **1.648** dark, and `--focus` at **1.466** light,
> against floors of 3.0. Their `--border-stronger` and their `--ring` are genuinely below what
> this repository asks, Supabase states no numeric contrast target anywhere in its 105
> authored documents, and he ruled «عدل اى قرار يتعارض مع هذا النظام» after being shown 1.47:1
> for the focus ring.
>
> **EVERYTHING ELSE IN §5 STANDS, AND THE REST OF THIS RULING IS UNTOUCHED.** A pair that fails
> on a value THIS repository chose is still a defect in the palette — which is exactly what
> the `brand` ink above was, and it stays fixed. And R-85 lowered nothing silently: both
> assertions are **pinned at their measured ratio** rather than deleted, so drift in either
> direction still fails and the number stays findable. A deleted assertion is a threshold
> nobody can locate again.
>
> **Read this before repairing either ratio.** Seen from `tests/test_panel_dom.py` alone they
> look like a regression against §5, and they are a ruling.

**AND ONE MEASUREMENT IN §5 SUPPORTED A FALSE CONCLUSION**, found while building `R-85` and
recorded here because this entry is where a reader looks for it. `--amber` was listed among
the departures on the strength of **2.677:1 against `--amber-weak`**. The number is correct
and the pairing is this repository's invention: **Supabase never puts warning text on its own
warning-300 tint.** Its ink for a warning fill is `--warning-foreground`, and their value with
their ink measures **6.923** light and **10.646** dark — so restoring their colour cost
nothing and RAISED the ratio. A measurement of a pair nobody renders is not evidence about a
palette.
---

### R-80 · One feature, one place — and a read-only second copy is still a second copy

**2026-08-30 · architecture · SUPERSEDES his ruling of 2026-07-29, which stays per C4**

> «لا اريد حتى صفحة الويب للعرض فقط · اتراجع عن هذه النقطة نظرا للحالة السيئة من البعثرة ·
> اريد فقط الميزة فى مكان واحد محدد»

**He retracted a concession he had made himself.** On 2026-07-29 he ruled *«لا اريد اى اعدادت
على صفحة الويب — الاعدادت كلها على extension بينما صفحة الويب للعرض فقط»*: the controls move
to the extension, and the engine's web page may keep **showing** the values. That half-measure
is what he withdrew, and he named the reason — *the bad state of the scattering*.

### What changed his mind, and it was measured in front of him

He was shown the count. Across the two surfaces: **11 `/api` routes called from both**, **31
live routes reachable only from the engine's own pages**, **18 only from the panel**, and
**eight settings that can be changed nowhere but the engine's web UI**. The concession had not
held the line; it had drawn one and left it unguarded for thirteen months of drift.

**And the guard that was supposed to enforce the 2026-07-29 rule cannot see a button.**
`_control_ids` in [tests/test_settings_live_in_the_extension.py](../tests/test_settings_live_in_the_extension.py)
matches `input|select|textarea` only. `_storage.html` holds eleven buttons and `_retention.html`
four — **fifteen actions the guard has never looked at**, driving thirteen write routes — and
the nine ids it *can* see are exactly the nine on its own exemption list, so its assertion
forbids nothing at all today. A rule enforced by a test that always passes is a rule that was
never enforced.

### The rule

> **A capability lives in exactly one place. Display is not an exemption: a value shown on a
> second surface is a second surface to keep true, and it is where the drift starts.**

The single place is the extension, per [R-48](#r-48--the-extension-is-the-control-room-and-the-only-interface-the-engine-executes-and-reports)
and [R-50](#r-50--the-engine-is-a-helper-to-the-extension-and-any-task-the-extension-can-do-moves-to-it).
The engine keeps only what the extension **cannot** do — and `R-50` already requires that to be
a measured technical limit rather than a category.

### What it does NOT say

**It does not order the engine's web UI deleted**, and it must not be read that way. `DEC-8`
measured that page as the SOURCE of the port — 3,212 lines of `grid.js` — so it is the asset a
migration spends, not debt to delete. What ends is a capability existing on both sides at once.

**It does not make the drift a fault of the people who wrote it.** Every one of the eight
web-only settings was correct when written; the concession is what allowed the second copy, and
the concession is what he withdrew.

### The cost, stated because it is a test that must be inverted

`test_the_web_page_still_shows_what_the_engine_holds` in the same file **asserts the retracted
rule**: *"Display-only is not the same as blank: moving the controls must not take the VALUES
away."* Under this ruling that test fails the build for doing the right thing. It is inverted
or deleted by whichever change first moves a value off the web page — not before, so that the
guard never covers less than it covers today.

### The evidence that a second copy rots rather than merely duplicating

Both surfaces carry the same restart-and-poll loop. **The panel's copy was repaired and the
engine page's was not**: `settings.html` polled `/api/marketlens/health`, a route deleted when
the two per-database health checks collapsed into one, so it could only ever 404 — and the
engine's own page reported a restart that had **succeeded** as *"The engine has not come
back."* on the one control a person reaches when they are already worried. Filed as `OP-114`
and repaired in the change that carries this ruling.


---

### R-81 · A command-line answer is not an answer; the panel is the only door

**2026-08-30 · how he works · corrects a session that had just offered him three shell commands**

> «انا لا استخدم terminal نهائى انا فقط استخدم الواجهة من خلال extension»

**He had asked twice when he could run a muqawil crawl.** He was told, in detail and with
measurements, that `scrapex contractors --plan` and `--crawl` were ready today and that only
the BUTTON was missing. **That answer was worth nothing to him**, and it took a second
question to find out why.

**WHAT THIS CHANGES, and it is not tone.**

**1 · An unbuilt panel control is an unbuilt FEATURE.** Not a convenience gap, not a nicety
deferred behind other work. If it has no control in the panel it does not exist for the one
person the tool is for, and a report that says *"it works, from the command line"* is a
report that a thing he cannot do is done.

**2 · The data he owns was collected in a way he cannot repeat.**
`REQUESTS.md` already carried the sentence and nobody had drawn the conclusion: *"every
muqawil crawl to date, all 34,834 pages, ran from a terminal."* **Every one of them was run
by a session on his behalf.**

**3 · `REQ-45` moves to the HEAD of the muqawil queue.** It had been sequenced behind the
engine page and the Drive defect on the reading that it was a convenience. **It is the door
every remaining muqawil step passes through** — `R-56`'s listing crawl, the profile parser,
`R-68`'s reconciliation — so it is not one item among them, it is the precondition for all of
them.

**4 · And `R-56` had been mis-filed as waiting on HIM.** It was ruled on 2026-08-26 — a fresh
listing crawl, priced at 58 minutes — and has sat since under "awaiting the owner". **He was
never the blocker.** It waits on a control he does not have, and this session filed it against
him again on 2026-08-30 before he corrected it.

**WHY THIS WAS NOT ALREADY WRITTEN DOWN, since it is the obvious question.** The repository
says the *shape* of it in three places and the *fact* in none.
[R-48](#r-48--the-extension-is-the-control-room-and-the-only-interface-the-engine-executes-and-reports)
makes the extension the only interface;
[R-50](#r-50--the-engine-is-a-helper-to-the-extension-and-any-task-the-extension-can-do-moves-to-it)
moves every task it can do to it; `PLATFORM-PLAN` names *"a non-technical user"* who never
touches a command line. **All three are about the product's users. None says the owner is
one of them.** So a session could hold every one of those rulings, obey them in design, and
still hand him a shell command — which is exactly what happened.

**WHAT A SESSION DOES INSTEAD.** Offer what the panel can do. Where it cannot, say so plainly
and name what is missing, rather than routing around it with a command. **Running something on
his behalf is a legitimate offer** — it is how the 34,834 pages were fetched — but it is an
admission that the feature is absent, and it is recorded as one rather than counted as
delivery.

---

### R-82 · The ten remaining decisions of REQ-49, taken in one pass

**2026-08-30 · design system · completes
[REQ-49](REQUESTS.md#req-49--review-the-design-system-against-supabases) with
[R-79](#r-79--device-colours-reach-the-user-and-the-ink-is-derived-rather-than-trusted)**

**HE CHOSE FROM PRICED OPTIONS RATHER THAN DICTATING**, as with `R-79`, so there is nothing
to quote and this entry records the choice and the numbers that were in front of him.
Twelve decisions came out of the review; `R-79` took two; these are the other ten, answered
in one pass when he asked for *«الاسئلة واختيارات للموصى»* — the questions with options and
a recommendation on each.

| | he chose | the number he chose it on |
|---|---|---|
| OD-01 | **no** to Supabase's numeric ramps, **yes** to the four status-border tokens only | 15 tokens x 3 blocks = 45 declarations, `THEME_PROPERTIES` 36 to 51, against 4 tokens with 14 call sites and nine competing mix percentages behind them |
| OD-02 | switch `--amber` to **`#8d5e00`** | the shipped `#965900` is a naive per-channel clip of a target 27.6% outside sRGB; it sits 9.5 degrees off Supabase's warning hue |
| OD-05 | the alpha-token fix gets **its own plan** | exact on `--background`, wrong on `--card` and `--popover` by 2/255 light and (5,6,6) dark |
| OD-06 | extract **`table-theme.css` only** | 101 lines already token-bound, against `grid-theme.css`'s 1,837 lines of Tabulator override; the extension has zero table CSS |
| OD-08 | discharge attribution under **both** licences | their root is Apache-2.0, `packages/ui` declares MIT with no licence text; this repository already discharges the same obligation three times for a smaller borrowing |
| OD-11 | **fold** `STATE.md`'s "Open pull requests" section | 642 lines with nothing open, grown 107 lines **above** the banner placed to stop it |
| OD-12 | **bare-path tier first**, `DOCUMENTS` widening second | the guard covers 9 of 82 documents, and widening alone changes zero verdicts |

#### Three went against the recommendation, and they are recorded as his

**`C5` asks for this explicitly** — *"if the evidence contradicts a ruling, say so and record
it"* — and the argument that lost is the one the next session needs when it reaches the same
fork. None of these is softened into agreement.

**OD-07 · grow the shared `.empty` AND migrate the ten local implementations.** The
recommendation was to grow it and migrate nothing until a screen was touched for another
reason, because `docs/UI-KIT.md` records a measured extraction that was **refused** on
exactly that ground. He chose the migration. The number either way: 3 declarations shared
against 10 local implementations and 19 usage sites.

**OD-10 · convert `design/gallery.html`'s 22 inline styles to classes.** The recommendation
was to exempt the file explicitly, asserting that every inline style on it is token-only —
21 of the 22 are pure `var(--token)` — so the catalogue could keep demonstrating tokens the
way a reader sees them. He chose conversion.

**OD-09 · "reject it", and IT IS NOT BUILT.** He was asked whether to sanction the panel's
control-height override, raise the 48px touch floor to the baseline, or reject the override.
He chose reject. **Measured, that reading deletes a live accessibility constraint**:
`tests/test_panel_dom.py:462-467` asserts a 48px bounding box on two selectors, so
"reject the override" is either "delete the floor with it" or "delete it and raise the
baseline for both surfaces" — materially different work, one of which removes an Android
touch floor. The three readings were put to him with the numbers and he replied *«كمل»*,
which is *carry on*, not a choice among them. **So it is parked, visible, and unbuilt.**
Nobody has quietly removed an accessibility constraint on his behalf, and nobody has
overruled him either.

#### Why they were taken in one pass rather than one at a time

Nine of the ten are independent of each other and eight of them cost no new token. Asking
them singly would have spent nine of his turns on decisions whose interaction is nil. The
one real coupling — OD-03 with OD-04 — was already ruled together in `R-79` for that reason.

---

### R-83 · A known Arabic omission loses one locale value, not the whole profile

**Ruled 2026-09-01.** After the profile refresh left eight locale mismatches, he asked to
locate the exact differences and then ruled: **«نفذ الاصلاح»** — keep the information that
is right and ignore only the missing value so nothing else is lost.

The eight are not ambiguous once measured against their stored English and Arabic pages:
Arabic omits `Address` on every one. Seven Arabic pages end at `Region`; contractor `2079`
continues with `Activity`, so a positional zip would shift that value into `Address`. The
correct result is a profile with the English address preserved, no invented `address_ar`,
and every later bilingual value still paired with its own field.

This does **not** replace `R-51`'s label-independent normal path. It adds one conservative
fallback only when Arabic is shorter by exactly one box. The English labels must be the
known canonical sequence, unique and ordered; every Arabic label must match the site's
observed vocabulary, be unique, and form that same sequence with exactly one field omitted.
An unknown spelling, duplicate, reorder, or any other count difference still refuses the
whole merge. Thus the fallback uses an Arabic label only to prove the exceptional gap; it
never guesses from a value or silently zips unequal arrays.

Replaying the eight real stored pairs through the repaired parser approves **8 of 8**, each
with the stable 27-field schema and no warning. Seven exercise the trailing omission and
`2079` proves the interior shift: both `activity` and `activity_ar` survive while only the
missing Arabic address is absent. The 177 ids rejected by the new crawl because the site
returned its listing page remain rejected; this ruling cannot manufacture a dead profile.

The repair changes code before it changes the warehouse. The running Organization
Enrichment job has an immutable input snapshot and cannot see a later re-approval. Apply the
eight recovered profiles after that job finishes, then run the update enrichment so only the
newly available profile facts enter the next snapshot.

### R-84 · The base changes now — and at publication no migration is ever deleted again

**2026-09-02 · architecture. It governs the migration CHAIN, and it does not touch
`R-24`, which governs the DATA.**

> «قواعد البيانات يتم ترقيتها ولكن base يتغير الان بحيث اننى لا اريد الاحتفاظ
> بترحيلات كثيرة لا يستخدمها احد اكيد عند نشر الاداة ساريد الحفاظ على كافة الترحيلات
> لانها ستكون مهمة للمستخدمين حيث غير محدد اى مستخدم توقف عنده هذه النسخة ولكن قبل
> الاصدار لا اريد اراكم الكود باختبارات وترحيلات لن تستخدم سوى مرة واحدة وهى لى»

and, earlier the same day, the sentence this refines:

> «قاعدة تحت v16 لا تُرقّى — تُحمَل أو تُبنى من جديد»

**PROVENANCE, because `C3` asks for HIS words and these two sentences reached two
different sessions.** Neither is second-hand: each was given by him directly, to
whichever session was in front of him at the time.

| the sentence | received directly by |
|---|---|
| «قاعدة تحت v16 لا تُرقّى — تُحمَل أو تُبنى من جديد» | the session that built `OP-120`-`OP-123`, in its own conversation |
| «قواعد البيانات يتم ترقيتها ولكن base يتغير الان …» | the **primary** session, in its own conversation, then passed on character-for-character |

**The distinction is not pedantry.** *"A session was told he said this"* and *"the
session he said it to wrote it down"* are different claims, and only the second
supports a ruling. Both here are the second. Recorded in the repository rather than
left in either conversation, which is the whole of `C7` — and the reason two sessions
had to compare notes to assemble one ruling is `ORCHESTRATION.md`'s subject, not a
defect in either.

**IT SUPERSEDES NOTHING, AND THE LINE WAS ALREADY IN `R-24`.** Read `R-24`'s own
quotation again — *«طبعا الافضل تطويرها لان **عند نشر الاداة** المفروض نحافظ على بيانات
المستخدمين»*. **The publication boundary was in that ruling from the day it was made.**
What nobody had done was apply it to the migration CHAIN rather than to the DATA. He
reaffirms the data half in this ruling's first clause: *«قواعد البيانات يتم ترقيتها»*.

| | |
|---|---|
| [`R-24`](#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema) protects **the data** | a database is upgraded, never replaced. **Untouched, and restated by him here** |
| **`R-84`** governs **the baseline** | before publication the chain is not a user-facing asset and may be collapsed. After it, **no migration is ever deleted** |

**AND A CORRECTION IS RECORDED HERE UNDER `C5`, because a session reported a conflict
that does not exist.** It read `R-24` as forbidding this and said so — *"a carry-over or
migration that refuses on real data is a release blocker"* and *"`init-db` is for an
installation with nothing to lose"*. **Those sentences are the ruling's ELABORATION,
written by a session, and they are stated unconditionally where his words were
publication-scoped.** The collision was between his ruling and its own commentary, not
between two of his rulings. Left standing in `R-24` rather than edited, because the
elaboration is right about the world it describes — the published one — and rewriting
it would hide that the distinction had to be found. `C4`'s reasoning applies to a gloss
as much as to a ruling: a corrected text inherited by the next session teaches nobody
that the mistake was available.

**AND THE GENERAL SHAPE, because it is not about these two rulings.** **An elaboration
under a ruling is not the ruling — and one written without the ruling's scope reads as
a stronger rule than the owner gave.** Every ruling here is his words plus a session's
working-out of them, and the working-out is the part that gets quoted later, because it
is in English and in bullet points. `R-24`'s gloss dropped «عند نشر الاداة» and became
an unconditional release blocker; two sessions then read it as his. **So a sentence in
an elaboration that constrains future work must carry the scope its quotation carried**,
or it will be obeyed further than it was meant. Three of the failures found on
2026-09-02 were prose disagreeing with a mechanism; this one is prose disagreeing with
the prose above it, which nothing guards at all.

**«تُحمَل» DOES NOT NEED IMPLEMENTING, and that was the blocker.** His warehouse was
measured read-only at `PRAGMA user_version = 16` — the head of the chain. **A baseline
squashed at the head replays nothing over it**: there is no upgrade for it to take, so
there is no carry-over to write and no rebuild to perform. The path that does not exist
for an engine database — `carry_over` reads the two pre-M5 files and never an engine
one, `warehousemerge` is evidence-only by its own docstring — is a path this ruling
never asks for.

**THE PRICE, RECORDED AS A WAIVER AND NOT AS A MEASUREMENT.** The squash removes the
upgrade path for any database below the new baseline. His primary machine is at the
head and unaffected. **The second machine's version is unknown and was never
measured** — he said *«لا اكترث لجهازى الثانى الان»*, and that is a waiver. **If that
warehouse is below the baseline, this change strands it**, and he accepted that on
2026-09-02 without its version being known. Written down because `C5` is satisfied by
recording missing evidence, not by treating a waiver as a finding.

**WHAT MUST BE BUILT BECAUSE OF THIS RULING, and it is not the squash.** He says the
rule INVERTS at publication: every migration kept forever, *«حيث غير محدد اى مستخدم
توقف عنده هذه النسخة»*. **A rule that lives only in prose is the failure this
repository keeps recording** — `R-07` ordered something removed on 2026-08-16 and
thirteen days of sessions read past it. So the squash lands with a check that refuses
to delete a migration once a release marker exists. That is the difference between
this ruling holding and this ruling being remembered.

**AND IT COVERS TESTS, WHICH IS EASY TO MISS IN HIS SENTENCE:** *«لا اريد اراكم الكود
باختبارات وترحيلات لن تستخدم سوى مرة واحدة»* — **tests too**. A test that exists only
to exercise a one-off migration is the same debt. **Two of them are not**, and the
distinction has to be made per file rather than by name: a test named for a migration
often asserts a PROPERTY of the resulting schema and is then the only thing checking
it; and `tests/test_migration_drift.py` must survive regardless, because proving that
an upgraded database equals a fresh build is the entire claim a new baseline makes.

---

### R-85 · The system is Supabase's exactly, and `supabase` is the only colour choice

**2026-08-31 · design system · GENERAL — «عدل اى قرار يتعارض مع هذا النظام» · supersedes
[R-74](#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour)
parts 2, 3 and 4, and discharges the palette registry
[R-59](#r-59--the-palette-registry-brand-is-default-alternatives-is-extensible-teal-is-debt)
decisions 1 and 3 · supersedes-in-part
[R-79](#r-79--device-colours-reach-the-user-and-the-ink-is-derived-rather-than-trusted) §5**

> «انا اريد النظام مطابق تماما لنظام supbase عدل اى قرار يتعارض مع هذا النظام»
>
> then, asked which of R-74's four colour choices survive:
>
> «احذف الثلاثة وابق supabase وحده»

**RECORDED THE SESSION HE GAVE IT, WITH THE WORK NOT YET STARTED**, and amended in the same
session when he answered the two questions it had left open. `C3` does not wait for a plan;
`C5` wants an unresolved half visible rather than settled by a session's judgement.

**WHY IT IS AMENDED IN PLACE RATHER THAN SUPERSEDED BY A SECOND ENTRY.** `C4` protects the
history of a PUBLISHED decision — superseded text stays because citations to it exist and
readers inherited it. This entry had never reached `main` when the answers arrived, so there
is no inherited reading to protect, and publishing a document that says "open" about
something already answered is a lie with a date on it. **What C4 does require, and what
section 4 keeps, is that the questions were ASKED and ANSWERED rather than never in doubt:**
the measurement that made them askable is what makes «القيم فقط» a decision instead of a
default.

**PROVENANCE, because a ruling rests on who heard it.** Both sentences quoted above, and both
answers in section 4, reached THIS session directly in his own words. No part of this entry
is a relay. *"A session was told he said this"* and *"the session he said it to wrote it
down"* are different claims and only the second carries a ruling.

#### 1 · What it replaces

`R-74` made Supabase's design system the baseline and then **named three exceptions on top of
it** — *«قد ضفنا له استثناء 3 palette الوان واتساب وجت هب و device»*. This ruling deletes those
three. `supabase` is not the default among four; it is the only one.

**Both rulings are general and each cancels what conflicts with it.** `R-74` said *«واى تعارض
معاها يلغى»* about itself; this one says *«عدل اى قرار يتعارض مع هذا النظام»* about Supabase.
Put to him as a direct question — do the three exceptions survive — and he answered by
deleting them. So the later ruling wins on the point it was asked about, and `R-74`'s first
part is untouched: the design system is still Supabase's.

#### 2 · What deleting the three costs, measured before it is built

| | |
|---|---|
| filled palette cells removed | **134** — `brand` 36+36, `blue` 31+31 (`blue` is five short of `THEME_PROPERTIES` in each scheme) |
| registry lines removed | **120** of `design/appearance.js` |
| device declarations removed | **20** across three blocks of `design/tokens.css` |
| stored-preference migration needed | **none** — `resolvePalette` already returns `DEFAULTS.palette` for an id it does not know, so a stored `whatsapp`, `github`, `brand` or `blue` resolves to `supabase` on its own |
| contrast matrix | **168 executions over 8 states → 21 over 2** |

**And it deletes work that landed hours earlier.** `R-79` was entirely about device colours —
the cascade fix that made *"Device colours"* reach the user in dark (`OP-101`), the discovery
that the operating system's own ink scores 4.21:1 on its own accent, the per-surface derived
ink, and two new tests. All of it goes with `device`. That was correct work under the ruling
standing at the time, and `C4` requires the history to be visible rather than tidied away.

#### 3 · What "exactly" costs, measured — three readings, orders of magnitude apart

**The ruling does not say which layer it means, and this is not a quibble.**

| reading | what it costs |
|---|---|
| **VALUES** — restore their colour values | **14 of 168 contrast assertions go red**, 18 once their white switch thumb is counted; all concentrated in the two states a fresh install paints |
| **SYSTEM** — also adopt what they have and delete what they do not | **+124 declarations**, `THEME_PROPERTIES` **36 → 72**, **144 hand-picked palette cells**, matrix **168 → 448** — *and the subtraction of* the bidirectional contract, `forced-colors`, `prefers-contrast`, seven of nine `reduced-motion` blocks, **79 `aria-live` sites**, the 48px touch floor and the Google button |
| **IMPLEMENTATION** — React, Tailwind, Radix, a build step | **351 `.ts/.tsx` files and 26 npm dependencies** against 20 authored stylesheets, inside an MV3 side panel and a pip-installed Flask app with no `package.json` at the repository root |

**THIRTEEN COMPONENTS ARE STRUCTURALLY IMPOSSIBLE, NOT MERELY EXPENSIVE**, and the reason is
the same each time: the thing being copied is a *runtime*, not a style. `chart.tsx` is
recharts reconciling a React tree to place axis ticks. `command.tsx` is cmdk's scoring and
virtual-focus engine. `form.tsx` **has no visual output at all** — it exists to wire
react-hook-form to `aria-describedby` ids from `React.useId`. `calendar.tsx` is
react-day-picker's locale and grid semantics; `drawer.tsx` is vaul's pointer-drag physics.

#### 4 · THE TWO QUESTIONS THAT WERE PUT TO HIM, AND HIS ANSWERS

**4a · Which layer does «مطابق تماما» mean?** Nothing can be planned before this. The
recommendation put to him: the VALUE layer plus the token-vocabulary additions that cost
nothing, with the implementation layer excluded **in the ruling's own text** — because
[R-48](#r-48--the-extension-is-the-control-room-and-the-only-interface-the-engine-executes-and-reports),
[R-50](#r-50--the-engine-is-a-helper-to-the-extension-and-any-task-the-extension-can-do-moves-to-it)
and [R-77](#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build)
all assume an engine with no framework.

**4b · Is the Arabic axis exempt?** **This is the only item whose cost is not counted in
assertions.** Supabase is LTR-authored and the lock is explicit, not an omission: **268
physical directional properties against 6 logical** across 351 files, zero `rtl:` variants,
zero `DirectionProvider`, zero `unicode-bidi`, and no mention of rtl, bidi, Arabic or i18n in
any of its 105 documentation files.

This repository is the inverse **because its data is Arabic**: 22 bidi-control declarations,
190 logical inline-axis properties against 20 physical, 26 `dir="auto"` render sites, 55
`*_ar` field names, 11 `*_ar` schema columns, and `"Noto Sans Arabic"` inside both font stacks
because Inter and Manrope do not cover Arabic.

**17,417 of 34,834 crawled pages are Arabic — exactly half** — and `contractors`, one of the
four categories `CLAUDE.md` names, is Arabic throughout.

**So on this axis there is nothing to copy. Exact match can only mean subtraction**: delete 22
declarations and flip 190 properties, after which Arabic company names, activities, regions
and addresses render with their digits, punctuation and Latin fragments in the wrong order
inside every English row. The affected screens are named: `source.html`, `offer.html`,
`changes.html`, `review.html`, `overview.html`, `manage.html`, `excel.html`.

The recommendation put to him is to exempt it **in the ruling's own words**, the way `R-74`
exempted three colour choices in its.

**HIS ANSWER TO BOTH, IN ONE SENTENCE: «القيم فقط، والعربية استثناء».**

**4a is answered THE VALUE LAYER.** Not the system layer, which would have been +124
declarations, `THEME_PROPERTIES` 36 → 72, 144 hand-picked palette cells and a contrast matrix
of 448 — *and* the subtraction of the bidi contract, four accessibility accommodations and 79
`aria-live` sites. Not the implementation layer, which is React, Radix, Tailwind and a build
step: 351 `.ts`/`.tsx` files and 26 npm dependencies against 20 authored stylesheets, inside
an MV3 side panel and a Flask application with no `package.json` at the repository root, and
13 components that are structurally impossible rather than merely expensive — `recharts`
computes axis geometry by reconciling a React tree, `cmdk` is a scoring engine, and
`form.tsx` has no visual output at all.

**4b is answered EXEMPT.** The bidirectional contract stays: 22 declarations, 190 logical
properties, 26 `dir="auto"` sites and `"Noto Sans Arabic"` in both stacks are untouched by
this ruling. **The exemption is not a concession to difficulty.** On that axis Supabase
publishes nothing to copy, so "exact match" could only mean deleting what this repository has
— and half the crawled corpus is Arabic.

#### 5 · Three departures this ruling would revert, and one that was never a departure

Measuring the ruling found the record of the departures itself partly wrong, and the
correction stands whatever he answers.

- **`--accent-contrast` was never a departure.** It is byte-exact to their
  `--primary-foreground` in both schemes — `#030303` light and `#131413` dark. The comment
  calling it a deliberate move away from their brand green describes a colour **Supabase does
  not use there either**.
- **`--amber`'s pair is this repository's invention.** Supabase never puts warning text on
  its own `warning-300` tint; its on-amber ink is `--warning-foreground`, which scores
  **6.92:1**. The 2.68:1 that justified the departure is a number for a pairing they do not
  render.
- **`--focus` fails in one scheme, not two.** Restoring their ring gives 1.47:1 in light and
  **3.56:1 in dark**, which clears the floor.

So the real departures are three positions, not five values: `--line-strong` in both schemes,
`--amber` in light, `--focus` in light.
