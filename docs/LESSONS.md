# Lessons — what the code cannot tell you

Hard-won knowledge from working on ScrapeX: the traps that cost real time, the
failures that are **silent**, and the beliefs that measurement overturned.

This is not [ENGINEERING.md](../ENGINEERING.md), which says how to write code,
and not [RULINGS.md](RULINGS.md), which records what the owner decided. This file
holds what was learned the expensive way.

**It grows (C2).** When something silent is caught, or a measurement contradicts
what everyone assumed, it is written here — including when the entry that was
already here turns out to be wrong. One below is a correction of exactly that
kind, kept visible on purpose.

---

## 1 · The environment lies to you

### Several live checkouts, and both imports *and* edits default to main

`C:\Users\User01\source\repos\ScrapeX` is the main checkout;
`...\ScrapeX\.claude\worktrees\<name>` are complete checkouts too. Work aimed at
one lands in the other in **two** different ways, and both look like the fix did
nothing.

**Imports.** `scrapex` is pip-installed editable against the **main** checkout,
so `import scrapex` resolves there. `python script.py` sets `sys.path[0]` to the
*script's* directory — not the cwd — so a scratchpad script never puts the
worktree on the path and the editable install wins.

**Edits.** An absolute path typed from memory or copied from an earlier grep is a
**main**-checkout path. Edit and Write accept it happily, the worktree's tests
stay red, and `git status` in the worktree shows nothing to explain it.

Hit on 2026-08-01: a connector fix was written to the main checkout, and the
giveaway was `AttributeError: module has no attribute '_stock_count'` **after**
an assert on `__file__` had already passed — the assert covered the *import*, not
the *edit*.

```python
WORKTREE = Path(r"...\.claude\worktrees\<name>")
sys.path.insert(0, str(WORKTREE))
import scrapex.ingest as _i
assert str(WORKTREE) in _i.__file__, f"wrong scrapex: {_i.__file__}"
assert hasattr(_i, "<symbol you just added>"), "worktree code not loaded"
```

**The second assert is the one that matters** — `__file__` alone only catches a
misdirected import. Recovery is cheap and non-destructive: `git diff > patch` in
the main checkout, `git checkout --` there, `git apply` in the worktree; then
verify the main checkout is clean and leave any unrelated staged work there
untouched.

`python -m pytest` from the worktree root is unaffected — cwd leads `sys.path`.

### Never hash a repo file's raw bytes

`.gitattributes` sets `* text=auto` and `core.autocrlf` is true at system level,
so the repo stores LF and Windows checks out CRLF. Hashing raw bytes therefore
gives a **different digest on Windows than on Linux/CI for the same commit**.

This shipped as a real outage. `Migration.sha256` hashed `path.read_bytes()`, so
the general database's migration ledger — stamped from LF content — rejected the
identical CRLF checkout and refused every `scrapex ingest` and
`scrapex backup-databases` with *"checksum changed; restore the original
migration file"*. Across both live databases **57 of 57 migrations matched one
form or the other and none had actually been edited**; 41 were stamped LF and 16
CRLF, so re-stamping either way would only have moved the failure to the other
platform.

**Apply:** normalise first — `data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")`
— and treat the normalised digest as canonical. Accept a legacy raw-bytes digest
on read only when that file's raw bytes hash to it (which proves
same-content-modulo-newlines), then upgrade it in place. Hashing in-memory
strings or DB rows is unaffected: `normalize.py`, `funnel.py`, `retention.py` and
`split.py::_table_hash` are all immune.

---

## 2 · The warehouse, and reading it without breaking it

### Where it lives

The warehouse is **split**. `~/.scrapex/databases.json` points at
`~/.scrapex/general/general.db` and `~/.scrapex/marketlens/marketlens.db`. The
top-level `harvest.db` is a stray stub with no tables.

