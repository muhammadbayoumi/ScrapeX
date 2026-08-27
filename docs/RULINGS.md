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
(`scrapex/version.py:483`, again in `scrapex/webui/app.py:1671`, drawn by
`extension/app.js:607` and `:641`). The moment the engine moves ahead of
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

> **PARTLY BUILT 2026-08-22, AND THE DELAY COST THE SAME 54px TWICE.** This ruling was
> given on 2026-08-16 and the advert stayed in the code. On 2026-08-22 a schema change
> moved `VERSION` to 0.3.0 for a legitimate reason under
> [R-35](#r-35--the-engines-version-moves-on-a-contract-change-the-extensions-on-a-user-visible-one),
> and **three panel layout tests failed with the identical 54px this ruling had already
> measured** — because `version_report` still read
> `bool(missing) or is_older(extension_version, VERSION)`, two questions welded into one
> verdict. The `is_older` half is gone: the GATE ("this extension lacks a capability it
> needs", a fact the engine owns) stays, and the ADVERT ("a newer extension exists",
> which is Chrome's answer) does not. Two tests pin the distinction from both sides.
>
> **STILL OWED, so it does not go missing for another six days:**
> `latest_extension_version`, `LATEST_SOURCE` and `UPDATE_INSTRUCTIONS` are named above as
> also going, and each needs a coordinated change in `extension/app.js`, which reads them.
> They were not smuggled in behind a one-line fix to the harm.

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
(`scrapex/webui/app.py:1321`, `@app.get("/export/{source_key}.xlsx")`). Both statements
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

### R-35 · The engine's version moves on a CONTRACT change; the extension's on a USER-VISIBLE one

**2026-08-21 · release · settles the trigger R-05 lost and R-07 left open**

> «كل تطويرتنا كانت تخص extension ام engine انا لا اعلم الان لان مشكل version غير
> محلولة · فكل منهم لهم version وهم لا يتحركوا طبقا للقاعدة اجعلها ديناميكية 100%»
> · «الثالث للمحرّك والثانى للإضافة، نفذ»

**He could not answer a basic question about his own project**, and that is the
defect: had the last two weeks' work gone into the engine or the extension? Measured
2026-08-21, over the 91 commits since `VERSION` last moved (`adf31b2`, 2026-08-10):

| | |
|---|---|
| touched `extension/` | **36** |
| touched `scrapex/` or `db/` | **42** |
| touched **both** | **12** |
| today's work alone | 9 commits, **0** touching `extension/` |

**One number asked about two products answers neither.** `scrapex/version.py` reads
`0.2.2` and `extension/manifest.json` reads `0.2.2` — equal **by history, not by
rule**: [R-07](#r-07--the-engine-keeps-the-version-gate-and-drops-the-advert)
unwelded them deliberately and `tests/test_version.py:536` fails if anyone re-pins
them. So their agreement today is a coincidence, which is precisely why the question
had no answer.

**A GATE ALREADY EXISTED AND WATCHED THE WRONG THING.** `tests/test_version.py` fails
when the *capability set* changes without `VERSION` moving. Capabilities had not
changed in 91 commits, so it stayed quiet while **three engine migrations landed in a
single day** — each one a change an older build cannot read.

### The two criteria, and why not one rule for both

    engine     a CONTRACT change: schema, protocol, or endpoint
    extension  a USER-VISIBLE change

A contract break stops **another program** working, which is what an engine consumer
needs warned about. Chrome shows the extension's number **to people**, so it should
move when what those people can *do* changes. One rule for both would either
announce releases the extension's users cannot see, or leave an engine consumer with
no signal that the schema moved.

**"USER-VISIBLE" IS NOT INVENTED HERE.** It is read off `version.Surface`, the
distinction `R-07` already relies on: a capability the **panel** executes raises the
minimum extension version, one the engine executes alone does not. Seven of the eight
capabilities are panel-executed.

### What "100% dynamic" was taken to mean, and what it was not

**Not** a number that moves with every commit — that is a commit counter, it is what
`R-05` was superseded for being, and it would break
`MINIMUM_EXTENSION_VERSION`, which `R-07` keeps as a **gate**: a gate that moves every
commit refuses everything.

**Instead: the criterion is enforced, so the number cannot fall 91 commits behind
again.** `scrapex/contractstamp.py` fingerprints the three parts and
`contracts/contract-baseline.json` records them against the version they describe. A
contract change with `VERSION` unmoved **fails the build**, naming the part:

```
the engine contract changed while VERSION stayed at 0.2.2:
  "schema": { "added": ["0008_a_page_remembers_how_to_ask_whether_it_changed.sql"] }
```

**The fingerprint is a sorted list and not a digest**, so the failure can say *which*
part moved. A digest can only say that something did, which is the report that sends
the next session reading three subsystems to find out.

**AND A REFACTOR IS EXPLICITLY NOT A CONTRACT CHANGE.** Moving code between files,
adding tests, writing documents — none of it changes anything another program can
observe, and a guard asserts the fingerprint cannot grow a part that a refactor moves.

**Proven by being made to fail**: the baseline was rolled back one migration and the
gate fired with the migration named. Twelve guards, and `tests/test_version.py`'s
forty-four still pass beside them.

**What this does not do:** it does not bump anything for him. The human part stays two
numbers and one command — `scrapex export-version` — which is what he measured it at.
What changed is that forgetting it is now a red build rather than a silent drift.

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
guess. **Eight stay refused**: Arabic is the shorter side, and which box *Arabic* dropped
is precisely what reading no Arabic label leaves unknowable.

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

