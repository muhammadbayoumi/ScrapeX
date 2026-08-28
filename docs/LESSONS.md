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

### A warning you have just read aloud is still a warning you can walk into

2026-08-20. `registry.py` refuses a pre-collapse pointer with a message that names the
trap explicitly: *"NOT `init-db`: … On an installation with data in them it produces an
empty warehouse beside a full one that nothing will open again."* I printed that
message in a status report, quoted it back, called `carry_over`'s refusal "the safety
design working" — and then set `SCRAPEX_DATA_ROOT` to a second location, ran
`init-db`, and crawled into the empty database. A different data root does not change
the outcome; it only moves where the empty file sits.

The owner caught it in one sentence, and his correction is
[R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema):
a database is upgraded, never replaced, because a shipped tool must carry its users'
data across schema changes.

**Why it happened is the part worth keeping.** The blocked thing (a warehouse to crawl
into) was not the important thing (the upgrade path). Creating a second warehouse made
the crawl runnable in ten minutes and left the release blocker untouched — and it felt
like progress, because something started working. **A workaround that unblocks you is
the most dangerous kind: it removes the pressure that would have fixed the real
defect.**

**Apply:** when a documented safety rail stops you, the rail is the finding. Fix what
it is protecting, or stop and say you are blocked. Do not build a path around it —
especially not one that works.

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

### On the owner's machine, neither `scrapex` nor `python` is on PATH

`scrapex ui` is the documented single launch path, and **it cannot be typed on the
machine where the owner works.** Measured 2026-08-21 on the Muhammad account:

| typed | what happens |
|---|---|
| `scrapex` | not found. `Scripts\` is not on PATH at all, though `scrapex.exe` is in it |
| `python` | the **Microsoft Store stub** — *"Python was not found; run without arguments to install from the Microsoft Store"* |
| `py` | works, and resolves to `…\Programs\Python\Python312\python.exe` |

The cause is PATH order, not a missing install: `…\Microsoft\WindowsApps` (the
Store aliases) sits at position 22 and `…\Programs\Python\Python312` at 26, so the
stub wins. `…\Python\Launcher` is at 21, which is why `py` is the one that works.

**Apply:** an instruction that begins `scrapex …` or `python -m scrapex.cli …` will
fail for him before it does anything, and the failure looks like a broken tool
rather than a PATH. Write `py -m scrapex.cli …` when handing him a command, and
remember the two-machine rule — the other account's PATH has not been measured and
may differ.

**And the same fact bites the frozen engine from the other side:** when there is no
Python on PATH at all, the shipped `.exe` is the ONLY way in. That is the argument
for the one-file binary, and the reason its silence when double-clicked
(`OP-32`) cost the owner the whole afternoon rather than a minute at a terminal.

---

## 2 · The warehouse, and reading it without breaking it

### Where it lives

**ONE FILE, AND THIS ENTRY SAID TWO UNTIL 2026-08-20.** M5 collapsed the pair into
`~/.scrapex/engine/scrapex-engine.db`, and `~/.scrapex/databases.json` names it under
`"mode": "single"` / `engine_path`
([scrapex/databases/registry.py:33](../scrapex/databases/registry.py)). This section
went on describing the split layout in the present tense, which is the failure §7 is
about, in the file that records §7.

**A pointer that still says `"mode": "split"` is a MACHINE that has not been carried
over, not a layout choice.** `DatabaseRegistry.read` refuses it by name and tells you
to run `scrapex carry-over` — *not* `init-db`, which would create an empty warehouse
beside the full one. Measured on the home machine on 2026-08-20: pointer in split
mode, no engine database at all, `general.db` present with **zero rows in every
generic table**. See [OP-22](BACKLOG.md).

The old `~/.scrapex/general/general.db` and `~/.scrapex/marketlens/marketlens.db` are
left where they were by design — carry-over copies, it does not move. The top-level
`harvest.db` is a stray stub with no tables. **`marketlens.db` will mislead anyone who
opens it looking for contractor data: it carries none of the generic tables.**

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

### A rowid lookup is not free on a table of page bodies, and the planner cannot tell

`generic_page_snapshot` stores compressed HTML — 24,480 rows over roughly 200 MB on
his warehouse. `page_snapshot_id` IS the rowid, so SQLite reads `captured_at` by
seeking the row, which drags in the page the body starts on. Measured 2026-08-22,
same query, same answer:

```
max(captured_at) over one dataset's ingested pages     353-373 ms   by rowid
                                              same       0.9 ms   INDEXED BY ix_generic_page_snapshot_page
```

`ix_generic_page_snapshot_page` is `(page_snapshot_id, captured_at)` and had existed,
unread, since migration 0014. The planner will not choose it: a rowid seek looks
cheaper than an index seek and nothing in the statistics says how wide the row is.
**On a table whose rows are documents, name the covering index.** And if it is ever
dropped, `INDEXED BY` makes SQLite raise instead of quietly paying the 373 ms — the
failure you would rather have.

### `max(id)` stops meaning `latest` the moment two warehouses are merged

The cheap version of that same read was `max(page_snapshot_id)`, then one lookup —
0.2 ms, and identical on this machine, because `save_snapshot` never supplies
`captured_at` and lets the column default fire, so ids and timestamps rise together.

`scrapex/warehousemerge.py:269` breaks it on purpose: the merge INSERTs the other
machine's `captured_at` **verbatim** under freshly assigned local ids, because the
row is evidence of when that machine fetched a page and rewriting it would be a
forgery. So after a merge — which
[R-43](RULINGS.md#r-43--drive-is-the-single-source-of-truth-for-data-the-repository-stays-it-for-code)
makes the routine operation between his two machines — the highest id can be the
oldest page.

The lesson is not about snapshots. **Any "newest row" shortcut that reads a
monotonic key instead of the timestamp is an assumption about who did the
INSERT**, and this repository has a supported operation that does it differently.
Order by the fact you mean.

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

### Store where a response CAME FROM, not only where it was asked for

**2026-08-23.** muqawil redirects a withdrawn profile id to the contractors listing and
answers 200 — and switches the locale on the way, `en` asked and `ar` returned.
`generic_page_snapshot` has a `source_url` column holding the URL the crawler
*requested*, and none for the URL the response actually came from. `httpx` follows
redirects silently. So the wrong page is filed under the right address and everything
downstream believes it.

**The guard written first read the CONTENT** — does this page link to contractors other
than the one asked for. That works, and it is the symptom. The cause is one comparison at
the fetch seam, before any parsing, and it catches every source that answers a gone
resource with an index page rather than a 404. Recorded as `OP-65`.

**The general shape: a guard at the symptom must be written once per parser; a guard at
the cause is written once.** Ours was in the parser because that is where the damage
surfaced, which is the natural place to look and the wrong place to fix.

### A 200 can be the wrong document, and a parser that only reads fields cannot tell

**2026-08-23.** muqawil answers a dead profile id with **the contractors listing**, at
HTTP 200 and ~373 KB where a profile averages 118 KB. `read_profile` calls `_boxes()`
over the whole document and `fields[key] = value` is LAST-WINS across its 160
`div.info-box` pairs, so it wrote the values of the **last** card on that listing under
the id that had been asked for: five declared columns — membership number, company size
and its Arabic, training hours and its Arabic — plus twelve undeclared `x_*` fields.
Address, email and the coordinates came out null. **39 ids were served the listing; 14
produced a row and 25 produced none**, and twelve of the fourteen took the same
stranger's card.

> **THIS PARAGRAPH WAS WRONG TWICE BEFORE IT WAS RIGHT**, and the corrections are the
> lesson. It first said *"city, size and email"*; that was narrowed to *"the membership
> number alone"*; both were measured false by adversarial review — city and email are
> null, size is not. Then *"the first card"* was the last, and *"thirteen ids"* was
> twelve impostors plus one rightful owner. Every wrong version was written from a
> probe rather than from the stored rows, which were one query away.

**Nothing downstream could catch it.** The row was complete, every field populated, every
value well-formed. `check_unique` would have caught it on the listing dataset and does not
run on profiles. It surfaced only because the owner asked whether a count was duplicated.

**So: check WHO a page is about before reading what it says.** The first fix counted
`section-card` and thresholded at 15 — *"7-9 on a profile, 22 on the listing, nothing
between"*. Both halves were false. 160 real listing pages carry **fewer** than 15 cards
(the last page of every filtered slice), so the gap did not exist on the side being
guarded; and the 7-9 census was taken with a **regex** while the parser uses
BeautifulSoup, which does not expose the `section-card` inside a `<script>` template —
through `select` a real profile has **six**.

What replaced it needs no threshold: **a profile page links to exactly one contractor,
itself.** 800 real profile pages gave min 1 and max 1; 400 listing pages gave 3 to 20.
And the caller passes the id, so the test is exact rather than statistical — a page
linking to anyone else is refused whatever its shape. Recorded as `OP-64`.

### A discriminator has to be tested against a known-good example first

Measuring how widespread the above was, the first pass classified a profile as *"a page
with no section-cards"*. A real profile has **seven**, so **398 of 400** sampled pages
were binned as unclassifiable and the run reported **0.5%** computed from the two that
survived. The percentage looked plausible and was an artefact of the instrument.

It was caught by reading the whole table rather than the headline: 99.5% unclassified is
not a result, it is a broken tool. Decoding three known snapshots showed the real shape in
one command, and the re-run gave 0.2% with 99.8% correctly identified.

**AND THE RE-RUN WAS STILL WRONG, WHICH IS THE REAL LESSON.** It sampled 500 when the
exact count cost twelve seconds, and reported *"about 70 (95% CI 0-206)"* — a normal
approximation at `np = 1`, where the interval is not valid. The census says **78**. Then
the same file's threshold was measured with a regex while the code uses `soup.select`,
and the two disagree by one card on every page. **A tool tested once is not a tool
tested**: the second instrument was as unexamined as the first, and only an adversarial
review that re-measured from scratch found it.

**Print what a measurement could NOT classify, next to what it could.** A count that
silently drops what it does not understand will report confidently on the remainder.

### Presence is not arrival: asserting the column, not the value

Four of the seven declared bilingual pairs on the contractor dataset shipped
**NULL in all 11,059 rows**, and every check passed the whole way. The test read:

```python
for field in BILINGUAL_CARD_FIELDS:
    assert all(f"{field}_ar" in row for row in without.rows)