Job state is in `crawl_job` (`checkpoint_json`, `error_summary`,
`counters_json`); worker liveness and last error in `scrapex_meta` under
`runtime_heartbeat` and `runtime_worker_error`.

The crawl job-journal is real files on disk: `~/.scrapex/job-journal/<SOURCE_KEY>/`,
one `<token>__<stamp>_<uuid>.json` per fetched page, each a serialized
`FunnelPayload`. It is **live** — mutated by the running worker, cleared by a
fresh crawl, replayed by a resume. Do not write to it while a crawl runs.

### A correction, kept on purpose: `?mode=ro` does **not** miss the hot WAL

This file used to claim a read-only connection reads a stale snapshot. **That was
wrong**, and how it was wrong is the lesson.

Re-measured 2026-07-30 with a crawl running and a 12.7 MB `-wal` on disk: copy
`marketlens.db` + `-wal` + `-shm` to scratch, open the copy read-write so SQLite
replays the log, and compare against a `?mode=ro` read of the live file. Both
report **`user_version` 54 and 77,630 `price_observation` rows** — identical. A
read-only connection on Windows attaches to the existing `-shm` the running
engine holds and reads through the WAL fine.

**What actually happened the first time:** `latest_schema_version()` was 56 while
the warehouse was at 54, and that gap was read as an unread WAL. It was not —
migrations 0055/0056 simply had not been applied yet. **The code leads the
warehouse; that is normal.**

The original entry diagnosed from a plausible-looking symptom without testing it.
That is the thing to avoid, and it is why R-01 exists.

**Apply:** `?mode=ro` + `Connection.backup()` is a sound way to snapshot the live
warehouse — it is what `spikes/opfs-sqlite/prepare.py` does. Do **not** use
`shutil.copy`: that takes the main file without the WAL and really is stale. Do
**not** read `user_version < latest_schema_version()` as evidence of a bad read.
Running a crawl into an isolated `--inbox`/`--db` is still right when measuring
**writes**, but is not needed merely to read.

### The version-gate incident, and the fix that would have been wrong

2026-07-30, ELBUROJ jobs 66/68. The journal held 871 July pages stamped
`payload_version=5`; `payload.py`'s gate was exact equality
(`v != PAYLOAD_VERSION`, `Literal[6]`), so **one stale page failed the whole
3,570-page ingest** at read-back.

The crawl was never the problem — it always stamped the current version. The
**gate** was too strict for what were additive, same-generation bumps. The real
fix landed in PR #27 (`c5bf4b2`): a `GENERATION_OF_VERSION` ledger,
`PAYLOAD_COMPAT_VERSION` derived from it, and a generation **range** check
replacing equality — 6 and 7 are both generation 5.

**The tempting wrong fix:** "drop journal pages whose exact `payload_version` is
not current". Under the generation scheme that drops same-generation pages the
gate now accepts, and needlessly re-fetches a paused crawl. Any journal-read
tolerance must be **generation-aware**.

The 871 v5 pages were dropped on the owner's instruction and preserved at
`~/.scrapex/journal-dropped-v5-ELBUROJ/`.

---

## 3 · Silent failures on the ingest path

### A new `price_observation` column stays NULL forever unless the append gate learns about it

`scrapex/ingest.py::_still_the_same_price` is **both** the price-period gate and
the gate on whether a `price_observation` row is appended at all. It decides on
the price key, which deliberately excludes non-price facts — stock, trade tier.

So any newly-added column stays NULL on every offer whose price has not moved. No
error, no warning, and **the connector looks guilty**.

