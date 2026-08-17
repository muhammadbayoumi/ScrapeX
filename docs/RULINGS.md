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
(`scrapex/version.py:477`, again in `scrapex/webui/app.py:1355`, drawn by
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
| **O-1** | **JSON column or child table** for the five multi-valued contractor groups? He allowed either. The trade is queryability against one table instead of six. | [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| **O-2** | **Does the contractor entity belong in the mbiXaddin workbook** — a `1.TableDefinition` row and its `2.SchemaRule` columns — or is it engine-only until it has proved itself? | [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| **O-3** | **Refresh shape.** A directory is re-read whole, not watched for price changes, so the append-gate reasoning does not apply. What does a second crawl of an *unchanged* contractor write? | [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| **O-4** | **Retention.** Offers keep history because a price has a date. Does a contractor profile keep history, or is the latest reading the only one? | [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| **O-5** | **B1 lists `DELETE /api/views/{id}` among nine dead routes to delete — but building saved views revives it.** Either B1 loses that line, or the new Data page cannot delete a saved view. **HELD 2026-08-16:** he has comments on B1 itself and will raise them first. Do not start B2 step 3 until he has. | [HANDOFF-resume-the-migration.md](HANDOFF-resume-the-migration.md) |

> **O-3 and O-4 may already be answered in practice** by what PR #211 implemented
> — `content_hash` over the normalised `data_json` as the change detector, an
> unchanged contractor moving `last_seen_at` and writing no revision, and history
> kept via `generic_record_revision`. Confirming that is his call to make
> explicit, not ours to assume.