```

That asserts the **column exists**. It was written to catch a real defect — a
schema that changed per page — and it caught that one. It could never have caught
an empty column, because an empty column is present.

The cause was worth the lesson too. `read_listing` keys a card's boxes by
`card_{_slug(label)}`, and `_slug` keeps `[a-z0-9]` only — so on the **Arabic**
page every label filtered down to nothing, became `unnamed`, and seven boxes
collapsed into one key the last of them won. The merge asked the Arabic page for
English names. The module's own docstring had already stated the right rule for
the profile path — *"the Arabic value is taken from the SAME INDEX … the Arabic
labels are never matched against anything"* — and only the listing path was doing
it by key.

**A test on a bilingual column asserts a value that is non-empty, DIFFERENT from
its partner, and in the right script.** Anything weaker passes on an empty table.

### `INSERT OR IGNORE` hid the same failure three times in one hour, in three different disguises

Building the carry-over guard on 2026-08-20. The task was one sentence — carry 3,739
pre-0058 offers into the engine schema — and it reported `written: 0`, then
`written: 1`, then correct, **with no error at any point**. Three distinct causes,
each invisible for the same reason: `INSERT OR IGNORE` treats a constraint violation
exactly as it treats a duplicate.

1. **A trigger.** `trg_offer_unit_needs_a_witness_insert` refuses an offer with a
   `selling_unit_id` and no provenance. Under `OR IGNORE`, `RAISE(ABORT)` does not
   abort — the row is skipped. Note that the CLI *did* raise on the real database, so
   the same defect looked like a hard error in one place and silence in another.
2. **`NOT NULL DEFAULT` defeated by an explicit column list.** The copy names every
   shared column, so an old `NULL` is passed as `NULL` and the new schema's `DEFAULT`
   never applies. `country_code_alpha2 NOT NULL DEFAULT '*'` rejects the row.
   **A DEFAULT only protects a column you do not mention.**
3. **A unique index collapsing rows that differ only by primary key.**
   `ux_source_offer_identity` is `(source_variant_id, COALESCE(branch_id,''),
   country_code_alpha2, customer_segment, COALESCE(selling_unit_id,0),
   basis_quantity)`. 3,739 rows built from one template are one row under it, and
   exactly one arrived.

**Two of the three were the FIXTURE, and that is the lesson rather than an aside.**
Causes 2 and 3 do not exist in the owner's real data — measured, not assumed: `0
NULLs of 3,739` in all six of those columns. A fixture written from memory described
data that has never existed, and it hid the real defect twice while looking like it
had found something. `OP-17` already says to build a fixture from the shipped schema;
this is what ignoring that costs.

**Apply:** when a bulk copy reports fewer rows than it read, do not reason about why —
re-run one row with a plain `INSERT` and let SQLite name the constraint. That took one
command each time and would have taken all three at once. And **compare the counts on
both sides**: `carry_over`'s `read` vs `written` check is the only reason any of this
was visible at all, which is what makes it worth more than the code it guards.

### A success count is not a write count

The seam's stated product is that a wrong parse is re-run over stored snapshots
with nothing re-fetched. Re-running the corrected parser over all 864 snapshots
reported **864 re-approved, 0 refused** — and changed nothing at all. Every
column was exactly as empty afterwards, and `generic_record_revision` had not
gained a single row.

`approve_candidate` short-circuits on `_approved_ingestion(conn, snapshot_id,
locator)`: same site, same dataset, same `schema_hash` means "already approved",
and it returns `{"recovered": True}` **without touching a row**. A corrected
parser produces the same schema with different values, so all 864 pages took that
path. The driver counted the returns and called them writes.

Two things follow. **Read the flag the function hands back** — `recovered` was
right there and unexamined. And **verify a repair by measuring the data, not the
run**: counting filled cells per column found it in one query, where the script's
own report was confidently wrong. Recorded as DEC-10, because the fix is a ruling.

---

### A release gate that asks only what no user types will pass a black window

The engine was published with a defect that made it unusable, and every check the
release ran was green. The gate asked the built binary one question:

    built=$(./dist/scrapex-engine.exe --version)

`--version` is the argument **nobody types**. A person double-clicks the file, which
passes none — a different branch of `packaging/engine_entry.py:main`, and in the
build that shipped as `engine-v0.2.1` that branch fell through to the Chrome native
messaging host, which waits on stdin for framed JSON and prints nothing at all.
Measured on the published artifact: **zero bytes, and still running after twenty
seconds.** The owner met a black window, concluded the engine had not installed, and
was right that something was broken.

**The source had been guarded the whole time**, which is the uncomfortable part.
`test_the_entry_point_tells_its_three_callers_apart` pins bare argv to `_first_run`
and has since #141. It was written *because of* this defect. It could not help: the
artifact was built from a commit six hours older than the fix, and no test in ~2,200
had ever run the built binary at all.

**Apply:** when something is shipped rather than imported, the gate must exercise
**the caller that exists in the world**, not the one that is convenient to assert on.
The convenient caller is usually a flag; the real one is usually a person, and its
signature is that it produces no exit code worth reading — a working first run never
returns, and a broken one exits 0 in silence. So judge the OUTPUT. "It printed
nothing" is the whole defect, and it is invisible to every check that reads a status.

**And a stale artifact is not a stale number.** `VERSION` had already moved to
0.2.2, `docs/STATE.md` tracked the gap as *version debt*, and `OP-15` recorded the
panel showing "Installed 0.2.2 / Latest released 0.2.1" as a **wording** problem
about the two meanings of "installed". Three documents held the evidence and all
three read it as bookkeeping. The number was telling the truth: no release carrying
the fix had ever been cut, and the only thing installable was the broken one — for
twelve days.

### A gate stops one line short, and the second time it is a pattern

**The same gate, the next release, the same shape of miss.** `engine-v0.3.0` was cut
on 2026-08-22 with the lesson above already built into the workflow: it launches the
binary with no arguments and requires three sentences of it. On 2026-08-23 the owner
double-clicked that release and got all three, and then this:

    [1/3] Unpacking...        done.
    [2/3] Preparing your database...  already there: ...\scrapex-engine.db
    [3/3] Starting the engine...
    error: Directory '...\_MEI000036d42\scrapex\webui\static' does not exist

**Every line the gate demanded is printed before the work begins.**
`packaging/engine_entry.py:_set_up_then_serve` announces the three steps and *then*
hands over to `scrapex ui`; `create_app` — the static mount, both Jinja environments,
the job worker — is entirely behind the last of them. So a binary that could not build
an app at all printed the gate's whole checklist and was published.

The line that separates *"the engine spoke"* from *"the engine can serve a page"* is
`scrapex/cli.py:906`, and it is one statement further on:

    app = create_app(...)                             # everything that can fail
    print(f"ScrapeX UI → {url}   (Ctrl+C to stop)")   # the first honest evidence

**Apply:** a gate on a shipped artifact must demand a line printed **after** the last
thing that can fail, and *after* is a property of the code, not a matter of taste —
`test_it_proves_a_SERVER_came_up_and_not_only_that_three_lines_printed` locates
`create_app(` by index in `_cmd_ui` and requires one demanded string to come from
below it. The three step announcements are progress; only what prints past the last
call is proof. And when a gate misses twice, widen the *rule*, not the string list.

**The second half of the miss was the guard's model of the path.** The fixture named
`double_click_path` read `packaging/engine_entry.py` alone, so the only sentences the
gate could legally demand were ones printed before control left that file. The guard
that was supposed to keep the gate honest had the same blind spot as the gate, for the
same reason, and could not have caught it.

### A killed process never flushes, so an unflushed line is not evidence of anything

**This one was caught before it shipped, and only because the fix above was tested
rather than reasoned about.** Having established that the release gate must demand a
line printed after `create_app` returns, the obvious move is to demand
`ScrapeX UI → …` from `scrapex/cli.py`. Measured against the source before changing
anything:

    timeout 20 python -m scrapex.cli ui --no-open --port 8131 2>&1
    -> ZERO BYTES

The server had started perfectly. **Three facts have to be true at once for that to
happen, and they all are here:**

1. `spoke=$(...)` makes stdout a **pipe**, and Python block-buffers a pipe. To a
   terminal it is line-buffered, so every interactive run looks fine.
2. A working first run **never returns** — it ends inside `uvicorn.run` — so nothing
   after that line will ever flush the buffer.
3. The release step therefore **kills** it with `timeout`, which is how the step
   passes rather than a fault. A killed process flushes nothing.

So a gate demanding that line would have refused **every good release**, and the
failure would have read as "the engine did not start" — sending the next session to
look at `create_app` when the defect was one keyword in a `print`.

`packaging/engine_entry.py:_say` had this right all along and says so; the three step
announcements survive for exactly that reason, which is also why nobody had noticed
the rule. `scrapex/cli.py:906` now carries `flush=True` with the measurement in a
comment beside it.

**Apply:** in this repository a printed line is only evidence if the statement that
prints it flushes, and
`test_every_line_the_gate_demands_is_FLUSHED_because_the_engine_is_killed` asserts
that of every string the release gate greps for — matching the enclosing call by
parentheses rather than by line, because the keyword sits on a different line from
the text. More generally: when a check reads the output of a process it also kills,
buffering is part of the contract, and the only way to find out is to run it.

### PyInstaller bundles MODULES; the files your package opens are invisible to it

The cause of that release's failure, and it is one sentence long: the recipe named two
data entries and the runtime opens five.

    --add-data db;db
    --add-data sources.yaml;.

Nothing else rode along. `scrapex/webui/app.py:364` computes
`Path(__file__).parent / "static"`, which in a one-file build is
`_MEIPASS/scrapex/webui/static` — exactly the path in the owner's error —
`StaticFiles(check_dir=True)` refuses to mount a directory that is not there, and
`scrapex/cli.py:1318` prints the `RuntimeError` verbatim. There was no warning at
build time worth reading and no failing test anywhere.

**Three of the five had been missing since the first release, and only one crashes:**

| what it is | what its absence does |
|---|---|
| `scrapex/webui/static` | `RuntimeError` at `create_app` — **loud, and the one that was reported** |
| `scrapex/webui/templates` | `Jinja2Templates` does **not** check its directory at construction. The engine starts, reports itself healthy, and every page is a `TemplateNotFound` |
| `apps_script/StagingAppScript.txt` | `scrapex/outputs.py:215` returns `""` and the route answers 404 saying the script *"is not bundled"* — a sentence that was true of every engine ever published, and nothing anywhere logs it |

The loud one is the lucky one. Had `static` been bundled and `templates` not, the
release gate would have passed and the panel's Engine page would have called the
engine healthy while no page in it rendered.

**And the fact already existed twice, in disagreement.** `pyproject.toml`
`[tool.setuptools.package-data]` lists the same trees for wheels. Two hand-maintained
lists of one fact, no test comparing them, and the newer one was the wrong one.

**Apply:** the runtime's data files belong in **one named list** —
`packaging/build_engine.py:RUNTIME_DATA` — and a list is only as good as the thing
that reads it. `tests/test_the_frozen_engine_carries_its_own_files.py` stages a
directory the way PyInstaller lays out `_MEIPASS` (modules from the package, then
`RUNTIME_DATA`, and **nothing else**) and starts the engine inside it, so the path
arithmetic under test is the real one and a resource added tomorrow fails in seconds.
Its `*.py` filter is the whole point rather than tidiness: copy the package wholesale
and `static` arrives as a side effect, and the test passes whatever the recipe says.
It carries its own mutation — drop the `static` entry, require Starlette's own words
back — because a staging test that cannot fail proves nothing.

### A static-analysis alert on a TEST can be pointing at a hole in production

CodeQL failed #246 with one high-severity alert:

    py/incomplete-url-substring-sanitization
    tests/test_the_engine_reads_the_same_release_feed.py:63
    The string raw.githubusercontent.com may be at an arbitrary position in the
    sanitized URL.

The flagged line was `assert "raw.githubusercontent.com" in engine_url` — a test
assertion about a constant the code builds itself. **Nothing about it was
exploitable**, and the obvious responses were both wrong: dismiss it as a false
positive, or silence it with a suppression comment.

**The alert was pointing one layer past itself.** The engine had just been given
an updater that downloads `installer.url` out of the release manifest, and
nothing anywhere checked that the URL belonged to us. The published SHA-256
proves the CONTENT arrived whole; it says nothing about WHERE the request went. A
manifest that was mistaken, edited, or served through a compromised path could
name any host, and the engine would request it — sending the user's address
somewhere neither party chose, before a digest was computed. **The absence of the
check was the finding; the test was only where the pattern happened to be
visible.**

The fix in both places is the same and is one line of reasoning: parse the URL
and compare `hostname` exactly. These are the cases a substring accepts and an
exact comparison refuses —

    https://raw.githubusercontent.com.evil.example/x.exe
    https://evil.example/raw.githubusercontent.com/x.exe
    https://github.com.evil.example/x.exe
    https://user:pw@evil.example/github.com/x.exe

**Apply:** when a scanner flags a test, ask what the same mistake would cost in
the code the test is about, and look there before deciding it is noise. And when
the answer is a host check, `urlsplit(url).hostname == "..."` is the whole fix —
`in`, `startswith` and `endswith` are all wrong on a hostname, in that order of
how convincing they look.

**The scheme belongs in the same check.** A digest survives an eavesdropper; an
`http://` installer URL still hands the whole download to anyone on the path and
tells them what is being installed.

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

### Half a composite component is dressed for the half that is missing

`.split-button` is a primary action beside a menu. The dataset card needed only
the menu, so it used the `<details>` half on its own — and got a control whose
`border-radius` computed to **`0 8px 8px 0`**: two rounded corners and two square
ones, because the shared rule rounds the trigger's OUTER edge and leaves the inner
edge flat to butt against the primary button. With no primary button beside it that
is a lopsided box, and it sat on the card's own rounded corner. He photographed it
and called it unprofessional (`REQ-36`, 2026-08-22); he was describing a composition
error, not a colour.

**Apply:** before reusing part of a composite, ask what the missing part was holding
up. The kit has `split-button` (action **and** menu) and `icon-button compact` (no
menu) and **nothing for a bare overflow menu** — so the honest options are to compose
the trigger's dress locally, as `.dataset-card` now does against
`.account-menu-button`'s treatment, or to promote a real component. See
[UI-KIT.md](UI-KIT.md) §UI-4.

**And measure the SHELL, not the element, when comparing two controls.** The border,
the fill and the shadow were never on `.split-button-trigger` — they are on the
`.split-button` wrapper around it. A guard that read `getComputedStyle(trigger)`
reported the card's trigger and the profile page's as identical **on the broken
build**, while the screenshot showed a box round one of them. The guard that works
reads `el.closest(".split-button") || el`. This is the same shape of error as the
z-index one below: the property you are looking for is on an ancestor, and reading
the obvious element gives a confident wrong answer.

### A z-index cannot escape its own stacking context, so raising the number is not a fix

A popover inside a repeated card was painted over by the NEXT card's button, and
what the owner saw was the same button **twice** — once on its card and once
floating over the open menu (`REQ-30`, 2026-08-22). The menu already carried
`z-index: 120`; the card's wrapper carried `z-index: 1`.

**Why:** any numeric z-index on a positioned element makes it a **stacking
context**, and a descendant's z-index is then only ever compared with its
siblings *inside* that context. The wrapper's `1` is what the outside world sees.
Every card's wrapper tied at 1, ties break by document order, and the later card
won. **Measured: the defect survives the menu going to 120, 1200 and
2147483647** — the number was never the variable.

**Apply:** when a popover is clipped or overpainted, look for a numeric z-index on
an ANCESTOR before touching the popover's own, and lift **that** element — only
while it is open, to `var(--z-overlay)`, which is what `.sx-select-list`,
`.account-menu`, `.finance-converter-options` and `webui.css`'s
`.source-filter-menu[open]` all already do. The extension's layers are three
tokens (`--z-sticky: 10`, `--z-overlay: 20`, `--z-modal: 30`); a fourth number
invented at a call site is the next instance of this bug.

**And test it by hit-testing, not by reading the style back.** `elementFromPoint`
at each row of the open menu answers the question a person asks — *what is in
front?* — and an assertion on the computed z-index would have passed on the broken
build, because the broken build's number was already large. Guarded by
`tests/test_panel_dom.py::test_an_open_source_menu_is_not_overpainted_by_the_next_cards_button`,
which also refuses to pass if no button lies under the menu at all: a guard whose
overlap has drifted away proves nothing and must say so rather than go green.

### Choose the stylesheet by WHICH SURFACE EMITS THE CLASS, not by where the neighbours are

`.coverage-open` dresses a button `extension/app.js` emits. It went into
`design/components.css` — the shared sheet — because that is where `button` and the
other card rules live, and `tools/sync_design_assets.py` regenerated it into both
surfaces. Every gate was green except one, and the full suite came back **`1 failed,
3330 passed`** on
`tests/test_ui_kit.py::test_every_shared_component_is_in_the_catalogue`.

**The failing test was the smaller of the two problems.** Chasing it produced a live
example in `design/gallery.html`, which passed — and an adversarial review then measured
the example against the code that emits the class: a `·` separator where `coverageShare`
writes ` (99.8%)`, a whole-number percentage where it writes one decimal, a parent
entry that `_dataset_listing` never puts in `coverage` at all, and a `100%` the
component cannot produce. **A green example that teaches a rendering the code cannot
produce is worse than the red test**, because nothing will ever fail again.

**And the sheet itself was the root.** The engine emits no `coverage-open` anywhere —
`_dataset_listing` builds `coverage` for the JSON API the panel consumes, and no engine
template renders it. So the shared sheet shipped a dead rule to
`scrapex/webui/static/components.css`, *and* levied UI-1's obligation on a component
only one surface has, *and* the catalogue links `tokens.css` and `components.css` only,
so it could not show the component inside the `.dataset-card` it actually lives in. One
wrong choice, three consequences.

**Apply:** before adding a rule to `design/components.css`, grep for the class in the
OTHER surface. No hit means it is not shared vocabulary and belongs in
`extension/app.css` or `scrapex/webui/static/webui.css` — where it needs no catalogue
entry, ships to nobody who cannot use it, and sits beside the component it dresses.
Specificity decides the cascade, not file order: `.coverage-open` is 0-1-0 against
`button`'s 0-0-1, so a per-surface sheet still beats the shared `button` rule.

**And if it IS shared:** the rule is not finished until a live example stands in
`design/gallery.html`, and the pair `pytest tests/test_ui_kit.py
tests/test_design_system.py` is the real gate — neither half is sufficient.
`sync_design_assets.py` is the obvious thing to run after touching `design/` and it says
nothing about the catalogue, because the catalogue is not a generated artefact; it is a
page somebody has to write an example on. Two green signals sat either side of that gap.

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

This project has two instances of a document stating the opposite of the code, and
four further patterns: a **docstring right about the intent and wrong about the
mechanism**; a citation that still resolves but no longer points at what it names; a
GUARD whose own discovery pattern cannot see its subject; and a guard that SKIPS
rather than fails and so reports green while absent. All are recorded below.

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

### A docstring can be right about the intent and wrong about the mechanism, and only a measurement tells them apart

Found 2026-08-20, building the partitioned listing crawl. `snapshotcrawl.py`'s
resume is explained in its module docstring in terms of **requests**:

> a second attempt re-fetched every one of them — on a full pass, hours of requests
> to re-learn what was already on disk. Keeping the evidence and re-fetching it
> anyway is not a resume.

Every word of that is the right intent. The check sits in `store`
([scrapex/snapshotcrawl.py:164](../scrapex/snapshotcrawl.py)), which is the
walker's `on_page` — called **after** the fetch. So the resume saves the INSERT and
saves no request at all, and the docstring's own justification is the one thing it
does not deliver. Recorded as [OP-21](BACKLOG.md).

**What made this different from the two instances above** is that the document was
not stale and was not describing old code: it described the *purpose* correctly and
was never checked against the *effect*. Reading it and reading the code both leave
you satisfied — `run_ref` exists, `already_stored` exists, `skipped` is reported,
the tests pass. It took resuming a nine-page crawl and **counting the requests** to
see it: the second run made exactly as many as the first.

**Apply:** when a docstring justifies a mechanism with a number — hours, requests,
bytes, rows — that number is a claim, and it is testable. Write the test that counts
it. A resume test asserting `skipped` is non-empty passes under this defect; one
asserting the request count does not.

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

### Four shapes of a wrong citation, and the guard only catches one

**2026-08-22.** All four turned up in one afternoon, three of them in documents
written that same day. They are worth separating because **the remedy above fixes
exactly one of them**, and the other three are invisible to it.

| shape | what the reader gets | caught by |
|---|---|---|
| the line does not exist | a hard failure | tier 1 |
| the line **drifted** and still resolves | lands twenty lines early and reasons from the wrong place, with full confidence | `PINNED` — and only for rows someone thought to add |
| the line is **blank** | reads as a formatting artefact, so nobody reports it | nothing, until #256 added the check |
| the file **resolves and does not say the thing** | the reader's trust is spent and returns the wrong assurance | **nothing, and nothing can** |

**The fourth is the worst and it is a different mechanism entirely.** There is no
drift, nothing to re-derive, and re-deriving every line in the repository would
never find it. Three instances, each a *true* claim with evidence pointing
somewhere that does not support it:

- `tests/test_ui_kit.py` justified reading only `design/` and named
  `tests/test_vendor.py` as the guard. The vendored copies **are** guarded — by
  `test_generated_design_assets_are_current` in `tests/test_design_system.py`. The
  conclusion was right and its evidence was not, so **a reader who checked would
  have found less assurance than actually exists.**
- A `settle_view` docstring carried every number justifying its own necessity —
  20/20 reads mid-animation, 7/20 failures, `47.99999237060547` — all measured
  against a test deleted ten days after it was written. It reads as the most
  careful thing in the file and is the least checkable.
- And the instance that produced this table: a session asked to cite `R-48` for the
  extension/engine boundary, when `R-48` did not exist — and when the substitute
  offered to it, `docs/ORCHESTRATION.md`, **resolves and governs something else
  entirely** (how sessions share one `main`, not the split). It refused both and
  cited `docs/PLATFORM-PLAN.md:9`, which is on `main` and says the thing.

**So the rule the fourth shape needs is not about numbers at all:** cite the
sentence, not the file. Paste the words you are relying on next to the reference,
so a reader comparing them can see in one glance whether the source supports the
claim. A citation that names only a path and a line asks the reader to trust that
someone read it.

**And do not build the guard that would catch it.** The shape required is
"resolve every claim about what supports what", which is prose inference — the
design `tests/test_the_documents_cite_what_they_claim.py` measured and rejected in
its own docstring, and the design a session threw away the same morning because
*it decides honesty by adjacency*. **A known gap, named, beats a guard that infers
intent.**

### A guard that reads a whole step cannot tell doing a thing from mentioning it

**Found 2026-08-23 by mutating a gate while writing it, and found three times in
one change** — which is what makes it a rule rather than a slip. Every check below
was written carefully, passed on the real workflow, and passed just as happily on a
workflow with the command deleted:

| the check | what still satisfied it after the command was deleted |
|---|---|
| `"curl -fsS" in step` | `-fsS` on a *different* curl further down |
| `"/static/" in step` | the words `/static/tokens.css` in the REFUSED message |
| `re.search(r"kill\s", step)` | the comment *"even if the kill below fails"* |

**The mechanism is the same every time, and it is a property of good comments.** A
step explains what it does directly above doing it, so the explanation survives
deleting the thing explained. The better the prose, the more reliably it fools a
substring check — which inverts the usual assumption that a well-commented block is
easier to reason about.

**And a fourth was subtler than a comment.** A check for `127.0.0.1:8000` was
satisfied by the *asset* fetch after the *page* fetch was deleted, leaving the gate
greping a `page.html` nothing had written. Not prose that time — a sibling command
that happened to share the substring.

**Apply:**

* **Ask about the COMMAND, not the block.** `_commands()` in
  `tests/test_the_release_proves_the_double_click.py` strips comment lines and every
  presence check reads that instead. Two lines, and it closed three holes.
* **Assert the specific thing, not a substring of it.** Not "some curl has `-f`" but
  *"every curl has `-f`"*; not "a URL on that port" but *"the root, specifically"*.
  A substring is a proxy, and a proxy is what drifts.
* **The only way to find these is to break the thing on purpose.** All four were
  invisible to reading and to a green suite. Twelve mutations were run against this
  one step; four of them passed at first and are now the reason the checks read the
  way they do. **A gate written without mutating it is a gate whose failure modes
  are unknown, not absent** — and this file guards a release, where an unfalsifiable
  check is indistinguishable from a working one until a user finds out.

**This is the same family as [`R-15`'s citations](#r-15s-guard-reaches-only-the-documents-on-claudemds-map-so-a-citation-anywhere-else-must-name-a-symbol)
and it is worth seeing as one thing:** a document that *resolves* can still be wrong,
and a guard that *passes* can still be checking nothing. Both fail by pointing at
something real that is not the subject.

### R-15's guard reaches only the documents on CLAUDE.md's map, so a citation anywhere else must name a symbol

**Found 2026-08-23 by an adversarial review of the packaging fix, in that fix's own
comments.** `packaging/build_engine.py` explained the 0.3.0 defect and cited
`scrapex/cli.py:1301` for the line that prints it. Line 1301 is
`def _force_utf8_output()`. The print is 17 lines away — and **the same change wrote
the correct number for the same fact** in `docs/BACKLOG.md` and `docs/LESSONS.md`.
**The difference was reach, not care**: those two are scanned, `packaging/` is not.

`tests/test_the_documents_cite_what_they_claim.py` iterates a `DOCUMENTS` tuple —
**the markdown documents on `CLAUDE.md`'s map, and nothing else.** And a `PINNED` row
cannot rescue anything outside it, because
`test_every_pinned_document_is_one_this_guard_reads` refuses one on purpose: *"a
pinned citation in an unread document would be checked by tier 2 and invisible to
tier 1 — half a guard, and the half nobody would notice."* So a `file:line` in a
build script, a workflow, or a test docstring **cannot be guarded at all.**

**The drift is not hypothetical and it is not slow.** In this one branch's lifetime a
single prose citation went `611 → 691 → 755`: 691 was computed correctly and then
invalidated by a lesson inserted above it, and 755 arrived when three merges landed
during the rebase. Both wrong numbers **resolved to real, non-blank lines**, so tier 1
and tier 2 passed all three times. A reader following 691 got a paragraph about
palette tokens, which reads exactly as plausibly as one about the layer scale.

**Apply, and it is two rules, not one:**

* **Outside those eight files, cite the SYMBOL** — `` `scrapex/cli.py:_cmd_ui` ``,
  `` `webui.app`'s `STATIC_DIR` ``, `` `main()`'s catch-all `` — never a line. A reader
  greps it, an edit above it cannot displace it, and it needs no guard. Eleven
  citations in `packaging/build_engine.py`, `.github/workflows/release-engine.yml` and
  the new packaging test were converted this way rather than corrected.
* **Inside them, a citation of PROSE needs pinning more than a citation of code does.**
  Code has a symbol to grep back to; a sentence has nothing, so nothing can tell you
  where it went. `OP-49`'s evidence is now a `PINNED` row for exactly that reason.

**And fix numbers AFTER the rebase, never before.** Correcting a line number and then
rebasing — or inserting anything above it — re-breaks what was just repaired. That is
how 691 was written: a correct pass, then a later insert, then a stale correction
sitting where the guard could not see it.

### `str.replace` on no match returns the original, and a print after it will still say it worked

**2026-08-23.** A scratch script added `docs/ORCHESTRATION.md` to the citation guard's
`DOCUMENTS` and reported success. It had added nothing: `#259` had put it there two
merges earlier, so the pattern being searched for — `APPROACHES.md` followed by the
closing paren — was not in the file at all. `str.replace` found no match, returned the
string unchanged, and the `print` on the next line was unconditional.

**The damage was not the no-op. It was the comment written next to it**, claiming the
entry as this change's work and stating that the list "did not" carry the document.
Both false, and sitting four lines below `main`'s own comment saying the opposite. In a
repository whose first rule is that a document which has gone stale is a bug, a
confident false comment is worse than the gap it described.

**Every other edit script in the same change opened with**

```python
assert src.count(old) == 1, "anchor moved"
```

**and every one of those was correct.** The single script without it is the single
script that lied. That is not a coincidence to note in passing — it is the whole
finding: the assertion is not defensive tidiness, it is the only thing standing between
"I changed the file" and "I believe I changed the file".

**And the check that was run could not have caught it.** Before adding the entry, the
guard was run to see whether that document's four citations resolve. They do — and they
resolve *identically whether the entry is present or absent*, because a document not in
`DOCUMENTS` is simply never scanned. **The right method, pointed at the wrong object:**
the question asked was "would adding this break anything", and the question needed was
"is it already there". A green answer to a question you did not mean to ask is the most
expensive kind.

**Apply:**

* **Never `str.replace` without asserting the count first.** `assert s.count(old) == 1`
  before, and where the edit matters, assert the postcondition after — that the new text
  is present, or that the old is gone.
* **A success message must be conditional on the success.** An unconditional `print`
  after a mutation is a claim, not a report.
* **Before adding anything to a list, read the list.** `git show origin/main:<file>` is
  one command, it answers about the base you are actually on, and it would have replaced
  this entire lesson with nothing.
* **Verify the OUTCOME, not the script — and then verify the verifier.** A script that
  lied reads fine, so re-reading it proves nothing; only the resulting file answers. The
  session that caught this one then audited its own ten edits of the day that way and
  found a tenth reporting missing — which turned out to be a bug in *its checker*, a
  needle spanning a line break that could never match. **A false alarm costs trust the
  way a false pass costs correctness**, and both are cheaper to find than to explain.
* **Related, and the same shape one level up:** the guard's own `DOCUMENTS` is what
  decides whether a citation is checked at all, which is why a citation outside it must
  name a symbol — see the section above.

### An instruction that names a version rots on the next bump, and only the person acting on it finds out

Found 2026-08-22, when the owner asked why the panel offered `0.2.1` with the
engine at `0.3.0`. The panel was right, the manifest was right, the workflow was
right; the only engine tag in the repository was `engine-v0.2.1` and no release
had been cut. **What was wrong was the way out.** Six places named the tag
`engine-v0.2.2` — two of them the whole command to copy, three the sentence
telling him to cut it, one a note about a past failure — while
`.github/workflows/release-engine.yml` opens with `test "$tag" = "$version"` and
`VERSION` had moved to 0.3.0. Everything but the last had been dead since #247. It
would have failed at the release's first step, having built nothing, on the day he
finally had time to ship.

*(That paragraph is written as narrative on purpose. Naming the dead tag inside a
copy-pasteable command would make this file a seventh place holding one — see
shape 3 below, which is the guard refusing exactly that.)*

**A citation guard cannot see this.** `docs/BACKLOG.md` cited
`scrapex/version.py:76` — the right file, the right line, the right symbol — and
the *value* on that line had changed under it. Tier 1 checks existence, tier 2
pins the symbol, and neither reads what the symbol is worth today.

**The class:** a document that repeats a number the code owns is a copy, and every
copy is a thing that stops agreeing. Three shapes, in order of preference:

1. **Derive it.** Say *"the tag is `engine-v$(VERSION)`"* and there is nothing to
   rot. Not always possible — a copy-pasteable command needs the literal.
2. **Guard it**, which is what was built here:
   `tests/test_the_release_the_documents_ask_for_is_the_one_that_would_run.py`
   compares every engine tag named **as an instruction** with `VERSION`. It found
   all six copies on the untouched documents before a single mutation was tried,
   which is the only kind of first run worth having.
3. **Write it as history instead.** The guard deliberately matches only the two
   shapes a person acts on — `git tag engine-v…` and `cut engine-v…` — because
   `engine-v0.2.1` shipped the black window and every sentence saying so is true
   for ever. A guard that demanded *every* tag name equal `VERSION` would force
   history to be rewritten on each bump, which is how a test comes to be satisfied
   by a lie.

**And the reason it does not simply ask the hub**, which is where "published"
actually lives: `actions/checkout@v4` fetches no tags, and a network fetch in the
suite is red on a train and vacuously green wherever it is skipped. Both failures
are already recorded in this file under *A skip is not a failure*. The guard
proves the tag he is told to push is the tag the workflow accepts, and says in its
own docstring that it cannot prove a release happened. `Q-16` asks him whether he
wants something that does look.

**IT ENDED IN A RELEASE, WHICH IS THE ONLY OUTCOME THAT SETTLES ANYTHING.** He read
the finding and said *«اقطع الوسم»*; `engine-v0.3.0` went out on 2026-08-22 and the
manifest the panel reads moved from `0.2.1` — where it had sat since 9 August — to
`0.3.0`. That is worth recording because the defect was never in the code: three
sessions had verified the install path and found nothing wrong with it, and what was
wrong was a number written down in six places.

**THREE THINGS THE RELEASE THEN TAUGHT, all within the hour:**

**1 · A completed instruction must be rewritten, not just satisfied.** Every one of
those six places became history the moment the tag existed, and a guard that reads
instructions cannot tell a finished one from a pending one. Left alone they would
have failed at the very next bump — which arrived immediately (below). Shape 3 is not
optional tidying; it is the step that ends the task.

**2 · `cut` is its own past tense, and English will not help you.** `Q-16` was
rewritten with that verb and the tag immediately after it — *"hours later he …
`engine-v0.3.0`"* — which is finished history that the pattern reads as an
instruction. It passed only because `0.3.0` was still `VERSION`, and would have gone
red at the next bump — which was `0.3.1`, already written on another branch.

> **THE RULE, FOR ANYONE WRITING RELEASE PROSE IN THIS REPOSITORY.** A release that
> has happened is written **tagged**, **published**, **released** or **went out** —
> **never `cut`**, and never with `git tag …` spelled out beside it. `cut` and
> `git tag` are the two shapes
> `tests/test_the_release_the_documents_ask_for_is_the_one_that_would_run.py` reads as
> *"a release somebody still has to make"*, and it holds those to
> `scrapex/version.py:VERSION`. Use them for work that is still owed and nothing else.
>
> It is a rule about four words because the alternative is a regex that guesses tense,
> and the cost is asymmetric: the wrong word costs one rewording, while the wrong
> silence costs a release instruction that the workflow refuses at its first step.

Pinned in `test_the_pattern_cannot_tell_the_tense_of_cut_apart`, because a rule that
lives only in a test message is a rule nobody writing prose will meet.

> **AND THIS PARAGRAPH WALKED INTO IT WHILE EXPLAINING IT** — the first draft quoted
> the bad sentence verbatim, verb and tag together, so the entry describing the trap
> was itself matched. Found by mutation, not by reading. That is twice now that an
> entry in this file has had to be written *around* the guard it documents, the other
> being the `git tag …` command a few paragraphs up. **A document that quotes an
> instruction is holding one**, and the elision above is the fix.

**3 · "No release is owed" is a legitimate state, and a guard must permit it.** The
guard originally asserted that at least one instruction existed, reasoning that a
pattern matching nothing measures nothing. After the release the set went empty and
the assertion failed **on the repository being correct**. Non-vacuity now comes from
running the pattern against fixed strings instead — a guard whose only evidence of
working is a live instruction stops being checkable the moment the work is done.

**AND THE NUMBER HAS A SECOND HOME, which a release runbook must name.** `VERSION`
lives in `scrapex/version.py` and is mirrored in `pyproject.toml` because the
installer cannot import Python. Both moved to `0.3.1` for migration `0010` — a
contract change under `R-35`, refused at `0.3.0` by the gate, which is that gate
working — and the primary session reports the mirror's guard firing on it when only
the first was bumped. That guard is `tests/test_version.py:73`, and the words below
are its own: **bump both or neither.** Three copies of one number now exist only if a document adds a
third, which is what this guard is for; the workflow's header comment gave up its
literal for the same reason and now says `engine-v<VERSION>`.

**One consequence to carry forward:** source ahead of published is the *ordinary*
state here, not a repeat of this defect. `0.3.1` in the tree against `0.3.0` on the
hub is development. `OP-32` was three faults at once — nothing released across two
bumps, a published binary silent on a double-click, and documents naming a tag the
workflow would refuse — and a version gap on its own is none of them.

### Two pull requests, DISJOINT IN FILES and COUPLED IN CONTENT, merge into a red `main`

Found 2026-08-22 by two sessions independently within minutes — one rebasing onto
`main`, one on its own branch — which is the strongest thing that can be said for
the guard that found it. `main` at `5f63bb0` was **red**:

```
FAILED tests/test_the_documents_cite_what_they_claim.py::
  test_a_pinned_citation_still_points_at_its_subject[BACKLOG.md-app.py-2710]
```

| | |
|---|---|
| both written against | `4615a14` (#250) |
| #252 added | `("docs/BACKLOG.md", "scrapex/webui/app.py", 2710, "if source_key not in known:")` |
| that symbol at `4615a14` | **2710** — #252 was **correct** |
| #251 added | fifteen lines to `scrapex/webui/app.py` |
| that symbol at `5f63bb0` | **2725** |
| did #251 touch the PINNED table? | **no** |
| did #252 touch `app.py`? | **no** |

**"CHECK WHETHER THE FILES OVERLAP" IS THE REFLEX THAT FAILS HERE, and that is the
whole lesson.** Not one file is changed by both, so git finds nothing to conflict
on and merges both cleanly. The coupling is in the *content*: one moved a line, the
other wrote that line's number down. Disjoint in files, coupled in content — and
only the second half decides whether the pair is safe.

**AND #252 WAS NOT MERGED UNTESTED, which is the part worth getting right.** GitHub
reported it MERGEABLE and CLEAN with every check passing. Those checks ran against
#252's own merge commit **against `4615a14`** — a base that stopped existing the
moment #251 landed. So the suite did not fail to run and did not fail to notice:
**it passed, truthfully, about a `main` that no longer existed.** "Green" without a
base is not a claim about anything.

**Which is why the setting is `require branches up to date`, not `require the check
suite`.** `docs/STATE.md` lists branch protection as his to switch on; *require the
check suite* — the obvious half — would have passed this pair through, because both
checks genuinely passed. Only re-testing against the `main` that will actually
receive the merge catches it. This is the second reason for that setting after
`ac3a5af`.

**Why a citation guard is the detector.** A `file:line` citation is the rare
assertion whose truth depends on a file the pull request does not touch, so it is
the most sensitive instrument for this class in the repository. The class is
general: any test pinning a **line, an offset, a byte count or a row count** is
exposed the same way, and the remedy is never a wider window.

*The repair itself — the PINNED row and `docs/BACKLOG.md`'s prose citation both
moving `2710` → `2725` — landed in `feat/the-profile-page-becomes-columns`, not
here. Two branches editing one table at one place is a guaranteed conflict for
whichever merges second, and only one of them needed to carry it. This entry is the
class; that branch is the fix.*

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

### The check for a leftover mutation ran while the killed harness was still alive

**This is the same failure as the one above, and the guard written for it did not catch
it.** A mutation run was killed by a two-minute timeout. The tree was checked
immediately: `grep` for every mutant string found nothing, so the run was declared clean
and the work was committed.

**`body_class=None` shipped anyway.** The killed process had not finished dying. It
applied its next mutation *after* the grep, and nothing looked again.

What found it, two commits later, was **not** the test named for that behaviour —
`test_the_stored_profile_is_labelled_as_a_profile` asserted `html_codec is not None` and
passed happily with `body_class=None`. It was the **lint gate**, complaining that
`label_for` was imported and unused. A defect caught by an unused import is a defect that
had no test.

Two things follow, and the second is the one that generalises.

**A killed harness has to leave a trace on disk.** `finally` does not run on SIGTERM and
a signal handler is best effort, so neither can be the record. A marker file written at
the start and deleted on a clean exit can be: if it exists and nothing is running, a
mutation is in the tree, and it names which file. The harness now refuses to start while
one is there.

**And a test that survives the mutation it is named for is not a weak test, it is not a
test.** `html_codec is not None` was true either way, because a default codec is still a
codec. Asserting the DECISION — the label actually passed to `save_snapshot` — kills both
`None` and the plausible wrong answer of the listing's dictionary. The rule that comes out
of it: assert the choice, not a downstream effect that something else also produces.

**And do not run a mutation harness in the foreground under a timeout at all.** Background
it. A foreground timeout kills the parent and leaves the work half done, which is exactly
the state no one thinks to look for.

### A mutation harness that trusts `finally` will leave a mutation in the tree

The method above depends on a harness that **mutates the source, runs the tests,
and puts the source back**. The putting-back is the dangerous half, and it has now
failed twice on the same day, in two different disguises:

| attempt | how the restore was written | what killed it | what it left behind |
|---|---|---|---|
| first | a `for` loop in **bash**, restoring after each mutation | the tool's two-minute timeout | a mutation in `scrapex/sightings.py` |
| second | a **Python** script restoring in `finally` | the same timeout | `outside = []` in `scrapex/partitioncrawl.py` |

The second is the instructive one, because `finally` *looks* like the fix for the
first. It is not. **A timeout arrives as `SIGTERM`, and Python's default
disposition for `SIGTERM` terminates the interpreter without unwinding the stack**
— so no `finally` block runs, no `atexit` handler runs, and the file stays
mutated. `try/finally` protects against exceptions, which is a different hazard
from being killed.

What it leaves behind is the worst possible artefact: **the check whose guard was
under test, deleted**, in a working tree where every other test still passes. The
next thing to run is a full suite that reports green on code with a hole in it, and
`git diff` shows a one-line change that reads like something you meant.

Two protections, and both are needed:

```python
def _on_signal(number, _frame):
    print("restored:", restore())
    sys.exit(128 + number)

for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGBREAK):
    signal.signal(_sig, _on_signal)
```

and **run the harness in the background**, where no timeout is counting. The
handler is the belt; the background is the braces. And after any mutation run that
did not print its own `restored: True`, **grep the tree for the mutations** rather
than assuming — that check is what caught this one.

### A mutation harness needs a control run, or every result it prints is a guess

Six mutations, six kills, `all 6 killed`. The harness was passing its subprocess
`env={"PYTHONPATH": ..., "PATH": ""}` — and an empty `PATH` breaks `anyio`'s backend
lookup at import time, so **every** run crashed identically before collecting a test.
Each crash was a non-zero exit, each non-zero exit was read as a mutant dying, and the
report was unanimous and worthless.

**The missing piece was one run of the unmutated tree**, under exactly the command and
environment the mutants get:

```python
control = run_tests()
if control.returncode != 0:
    raise SystemExit("the clean tree does not pass; every result below is meaningless")
```

The clue was there and easy to skim past: the per-case line printed no `N passed`
summary, because there was no summary to print. **A kill is only evidence when the same
harness can demonstrate a pass.**

### And the anchor a mutation replaces has to be UNIQUE, or it mutates something else

`str.replace(old, new, 1)` takes the FIRST match in the file, and
`"    if not outcome.provably_complete:"` matched twice — once at four spaces as the
gate being tested, and once at **eight** spaces as a per-cell note, because a
four-space anchor is a substring of an eight-space line. The note got mutated, the gate
was never touched, and the harness reported a survivor that did not exist. Two hours
were nearly spent strengthening a test that was already correct.

Both failures point the same way, and it is the opposite of the intuitive one:

| the harness said | what was true |
|---|---|
| `all 6 killed` | nothing ran at all |
| `1 SURVIVED` | the mutation never reached the code under test |

**So a mutation result is a measurement and needs its instrument checked.** Three cheap
assertions catch all of it: the clean tree passes; the anchor occurs **exactly once**;
and the file is byte-identical to the original after every restore. Without them the
harness reports with total confidence in both directions — which is worse than not
running it, because a false `killed` retires a real concern.

**And the third assertion collides with the second.** Comparing BYTES is what makes the
restore check trustworthy — `read_text()` normalises newlines, so a text comparison can
report a clean restore over a file whose line endings changed. But reading bytes means
the anchors are matched against CRLF, because `.gitattributes` sets `* text=auto` and
Windows checks out `

`. Every anchor written with `
` then finds nothing, and the
harness says `anchor occurs 0x` about code that is plainly on the screen. Translate the
ANCHORS to the file's line endings; normalising the file would rewrite every line in it
and defeat the restore check the bytes were for.

### And a restore can be perfect on disk while the INDEX still holds the other version

The sibling above is about the *file*. This one is about the thing beside it, and it
surfaced on 2026-08-22 taking a before/after screenshot pair.

To photograph the old look, the script checked two files out of `origin/main`,
shot them, wrote the saved text back, and compared hashes — normalised for CRLF,
as this file already insists. It reported restored, and the files WERE byte-perfect.

`git checkout <ref> -- <path>` **writes the index as well as the worktree.** So the
staging area still held `origin/main`'s copy of both files while the worktree held
the branch's, and the next `git add` of unrelated paths would have committed a
partial revert of the branch's own work.

What caught it was `git status`, in a form worth recognising on sight:

```
MM extension/app.js        <- staged AND unstaged changes to one file
MM extension/app.css
```

**Apply:** a harness that reaches for `git checkout <ref> -- <path>` must restore
**both** halves — write the file back *and* `git add` it (or use
`git show <ref>:<path> > file`, which never touches the index and is the better
tool for the job). Verify with `git status --porcelain`, not with a content hash: a
hash of the worktree is blind to the index by construction. And read the two-letter
status codes rather than skimming for filenames — `MM` and ` M` mean different
things, and only one of them is what you expected.

### And `restored: True` can be true while the file on disk has changed

The harness proves it restored by comparing what it wrote back:

```python
return SRC.read_text(encoding="utf-8") == original
```

That comparison **cannot see a line-ending change**, because `read_text` opens in
text mode and universal newlines turns `

` into `
` on the way in. Both sides
are normalised, so both sides match — while `write_text` has meanwhile translated
every `
` back to `

` on Windows. A run that reports `restored: True` can
therefore leave a file whose **452 lines all changed ending**.

On this repository that surfaces as the confusing pair:

```
git status  ->  M tools/crawl_muqawil_listing.py
git diff    ->  (nothing)
```

`.gitattributes` sets `* text=auto`, so `diff` normalises the endings away and shows
an empty change, while `status` still reports the file modified. Nothing was wrong
with the content — measured: identical after `b"

" -> b"
"` on both sides — and
`git checkout --` on the file settles it.

**This is CLAUDE.md's second trap seen from the other side.** That one says never hash
a tracked file's raw bytes, because CRLF-vs-LF makes equal files look different. This
is the same fact making *different* files look equal: **normalise when you are asking
"is the content the same", and compare bytes when you are asking "did I put the file
back".** The two questions have different right answers, and one function cannot serve
both.

### A byte-perfect restore still leaves the mutation running, because `__pycache__` believes it

Found 2026-08-22, mutating the release-instruction guard. The harness restored
every file by writing the **original bytes** back and verified each restore by
**re-hashing the file on disk** — the strongest form of the check the lesson above
argues for. All eight mutations reported `restored=True`, `git status` showed
`scrapex/version.py` unmodified, and the file said `VERSION = "0.3.0"`.

**And `import scrapex.version` said `0.4.0`.**

```
grep '^VERSION = ' scrapex/version.py   ->  VERSION = "0.3.0"
python -c "import scrapex.version as v; print(v.VERSION)"  ->  0.4.0
```

The `.pyc` written while the mutation was in place was still being trusted.
CPython invalidates a cache entry on the source's **mtime and size**, and a
mutation that swaps one version string for another of the same length, restored
inside the same filesystem timestamp tick, changes neither. The cache was valid by
its own rule and wrong by every other.

**What it cost, and why the post-control run is not optional.** Every mutation
after M2 ran with an extra test failing for a reason nobody had asked for, and the
one whose kill criterion was that same test could have reported KILLED over a
mutation that did nothing. The only thing that caught it was running the guard
**again after the whole set finished** and finding it red on a clean tree — the
check LESSONS §8 already insists on, catching a cause it had not met before. Both
runs are recorded rather than only the good one: eight KILLED with a red
post-control is a result to throw away, not to report.

**The rule: purge `__pycache__` between runs, not just the source.** A restore is
not complete until everything derived from the mutated file is gone too. With the
purge in place: eight mutations, eight killed, post-control green.

---

## 9 · A measurement is only as good as the instrument

### A witness that compares the wrong thing certifies nothing, and looks fine doing it

The muqawil completeness proof rests on one check: after reading a slice, re-fetch its
first page and confirm the listing never reshuffled underneath. As designed
([DEC-11](BACKLOG.md)) that check was **"byte-identical"**.

Measured: a re-fetched page whose contractor ids came back in the **exact same order**
was **not** byte-identical. The body carries per-response noise. So the comparison would
have failed on every slice, every time — and a witness that always fails does not raise,
it simply never certifies anything. The crawl would have run for hours, discarded and
retried each slice forever, and reported no completeness at all, while every line of it
worked as written.

**Compare the thing the claim is about.** The claim is *"the ordering did not change"*,
so the comparison is the id sequence. The bytes are a proxy that is strictly stronger
than the property, and a proxy stronger than the property is not a conservative choice —
it is a check that can never pass.

### A proof that demands more than it needs fails exactly where it is needed most

2026-08-21. `partitioncrawl` had one completeness rule: a cell is complete when its
witness held **and** its distinct ids equalled the declared count. The witness proves
the pages were read inside one cache generation, so they were disjoint.

**A cell above the generation's reach can never satisfy that, by construction.** The
first real crawl measured six such cells — worst 236 pages against a 31-page ceiling —
and reported a deficit of **3,690 with no route to close it**. Not a bug in the code;
the rule itself had made those cells unprovable.

**And the second proof was there the whole time.** A cell that declares `N` rows
cannot show `N` DISTINCT ids unless it has shown all of them, and the ids may be
accumulated over any number of reads. No generation, no witness, no single pass. Both
proofs rest on the same assumption — that the paginator's `N` is true — so the witness
adds no *completeness* the count does not.

**What made it hard to see is worth more than the fix.** The module docstring stated
the opposite as settled fact — *"the union can reach N by luck across two generations
and that proves nothing"* — and a test was named
`test_a_union_across_two_generations_is_not_a_proof` and asserted it. Nine guards and
twenty-one killed mutations all agreed with each other, because they were all
checking the same wrong rule. **Mutation testing cannot find a mistake in what you
decided to prove**; it only checks that you still prove it. The error surfaced only
when a live run produced a deficit and the question became "how would we ever close
this?"

**Apply:** when a check combines conditions with `and`, ask which of them the claim
actually needs, and what class of input the extra condition excludes **permanently**.
An over-strict proof reports false negatives, and a false negative on a completeness
claim looks exactly like missing data — so it sends someone hunting for rows that were
never lost. Both proofs are now computed, and the report says which one carried each
cell (`[by witness]` / `[by count]`), because a claim whose grounds are invisible is a
claim nobody can re-check.

### A stop condition that measures progress must exclude the work it replays

**A resumed crawl gains nothing new, by design.** The partitioned crawl stores each
page it fetches, so resuming a cell reads its ids back **off disk** rather than off the
wire — that is the point of it. The dry-stop then compared `gained == 0` and concluded
the site had nothing left:

```
region_id_1-company_size_verysmall: 3,125 of 4,699, D=1,574 [3 attempt(s), 5 requests]
```

**Five requests, and it declared the cell exhausted.** Two of the three attempts were
pure replay. The five heaviest cells all stopped this way, and the run *looked* correct
— it reported its deficit honestly, it just never went and asked. The tell was in the
report all along: `3 attempt(s)` beside `5 requests` cannot both be true of a cell
holding thousands of rows, and nothing was comparing those two numbers.

The fix is one clause in two places — an attempt counts as dry only if it **asked**:

```python
asked_the_site = attempt.pages_read > 0
dry = dry + 1 if number > 1 and asked_the_site and gained == 0 else dry
```

`went_dry()` needed the same filter, because a stop condition evaluated in two places
is two stop conditions. Afterwards: **631 new contractors in 727 pages, `D` 633 → 2.**

**The general shape.** Any "we are done because nothing changed" test is invalid over
work that is *defined* to change nothing. Cache hits, replays, no-op migrations,
idempotent writes: they satisfy the condition without being evidence for it. Gate the
condition on the work having actually happened, and make the two numbers — attempts
and requests — sit next to each other where a reader can see them disagree.

### Measure whether the server sends a validator before designing around `304`

`fetch_validator` held **0 rows after 727 fetched pages** and the obvious reading was a
wiring bug. One request settled it instead:

| header | muqawil.org sends |
|---|---|
| `ETag` | **absent** |
| `Last-Modified` | **absent** |
| `Cache-Control` | `no-cache, private` |

It is a Laravel application minting a fresh `XSRF-TOKEN` per response. There is no
stable entity to validate, `no-cache` says so, and an empty table is **correct
behaviour**. An hour of debugging a working feature was one `urlopen` away.

**The cost is that a written plan carried a false premise.** It said conditional
requests are *"what makes maintaining 48 columns affordable"* — and on this source they
are worth nothing. A recurring pass re-downloads all 34,806 pages in full. What
survives is the half that never needed the server: `R-20` compares `content_hash`
**after** the fetch, so an unchanged page still writes no revision. Bandwidth is not
reducible here; history and storage already are.

So: **a server-side optimisation is a property of the server, and it is one request to
check.** Do it before it becomes a line in a plan, and keep the client-side half
separate — that half works everywhere.

### A facet's controls may not be a `<select>`, and its null class may have a value

Two beliefs about muqawil's listing were recorded from a search of its `<select>`
elements, and both were wrong in a way that changed the plan:

- **`company_size`, `user_type` and `rating_stars` are radio inputs.** They were written
  down as having "no `<select>` in the listing at all", which was true and read as *no
  filter exists*. Their values were in the page the whole time.
- **`city_id`'s `<select>` is genuinely empty** — but only because an endpoint fills it.
  `var citiesUrl = …/contractors/cities` sat in the same page's jQuery, four kilobytes
  from the empty element. **The stored HTML answered a question we had recorded as
  needing new evidence.**

And the one that mattered most: summing a facet's values fell **1,437 short** of the
whole, which looked like proof that 8.3% of contractors were unreachable by any filter.
They were reachable — `region_id=0` returns exactly that set, exactly that size. **A
facet's "not set" class can be addressable, and the way to find out costs one request.**

Both of these are the same mistake with two faces: **an absence found by one instrument
was reported as an absence in the world.** Before recording that something cannot be
done, name the instrument that failed to find it.

---

## 10 · Two features written two days apart, neither knowing the other exists

### The merge moved the pages and left the key to reading them behind

`snapshotbody.py` landed on 2026-08-20 and stores a page as a zstd frame compressed
against a **dictionary row**, without which the body cannot be decoded and the plaintext
exists nowhere else. `warehousemerge.py` landed on 2026-08-22 and moves "only the
evidence" between two machines. Both are correct on their own. Together they were not:

- `snapshot_dictionary` was **not merged at all**, and
- `html_dict_id` was **copied verbatim** — a foreign machine's primary key, which the
  merge's own docstring says never crosses.

His real transfer hit it: 20,379 pages, every one `zstd-raw-dict`, arriving into a
warehouse holding zero dictionaries → `FOREIGN KEY constraint failed`.

**AND THE LOUD FAILURE WAS THE LUCKY ONE.** The foreign key only fired because the
receiving side had *no* dictionaries, so the arriving ids pointed at nothing. Had the
receiver held two dictionaries of its own — which it will, the moment it crawls anything —
ids `1` and `2` would have been perfectly legal numbers naming **the wrong bodies**. No
constraint fires on that. 20,379 pages would have been "merged" successfully and decoded
to garbage, discovered whenever somebody next opened one.

### What the seventeen passing tests could not see

`test_two_warehouses_become_one.py` had seventeen tests, including a sharp one about
`seen_count` being summed instead of maxed. **All seventeen passed before the fix and
after it**, because not one of them stored a *compressed* page — every fixture wrote
`html_content` as plain text through raw SQL.

> **A test suite for feature B, written while feature A already existed, tests the
> author's mental model of A rather than A.** The fixtures here were written by hand
> against the columns the author was thinking about. The new tests go through
> `save_snapshot` — the production writer — so the row is shaped by the code that really
> writes it, and a future column arrives in the fixture without anyone remembering to add
> it.

### The generalisable rule

**When a feature moves, copies, backs up or exports rows, list the table's foreign keys
and ask what happens to each one.** Not "does it round-trip" — that passes — but *does
the destination hold the thing this column points at, and is the value still true there?*
An id is only meaningful inside the database that issued it, and the merge already knew
that; it just did not notice that a column added two days earlier had made a second id
travel.

The matching key is worth stating too, because the obvious one was wrong: dictionaries
match on **body**, never on `label`. Each machine seeds a dictionary from the first page
of that kind *it* fetched, so `muqawil.org/listing` is a 298,954-byte page here and a
different page there. Matching on the label would have merged two unrelated dictionaries
into one and broken both sides' pages.

---

## 11 · A page you measured once is a page you have not measured

**2026-08-22.** He said it in the middle of the work, and it was the most useful
sentence of the session:

> «المعلومات غير ثابته ولا متفقثة بين الصفح يعنى ممكن تلاقى معلومات تانية وطريقة عرض
> مختلفة»

*The information is neither fixed nor consistent between pages — you may find other
information and a different presentation.*

Everything this repository believed about the muqawil profile page came from **two
committed fixtures**, which are one contractor. That was honest and it was labelled:
`R-19` says *"The limit of this evidence, stated plainly: one contractor."* The
problem is not that the limit was unrecorded. **The problem is that the conclusions
outlived it** — they were written into a module docstring, a declaration and a plan,
where nothing carries the caveat.

Measured over **2,419 real profile pairs** read out of the running crawl, four
written statements were wrong. Not stale: wrong.

### 1 · A regex that chunks "until the next id" is not a DOM subtree

The premise: the self-build price table lives in `div#contractor-tab4`, the pane the
tab button `التقييم الفني` points at.

The measurement that produced it chunked the HTML with

```python
re.compile(r'<div[^>]*id="(contractor-tab\d+)"[^>]*>(.*?)'
           r'(?=<div[^>]*id="contractor-tab\d+"|\Z)', re.DOTALL)
```

On a page whose tab4 is **empty**, that chunk does not stop at the pane — it runs on
into everything after it. So the price table, which sits in a `section-card` of its
own several elements later, read as "inside tab4". Asking the same question through
`BeautifulSoup.select('div#contractor-tab4')` gives **zero tables on 2,360 of 2,360
pages**.

**The tell was there and it was ignored:** the same census reported *15 distinct
shapes* for that one pane, and 12 of the 15 contained the string `Interests` — the
name of a card that is not in the pane at all. A shape count that explodes is a
selector that is wrong, not a site that is inconsistent.

### 2 · Naming the heading level hides a card

The first card census asked for `h3.card-title` and `h2.card-title`, and reported
**two** section titles per page. The page has seven. The price card's title is an
**`h4`**, so the card that no document in this repository had ever named was also the
card the census could not see.

`_CARD_TITLE_TAGS` now lists `h1`…`h6` and the level is never named.

### 3 · The dash in a bilingual cell was a hierarchy separator

`contractors.write_groups` recorded the licensed-activities cell as carrying *"BOTH
languages in one string with no separator"* and concluded that splitting it *"needs a
script-boundary rule"*. Half right, and the wrong half was load-bearing.

There **are** separators in that cell. They are inside each language and they
separate **levels**:

```
تشييد المباني - تشييد المباني - جميع الأنواع Construction of Buildings - Construction of Buildings – All Types
└──────────── a three-level Arabic path ────────────┘└──────── the same path in English ────────┘
```

A parser that split on the dash would have cut a path into pieces and called each
piece a language. The real boundary is the **first Latin letter**, and it is provable
rather than plausible: the script-run signature of all 1,500 activity cells measured
is `AL` — Arabic, then Latin, exactly one transition.

**And the site's own English is wrong on 100 of 1,685 rows** — 30 truncated to
`Civil Engineering -` (the same string for two different activities) and 70 naming a
*different activity* altogether. The lucky property, which is why nothing has to
recognise an activity to be safe: **all three defects change the number of levels**,
so comparing level counts catches every one.

### 4 · Two vocabularies that look like one, and fuse at the root

Interests and licensed activities are both trees of construction activities and the
obvious move is one `classification_scheme` for both. Measured:

| | English paths | Arabic paths |
|---|---|---|
| Interests | **211** | 214 |
| Licensed activities | **19** | 21 |
| exact overlap | **0** | 2 |

Zero English overlap, because the site writes `Civil engineering` in one and `Civil
Engineering` in the other. But their **Arabic roots do overlap**, and
`taxonomy.ensure_path` is idempotent on `(scheme, parent, node_name_ar)` — the Arabic
name is the identity. One scheme would have matched the licence root to the interests
root, let the licence leaves hang under a node whose English name came from the other
vocabulary, and produced a tree that is neither. Nothing would have raised.

### What to do instead, and it is cheap

**Declare what the page publishes, and let the page contradict the declaration.**
`PROFILE_CARDS` names all seven cards and `undeclared_cards()` reports any
data-carrying card that is not among them. It costs one tuple. It turns "the site
grew a section" from something nobody notices into something a test says out loud.

Two details of that guard were themselves decided by measurement rather than taste:

- **The contractor's own name is a card**, and its title differs on every page, so it
  must be excluded or the guard reports thousands of unknowns on its first run.
  Position said *"card 0"* and was wrong on **40 of 5,668** pages; content said
  *"carries no table and no list"* and was wrong on **0**. Content won, and the cost
  is stated in the docstring: a new **text** card would not be reported.
- **`read_licensed_activities` needs one page, not two.** The cell is already
  bilingual, so a profile whose Arabic half never arrived still yields its licences —
  unlike interests, which pair across locales by position and can raise.

**And measure the failure path before you trust the count.** Two things would have
stopped a 34,834-page approval dead, and both were measured before the parser was
wired rather than after: interests paired in **2,252 of 2,252** pairs, and the info
box carried **11 distinct labels, all of them known** — no field was being silently
dropped. Neither number was known when the profile parser was declared finished.

---

## 12 · A register id is renamed by a sweep, never by an edit

**Measured on this branch on 2026-08-22, twice in one afternoon.** Two pull requests
merged while it was open and took every id it had reserved: `#252` took `REQ-30` and
`OP-42`, then `#254` took `REQ-31`, `REQ-32` and `OP-43`. So one entry was renumbered
twice — `OP-42` → `OP-43` → `OP-44`, and `REQ-30` → `REQ-31` → `REQ-33`.

**Both times the heading moved and a reference did not.** The survivor was a link
inside the `OP` entry's own body pointing at its `REQ` twin:

    [REQ-30](REQUESTS.md#req-30--the-dataset-cards-said-no-successful-crawl-over-crawled-rows)

Every part of that line is wrong in a way nothing catches. The **text** names a
different request — `REQ-30` is the duplicated `⋮` button — and the **anchor**
resolves to nothing, because no heading slugs to it any more. The citation guard does
not see it: `tests/test_the_documents_cite_what_they_claim.py` checks `file:line`
citations, and this is a markdown anchor. The board guard does not see it either:
`test_the_request_board_matches_its_entries.py` compares the board against the
entries, and this link is in neither.

**Why a targeted fix is not enough, and this is the part worth keeping.** A sweep by
SUBJECT — every line mentioning the work, checked for the right id — found the one
above and **missed a second**, because the surviving reference was a comment about
`SUFFIXES` that never names the subject at all. What found it was the opposite
question: take every id the diff introduces and print the heading that number
actually names today. A number that names something else is the defect, whatever the
prose around it says.

So, when a register id changes:

1. `grep` the id, not the subject. The subject is what a rename does not mention.
2. Check the **anchor** as well as the text — `#req-nn--slug` is a second copy of the
   number and it rots silently, because a dead markdown anchor is not an error.
3. Resolve every id against the register's headings afterwards, and read what each
   number names. That is a two-line script and it is the only check that cannot be
   fooled by wording.

**And the same shape applies to line numbers, which this branch also carried three
times.** `app.py:2710` → `2725` → `2787` in one day: `#252` measured it correctly on
its own base, `#251` had already moved the symbol, and `main` went red between the two
merges with no conflict for git to find, because no file was changed by both. Re-read
the number out of the file at the new base on every rebase. Never adjust it by
arithmetic, and never carry it.

---

## 13 · A test named in a docstring is a citation, and nothing was checking it

**The documents are guarded and the tests were not.** `R-15` put every `file:line`
in `CLAUDE.md`, `ENGINEERING.md` and `docs/` behind
`tests/test_the_documents_cite_what_they_claim.py`. A test docstring saying *"this
is why, see `test_foo`"* is the same kind of claim and had nothing behind it at all.

**THE DATES ARE THE ARGUMENT, and they kill the obvious excuse.**
`test_the_engine_overflow_trigger_has_no_visible_resting_container` was added by
`8796fb5` on **2026-08-10** and removed by `ce80886` on **2026-08-20**, when the
Engine page's overflow menu became action rows and the trigger it measured stopped
existing. **Three references outlived it.** A ten-day-old test accumulated three
dangling citations within two days of dying. Nobody can call that neglect over a
long period: they were wrong almost immediately, and nothing noticed.

**And the number in the first draft of that sentence was "nine months", written
from an assumption and corrected by running `git log` before it was pushed.** That
is the fourth time in one afternoon a session caught its own claim by measuring it
rather than by being contradicted. Measure the thing you are about to assert, even
when — especially when — it is only the connective tissue of a sentence.

### `settle_view` is the case that proves the class, not an example of it

The worst of the three was in the docstring of `settle_view`
([tests/test_panel_dom.py:161](../tests/test_panel_dom.py#L161)) — a helper used at
four call sites, one of them the guard `#252` added. Its docstring **is** the entire
evidentiary basis for the wait: 20/20 runs reading the box mid-animation, 7/20
failing outright, height `47.99999237060547` = 48 − 2⁻¹⁷ at one float32 ulp. Every
one of those numbers was measured against the deleted test, so a reader who doubted
the wait had **nothing they could re-run**.

Its own first line reads *"a wait with no visible cause is a wait the next reader
deletes."*

**A docstring that argues for its own necessity, on evidence nobody can check, is
exactly what this class produces.** It reads as the most careful thing in the file
and it is the least verifiable.

### Facts kept, references repaired — not paragraphs deleted

Neither comment was **wrong**. The clamp it named is real and still in the sheet —
`button, .button { min-height: var(--control-height) }`
([design/components.css:378-380](../design/components.css#L378)), applying to every
bare `<button>`, which is why a rendered box alone cannot catch a height
regression. The 47.5 incident happened. What had gone was the ability to **check**
either.

So the temptation on finding a dangling citation is the trap: **deleting the
paragraph throws away a true fact in order to fix a broken pointer.** Repair the
pointer. Name the commit that added the test and the one that removed it, say
plainly that it is gone, and point at the `git show` that still produces it.

### The guard reads the claim, not the prose around it

The first version of the guard forgave any dead name sitting near the words
*"renamed from"* or *"no longer exists"*. It was thrown away, and the reason is the
sharpest form of a trap this repository keeps meeting: **it decides honesty by
adjacency.** It would pass any dead name that happened to fall near the word
"removed" and fail an honest one phrased differently.

What replaced it is the shape already settled twice here — `PINNED` in the citation
guard and `RESERVED` in `tests/test_the_registers_cannot_collide.py`: **a
deliberate exception is DECLARED, not inferred.** A historical name goes in
`HISTORICAL` ([tests/test_the_tests_name_tests_that_exist.py:86](../tests/test_the_tests_name_tests_that_exist.py#L86))
with the ref to read it at, and every row is **verified** rather than trusted —
`git show <ref>:<path>` must still produce the test
([tests/test_the_tests_name_tests_that_exist.py:144](../tests/test_the_tests_name_tests_that_exist.py#L144)).

That verification caught its own author on its first run: the row for the
native-host test named `6ccdd3c`, which does not contain it. The commit that does
is `ff21042`. **A row asserting where to find something is itself a claim, and it
rots like any other.**

### Two collection facts, learned from the gates rather than guessed

* **`pytestmark = ()` is not how to say "no marks".** pytest unpacks it and
  collection dies with `got () instead of Mark`. Say it in prose instead.
* **The extension gate keys on the browser directory's name appearing anywhere in a
  test file's text** — including in prose explaining that the file does *not* read
  it. That is a guard reading text and concluding intent, which is the same shape
  as the keyword version rejected above; the difference is that this one is
  deliberately broad, and its own note says a false positive "costs one marker".

  Here the marker would cost the guard: carrying it moves the file into the tier CI
  runs **separately**, so a guard about test docstrings would stop running on
  engine-only and docs-only changes — which is precisely when docstrings change.
  So the prose avoids the name, the same trade already taken in
  `tests/test_the_version_moves_when_the_contract_does.py`. **Two independent
  tenants make that a practice rather than a preference**, and the reason is
  written at the top of the guard, where someone will try to "fix" it by adding the
  marker.

**Apply, for this class:** when you delete or rename a test, grep `tests/` for its name before you
commit — `test_the_tests_name_tests_that_exist.py` now does it for you and fails
with the file and line. When you cite a test as your reason, prefer citing the
live rule or file it rests on: `design/components.css:378-380` outlives any test
that measured it.

### The general form: a claim survives being wrong wherever nothing checks it

This is not really about test files. **Four instances turned up on one day, in four
shapes, and the only thing they share is that no check covered the place the claim
was written** — ordered worst first, because the first one punishes the reader who
does the right thing:

| the claim | where | why nothing caught it |
|---|---|---|
| the design system's copies are guarded by `tests/test_vendor.py` | `tests/test_ui_kit.py` | nothing checks a claim about **where a guard lives** |
| a document joins the map, so it joins the checked list | the citation guard's own `DOCUMENTS` | the sentence was a comment, enforced nowhere |
| three docstrings naming a deleted test | `tests/` | the citation guard reads documents, not tests |
| three citations resolving to a **blank line** | `docs/BACKLOG.md` | tier 1 asks only that the line *exists* |

**The first is a different failure from a dangling reference: it is a MISDIRECTED
one, and it punishes diligence.** That comment justified reading only `design/` —
*"so reading the canon is reading both"* — and named the wrong file. `test_vendor.py`'s
only byte-equality assertion compares the two vendored copies of Tabulator. The copies
**are** guarded, by `test_generated_design_assets_are_current` in
`tests/test_design_system.py`. So the conclusion was true, the evidence pointed at
nothing, and **a reader who checked would have found less assurance than actually
exists.** A dangling reference wastes a reader's time; this one spends their trust and
returns nothing. The careless reader was unaffected.

**The second is the guard doing it to itself, which is why it is second.** The comment
above `DOCUMENTS` reads *"if a document joins that map, it joins this list"* —
and `docs/ORCHESTRATION.md` joined the map in `#257` without joining the list, so the
one document that tells a session how to merge had its citations checked by nothing,
while the comment promised otherwise. Found by reading the map against the list rather
than trusting the sentence. **A rule written as a comment is a rule with nothing behind
it, however well the comment is written.**

**And it is the first failure again, one level up: not a citation pointing at the wrong
line but a GUARD pointing at the wrong scope.** The guard was not merely silent about
that file — it was *affirmatively misleading*, because a reader who checked the comment
would have concluded the file was covered. Misdirection is the worse half of this class
wherever it appears, and it appears at every level: in a comment about where a test
lives, in a comment about which guard covers what, and in a guard's own statement of
what it reads.

**And what this section's own guard does NOT catch, said plainly.** The first instance
is a reference to a test *file*, not a backticked test *name*, so it falls outside the
pattern. It was fixed by hand and left unguarded on purpose: the shape that would catch
it is *"resolve every claim about which guard covers what"*, which is prose inference —
the design `tests/test_the_documents_cite_what_they_claim.py` measured and rejected in
its own docstring, and the same design thrown away here for deciding honesty by
adjacency. **A known gap named beats a guard that infers intent.**

**Recording is not building, and this section has its own instance.** The misdirected
pointer above was found in the morning, written down, and left for hours while three
other things were fixed. It cost nothing this time. Two of his requests went the same
way on the same day — briefed to a session, acted on correctly, and never reaching
`REQUESTS.md`, which is exactly the failure `C7` exists to prevent and `REQ-04` is
named after.

**Apply, generally:** when you write down why something is true, ask which check
would fail if the reason stopped being true. If the answer is *none*, you have
written a claim that will outlive its evidence — and the more carefully it is
written, the longer it will survive.

---

## 14 · A measurement that outlives its base — and the instance that was a live process

This is the family §12 keeps meeting from one direction, §13 above from another, and
`docs/ORCHESTRATION.md` §4 from a third: **something true when it was measured, still
being read as current after the thing it measured moved.** Six instances are tabled
below and the sixth broke a rule the other five could not, so it gets the section — then
building the fix produced a **seventh**, recorded at the end because it is the only one
of them caught by its own author before it shipped.

**Every row below was re-derived at `f1844af`**, not copied from a brief — and saying
which base is the whole discipline, so this line moves whenever the table is re-checked.

| # | the artefact | the base it outlived | what caught it |
|---|---|---|---|
| 1 | a `PINNED` citation, `app.py:2710` | `#251` moved the symbol to `2725`, then `2787` | a red `main`, after both merged clean |
| 2 | a `RESERVED` register row | the branch it named moved off the number | a session **asking who held 44** |
| 3 | `docs/STATE.md`'s own opening line | five bases in one afternoon | the line correcting itself, again |
| 4 | three docstring citations of a deleted test (§13, `#259`) | the test died ten days after it was written | a session **asking what else is unguarded** |
| 5 | a published `.exe` (`#244`, `afb8648`) | the fix landed after the build | the owner, meeting a black window |
| 6 | **a running process** | the checkout moved 199 seconds after it started | **nothing. He found it.** |

*(One more was described to this session — a verification table still quoting a
superseded commit — and is **not** listed, because the commit it named appears nowhere
in this repository at `f1844af`, and an instance that cannot be re-derived is not
evidence. That is this section's own rule turned on its own source.)*

### The sixth instance, measured

2026-08-23. The owner's panel said **"no successful crawl yet"** under **17,304 rows**.
`#255` (`bcb8f6e`) had fixed exactly that two days earlier and the fix was on `main`.

| fact | value |
|---|---|
| process answering `127.0.0.1:8000` | `pythonw -m scrapex.cli ui --port 8000` |
| it started | **07:35:44** |
| the checkout left `451468d` for `31c369e` | **07:39:03** (`.git/logs/HEAD`, epoch 1787459943) |
| delta | **+199 seconds too late** |

**Python imports a module once.** A long-lived engine started from an editable install
holds the tree that existed at import time for as long as it runs. The tree this one
held still carried the literal `#255` removed — in `451468d`'s copy of
`scrapex/webui/app.py`, at line 650 of **that** commit, `"last_success": None`. The
disk had the fix; the process did not; the panel was reporting faithfully.

*(**Written that way on purpose, and this paragraph is the section's own subject in
miniature.** Prefixing a commit to a path and then a colon and a line number produces
a span that `tests/test_the_documents_cite_what_they_claim.py` reads as a claim about
the file **on disk today** — where that line is now a bare `continue`. Tier 1 checks
only that the line exists, so the guard passes it and the reader lands nowhere. Worse,
a remap script run over these documents will helpfully renumber it on the next edit,
which is how a historical fact quietly becomes a false present-tense one. It happened
here: a first draft of this entry carried that span, an automated re-derivation moved
it, and it also moved `app.py:2710` in §12 — corrupting the very sentence whose
subject is that 2710 became 2725 and then 2787. **A historical line number is written
in prose — "line 650 of that commit" — never in the shape that means "current",** and
`git show <commit>:<path>` is how a reader gets there. This is the third time an entry
in this file has had to be written *around* the guard it documents; the other two are
the `git tag` command in §7 and the past tense of `cut`.)*

**AND THE VERSION STRING WAS NO HELP, WHICH IS THE STRUCTURAL PART.** `/api/health` and
`/api/version` both answered `"version": "0.3.0"` — **truthfully**, because
`engine-v0.3.0` *is* `451468d`. One string was being asked to separate three things:

    the published engine-v0.3.0 build
    a source checkout sitting at that tag
    a process that imported that tree and kept running while the disk moved on

And it cannot, **by design rather than by accident**. `R-35` moves the engine's number
on a *contract* change, so many trees share one number on purpose. Counted: **ten
commits report `VERSION = "0.3.0"`** — every tree from `e963269` (#247) to `31c369e`'s
parent (#257), one of them the release tag. **A string ten trees share cannot name one
of them**, and it was the only self-description the engine had.

### What makes this one different, and it is not a detail

**The artefact was not a document, a table or a test log. It was a live process — so
the check that catches it cannot be a citation guard.**

Every remedy this repository had built for this family reads *text at rest*:
`tests/test_the_documents_cite_what_they_claim.py` reads a `file:line`,
`test_the_release_the_documents_ask_for_is_the_one_that_would_run.py` reads a tag named
in prose, `test_the_registers_cannot_collide.py` reads headings. **There is no line of
prose here to check.** The stale thing was bytes in RAM, it existed only while the
process ran, and it left no trace on disk — so the only possible instrument is one that
lives *inside the artefact* and answers *at run time*. That is
`docs/ORCHESTRATION.md` §5's argument — *move the check into the artefact so nobody has
to remember to look* — arriving at its limit case.

**AND #244'S GATE, WHOSE OWN TITLE IS *"the gate could not tell"*, COULD NOT TELL EITHER.**
Worth stating precisely, because it looks like it should have. What it added
(`.github/workflows/release-engine.yml`, *"And it must speak when a person double-clicks
it"*) runs the freshly built `.exe` and greps three sentences out of its stdout. The
step beside it claims more than it can deliver: *"the answer must be the number on the
tag — which also proves the binary carries the source that was checked above, and not a
stale build."* That is true **only inside that job**, because the binary was built from
that checkout seconds earlier. Both checks are build-time, one-shot, and their subject
is a subprocess that has just started. Neither has any representation inside the
long-lived process the build produces. **#244 proved that a new artefact speaks; it
added nothing that lets a running process say which bytes it loaded.**

> **THIS IS A DIFFERENT FAILURE FROM THE ONE #244'S TITLE NAMES, and the distinction
> is the reason this section exists.** #244 is about an artefact **built** before its
> own fix. This is about an artefact **running** after its own fix. The words are
> nearly the same and the instrument required is not: one is checkable at build time
> by asking the thing you just made a question, and the other is checkable only from
> inside a process that has been alive for hours. **A reader who concludes that #244
> already covers this will not build the thing that catches it** — which is exactly
> what a session did conclude, before measuring what that gate reads.

**And its scope is smaller than it looks, which matters if you go there to read it.**
Of the three tests usually named as #244's, only
`tests/test_the_frozen_engine_can_start_itself.py` is (`afb8648`); the other two are
#154 (`756fa39`) and #253 (`5364c82`). #244's own additions are that test, the
double-click workflow step, and `tests/test_the_release_proves_the_double_click.py`.

### The remedy, and why "restart" was never the missing piece

`scrapex/provenance.py`. The engine seals a snapshot of what it loaded on
`create_app`'s last line — the only moment at which every module it will serve with is
imported and none of them can have changed yet — and compares it against the disk on
demand. Two answers, because they fail independently: **`stale`** (a loaded module's
file no longer matches, which needs no git and is the exact defect) and **`moved`** (the
checkout is on another commit, which is what gives the answer words a person can act
on). It rides `/api/health`, which the panel polls, and lands on the Build row under
*Installed version* — the row that could not tell the three states apart.

**A frozen build answers `None`, never `False`.** A one-file `.exe` carries no `.git`
and no source tree; its modules live in a per-run temp directory that says nothing
about whether newer code exists. `False` there would tell the owner his engine is
current on the one build where we cannot know. This is the discipline `/api/health`'s
worker block already states — *"Unknown is now said as unknown, and the reason for not
knowing travels with it"* — and it is pinned by a test asserting `stale is not False`.

**The defect was never that a restart was needed.** `POST /api/engine/restart` has
existed the whole time and its docstring reads *"Replace this engine with one running
the current code"*. **Nothing said a restart was owed**, and nothing could have: the
route had no way to know whether it was needed and no way to report afterwards whether
it worked. Detection and honest reporting, not hot-swapping — a live-reload mechanism
would have hidden the fault instead of naming it.

### The operational fact that decided the remedy

**The crawl was a separate process.** The engine was PID 35036; the crawl was PID 35340,
started 07:36:45 as `contractors --details --run-ref profiles-2026-08-22 --workers 6`.
Restarting the engine therefore did not touch it — which is the only reason the fix
could be applied at all while 17,304 rows' worth of work was in flight. Had the crawl
run inside the engine process, the remedy for a stale engine would have been "lose the
crawl", and the honest report would have had to say so.

### And a citation shape the guard cannot see at all, found while fixing this branch

Not part of the incident, and it is recorded here because **this branch is what
demonstrated it.** A continuation citation — a bare `` `:NNN` `` inheriting its path
from a full citation a few words earlier, as in
`` (`extension/app.js:1602`, `:1641`) `` — **is invisible to
`tests/test_the_documents_cite_what_they_claim.py`.** `CITATION` requires a path before
the colon, so it matches `app.js:1641` and does not match `:1641`. Measured, not
reasoned: the regex returns a match for the first string and `None` for the second.

**Nineteen of them exist** in the guarded documents at `f1844af`. What this branch
proved is that they move silently: edits here shifted `extension/app.js` by eight lines,
four continuation citations went with it, **the guard stayed green through all of it**,
and they were found by reading the diff by hand. That is the *drifted-and-still-resolves*
shape — except the remedy for that shape, a `PINNED` row, is structurally unavailable,
because tier 1 never discovers the citation in the first place and so there is nothing
to pin.

**Stated honestly, because the distinction decides whether anyone should act:** at
`f1844af` **none of the nineteen is wrong** — all resolve to non-blank lines, and the
one spot-checked in full — the `docs/STATE.md` sentence citing
`scrapex/features.py:54` and `:65` for two lit feature flags — names the `True` on
both lines correctly. (That document's own line number is deliberately not quoted
here: this branch edits `docs/STATE.md`, so the number would move inside the very
pull request describing the problem.) **So this is a latent structural gap, not a live
defect**, and the class pre-dates this branch even though the four silent movements
were this branch's own.

**The remedy that avoids the trap this repository keeps falling into.** The obvious
guard — inherit the path from the nearest preceding citation — is *deciding by
adjacency*, which has now been measured and rejected twice here (the prose-inference
tier in the guard's own docstring, and the keyword allowlist §13 threw away). The
non-inferring fix is the opposite: **forbid the continuation form** in guarded
documents. Require every citation to name its path, which is one mechanical rule, and
nineteen invisible citations become nineteen that tier 1 and `PINNED` already handle.
Filed as `OP-61` rather than built here, because rewriting nineteen citations across
five documents is a second change with its own conflict surface.

*(There is a table of **four shapes of a wrong citation** that this would be the fifth
row of. It is not cited above because it is **not on `main`** — it lives on
`origin/docs/the-boundary-becomes-a-ruling` at `c6d9212`, unmerged. Whoever lands that
branch should add the row; `OP-61` carries the finding until then. Citing it as though
it were here would be this section's own subject, one paragraph after describing it.)*

### And the branch produced a seventh instance, inside the test file about the family

**Worth one paragraph because it was caught by its author before it shipped, which none
of the other six were.** The test proving that a module imported *after* the seal is
noticed set its fixture's mtime from a module-level `time.time() + 3600`, **evaluated at
collection**. Collection happens once and that test runs much later, so any run taking
over an hour to reach it would have compared against a moment already in the past and
failed on correct code. The local suite is about twenty minutes and CI thirteen, so it
would never have fired *today* — which is the reasoning this whole section exists to
refuse. It now derives the base from the seal the test itself just took
(`_SNAPSHOT.sealed_at + 60`), at the moment of use.

**A measurement that outlives its base, written into the file whose subject is
measurements that outlive their base.** Reading an entry is not the same as applying it
— the same conclusion §7 already reached about its own overreach, and the reason
[APPROACHES.md](APPROACHES.md) A5 became [R-17](RULINGS.md#r-17--a-fix-is-adversarially-reviewed-before-it-is-written).

**Apply, and this is the general rule every instance above shares:** ask what the base of
every claim is, and whether the claim can still be read after that base has moved. When
the answer is *yes*, the fix is to make the claim carry its base or re-derive it
(§12, `ORCHESTRATION` §4). **When the artefact is a process rather than a file, no
amount of re-deriving helps — the artefact has to be able to answer for itself.**

---

## 15 · An assertion that lists the allowed answers passes when every answer is wrong

**Measured 2026-08-26, reviewing the plan that moves the source page into the
extension.** Three guards were examined and all three were the same defect wearing
different clothes: *the expectation was retyped beside the thing it guards instead
of derived from it.* Retyped expectations do not merely go stale — they go stale
**silently and in the safe-looking direction**, which is why none of the three had
ever failed.

### The instance that is worst, because the column exists to prevent guessing

`observed_state` exists on his instruction — «عمود يوضح الحالة الجديدة لا تدع
المستخدم يستنتج الحالة». The test covering it
([tests/test_a_dataset_is_a_table_like_any_other.py:869](../tests/test_a_dataset_is_a_table_like_any_other.py#L869))
asserts membership:

```
assert row["observed_state"] in {"new", "updated", "confirmed", "returned",
                                 "absent", "unsighted", "retired", "unavailable"}
```

`unsighted` is in that set. So a table where **every single row** collapsed to
`unsighted` is green. And there is a live path that does exactly that:
[scrapex/extract/service.py:915](../scrapex/extract/service.py#L915) resolves the
identity field as `identity[0] if len(identity) == 1 else None`, so a dataset with
two `key_part` fields — or zero — yields `None`, every row's `external` is `None`,
every sighting lookup misses, and the whole column is wrong with nothing to say so.

**Two facts make this a lesson rather than a hypothetical.** `grep -rn "key_part"
tests/` returns **zero** — the identity resolution has no test at any arity. And the
comment two lines above the collapse names the trigger: *"`contractor_id` is
muqawil's answer; Balady's and the UAE's will not be."* The next source is the
event, and `docs/BALADY-ENG-OFFICES.md` and `docs/UAE-SOURCES.md` are already
written.

### The general form, and the cheap test for it

**An assertion whose right-hand side is a SET is only as strong as the worst member
of that set.** Ask of any such assertion: *if the code returned this same value for
every row, would this still pass?* When the answer is yes, it is measuring that the
code produced a string, not that it produced the right one.

The fix is not a bigger set. It is asserting the value a **named** fixture must
produce — one row that is genuinely `confirmed`, one genuinely `unsighted` — so the
mapping is checked rather than the vocabulary.

### The same shape twice more, both closed the same way

- **The payload contract.** `test_it_answers_every_key_the_grid_reads` asserted
  thirteen keys typed into the test. `grid.js` reads ten, and three of the thirteen
  it never reads. Worse, it opens no file, so a **new** `payload.x` read in `grid.js`
  failed no test — the crash the docstring names was the one case it could not see.
  Closed by deriving both sides from the artefacts
  ([tests/test_the_table_payload_answers_every_key_its_readers_read.py](../tests/test_the_table_payload_answers_every_key_its_readers_read.py)),
  the mechanism `R-15`'s citation guard already established.
- **CI's browser floor.** `.github/workflows/ci.yml` said it in its own comment —
  *"a per-file 'at least one' would not have noticed 48 becoming 1"* — and then
  applied a real number to one suite of ten. `test_grid_dom.py` (20) and
  `test_tab_page_dom.py` (10), the two suites that draw the Data page, sat on `-ge 1`.

**So the rule generalises past tests:** a guard that states its own reasoning and
then applies it narrowly is more dangerous than one that never stated it, because
the stated reasoning reads as coverage.

## 16 · Reading the renderer is not drawing it, and the gap was one word wide

**Same review, and it cost ten minutes rather than an afternoon only because a
harness existed.** `grid.js` pushes the moved-column card into
`detailSections.get("specifications")`, so a test written from the source waits for
`[data-inspector-view="specifications"]`. It times out: the record panel renders
**exactly two** view buttons, `details` and `history`. "specifications" is a
*section inside* Details, not a view of its own — a distinction invisible in the
line that names it.

**And a second one in the same test.** The card's heading is upper-cased by CSS, and
`innerText` reports the transformed text, so `"Moved out of the table" in panel` is
false while the card is plainly drawn. A behavioural assertion must not be able to
fail because a stylesheet changed its mind about capitals.

**Apply:** when a gate says *"the card appears"*, the only thing that can prove it is
a browser. Both misreadings above were made while looking directly at the correct
line of source, which is the argument the plan makes for its own harness — the Data
page shipped **broken** once with 2,460 engine and 398 extension tests green on it —
arrived at again from the other end.

**And the corollary that is easy to skip:** the negative control must open the same
view as the positive test. Asserting "no card" against a panel whose section was
never opened passes for the wrong reason, and an absent card and an unopened section
are indistinguishable from outside.

---

## 17 · Three findings that only a caller, a mutation, or a count could have produced

All three lived in one plan's checklist rather than here. Each was found by running
something rather than by reading it, which is why nothing in the suites named them.

### 1 · A compression ratio measured against a dictionary drawn from the same sample is a self-comparison

`STORAGE.md` recommended `zstd` + one real page as a raw dictionary on a measured **187×**
for listings. Counted on the finished warehouse — 20,683 listing pages, 500 sampled, decoded
through `scrapex/snapshotbody.py:193` — the shipped ratio is **46.3×**. The profile figure
held (46× projected, **51.7×** measured); only the listing one moved, and it moved 4×.

**The mechanism, stated as unproven:** the 187× came from 40 pages sharing a near-identical
skeleton, with the dictionary page taken from among them. Production spans 56 city×size
cells whose filter markup differs. **The choice of codec is still right** — 46× beats every
alternative in that table — but the number that argued for it was not a prediction.

**The cheap test:** if a dictionary, a fixture or a baseline comes out of the same sample it
is scored against, the score is an upper bound, not an expectation. Draw it from outside, or
say which it is.

### 2 · Two sequences paired by position are a guess unless something proves they are the same length

`enumerate(detail_urls(page))` handed the index to `belongs_to_slice`, which indexes listing
**rows** while `detail_urls` yields **URLs** (`scrapex/pagesource.py:183` and `:187`).
Right only when a page yields one URL per row. muqawil yields one per **locale**: measured on
a stored page, **17 cards and 34 URLs**, so url index 1 was contractor 0's Arabic page being
asked about card 1 — a different contractor — and **17 of the 34 indices pointed past the
last card** and were silently dropped. A slice would have fetched a set that is neither the
slice nor its complement, and it reads as a smaller city.

**Two reasons nothing caught it.** Nothing used the slice path, and **every fake in the
walker's own slice tests yields one URL per row** — the single case the assumption fits.
Fixed by having the source pair each URL with its row (`detail_rows`,
`scrapex/sites/muqawil.py:292`) and by making `belongs_to_slice` **refuse** a row past the
last instead of answering `False`, which is what made the overshoot invisible. **0 mismatches
of 34** on the same real page; six mutations killed.

### 3 · A line that reads like protection and cannot fail is worse than no line

A `retired` guard at the top of the departure loop was dead code: both branches already
named the status they act on. **A mutation deleted the guard and every test passed.** It was
removed, with the reason written where it had been — because the next reader would have
treated it as the thing keeping retired rows safe.

**And the opposite case, from the same loop, is why "delete dead guards" is not the lesson.**
A nested outcome reports `provably_complete = True` *correctly* — the flag is a claim about
its own `scope` — so the `nested` check beside it **is** load-bearing: without it one cell's
proof delists the rest of the country. Two lines that look alike; one cannot fail and one is
the only thing standing between a proof and a false delisting. **The test is a mutation, not
a reading.**

### 4 · A test that compares a literal timestamp against `now` asserts nothing after that date

`tests/test_a_dataset_is_a_table_like_any_other.py` pinned the newest crawl at
`2026-08-21T12:00:00Z` and set only the last row's `first_seen_at` to it, expecting one
`new` row. The other rows kept whatever `stored()` wrote — **`now`** — and `row_state`
returns `STATE_NEW` on `first_seen_at >= newest`. At 13:28Z that is true of every row.

**Proved by moving the stamp and nothing else:** `2026-08-21T12:00:00Z` → **FAIL, 3 new**;
`2027-08-21T12:00:00Z` → **pass**.

**It does not heal overnight, and that distinction is the whole cost.** `now` only
increases, so the comparison is true for ever from 12:00Z that day. #243's own comment
called it a dependency on the *time of day* — true of 2026-08-21 alone. **Told it is
time-of-day, a reader waits for the morning, and the morning never fixes it.** `main` was
red from then on, and `release-engine.yml` runs the suite before it builds, so `OP-32` —
the release he had asked for — could not ship while it stood.

**The repair is to pin both sides**, not to move the literal: the `last_seen_at` lines two
above already did, and `first_seen_at` pinned one. Three mutations killed, **two of them in
production code** — a test edited into passing would have survived those.

**The sweep, so this is a class and not an anecdote:** the other 13 test files holding a
hardcoded 2026 timestamp pass every value to `row_state()` explicitly, so no `now` is
involved, and **no future-dated literal exists anywhere in `tests/`** that would arm the
same bomb for a later date. Every such literal is a date on which the suite changes its mind.

## 18 · Three checks of my own that reported the wrong thing, on live data

All three passed. All three were measuring something other than what their label said, and
two of them were about the warehouse the owner actually uses.

### 1 · Two migration streams share numbers, so `LIKE '0013%'` is a false positive

Checking whether `0013_two_versions_may_share_a_shape_across_time.sql` had reached his
warehouse, `SELECT 1 FROM database_migration WHERE migration_name LIKE '0013%'` returned a
row. It was **`0013_marketlens_database_identity.sql`** — a different stream, with
`0010_view_region.sql`, `0011_retention.sql` and `0012_pins_must_match_an_observation.sql`
sitting beside their engine namesakes in the same ledger.

The contradiction is what saved it: `user_version` said 12 while the prefix check said
applied. **Compare a migration by its full filename, never by its number** — and when two
readings disagree, neither is the answer until one is explained.

### 2 · A count that ignores `generic_record.status` measures a population nobody asked about

Verifying step 1, a query counted rows joined to a retired `dataset_schema_version` and
printed *"live rows bound to a RETIRED version: 14 — must be 0"*. All fourteen were
`status='retired'` — `OP-64`'s impostor pages, which the design deliberately leaves on `v3`.
The number that matters adds `AND g.status = 'active'`, and it was 0.

**A retired row and a live row are not distinguished by which version they point at.** Any
count over `generic_record` that omits `status` is counting history as if it were current.

### 3 · A pipe swallowed a real exit code again, in the same session that wrote the rule down

`scrapex contractors … | tail -30; echo "DRY_EXIT=$?"` printed `DRY_EXIT=0` for a command that
had not run at all — `scrapex` was not on that shell's `PATH`. `$?` was `tail`'s.

This is `§8`'s false-green wearing a third face, and it appeared **after** the guards for the
first two were merged. `status=$?` on the line immediately after the command, before anything
else runs, is the only form that survives.

### And the one that was not mine: the restart button cannot move the engine to newer code

`POST /api/engine/restart` relaunches from `Path(__file__).parent.parent` **of the running
process**, so it perpetuates whichever checkout the engine was born in. His engine had been
serving from an unmerged worktree for hours. Full measurement in `OP-88`; the reason it
belongs here too is that the route answers `ok: true` with a new pid, which reads as success.

## 19 · Three ways a mutation run lied about itself, all in one afternoon

A guard is untrusted until the defect it names makes it red. That rule is only as good as
the harness, and this harness reported three different falsehoods before it reported a
number worth quoting.

### 1 · CRLF: every single-line anchor matched and every multi-line one silently did not

The harness read the file, searched for an anchor, replaced it, ran the suite. Nine
mutations; three reported killed and six reported *"anchor appears 0 times"*. The three
that worked were the three whose `old` text was a **single line**.

`.gitattributes` sets `* text=auto`, so the repository stores LF and Windows checks out
CRLF — trap 2 of `CLAUDE.md`, which is written there about **hashing** and bit a mutation
harness instead. Normalise `\r\n` → `\n` after `read_bytes()` and restore from the
captured bytes, never from the normalised text.

**What made this recoverable rather than a false 3/3:** the harness distinguishes *"the
suite stayed green"* from *"the anchor never matched"* and calls only the first a survivor.
A harness that just ran the suite and checked for red would have reported three kills out
of three attempted and been believed.

### 2 · A syntactically invalid mutation goes red for the wrong reason

One mutation deleted `return int(` from the head of a multi-line expression and left the
closing `).rowcount)` behind. The module stopped importing, **every** test in the file
errored, and the run was red — so a harness checking only the exit code would have counted
it as a kill. The named test was not among the failures, which is the only reason it was
caught.

**So a mutation needs two assertions, not one:** the suite must go red, *and* the specific
test that names the defect must be among the failures.

### 3 · `IN ()` is legal SQLite, so a guard against it cannot fail

`_confirm_seen` was written with `if not record_keys: return 0` and a comment saying an
empty `IN ()` would be a syntax error. Deleting that guard left every test green, which is
the signature `_rows_unchanged` already records one screen above — *"a line that read like
protection and could not fail."*

Measured on SQLite 3.50.4: `UPDATE t SET d = 'new' WHERE k IN ()` is **accepted**, matches
nothing, and reports `rowcount` 0 — exactly what the guard returned by hand. The guard is
gone rather than kept behind a corrected comment, and the test now pins the behaviour,
which holds either way.

---

## 20 · Copying a design system copies its accessibility failures too, and four ways a default can be a fiction

*Written 2026-08-28, building `REQ-48` / [R-71](RULINGS.md#r-71--an-appearance-is-a-whole-design-system-and-supabase-is-the-default-one).*

The task was to add a `supabase` appearance and make it the default. Five of the things that
made it hard were not in the request, not visible from the code, and each is the kind of
failure this file exists for: **the tree keeps working and something stops being true.**

### 20.1 · The reference system's own values failed guards this repository already enforces

The instinct with a published design system is fidelity: copy the values. Measured against
`tests/test_panel_dom.py`'s existing contrast gate, three of Supabase's own values do not
clear it — **against their own backgrounds**, not against ours:

| their value | measured | the guard needs |
|---|---|---|
| focus ring (`--primary` at 55%, flattened) | **1.47:1** on their `--background` | 3:1 |
| `--border-stronger` | **1.57:1** light, **1.53:1** dark, on their own `--card` | 3:1 |
| `--warning` | **2.68:1** on their own published `warning-300` tint | 4.5:1 |
| brand green on white | **1.99:1** | — |

A faithful copy would have shipped three accessibility regressions **and** been the palette
the owner sees first. The last row is the load-bearing one: because the brand green is
1.99:1 on white, `accentContrast` has to be **near-black in both schemes** — which then
forces the switch thumb dark too, since white on their `brand-500` is 2.63:1 against a 2.9
floor.

**The rule:** where a reference value fails, hold the reference's own *hue and chroma* and
move only the lightness. Their `--warning` is `oklch(0.68 0.14 75)`; hue 75 and chroma 0.14
were kept and 0.68 became 0.52, which is 5.14:1. The divergence is then one number with a
reason, not a new colour.

**And say WHICH values are quotations.** Supabase's docs publish token *names* with no
values. The stepped ramps are real HSL literals in their packages; every semantic colour is
computed at runtime in OKLCH from about ten scalar inputs, so **no hex exists to copy** and
each one has to be derived by evaluating their expressions. Every value in the palette entry
is marked `PUBLISHED` or `derived`. Before the derivations were trusted, the OKLCH→sRGB
conversion was checked against five known values and reproduced all five.

**One more thing a reference can be wrong about: itself.** Third-party token extractors, and
Supabase's own `packages/config`, still name `Circular` as the brand face. It is a dead
self-referential `var()` fallback — the live stack across every one of their apps is Inter,
Manrope and Source Code Pro, all OSS. The licensing problem that would have blocked the
typography half **did not exist**, and only reading their app-level CSS showed that.

### 20.2 · A registry that carries only colour cannot carry a design system, and the count is the proof

`THEME_PROPERTIES` was 36 entries: **shape 0, typography 0, spacing 0, elevation 0, motion
0.** So *«لن يكون الوان فقط»* — not colours only — was not a bigger palette entry, it was an
axis that did not exist. A session that read the request as "add a row to `PALETTES`" would
have produced a recoloured UI and reported a design system.

**Count the properties before agreeing to the adjective.** «كامل» is checkable: 107
properties in `tokens.css`, 71 beyond the registry's reach, 53 that a design system must
override, of which 3 must stay unreachable by a recorded decision.

### 20.3 · Four ways a "default" was already a fiction

**`DEFAULTS.palette` was unreachable.** `deviceColors` defaults to `true` and `apply()`
returns early on that branch after `clearTheme()` — no `data-palette`, no properties. So
`github` had never been the default anybody saw, for as long as the setting has existed. A
rename would have satisfied the request in the register and changed nothing on screen.

**A hard-coded parametrize list is a hole, not a list.** The contrast guard read
`["whatsapp", "github"]`, so a palette added to the registry was simply never
contrast-tested — and under `R-71` the **default** would have been the untested one, with
nothing anywhere saying so. Derived from the registry it went from 68 assertions to 102.
Same shape in the hover sweep's four hard-coded pairs.

**Two literals made two tokens unreachable.** `--control-bg` was `#171b21` in both dark
blocks and is not a `THEME_PROPERTY`, so no palette ever reached a dark control background —
WhatsApp's dark surface is `#182229` and GitHub's `#151B23`, and neither ever arrived.
`--shadow-lg` spelled its colour as a literal while both siblings derived from
`--shadow-color`. **A token that exists is not a token that reaches anything**, and the
cheapest check is to grep the token's own name in the dark blocks as well as the light one.

**And 48 rules spelled a token's value by hand.** `--radius` moving 9px → 6px changes
nothing at `border-radius: 9px`. A design system a rule does not consume is decoration.

### 20.4 · The cross-surface divergence that reports nothing and retries forever

Adding a palette the server did not know produced **no error anywhere** and a permanent
2-second write loop. The chain, worth reading once because every link is ordinary:

1. `set()` stores locally, so the panel looks correct.
2. `pushRemote` POSTs; the server raises 400.
3. `pushRemote` returns `response.ok` from inside a `try` — and **both call sites discard the
   return value.**
4. `pullRemote` keeps polling. Its GET answers **200** with `{"appearance": null}`, so
   `consecutiveFailures = 0` runs every tick and the `QUIET_AFTER_FAILURES` backoff **never
   engages** — the backoff counts *transport* failures, and there weren't any.
5. `!remote && current.updatedAt` stays true, so every tick POSTs again. Forever.

**A success on the read path can hide a permanent failure on the write path.** And the suite
could not have caught it: the only POST in it sent an accepted palette and expected 200, and
one other sent nonsense and expected 400 — a pair whose verdict is identical either way.
`tests/test_the_appearance_registry_agrees_across_both_surfaces.py` is the answer, and it
reads the JavaScript rather than holding a third hand-written list, because a third list is
the defect.

### 20.5 · Three self-inflicted ones, kept because they are the cheapest to repeat

**A sweep whose pattern matches less than it claims reports a clean run.** The script that
re-derived shifted citations parsed the `PINNED` table with a regex accepting only
double-quoted expected strings. Four rows are single-quoted *because their text contains a
`"`*. Those four stayed stale and the run printed success. **Assert the parse count against
something independent** — it now compares against the number of tuples the table opens, and
that check is what turned 42 parsed rows into 57.

**And the same sweep silently CORRUPTED a citation, which is worse than missing one.** A
`path:369-371` range is two numbers, and rewriting `path:369` inside it produced
`path:380-371` — a backwards range that no guard checks, because both the blank-line test
and the `PINNED` test read only the first number. It survived two green runs and was found
by reading the file. **A line-number rewrite has to recognise ranges**, or it turns a
correct citation into a nonsensical one while reporting success. Two documents carried it.

**Recording history and making a citation are different acts, and this repository spelled
them the same way.** `ORCHESTRATION.md` documents past citation drift as
`webui/app.py` :2589 → :2604. Growing `app.py` by 28 lines made old line 2589 blank and the
blank-line guard failed **on a sentence that was never wrong** — correcting the number would
have falsified the record. A space before the colon breaks the `path:line` shape and keeps
the meaning. Three sibling numbers in the same sentence were latent instances of the same
false positive. *(And writing the offending form out as an illustration failed the guard a
second time.)*

**Pointing a hard-coded value at "the token it already equals" can be wrong.** The
Sign-in-with-Google rule spelled `font-size: 14px`, which is exactly `--fs` — a free win by
every mechanical test. Google's branding guidelines fix that button's type size, its own
guard asserts the literal, and Supabase moves `--fs` to 15px. **The same reasoning that
keeps the three `--google-btn-*` colours out of the palette applies to its type size**, and
only the guard connected them.

### 20.6 · When the guard cannot run locally, run its formula by hand first

`tests/test_panel_dom.py` needs playwright, which `importorskip` skips on this machine. So
**CI would have been the first thing to discover that Supabase's focus ring is 1.47:1.**
Transcribing `_contrast` and its 17 pairs into a scratch script and running the proposed
palette through it *before* writing it into the source found two failures and cost minutes.

The scratch script asserts on `REQ-48` in `docs/REQUESTS.md` — a string added in this
session — rather than on `__file__`, per the trap in `CLAUDE.md`: `__file__` catches a
misdirected import and never a misdirected read.
