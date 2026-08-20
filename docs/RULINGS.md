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

### R-06 · `VERSION` moves with every merged pull request
**2026-08-16 · release · supersedes [R-05](#r-05--version-moves-per-user-visible-capability)**

`scrapex/version.py:VERSION` moves on **every new commit**. PRs are
squash-merged here, so one commit on `main` = one merged PR = one bump. Each bump
regenerates `contracts/capability-baseline.json` and `CHANGELOG.md` in the same
commit, and updates the `pyproject.toml` mirror.

**Why the old rule died:** "each user-visible capability" left the judgement to
whoever was writing, and they kept deciding no. Measured with
`git log -G'^VERSION = "'` — the number moved **three times in the project's
life**, last at `adf31b2` on 2026-08-10, then stood still for 48 commits covering
Phase A entire, T1 and B2. He noticed and said so. (As of 2026-08-17 the gap is
**58 commits**.)

> Use `-G`, not `-S`, on this file: `-S` finds only one of the three, because
> `0.2.1` → `0.2.2` leaves the count of the searched string unchanged.

**BLOCKED — do not simply bump it.** See [R-07](#r-07--the-engine-keeps-the-version-gate-and-drops-the-advert).

**Conflict — RESOLVED 2026-08-17.** [ENGINEERING.md](../ENGINEERING.md) **W4**
read *"ONE product version, and it moves when the behaviour does"* — the
superseded R-05 trigger — and was stale in a second, more dangerous way: it
called `extension/manifest.json` a **mirror** with a drift test, which
[R-07](#r-07--the-engine-keeps-the-version-gate-and-drops-the-advert) and PR #112
deliberately undid. Measured before rewriting: `pyproject.toml` really is an
enforced mirror (`tests/test_version.py:79`), while the manifest comparison was
removed on 2026-08-05 and `tests/test_version.py:536` now **fails if anyone
re-pins it**. A reader following the old W4 literally would have re-welded the
two numbers — the one thing this ruling forbids. W4 now states both correctly.

---

### R-07 · The engine keeps the version **gate** and drops the **advert**
**2026-08-16 · release · unblocks R-06**

`MINIMUM_EXTENSION_VERSION` is a fact the engine owns, derived from the ledger —
it **stays**. "What is the newest extension available" is Chrome's answer, not
the engine's — it **goes**, along with the two constants that still say the
engine carries the extension.

**The defect, found by trying the bump and reverting it the same day:**
`version_report` sends `"latest_extension_version": VERSION`
(`scrapex/version.py:477`, again in `scrapex/webui/app.py:1439`, drawn by
`extension/app.js:595` and `:629`). The moment the engine moves ahead of
`extension/manifest.json`, the panel draws *"This ScrapeX extension is older than
the engine it is talking to"*. Measured at 320×440: the profile page's legal line
went from 396 to 494 against a 440 viewport — 54px clipped. Under "bump every
commit" that card becomes **permanent and false**.

Also to go: `LATEST_SOURCE` (*"it ships with the extension"*, `:289`) and
`UPDATE_INSTRUCTIONS` (*"it carries the new extension with it"*, `:292`).

**Never fix this by bumping `extension/manifest.json` alongside VERSION.** That
was recommended once and it was wrong: it re-welds exactly what PLATFORM-PLAN
Decision 21 unwelded (PR #112), whose "Done when" is *"the other number
untouched"*. The two ship down separate paths — Google reviews the extension,
nobody reviews the engine.

**Apply:** its own pull request, with a guard that fails if the engine ever
answers for the extension's head again.

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

Recorded in [plans/2026-08-16-muqawil-contractor-source.md](plans/2026-08-16-muqawil-contractor-source.md).

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
| **SR-13** | **Nothing is collected that is not declared in `sources.yaml`.** The manifest is an extraction contract with a scope guard that rejects out-of-contract rows. | Owner principle: «له أساس ليس جمعاً عشوائياً» — *it has a basis, it is not random collection.* | `sources.yaml:1-18` |
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

### R-18 · Merge it when it is green

**2026-08-20 · process**

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

**What it costs.** Five tables and their migration; a read path per table; and the
dataset payload has to carry them, which today it cannot. That last part is the real
work and it is not yet designed — and it would have been needed for JSON too.

**What is already true and helps.** `dataset_relationship` and
`relationship_field_pair` exist (`db/migrations/0013_generic_dataset_catalog.sql`),
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

## Superseded

Kept per **C4**. Do not follow these; they are here so the current rule can be
understood.

### R-05 · `VERSION` moves per user-visible capability
**2026-08-01 · ~~active~~ SUPERSEDED 2026-08-16 by [R-06](#r-06--version-moves-with-every-merged-pull-request)**

The rule was: raise `scrapex/version.py:VERSION` for each capability a person
would notice the absence of.

**What changed:** it left the judgement to whoever was writing, and they kept
deciding no. The number stood still for 48 commits — Phase A entire, T1 and B2 —
while the ledger's gate stayed green either way. The owner noticed and replaced
the rule with a mechanical one that needs no judgement.

**Still live from the old ruling:** the capability ledger itself, the derived
`MINIMUM_EXTENSION_VERSION`, and the generated `CHANGELOG.md`. Only the *trigger*
changed.

---

## Open — awaiting the owner's ruling

Recorded rather than defaulted, per **R-02**.

| # | question | context |
|---|---|---|
| **O-2** | **Does the contractor entity belong in the mbiXaddin workbook** — a `1.TableDefinition` row and its `2.SchemaRule` columns — or is it engine-only until it has proved itself? | [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| **O-5** | **B1 lists `DELETE /api/views/{id}` among nine dead routes to delete — but building saved views revives it.** Either B1 loses that line, or the new Data page cannot delete a saved view. **HELD 2026-08-16:** he has comments on B1 itself and will raise them first. Do not start B2 step 3 until he has. | [HANDOFF-resume-the-migration.md](HANDOFF-resume-the-migration.md) |

> **O-3 and O-4 may already be answered in practice** by what PR #211 implemented
> — `content_hash` over the normalised `data_json` as the change detector, an
> unchanged contractor moving `last_seen_at` and writing no revision, and history
> kept via `generic_record_revision`. Confirming that is his call to make
> explicit, not ours to assume.