This has happened three times: `price_trade` (0052), and `stock_quantity` (found
2026-07-30, PR #42). Each fix is a carve-out in that function:
`if v.get("<col>") is not None:` compare against the latest observed row and
return `False` when it differs.

**Why it happens:** `record_hash` already hashes these fields and
`ux_price_obs_dedupe(offer_id, business_date, record_hash)` would admit the row —
but the gate runs first and returns before the INSERT. **The gate and the hash
disagree by construction.**

**Apply:** adding the column to the connector, the rowspec and
`_observation_values` is **not enough** — check `_still_the_same_price`. And note
`offer_state.<col>` is a **cache**, derived by `pricehistory.rebuild_offer` from
the latest observation and separately stamped by `_confirm_seen` (SUCCESS runs
only). A value present in `offer_state` but absent from `price_observation` does
not survive a rebuild, so `offer_state` coverage is **not** evidence the column
works.

### Test the second crawl, never the first ingest

A round-trip test that calls `ingest_payloads` **once** into a fresh `tmp_path`
database proves almost nothing. A first-ever ingest has no open `price_period`,
so `_still_the_same_price` short-circuits and every value lands. Production is
always the **second** crawl of an offer whose price has not moved — the only
state where the append gate can silently drop a field.

`test_display_method_and_quantity_facts.py` asserted
`price_observation.stock_quantity == 8` and passed green for a day while the live
warehouse held **0 of 6,146**. The single ingest was the blind spot, not the
assertion.

**Apply:** crawl at least **twice** (yesterday's payload, then today's) and assert
on the state after the second. Add a third asserting `observations == 0`, to prove
the table does not grow a row per crawl. Assert the value survives
`pricehistory.rebuild_offer`.

---

## 4 · Tests that pass while the thing is broken

The recurring shape: **the test exercises a path the product never takes.**

### A fixture of one page cannot see a schema that varies per page

PR #211 hit this four times in a row, and every instance was the same bug wearing
a different hat. `_schema_payload` hashes `field_key`, `source_name`,
`data_type`, `nullable`, identity and **position**. Anything in that hash which
varies *per page* makes every page after the first "a different approved schema",
and the dataset stops at one page.

1. **The classification puts its data in the label.** `.info-name` reads
   `Second Classified` and `.info-value` reads `2` — the reverse of every other
   box. Slugging the name gave `card_second_classified` on one page and
   `card_fifth_classified` on the next. Fixed as one field pair taken by
   **position**, verified over 800 real cards.
2. **First-seen order.** 55 cards in 800 carry seven boxes rather than eight, so a
   page whose thin card led produced the same fields in a **different order** —
   and position is in the hash. Fixed with a fixed lead, then sorted.
3. **`nullable` measured per page.** It read `False` where that page happened to
   be complete. Nullability is a fact about the **dataset**; one page cannot
   honestly answer it. Now always `True`.
4. **`_ar` emitted only where an Arabic value was found.** The column list then
   depended on which contractors that page's Arabic half happened to show — and
   the listing reorders, so **118 pages in 119 were refused**. Which fields the
   *site* translates is a fact about the site: `BILINGUAL_CARD_FIELDS` declares it
   once, and an absent value is a NULL in a column that is always there.

**Every one was invisible to a single-page fixture and obvious the moment real
pages were approved in a row.** The measurement that proved it: 1 page approved of
120 → 15 → 28 of 200 → **250 of 250**, then 299 of 300 in both languages.

### Merge by identity, never by position

`en?page=5` and `ar?page=5` are two requests against a listing that **reorders
every thirty seconds** — measured, 4,556 of 11,059 contractors turned up on more
than one page within a single pass. Zipping the two pages row by row attaches one
company's Arabic name to another company's English one, **and the result looks
perfectly reasonable on screen**.

### A harness that stubs too little makes a whole surface unreachable — silently

`tools/panel_harness.py` stubbed only `getAuthToken` and
`removeCachedAuthToken`, so `identity.js:authorize()` fell into its
`getRedirectURL()` try/catch and returned state `failed` under **every panel test
ever written**. The entire multi-account surface was unreachable, and a test could
press a button and read a plausible error message. It also had no route for
Google's revoke endpoint, so every sign-out driven through it took the
`local-only` path on a 404 and no test ever looked at the message.

**Apply:** when a test harness stubs a platform API, assert the *success* state is
reachable — not merely that the call does not throw. `silent_for` and
`revoke_status` are the knobs that fixed this one.

### A page that throws before its last line does nothing at all

`showView("inspect")` is the **last** line of `showTable`, so a throw anywhere
above it means pressing a table does nothing: the sections are built into a view
that is never revealed. No error, no half-drawn page, no clue. Found only by
rendering the Console for real in `tests/test_console_dom.py`.

### Some modules cannot be flattened into one scope — serve them instead

The Console's fourteen modules declare **nineteen colliding top-level names**
between them: six rule modules each declare `finding`, `text` and `same`; two
declare `SHEETS`. Flattening them into one scope is a `SyntaxError` before a line
runs. `tests/test_console_dom.py` serves `console.html` over http and loads its
real module graph instead — **the stronger arrangement, and the one to copy.**

### A guard joined by `or` cannot report which branch is false

`tests/test_the_ruling_matches_the_code.py` checked that the generated document
tells its reader how to regenerate it:

```python
assert "export-docs" in text or "export-version" in text
```

It was green for as long as it existed, and the document it guards said *"GENERATED
— by `python -m scrapex.cli export-docs`"*. **There is no `export-docs`.** argparse
answers `invalid choice: 'export-docs'` and lists the twenty-two real subcommands.
The wrong name was in the generator itself, `scrapex/cli.py:302`, so the sentence
was faithfully produced — and a reader following the repository's own instruction
got an error.

Two names joined by `or` accept either, so the assertion could not fail on the one
that was wrong. It was not a weak test; it was a test whose failure mode did not
exist. Found 2026-08-20 by reading the pattern before copying it, not by any test.

**The fix reads the parser, not a list beside it:** every
`python -m scrapex.cli <name>` in the document is checked against
`build_parser()`'s real subparser choices. A list of valid names kept in the test
would have drifted exactly the way the sentence did.

**Apply:** an `or` between two *alternatives* is fine; an `or` between two
*spellings of the same fact* is a hole. When a test tolerates more than one answer,
ask which wrong answer it now accepts — and whether the truth is available to be
read instead of matched.

### Record an equivalent mutant rather than contorting a test

In the sign-out work, removing the early return **and** switching the message from
`ended.revoked` to `ended.state === "ok"` — *both at once* — produces identical
behaviour on every reachable input, because `revokeToken` differs between the two
only when handed a falsy token. Either mutation alone is caught.

It is recorded rather than papered over. Contorting a test to kill an equivalent
mutant would be the lie.

---

## 5 · The design system: a token has four homes

A new semantic colour is **not one edit**. It must land in `design/tokens.css`
**three** times — `:root`, `:root[data-theme="dark"]`, and the
`@media (prefers-color-scheme: dark)` block (miss the third and only the
system-dark path is wrong) — **and** in `design/appearance.js` in both
`THEME_PROPERTIES` and every palette's light and dark theme. Then run
`python tools/sync_design_assets.py`.

**Why:** `apply()` writes only the names in `THEME_PROPERTIES` as inline styles on
`:root`. A token absent from that list keeps its `tokens.css` value under every
custom palette — so it is the one colour that ignores the user's choice, and
nothing looks broken enough to notice.

**Apply:** prefer deriving from an already-themed token
(`--control-active: var(--chip)`) — that needs no palette work and follows device
tones for free. Reach for a raw hex per palette only when the hue itself must be
fixed. **`--accent` is not a safe state colour**: device mode resolves it to the
OS `AccentColor`, so it can collide with the fixed `--amber`. Guarded by
`test_every_custom_property_a_stylesheet_reads_is_one_something_defines`.

---

## 6 · Two OAuth clients, therefore two grants

`manifest.json:oauth2.client_id` is a **Chrome-Extension** client (used by
`getAuthToken`); `identity.js:WEB_CLIENT_ID` is a **Web** client (used by
`launchWebAuthFlow`). A Google grant is per client, so `revokeToken` ends only the
grant of the client that minted the token it was given.

For an account added through the switcher that is complete — it only ever had a
Web grant. For the Chrome profile's **primary** account, which can hold both, one
may survive. The comment at `identity.js:176-189` is written as though there were
one client.

**Not to be fixed by revoking both:** on an `admin_policy_enforced` Workspace
account, `blocked-by-admin` is the branch that pressing again cannot fix, so
dropping the Chrome-Extension grant could leave an owner unable to sign back in at
all.

Two more found in the same reading, deliberately left alone:

- **HTTP 400 counts as revoked** (`identity.js:205`). Google answers 400 for an
  **expired** token as well as an already-revoked one, and an implicit-flow token
  lives about an hour. Sign out after an idle hour and the panel reports a grant
  ended that is still listed.
- **Neither `authorize` nor `revokeToken` has a deadline**, while `getToken` and
  `accountFor` both do. A hung revoke leaves the Sign out button disabled with the
  panel still holding the token.

---

## 7 · A document can drift into the opposite of the code

A stale document is not a neutral cost. It **actively directs the next reader
into the wrong action**, and it does so with the authority of a rule.

This project has two instances of a document stating the opposite of the code, a
third pattern — a citation that still resolves but no longer points at what it
names — a fourth, a GUARD whose own discovery pattern cannot see its subject — and a fifth, a guard that SKIPS rather than fails and so reports green while absent.
All are recorded below.

- **`docs/data-page-schema.md`** — it called itself "the ruling" and had drifted
  into stating the opposite of the code **in five ways at once**: wrong
  classification levels, Brand filed under the wrong block, the reading order the
  owner's agreement had already replaced, four columns absent, eight price
  columns absent. PR #63 was sent back partly for leaving it behind. The tables
  are **generated** now, and `tests/test_the_ruling_matches_the_code.py` is what
  stops them going stale again.
- **`ENGINEERING.md` W4** — found 2026-08-17. It was stale twice: the version
  trigger (superseded by R-06 on 2026-08-16), and a claim that
  `extension/manifest.json` is an enforced mirror of `VERSION`. That second one
  had been deliberately undone on 2026-08-05 (Decision 21, PR #112), and
  `tests/test_version.py:536` now **fails if anyone re-pins the two numbers**. So
  the most-read rules document in the repository was pointing at an action the
  test suite actively blocks and [R-07](RULINGS.md#r-07--the-engine-keeps-the-version-gate-and-drops-the-advert)
  explicitly forbids.

**The pattern:** in both cases the *code* was right and the *document* was wrong,
and the document was the thing a newcomer would trust. Neither was caught by a
test, because nothing tested the prose.

**Apply:** when a rule and the code disagree, measure which is right before
rewriting either — W4 was rewritten only after `tests/test_version.py:79` and
`:536` were read and the two mirrors were confirmed to differ. And where a
document states a fact the code owns, prefer **generating** it over promising to
keep it current. *A document nobody can trust is worse than no document.*

---

### A citation that still resolves can still be wrong, and that is the dangerous kind

Found 2026-08-19, building the [REQ-08](REQUESTS.md#req-08--a-guard-against-the-documents-going-stale)
guard. `docs/STATE.md` was two days old and three of its own `file:line`
citations were already wrong:

| citation | said | was | why |
|---|---|---|---|
| `"latest_extension_version": VERSION` in `scrapex/webui/app.py` | 1355 | **1375** | #211 and #212 inserted twenty lines above it |
| `LATEST_SOURCE` in `scrapex/version.py` | 289 | **282** | wrong the day it was written; the file was never touched |
| `UPDATE_INSTRUCTIONS` in `scrapex/version.py` | 292 | **285** | same |

**The file existed and the line existed in every case.** An existence check —
the obvious guard — passes all three. What makes this class dangerous is that the
citation looks healthy: a reader follows it, lands on plausible code twenty lines
early, and reasons from the wrong place with full confidence. Three more were
found in `BACKLOG.md` the same afternoon (`app.py:1366`, `:2363`,
`extension/app.js:885`), and two of mine were wrong within an hour of writing
them — `scrapex/features.py:57` and `:62` are a closing bracket and a docstring;
the flags are at 54 and 60.

**The remedy is `tests/test_the_documents_cite_what_they_claim.py`**
([R-15](RULINGS.md#r-15--the-documents-are-guarded-by-a-test-not-by-good-intentions)),
and the lesson for anyone writing a citation: **paste the line you are citing,
from the file, at the moment you cite it.** Every wrong number above came from
remembering a number instead of reading one.

### A guard that infers its subject from prose cannot be both sensitive and precise

The natural design for the above is to read the symbol out of the sentence — take
the backticked span next to the citation and require it on the cited line. It was
built that way first, and measured three ways:

| rule | citations checked | failures | of those, false |
|---|---|---|---|
| nearest span within 220 chars | 26 | 11 | **4** |
| same, path-like spans excluded, 120 chars | 26 | 10 | **2** |
| strict adjacency only | **3** | 0 | — |

The false alarms all came from the same thing: prose puts other backticked names
beside a citation. `extension/manifest.json` sat sixty characters from a
**correct** citation of `tests/test_version.py:536`; `` `_about` renders the
engine's own `/settings` page (`…settings.html:162-167`) `` offers `/settings` as
the nearest span while the citation is perfectly right. Tightening to fix those
dropped coverage to three citations and stopped catching the `app.py:1355` drift
that motivated the whole exercise — because in
`` (`scrapex/version.py:477`, again in `scrapex/webui/app.py:1355`) `` another
citation stands between the symbol and its line.

`tests/test_the_published_documents_are_checked_not_announced.py` had already
written the rule that settles this: *"A publish step that cries wolf gets ignored,
which is the exact failure it exists to prevent. Two cheap checks that cannot
flake beat one true check that does."* So the guard that shipped **infers
nothing**: a mechanical tier over every citation, and an explicit pinned list for
the ones that carry weight. The pinned list costs a line of maintenance per
important citation, and that cost is the feature.

**IT HAPPENED AGAIN ON 2026-08-20, with this section already on the page.** A
no-elapsed-durations rule was written over the four registers' free prose, run,
and withdrawn within the hour: it flagged **twelve** lines and essentially every
one was honest history — *"no one noticed for eleven days"*, *"Sixteen days later
nothing had been built"*, *"two days after this was captured"*. A **closed** past
interval does not rot. An **open** count against today does. No regex over prose
separates them, which is this section's claim restated in a new subject.

The rule now reads the parsed state fields of `docs/REQUESTS.md` — the board cells
and the entry state lines — where the boundary is structural rather than inferred,
and it is exact there. Same remedy as the pinned list: infer nothing, and pay a
small explicit cost instead.

The lesson about the lesson: it was recorded and still overreached. Reading it is
not the same as applying it, which is why [APPROACHES.md](APPROACHES.md) A5 is now
[R-17](RULINGS.md#r-17--a-fix-is-adversarially-reviewed-before-it-is-written) —
the default for a fix, not an option.

### A path filter tested against absolute parts skips the whole worktree

Cost about fifteen minutes on 2026-08-19, and it belongs beside §1.

The guard indexes the repository and excludes `.git`, `node_modules`, `.claude`
and friends. Written the obvious way:

```python
if path.is_file() and not any(part in skip for part in path.parts):
```

A worktree lives at `...\ScrapeX\.claude\worktrees\<name>`, so **`.claude` is a
part of every absolute path in it**. The index came back empty, and the test
reported all seventeen bare-basename citations as unresolvable — a failure that
reads exactly like the documents being wrong. The fix is one call:

```python
for part in path.relative_to(ROOT).parts:
```

Same family as §1: the worktree makes correct work look broken. Any path filter,
ignore rule or glob in this repository must be applied **relative to the
repository root**.

---

### A guard's own pattern can miss its subject, and the guard reports green

Found 2026-08-19, measuring why CI took thirteen minutes.

`.github/workflows/ci.yml` has a step whose entire purpose is to refuse a browser
suite that silently collects nothing. It finds its subjects by grepping, and the
grep read:

```
grep -l 'importorskip("playwright"' tests/*.py
```

Note the closing quote. `tests/test_grid_dom.py:24` writes
`pytest.importorskip("playwright.sync_api")`, so it **never matched**, and its 20
browser-driven tests were invisible to the guard for as long as they existed.
Dropping one character fixes it.

**The step's own comment describes the failure it then had.** It says *"THE FILES
ARE DISCOVERED, NOT NAMED… A guard that lists its subjects fails on the one nobody
added to the list"* — and discovery by an over-precise pattern fails the same way,
just less visibly, because there is no list to audit. The same afternoon, the new
docs-gate detector required a `/` before a quoted `*.md` and therefore could not
see `test_the_documents_cite_what_they_claim.py`, **the one test whose whole
subject is the documents.**

The lesson is not "write better regexes". It is: **after writing a discovery
pattern, print what it found and read the list.** Both misses were obvious the
moment the list was printed, and invisible for as long as only the exit code was
read.

### A tier that runs a subset needs a set, a floor, and a test that the tier exists

The extension split had all three and worked. The documentation tier added
2026-08-19 copies it deliberately rather than inventing a second mechanism:

| | extension | docs |
|---|---|---|
| marker | `pytest.mark.extension` | `pytest.mark.docs` |
| completeness guard | `test_the_extension_gate_is_complete.py` | `test_the_docs_gate_is_complete.py` |
| floor in CI | ≥300 collected | ≥150 collected |

**And the copying found a hole in the original.** `docs/` was already inside the
extension-only path filter, so a documentation-only change ran `pytest -m
extension` — but `test_the_ruling_matches_the_code.py` reads
`docs/data-page-schema.md`, carries no extension mark, and never needed one. A
hand-edited copy of that generated ruling would have passed CI on exactly the kind
of pull request that hand-edits it. The two sets overlap and **neither contains the
other**, which is why the extension tier now runs `-m "extension or docs"`.

Two things worth carrying to the next tier: the marker must be registered in
`pyproject.toml` or `--strict-markers` rejects it, and the tier needs a test that
**the workflow still runs it** — a marked set nothing executes reads as coverage
and is worse than no set at all.

### A scope rule written in bash inside YAML is code that no linter reads

The rule deciding whether a change runs 178 tests or 2,656 was a `grep -qvE`
pattern in `ci.yml`. Nothing checked it. Widening it by accident — adding
`scrapex/` while meaning `docs/` — would make a warehouse change run the
documentation suite and report green, and the failure would be invisible because
green is what everyone expects.

`test_the_workflows_documentation_pattern_admits_exactly_what_it_should` now lifts
the pattern out of the YAML and classifies fifteen real paths with it, over half of
them cases that must NOT be admitted. Verified by mutation: adding `scrapex/` to
the pattern fails the test naming three files.

**Any decision expressed as a pattern in a config file is testable, and the
expensive ones should be tested.** The measured saving here — 12m49s to about 30
seconds for a documentation-only pull request — is exactly the size of the mistake
a silent widening would make in the other direction.

---

### A skip is not a failure, and a guard that skips is a guard that is gone

The worst defect in the CI work of 2026-08-19 was introduced BY that work, and
caught by an adversarial review before it merged. It earns the space because the
shape recurs.

Moving the scope computation into its own job made `fetch-depth: 0` look unnecessary
on the `test` job, and the comment "Shallow is enough here now" went in with the
change. It was wrong. **Two guards ask git when something last really changed, and
both skip rather than fail on a grafted clone:**

| guard | on a shallow clone |
|---|---|
| `tests/test_the_privacy_policy_is_true.py:433` -- the policy's "Last updated" line | `_last_changed()` returns None, the test **skips** |
| `tests/test_version.py:231` -- every capability's cited commit | **skips** |

Under `addopts = "-q --strict-markers"` a run full of skips reports **green**. The
review proved it by experiment rather than argument: edit `docs/privacy-policy.md`,
leave its date alone, and full history reports one failure while `--depth 1` reports
none. That is precisely the defect the guard was written for on 2026-08-12, after the
policy was edited three times in a day while advertising an older date -- and the
Chrome Web Store listing hangs on that document.

**The repository had already learned this once.** `publish-docs.yml` and
`release-extension.yml` both ran the file at depth 1; both were fixed, and the
helper's own comment names them and says it "refuses to guess if one ever stops".

**So why it happened again.** The requirement lived as prose beside the file that
NEEDED the history, never on the jobs that have to PROVIDE it. Nothing structural
connected the two. `tests/test_the_workflows_check_out_enough_history.py` is that
structure now -- and on its first run it found a **fourth** instance nothing else
had: `release-engine.yml`'s build job runs the whole suite at depth 1, so both guards
have been skipping on **every engine release**.

Two things to carry:

- **When a test can skip, ask what makes it skip and who guarantees that never
  happens.** A skip is invisible in a way a failure is not.
- **A requirement written next to its consumer will be violated by its provider.**
  Put it in a test that reads the provider.

### `git diff --name-only` hides half of a rename, and a scope filter believes it

Rename detection is on by default, so `--name-only` prints only a move's
**destination**. `git mv scrapex/webui/templates/settings_partial.html
extension/settings.html` reports one path under `extension/` -- and a scope filter
reading that classifies the change as extension-only and never runs the engine suite,
on a change that **deleted an engine template**. Reproduced in a scratch repository:
`--name-status` shows `R100 old new`, and `--no-renames` shows both paths.

It matters here specifically because
[REQ-04](REQUESTS.md#req-04--every-setting-moves-into-the-extension) is exactly that
kind of move -- ten settings going from the web page into the extension.

`--no-renames` is the fix, and it can only ever widen the scope, which is the safe
direction for a filter deciding what NOT to run.

### Extract the pattern and you have still not tested the decision

The guard written for the scope rule lifted the regex out of `ci.yml` and classified
paths with it. An adversarial pass then inverted the shell logic -- `! grep -qvE`
("no line fails to match", so all match) to `grep -qE` ("at least one matches", the
opposite) -- and **every assertion stayed green**, because the extracted pattern was
byte-identical. A diff of one Markdown file plus one connector would have run the
documentation tier.

A configuration guard has to pin the **polarity** as well as the pattern. The two
decision lines are now asserted verbatim, with the reasoning beside them so the next
person to reshape them re-derives the polarity instead of preserving characters.

---

## 8 · The method that caught all of these

Reading the code found almost none of these. What found them:

- **Run it against reality, in a row.** Not one page — 250 pages. Not one ingest —
  a second crawl. Four schema leaks and the frontier bug surfaced only under
  repetition.
- **Measure before believing, and re-measure before repeating.** Two claims in
  `MIGRATION-PLAN.md` were false and both were caught by measuring rather than
  reading: T1's remedy would have done nothing (`alsweed.sa/robots.txt` declares
  no `Crawl-delay`), and `/api/records` is the panel's card endpoint, not the Data
  page's. A third claim was checked and **upheld**.
- **Break the test deliberately first.** Every one of the ten Console DOM tests
  was made to fail on purpose before being trusted.
- **Ask what a passing test would look like if the feature were broken.** That
  question is what exposes the decoded-email guard, the coordinate guard, and the
  single-ingest blind spot.
- **When a fix looks like it did nothing, suspect the environment before the
  logic** — §1 above.
