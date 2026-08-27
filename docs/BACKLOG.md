# ScrapeX — what we found: open problems, debt, and decisions not yet built

Written **2026-07-29**. This file exists because decisions kept getting lost between
sessions. It is the single place where the project's *state* lives: what is settled, what
is broken, what was approved and never built, what shipped but nobody has confirmed, what
we deferred on purpose, and what is waiting on the owner.

It is **not** an architecture guide. It does not explain how the code works. Every entry
carries its evidence — a commit hash, a `file:line`, a number measured against the live
warehouse, or the owner's own words. Anything I inferred rather than verified is marked
**(inferred)**.

> ### ⚠ It is no longer the ONLY tracking document — read this before adding an entry
>
> A documentation system was built on **2026-08-17** ([R-09](RULINGS.md#r-09--one-documentation-system-in-the-repository-all-english)),
> and it starts at [../CLAUDE.md](../CLAUDE.md). Three registers now exist, and the
> test for where a thing belongs is **where it came from**:
>
> | it came from | it belongs in |
> |---|---|
> | **the owner asked for it** | [REQUESTS.md](REQUESTS.md) — `REQ-nn` |
> | **we found it** — a bug, a debt, a duplication | **this file** — `OP-`, `DEC-`, `DEBT-` |
> | **a decision was taken** | [RULINGS.md](RULINGS.md) — `R-nn` |
>
> **The overlap that stood here is resolved.** §1's `SR-1..SR-23` and
> `RULINGS.md`'s `R-nn` were both registers of his rulings, because `RULINGS.md`
> was written without reading this file. He ruled on **2026-08-19**
> ([R-16](RULINGS.md#r-16--one-home-for-rulings-and-it-is-this-file),
> [REQ-09](REQUESTS.md#req-09--one-home-for-rulings-not-two)): the `SR-` rules moved
> to `RULINGS.md` keeping every number, and **a new standing rule goes there, never
> here.**
>
> Also note the live state of the work has moved to [STATE.md](STATE.md), which is
> kept current per **C2**; the "Repository state" block below was last re-measured
> on 2026-08-12 and its own warning about drifting numbers applies to it again.

**Repository state — re-measured 2026-08-12**

| | |
|---|---|
| `origin/main` | `4fcc14f` — *Check the chooser owners are actually sent to, every day (#179)* |
| working tree | clean |
| suite | 1,830 engine · 570 extension · 181 node · 2 skipped · 1 xfailed · ruff and eslint clean |
| branches | **148 local / 128 remote** — see **DEC-7**, and note the number keeps being quoted stale |
| live warehouse | `~/.scrapex/engine/scrapex-engine.db`, **119.2 MB** · **90,013** price observations · **17,471** offers · **12** sources, 7 active · **59** migrations applied · 122 crawl jobs |

> **The numbers above were wrong for two weeks.** This block described 2026-07-29
> until today: a branch that no longer exists, a 75 MB warehouse that is now 119,
> nine sources that are twelve. Every figure in this file was re-measured on
> 2026-08-12 by six agents reading the code and the live database rather than
> reading this file; what they found is in **§6d**. Where an entry's own numbers
> were wrong they are corrected in place and the old figure is kept beside them,
> because a number that drifted once will drift again and the drift is the
> evidence.

**How to read an entry.** Every entry has a stable ID (`SR-`, `OP-`, `DEC-`, `BV-`,
`DEBT-`, `Q-`). IDs are never reused; when something is finished, move it to §7 and keep
the ID. Sections are ordered by consequence, not by category — data-correctness sits above
cosmetics everywhere.

---

## 1. Standing rules — MOVED to docs/RULINGS.md

**`SR-1`–`SR-23` left this file on 2026-08-19** for
[RULINGS.md](RULINGS.md#standing-rules--the-data-product-and-process-policy-sr-1sr-23),
on the owner's ruling
[R-16](RULINGS.md#r-16--one-home-for-rulings-and-it-is-this-file).
**Every number is unchanged** — an `SR-` cited in this file, in another document, or
in a test still means what it meant.

They moved because his rulings were in two registers at once: this §1 since
2026-07-29, and `RULINGS.md` since 2026-08-17, which was written without reading
this file. `RULINGS.md` is where **C1** sends every session before it designs
anything, and this document is too long to be read before every decision.

**This file keeps what it is best at** — what *we* found rather than what he ruled:
`OP-` (open problems), `DEC-` (decided, not built), `BV-` (built, not verified),
`DEBT-` (deferred on purpose) and `Q-` (questions for him). A new standing rule goes
to `RULINGS.md`; a thing we discovered goes here.

---

## 2. Open problems — known broken or wrong

Ordered by consequence.

### The twelve below came from ONE review, 2026-08-26 — the source-page plan, read against the code

He asked for `docs/plans/2026-08-22-the-source-page-moves-into-the-extension.md` to be
reviewed before a line was written, section by section, and ruled a direction on each
finding. **Sixteen were found; four were built the same day** — the row handle, the payload
memory, the derived contract guard, and the DOM and CI floors. **These twelve are the ones
not built**, filed the day they were found, because a finding that lives in a chat channel
did not happen. That is the mechanism `OP-69` was three days late by.

`OP-70`, `OP-71` and `OP-72` lead because they are the three the primary session separated
out, and the ordering rule is worth stating: the first has a **scheduled arrival date**, the
second is a **comment naming a trap sitting above code that walks into it**, and the third
is the only one that lets a caller **manufacture state**. The remaining nine follow by
consequence.

**Every citation here was re-derived at `35962cc` and none was carried from the plan.** The
plan was written at `4522158`, six merges earlier, and every `app.py` and `app.js` line
number in it had moved. That `docs/plans/` sits outside the citation guard's `DOCUMENTS` is
`OP-59`'s shape one file over.

### OP-70 · A dataset with a composite identity reports every row as `unsighted`, and the test covering that column cannot see it

**Found 2026-08-26. Two halves, and the second is what lets the first survive.**

**The collapse.** [scrapex/extract/service.py:915](../scrapex/extract/service.py#L915)
resolves the identity field as `identity[0] if len(identity) == 1 else None`. With **two**
`key_part` fields, or **zero**, that is `None` — so every row's external id is `None`, every
`dataset_sighting` lookup misses, and `row_state` runs with `sighted_at=None,
last_absent_at=None` for the entire table. `observed_state`, the column that exists on his
instruction in `REQ-44` — «عمود يوضح الحالة الجديدة لا تدع المستخدم يستنتج الحالة» — is then uniformly
wrong with nothing on screen or in a log to say so.

**It is not hypothetical, because the code names its own trigger two lines above:**
*"`contractor_id` is muqawil's answer; **Balady's and the UAE's will not be**, and this
function is the one the panel calls for every generic source."* Both sources are already
written up — `docs/BALADY-ENG-OFFICES.md` and `docs/UAE-SOURCES.md`. A defect with a
scheduled arrival date.

**The guard that cannot fire.** `grep -rn "key_part" tests/` returns **zero**: the identity
resolution has no test at any arity. And the assertion covering the column
([tests/test_a_dataset_is_a_table_like_any_other.py:869](../tests/test_a_dataset_is_a_table_like_any_other.py#L869))
tests membership in an eight-value set that **contains `unsighted`**, so a table where every
row collapsed stays green. General form in `LESSONS` §15.

**His direction, 2026-08-26: build the edge case AND strengthen the assertion.** The `else
None` swallows an unanswered question — what a two-key dataset *means* — and took the worst
of the three available answers: explicit refusal, a composite key, or silent omission.
**Which of the three is his call, not a developer's.**

### OP-71 · The `MAX(observed_at)` subquery cannot be served by its index, twelve lines under a comment condemning that exact pattern

**Found 2026-08-26.** [scrapex/extract/service.py:940](../scrapex/extract/service.py#L940)
runs `(SELECT MAX(v.observed_at) FROM generic_record_revision AS v WHERE
v.generic_record_id = r.generic_record_id)` — once per row.

The only index available is [db/engine/schema.sql:849](../db/engine/schema.sql#L849),
`ix_generic_record_revision_record ON generic_record_revision(generic_record_id,
record_revision_id)`. **Its second column is `record_revision_id`, not `observed_at`**, so
SQLite can seek a record's revisions from the index and must then read the table for each
one to get the timestamp. No covering index, no index-only `MAX`.

**And the trap is named on the same screen.**
[service.py:954](../scrapex/extract/service.py#L954), twelve lines below, explains that the
sighting side is read in ONE query because joining per row *"would be the
correlated-subquery defect `OP-27` measured at 49s all over again."* The rule is known,
written down, and applied to the neighbouring table.

**His direction: a covering index on `(generic_record_id, observed_at)`, and explicitly NOT
a cache.** A crawl writes continuously, and a stale cache produces *"why is the new
contractor not showing?"* — a silent failure worse than a slow query. **The migration number
is `0012`**, swept across every ref on 2026-08-26: `main` holds `0010`,
`origin/feat/organization-enrichment` holds `0011`. Ask for it rather than counting it.

### OP-72 · Three write tables key on a bare `TEXT source_key` with no foreign key and no existence check

**Found 2026-08-26, and it is the only one of the twelve that lets a caller manufacture
state.** `dataset_field` ([db/engine/schema.sql:176](../db/engine/schema.sql#L176)),
`saved_view` ([:511](../db/engine/schema.sql#L511)) and `source_attribute_promotion`
([:575](../db/engine/schema.sql#L575)) each declare `source_key TEXT NOT NULL` with **no
`REFERENCES`**, and `fields.ensure_fields` and `fields.set_promotion` check nothing before
inserting. A `POST` naming a source that does not exist **creates rows for it**.

Related and separate: `fields.delete_view` is `DELETE FROM saved_view WHERE saved_view_id =
?` with **no `source_key` scoping**, so the id alone is the whole authority.

### OP-73 · `POST /api/fields` has no catalogue branch, so hiding a contractor column returns 404

**Found 2026-08-26.** Step 0 of the plan gave `GET /api/fields` a dataset branch
([scrapex/webui/app.py:2269](../scrapex/webui/app.py#L2269)) and **the POST at
[:2335](../scrapex/webui/app.py#L2335) never got one.** It runs the price machinery
unconditionally, and its seeding is keyed on `BROWSE_COLUMNS`: `wanted = [key for key, _ in
BROWSE_COLUMNS if key in present or key == body.get("field_key")]`.

**Measured: `BROWSE_COLUMNS` holds 54 keys and not one is a dataset field** —
`company_name`, `contractor_id`, `membership_level` and `company_name_ar` are all absent.
The comprehension iterates `BROWSE_COLUMNS`, so a contractor key never enters `wanted`,
`ensure_fields` seeds nothing, `set_visibility` updates zero rows and raises `KeyError`, and
[:2371](../scrapex/webui/app.py#L2371) turns that into **404**.

**Reachable today.** Hiding a column from the grid's three-dot menu is the POST at
[grid.js:1246](../scrapex/webui/static/grid.js#L1246); the GET that seeds runs only inside
the Choose-Columns panel builder at
[grid.js:1205](../scrapex/webui/static/grid.js#L1205). Open the contractors table, hide a
column from the column menu without opening Choose-Columns → 404. **And the comment at
[app.py:2340](../scrapex/webui/app.py#L2340) describes this exact failure and says it was
fixed** — the fix is `BROWSE_COLUMNS`-shaped, so it is products-only.

**Nothing tests it:** every `POST /api/fields` test uses a products key, and all four
`contractors` HTTP calls in the step-0 suite are `GET`.

**His direction: repair the seam BEFORE the port starts**, so steps 1–4 really are the
"pure client ports" the plan calls them rather than discovering a server defect mid-way.

### OP-74 · `list(body["order"])` is unguarded: a 500 one way, a forged «this is your arrangement» the other

**Found 2026-08-26.** [scrapex/webui/app.py:2367](../scrapex/webui/app.py#L2367) is
`reorder(conn, source_key, list(body["order"]))` with no type check. Two failure modes,
traced through [scrapex/fields.py:153](../scrapex/fields.py#L153):

- `{"order": 5}` → `list(5)` raises `TypeError`. `_write` catches only `DbLockedError`, the
  outer `try` only `KeyError`, and the app-level handlers only three database errors →
  **unhandled 500**.
- `{"order": "abc"}` → `list("abc")` is `['a','b','c']`, which **passes** the `if not
  ordered_keys: return` guard at [fields.py:160](../scrapex/fields.py#L160), matches no real
  key, changes no order — and then [fields.py:173](../scrapex/fields.py#L173) stamps
  `arranged_at` for the whole source **unconditionally**. `order_source` flips from
  `"agreed"` to `"yours"` with nobody having arranged anything.

The second is worse, and the comment above the stamp says why: *"This is the only path a
PERSON can reach."* The stamp's whole meaning is *a person arranged this*, and an
unvalidated cast lets a stray string forge it. `0059` rests on that distinction.

**His direction: reject a non-list `order` with 422, plus tests for `5`, `"abc"`, `[]`, `{}`
and an unknown key.**

### OP-75 · `GET /api/fields` writes and commits on both branches, outside the write lock every `POST` pays for

**Found 2026-08-26.** The GET commits at
[app.py:2240](../scrapex/webui/app.py#L2240) — the dataset branch, seeding from the schema —
and at [app.py:2291](../scrapex/webui/app.py#L2291) on the price branch. A grep over the
whole `api_fields` region finds **two `conn.commit()` and zero `write_lock`**, while every
`POST` goes through `_write` ([app.py:2178](../scrapex/webui/app.py#L2178)), which takes the
lock for the reason it states: *"A crawl in progress holds that lock."*

**The write-on-GET is deliberate, documented and tested** — that is not the finding. The
finding is that it is **unlocked**, so the protection depends on the HTTP verb rather than
on what the code does, and a GET can write while a crawl holds the lock.

**This is also what makes read-only connections more than a one-line change.** Neither
`read_conn` nor `general_read_conn` opens read-only: both reach plain
`sqlite3.connect(str(path))`
([databases/domain.py:144](../scrapex/databases/domain.py#L144)), and the only `?mode=ro` in
the package is in `bundle.py` and `carry_over.py`. Making the read paths read-only breaks
this GET **immediately**, so every endpoint must first be classified "reads" against "reads
and seeds". **His direction: put the lock where the write already is, and move the seeding
to `POST` later, alongside `OP-73`.**

### OP-76 · The two payload producers label columns by different rules, and the difference is visible to him

**Found 2026-08-26.** `grep display_name scrapex/reports.py` returns **zero hits**: the
products payload labels from a module constant only —
[reports.py:2191](../scrapex/reports.py#L2191), `labels = dict(BROWSE_COLUMNS)`. The dataset
payload does the opposite at [service.py:1043](../scrapex/extract/service.py#L1043),
preferring his stored `display_name`.

**So renaming a column reaches a contractor table's heading and never a products table's.**
The plan lists *"a rename reaches the heading"* as a met step-0 gate; it holds for datasets
only, and the plan does not say so.

**His direction, 2026-08-26: unify it — his renames should reach products headings too.**
Recorded as a decision rather than a cleanup, because it changes what existing product
tables display.

### OP-77 · `dataset_table_payload` reimplements two `fields.py` helpers inline while the products path calls them

**Found 2026-08-26.** It imports and uses two of the five helpers
([service.py:16](../scrapex/extract/service.py#L16)) and reimplements `hidden_columns` and
`column_order` in the function body, where
[reports.py:2183](../scrapex/reports.py#L2183) calls the helper. Two surfaces answering one
question two ways — which is what step 2's own gate forbids: *"a grep finds no second copy of
any of the three bodies."*

**Not inflated beyond what it is:** `fields.list_fields` and `catalog.list_fields` are a
**name collision, not duplication** — different tables, different keys, different return
shapes. Recorded so that a later reader does not "fix" it.

### OP-78 · `tree` is produced by both producers, asserted by a test, and read by no consumer anywhere

**Found 2026-08-26.** [reports.py:2255](../scrapex/reports.py#L2255) computes it with
`_tree_shape`; [service.py:1046](../scrapex/extract/service.py#L1046) hard-codes `{}`. No
consumer reads `payload.tree` — `grid.js`'s `features.tree` is a name collision — and the
13-key list asserts it regardless.

**Recorded rather than deleted, on his direction:** removing a key from the contract while a
third producer is being written against it is two changes at once. It is now **named** in
`UNREAD_BY_EVERY_READER` in
[tests/test_the_table_payload_answers_every_key_its_readers_read.py](../tests/test_the_table_payload_answers_every_key_its_readers_read.py),
so it is a listed decision instead of an accident, and anything that joins it fails that
test.

### OP-79 · `reorder` reads `dataset_field` unfiltered, so `OP-53`'s eleven inert rows still consume ordering positions

**Found 2026-08-26.** [fields.py:162](../scrapex/fields.py#L162) builds `current` from a bare
`list_fields`, which is `SELECT ... FROM dataset_field WHERE source_key = ?` with no
intersection against the dataset's real schema. The intersection that makes `OP-53`'s eleven
price-path rows inert lives **only on the read path**, at
[app.py:2243](../scrapex/webui/app.py#L2243). So the eleven are invisible in the chooser and
still occupy `display_order` slots whenever anything is reordered.

Depends on `OP-58`: whether those rows are deleted at all is his gate, since
`COMPATIBILITY.md` puts a destructive migration behind his review.

### OP-80 · One uncached `/api/offer` request per selected row, with no cap — and step 3 would port it verbatim

**Found 2026-08-26.** [grid.js:3085](../scrapex/webui/static/grid.js#L3085) is
`rowsData.forEach((row) => { ... fetch("/api/offer/" + ... + row.offer_id)` — one request per
selected row, all in parallel, no batching, no cache, and `rowsData` carries no length limit.

These are the multi-row selection cards: 109 lines of the 967-line step-3 cluster, so the
shape crosses into the panel unchanged, where it also crosses the extension's 5,000 ms
deadline.

**His direction: a cap that SAYS what it excluded, plus a batch endpoint.** Step 3 builds a
new endpoint anyway, so making it batch costs about the same and stops the N+1 reaching a
second surface.

### OP-81 · Nothing on the data path is cached, anywhere

**Found 2026-08-26.** Zero hits for `cache-control|etag|last-modified|max-age` across
`webui/app.py`, `reports.py`, `extract/service.py` and `fields.py`, and zero for
`lru_cache|functools.cache|@cache` across **all** of `scrapex/`. None of the three registered
middlewares ([app.py:565](../scrapex/webui/app.py#L565)) adds a header. Every open of a data
tab recomputes the whole payload, measured at 24.26 MB over 17,304 rows for `contractors`.

**Recorded as a characteristic rather than a defect to fix, and he ruled against caching
directly** — see `OP-71`. A crawl writes continuously, and stale data he cannot explain is
worse than a slow query he can. **The remedy for the cost is the covering index, not a
cache.**

### OP-43 · Four written premises about the muqawil profile page were wrong, and one of them hid a price
**Found 2026-08-22** under `REQ-31`, measured over **2,419 real profile pairs** read
read-only out of the running crawl, after he warned that the pages are not consistent —
«المعلومات غير ثابته ولا متفقثة بين الصفح يعنى ممكن تلاقى معلومات تانية وطريقة عرض مختلفة».

Everything this repository believed about that page came from two committed fixtures,
which are **one contractor**. `R-19` labelled that limit honestly; the conclusions
outlived the label.

| premise, and where it was written | what 2,419 pages say |
|---|---|
| `extract/muqawil.py`'s module docstring: the fifth `<table>` is *the technical rating* | There is no technical-rating table. `contractor-tab4` holds **zero tables** in its DOM subtree on 2,360 of 2,360 pages. The fifth table is the **self-build price** schedule |
| `GROUPS_NOT_LOCATED`: the technical rating *"carries no table for this contractor"* | Not this contractor — the site. It is a tab button over an empty pane |
| the plan: `contract_request_url` *"has no known URL pattern and is not on the card"* | The card is on **100%** of pages. The URL is one site-wide constant, so it earns no column — and the form carries the **Commercial Registration number** |
| `write_groups`: the licences cell carries both languages *"with no separator"* | There are two dashes in it. They are **hierarchy** separators inside each language, and splitting on them would have cut a path into pieces and called each piece a language |

**All four are fixed and the fixes are in the same pull request**, per **C2**. What is
left over is recorded rather than repaired:

- **The site's own English is wrong on 100 of 1,685 licence rows** — 30 truncated to
  `Civil Engineering -` (the same string for two different activities) and 70 naming a
  *different activity*. Detected by level count, stored with the Arabic path alone.
  Across the corpus that leaves **3 of 29** taxonomy nodes with no English name, which
  are the three the site never publishes correctly. → `Q-17`.
- **`sub_contractors` and `main_contractors` carry rows on 2 and 0 of 2,419 pages.**
  Declared and unbuilt. → `Q-18`.
- **The card census has one stated blind spot.** `undeclared_cards()` reports an
  undeclared card only when it carries a table or a list, because the contractor's own
  name is a text card whose title differs on every page. Measured: filtering by
  position is wrong on 40 of 5,668 pages, by content on 0 — so a new **text** card
  would not be reported. The narrower guard with no false positives was chosen
  deliberately.

**Next action:** none blocking. The 34,834-page crawl is storing evidence now and
`R-40` made the re-parse path work, so every column above lands on a re-approval with
no network.

### OP-1 · The engine on the owner's machine ran unmerged, half-written code
**Status: CLOSED, re-measured 2026-08-09.** `_host_lanes` is on `origin/main` in
`scrapex/jobs.py`; the PR was opened and merged. The account below is kept because
it is the only end-to-end description of the fault, and because it is the class of
failure **OP-13** exists to catch and still does not.
Three crawl jobs failed on 2026-07-29 between 15:23 and 15:25 with
`worker error: name '_host_lanes' is not defined` (`crawl_job` rows `job_aebc47261d01`,
`job_50a7783ad32a`, `job_b094a0510dce` — measured). The engine restarted while `jobs.py`
had the call and not yet the helpers; the commit `1deff23` says so itself. The file is
whole now, but `1deff23` is **not on `main`** and no PR exists for it (`gh pr list` tops
out at #15).
**Next action:** none. What remains is **BV-1** — it has still never been run at
width > 1 on the owner's machine.

### OP-2 · Three different answers to "which sources are active"
**Status: open.** Measured 2026-07-29:

| source | `main` | working tree | live `source_site.active` |
|---|---|---|---|
| MADAR | false | **true** | 1 |
| ALSWEED | true | **false** | 1 |
| ELBUROJ | false | false | *(no site row)* |
| ADVANCEDCASTLE | true | true | 1 |
| ELSEWEDYSHOP | true | **false** | 1 |
| MASDAR | true | **false** | 1 |
| SIKAEGSHOP | false | false | 1 |
| SAMEHGABRIEL | true | **false** | 1 |
| GPP_ENERGY | true | **false** | 1 |
| ARAMCO_FUEL_SA | true | true | 1 |

The manifest edit is uncommitted, so it exists on exactly one machine and dies with the
next `git checkout`. And the warehouse says every source is active, which contradicts both
files — either `source_site.active` is never re-synced from the manifest, or it means
something else entirely.
**RE-MEASURED 2026-08-09 — the uncommitted edit is gone, exactly as the paragraph
above predicted it would be.** `sources.yaml` in the working tree is now
byte-identical to `main`: six sources active of twelve. Nobody decided that; a
`git checkout` did, and no one noticed for eleven days. So there are **two**
answers now rather than three, and the warehouse is still the one that disagrees —
which makes the second half of this entry the whole of it.

**RE-MEASURED 2026-08-12 — the three answers are now ONE, and the disagreement
this entry exists for is gone.** Measured, not inferred:

| | |
|---|---|
| manifest (`sources.yaml` at the repo **root**, not `config/`) | 12 sources, **7 active** — ALSWEED, ADVANCEDCASTLE, ELSEWEDYSHOP, MASDAR, SAMEHGABRIEL, GPP_ENERGY, ARAMCO_FUEL_SA |
| `main` vs working tree | byte-identical (`50ff470`), nothing uncommitted |
| live `source_site.active` | the **same seven**, set for set |

So "six of twelve" (2026-08-09) is stale too: it is **seven**. What fixed it is
`80c7258` (#177) — `reconcile_active` already existed and was already correct;
the commit gave it a caller at startup and on every manifest-reload route.

**But the fix is not guarded, and that is my own failure to record.** The two
tests that cover what the commit actually CHANGED are **string greps over
`app.py`'s source text** — `source.count("_follow_the_manifest()") >= 6`. Neither
builds an app, hits a route, or reads a row. The five behavioural tests call
`reconcile_active(conn)` directly — the function that was already correct. Seven
tests pass, and they pass for the wrong reason. The route's new
`warehouse_updated` field is read by nothing: one occurrence repo-wide, its own
definition.

**Next action:** a test that drives a reload route through `TestClient` and
asserts a warehouse row changed. Then this entry can close. The remaining
question — whether **seven of twelve** is the set the owner *intends* — is
**Q-11**, and it is a decision, not a discrepancy.

### OP-3 · ~~Five currencies have no exchange rate~~ — CLOSED 2026-08-11, and it was never five

**CLOSED 2026-08-11, and it was never five.** Measured: 123 currencies in use, 119 with a
rate, four without — and three of the four were not gaps. `UNKNOWN` belonged to the deleted
SPARK_ESHOP, `USD` is the base, `SLL`/`ZWD` retired in 2022 and 2009. Named in `UNQUOTABLE`
(#156).

**Kept because its premise was wrong:** the stored note blamed *"the page shape has
changed"*, when the cause was that Google Finance no longer quotes withdrawn currencies. A
message that names the wrong cause sends the next reader to the parser.

### OP-4 · `scrapex/webui/app.py` is 3,347 lines / 95 routes, and the extraction it started stopped
**Status: open. Re-measured 2026-08-12.**

| when | lines | routes |
|---|---|---|
| `REVIEW-2026-07-28` | 1,820 | 82 |
| 2026-07-29 | 2,480 | 89 |
| 2026-08-09 | 2,955 | 95 |
| 2026-08-11 | 3,246 | 98 |
| 2026-08-12 (*Sheets moves into the panel*) | 3,198 | 93 |
| **2026-08-12 `4fcc14f`** | **3,347** | **95** |

**Two things this entry said are wrong, and both make the work easier, not harder.**

*"It has grown at every measurement"* — it has not. One PR reduced it by 48 lines
and 5 routes. The trend is still upward, but the sentence was rhetoric, and
rhetoric in a measurement file is how a number stops being checked.

*"The router-factory pattern is already applied inside the same file to four
fragments"* — it is not inside the file. `grep -nE 'def [a-z_]*(router|_api)\w*\(' scrapex/webui/app.py`
returns nothing. All four factories live in **sibling modules** and are imported
(`app.py:56`, `:161`, `:162`):

| module | lines | routes |
|---|---|---|
| `scrapex/webui/catalog_api.py:21` `create_catalog_router` | 122 | 8 |
| `scrapex/webui/database_api.py:11` `create_database_router` | 82 | 3 |
| `scrapex/webui/database_api.py:65` `create_domain_health_router` | *(same file)* | |
| `scrapex/extract/api.py:42` `create_extraction_router` | 134 | 6 |

338 lines and 17 routes are out; 3,347 lines and 95 routes are still in. The
pattern is *extraction to a module*, already proven three times — so the next
action is smaller than the entry implied. `catalog_api.py` and `database_api.py`
are byte-for-byte the same size as on 2026-08-09: no extraction has happened in
three days.

The regex-scraping test is real and still there: `tests/test_ui_manifest.py:25`.

**Next action:** continue the extraction. The alternative branch — declare the
size acceptable and delete the pattern — is contradicted by the file itself,
which added 392 lines in three days. *"Keep extracting when there is time" is not
a third option; that is what has been happening.*

### OP-5 · `reports.py` computes the six history statistics twice, and the price has already been paid once
**Status: open. Line numbers corrected 2026-08-12.** `export_source_table`
(`scrapex/reports.py:1214`, was cited as `:982`) and `table_payload` (`:1997`, was
`:1664`) each carry their own copy; the file is now 2,795 lines. This was a
maintenance argument until the review found the owner's own comment in the code
recording that adding one column shifted `observations` / `min` / `max` /
`previous` by one during the brand work.

The duplication is between the `_EXPORT_SELECT` dict (`:1016`, entries at
`:1064-1078`) and `table_payload`'s own restated subqueries.
**Next action:** one expression source read by both — and have `table_payload`
read its results **by alias** rather than by `r[19]..r[22]`, so the shift-by-one
class of defect dies with the duplication instead of merely moving.

### OP-6 · Four review findings were never refuted, and one of them is about test coverage
**Status: partly closed, partly unknown.** `REVIEW-2026-07-28` §5 warns that the
refutation stage for eight findings (ت1–ت8) died on a session limit, and that at the
observed rate (6 of 18 fell under refutation) **2–3 of the eight should be wrong**. Do not
treat them as facts.

| claim | status now |
|---|---|
| ت4 `matching.py` rescans the material table per product per name | **fixed** `0a2209c` |
| ت5 `LocalSink` reloads the whole workbook per tab | **fixed** `0a2209c` |
| ت6 the panel rebuilds the log every 1.5s and steals the selection | **fixed** `f901638` |
| ت7 the whole 45-test panel suite silently skipped in CI | **fixed** `48ec48b` + the ≥40 collection floor in `ci.yml` |
| ت1 restore / start-fresh always broken while the worker thread runs | **HALF closed, re-measured 2026-08-12** — *start-fresh* is guarded and tested; `/api/storage/restore` has **no** active-job 409. Refusing is the correct behaviour, and only one of the two routes does it |
| ت2 the heartbeat is written between jobs only, so the engine declares itself dead mid-crawl | **OPEN — and its stated cause is now wrong.** See below |
| ت3 every run rebuilds the full derived timeline of every touched offer | **open** — the entry pointed at DEBT-4; it means **DEBT-3** |
| ت8 the `grid.js` XSS guard scopes itself by splitting on two comments and leaves a gap | **changed** — that guard is gone. Its replacement scopes by line-suffix and by a 14-word `_TEXT_BEARING_FIELDS` allowlist, which leaves two nested markup builders unchecked |

**ت2, measured rather than read (2026-08-12).** Two probes driving a real
`JobRunner`:

- The docstring's stated root cause — *"the loop hands its whole pass to
  `run_job_once`"* — **is stale**. Jobs run on their own threads
  (`jobs.py:1450`) and `touch_runtime_heartbeat` fires every poll
  (`jobs.py:1334`): 6 distinct heartbeats in 12 s.
- The real cause: when a job **holds an open write transaction** — which a long
  ingest does — `touch_runtime_heartbeat` raises
  `sqlite3.OperationalError: database is locked` from `jobs.py:1035` and the
  runtime heartbeat **freezes** (1 distinct value across 45 s).

And only one of the **two** `worker_alive` computations was fixed:

| where | what it calls | verdict |
|---|---|---|
| `scrapex/webui/app.py:1682` — `/api/health` | the new two-heartbeat `worker` verdict | correct; the panel reads this one (`extension/engine.js:38`) |
| `scrapex/webui/app.py:2749` — `_about` | `worker_is_alive(conn)`, single heartbeat | **the function the fix superseded** |

`_about` renders the engine's own `/settings` page
(`scrapex/webui/templates/settings.html:162-167`), so **the engine still shows
"Not running" while it is crawling**, and advises the owner to check whether the
engine is started at all.

**Next action:** three separate things — the second `worker_alive` at
`app.py:2749`; the heartbeat's behaviour under a held write lock; and the 409 on
`/api/storage/restore` with a mirror of
`test_start_fresh_is_refused_while_a_crawl_runs`.

### OP-7 · `/api/native-host/register` takes no authentication and REPLACES the allowlist
**Status: open, needs an owner decision (**Q-8**).** `REVIEW-2026-07-28` §2 #2. Since the
origin lock (`3d7d1a9`) no web page can reach it, but this route is the *deliberate*
exemption from the guard — any extension reaches it, and `install()` overwrites the list so
registering one id evicts the one that was working. It writes an HKCU registry key.

### OP-8 · The Apps Script funnel is frozen on v1 payloads and the block is on the owner's desk
**Status: open, blocked on the owner.** Live `scrapex_meta.setting:apps_script_last`,
2026-07-26T13:40:49Z:

> *"Delivered 87 rows in 19 chunk(s). The sheet did not confirm writing — update the pasted
> script (Copy Script) to get write confirmations, or run Rebuild tables from the sheet's
> ScrapeX menu."*

The vocabulary sweep changed `product_name`'s meaning, so the old pasted script acks each
chunk, throws inside `reassemble_`, and keeps republishing the last v1 batch — alive,
openable, and frozen for three days.
**Next action:** owner opens Settings → Copy Script and re-pastes it. Nothing else unblocks
it.

### OP-9 · 154 rows hold a name with no Arabic character in the Arabic column
**Status: open, small, and it is stale data rather than a code defect.** Measured today
across 3,799 products: **MADAR 147, GPP_ENERGY 6, MASDAR 1** carry a `product_name_ar`
containing not one Arabic character. The GPP six are the material keys (`DIESEL`,
`GASOLINE`, …) folded there before the sweep. A re-crawl of each source moves them.
Memory recorded 148; the measured figure is 154.
**Next action:** re-crawl MADAR and GPP, then re-measure. Tax survives regardless — the
material key is read through `COALESCE(NULLIF(product_name,''), product_name_ar)`.

### OP-10 · MASDAR is missing nine English names, and MASDAR is a bilingual source
**Status: open (new — found while writing this file).** Measured: 9 of 617 MASDAR products
have an empty `product_name`. ALSWEED (1203/1203) and SAMEHGABRIEL (18/18) are *correct* —
salla and woo are monolingual and the empty English column is the pinned rule (SR-15). But
hybris publishes both, so under **SR-2** nine missing English names are a defect.
**Next action:** find out whether those nine products genuinely have no English name on the
site (then it is data) or the English pass dropped them (then it is a bug).

### OP-11 · 2,385 attribute rows carry no language mark
**Status: open, deferred once already.** The vocabulary sweep deferred MADAR /
SAMEHGABRIEL's `lang=''` attribute rows; memory recorded 1,129. Measured today:
**2,385**. It has more than doubled, so whatever produces them is still producing them.
**Next action:** find the connector path that emits an attribute with no `lang` before
back-filling, or the backfill will be undone by the next crawl.

### OP-12 · ~~No linter, formatter or type checker~~ — PARTLY CLOSED 2026-08-11

**PARTLY CLOSED 2026-08-11 — and the open half is the half that was never true.** The
original line said *"no `ruff`, no `mypy`, no `eslint` anywhere"*, which was **false when it
was written**. It is the clearest case in this file of a status line outliving what it
described.

| gate | covers |
|---|---|
| `ruff==0.16.2` (`ci.yml:30`) | `scrapex/` **only** |
| `eslint@9.39.0` (`ci.yml:38`) | `extension`, `scrapex/webui/static`, `contract`, `apps_script` |
| mypy | **nowhere** — no CI step, no `pyproject` section, no config, no pre-commit |

`ruff check tests/ tools/` gives **395 errors, 233 auto-fixable**, 378 of them in `tests/`.
`mypy --strict` was run once over the price files: 72 findings, 14 correctness-shaped, of
which **2 real** and both fixed (#157). The gate was deliberately not added — 60 of the 72
are annotations and that churn buys no defect.

**Still open:** widen ruff to `tests/` and `tools/`, and either add the mypy gate or move it
to §5 as declared debt with its reason. The current state is neither.

### OP-13 · ~~There are no end-to-end or chaos tests~~ — CLOSED 2026-08-11

**CLOSED 2026-08-11.** `ENGINEERING` T7 named killing the engine mid-job, corrupting a
checkpoint and force-closing the browser, and none existed. They do now --
`tests/test_the_engine_survives_being_killed.py` and the end-to-end test in the same PR.
**The chaos test's own reliability is the live problem — `OP-19`.**

### OP-14 · The Native Messaging size ceiling — the backwards sentence is already gone
**Status: changed, minutes of work left.** `scrapex/native.py` no longer carries
the reversed claim the entry describes, so the thing to settle is settled. What
remains is that the comment still does not state the two limits plainly.

**Next action:** one comment edit — a host→extension message is capped at 1 MB;
extension→host is 64 MiB — and drop the "decides whether a large record set can
be returned at all" clause, which was the reason for urgency and no longer holds.

---

### OP-15 · The panel talks about the engine in the wrong places, and says it twice differently

Reported by the owner on 2026-08-11 with the engine at 0.2.2 and the unpacked
extension at 0.2.1, so all of it is visible on a real installation right now.
Recorded in full as issue #160; the four parts are:

- The version-mismatch banner follows the reader onto **all eleven views**. It
  sits outside every view deliberately — its comment argues that a warning you
  have to hunt for arrives after the owner has already asked why a feature is
  missing. That reasoning was sound before the Engine page existed. Moving it is
  a **reversal of a documented decision**, so whoever does it must answer the
  original problem rather than delete the note.
- The Engine card reads `Installed version 0.2.2 / Latest released 0.2.1` while
  the banner above it reads `Installed extension 0.2.1 / Engine 0.2.2`. Each is
  correct alone. **The word "installed" means two different things two inches
  apart.**
- Engine controls stay enabled when there is no engine to control.
- The About page carries three version numbers and eight capability entries with
  their own commit hashes. That is a changelog, on the page a person opens to
  find out what the thing is.

The owner's own rule decides most of it without arguing case by case: *leave what
belongs to the extension where it is, and tie everything else to the engine.*

### OP-16 · "Closing the panel never stops a run" is asserted in a comment and checked by nothing

`extension/app.js` opens by stating that the panel is a remote control, that
closing it never stops a run, and that reopening reconnects to whatever is in
flight. **No test exercised any of it** — every panel test opened the panel, drove
it, and ended. Issue #161.

**Half of this is now closed. Re-measured 2026-08-12.** *Reopening reconnects* was
the fragile half and it was also **false**: a reopened panel showed a live crawl
as idle. `reattachToRunningJob` and the panel-visibility handling fixed it and
tests drive it.

*Closing never stops a run* is **still asserted and still checked by nothing.**
It is probably true — the engine owns execution — but the panel holds a poll loop
and, since #152, work that begins on `load`; if the close path aborts a request
the engine reads as a cancel, a long crawl dies because the owner closed a side
panel to read a page, and they would never connect the two.

**Next action:** restate this item as the first half only, and pin it with a test
that fires `pagehide` on a panel with a job in flight and asserts the job row is
still queued or running afterwards.

### OP-17 · `carry_over` cannot merge a table that lives in both old databases

Found by running the carry-over for real on 2026-08-11. Both old files number
their rows from 1, so any table present in BOTH collides on its primary key and
`INSERT OR IGNORE` drops the second file's rows without a word. It did not bite
the owner only because no table of theirs lives in both.

**Refusing is the correct behaviour and the row-count guard already produces it**
— 45 read, 40 written, pointer not moved. Recorded rather than fixed, because a
merge would have to invent new keys and rewrite every foreign key that points at
them. Worth doing only if a real installation ever needs it.

A second thing that run taught, worth keeping beyond this item: **`INSERT OR
IGNORE` swallows a CONSTRAINT failure exactly as quietly as it swallows a
duplicate.** A row violating a NOT NULL in the new schema vanishes with no error;
the row count is the only thing that notices. `PRAGMA table_info` does not show
CHECK constraints at all, which is why the test fixture was wrong three times
before it was built from the shipped schema instead of from memory.

### OP-21 · `snapshotcrawl`'s resume saves the write and none of the requests

**MEASURED 2026-08-20**, by resuming a nine-page crawl and counting: the second run
made exactly as many requests as the first.

The module's own docstring gives the reason it exists in requests —
*"a second attempt re-fetched every one of them — on a full pass, hours of requests
to re-learn what was already on disk. Keeping the evidence and re-fetching it
anyway is not a resume."* The implementation checks the resume in the wrong place:

```
scrapex/snapshotcrawl.py:154   def store(page: FetchedPage) -> None:
scrapex/snapshotcrawl.py:164       if page.url in seen:
```

`store` is the walker's `on_page`, and `PageWalker.walk` calls it **after**
`self._get(url, …)` has already fetched. So a resumed run re-fetches every page and
then declines to store it. It saves the INSERT and the compression, which is real,
and none of the hours, which is what was claimed.

**Not fixed here, per [R-01](RULINGS.md#r-01--diagnose-confirm-then-fix--one-step-at-a-time)**
— where the skip belongs is that module's own decision, and the honest fix moves
the check into the walk rather than adding a second one. `scrapex/partitioncrawl.py`
needs a resume that actually saves requests because it is a ~2,000-request crawl, so
it filters the already-stored URLs out of the `PageSource` before the walk sees them
(`_Unstored`) and reads those pages' ids back off the stored snapshot instead of off
the wire. That is a local answer, and it leaves this defect standing for every other
caller.

**Why it matters beyond the tidiness:** the resume is the reason a crawl can be
interrupted. An eight-hour profile crawl (step 4 of the muqawil plan, 34,806 pages)
interrupted at hour six would, today, re-fetch six hours of pages to store nothing.

### OP-22 · The warehouse exists on ONE of the two machines, and the pointer on the other is pre-collapse

**MEASURED 2026-08-20 on the home machine**, before anything was run:

| | |
|---|---|
| `~/.scrapex/engine/scrapex-engine.db` | **does not exist** |
| `~/.scrapex/databases.json` | `"mode": "split"` — the layout from before the two databases were collapsed into one, so `DatabaseRegistry.defaults()` **raises** |
| `~/.scrapex/general/general.db` | 192 KB, has the generic tables and **0 rows in every one of them**; no `dataset_sighting`, no `snapshot_dictionary` |
| `~/.scrapex/marketlens/marketlens.db` | 21 MB, and carries none of the generic tables |

So the 11,059 contractors, the 1,728 page snapshots and — the part that cannot be
re-derived — the `dataset_sighting` ledger from the six-pass sweep, with its 17,283
ids and their frequency distribution, are on the work machine only. The home machine
can read every document describing them and open none of them.

> **THE FRAMING BELOW WAS MINE AND HE OVERTURNED IT THE SAME DAY. Kept per C4/C5.**
> I wrote that this is *"`CLAUDE.md`'s founding failure in the one place the
> repository cannot follow it"*. It is not a failure at all:
> [R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)
> — ScrapeX is a tool **many people install**, so an installation with no warehouse
> is the product's **normal first-run state**, and a warehouse is per installation.
> The repository rule is about decisions and knowledge, which do travel; a user's
> collected data was never meant to.
>
> **What survives as a real finding** is the second half: a *coverage number is a
> fact about one installation*, so "11,059 of 17,403" must never be written as a
> project-wide truth — and any session must check which warehouse it is looking at
> before trusting one. That part stands, and it is why this entry is not deleted.

~~**This is `CLAUDE.md`'s founding failure in the one place the repository cannot
follow it.** A document is committed and travels; a 796 MB database is not and does
not.~~

**The question it raised was the owner's** and was recorded as `O-6`: carry the file
across, run only where the data is, or let each machine hold a warehouse and
reconcile them. **He chose none of them** — see the note above. It never blocked the
*build*; the crawl was written, tested and priced without it.

### OP-23 · ~~`carry_over` cannot carry a pre-0058 installation~~ — FIXED 2026-08-20, and the fix was a ruling first

**FIXED 2026-08-20, the same evening it was found, and the fix was a ruling first.** I had
recorded it here and stepped around it by creating a second warehouse. He refused that:
[R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
-- a database is upgraded, never replaced, and a migration that refuses on real data is a
release blocker, not debt.

`Backfill` in `scrapex/databases/carry_over.py` supplies the columns the engine schema
requires and the split era never had, **reusing migration 0058's own `legacy_unwitnessed`
rather than minting a second literal**. It then ran on the real installation: 3,739 offers,
3,739 observations, 3,739 periods, 17,111 attributes, 7,410 change events, 966 products --
**not one row short**. Six mutations killed.

**Two reasons it had to be at the INSERT, both measured:** the trigger fires on INSERT, so a
later `UPDATE` never runs; and copy-then-migrate is architecturally closed — a copy of
`marketlens.db` is refused on `application_id` before its `user_version` is even read. That
is why the row-copy design is correct by necessity rather than by oversight.

### The diagnosis, kept because it is where the fix came from

**MEASURED 2026-08-20, by running it for real on the home machine** while creating the
warehouse [R-23](RULINGS.md#r-23--scrapex-is-a-multi-user-product-so-a-warehouse-is-per-installation)
calls for. `scrapex carry-over` refused:

```
error: a selling unit must carry its provenance and its witness
```

**It refused correctly and moved nothing** — the pointer is still `"mode": "split"`,
which is the safety design in `carry_over`'s own docstring working exactly as written.
But the documented upgrade path for this installation is now closed.

**The cause, exactly.** Migration 0058 added `unit_basis_provenance` and
`unit_basis_witness` to `source_offer` plus two triggers that refuse a row carrying a
`selling_unit_id` without both. `carry_over` INSERTs the old rows into an
already-migrated database, so the triggers see them — and the old schema has **no such
columns at all**:

| | |
|---|---|
| `source_offer` rows in `marketlens.db` | **3,739** |
| of those, carrying a `selling_unit_id` | **261** |
| `unit_basis_provenance` / `unit_basis_witness` in the old schema | **the columns do not exist** |

**And the fix needs no decision about evidence, which is why this is a defect and not
a question.** 0058 already faced the same rows in the in-place upgrade path and answered
it — [db/migrations/0058_a_unit_that_can_name_who_said_it.sql:89-90](../db/migrations/0058_a_unit_that_can_name_who_said_it.sql)
sets `unit_basis_provenance = 'legacy_unwitnessed'` with a witness that says in words
that nobody can say where the value came from. So the honest value exists, is named,
and counts as unresolved under the resolution metric. `carry_over` simply never applies
it, because it copies rows rather than migrating a file.

~~**Not fixed here, per R-01.**~~ **Struck 2026-08-20:** R-01 governs a fix landing before the CAUSE is agreed, and the cause was agreed the moment it was measured. What I actually did was defer a release blocker, which is what R-24 refuses.
It touches the path that carries the owner's 3,739 price observations, which is the
highest-consequence surface in the project, and it is unrelated to the muqawil crawl
this pull request is about. The shape of the fix is one `UPDATE` after the copy, reusing
0058's own literal rather than inventing a second one — and it needs a test that the
carried rows come out marked `legacy_unwitnessed` rather than merely arriving.

**A sibling of [OP-17](#op-17--carry_over-cannot-merge-a-table-that-lives-in-both-old-databases)**,
and the same lesson from a different direction: that entry recorded that
`INSERT OR IGNORE` swallows a CONSTRAINT failure as quietly as a duplicate. Here the
constraint is a TRIGGER, so it aborted loudly instead — which is better, and is why
this was found in one command rather than by counting rows afterwards.

### OP-24 · The marketlens → engine rename is a MANUAL command, so a shipped user gets a dead engine

**HIS QUESTION, 2026-08-20, on the board as [REQ-20](REQUESTS.md#req-20--the-database-rename-must-reach-every-user-not-just-this-machine):** «قاعدة بيانات marketlens تم تغيير اسمها — هل تم تغيير
اسمها عند كل المستخدمين؟» The answer is no, and it was measured rather than reasoned.

**The mechanism exists and the product does not reach it.** `carry_over` has exactly
**one** production caller — the manual subcommand `scrapex carry-over`
(`scrapex/cli.py:1009`). Nothing automatic calls it: not `ui`, not autostart, not the
native host, not the panel.

**What a split-era user actually gets**, simulated end to end against a fake split
installation:

| path | result |
|---|---|
| any CLI command | clean message naming `scrapex carry-over` — `main()` catches everything (`scrapex/cli.py:1143`) |
| `native.startup_check()` — how the PANEL starts the engine | `ok: false`, `action: "check_storage"`, detail = *"Run 'scrapex carry-over'"* |
| `native.upgrade_database()` — **the panel's own repair action** | `ok: false`. **It cannot fix this**: `DatabaseRegistry.defaults()` refuses before `initialize()` is ever reached |

So the one button the product offers for a database problem is unable to fix the one
transition every existing installation must make — and it reports the failure as
`check_storage`, which is the wrong action: nothing is wrong with the storage.

**THE PROJECT HAS ALREADY RULED ON THIS EXACT SITUATION, and the ruling was not applied
here.** `cli._upgrade_what_is_only_behind` exists because of his instruction of
2026-08-05, and its docstring is this entry's whole argument:

> Migration 0061 merged and was never applied here, so the next time the engine started
> it refused — correctly, and with the exact command to run — and the owner saw only a
> dead engine. The rule protected the data and cost him the product, because **the one
> person the refusal speaks to is the one who does not read a log.**

That reasoning was applied to *migrations* and never to *carry-over*, which is the
bigger of the two transitions.

**And the automatic version is SAFER than the one already shipped**, which is the part
that makes this cheap. `_upgrade_what_is_only_behind` advances the user's file in place
and therefore has to take a backup first. `carry_over` opens both old files
**read-only**, writes a new one, verifies every table's row count, and moves the
pointer **last** — so the old files are the backup, by construction, and a failure
leaves an installation that refuses to start rather than one that starts on half its
data.

**Shape of the fix**, for whoever picks it up: call `carry_over` from the same place
`_upgrade_what_is_only_behind` is called (`scrapex/cli.py:867`) when the pointer is
split, say so on stdout and in the log naming both source files, and give
`native.upgrade_database()` the same path so the panel's button works. Then a test
that a split installation **starts**, which is the test nobody has written — every
carry-over test to date has called `carry_over` directly, so the gap was invisible.

**Not built here.** It is a different concern from the muqawil crawl in flight, and
under [R-24](RULINGS.md#r-24--a-database-is-upgraded-never-replaced--the-users-data-survives-the-schema)
it is a **release blocker** rather than debt — so it is his call whether it goes in its
own session now or immediately after the crawl lands.

### OP-25 · The partition made the crawl provable and broke the approval, for the SAME reason

**MEASURED 2026-08-21 on the first partitioned crawl.** 897 stored page-pairs went
through `--approve`. **74 approved, 823 refused** with
`ExtractionConflict: This dataset already has a different approved schema.`

**74 is not a round number and it is not random.** `region_id=0`'s four cells are
`1 + 4 + 10 + 59 = 74` pages, and `region_id=0` **is** the 1,438 contractors who
publish no location at all. Their cards carry no location box, so:

| page | fields |
|---|---|
| `region_id=0 & company_size=big` | **21** — no `card_city_region` |
| `region_id=1 & company_size=big` | **22** |

Those 74 pages taught the dataset a 21-field schema, and every located contractor's
page after them presented 22 and was refused.

**The cause is the partition itself, which is what makes this worth writing down.**
`_candidate_from` derives the field list from the union of THAT PAGE's cards. The old
unfiltered crawl mixed every kind of contractor onto every page, so
`card_city_region` was always in the union and the schema was stable — 864 pages
approved into 11,059 records. The partition deliberately **groups like with like**, so
the first cell is systematically unrepresentative. The same property that makes a cell
provably complete makes its schema a bad sample.

**The full card field set, measured across page 1 of every cell:** 15 fields, of which
14 appear on every page that has any cards, and only `card_city_region` varies (58 of
64 pages). The intersection reads 0 because one cell — `region_id=8 &
company_size=big` — publishes **no contractors at all**, so its page contributes an
empty set.

**The fix is already written in the same file, for the same reason, applied to only
half the problem.** `extract/muqawil.py` declares `BILINGUAL_CARD_FIELDS` and says why:

> Emitting `_ar` only where an Arabic value happened to be found made the column list
> depend on which contractors that page's Arabic half showed — and the listing
> reorders, so 118 pages in 119 were refused as a different schema. Which fields the
> SITE translates is a fact about the site, so it is declared here … and an absent
> value is a NULL in a column that is always there.

That argument is identical and covers the `_ar` half only. **The base card fields need
the same declaration**: which boxes a card can carry is a fact about the site, not
about which twenty contractors a page happened to show.

**AND IT NEEDS A DECISION, because the 74 pages already landed.** A parser that always
emits 22 fields produces a different `schema_hash`, so those 74 are refused too. Three
ways out, and the choice has data consequences:

- **(a) Wipe the `contractors` dataset and re-approve all 897 pages from disk.** ~20
  minutes, **no re-fetching** — the snapshots are stored, which is the whole economics
  of the seam. Cleanest, and destroys 1,172 rows that would be immediately rebuilt.
- **(b) A new dataset key.** Keeps the 74 pages' dataset, and leaves two datasets
  describing one directory — which `R-11` would not thank anyone for.
- **(c) Schema-drift review support**, which the error message itself points at and
  which does not exist. The largest option and the one that would help every future
  source.

*Recommended: (a), and it is only cheap because nothing has to be re-fetched.*

**RULED 2026-08-21 — (a).** → [R-28](RULINGS.md#r-28--the-74-approved-pages-are-wiped-and-re-approved-from-disk).
**What remains of OP-25 is option (c) alone**: schema-drift review still does not
exist, the error message still points at it, and it was passed over for timing
rather than on merit. It stays open here as the part that serves every future
source.

### OP-26 · The contractor directory can be COLLECTED but not MAINTAINED

**MEASURED 2026-08-21**, answering [REQ-22](REQUESTS.md#req-22--what-happens-on-a-new-contractor-a-vanished-one-a-changed-one-and-on-update).
Collection is in good order after this session — provable, evidence-stored,
resumable, and every id seen is recorded. **Everything that happens after the first
crawl is missing**, and these are four separate defects that share one cause: nothing
has ever run a SECOND crawl of this source through to rows.

> **FIRST, A DISTINCTION HE HAD TO CORRECT ME ON, 2026-08-21.** I wrote this entry as
> though "missing" and "disappeared" were one problem. They are two, and only one of
> them is detectable:
>
> > «لو تقصد المقاول الذى سالت عنه برقم العضوية فهذا لانى اعرف هذا المقاول بالتحديد
> > وبعد اول زحفة لم اجده ضمن المقاولين ولكن هذا لا يعنى بالضرورة انى اعرف باقى
> > المختفيين»
>
> | | what it is | can it be detected? |
> |---|---|---|
> | **never seen** | no pass has ever shown this contractor. **10001274's case** | **no — not who, only how many.** That number is the deficit `D`, which is why closing `D` is the only thing that addresses it |
> | **disappeared** | seen and STORED, then absent from a pass that proved it read every row of that contractor's cell | yes, by query — and nothing does it |
>
> **He found 10001274 because he happened to know that company.** That is exactly what
> does not scale: the rest have nobody to ask after them. So the sighting ledger and
> `missing_ids` answer "stored vs sighted" — a real question — and neither of them
> reaches a contractor the site has never shown us at all. Only `D` does.

**1 · A contractor that disappears is invisible** — **DETECTION BUILT 2026-08-21, the
write still open.** No production code moves a `generic_record` out of `'active'`, so
a delisted contractor keeps `status='active'` with a frozen `last_seen_at` and is
**indistinguishable from one this run did not crawl**. That matters more than it
looks: the listing SHRANK by 25 rows on the night of 2026-08-20, so departures are
routine.

> **A CORRECTION TO THIS ENTRY, and it changes what has to be decided.** It said no
> code sets `status = 'superseded'`. **`generic_record` does not accept that value at
> all** — its CHECK is `status IN ('active','unavailable','retired')`
> ([db/engine/schema.sql:303](../db/engine/schema.sql)). `'superseded'` belongs to
> `source_offer` and `source_variant`, which is where I read it from. Found by a test
> raising `IntegrityError` on the value this entry recommended.
>
> **So the schema anticipated departure and offered TWO words for it**, and choosing
> between them is a decision rather than a detail:
>
> | | |
> |---|---|
> | `unavailable` | the site is not showing this contractor **right now** — reversible, and the row comes back on the next crawl that sees it. **RULED 2026-08-21: this one** → [R-29](RULINGS.md#r-29--a-contractor-the-site-stops-showing-is-unavailable-not-retired) |
> | `retired` | it is gone, and the row is history |
>
> A directory that reorders and churns by 25 rows a night will produce both, and
> reading one as the other either loses a real delisting or retires a contractor over
> a page the crawl happened to miss. **His call.**

**`sightings.departures` is the detection**, and it is read-only on purpose: a cell
closed with `D=0` proves the crawl saw every row it publishes, so a stored row of
that cell missing from the run **has left**. A query, not a re-crawl — and it keeps
two lists apart, because a row with no sighting at all is a gap in the LEDGER (it
predates #227) and not a contractor leaving. It reaches only rows we already HOLD; a
contractor never shown to us is in neither list, which is the distinction he had to
correct me on above.

**2 · An unchanged contractor still writes history**, contrary to
[R-20](RULINGS.md#r-20--an-unchanged-contractor-is-confirmed-not-re-recorded). The
ruling says a second crawl finding no change updates `last_seen_at` and writes no
revision; `content_hash` is on the table and **is not consulted on ingest**. 34,550
revisions for 11,059 contractors, from two crawls of a directory that barely moved.
R-20 records this as a change to the write path rather than a description of it, and
it is still unwritten.

**3 · There is no path from the product's own interface.** `scrapex/jobs.py` — what
the panel drives through `POST /api/jobs` — contains **no reference to** `muqawil`,
`generic_record`, `partitioncrawl` or `snapshotcrawl`. Pressing the panel's update
button runs the price connectors and does nothing whatever to the contractors. They
can be crawled only by `tools/crawl_muqawil_listing.py` from a terminal. Same family
as [REQ-20](REQUESTS.md#req-20--the-database-rename-must-reach-every-user-not-just-this-machine):
a capability that exists and that the product cannot reach.

**4 · And the schema question gates the rows**, [OP-25](#op-25--the-partition-made-the-crawl-provable-and-broke-the-approval-for-the-same-reason),
deferred by [R-25](RULINGS.md#r-25--the-crawl-method-is-settled-first-the-schema-and-retention-questions-come-last).

**Why all four were invisible until tonight.** Every test of this path approves a
page or two into an empty database. The defects are all in the SECOND pass — what
happens to a row that already exists, or that should stop existing — and
`LESSONS.md` already says it in those words: *"test the second crawl, never the first
ingest."* This source had never had a second crawl reach rows at all.

### OP-27 · A site's own id has no indexed column, so every coverage question is a table scan

**MEASURED 2026-08-21 on the live warehouse**, and the numbers are not marginal:

| | before | after |
|---|---|---|
| `coverage` | **49.74 s** | 0.03 s |
| `missing_ids` | **48.81 s** | 0.03 s |

The two together exceeded the two-minute limit, so `--coverage` simply never
returned. **~1,600×**, for the same answers.

**The cause is that the warehouse has nowhere to put a site's own identifier.**

- `generic_record.record_key` is `_digest(_canonical(identity))` — a **SHA-256**.
  Measured: it equals the contractor id on **0 of 1,172 rows** (`'ff88670d…'` against
  `'20044482'`).
- The id itself lives **inside `data_json`**, reachable only as
  `json_extract(data_json, '$.contractor_id')`, and **no index can serve that**.

So every question of the form "do we hold the row for this id" was a correlated
`EXISTS` scanning `generic_record` once per sighting: 14,180 × 1,172 = **16.6M**
comparisons.

**What was done, and what it is not.** `sightings.stored_ids` reads each side once and
intersects in Python — O(n+m). That is a route around the problem and it scales to the
17,403 contractors, **not** to `R-19`'s child tables, which are projected at ~500K
rows across five groups. At that size the set fits in memory but the full scan of
`generic_record` per call does not stay cheap.

**The structural fix is an indexed `external_id` on `generic_record`**, written at
approval time from the dataset's declared identity field. It is a migration plus a
write-path change, it would make every one of these an index seek, and it benefits
every future source — which is why it is here and not folded into a performance patch.

**And it hid a correctness defect, which is the part worth remembering.** Because
`record_key` looks like it should be the id, the first draft of `departures` joined on
it and would have reported **every stored row as unsighted**. The tests passed: the
fixture wrote `record_key = contractor_id`, which production never does. The fixture
is fixed (it now hashes exactly as the write path does) and reverting the join fails
four tests — but a column named for what it actually holds would have made the mistake
unavailable in the first place.

---

### OP-28 · The muqawil crawl driver had 452 lines and no tests at all
**Status: ADDRESSED 2026-08-21** — 19 tests in `tests/test_the_crawl_driver_cannot_lose_a_run.py`, eleven mutations killed.
The account below is kept because the exposure it describes is the reason the tests are shaped the way they are.

> **Corrected:** first written as *"306 lines"*, which was wrong — the number was read off a line in a traceback rather than off `wc -l`. It is **452**.

Found 2026-08-21 while scoping what a Windows-only failure could hide.
`tools/crawl_muqawil_listing.py` — the driver for `--plan`, `--crawl`, `--approve`,
`--coverage`, `--only`, `--heavy-attempts`, `--not-seen-since` — is referenced by
**zero tests**:

```
grep -rln "crawl_muqawil_listing" tests/   ->   no matches
```

It is also the file where the one Windows-only defect of this whole track lived: a
`UnicodeEncodeError` on `→` in `say()` killed a run **after all 114 requests had
succeeded**, because the console codepage is cp1252 and the arrow is not in it. The
fix (a `say` that cannot raise) is guarded by nothing, and CI cannot catch a
regression: CI is **ubuntu-only**, and `tools/` is not even in the linted path
(`ruff check scrapex/`).

So the exposure is specific rather than theoretical: **argument handling, resume
selection and console output in the one file whose failure mode is invisible to CI.**

### What the tests cover, and what they found

Nineteen tests, grouped by the way hours get lost rather than by function:

| | |
|---|---|
| a log line kills the run | a real `cp1252` stream (`TextIOWrapper`, `errors="strict"`), not a mock — `say` must not raise, the **log must keep** the character the console could not show, and a line cp1252 *can* encode must not be degraded to ASCII |
| a crawl into a warehouse that is not there | `open_engine` exits 2 and **the file is not created** (`R-24`) |
| a mistyped `--only` | refused, and refused **before the connection is touched** — `conn=None` is passed deliberately, so a late refusal would raise the wrong error |
| `--approve` reading another run's evidence | `_` is a `LIKE` wildcard: unescaped, `my_run-%` also matches `myXrun-…` |
| the two locales of one page | paired on the URL with the locale removed, never on arrival order; and the **later** read wins for a page a retry stored twice |
| an empty departure window | says *"Crawl first"* rather than reporting every contractor as departed |

**And the mutation run found two defects in itself, which is the part worth keeping.**
Three of the first twelve mutations printed `NOT APPLIED` — their literal source
strings had their backslashes mangled passing through a shell heredoc — and they were
the valuable three: the `LIKE` escaping, the last-read-wins ordering, and the log
keeping an unshowable character. A fourth applied but was a **no-op** (a trailing comma
added to a call), "survived", and meant nothing. **A mutation that does not apply is
not a passing guard**, and reporting it beside real results is a harness lying quietly.
Re-authored by line number, with the anchor lines asserted before anything is written.

---

### OP-29 · ~~An invalid escape sequence in a test docstring is a future `SyntaxError`~~ — FIXED 2026-08-21

**FIXED 2026-08-21, the day after it was filed.** `tests/test_relaunch_log.py:85` now opens
`r"""`, so the Windows path it quotes is text rather than three escape sequences. Python 3.12
warned; a later Python makes it a `SyntaxError` and the file stops importing.

**The sweep is the value, not the one character.** All **273** tracked `.py` files were
compiled and every literal classified: **zero** invalid escapes remain; the only three
non-raw literals holding a valid-but-silent escape are deliberate byte constants (BOM, length
prefix, PNG magic); and **all 171 regex patterns are already raw**, so none holds a `\b`
meaning *backspace* where a word boundary was meant — this defect's silent twin, which never
warns.

`tests/test_gpp.py:496` read like a fourth finding and was a line continuation that only
looked like backslash-CR because the checkout is CRLF — **trap 2 of `CLAUDE.md` biting the
scan that was hunting trap-shaped bugs.**

The `r` is pinned in `PINNED`, so deleting it fails tier 2 of the citation guard rather than
printing a warning nobody reads.

### OP-30 · Two migration ledgers, one number space — and engine `0006` is the first to collide

**Found on the owner's LIVE warehouse, 2026-08-21, while upgrading it at his
instruction.** The upgrade backed the file up, applied both migrations correctly, and
then **refused to stamp them**, leaving a warehouse no current build can open.

```
engine migration 0006_a_row_says_when_it_was_last_proved_absent.sql
checksum changed; restore the original migration file and retry
```

**The message is wrong about the cause, which is what made this take a while.** No
migration file changed. `database_migration` is `migration_number INTEGER PRIMARY
KEY` — **one number space** — and the collapsed warehouse carries **two streams** in
it:

| numbers | stream | applied |
|---|---|---|
| 1–5 | the **engine**: `schema.sql`, `0002…` – `0005_a_snapshot_says_how_it_is_encoded.sql` | 2026-08-20 |
| 6–55 | the **price** database, carried over: `0006_change_event.sql` – `0057_the_weight…` | 2026-07-31 |

So `_verify_checksums` looks up **number 6**, finds `0006_change_event.sql`'s digest,
compares it against engine `0006`'s, and reports a changed checksum. The row keyed 6
is not engine migration 6 — **it is a foreign row.**

**WHY THIS WAS LATENT UNTIL NOW, EXACTLY.** Engine migrations had only ever reached
`0005`. Number 6 is the first the engine has ever wanted, and #235 is what introduced
it. Every earlier engine migration fitted below the carried-over range by luck.

**WHY NO TEST AND NO CI RUN COULD HAVE CAUGHT IT, which is the part worth keeping.**
A fresh `init-db` writes only the engine's own rows, so the number space is empty
above 5 and nothing collides. **CI always starts from a fresh database**, and 273
tracked test files plus the `migration-authority` job — which runs the whole suite
against the real migration stream — all pass. The collision needs a warehouse that
*carried over from marketlens*, and no test has one. That is the same class of gap as
`R-24`: the upgrade path is only exercised by a real user's file.

**WHO IT HITS.** Every installation that carried over from the price database, the
moment it upgrades past engine `0005`. A fresh installation is unaffected.

### What the state actually is, measured rather than feared

| | |
|---|---|
| `PRAGMA integrity_check` | **ok** |
| both migrations | **applied** — `dataset_sighting.last_absent_at` and `generic_record.node_id` are both there, `generic_record_field_change` exists |
| `user_version` | **7**, correct for the applied schema |
| rows | **every one of 53 tables unchanged** except `generic_page_snapshot` +6, which is the crawl writing six more pages before it was stopped |
| the backup | verified restorable: integrity ok, v5, 16,781 sightings, 9,526 snapshots, 1,172 records |

**So no data was lost and the schema is right.** What is wrong is four fields in a
ledger — and `connect()` verifies that ledger, so the warehouse is unopenable until it
is fixed. **The crawl cannot resume until then either**, because `open_engine` goes
through the same `connect()`.

### The fix, and why it is not "renumber and move on"

The engine's verification keys on a number that another stream also owns. The honest
reading is that **it should key on the migration NAME**, which is unique across both
streams, and that a name with no row is simply unstamped. Three ways, and the choice
has data consequences:

- **(a) Verify and stamp by `migration_name`.** Smallest change, and it makes the
  foreign rows harmless rather than fatal. `migration_number INTEGER PRIMARY KEY`
  means a new row cannot reuse 6, so the number becomes `MAX(number)+1` and stops
  meaning "position in the stream" — which it already does not mean, given two streams
  share it.
- **(b) Namespace the ledger** with a `stream` column, keyed `(stream, number)`, and
  backfill the carried-over rows as `price`. Correct, and it is a migration that has
  to run *before* verification — the ordering is the whole difficulty.
- **(c) Have `carry_over` not bring the price ledger across at all,** and repair
  existing warehouses. Cleanest in the long run and the largest change; it also
  discards a record of what the price database did, which `C4` reasoning says to keep.

*Recommended: (a) now, because it unblocks a live warehouse and makes the failure
impossible rather than deferred; (b) or (c) as the real model, once he rules.*
**Not started — his call, on live data.**

### OP-44 · ~~A dataset card said "no successful crawl yet" over 17,304 crawled rows~~ — FIXED 2026-08-22

**FIXED 2026-08-22.** He reported it from his own panel --
[REQ-33](REQUESTS.md#req-33--the-dataset-cards-said-no-successful-crawl-over-crawled-rows) --
two muqawil cards reading *"no successful crawl yet"* over **17,304** rows while the price
sources beside them read a date.

**The cause was not the missing `crawl_run` row.** `_dataset_rows` wrote
`"last_success": None` as a **literal**, and `freshnessLine` prints that sentence whenever the
key is absent. A `crawl_run` row for muqawil would have changed nothing on the card.

**And the row could not honestly be written:** `crawl_run.source_id` is `NOT NULL REFERENCES
source_site(source_id)` and muqawil lives in `site_profile` — which registry a source lands
in is exactly what
[REQ-25](REQUESTS.md#req-25--one-source-registry-with-a-category-visible-to-every-user) holds,
and it is his to decide rather than a side effect of fixing a caption.

**So the freshness is DERIVED and nothing new is stored:** `last_evidence_captured_at` reads
`max(generic_page_snapshot.captured_at)` over the pages `generic_ingestion` says the dataset
was built from — **`generic_ingestion`, not `generic_record.source_snapshot_id`**, because a
record keeps pointing at the snapshot that last *changed* it (`R-20`), so a confirming
re-crawl would leave the date stale, which is the complaint itself. Six mutations killed, and
the one that mattered swapped those two.

**Two measurements from it live in `LESSONS`:** the `INDEXED BY` finding (353-373 ms by rowid,
**0.9 ms** through the index, identical answer) and why `max(page_snapshot_id)` stops being a
cheaper spelling once `R-43`'s merge inserts another machine's `captured_at` under fresh local
ids.

**And no measure goes beside the date, on purpose.** `dataset_sighting` already means *what
the site showed us* — **17,417 sighted against 17,304 stored** — so putting the stored count
under the word `seen` would answer a question this schema answers exactly, and wrongly.

**Still open, and it is his:** the two registries. This closed the display; a dataset still
has no run ledger of its own.

---

### OP-41 · The test suite writes into the owner's live crawl log

**Found 2026-08-21, by reading the log to check on a crawl.**

`contractors.say` appends every line to `Path.home()/".scrapex"/"contractors.log"` with
no way to redirect it, so any test that reaches it writes to the **real** file. What
surfaced it: two lines saying *"departures not marked: the crawl is not provably
complete"* sat at the tail of the live log while a real crawl was running, and they came
from the gate tests, not from the crawl. A log read to find out what a crawl did is
worth nothing if a test can write to it.

It predates the work that found it — `test_the_crawl_driver_cannot_lose_a_run.py` has
been calling `crawl()` and therefore `say()` since it was written. Two things follow
from it, and the second is the reason this is recorded rather than patched:

* **Wrong content in a file used for diagnosis.** The lines are indistinguishable from
  a real run's, and this one nearly cost a wrong conclusion about a live crawl.
* **A path derived from `HOME` at import time.** In CI that is a container's home and
  harmless; on a developer's machine it is the file they read. The fix is to make the
  destination injectable rather than to monkeypatch it per test file — which is a small
  change to a module that is currently being edited by the six-item track, so it waits
  until that lands rather than colliding with it.

Mitigated where it was found: the new tests redirect `contractors.LOG` to `tmp_path`.
The general fix is still open.

---

### OP-31 · Six crawl workers starve another process out of the warehouse

**Measured 2026-08-21, minutes after `--workers` was built, by using it.** The owner
asked for the Engine to be started while a six-worker crawl was running. It refused:

```
sqlite3.OperationalError: database is locked
  scrapex/jobs.py:932  record_worker_failure
```

Every connection sets `busy_timeout = 5000`, so a writer waits five seconds before
giving up. **Six concurrent writers kept it waiting longer than that** — so the
failure is not a missing timeout, it is a timeout that is too short for the load the
new flag can create.

**THIS IS A COST OF `--workers`, NOT A DEFECT IN THE ENGINE**, and it was not measured
before the flag was written. `R-21` is about pacing outbound requests per site and it
says nothing about how many writers one SQLite file will tolerate — the concurrency
was designed against the site's tolerance and not the warehouse's.

**What is NOT wrong:** the crawl itself. WAL lets readers proceed throughout, the
workers wait for each other correctly, and no row was lost — `integrity_check` is ok
and 53 table counts were unchanged across the whole run. The contention is with
*other processes*, which is exactly what a background crawl is supposed not to do.

Three ways out, and the choice is a trade:

- **(a) Raise `busy_timeout` for the crawl's own connections only.** Smallest, and it
  makes the crawl wait for the Engine rather than the reverse — the right priority,
  since the Engine is what the user is looking at. Does not help a third process.
- **(b) Serialise the crawl's WRITES behind one lock** while leaving the fetches
  concurrent. The DB work is milliseconds against a six-second fetch, so this costs
  almost nothing and bounds the contention at one writer regardless of `--workers`.
  Larger change to `snapshotcrawl`'s write path.
- **(c) Cap `--workers` by measurement** rather than by the latency ratio alone, and
  say in the help what it costs. Cheapest to write, weakest guarantee.

*Recommended: (b) — it is the only one that makes the guarantee independent of how
many workers are asked for, and the cost is bounded by arithmetic rather than by
hoping. (a) as an immediate mitigation.*
**Not started.**

### OP-32 · ~~The fix for the black window has sat in the repository, unreleased~~ — RELEASED 2026-08-22 as `engine-v0.3.0`

**RELEASED 2026-08-22 as `engine-v0.3.0` — the gate that let it happen was closed first,
then he published.** Reported as *"it did not install — black screen"*, captured as
[REQ-28](REQUESTS.md#req-28--the-engine-would-not-install-and-showed-a-black-screen).

**The install path was neither missing nor broken. It was STALE, which is worse, because every
part of it worked.** The panel read the manifest, got `0.2.1`, correctly said *"Available to
install"*, and handed over a byte-perfect download of the build from **before `_first_run`
existed** — which landed six hours after that release, `--splash` the next day. Measured on
the published artifact twice: zero bytes, and with stdin held open as a real console holds it,
still running after twenty seconds, with nothing in `~/.scrapex/engine.log` because it never
reached code that could write.

**WHY CI PASSED IT, and this is the part a test prevents.** The release asked the built binary
exactly one question — `--version` — the one argument no user ever types, on the one branch
that was already correct. `tests/test_native.py` had guarded the *source* dispatch since #141;
**nothing had ever run the artifact.** Now
`tests/test_the_release_proves_the_double_click.py` launches it with no arguments under a
timeout and refuses a build whose output is empty. Eleven mutations, eleven killed.

**It was half-seen and not followed through:** `OP-15` recorded on 2026-08-11 that the card
read *"Installed 0.2.2 / Latest released 0.2.1"* and filed it as a **wording** defect. The
numbers were the finding.

**And its own next action had gone stale while it waited** — six copies of `engine-v0.2.2`
across three documents while `VERSION` had moved to 0.3.0, so the release the documents were
telling him to cut would have been **refused before anything was built**. Corrected in #253
and guarded by `tests/test_the_release_the_documents_ask_for_is_the_one_that_would_run.py`,
which found all six on the untouched documents before a mutation was tried.

**The limit of that guard, stated rather than discovered later:** it proves the tag he is told
to push is the tag the workflow accepts. It cannot prove a release was cut, because nothing
committed here knows what the hub holds. `Q-16` asks whether he wants a scheduled workflow
that does look.

**A later version gap is not this defect returning.** `OP-32` was three things at once:
nothing released across two bumps, the newest installable engine silent on a double-click, and
the documents naming a tag the workflow would refuse. A gap alone is none of them.

### OP-33 · ~~The owner's own warehouse is ahead of `main`, so the engine refuses to start on his machine~~ — FIXED 2026-08-21 by #243

**FIXED 2026-08-21 — by the merge, not by this work.** `claude/his-four-rulings` landed as
[#243](https://github.com/muhammadbayoumi/ScrapeX/pull/243) with engine migrations **0007**
and **0008**, so `main` reads schema v8 and a released engine can open his warehouse. Verified
read-only against his live file: `"status": "Healthy", "schema_version": 8`.

**The diagnosis, because it is why the merge mattered.** `PRAGMA user_version` on his warehouse
was **8** while `db/engine/migrations/` on `main` stopped at 0006, so `scrapex database-status`
answered *"Needs a newer ScrapeX"* and `scrapex ui` exited 1. The two migrations existed in
exactly one place — an unmerged worktree branch that had already been run against his live
warehouse — and `R-24` forbids the obvious shortcut of replacing the database.

**What is NOT closed is the panel's sentence.** An engine that refuses to start never binds a
port, so `extension/app.js:3424` reports **"Not detected"** for a schema fault, a permissions
fault and an absent engine alike — false, and it sends the reader to reinstall what is already
installed. That half is `OP-38`.

### OP-34 · A launch that dies in a console writes nothing to `engine.log`

**Status: OPEN, filed not fixed, per `R-01`.** Found while looking for the black
window's trace and finding none.

`_bind_log_streams` (`scrapex/cli.py:992`) says it plainly: *"run it from a terminal
and this does nothing at all."* It exists for the `pythonw` autostart path, which
has no streams. A double-click **does** get a console, so the redirect no-ops and
the failure goes to a window that is closing. `~/.scrapex/engine.log` is dated
**2026-08-01** across every launch attempt described in `OP-32`.

The instinct — *"a black screen very likely wrote something to engine.log"* — is
therefore wrong for the one path a user actually takes, and an hour can be spent
reading a three-week-old log as though it were evidence.

`_first_run` covers the user-facing half already: it holds the window open on
failure and names where it stopped. What is missing is the **record afterwards**,
for the machine the owner is not sitting at.

### OP-35 · ~~Half the CLI is unreachable from the shipped engine, and says nothing about it~~ — FIXED 2026-08-21

**FIXED 2026-08-21 on his instruction.** `KNOWN_COMMANDS` is gone:
`packaging/engine_entry.py:18` calls `known_commands()`, which reads the subparser choices off
`build_parser()` itself. **Derived, not extended** — a longer literal would have fixed today
and drifted again. **24 of 24 reachable, against 12 before.**

**The defect was `OP-32`'s, one layer along.** The frozen binary hand-maintained the set of
subcommands it would forward; anything else was assumed to be Chrome and went to `serve()`,
which waits on stdin and prints nothing. Measured on the published artifact **with a control**,
so this is not read off the source:

| typed at `scrapex-engine.exe` | in the set? | exit | bytes |
|---|---|---|---|
| `status` | yes | 1 | **94** — a useful sentence |
| `database-status` | no | 0 | **0** |
| `autostart` | no | 0 | **0** |

**`OP-33` was diagnosed with `database-status`** — the command that names a schema-ahead
warehouse in one line — so the shipped engine could not answer the question a stuck user most
needs answered. Neither could `backup-databases`, `restore-database` or `carry-over`: the three
that exist to protect his data.

Guarded by `tests/test_the_frozen_engine_can_start_itself.py`, which asserts the two sets are
equal **and names the twelve casualties separately**, because equality alone still passes if
both sides shrink together. `subcommands()` **raises** rather than returning an empty set if
argparse ever changes shape — an empty set would make every argument look like Chrome, which
is this defect total instead of partial.

### OP-36 · ~~FOUR spawn sites put `-m scrapex.cli` in front of an executable that ignores it~~ — FIXED 2026-08-21

**FIXED 2026-08-21 on his instruction — «ابدأ بـ OP-36 و OP-35 وضمهم لنفس tree».**
Re-measured after the #243 merge it was **four sites, not two**.

**One module, four call sites.** `scrapex/enginelaunch.py:74` answers the `-m` question once
and is `nativehost.py:57`'s three lines generalised — `frozen()`, `runner()`, `engine_argv()`.
**The fix was already written once in this repository** and four callers had each re-derived
it, three of them wrongly. All three bugs closed, the mirrors asserted, **ten mutations and
ten killed**.

`autostart.py:48` was broken a third way, and it was the worst of them — recorded in the
diagnosis at `git show 0afcf3d:docs/BACKLOG.md` rather than repeated here.

### OP-37 · ~~`main` went red at 12:00Z today and stays red, which blocks the engine release~~ — FIXED 2026-08-21

**FIXED 2026-08-21, the same day — and twice, independently, which is the interesting part.**
While this branch wrote the fix, [#243](https://github.com/muhammadbayoumi/ScrapeX/pull/243)
landed **the identical one line** on `main` from another session. Two sessions reaching the
same repair unseen is corroboration rather than waste — and it was not invented either: the
sibling test in the same file already used the correct pattern for the same column.

**It was a time bomb and it had gone off.** The test pinned the newest crawl at
`2026-08-21T12:00:00Z` and set only the last row's `first_seen_at` to it; the others kept
`now`, and `row_state` returns `new` on `first_seen_at >= newest`. From 12:00Z that is true for
ever, so **`main` was red from then on** — and `release-engine.yml` runs the suite before it
builds, so `OP-32` could not ship and `R-18` was unsatisfiable for every open pull request.

**The class is now
[LESSONS §17.4](LESSONS.md#4--a-test-that-compares-a-literal-timestamp-against-now-asserts-nothing-after-that-date)**,
carrying the correction that made it worth writing: #243 called it a dependency on the *time of
day*, which was true of 2026-08-21 alone. Told that, a reader waits for the morning.

Three mutations killed, **two of them in production code** — a test edited into passing would
have survived those.

### OP-38 · "Not detected" is what the panel says about an engine that is installed and refusing

**Status: OPEN.** The half of `OP-33` the #243 merge did not close, split out so it
is not filed as fixed with it.

An engine that refuses to start never binds a port. So `checkEngine` in
`extension/engine.js` gets a connection error, and
`extension/app.js:3424` reports:

    text: "Not detected"      detail: "The panel could not reach the Engine."

**That sentence is false in every case except one**, and it sends the reader to
reinstall software that is already installed. The engine knew exactly what was
wrong — *"This database was written by a later version (schema v8; this build reads
v6)"* — and there was no channel to carry it. Same for a locked database, a busy
port, a permissions fault, or a half-written config.

**The states are already distinguished where they CAN be**: `Not running`,
`Installed, not running`, `Check timed out` and `Incompatible` all exist and are
reasoned about in `engineStatusFromState`. The gap is only the case where nothing
answers at all — and it is the case a stuck user is in.

**The cheapest honest fix is not a protocol.** A refusal already knows how to write
a line; it just has nowhere durable to write it (`OP-34`). If a failed start left a
one-line reason where the panel could read it, "Not detected" could become "Installed,
but it stopped: …". Fixing `OP-34` and this entry are the same work.


### OP-39 · The update stops one step short: nothing replaces the running executable yet

**Status: OPEN by design, not by omission.** `REQ-29`'s engine half is built —
the engine reads the release feed, fetches the installer, verifies its SHA-256
and stages it. What it does not do is install it.

**Why it stops there, and why that is the honest place to stop.** Windows will
not let a running `.exe` be overwritten, so the swap is necessarily performed by
a **detached helper after this process exits**. Every part of that is testable
except the part that matters: whether a real frozen engine, replaced underneath
itself, comes back. A test that set `sys.frozen` and asserted a rename would
prove the plan and nothing about the outcome — and this repository has already
paid for the difference once, in `engine-v0.2.1`, where the guarded thing and the
shipped thing were different things.

**So the plan is data instead of code.** `update.plan_swap` returns the steps,
the file it would overwrite, the digest it verified, and whether it is possible
at all; `GET /api/update/plan` serves it. `R-36` bought an updater before code
signing existed, and what makes that acceptable is that every step is inspectable
before it happens — a plan nobody can read is the same trust problem in a new
place.

**The machinery it needs already exists and is already correct**, which is the
one piece of luck here: `scrapex/relaunch.py:spawn_helper` starts a detached
process that waits for a named pid to exit, for exactly this reason. **This is
why `OP-36` had to be fixed first** — before that, the helper a frozen engine
spawned was a silent native messaging host and would have waited for ever.

**Next action, and its precondition is now met.** This belonged after a release
rather than before one, and the release happened on 2026-08-22 (`OP-32`): a published
`engine-v0.3.0` is the first frozen artifact that can exercise any of this. So the
swap can now be implemented against a binary that exists rather than against
`sys.frozen` set by a test.

### OP-40 · His warehouse has moved ahead of `main` again — v9 now, and this is the third time

**Status: OPEN, and it is the pattern rather than the instance that matters.**

Measured while smoke-testing the update API against the live installation:

    RuntimeError: engine database is needs a newer scrapex: This database was
    written by a later version (schema v9; this build reads v8).

**The third time in one day.** It was v8-against-v6 this morning (`OP-33`, closed
by #243 merging migrations 0007/0008), and it is v9-against-v8 this afternoon —
so some other branch now holds migration `0009` and has run it against his real
warehouse.

**Why this is not just #243 again.** Each instance closes by merging; the class
does not. A session that runs unmerged migration code against the owner's only
warehouse leaves `main` unable to open it, which means **the shipped engine
cannot open it either** — and `R-23` says a warehouse is per installation while
`R-24` says a database is upgraded, never replaced. Both hold. What is missing is
any rule about which code may write to the live one.

**It also makes the updater more valuable rather than less:** the owner's engine
being older than his own database is precisely the situation an Update button
exists for. Today the only route is a merge and a release.

**A question for him, not a decision to take:** should a session be allowed to
run an unmerged migration against the live warehouse at all? `SCRAPEX_DATA_ROOT`
already makes a private one free, and `R-24`'s repair path (`carry_over`) exists.
Recorded as `Q-15`.


### OP-42 · ~~A generic dataset card offers no actions at all, and one of the six would work~~ — FIXED 2026-08-22, and he asked for it before the fix was scheduled

**FIXED 2026-08-22, the same day it was recorded, because he read the same screenshot and
asked for it in his own words — `REQ-36`.**

**What shipped is not the narrow fix this entry proposed.** It suggested a per-entry predicate,
which is still a hand-written claim about somebody else's routing — the exact thing that
rotted here. The blanket hide was right when it was written and became wrong when `/api/table`
learned to resolve a dataset key, and nothing connected the two.

**Measured, and it is the whole answer to "which of the six":** the panel driven with two
`kind: "dataset"` rows offered **no menu at all**, while `Open the data table` was built and
working for a dataset.

**And the guard this entry asked for pointed the other way** — it pinned the absence rather
than the capability, so it would have kept the menu hidden after the route learned to answer.
That is the shape to look for: **a guard that asserts today's limitation is a lock, not a
test.**

### OP-46 · The custom `<select>` is built twice, and `focusOption` is character-identical in both

**Status: OPEN. Found 2026-08-22 by a DRY review of `#252`.** That PR's own comment
names `.sx-select-list`, `.account-menu` and `.finance-converter-options` as the
overlay-layer precedent it was following. Reading the three together to check the
claim turned up something the PR did not raise: two of them are not dropdowns that
merely look alike. They are **one component written twice**.

**Nothing is broken today, and this entry says so before anything else.** Both
dropdowns work, both are keyboard-operable, no screenshot produced this and no user
saw it. What is duplicated is the *state machine*, and the cost is that every future
fix to it has two homes.

**The two implementations**, each mirroring a native `<select>` and replacing its
popup:

| | finance converter | run mode |
|---|---|---|
| entry point | `setupFinanceConverterSelect` ([extension/app.js:964](../extension/app.js#L964)) | `setupRunModeSelect` ([extension/app.js:2016](../extension/app.js#L2016)) |
| `close({restoreFocus})` | adds `hidden`, `aria-expanded=false`, removes `is-open`, restores focus | same four steps, same order |
| `open()` | removes `hidden`, `aria-expanded=true`, adds `is-open`, `requestAnimationFrame` then focuses selected-or-first with `preventScroll` | same five steps, same order |
| `choose(value)` | validates against `select.options`, assigns, dispatches bubbling `change`, closes with `restoreFocus: true` | same four steps, same order |
| `focusOption(direction)` | **identical** — see below | **identical** |

**`focusOption` is the same function, measured rather than eyeballed.** Normalise
the candidate-list identifier (`choices` / `enabled`) and the one expression that
builds that list, and the two bodies are **character-identical** — the guard, the
`indexOf(document.activeElement)`, the `aria-selected` lookup, the
`current >= 0 ? current : Math.max(selected, 0)` fallback and the
`(start + direction + n) % n` wrap:

```
function focusOption(direction = 1) {const OPTS = BUTTONS;if (!OPTS.length) return;
const current = OPTS.indexOf(document.activeElement);const selected = OPTS.findIndex(
(button) => button.getAttribute("aria-selected") === "true");const start =
current >= 0 ? current : Math.max(selected, 0);OPTS[(start + direction + OPTS.length)
% OPTS.length].focus({preventScroll: true});}
```

**And the CSS is the same surface twice**, counted by declaration after stripping
comments:

| pair | identical | differ |
|---|---|---|
| `.sx-select-list` (14) vs `.finance-converter-options` (15) | **10** | `max-height`, the `inset` shorthand vs `inset-block`/`inset-inline`, one animation, two scrollbar properties |
| `.sx-select-option` (13) vs `.finance-converter-option` (16) | **10** | `gap`, `min-height`, `border-radius`, three font properties |

Both popovers share `position`, `z-index: var(--z-overlay)`, `display: grid`,
`gap: 2px`, `padding`, `overflow-y`, `border`, `border-radius`, `background` and
`box-shadow` — the same ten. This is the shape `UI-2` already ruled on: `.icon-tile`
was extracted at **six** identical declarations across three sheets, and this is ten
across two blocks of one sheet.

**What looks like drift and is NOT — the part that decides the severity.** A first
reading of this made it look as though the two copies had already diverged in
accessibility. They have not, and the difference is requirement-driven:

* Run mode disables options **individually**, because which run modes are on offer
  depends on the selection — `for (const option of select.options) option.disabled =
  !allow[option.value]` ([extension/app.js:2181](../extension/app.js#L2181)). Its
  `focusOption` filters disabled candidates because it genuinely has some.
* The finance converter disables **the whole control** when there are no stored
  rates — `select.disabled = !state.financeRates.length`
  ([extension/app.js:1149](../extension/app.js#L1149)) — and mirrors that onto the
  trigger inside `sync()`. It never has a disabled option, so it has nothing to
  filter.
* Type-ahead exists only on the finance side, and a currency list needs it where
  four run modes do not.

So this is **not** a case of one copy having been fixed and the other missed. It is
a shared core with three honest local differences, which is why it is filed here as
cost rather than as a defect.

**One difference is accidental, and it is the whole argument in miniature.** Run
mode's `close()` opens with an early return when the list is already hidden; the
finance copy has no such guard. Nobody decided that. It is what a duplicated state
machine does over time, and it is the second edit — not this one — that will hurt.

**The narrow fix, and it is deliberately narrow.** Extract only the shared state
machine — `open`, `close`, `focusOption`, `choose` — to `design/select.js`, on the
exact precedent the repository already set for this class of problem:
`design/split-button.js` exists because *"the dataset Export control and the
Activity panel's log control cannot become two implementations"*
([tools/sync_design_assets.py:25-26](../tools/sync_design_assets.py#L25)), it is
distributed to both surfaces through `ASSETS`, and the copies are held byte-equal by
`sync(check=True)` in
[tests/test_design_system.py:16](../tests/test_design_system.py#L16). The
candidate-set predicate and the optional type-ahead are passed in.

**Do not merge `sync()`.** Rendering the options genuinely differs — one writes a
`<span>` plus a check icon, the other a label and a tick with different tokens — and
that is the part that should stay local. Nor should `.account-menu` or
`.split-button-options` be folded into the CSS half: their surfaces really are
different (`--line` / `--surface-raised` and `--line-strong` / `--surface` /
`--radius` against the two dropdowns' `--outline-variant` /
`--surface-container-high` / `--radius-lg`). Pulling all four together is the wrong
abstraction that `UI-2`'s closing rule warns about.

**Proof it must carry**: `tools/style_snapshot.py` across both surfaces, with no
computed style changed anywhere — the same evidence `UI-2` used, and the same reason
screenshots cannot supply it.

**Why it is not done in this pull request.** Three sessions were open on 2026-08-22
and one of them is editing `extension/app.js` and `extension/app.css`; a behaviour
extraction across those two files from a secondary session is how the register
collisions of 2026-08-21 happened. It also adds a **third** shared JS module to a
surface the owner has opinions about, which is his call and not a reviewer's.

**Its citations are deliberately NOT in `PINNED`.** Every line above points into
`extension/app.js`, which this branch does not touch and another session was editing
when this was written. `main` went red on 2026-08-22 from exactly that shape, and the
account is recorded beside the row it broke
([tests/test_the_documents_cite_what_they_claim.py:209](../tests/test_the_documents_cite_what_they_claim.py#L209)):
`#252` measured a line in `app.py` correctly on its own base, `#251` landed first and
added fifteen lines above it, and because **no file was changed by both**, git found
nothing to conflict on and neither suite could see the other. **That row has since moved
a third time — 2710 → 2725 → 2787 — which is the argument for this paragraph rather than
against it: the line moves whenever anything lands above it, so a pin is a commitment to
re-derive it on every rebase.** "Check whether the
files overlap" is the reflex that fails here.

Tier 1 still guards these seven citations, and that was proved rather than assumed —
the guard's own `CITATION` pattern extracts all seven from this entry and every one
resolves to a real file and a real line. Pin them when `extension/app.js` is quiet,
and pin `setupFinanceConverterSelect` and `setupRunModeSelect` first.
### OP-47 · The shared split button documents its stacking trap instead of owning it

**Status: OPEN — recording, not fixing. Found 2026-08-22 by the DRY review of `#252`,**
the pull request that fixed the trap for `REQ-30`. It fixed it in the right place for
that screen and in the wrong place for the component.

**CITED BY SELECTOR, NOT BY LINE, ON PURPOSE.** `extension/app.css` and
`extension/app.js` were under concurrent edit by another session on 2026-08-22 — it was
giving the `dataset`-kind cards a `⋮` at all (`OP-42`'s tail) and restyling the card's
trigger at his request. **That request is deliberately not quoted or numbered here**:
the session doing the work is capturing it, and a second copy on the board is the drift
`REQUESTS.md` exists to prevent. Every rule below is named so a reader who finds
different text nearby knows the neighbourhood moved rather than assuming this entry
rotted. The stable files carry line numbers.

**AND THIS ENTRY CARRIES ITS OWN CORRECTION.** The request above was filed as `REQ-36`
on another branch while this was being written, so: **cite `REQ-36` once it is on
`main`.** `REQ-30` is its root and is the truthful citation until then — the trigger
being restyled is the same control whose menu `REQ-30` was about. Swapping it is a
one-word edit that needs no rediscovery, which is the point of writing the instruction
down rather than leaving it for whoever picks this up.

**What `#252` did.** `.dataset-card > .split-button` in `extension/app.css` carried
`z-index: 1`, which made every card's wrapper a stacking context and spent the open
menu's own `z-index: 120` inside it. The fix adds
`.dataset-card > .split-button:has(.split-button-menu[open])` lifting the wrapper to
`var(--z-overlay)` while open — correct, measured, and guarded by a hit test.

**Why the rule belongs one level up.** The `120` is the shared component's
([design/components.css:1429](../design/components.css#L1429)), so the knowledge *"this
menu must not be painted over"* is the component's too. The component's own comment,
ten lines under that declaration, states the repository's rule for exactly this
situation: *"When two independent consumers break the same way, the shared rule is the
defect rather than the consumers"*
([design/components.css:1439](../design/components.css#L1439)).

**And the prose now tells the next consumer to write the selector again.**
`docs/UI-KIT.md` records the trap as placement guidance — *"where a layer really is
needed, raise it to `var(--z-overlay)` **only while the menu is open**
(`:has(.split-button-menu[open])`)"* ([docs/UI-KIT.md:202](UI-KIT.md#L202)). That is a
documented invitation to a second copy, and `webui.css` is already the first:
`.source-filter-menu[open]{z-index:var(--z-overlay)}`
([scrapex/webui/static/webui.css:142](../scrapex/webui/static/webui.css#L142)),
asserted as literal text at
[tests/test_workspace.py:274](../tests/test_workspace.py#L274).

**NOTHING ELSE IS BROKEN — measured at `451468d`, and the measurement is sharper than
"no other consumer has a z-index".** The defect needs two things: a stacking context on
the wrapper **and** a later sibling inside it to lose the tie to. Only one consumer
supplies the second, because only one is *repeated*:

| consumer | how it is wired | repeated? |
|---|---|---|
| dataset cards | `querySelectorAll(".dataset-card .split-button")` in `extension/app.js` | **yes — the broken one** |
| Activity log | `$("activity").querySelector(".split-button")` in `extension/app.js` | no, singular |
| Manage account danger menu | `$("drive-disconnect")`, markup at [extension/app.html:1347](../extension/app.html#L1347) | no, singular |
| source page export | one control in `#grid-toolbar` ([scrapex/webui/templates/source.html:291](../scrapex/webui/templates/source.html#L291)), wired by [scrapex/webui/static/grid.js:3118](../scrapex/webui/static/grid.js#L3118) | no, singular |
| gallery example | one control ([design/gallery.html:379](../design/gallery.html#L379)) | not a product surface |
| grid harness fixture | [tools/grid_harness.py:68](../tools/grid_harness.py#L68) | not a product surface |

**THE FIRST VERSION OF THAT TABLE WAS WRONG TWICE, corrected 2026-08-22 when the
re-measurement below came due. Both errors were in the instrument, not the conclusion:**

* **It missed the Manage account danger menu entirely.** The search was
  `class="split-button"` — an exact match including the closing quote — and that markup
  reads `class="split-button danger"`. A multi-class attribute is invisible to it. The
  shared component's own comment *names* this consumer ("Manage account's danger menu")
  and the omission still survived reading that comment.
* **It listed the source page's Export control twice**, once as "grid toolbar" and once
  as "source page export". `grid.js`'s `toolbar` is `document.getElementById("grid-toolbar")`,
  which is the `<div id="grid-toolbar">` enclosing that very control. One control, two
  rows — so the table claimed five consumers where there were four product surfaces.

**Neither error changed the conclusion**, which is the only reason this is a correction
and not a retraction: every consumer except the dataset card template is still
singular, so only that one can lose a tie to a later sibling. **But a table that was
wrong twice is exactly what "measured at a commit" is supposed to protect against, and
it did not, because re-measuring was left to a person remembering.**

Checked at the same commit: `.toolbar` carries no `z-index`, there is no rule for
`#activity .split-button`, and neither `.dataset-card` nor `#datasets` carries a
`transform`, `filter`, `opacity`, `contain`, `isolation` or `will-change` that would
build a context another way. **This is future safety, not a live defect.**

**RE-TAKEN 2026-08-22 at `d10e974`, after `fix/a-dataset-card-gets-the-menu-it-can-use`
landed as `#258` — this is the discharge of that instruction, not a fresh promise.**
The instruction it replaces said the table was a measurement at `451468d` and had to be
re-taken; it was, and the table above carries the result plus the two errors the
re-measurement exposed.

**The conclusion held and only the number moved, as predicted.** `#258` gave the
`dataset`-kind cards the menu entries that work — `OP-42`'s tail — so the stub goes from
3 cards / 2 triggers to 3 cards / 3 triggers. It was card-local: `.dataset-card`'s block
and `sourceMenu`, with the shared component and its generated copies untouched and no
consumer added anywhere new. The cards given triggers are still `.dataset-card`, matched
by the same `querySelectorAll`, so the repeated-consumer fact is **stronger** than when
it was written, not weaker.

**Verified at the same commit** that all four of `OP-46`'s `extension/app.js` citations
still name their symbols after `#258` moved that file, and that no open pull request
touches `extension/app.js` — which is what let the two `PINNED` rows this entry's
neighbour was waiting on finally be added.

**Still true, and now the standing instruction:** any future branch that adds a consumer
or lifts a different wrapper invalidates the table rather than just the count. The
`querySelectorAll`-versus-`querySelector` distinction is the thing to re-derive, and it
must be searched on the CLASS TOKEN rather than on `class="split-button"`, which is the
mistake recorded above.

**The risk is specific, and that session makes it likelier rather than moot.** The
defect is *created* by fixing consumers instead of the component, and another consumer
is being fixed right now. The next list of anything carrying a per-row actions menu
reproduces it, because the component still ships the trap and the guard is bound to one
screen: `test_an_open_source_menu_is_not_overpainted_by_the_next_cards_button` reads
`#datasets .dataset-card .split-button-trigger`, so it would stay green while a new
repeated consumer was broken.

**The narrow fix.** Move the conditional lift into the shared sheet, beside the
declaration whose knowledge it is:

```css
.split-button:has(.split-button-menu[open]) { z-index: var(--z-overlay); }
```

then `python tools/sync_design_assets.py`. It applies — `.split-button` is already
`position: relative` ([design/components.css:1352](../design/components.css#L1352)) —
and it is inert unless a menu is open. The card keeps its own `z-index: 1`, which is
local placement, not this rule.

**The objection on record does not transfer, and that needs saying plainly.**
`extension/app.css` says *"Changing the shared rule would move the Activity log's menu,
which is not broken"*, and a reader may take that as a decision against touching the
shared sheet. It belongs to the block above it — the **positioning** of the wrapper in
the card's corner — not to the layer. No ruling covers sharing the z-index rule.

**Proof it must carry:** `tools/style_snapshot.py` over both surfaces, with no computed
style changed except where a menu is open, and the hit test generalised off `#datasets`
so it covers whatever the second repeated consumer turns out to be.

**Sequencing:** build this **after** `OP-48` and after the card session lands. It edits
a component five surfaces consume, and doing that while one of them is being restyled is
how two correct branches produce one broken screen.

### OP-48 · The layer scale is transcribed by hand on both sides of the boundary, and a comment is all that holds it equal

**Status: OPEN — recording, not fixing. Found 2026-08-22 by the DRY review of `#252`.**
Of the three findings that review produced this is the one to build first: the fix is a
three-value substitution that cannot change a pixel, and the thing it removes is tied to
a defect he photographed the same day.

**THE ARGUMENT, BEFORE ANY INDIVIDUAL VIOLATION.** The extension and the engine each
transcribe the layer scale **by hand**, and the two sheets share nothing but
`tokens.css`. So changing a layer is not editing a token — it is editing a token and then
remembering that two unrelated stylesheets also spell its value out, one of them on the
other side of a boundary the two surfaces cannot import across. That is the defect. The
three rules below are only how it shows today, and a guard scoped to either surface alone
would go green with the other still wrong — `OP-18`'s shape exactly, and the same failure
as a parameterised test that matches nothing: green because it looked in one place.

**Cited by selector for `extension/app.css`, by line elsewhere** — that file was under
concurrent edit on 2026-08-22 and every rule below it shifts when the card block above
it changes. See `OP-47` for the same reason at more length.

**The scale is three tokens** — `--z-sticky: 10`, `--z-overlay: 20`, `--z-modal: 30`
([design/tokens.css:128](../design/tokens.css#L128)) — and **three rules across two
sheets** write a token's value as a raw number instead of reading it. This is the
complete set, measured at `451468d` by matching a bare integer equal to any of the three:

| rule | sheet | writes | which is exactly |
|---|---|---|---|
| `nav.side-rail` | `extension/app.css` | `z-index: 30` | `--z-modal` |
| `.workspace-menu-backdrop` | `extension/app.css` | `z-index: 20` | `--z-overlay` |
| `.workspace-menu-button` | [scrapex/webui/static/webui.css:81](../scrapex/webui/static/webui.css#L81) | `z-index:10` | `--z-sticky` |

**How the third row was found is part of the finding.** The static guard below was first
written scoped to `extension/app.css`. Checking whether that scope was the whole set —
rather than assuming it — produced `.workspace-menu-button` on the engine's side. The
scope was the bug, not the count.

**`.modal-veil` already depends on the first equality, and its own comment says so.** It
uses `z-index: calc(var(--z-modal) + 10)` and explains why: *"--z-modal is 30 and the
side rail is also 30 (see .side-rail above), so the token as it stands ties with the
thing this has to cover and the winner would be decided by source order. Correcting the
token is a design-system decision, not this screen's."*

That comment is an accurate diagnosis and a deferral, and it is also the whole problem:
**a comment is not a constraint.** The veil is modal — it exists so a question about
revoking a grant cannot be navigated away from — and its correctness rests on a number
in a different rule 1,100 lines away staying equal to a token. Move either and the veil
silently stops outranking the rail. Nothing goes red.

**The concrete consequence, and it lands on the bug he just reported.** Lower
`--z-overlay` below 20 — an ordinary design-system decision — and
`.workspace-menu-backdrop`'s raw `20` outranks **every popover that reads the token**:
`.sx-select-list`, `.account-menu`, `.finance-converter-options`, and the
`.dataset-card > .split-button:has(.split-button-menu[open])` rule that `#252` added
hours earlier. The drawer's backdrop would paint over the very menu whose overpainting
he photographed and asked «لماذا تظهر مرتين» about — `REQ-30`, fixed that same day. One
token edit, and the fix is undone from a file that never mentions it.

**Nothing catches any of this, and that is a finding in its own right.** The repository
has **no test that reads a z-index**. The single guard that touches the subject asserts
the literal *text* of one rule —
`assert ".source-filter-menu[open]{z-index:var(--z-overlay)}" in styles`
([tests/test_workspace.py:274](../tests/test_workspace.py#L274)) — which proves that one
line is spelled that way and nothing about layer order anywhere else. The most recent UI
defect he reported was a stacking bug, and `#252`'s own lesson is that reading a z-index
back would have passed on the broken build.

**So what a guard has to assert is order, not numbers.** Two shapes, and **the static
one is the more valuable** — it fires at review time, where the behavioural one can only
fire after a regression has been written:

* **Static, and the one to build:** **no stylesheet in the repository** may write a bare
  integer equal to the value of a layer token — it must read the token. Repo-wide, not
  `extension/app.css` alone: scoping it to the panel would have missed
  `.workspace-menu-button` in `webui.css`, which is how the third row of the table above
  was found. That is exactly the rule `docs/LESSONS.md` now states in prose (*"The
  extension's layers are three tokens …; a fourth number invented at a call site is the
  next instance of this bug"*, [docs/LESSONS.md:831](LESSONS.md#L831)) and nothing
  enforces. It is also cheap: the three substitutions below are the whole of today's
  violation set, so the guard goes green the moment they land.
* **Behavioural, for `.modal-veil`:** open the confirmation and hit-test a point over the
  side rail rather than reading a z-index back, the way
  `test_an_open_source_menu_is_not_overpainted_by_the_next_cards_button` does.

**And that second bullet is the same lesson twice, which is the point of writing it
here.** `#252`'s guard learned it the hard way: an assertion on the computed z-index
**passed on the broken build**, because the broken build's number was already large.
`.modal-veil` would fail the same way — its `calc(var(--z-modal) + 10)` reads back as a
perfectly correct 40 whether or not the rail it must cover has moved. One instance is a
trick; two make it the practice for this codebase. **Hit-test what is in front, because
that is the question a person is asking.**

**The same file breaks the three-token rule in four more places, and those are NOT this
entry.** `.workspace-menu` invents `z-index: 25` between overlay and modal;
`.split-button-options` uses `120` ([design/components.css:1429](../design/components.css#L1429));
`.grid-feature-popover` uses `100` and `.column-chooser-backdrop` `10020`
([scrapex/webui/static/grid-theme.css:663](../scrapex/webui/static/grid-theme.css#L663),
[scrapex/webui/static/grid-theme.css:311](../scrapex/webui/static/grid-theme.css#L311)).
Those are numbers the scale has no name for — renumbering them changes paint order and is
a design-system decision, which is the call `.modal-veil`'s comment already declined to
make on its own. **Recorded here, deliberately not folded in.**

**The narrow fix, and it is provably inert.** Substitute only the three values that are
already exactly equal to a token: `nav.side-rail` → `var(--z-modal)`,
`.workspace-menu-backdrop` → `var(--z-overlay)`, `.workspace-menu-button` →
`var(--z-sticky)`. Same numbers, so no computed style changes — verified with
`tools/style_snapshot.py` across both surfaces, the same evidence `UI-2` used. Then the
equality `.modal-veil` depends on is expressed instead of commented, and lowering
`--z-overlay` moves the backdrop *with* the popovers instead of past them.

**Why it is not done in this pull request.** Two of the three lines are in
`extension/app.css`, which another session was editing on 2026-08-22 on the owner's
instruction. The change is three lines and behaviour-neutral; it should land as its own
change once that file is quiet, together with the static guard above so the fix arrives
with the thing that keeps it. It does **not** need to wait for `OP-47`.
### OP-53 · Eleven price-path columns are registered against the contractor directory — CODE FIXED 2026-08-22, the rows are still on disk (`OP-58`)

**Status: FIXED 2026-08-22 in code; the eleven rows are still on disk — see `OP-58`.**

Measured read-only against the live warehouse, not reasoned about:

```
dataset_field WHERE source_key = 'contractors'   ->  11 rows
display_method · price · minimum_quantity · quantity_increment · stock_quantity
tax · category_leaf · category_leaf_ar · price_changed_on · last_confirmed_on
curation
```

**Not one of the directory's own 28 fields is among them**, and
`contractor_profiles` has none at all — nobody ever opened its chooser.

**The cause is a missing branch, and the endpoint wrote its own mistake down.**
`/api/fields/{key}` had no dataset path, so a dataset key fell through to the price
path and asked `column_presence` — *"which BROWSE columns does this source
populate"* — about a contractor directory. `ensure_fields` is additive by design,
so **merely opening Choose-Columns registered them permanently.**

Fixed by giving `/api/fields` the catalogue-first order `/api/table` already had,
and by listing a dataset's fields by intersection with its own schema so rows
already written go inert. `dataset_schema_fields` now has one reader instead of
two copies of the same join — the second copy is what caused this.

### OP-54 · ~~Choose-Columns was a silent no-op on every dataset table~~ — FIXED 2026-08-22

**FIXED 2026-08-22.** `dataset_table_payload` built `columns` from `field_definition` via
`schema_version_field` and **never read `dataset_field`**. So hiding a column on a contractor
table wrote `is_hidden = 1` and changed nothing on screen; a rename was stored and the heading
kept the old text; a reorder was saved and ignored.

### OP-55 · Server capabilities on the engine's page that nothing can reach

**Status: OPEN — and the action is "do not port", not "fix".**

Found while censusing `/source/{key}` for `REQ-07`. The page's server side still
supports a global search term, an availability filter, server-side sort links and
server-side pagination. The grid replaced all four in the browser, and nothing in
the current template reaches them.

**Why it matters now:** a port that copies the page copies dead code into a second
place, and the extension is the place we would then have to keep it working in.
Named here so step 4 of the plan carries the working half only.

### OP-56 · The panel prints "bilingual" for every source, because `{}` is truthy

**Status: OPEN. One line, and its test asserts a shape the server never sends.**

`extension/datatable.js`'s `summarise` does `if (payload?.bilingual) parts.push("bilingual")`.
The engine sends `bilingual` as an **object** of AR→EN pairs — `reports.table_payload`
and `dataset_table_payload` both build a dict — and an empty object is truthy in
JavaScript. So a source with no Arabic column at all still reads *"N rows · bilingual"*.

**And the guard cannot see it**, because `datatable.test.mjs` sets
`bilingual: false` in its payload and asserts on `bilingual: true` — booleans,
which is not what either producer returns. The test is green about a shape that
does not exist.

Fix with the feature, in step 1 of the plan: the check becomes
`Object.keys(payload.bilingual || {}).length`, and the fixture starts carrying a
real pair dict.

### OP-57 · The extension's data table is keyed on a column no dataset row has

**Status: OPEN. Fix it with the port, not before.**

`extension/data.js` builds Tabulator with `index: "offer_id"`. A dataset row has
no `offer_id` — `dataset_table_payload` never emits one, and the identity is
`generic_record_id` — so for every contractor row the index is `undefined`.
Tabulator tolerates it for drawing, which is why nothing has reported it, but
`getRow`, `updateData` and selection-by-index cannot work on a dataset. It is
therefore a live blocker for the record card in step 3 rather than a cosmetic
issue.

### OP-58 · Whether to delete the eleven rows — HIS gate, not ours

**Status: OPEN — awaiting the owner. Do not delete them without his word.**

`OP-53`'s code fix makes the eleven rows inert; it does not remove them. Removing
them is a `DELETE` against his warehouse, and `COMPATIBILITY.md` is explicit that
*"Destructive or irreversible migration"* requires programmer approval, and that
old data is *"never rewritten merely to make an internal model look cleaner"*.

**The safe version is narrow and provable:** delete only `dataset_field` rows whose
`field_key` is absent from that dataset's own `field_definition` set. That cannot
touch a products source and cannot touch a field the directory publishes.

**The argument for leaving them:** they are invisible now, and a migration that
deletes rows is a class of change this repository has been careful about.
**The argument for deleting them:** they will resurface the moment anyone removes
the intersection filter, which is a trap for a future session.

Recorded rather than defaulted, per `R-02`.

### OP-59 · `HANDOFF-resume-the-migration.md` sits outside the citation guard, and two of its citations are stale

**Status: OPEN.**

`tests/test_the_documents_cite_what_they_claim.py` checks the eight documents in
`CLAUDE.md`'s map. `docs/HANDOFF-resume-the-migration.md` is not among them, and
it is the living state of Track 1 — the file a session picking up the console
migration is told to read.

**Two citations in it are wrong at `4522158`.** It puts `loadSourceColumns` at
line 1579 of `extension/app.js` and `saveSourceColumns` at 1618; they are at 1594
and 1633. `STATE.md` carries the same pair correctly, which is how the drift was
caught — two documents citing one symbol at different lines.

**Those four numbers are deliberately NOT written in the `path:line` form.**
`extension/app.js` was being rewritten by `#258` when this was written, so a real
citation here would have become a red build the moment that merged —
`ORCHESTRATION.md` §4 — and writing this bug report in the very form the bug
describes would have been a poor joke. **`#258` has since merged at `d10e974` and
both symbols happened to survive at 1594 and 1633**, which is luck and not
stability. Re-derive them rather than trusting them.

**AND THE LUCK RAN OUT ONE PULL REQUEST LATER, which is worth adding rather than
editing the numbers above away.** The branch that added `scrapex/provenance.py`
inserted lines into `extension/app.js` above both symbols: they are at **1602 and
1641** on that branch. The paragraph above is still true *at `4522158`*, and it says
so — that scoping is the only reason it did not simply become wrong. It is also the
best illustration this register has of why the numbers were kept out of `path:line`
form: no guard could have told you they had moved, because no guard can see a line
number written as prose.

**The interesting part is that both citations still point INSIDE the file**, so
Tier 1 would have passed them even if the file were guarded; only the `PINNED`
table catches a citation that moved off its symbol. #256 has since added a check
that a cited line is not blank, which found three more.

**Two options, and they are not equivalent.** Adding the handoff to `DOCUMENTS`
guards it and immediately turns the build red until the two lines are fixed —
which is the point. Fixing the two lines without guarding the file leaves the next
drift silent. The first is recommended.


### OP-51 · Two of the six source-menu entries lead nowhere, and not only for datasets

**Status: OPEN. Measured 2026-08-22 while proving which actions a dataset card may
offer for `REQ-36` — these two are broken for PRICE sources too, which is why they
are here and not folded into `OP-42`.**

Every entry of `SOURCE_ACTIONS` was called against a running engine. Four behave.
Two do not, and neither failure has anything to do with datasets:

| entry | what it opens | what is there |
|---|---|---|
| **Source settings** | `/sources/{key}` | **no such route exists.** Measured: `[p for p in app.routes if p.startswith("/sources")]` is empty, and the request answers `404 Not Found` for a price key and a dataset key alike |
| **Recent changes** | `/source/{key}#changes` | the page renders, and **`id="changes"` exists nowhere in the repository** — `grep -rn 'id="changes"' scrapex/ extension/` returns nothing. The fragment is ignored, so the entry lands at the top of the source page |

**The changes page it should be opening already exists**: `GET /changes?source_key=`
is a real route (`scrapex/webui/app.py:1294`, re-derived at `31c369e`; #257 moved
it from 1223) and answers 200. So this is a wrong
URL rather than a missing feature — one line, but it changes what a card does on
his screen, which is why it was recorded instead of fixed inside a PR about the
three dots.

**Source settings has no obvious right answer, which is the part for him.** There is
no engine page for one source's settings; the panel has its own Source manager view
(`data-view="sources"`) with an editor in it. Whether the entry should open that
panel view, or the engine should grow the page, is a product decision.

**Why the guard did not catch these.** `tests/test_a_dataset_card_offers_what_works.py`
proves what each route does with a DATASET key, and both of these are correctly
withheld from a dataset card — `settings` because it 404s, `changes` because the page
carries no changes section. Withholding them for the right reason is exactly what
that file asserts. Nothing yet asserts that an entry offered on a PRICE card reaches
something, and that is the guard this entry is asking for.


### OP-52 · A dataset appears on two more screens whose only controls cannot touch it

**Status: OPEN. Measured 2026-08-22 while building `REQ-36`, and found by the stub
rather than by reading — this is what the dataset-kind row in
`tools/panel_harness.py` bought.**

`OP-42` was about the Data screen's cards. The same `kind: "dataset"` row shows the
same class of defect on two others, both driven from the same `/api/sources` listing:

| screen | what it offers a dataset | what happens |
|---|---|---|
| **Run** (`#sites`) | an ENABLED checkbox, alongside the price sources | `POST /api/jobs` answers **404 `unknown source_key 'contractors'`**. The crawl a dataset needs is `scrapex contractors`, a CLI command with no panel path — `REQ-24` closed the command and says the panel path is still missing |
| **Source manager** (`#source-manager-list`) | a card, counted in "4 of 4", whose only control is **Edit** | the editor posts to `/api/sources/{key}/edit`, a manifest route. A dataset is not in the manifest |

Measured directly, with the panel driven against a stub carrying the dataset:

    Run screen rows:  LONG_AR(enabled) SHORT(enabled) NOT_READY(disabled)
                      contractors(ENABLED)
    Source manager:   "4 of 4", four cards, every card's only button "Edit"

**AND `R-47` NOW DECIDES WHAT THE RIGHT ANSWER IS, which it did not when this entry
was written.** It landed with #257 and rules that muqawil is **one card with two crawl
options** — the listing sweep and the profile sweep, which "run, resume and approve
separately". So the Run screen offering a dataset a single checkbox is not merely
broken, it is the wrong shape: there is no one crawl to tick. The fix is a card that
offers the two, and it needs a panel path to a dataset crawl, which does not exist
(`REQ-24` shipped `scrapex contractors` as a CLI command and says the panel path is
still missing).

**UPDATED 2026-08-23: HALF OF THAT IS NOW BUILT AND THIS ENTRY IS THE HALF THAT IS
NOT.** `R-47`'s points 1 and 2 shipped — `_dataset_listing` folds the two muqawil
datasets into one listing row and reports the profile crawl as coverage, so the Data
screen draws one card. The sentence this paragraph used to end on — *"`_dataset_rows`
still ends `GROUP BY d.dataset_definition_id`, so the ruling is recorded and not yet
built"* — is **kept as history and no longer true of the listing**: that function still
groups per dataset, deliberately, because `/source/{key}` resolves one dataset out of
it by key and folding there would 404 the profile table. What remains open is exactly
what this entry names: **the Run screen and the Source manager still draw a dataset from
the same `/api/sources` answer and still offer it controls that cannot touch it.** The
fold changed the number of cards on those two screens as well; it did not give either
of them an action that works.

**Note what the Run screen already knows how to do**: `NOT_READY` is rendered
DISABLED with "Not supported yet" on it, because `implemented` is false. So the
screen has a mechanism for "listed but not runnable" and a dataset is not using it —
the engine reports `implemented: True` for a dataset (`_dataset_rows`), which is true
of the DATASET and false of the crawl. That is the cheap fix if he wants one, and it
is a decision about what `implemented` means rather than a bug in either screen.

**Deliberately not fixed with `OP-42`.** That fix changed what one card's menu
offers, on his direct request, and left every other screen's behaviour alone. These
two change what two more screens offer, and the `test_panel_dom.py` line that counts
"4 of 4" carries a comment saying so, so that nobody closes this by shrinking the
stub back.

### OP-62 · ~~The published engine could not serve one page, because PyInstaller was told to carry two files and the runtime opens five~~ — FIXED #265, AND IT REACHED HIM in `engine-v0.3.1`

**CLOSED 2026-08-23.** Reported by him against the published `engine-v0.3.0` — the newest
thing the panel's Download button offered. **The path in his console message was the whole
diagnosis:** every step the engine announced succeeded, and then it could not render.

**`packaging/build_engine.py` named two data paths and the runtime opens five.**

| the runtime opens | at | bundled before |
|---|---|---|
| `db/` | [scrapex/db.py:22](../scrapex/db.py#L22), [scrapex/databases/domain.py:20](../scrapex/databases/domain.py#L20) | **yes** |
| `sources.yaml` | [scrapex/config.py:55](../scrapex/config.py#L55) | **yes** |
| `scrapex/webui/templates` | [scrapex/webui/app.py:294](../scrapex/webui/app.py#L294), [scrapex/extract/api.py:33](../scrapex/extract/api.py#L33) | **no** |
| `scrapex/webui/static` | [scrapex/webui/app.py:364](../scrapex/webui/app.py#L364) | **no** |
| `apps_script/StagingAppScript.txt` | [scrapex/outputs.py:214](../scrapex/outputs.py#L214) | **no** |

**Only one of the three missing ones crashes, and that is the luck in it.**
`Jinja2Templates` does not check its directory at construction, so a missing templates tree
is not a startup error — it is a `TemplateNotFound` on whichever page he opens first.

**Why the release gate passed it, which is worth more than the fix:** the gate proved the
binary STARTED. That half is `OP-69`.

**Fixed and measured on a real artifact rather than argued** — the rebuilt engine answered
`GET /` with **200 and 26,022 bytes of rendered template**, and
`GET /api/outputs/apps-script/script` with **200 and 35,702 bytes, a route that had never
worked in a shipped engine**. `tests/test_the_frozen_engine_carries_its_own_files.py` stages
the build and keeps it fixed.

**And it reached him, which the entry could not claim when it was written.** Verified end to
end rather than assumed: #265 is `467a3ac`; the tag `engine-v0.3.1` on origin points at
`467a3ac`; `release-engine.yml` succeeded at `2026-08-23T12:37`; and the manifest the panel
actually reads — `ScrapeX/json/version.json` on the hub — says `"version": "0.3.1"`,
`"tag": "engine-v0.3.1"`, published `2026-08-23T13:03:28Z`, with a 33,847,073-byte installer
and its sha256. **Releases live on `muhammadbayoumi/mbiX-hub`, not on this repository**, which
is why `gh release list` here is empty and says nothing about whether a release happened.

### OP-60 · A frozen engine cannot name the commit it was built from, and says so

**Status: OPEN by design, and the honest half of a fix that landed.** Measured
2026-08-23 while building `scrapex/provenance.py` (`LESSONS` §14).

A source-run engine can now answer *which code am I running* — it seals what it
loaded and compares it against the disk. **A PyInstaller one-file `.exe` cannot.** It
carries no `.git`, no source tree, and its modules unpack into a per-run temp
directory that says nothing about whether newer code exists anywhere. So it answers:

    mode    "frozen"
    commit  null
    stale   null      <- unknown, NEVER false

**That is correct, not a stub**, and a test pins it (`stale is not False`): on the one
build where staleness cannot be measured, claiming `False` would tell the owner his
engine is current when nobody knows. The gap is narrower than "the frozen build is
unguarded": what is missing is only the **commit it was built from**, which no amount
of run-time inspection can recover and which only the build can write down.

**The fix is a build-time stamp**, and it is small: the release workflow writes the
commit it is building into a generated module, and `provenance` reads it if present.

**NOT DONE HERE, and the reason is a live constraint rather than laziness.** The
primary session is cutting `engine-v0.3.1` from `.github/workflows/release-engine.yml`,
and a change to that workflow from a branch merging into the same window is a change to
the thing being run. `R-35`'s gate also refuses a version edit from this branch. So the
reader is the whole of this change and the writer is the next one.

**Do not close this by making a frozen build guess.** The `None` is the feature.

### OP-61 · A continuation citation is invisible to the citation guard

**Status: OPEN. Measured 2026-08-23, re-measured at `f1844af`. A latent structural gap, not a live
defect — that distinction is the whole entry.**

A citation written as `` (`extension/app.js:1602`, `:1641`) `` carries two references
and the guard sees one. `CITATION` in
`tests/test_the_documents_cite_what_they_claim.py` requires a path before the colon, so
it matches `app.js:1641` and does not match a bare `:1641`. Measured directly: the
regex returns a match for the first string and `None` for the second.

| | |
|---|---|
| continuation citations in the guarded documents at `f1844af` | **19** |
| of those, resolving to a blank line or past EOF | **0** |
| spot-checked and correct | the `docs/STATE.md` pair citing `scrapex/features.py:54` and `:65` |
| moved silently by this branch's edits, guard green throughout | **4** |

**What makes it real is the fourth row.** Edits on the branch that added
`scrapex/provenance.py` shifted `extension/app.js` by eight lines; four continuation
citations went with it; the guard passed the whole time; they were found by reading the
diff by hand. Tier 2 cannot help, because a `PINNED` row is keyed on a path the tier-1
sweep never discovered — there is nothing to pin.

**What makes it NOT urgent is the second row.** None of the nineteen is currently
wrong. The class also pre-dates the branch that found it; only the four movements were
its own.

**The remedy, and the trap to avoid.** The obvious guard — inherit the path from the
nearest preceding citation — is *deciding by adjacency*, which this repository has
measured and rejected twice (the prose-inference tier the guard's own docstring
records, and the keyword allowlist `LESSONS` §13 threw away). **The non-inferring fix
is to forbid the continuation form:** require every citation in a guarded document to
name its path. One mechanical rule, zero inference, and nineteen invisible citations
become nineteen the existing tiers already handle.

**Cost:** rewriting nineteen citations across five documents — a conflict surface of
its own, which is why it was not bundled into the branch that found it.

**And there is a table this is the fifth row of, which is not on `main`.** *Four shapes
of a wrong citation* lives on `origin/docs/the-boundary-becomes-a-ruling` at `c6d9212`,
unmerged. Whoever lands that branch should add the row.

### OP-68 · "The last crawl" is a TIMESTAMP, so 17,256 of 17,304 contractors are shown as having disappeared

**Found 2026-08-24 by an adversarial review verifying `#267`'s numbers. It predates `#267`
entirely** — `contractors` was not touched by that work, and the skew is older than the
`R-51` recovery run.

**`scrapex/sightings.py:398` decides a row is gone by comparing its `last_seen_at` against
`newest`, and `newest` is `MAX(last_seen_at)` to the SECOND** — a timestamp, not a run
identifier ([scrapex/extract/service.py:943](../scrapex/extract/service.py#L943)):

```python
if last_seen_at is None or last_seen_at < newest:
    return STATE_ABSENT
```

A crawl writes its rows over half an hour, so only the rows written in the **final second**
survive that comparison. Measured read-only on the live warehouse:

| | `contractors` | `contractor_profiles` |
|---|---|---|
| `newest` = `MAX(last_seen_at)` | `2026-08-22T07:39:56Z` | `2026-08-24T11:47:30Z` |
| rows equal to it | **48** | **1** |
| rows earlier than it → `STATE_ABSENT` | **17,256** | 17,384 |
| distinct `last_seen_at` values | **1,034** | 3,412 |
| `dataset_sighting` rows | 17,417 | **0** |

**So the Data screen tells the owner that 17,256 of his 17,304 contractors have stopped
being published — after a crawl that read every one of them.** That is the loudest possible
false alarm on the one screen whose job is to show what the site is doing.

The profile table is wrong differently and it is worse for being quiet: `dataset_sighting`
holds **zero** rows for `contractor_profiles`, so `sighted_at is None` fires two checks
earlier and all 17,371 read `unsighted`. The absence bug is masked by a gap in the ledger.

**The reasoning that fixes it is already in the file, eight lines below the defect.**
`scrapex/sightings.py:403-407` explains that `last_absent_at` needs `>=` rather than `>`
*"because both timestamps are `strftime(...,'now')` at SECOND resolution"*. The same
argument applies to `newest` and was never carried across. A run identifier — or the crawl
run's own start time — answers "was this row seen by the last crawl?"; the maximum of a
column written row by row cannot.

**Two statements nearby are also false, and both predate `#267`:**

* [scrapex/extract/service.py:613](../scrapex/extract/service.py#L613) says *"`last_seen_at`
  still moved: the upsert above sets it unconditionally, so a confirmation is recorded on
  the RECORD."* The `DEC-10` early `return` at
  [scrapex/extract/service.py:515](../scrapex/extract/service.py#L515) fires **before** that
  upsert. Measured: **0** profile rows have a `last_seen_at` on 2026-08-24 with an earlier
  `first_seen_at`; all 17,264 pre-`R-51` rows still read 2026-08-23, after a full
  re-approval that touched every one of them.
* `docs/RULINGS.md` claims `dataset_table_payload` *"filters `AND status = 'active'`"* and
  drops the observation facts. Both were true once and are not now: `ec53b17` (#235) removed
  the filter under `R-27`, and the payload attaches `observed_first_seen`,
  `observed_last_seen`, `observed_status`, `observed_last_changed`, `observed_state` and
  `observed_state_meaning`. **The audit that produced that paragraph asked "does it
  filter?" and never asked "does the derived state say the right thing?" — which is where
  the defect actually is.**

**AND IT IS NOT A DISPLAY BUG — IT IS A PUBLISHED COLUMN.** `publish.py`'s
`dataset_workbook_tables` turns every payload column into a workbook column
([scrapex/publish.py:135](../scrapex/publish.py#L135)), and the payload carries six:
`observed_state`, `observed_state_meaning`, `observed_last_seen`, `observed_first_seen`,
`observed_last_changed`, `observed_status`. Read from the live warehouse just now:

```
observed_state          'absent'
observed_state_meaning  'The most recent crawl did not show this row'
```

on 17,256 of 17,304 rows. So the false sentence is written **into the Google Sheet the mbiX
Excel add-in reads** — the single boundary `CLAUDE.md` says the two systems meet at. That
moves this from "a screen is wrong" to "the product's only output is wrong", and it is why
this entry leads the register rather than sitting in it.

**AND IT IS THREE STATES, NOT ONE.** The docstring states the flawed premise out loud
([scrapex/sightings.py:365](../scrapex/sightings.py#L365)): *"`newest` is the dataset's
latest `last_seen_at` — 'the last crawl'. Everything is relative to it."* Everything is,
and three of the eight states rest on it:

| step | test | what it gets wrong |
|---|---|---|
| 3 · `absent` | `last_seen_at < newest` | **17,256 of 17,304** contractors |
| 4 · `new` | `first_seen_at >= newest` | **1** profile reads `new`; **121** were first seen today |
| 6 · `updated` | `changed_at >= newest` | same second-resolution window |

So the screen under-reports what arrived by the same arithmetic that over-reports what
left. `R-27`'s own instruction was «لا تدع المستخدم يستنتج الحالة» — and the column that
exists so he does not have to infer is wrong in both directions.

**THE HALF THAT NEEDS NO RULING, and it is the half that lies in the sheet.** `absent`
must come from the ledger's own absence record, not from a timestamp race.
`mark_unavailable` / `mark_departures` exist to write exactly that, step 5 already reads
`last_absent_at` for `returned`, and step 3 ignores it. Measured, the ledger is right and
the comparison is noise:

```
dataset_sighting for 'contractors':  17,417 rows
   ever marked absent          0
   absent NOW                  0        <- the ledger's answer
   the timestamp says absent  17,256    <- what the screen and the sheet publish
```

So `if last_absent_at is not None and (last_seen_at is None or last_absent_at > last_seen_at)`
is the whole change for step 3, and it needs no new column and no decision.

**THE HALF THAT IS HIS TO RULE.** What "the last crawl" MEANS for `new` and `updated`,
because this pipeline has no single answer today:

* `crawl_run` is the **price** path only — `source_id` points at a price source, and a
  generic crawl writes nothing to it. 159 rows, none for a dataset.
* `dataset_sighting` carries `first_run_ref` and `last_absent_run_ref` and **no
  `last_run_ref`** — the missing third of three is conspicuous.
* A partitioned listing crawl is **93 run refs**, not one, and they share only a prefix.
* And `first_seen_at` is an **approval** time while `generic_page_snapshot.captured_at` is
  a **fetch** time; the R-51 recovery approved pages fetched two days earlier. Comparing
  the two would call a two-day-old page "new".

So "seen by the last crawl" is not derivable from what is stored, and inventing a rule
here would be answering for him — `R-02`'s shape exactly. The options, with their cost:

| | change | what it buys |
|---|---|---|
| **A** | `dataset_sighting` gains `last_run_ref`; a crawl stamps it | an exact answer for all three states; one migration |
| **B** | a generic `dataset_crawl` run table, started and finished | the same, plus a real progress denominator and history |
| **C** | leave `new`/`updated` blank until A or B | no false state, and two columns that say nothing |

**Recommended: fix step 3 now under this OP — it is the one that reaches the sheet — and
put A against B against C to him as its own decision.** Splitting it that way means the
published lie stops today without a schema change being rushed to carry it.

**RULED 2026-08-24 — «نفذ ب».** `R-52`: a generic crawl is a RUN with an identity, in a
table of its own — one row per crawl, not the per-contractor attendance register `0006`
weighed and refused at 17,403 rows a crawl. `started_at` is what `absent` compares
against, `finished_at` is what stops a run still in flight from declaring departures, and
the same table gives `declare_frontier` the denominator `STATE.md` has been missing. Step
3's ledger fix stands on its own and lands first.

**Why this is not folded into `#267`.** It is not caused by that work, it touches the state
derivation every dataset row on the Data screen reads, and `R-51`'s own three new columns
land directly on top of it. Recorded here so it is picked up as its own change with its own
review, which is what this register is for.

### OP-67 · A SECOND obfuscated email on the page is stored as Cloudflare's placeholder text

**Found 2026-08-24 while checking the `R-51` recovery run for damage.** It found none — and
found this instead, which predates that work entirely.

**16 rows hold the literal string `[email protected]` in a declared column:** 13 in
`contractor_profiles` (all in `address`) and 3 in `contractors`. Verified against the
newly written rows: **0 of the 16 are among the 121 `R-51` recovered**, so this is not the
alignment repair's doing.

**The cause. `read_email` takes the FIRST `data-cfemail` on the page and there can be
two.** Contractor `1006`'s English profile carries exactly two:

```
BOX: Organization Email  [email protected]
     data-cfemail -> ayman@smart-const.com          <- read_email finds this one. Correct.
BOX: Address  Al Khobar Al Shemaliyah Cross 15 - Buldg. # 7484 - ...
     data-cfemail -> info@smart-const.com           <- nothing decodes this one
```

`_CFEMAIL.search(html)` is a `search`, so `organization_email` is right on all 17,385 rows.
But the address box's **text** is stored verbatim, and where the second obfuscated address
sat there is now a placeholder:

```
1006: 'Al Khobar Al Shemaliyah Cross 15 - Buldg. # 7484 - 4th Floor - Office # 10
       P.O. Box 1861 Al Khobar 31952 Tel: 00966138941919 - Fax: 00966138965511
       [email protected] www.smart-const.com'
4776: 'Tel: 0138196000 Fax: 0138113334 Email: [email protected]
       Www.Alosais.com P.O. BOX 1083. Dammam 31431, KSA'
```

**Why nobody saw it.** This is failure #1 of `scrapex/extract/muqawil.py`'s own module
docstring — *"every contractor stores the literal `[email protected]` and any 'is the
column populated' test passes forever"* — and the guard written for it watches
`organization_email`, which is the field that was never wrong. The address is 90% correct,
so it reads as a full value; the placeholder sits at the END on only 5 of the 13, buried
mid-string on the other 8. **1,392 of 17,385 rows carry an address at all**, so this is 13
of 1,392 — under one percent, and invisible at any sample size a person would eyeball.

**The fix, and it is not where the bug looks.** `read_email` is correct and should not
change; what is wrong is that a box's TEXT is read without decoding the `data-cfemail`
inside that box. `read_profile` should decode per box — replace each obfuscated span with
its own decoded value while reading the pair — which fixes `address` and any future field
the site hides an address inside. Replayable from the stored snapshots with no network,
like `OP-66`.

**NOT BUILT, AND DELIBERATELY NOT IN `#267`.** It predates `R-51`, it touches
`read_profile` — the same critical parser the adversarial loop is currently converging on
— and folding it in would restart that loop for a defect affecting 16 rows. Recorded here
with its measurement so it is picked up on its own, which is what this register is for.

### OP-66 · The Arabic profile publishes an address box the English one does not, and 129 contractors are held out by it

**Found 2026-08-24 by the owner asking whether another crawl was needed.** It is not, and
answering that question found this.

**The crawl is complete.** 36,358 profile snapshots on disk, **17,452 distinct contractor
ids — the full union — and zero left to fetch.** What is missing is not pages; it is rows.

| | |
|---|---|
| listing rows (`contractors`) | 17,304 |
| profile rows (`contractor_profiles`) | 17,264, of which 14 retired by `OP-64` |
| listing row with **no profile row at all** | **188** |
| listing row with no *active* profile row | 202 (the 188 plus the 14) |
| profile row with no listing row | 148 |

Every one of the 188 has a stored snapshot. Replaying the current parser over them —
read-only, no network — splits them cleanly:

| count | refused by | can a crawl fix it? |
|---:|---|---|
| **59** | `PageIsNotAProfile` — layer 1 of `OP-64`; the id is dead and the site answers with the listing | **No, ever.** The page does not exist |
| **129** | `merge_locales` — the two locales publish different box counts | **No.** The pages are on disk |
| **0** | would approve today | re-approval adds nothing |

**The cause of the 129, measured.** The Arabic page carries a `عنوان` (address) box that the
English page does not publish at all:

```
[en]  9 info-boxes   ...  8. Region  Eastern Province
[ar] 10 info-boxes   ...  8. المنطقه الشرقية
                          9. عنوان  الرياض - شارع العليا - مقابل أبراج العليا
```

`CONTRACTOR-SOURCE.md` already records that the address is Arabic-only; what is new is that
on these pages the English side omits the box **entirely**, so the counts differ and
`merge_locales` refuses.

**AND THE FIRST VERSION OF THIS ENTRY MEASURED IT WITH THE WRONG ARRAY.** It reported a gap
of **+2** on every pair and concluded that **"121 of 121 are MISALIGNED"**, so no repair was
possible. Both claims were artefacts of the instrument: they compared `Reading.fields`, a
dict whose insertion order is not the page's, because `read_profile` adds
`organization_email` and `commercial_registration` after the info-box loop.
`merge_locales` reads `english.labels[index]` and — since `R-51` — the Arabic value at
the position `align_locales` works out
([scrapex/extract/muqawil.py:1715](../scrapex/extract/muqawil.py#L1715)). Re-measured
against **those**:

| pages | shape | the last label on each side | is the odd box at the END? |
|---:|---|---|---|
| **97** | AR one longer | EN `Region` · AR `عنوان` | **yes** — Arabic simply adds the address |
| **24** | AR one longer | EN `Activity` · AR `الخدمة` | **no — it is interior** |
| **7** | EN one longer | EN `Address` | yes |
| **1** | EN one longer | EN `Activity` | no |

The gap is **±1 on every one of the 129, never ±2**, and **no pair is misaligned before the
divergence** — the digit instrument reports zero disagreements, because the odd box always
falls after the last numeric field. So digits cannot decide this question either; the LABEL
POSITIONS can.

**THE REFUSAL IS STILL CORRECT, AND THE 24 ARE THE PROOF.** Contractor `20000713`:

```
    8   EN Region                AR المنطقه
    9   EN Activity              AR عنوان        <-- diverges here, in the MIDDLE
   10   EN     --                AR الخدمة
```

Zipping to the shorter list would write the Arabic **address** into `activity_ar` for those
24. So the tempting repair — tolerate a trailing extra box — is wrong, and `merge_locales`
is right to refuse rather than zip. What was wrong was the conclusion that NO repair exists.

**The repair that does exist, and reads no Arabic label.** `PROFILE_FIELDS`
(`scrapex/extract/muqawil.py:121`) is an ordered map of the **eleven** English labels **in
page order**. Every one of the 129 English pages carries a subsequence of those eleven, in
order, with no unrecognised label — checked, zero strays. So when the English page omits a
box, *which* box it omitted and *where* is known, and the Arabic list can be indexed around
that gap. Measured over all 188:

| count | outcome under the canonical-position repair |
|---:|---|
| **121** | **recoverable** — Arabic is the longer side, so the gap is deducible from English |
| **8** | refused — Arabic is the SHORTER side, and which field *it* dropped cannot be deduced without reading an Arabic label |
| 59 | untouched — layer 1 still refuses them, and rightly (`OP-64`) |

**Why this preserves the property the current code is built on.** `merge_locales`'s docstring
argues that reading no Arabic label is what stops a spelling change in one from breaking the
merge — and the site's own `المنطقه` is spelled with `ه` where `ة` belongs, so that argument
has teeth: a hand-written Arabic vocabulary would have to carry the site's typo and would
break the day they fix it. The canonical-position repair reads Arabic **values** only, exactly
as today.

**Worth +121 contractors with their address** — a field the English page cannot supply for
anyone. Independent of the network, replayable from the snapshots already stored.

**BUILT AND RULED, 2026-08-24 — `R-51`.** He was shown the two options and chose the
second: «نفذ ب». `align_locales` (`scrapex/extract/muqawil.py`) locates the gap from the
English side and `merge_locales` asks it; no Arabic label is read, which is the property
the old refusal was built on and is worth more than the 129. Guarded by
`tests/test_the_two_locales_line_up_around_a_missing_box.py` on two real page pairs
committed as fixtures, and mutation-tested on eleven branches — one mutant survived the
first draft and proved the order check was passing for the wrong reason.

**Measured after the repair, replaying the 188 through the parser:** 121 merge, 24 of them
carrying an address they did not have, 8 still refused, 59 still at layer 1.

**AND THEN RUN FOR REAL, which is the number that counts.**
`--approve --run-ref profiles-2026-08-22` over 17,417 stored pairs, **83.9 minutes, zero
network requests**:

| | |
|---|---|
| profile rows | 17,264 → **17,385** — **exactly 121 added** |
| of those 121, carrying an address | **24** — the prediction, to the row |
| listing rows with no profile row | 188 → **67** = the 8 refused plus the 59 dead ids |
| pages unchanged, writing nothing | 17,249 (`DEC-10` idempotency held) |
| re-parsed with NEW values | **0** — not one already-approved row was rewritten |
| rows where `activity_ar` equals `address` | **0** — the corruption a tail-drop would have caused, on the whole table and not just the new rows |

The 67 that remain are the floor this repair cannot lower: 59 need a page the site no
longer serves, and 8 need an Arabic label read. `REQ-42` owns the 59. The 59 belong
to `REQ-42` (a withdrawn contractor entered with a state that says so) and are separate
from this.

### OP-65 · A snapshot records the URL we ASKED for, never the one we landed on

**Found 2026-08-23 by the owner asking whether the new guard was even correct.** It is —
and the question found something better than the guard.

`OP-64` diagnoses a dead profile id from the CONTENT of the page that comes back. That was
reading the symptom. The cause, measured live:

```
asked   /en/contractors/20074580/143
302  ->  /contractors
302  ->  /en/contractors
landed  /en/contractors        <- two hops, to the listing
HTTP    200        372,141 bytes        the listing, 20 contractor links

control
asked   /en/contractors/1004/143
landed  /en/contractors/1004/143
HTTP    200        122,717 bytes        a real profile
```

**muqawil redirects a withdrawn id to the contractors listing** and answers 200, in TWO
hops through a locale-less `/contractors`.

> **CORRECTED.** This entry first said the locale switched — *"`en` was asked for and `ar`
> came back"* — and made that the fingerprint. Re-measured live: `en` was asked for and
> `en` came back. The real fingerprint is the two-hop 302 chain, which is stronger and
> which the first measurement never recorded.

### Why nothing in the project could notice

`generic_page_snapshot` stores **`source_url`**, which is the URL the crawler *requested*.
There is no column for the URL the response actually came from, and `httpx` follows
redirects silently (`follow_redirects=True` at `scrapex/funnel.py:194` and three other
call sites). So a page fetched from somewhere else is stored under the address we wanted,
and every reader downstream — the parser, the approval, the coverage report — believes it.

**This is a whole class, not one site's quirk.** Any source that answers a gone resource
with a redirect to an index page produces the same silent substitution, and `OP-64`'s
remedy would have to be written again per parser. A `final_url` on the snapshot catches
all of them at the seam where the evidence is created.

### What it needs

1. **A `final_url` column** on `generic_page_snapshot`, written by the fetch seam.
2. **A refusal at the seam, not in the parser**: if the final URL is not the requested one,
   the page is evidence of a redirect and not of the thing that was asked for. `OP-64`'s
   layer 1 then becomes a second line rather than the only one.
3. **The 78 snapshots already stored under the wrong address stay wrong**, because the
   fact was never captured. They are identifiable by content and that is all.

**It does not replace `OP-64`.** A page can be substituted without a redirect, and the link
test still catches that. But the redirect is the cheaper signal and it arrives first.

### OP-64 · The site answers a dead profile id with the LISTING page, and the parser believes it

**Found 2026-08-23 by the owner asking whether the counts were duplicated.** They were
not. Chasing why the membership number repeated found this instead.

**`card_membership_number` on the listing is unique and the owner's rule holds**: 17,304
rows, 17,304 distinct values, zero blank. The repeats are in the PROFILE dataset —
13,347 rows, 13,333 distinct, **three values shared**, one of them (`117511752`) sitting
on **thirteen different contractor ids**. Fourteen contractors carry a different
membership number in the profile table from the one on their listing card.

**Re-measured 2026-08-24, after the profile crawl finished: 17,264 rows, 17,250 distinct,
still exactly three shared values and still 14 excess rows** — `117511752` on 13 ids,
`121612167` on 2, `587458748` on 2. The row count above was taken mid-crawl and did not
say so, which is the defect; the finding itself did not move, and 3,917 further profiles
added not one new collision.

**The cause is not bad data entry. The site served the wrong document.**

```
GET /en/contractors/20034161/143
    <title>       Contractors | Muqawil Platform
    decoded       375,363 bytes, 22 section-cards
a real profile    ~122,000 bytes,  7 section-cards
```

For an id that no longer resolves, muqawil answers **the contractors listing** with HTTP
200. `read_profile` calls `_boxes(soup)` over the whole document, so it read the first
card of that listing and attributed a stranger's values — `160916095`, `Small`, `96 h`,
`RIYADH - Riyadh` — to whichever id had been asked for. **That is why thirteen ids share
one membership number: they all took the same stranger's card.**

**Measured, and it is small.** A random sample of 500 decoded snapshots:

| | | |
|---|---|---|
| real profile | 499 | 99.8% |
| listing served instead | 1 | 0.2% |

About 70 of the 34,834 snapshots (95% CI 0–206) are the wrong document.

> **CORRECTED TWICE, and the second correction reverses half of the first.** This entry
> first said the rows hold *"another company's address, city, size and email"*. I
> corrected that to *"the membership number alone"*. **Two adversarial reviews measured
> both and both were wrong** — the first overstated it, mine understated it.
>
> **What is actually wrong, dumped from `generic_record_id=20579`:** FIVE declared
> columns carry the stranger's values — `membership_number`, `company_size`,
> `company_size_ar`, `training_credit_hours`, `training_credit_hours_ar` — plus **twelve**
> undeclared `x_*` fields. `address`, `organization_email` and the coordinates ARE null,
> which is the half my correction got right.
>
> **And the blast radius is 39 ids, not 14** *(as of 2026-08-23T16:00Z — see the note
> below; it was 72 before this entry was even committed)*. 78 snapshots, both locales; 14
> produced a row, **25 produced none**, which is why counting rows undercounted the
> defect by 2.8x. Of the 39, **28** sit in the id block `20074580`–`20075073` — 9.96% of
> that block against 0.224% crawl-wide, **44x** — and **eleven** are outside it with no
> story, not two.
>
> **AND THIS CENSUS WAS STALE BEFORE THE COMMIT THAT STATES IT.** Round two measured the
> clock: 39 ids / 78 snapshots was exact at `16:00Z`, and by `16:44Z` — when the commit
> asserting it was authored — a targeted re-crawl had made it **72 ids / 154 snapshots**,
> because re-fetching a dead id stores the listing again. **A census of a growing corpus
> needs an as-of instant or it is a claim about the past written in the present tense.**
> The undercount factor is not 2.8x but 5.2x, and the block percentages below
> (9.96%, 44x) were computed from an intermediate denominator and do not reproduce: the
> block holds 321 ids with profile snapshots, so it is 8.72% and 39x.
>
> **It is the LAST card on the listing, not the first.** `fields[key] = value` is
> last-wins over every `div.info-box` pair on the page, and the poisoned page has 160 of
> them. The values this entry originally quoted — `160916095`, `Small`, `96 h` — belong
> to the FIRST card and appear in no stored row.
>
> The numbers below are kept as written, with their errors, because `C4` says a changed
> mind keeps its predecessor:
>
> ```
> id 20034161   membership 117511752   (its listing card says 355735571)
>               city=None  email=None  latitude=None  company_size='Very Small'
> ```
>
> The profile parser looks for `PROFILE_FIELD_ORDER`'s labels, does not find them on a
> listing page, and emits **nulls**; only the membership number leaked through. Populated
> fields average 18.0 on the wrong rows against 18.2 on healthy ones — they are not
> impersonating anyone, they are empty with one borrowed number.
>
> The original claim came from probing the page with `_boxes()`, which is what
> `read_listing` uses; the stored rows came from the profile path, which behaves
> differently. **A probe is not the pipeline.** The rows themselves were the only honest
> witness and they were one query away.
>
> It still is not harmless: thirteen ids collide on one number, and anyone searching by
> membership number reaches the wrong company.

### What it needs

> **SUPERSEDED, and the paragraph below is the design this entry's own correction
> refuted.** It is kept per `C4`. What shipped counts CONTRACTOR LINKS, not cards: a
> profile links to exactly itself and a listing to many, so there is no threshold to
> defend. The card count was measured with a regex the parser does not use — through
> `soup.select` a real profile has six — and 160 real listing pages carry fewer than 15
> cards, so the gap it relied on did not exist on the side it guarded.

A **shape check before parsing**: a profile page is not a listing, and 22 section-cards
where 7 are expected is the site saying "this id is gone" in the only way it does — with
a 200. Refuse the page rather than parse it; the id belongs in a not-found list, not in
the table. `PROFILE_FIELD_ORDER` already distinguishes the two documents at approval time
(`scrapex/contractors.py`), so the knowledge exists and is applied one step too late.

**And the rows already written must be found and removed**, not left: they are wrong in
the most expensive way, being plausible. The listing's own membership number identifies
them — a profile row whose number disagrees with its listing card is the marker.

### A note on the measurement itself, because it nearly shipped wrong

The first attempt discriminated on *"a profile has no section-cards"*. A real profile has
**seven**, so 398 of 400 sampled fell into "other" and the run reported **0.5%** from two
survivors. The number was an artefact of a broken instrument, not a finding. It was caught
because 99.5% unclassified is not a result. **A discriminator has to be measured against a
known-good example before it is trusted to count anything.**

### OP-63 · The word "products" over a contractor directory — PANEL HALF CLOSED, the engine page is `Q-26`

**Status: the PANEL half is CLOSED by this branch. The ENGINE PAGE half is OPEN and
is a design question, not a noun.** Found 2026-08-23 while diagnosing why his Data
screen still showed two muqawil cards — he did not report this one, which is why it
is here and not in `REQUESTS.md`.

His screen read:

```
muqawil.org / Saudi Contractors Authority · contractors [Row 17,304]
  17,304 products
```

**A contractor is not a product, and 17,304 contractors are not 17,304 products.**

**THE PART THAT MAKES IT A REAL FINDING RATHER THAN A TYPO: the engine already knew
the word was meaningless, in writing.** `_dataset_rows` (`scrapex/webui/app.py`)
carries this comment over the line that fills the field:

> *"`observations` is what the Data screen filters on, and for a directory the honest
> number is its rows. `products` has no meaning for a company, so it carries the same
> count rather than a zero that would read as an empty dataset."*

So the engine deliberately passed a duplicate of the row count through a field it
documents as meaningless for a company, and the panel printed the meaningless word
underneath it. Neither side was unaware; the two notes never met.

#### What was fixed, and why the noun is not a special case

`extension/app.js` hardcoded `${fmtCount(s.products)} products` for every card. The
replacement is `countLine`, three branches, each keyed on what the engine reports
rather than on a key's spelling — because `jobs` and `tenders` are named in
`CLAUDE.md` as coming and `if (contractors)` would be the third wrong noun the day
`tenders` lands:

| the card | the second line | why that |
|---|---|---|
| a price source | `1,812 products` — **unchanged** | there the word is TRUE and the number is a DIFFERENT one: spark-eshop reads `[Row 6,969]` above `1,812 products`. This is why the noun could not simply be replaced |
| a dataset with a confirmed one-to-one detail crawl | `Contractor profiles: 704 of 17,304 (4.1%)` | `R-47`'s second point. For a dataset `observations` and `products` are the SAME number, so any noun would print the figure twice; coverage is the fact that slot was missing |
| any other dataset | `8,412 rows` | the honest generic |

**WHY `rows` AND NOT A BETTER WORD, since `R-45` governs it.** «ما يقوله الموقع هو
مصدر الحقيقة الوحيد» forbids inventing a label the site never gave, and it rules out
the two tempting alternatives: `dataset_definition.original_name` would print
`17,304 contractors` for one dataset and `704 contractor_profiles` for the next, and a
raw key dressed as an English noun is exactly the invented claim `R-45` refuses.
`dataset_kind` was checked and is not the unit of a row — measured read-only on his
warehouse 2026-08-23, it is `'table'` for both muqawil datasets, a structural kind.
**Nothing in the warehouse names the unit of a row.** `rows` claims nothing about the
site, and it is not a new vocabulary either: `sourceIdentity`'s default metric label
is already `Row`, so the line above reads `[Row 17,304]`, and the Drive offline card
in the same function already prints `<n> rows`. The COVERAGE label is the one word
taken from the site, and it is the child dataset's stored `display_name` — what the
approval recorded, never ours.

**`rows` IS THE ANSWER, NOT A FALLBACK, and the distinction matters because nothing
has been ruled here.** No ruling covers the boundary between `products` and a
directory, so this is a choice and it is recorded as one: a generic word that is true
of every dataset beats a specific word that is true of one and invented for the rest.
The moment the site itself gives us a word for what a row IS — not what the table is
called, which `display_name` already holds — that word wins and this branch should be
revisited. **His call if he wants a different word;** the reason for this one is above.

> **CHECKED AGAINST `R-45`'s CORRECTION, 2026-08-23, because that correction landed
> while this was open.** #261 measured that the per-row record card **has existed on
> the engine since 2026-07-22** — 967 lines of `grid.js`, opened by row *selection*,
> which is why a census searching for `rowFormatter` missed it — so `R-45`'s own table
> was wrong about the card, and products have it while contractors do not.
>
> **None of that moves the noun.** This entry rests on `R-45` **part 1** — *"WE NEVER
> TRANSLATE. The site's words are the record… A mapping we invent is our claim dressed
> as the site's data"* — and the correction is about **part 2**, whether the row's card
> exists and what it costs. The ruling's own words are that it *"stands unchanged"*.
> Re-checked rather than assumed, since a reasoning chain resting on a ruling that has
> just been corrected is exactly the thing worth re-reading.

#### The open half: the engine's own page says it too

**`/source/contractors` prints a "Products" tile over the very same rows** — and that
is the surface this branch did not touch. `_source_overview.html` renders four tiles
from `SourceSummary`, and `/source/{key}` fills `products` for a dataset out of
`_dataset_rows`, which is why the field is still sent rather than dropped.

**RENDERED, not read.** The page was fetched from a real engine holding one approved
dataset of 4 rows and the four `<dd>` values read off the returned HTML — because a
claim about what a template prints, reached by reading the template, is the shape this
repository keeps catching:

```
GET /source/contractors -> 200, 42,058 bytes
  Products    4
  Variants    0
  Data rows   4
  Matched     0
```

**Three of those four say nothing about a contractor directory and the fourth
duplicates the first**: `Products` is the meaningless field, `Variants` and `Matched`
are price-path concepts a company has none of, and `Data rows` is the honest number
already. So this is not the panel's one-line fix wearing a different template — it is a
question about what a dataset's overview should show at all.

**The question for him is [Q-26](#q-26--for-a-dataset-does-the-overview-keep-four-tiles-or-show-two)**, filed in §6 with the three priced options, because a question buried in an open problem is not on the register that tracks what he owes an answer to.

### OP-69 · The release gate proves the engine STARTED, never that it can serve a page

**Found 2026-08-23 by the session that wrote `OP-62`'s fix. Filed 2026-08-26, and the
three-day gap is the defect worth recording first.**

**THIS ENTRY IS LATE AND THE LATENESS IS THE LESSON.** The session that fixed `OP-62`
scoped this gap deliberately OUT of that change — correctly, because widening a defect fix
into a new feature is how a fix stops being reviewable — and then **told the primary
session about it rather than leaving it.** The primary said it would take it and give it a
number. **It never wrote it down.** For three days it existed in a chat channel, which is
the one place `CLAUDE.md` says does not count: *"the repository is the only memory. A note
that is not committed did not happen."* The finder had to come back and ask for the number
a second time, having first checked `BACKLOG.md`, `STATE.md`, `REQUESTS.md`, `LESSONS.md`
and `RULINGS.md` and found nothing.

**So it is filed before the fix rather than with it.** Had it been filed with the fix, and
had the fix not been authorised, the record would have been lost a second time by the same
mechanism.

### The gap

`OP-62` was the published engine unable to serve a single page: `packaging/build_engine.py`
told PyInstaller to carry two data paths and the runtime opens five. It is fixed — all five
are in `RUNTIME_DATA` and `tests/test_the_frozen_engine_carries_its_own_files.py` guards
them by enumerating what the source actually opens rather than restating the recipe.

**The release gate, however, still stops one step short of the thing that fails.** Its final
check runs the built `.exe` and requires four lines of output, the last being `ScrapeX UI`.
That line is printed by `scrapex/cli.py`'s `_cmd_ui` only once `create_app` **has returned** —
which is a real and deliberate improvement, because `StaticFiles(check_dir=True)` refuses to
mount a missing directory and so a bundle without `scrapex/webui/static` cannot reach it.

**But `Jinja2Templates` does NOT check its directory at construction.** `RUNTIME_DATA`'s own
comment says so in as many words:

> *"Jinja2Templates does NOT check its directory at construction, so a missing templates
> tree is not a startup error; it is a `TemplateNotFound` on whichever page the owner opens
> first."*

So a build missing `scrapex/webui/templates` **starts cleanly, prints all four lines,
passes the gate, reports itself healthy — and answers every page with
`TemplateNotFound`.** The same is true of `apps_script/StagingAppScript.txt`, whose absence
is quieter still: the route answers 404 saying the script *"is not bundled"*, which was true
of every engine ever shipped until `OP-62` closed it.

**This is the same shape as `OP-62` itself, which is why it is worth a number rather than a
shrug: a gate that proves the step before the one that breaks.** `OP-62`'s own history is
the argument — the gate had already been widened once, after `0.2.1` shipped a black window,
and it *still* stopped one line short of the failure `0.3.0` shipped.

### What today's guard does and does not cover

**Covered, and this matters when scoping the work:**
`tests/test_the_frozen_engine_carries_its_own_files.py` stages a bundle from `RUNTIME_DATA`,
starts the engine inside it, and asserts every `templates/**/*.html` in the repository is
present — enumerated from the tree, not restated. It carries its own mutation test, which
removes the static directory and requires the check to fail.

**Not covered:** nothing anywhere fetches a page from the built artefact. The suite proves
the *recipe* is complete against today's source; it does not prove the *published binary*
answers `200`. Those differ the moment a build step, a PyInstaller upgrade or a
`--exclude-module` changes what actually lands in the archive — and the artefact is the thing
the owner installs.

### The remedy, which is small

In `.github/workflows/release-engine.yml`, after the existing double-click step: bind a port,
fetch `/`, require a **200 with real content** rather than merely a status line. It must
assert something a template produced, or it proves only that uvicorn is listening.

**And it must keep the timeout shape the current step uses.** `ScrapeX UI` is the last thing
printed before uvicorn takes the process, which is why that step passes on a *timeout* rather
than an exit code. A fetch step has to start the engine in the background, poll the port, and
then be sure to kill it — a release job that leaks a listening engine is its own defect.

### Who holds it

Being built on `fix/the-release-gate-fetches-a-page` by the session that found it, base
`35962cc`. **This entry deliberately does not depend on that branch landing.**

---

### OP-84 · ~~The warehouse is ahead of `main` again, and `OP-33`'s remedy was a merge rather than a guard~~ — CLOSED 2026-08-27, and this time with the guard

**Found 2026-08-27 · proved by running · [R-64](RULINGS.md#r-64--a-migration-reaches-his-warehouse-only-after-it-is-on-main-and-no-tag-is-cut-while-his-warehouse-is-ahead) rules it**

> **CLOSED 2026-08-27 in #276, and closed differently from `OP-33`.** `0011` and `0012` are on
> `main`, and `database-status` from `main` now answers `"ok": true · "Healthy" ·
> schema_version 12` — read after the merge, not before it.
>
> **`OP-33` was closed by a merge, which is why it came back.** This one is closed by a merge
> **and two guards**: the step *"No unmerged branch may hold a migration this release does not
> carry"* in `release-engine.yml`, proved to refuse against the real refs
> (`origin/main` ceiling 10 → REFUSED naming `origin/feat/organization-enrichment(12)`), and
> `.githooks/pre-push`, executed in `tests/test_no_tag_is_cut_while_the_warehouse_is_ahead.py`
> with a stubbed probe. **Nine mutations, nine killed** — and the ninth found a hole in the
> test itself, where an assertion matched a second occurrence of the string it was checking.
>
> **What is NOT closed:** `feat/organization-enrichment` is still unmerged and unreviewed at
> 7,832 lines, its `REQ-44` collides with `main`'s, and its 12 tables now exist on `main` with
> **no reader** until it lands. It is queue position 3.

| | |
|---|---|
| his live warehouse | `PRAGMA user_version` = **12** |
| `main` | migrations stop at **`0010`**, so a build from it reads **v10** |
| `database-status` from `main`'s level | `"ok": false` · *"Needs a newer ScrapeX (schema v12; this build reads v10)"* |
| where `0011`/`0012` live | `feat/organization-enrichment` — pushed, **no PR ever opened**, 3 ahead and **8 behind** |

**So a `0.4.0` release built from `main` would refuse to start on his machine** — which is
`OP-33` exactly, five days later, with a different pair of migrations. `R-24` forbids the
shortcut, and the gate's own message says *"do not downgrade the database."*

**Nothing guards the class.** `migration-authority` in CI reads the branch's own diff; it
cannot see another branch and cannot see his machine. `OP-33` was closed by merging #243, so
the remedy did not survive the incident.

**And the branch is not a small thing to merge for the sake of the gap:** 7,832 lines across
44 files, 415 lines of SQL, absent from `REQUESTS.md` entirely, and it edits
`tests/test_the_documents_cite_what_they_claim.py` and
`tests/test_the_registers_cannot_collide.py` — **the two guards that keep this documentation
system honest.** He ruled it is read and reported before anything of it merges.

---

### OP-90 · A re-approval silently un-retires the rows `OP-64` disowned

**Found 2026-08-27 while building `R-54`'s root half**, and deliberately NOT fixed there —
it is outside that ruling and it is his call whether a confirmation may reactivate a row.

`approve_candidate`'s upsert ends
`last_seen_at=strftime(...), status='active'` — **unconditionally**. So the next
re-approval of the fourteen profile pages `OP-64` retired writes `status='active'` back over
them, and the disowning disappears with nothing raised. Those rows are the ones whose
membership number disagrees with their own listing card: the site answered a dead id with the
contractors listing at HTTP 200, so their address, city and coordinates came from nowhere.

**What makes it live rather than theoretical:** `OP-64`'s own open half is that *"no command
targets specific ids today"*, so the honest repair is a re-fetch of those pages — which is
exactly the operation that would resurrect them.

**The confirming path added for `R-54` does not do this**, and its docstring says why: a
withdrawal somebody decided outranks an observation, which is `sightings.row_state`'s first
precedence rule. A mutation that adds `status='active'` to it is killed by
`test_a_confirmation_does_not_resurrect_a_retired_row`. So this entry is about the ONE place
that still does it.

**The question underneath is his:** should the upsert leave `status` alone when the stored
row is `retired`, or should a re-fetch that produces the same wrong number be refused
earlier — at `OP-64`'s layer 2, where the mismatch is already detected?

### OP-89 · `STATE.md`'s "Open pull requests" is 535 lines in which nothing is open

**Measured 2026-08-27.** The section runs from the heading to `## Track 1`, and **every pull
request in it has merged** — #274, #244 and the rest. The heading is present tense and the
document is the one every session is sent to second, after `CLAUDE.md`.

It is not deletable as it stands: the entries carry measurements other documents rely on, and
`tests/test_the_documents_cite_what_they_claim.py` pins citations inside them. Folding it means
moving each measurement to the track it belongs to and leaving a one-line merged row behind —
the same operation that took the `.md` corpus from 42,592 lines to 32,702 earlier the same day.

**A dated banner was added instead**, which makes the section honest without moving anything.
That is a stopgap and this entry says so.

### OP-88 · His engine was serving from an unmerged branch's worktree, and the restart button cannot move it

**Measured 2026-08-27, immediately after `#279` merged**, while checking whether `0013` had
reached his warehouse.

His engine on port 8000 was `pythonw -m scrapex.cli ui` with its **cwd in
`C:\tmp\ScrapeX-organization-enrichment`** — the `feat/organization-enrichment` worktree,
`VERSION 0.3.4`, migration ceiling `0012`. `-m` puts cwd ahead of site-packages, so the
branch's package won even though the editable install resolves to the main checkout.

**The proof was a route, not a path:** `/api/dry/contractors` from the live engine returned
**zero** matches for `reapprove_schema`, the pass `scrapex/passes.py` declares.

**This is how the warehouse reached `user_version 12` while `0011`/`0012` were on no merged
branch** — the sequence [R-64](RULINGS.md#r-64--a-migration-reaches-his-warehouse-only-after-it-is-on-main)
now forbids, done before `R-64` existed.

**`POST /api/engine/restart` cannot repair it, and this was tried.** `relaunch.repo_root()` is
`Path(__file__).resolve().parent.parent` **of the running process**, so the helper relaunches
whichever checkout the old engine was born in. It answered `ok: true` with a fresh pid and
came back on `0.3.4` — the route's own docstring names this fault («a database written by a
NEWER build than the process reading it») and cannot cure the case where the *process* is the
old build from another directory.

**The Startup entry is correct** — `ScrapeX Engine.vbs` runs from
`C:\Users\User01\source\repos\ScrapeX`. So a logon fixes this and the button does not.

**Fixed by hand here**, with `0 running` and `0 queued` jobs confirmed first: stop the
process, then `wscript "ScrapeX Engine.vbs"`. The engine came up on `0.4.2`, found the
warehouse behind, backed it up to
`scrapex-engine.pre-upgrade-20260827T125628Z.backup.db` and applied `[13]`.

**Open:** should the restart route refuse when its own package is not the installed one, or
relaunch from the console script instead of from `__file__`? That is a design question, and it
is the only reason this entry is open rather than done.

### OP-87 · `feat/organization-enrichment` reviewed before merge — four blockers, and the architecture is sound

**Reviewed 2026-08-27 on his ruling** («أقرأُه وأُبلِغُك قبلَ أىّ دمج»). 7,832 lines, 44 files,
queue position 3. **The two suspicions that brought it here were both wrong, and both are
recorded as withdrawn rather than quietly dropped.**

| # | finding | verdict |
|---|---|---|
| 1 | **`REQ-44` collides.** The branch uses it for the website/LinkedIn request; `main`'s `REQ-44` is his own instruction that the state gets its own column (`R-27`, #235). `REQ-43` is free and stays | **blocks merge** — renumber to `REQ-47` |
| 2 | **Three versions disagree.** The branch sets engine `0.3.4` and `extension/manifest.json` `0.3.3`, and its capability declares `since="0.3.2"` — a version that will never be released. `main` is `0.4.1` and he ruled the branch takes **`0.5.0`** | **blocks merge** |
| 3 | **It hand-rolls the schema-version lifecycle.** In `scrapex/enrichment/service.py` — a file that exists only on the branch, readable with `git show feat/organization-enrichment:scrapex/enrichment/service.py` — it computes `max(version_number)+1`, retires the active version with a raw `UPDATE … status='retired'`, and inserts `dataset_schema_version` + `schema_version_field` directly — while `extract/service.py`'s `_retire_or_refuse` owns exactly that under `R-31`. **It does call `catalog.register_field`**, so fields are not reimplemented, only the version lifecycle | **declared debt** — see below |
| 4 | **A third outbound HTTP owner** — `R-66`, `R-67`, `OP-86` | ruled, not a blocker |

**Why 3 is debt and not a blocker, stated so it is not re-argued.** `R-31`'s subset rule exists
because a shrinking field set is how a broken parser looks. This schema is a fixed
`OUTPUT_FIELDS` constant, not parsed from a site, so the failure `R-31` guards cannot occur
here. What remains is a second implementation of one lifecycle — the pattern the muqawil audit
already recorded when `dataset_table_payload` reimplemented `fields.hidden_columns`.

### The two suspicions that were wrong

**It does not violate `R-45`, and the schema forbids it from doing so.** Its three
`UPDATE generic_record` writes are all `WHERE dataset_definition_id = <output_id> AND
source_locator LIKE 'organization:%'` and all set only `status='unavailable'`, `OP-26`'s ruled
marker. **The muqawil dataset is read and never written.** And it is not a convention:
migration `0011` carries `trg_enrichment_definition_datasets_differ_insert`, which
`RAISE(ABORT, 'the enrichment output must be a new dataset')`. It also refuses an enrichment
output as its own source.

**And the guard edits were legitimate.** It changes
`tests/test_the_documents_cite_what_they_claim.py` and
`tests/test_the_registers_cannot_collide.py`, which is what brought it under suspicion — a
branch that edits its own guards. Read: they are PINNED line numbers following its own code
shifts (`app.py` 1671→1679, `version.py` 483→494) and two register-collision rows. **That is
what the guard is for, and the branch did the right thing.**

### What it is, measured

A new subsystem: `scrapex/enrichment/` (4,000+ lines), `extension/enrichment.{js,html,css}`
(1,060), two migrations (415 lines of SQL, now on `main`), 1,523 lines of its own tests.
**No secret is committed** — `google_places` takes the key as a parameter, and it made **zero**
observations, so no paid call was billed. Its website provider is careful: `robots.txt`, and it
refused **64** off-domain redirects, **10** HTTPS downgrades and every private peer during its
live run.

**Its live run is what produced `OP-84`'s discovery** and was cancelled at his ruling: job
`job_f0f269d7336a`, **4,046 of 17,304**, `facts_changed` 25,132, `needs_manual_review` 435.
The rows are in his warehouse and the run is resumable — `item_status='pending'` is its own
ledger.

---

### OP-86 · `crawl_obey_disallow` is a robots setting with no surface on either side

**Found 2026-08-27 while enumerating the keys [R-66](RULINGS.md#r-66--every-outbound-request-knob-is-a-setting-the-user-controls-and-robots-is-one-of-them) names**

`crawl_obey_disallow` is read in code and appears in **neither** `extension/app.html` nor
`scrapex/webui/templates/settings.html` — measured by grep on both. Its four siblings are on
both surfaces (`crawl_min_interval_s`, `crawl_honour_delay`, `crawl_timeout_s`,
`crawl_user_agent`) and `crawl_parallel_sources` is in the extension only.

**So the one robots knob that decides whether a `Disallow` is obeyed is settable only by
editing the database by hand** — the same shape as `crawl_scope`, which `REQ-45` recorded
and which `--details` refuses under while telling the owner to change a setting that has no
place to be changed.

**It is `R-66`'s first item**, and it is registered separately because it is true today and
independent of the enrichment branch landing.

---

### OP-85 · `Coverage.fraction` returns 1.0 when nothing has ever been sighted

**Found 2026-08-27 while building `#274`'s dry route**

`Coverage.fraction` answers **1.0** for a dataset with an empty sighting ledger, while its own
sentence says coverage *"cannot be stated"* in that case. So a dataset nobody has ever crawled
reports **100% covered**, and `contractor_profiles` held zero `dataset_sighting` rows until
recently — the exact case.

`#274`'s route emits **NULL** rather than 1.0, so the surface is honest today. **The dataclass
is unchanged**, which means the next caller gets 1.0 again.

**Not urgent, and the reason is specific:** the only two readers are the route (correct now)
and `report_coverage`'s printer, which prints the count beside the fraction so a reader sees
`0 of 0`. It becomes urgent the moment a third caller compares the fraction to a threshold.

---

### OP-83 · 1,728 snapshots were never compressed — 69% of the stored bytes, 623 MB recoverable

**Found 2026-08-27 by counting the warehouse instead of quoting the study.**

| | |
|---|---|
| snapshots in `generic_page_snapshot` | **57,041**, 921.5 MB of `html_content` |
| of them `html_codec = 'plain'` | **1,728 rows — 636.8 MB** |
| share of the bytes / of the rows | **69.1% / 3.0%** |
| captured | `2026-08-17T06:44:32Z` … `2026-08-20T05:56:40Z` — before the codec shipped |
| distinct URLs | 1,728 — no duplicates to dedupe first |
| at the measured 46.3× | **13.8 MB. 623 MB recoverable, zero network** |

**These are the first listing crawl's 864 pages in both locales.** Compression landed after
them and nothing went back. `scrapex/snapshotbody.py:193` reads either codec, so they are
correct today — just large. The measurement that replaced the projection is in
[STORAGE.md](STORAGE.md#measured-on-the-finished-warehouse--2026-08-27-and-the-headline-was-4x-optimistic).

**Why this is an `OP` and not a plan.** Re-encoding a stored row rewrites evidence, and
`generic_page_snapshot` is the table this repository treats as immutable. The `content_hash`
stays valid — it is taken over the decoded body — but a session must confirm that before
touching a row, and `scrapex/warehousemerge.py:198` already refuses a non-`plain` row whose
`html_dict_id` is null. **Not urgent:** 623 MB on a 1.2 GB database is worth doing, and
nothing breaks while it waits.

---

---

### OP-82 · The palette registry is two hard-coded aliases, not a registry

**Found 2026-08-27 by sweeping the documents, not by a failure.**

[scrapex/webui/app.py:195](../scrapex/webui/app.py#L195) rejects anything outside
`{"whatsapp", "github"}`. Under [R-59](RULINGS.md#r-59--the-palette-registry-brand-is-default-alternatives-is-extensible-teal-is-debt)
those two names are **legacy aliases** and the real names are `brand` and `blue`, with
`alternatives` extensible. So the route enforces the compatibility layer and knows nothing
of the thing it is compatible with.

**Not urgent** — no third palette exists to add. It is registered because the ruling that
contradicts the code was itself invisible until today, and the next session to add a palette
would find the refusal before it found the rule.

---

---

## 3. Decided, not yet built

### DEC-1 · Topology A — the TypeScript extension as the public product
**Approved 2026-07-18. Zero commits since.** This is the largest gap between what was
decided and what exists.

The owner chose Topology **A** over the study's recommendation of B — *"A, but leave the
current engine running until the new engine is finished"* — with the Python engine kept as
the golden reference oracle (its `OWNER DECISION` section, at `d6f4967`). The plan records Spike 1
(fingerprint parity) as **PASSED** and names `spikes/fingerprint-parity/` as the artefact.

What I can verify: `git log --all -- spikes` returns nothing — that directory has never
existed in this repository. The surviving descendant is `contract/parity/`, which every
commit reports as "contract parity 3/3". Spike 2 (wa-sqlite + OPFS running `db/schema.sql`
verbatim inside an MV3 worker) has never been attempted, and Phases 1–3 of the A roadmap
(port connectors + normalize + rowspec + ingest to TS) have not started. Every one of the
last 130 commits is Python, and the extension has remained a thin panel over the Python
engine's JSON API.

That may well be the right outcome — the Python product got very good in the meantime — but
nobody ever said so out loud.

**Half of this closed on 2026-08-27, and it is the half that was never the point.** The
document was cut to its §8.3 under [R-60](RULINGS.md#r-60--a-finished-document-leaves-the-tree-and-git-is-the-archive),
so it no longer reads as the live plan and its §8 no longer asks him to confirm a topology
its own header answered. **The decision is still open.** `R-48` and `R-50` describe the
architecture that actually shipped — extension as control room, engine as helper — and
neither of them says Topology A was abandoned, which is what `Q-6` asks.

**Next action:** **Q-6**, unchanged. Editing the document was never the answer to it.

### DEC-2 · shopify cannot resume per page as it stands
`fd2b6d9` states it plainly: the English-title pass runs *after* paging and back-fills
`product_name` into rows already built (`scrapex/connectors/shopify.py:57-63`), so a page
yielded during the loop would go out without its English name. Fixing it means fetching
English first or accepting two passes over the catalogue — a redesign, deliberately not
smuggled into a mechanical change.

### DEC-3 · custom_json's interruption rescue cannot survive an interruption
`fd2b6d9`: it accumulates pages into one list, and its `CrawlBlocked` rescue table carries
no page token — so `clear_untokenized` deletes the rescue on resume. The rescue is destroyed
by exactly the event it exists for.

### DEC-4 · The rest of the vocabulary sweep
`docs/column-vocabulary.md` §Status. The language half landed (0038–0042). Still to move:
the `price_*` family, `tax`, `curation`, and `open`/`product_url` → `product_link`. The last
one is blocked on **Q-7** (a `dataset_field` UNIQUE collision — one of the two names has to
lose).

### DEC-5 · Sources that are proven and unfinished
- **ELBUROJ** needs a second pass for English names, on a 10s-delay crawl
  (`plan-closing-the-gaps` §5.2). Measured in `2253308`: 3,874 products at `Crawl-delay: 10`
  ≈ **eleven hours**.
- **SIKA datasheets** want their own connector (§5.3). The site is Sika Egypt's *corporate*
  AEM instance (`egy.sika.com`), not the shop: ~310 products and ~1,050 TDS PDFs behind
  stable DMS GUIDs, with sitemap `lastmod` driving an incremental re-scrape. It publishes
  **no prices** — it would feed `material_attribute_value` only, never `price_observation`.
  `datasheet-enrichment` is in `vocab.ConnectorFamily` with **no builder** in
  `connectors/factory.py`, so the connector is the whole of the work and a manifest entry
  cannot come first: `test_no_manifest_entry_declares_a_family_nothing_can_build` refuses a
  family nothing can build. That is why `SIKA_EGYPT_DATASHEETS` was removed in `256cd27`,
  which also records the two things that make this bigger than it looks — SIKAEGSHOP already
  stores 154 datasheet PDFs as `Attachment` rows, so the only new gain is reading *inside*
  the PDFs, and `pyproject.toml` declares no PDF library at all.
- **TABLER** has never been probed (§5.4). Now tracked with the rest of the unprobed
  queue in `docs/CANDIDATE-SOURCES.md`, whose row also records that its URL was never
  written down anywhere.

### DEC-6 · Authenticated capture for prices an anonymous crawl can never reach
Decided in principle, unbuilt: ALSWEED's variant prices (`offers.price=0` in JSON-LD),
sikaegshop's trade tier for `customerTypeId 2`, MADAR's business-segment prices and
per-branch availability. All three need an extension session capture, not a connector
change. `sources.yaml:131`, `:112`, memory `sika-trade-tier-price.md`.

### DEC-7 · Branch cleanup, which the owner asked to be reminded of
**RE-MEASURED 2026-08-20, with the right test this time: 172 local, 125 remote.**

Run over all 172 local refs with `git merge-tree --write-tree origin/main <branch>`
compared against `git rev-parse origin/main^{tree}` — the test this entry itself
prescribes, on `main` at `72f93a8` (#218):

| | |
|---|---|
| fully contained in `main` — merging changes **nothing** | **60** |
| merging would **conflict** | **110** |
| merges cleanly and **adds** something | **2** |

The shape has held across three measurements over eleven days: 47/68/1, then this.
Local grew 148 → 172 while remote SHRANK 128 → 125, so someone is deleting remote
branches and nothing is deleting local ones.

**And both members of the `adds` bucket are instructive rather than a backlog.**

- `docs/branch-protection-is-its-own-session` — in flight; this entry's own commit.
- `feat/the-warehouse-travels-through-drive` — **THE TRAP, and it must not be
  merged.** It reads as "adds something" because its content is genuinely absent
  from `main`. But its commit *did* land, as `8ebb1f5` (#123), and
  `scrapex/drive.py` was then **deliberately deleted** by `59d5910` (#164), "Drive
  moves into the panel, and the engine stops holding a token it never needed".
  Verified: `git cat-file -e origin/main:scrapex/drive.py` fails. Merging it
  resurrects a module the owner had removed on purpose.

  **So `adds` is not a synonym for `wanted`.** The bucket test answers *would
  merging change main*, never *should it*. Any branch whose files `main` later
  deleted lands in `adds` for ever, and this is the second time this entry has
  had to warn about a bucket being read as an instruction.

**A branch rots between measurements, which is the case for acting rather than
re-measuring.** `claude/jolly-borg-a826ba` — the one branch the 2026-08-20 morning
inventory found holding live work that merged **cleanly** — is now in the
**conflict** bucket. #217 and #218 moved `extension/app.css`, `extension/console.css`
and the three parallel `tokens.css` / `appearance.js` copies, which is exactly the
surface it touches. It was mergeable in the morning and is not by the afternoon,
and nothing about the branch changed.

**Previous measurement, 2026-08-12: 148 local branches, 128 remote.** It has GROWN by 31
local and 22 remote in three days — every session that opens a branch adds one,
and nothing removes any. The 2026-08-09 figures (117 / 106) are kept below with
the analysis that was done against them, because the *method* is the valuable
part and it does not need re-running to stay true.

Three `.codex` worktrees now, not two: `git worktree remove` still comes first.

**Previous measurement, 2026-08-09: 117 local, 106 remote, 21 worktrees.**

And the measurement below was made the wrong way, which matters more than the count.
`git branch --merged` reports 11, and it is **meaningless here**: this repository
squash-merges, so a squash-merged branch reads as unmerged for ever. `git diff
origin/main...branch` is no better — for a diff, three dots means *merge-base to
branch*, which answers "what did this branch add when it forked", not "is it in main
now". It reported 105 branches holding work. That number is wrong.

**The test that actually settles it is `git merge-tree --write-tree origin/main
<branch>`: if the tree it writes equals main's tree, merging that branch changes
nothing.** Run over all 117:

| | |
|---|---|
| fully contained in main — merging changes **nothing** | **47** |
| merging would **conflict** | 68 |
| merges cleanly and **adds** something | **1** *(and it is the branch open in PR #141)* |

Of the 68 conflicting, **31 carry a subject line that is already on `main`**, so they
are squash-merged and their conflict is just main having moved on. The remaining 37
are the only ones that need a human to look, and several of those are review scaffolding
(`review-6x`, `refute-6x`, `t64`, `t65`, `merge43`, `ranktest`) rather than work.

The 2026-07-28 note listed three stale branches. It read: `codex/selected-card-layout`,
`codex/source-card-display-review` and `codex/unified-record-inspector-scroll` each carry the
same four unmerged commits (`dd786b9`, `9e4c1c4`, `d25b166`, `465bfd2`) whose *titles* are
already on `main` under different hashes — so they are almost certainly superseded rather
than missing **(inferred from the titles; the check is a diff, not a title match)**.
`codex/workspace-overview-ui` still holds the one genuine orphan `c88961a`, already ruled
**superseded, do not merge**. Two branches live in `~/.codex/worktrees/`, so
`git worktree remove` comes before any deletion.

### DEC-12 · The append gate's key is not the number, and three of his briefs prove it separately

**FOUND 2026-08-20**, not from the code but from reading three price briefs he sent
within an hour of each other. Each describes a different product, each was written
independently, and **each breaks `SR-6` in a different place.** One case would be a
quirk; three from three directions is a defect in the key.

`SR-6` is right about what it was written for: a scraped shelf price where an
unchanged number carries no new information, so the observation is **confirmed rather
than appended**. That is what `_still_the_same_price` implements, and it is why the
warehouse is not full of identical rows.

**It is wrong about what "the same" means for an official published price.**

| the brief | what carries the new fact | what `SR-6` sees |
|---|---|---|
| [DIESEL-PRICES.md](DIESEL-PRICES.md) §3 — *"never overwrite a previous price when a new month or quarter begins"* | **the period.** Oman published `0.258 OMR/litre` for August. If July was also `0.258`, the ministry setting it again for a named month **is** the fact | no change → writes nothing → **the August period never exists** |
| [BITUMEN-PRICES.md](BITUMEN-PRICES.md) | **the commercial basis.** Two observations can be ex-refinery and delivered, taxed and untaxed, 25-tonne truck and sea — different facts at equal values | no change → collapses them → destroys the only thing that made either usable |
| [CONCRETE-MATERIALS.md](CONCRETE-MATERIALS.md) §3 | **the source type.** Its table has a column headed *"Can it populate `price_amount`?"* and the answer is **No** for `official_price_index`, `official_approved_source` and `official_specification`. An index point and an absolute price are not comparable quantities | no change → treats an index value and a price as the same observation |

> **So the key is not `(product, price)`. It is at least
> `(product identity, period, commercial basis, source type)`** — and the concrete
> brief goes further than a key: an index must not enter the price column **at all**,
> which is a schema boundary rather than a gate condition. It gives
> `price_index_observations` and `water_tariffs` their own tables for exactly that
> reason.

#### Why this is recorded now, before any of it is collected

Because the failure is **silent and unrecoverable**. A dropped month is not a wrong
row that a later fix corrects — it is a row that never existed, in a table whose whole
purpose is history. By the time anyone notices August is missing, August is not
re-fetchable: these are dated bulletins and expiring quotations, and the Qatar bitumen
figure had **already expired** when he sent it.

**And this shape has already happened here once.** A new `price_observation` column
stayed NULL because the append gate never learned to notice it — the gate decides what
history exists, and it only ever knew about the price. That is the same defect at a
smaller scale, and it is the reason to believe this one.

#### Water is the sharpest single example, and it is his

The concrete brief §2.2 refuses to store one water price at all. The official network
tariff is **one component** of the site cost, beside meter charges, wastewater
charges, tanker filling, transport, storage and testing — and *"a potable-water tariff
alone does not prove technical suitability"* for concrete mixing. **One number here
would be false in both directions**: too low as a delivered cost, and not evidence of
fitness for purpose. So the tariff and the delivered quotation are two tables, which
is the same argument as the three rows above with the volume turned up.

#### What this does NOT say

It does not say `SR-6` should be removed. `SR-6` earned itself on the price sources
this project already runs, and removing it would fill the warehouse with identical
rows. **It says the gate needs to be told what "new" means per product class**, and
that the three product classes he has now queued each answer differently.

**Not built, and deliberately not designed here.** The evidence is recorded while it
is fresh; the mechanism is a decision for when the first of these collections is
actually scheduled, and it will need his ruling because it changes what `SR-6` means.

---

### DEC-11 · How to crawl muqawil without missing anyone, and what it costs

**STUDIED 2026-08-20 on his instruction** — «ازاى نزحف صح بدون ان نغفل شى» and «اريد
منك فحص كل الحلول والحالات» — because the warehouse had told him a real company did
not exist. Fifteen agents over five angles, each proposed method then attacked to find
the contractor it misses.

#### First, four numbers in this repository are wrong, including one of mine

| stated | measured 2026-08-20 |
|---|---|
| 865 listing pages | **871** |
| ~17,300 / "at least 17,283" contractors | **17,402** = `(L−1)×20 + c`, where the last page now carries **2** cards, not 15 |
| a 2026-08-17 pass ran at 5.4 requests/second *(mine, in conversation)* | **FALSE.** `captured_at` is the INSERT time, not the fetch time. The "160 seconds" was a database copy. The real rate is **5.84 s PER REQUEST** — 34× slower |
| 121,157 detail requests | superseded, and still written down |

**So speed IS a problem, contrary to what I told him.** The correction matters because
every cost below is priced at 5.84 s and would be nonsense at 5.4/s.

#### The mechanism, and it is the whole answer

The listing order is **not** randomised per request. It is a randomised ordering held
in a cache whose generation lasts **more than 66 s and at most 268 s**. Measured.

- **Inside one generation, pagination is an exact partition** — pages disjoint,
  together covering every published row once.
- **Across generations it is independent resampling**, which is why 864 pages read
  over hours yielded 11,059 of 17,275 slots and why six passes never converged.

> **Therefore any page set read entirely inside one generation is provably complete
> for that set.** That sentence is the difference between hoping and knowing.

#### The method: partition, then witness the partition

| step | what it does | cost |
|---|---|---|
| **0 · ceiling** | page 1 → `L` and cards-per-page `S`; page `L` → `c`; `N = (L−1)·S + c`. **`S` is READ, never assumed** — he warned it may change, and it did change on the last page | **2 requests, ~12 s** — replaces an 8h54m six-pass sweep |
| **1 · partition** | slices small enough to read inside one generation. **`region_id` × `company_size`, 56 cells, exhaustive and verified to the unit** — see the measurement below. Slice sizes are read from each cell's own paginator, never assumed | 1 request a cell |
| **2 · witness** | after reading a slice, **re-fetch its page 1 and compare THE ID SEQUENCE** — never the bytes; see the correction below. Same sequence ⇒ the generation never rolled ⇒ the pages were one true partition ⇒ if `distinct == N_s` the slice is **provably complete**. Different ⇒ the ids still count, and the slice retries | `L_s + 1` |
| **3 · exhaustiveness audit** | `Σ N_s == N_total`? If short, **the deficit is exactly the count of contractors whose facet value is null** — the "contractor in no partition" case, detected and counted instead of silently dropped | 2 per slice |
| **4 · global deficit** | `D = N − |distinct|`. `D > 0` **proves** incompleteness and names its size; `D == 0` proves every published row position was read. Re-read `L` at the end: if it moved, say "complete as of the start, with N arrivals deferred" | free |

**Cost: ~1,670 requests ≈ 2.7 h serial, ~58 min at concurrency 4** — against **18.4 h**
for a blind 13-pass sweep that can still only ever say *"expected unseen 0.04"*. Seven
times cheaper **and provable instead of probabilistic**.

**Concurrency buys wall-clock, not coverage.** Closing an 871-page pass inside a 66 s
generation would need ~34 in flight, and `pacegovernor.py` already measured the price
of four (latency 6.6 s → 9.2 s, *"a server saying it is hurting"*). Coverage comes from
slice size, not from parallelism.

#### What this method still cannot see, and it is the most important paragraph here

It proves it read every row the paginated listing **publishes**. It cannot prove the
listing publishes every contractor the site knows:

> **The site's own header counts 123,842 "Saudi Contractor" against 17,402 published
> rows — a factor of 7.1.**

So the only honest warehouse claim is *"every contractor findable in the muqawil.org
contractor listing as of «timestamp»"*, never *"every Saudi contractor"*. And
membership **10001274** is therefore **explained but not closed**: `q` reaches it
(tested — it returned exactly id 1301), and whether it appears in the unfiltered
listing is unknown until one crawl closes with `D == 0`.

#### The blind fallback, priced honestly

Expected unseen after `k` passes = `N·e^(−k)`, and the model is validated: it predicted
42.9 unseen after 6 passes; the sweep observed 38. `k=10` for expected unseen below 1,
`k=13` for 95% confidence of missing nobody, `k=15` for 99%. Reserve it for the
residual, never as the primary method — it cannot say "complete".

#### And one cost correction that changes the plan

`sites/muqawil.py:118` computes `listing_requests = last_page × len(locales)`. Correct
about requests, **but it must not be read as coverage**: Arabic page N returns the SAME
20 ids as English page N — 20 of 20 identical on 845 of 864 stored pages. The Arabic
half buys **129 new ids for 865 requests**. Count passes in ONE locale for completeness
planning and treat Arabic as a data-pairing cost, not a coverage cost.

#### The partition, measured 2026-08-20 — and it is exhaustive to the unit

**MEASURED, 152 requests** — 43 sizing the regions, 61 the region×size cells, 13 the
cities endpoint, 10 probing whether a null facet is addressable, 10 sizing
`region_id=0`, 14 witnessing, 1 diagnosing.

The three unknowns this study left open were the ones the method stood on. Two are now
closed and the third is closed as a defect.

**The page count never needed a sweep.** The paginator publishes its own last page:

```html
<li class="page-item"><a href="…?region_id=1&amp;page=322">»</a></li>
```

So **one request sizes any slice**, filtered or not. `read_last_page` already did this
and nobody had noticed it answers the filtered case too.

**Every filter the listing offers, because a `<select>`-only search had missed most of
them.** This study previously recorded that `company_size`, `rating_stars` and
`user_type` "have no `<select>` in the listing at all". True, and misleading: **they are
radio inputs**, and their values were in the page the whole time.

| parameter | values | exhaustive? |
|---|---|---|
| `region_id` | `1`…`13`, **and `0`** | **yes, with `0`** — see below |
| `city_id` | 3,953 ids, AJAX only | no — same null class as region |
| `company_size` | `big` `medium` `small` `verysmall` | **yes** |
| `user_type` | `SC` `NSC` | **yes** (783 + 88 = 871 pages, the whole listing) |
| `rating_stars` | `1`…`5` | no — **17 contractors in total** carry any rating |
| `lc_program_list_id` | 13 programme ids | no |
| `interest_id` | `jstree`, hierarchical | no, and multi-valued |
| `q` | free text | **matches the membership number exactly** |
| `my_contractors` | `1` `2` | no — a logged-in user's own list |

**`city_id` comes from an endpoint, and it was in the stored HTML all along**, in the
listing's own jQuery rather than in any `<option>` — which is exactly why a search of
the `<select>` found an empty one:

```js
var citiesUrl = "https://muqawil.org/en/contractors/cities";
```

`GET /{lang}/contractors/cities?region_id=<n>` → `[{"id":…,"name":…}, …]`. Thirteen
requests give **3,953 cities**. `city_id` also works **without** `region_id`
(`?city_id=3` alone → 296 pages, which is RIYADH — the warehouse projects 5,896 for
that city and the paginator says 5,920).

**`region_id=0` is the whole answer to the exhaustiveness question.** `Σ N_r` over
regions 1–13 came to **15,966** against a whole of **17,403** — 1,437 short, the
contractors whose card publishes no location at all. `region_id=0` (and
`region_id=null`) returns **exactly those 1,437**, every card blank:

| | |
|---|---|
| Σ regions 1…13 | **15,966** |
| `region_id=0` | **1,437** — and its own four `company_size` cells sum to 1,437 |
| whole listing | **17,403** = 15,966 + 1,437, exact |

Corroborated independently: 960 of the 11,059 stored records (**8.7%**) have a null
`card_city_region`, and 1,437 of 17,403 is **8.3%**. Two measurements, different
instruments, same class of contractor. **This is the "contractor in no partition" case
the study warned about, and it turns out to have a URL.**

`company_size` is a second exhaustive axis: its four values sum to **17,405** against
17,403 — a drift of two arrivals in the minutes between the two measurements — and
`card_company_size` is filled for **all 11,059** stored records with no empties, ratios
matching the live page counts to a tenth of a percent (76.6 / 14.4 / 6.1 / 3.1).

**So the partition is `region_id` × `company_size` — 56 cells, exhaustive, exact.**

| | |
|---|---|
| cells | **56** |
| Σ pages over cells | **897** against 871 unfiltered — **3% overhead**, the per-cell rounding |
| cells over 31 pages | **6**: Riyadh×verysmall 235, Makkah×verysmall 156, Eastern×verysmall 93, no-region×verysmall 59, Riyadh×small 51, Madinah×verysmall 32 |
| those 6, split again by `city_id` | **405 of 410** city×size cells fall under 31 pages. The five that do not: RIYADH×verysmall ~212, JEDDAH×verysmall ~92, RIYADH×small ~48, MAKKAH×verysmall ~39, DAMMAM×verysmall ~32 |

**Re-priced: ~1,065 requests, ~1.7 h serial** (56 to size + 897 to read + 56 to
witness + 56 tail counts) against this study's earlier estimate of 1,670 and 2.7 h, and
against **18.4 h** for the blind sweep. And it is now provable rather than hoped-for,
because the partition is exhaustive rather than assumed to be.

#### Two corrections the measurement forced, and one would have broken everything

**1 · The witness must compare the ID SEQUENCE, not the bytes.** Step 2 said
"byte-identical". Measured: a re-fetched page 1 whose id order was **identical** was
**not** byte-identical — the body carries per-response noise. A byte comparison would
have failed every witness, so the method would have certified **nothing**, ever, while
looking like it was working.

**2 · A filtered listing hid its page count behind an entity, and that is a defect in
this repository rather than a quirk of the site.** `read_last_page` matched
`[?&]page=(\d+)`. Unfiltered, the paginator writes `?page=2` and it matched. Filtered,
it writes `&amp;page=322`, where the character before `page=` is a **semicolon** — so
nothing matched, the function raised, and a caller that guarded the raise read Riyadh's
**322 pages as one page of twenty**. It is fixed, read only from inside an `href`
(unescaping alone would let prose containing `page=` count as pagination), and both
halves are mutation-proven.

#### Proven once, end to end

`region_id=13` × `company_size=verysmall`, 7 pages: **128 ids read, 128 distinct**, and
the witness page 1 came back in the same order. `D = 0`. **That slice is complete, and
the claim is a proof rather than a hope** — the first time anything in this project has
been able to say that about muqawil.

And the generation lasts longer than the study assumed. Page 1 of a filtered slice held
its exact order at **55 s, 90 s and 157 s**, and had rolled by **282 s** (10 of 20 ids
in common). So the working floor is **157 s**, not 66 s — which is what makes 31-page
cells comfortable and the six heavy cells worth attempting at all.

#### Unknowns that remain

1. **Is 10001274 in the unfiltered listing?** Still unknown until a crawl closes with
   `D = 0`. But it is now **reachable on demand**: `?q=10001274` returns exactly one
   card. That is the reconciliation primitive `dataset_sighting` needed — one request
   per missing id, not a re-crawl.
2. **The five city×size cells over 31 pages**, worst RIYADH×verysmall at ~212. No
   fourth exhaustive axis is fine enough — `user_type` only halves it to ~190. The
   witness makes attempting them **safe rather than risky**, since a failed witness
   still contributes its ids and retries, so this is a cost question and not a
   correctness one.
3. **Whether `q` can cover the residue.** `q=zzz` → 0 results and `q=a` → 856 pages, so
   it is a substring match and a cover built from it would overlap. Unmeasured whether
   every published name contains an ASCII letter.

#### Dead ends, so nobody spends the requests twice

Recorded because a negative result stated firmly is worth as much as a positive one,
and each of these looked promising enough to chase:

- **The sitemap does not enumerate contractors.** `/sitemap.xml` → `/ar/sitemap.xml` →
  a sitemapindex of `sitemap-ar.xml` and `sitemap-en.xml`, and the English one holds
  **20 static pages**. Settled; do not re-check.
- **`/en/contractors/map` carries no contractor markers.** The page is 406 KB and
  holds 263 distinct latitude-shaped numbers, which is what made it look like a feed.
  It is not: the one coordinate in the map's own script is the map CENTRE — Riyadh,
  `{lat: 24.70372261387751, lng: 46.683}` — sitting under a comment copied straight
  from a Google Maps tutorial, `// The location of Uluru`. **Zero contractor profile
  links on the page.** Its only endpoints are `/api/js` (Google Maps) and
  `/api/rating-api` (the rating widget). So the map gives neither an enumeration nor
  the coordinates the owner asked for — `latitude`/`longitude` remain a profile-page
  field, exactly as `CONTRACTOR-SOURCE.md` already marks them (`js`, inline script
  only).
- **No stable sort exists.** `sort`, `order`, `order_by`, `orderby`, `sort_by`,
  `direction` and `sort_field` were each tried against the live listing and **not one
  changed the order** — measured before this study, and recorded in
  `scrapex/sweep.py`'s header. There is nothing to build.
- **Id-space enumeration is not viable.** Contractor ids span 720 … 20,217,024 in two
  series the site publishes, far too sparse to probe.

---

### DEC-9 · Snapshots are stored uncompressed, and the full crawl is 6.4 GB of it

> **SUPERSEDED 2026-08-20 by [STORAGE.md](STORAGE.md), and kept in full per C4.**
> It asked *how to store 6.4 GB more cheaply* and answered that well. The owner
> asked *why we are storing 6.4 GB at all*, and five of the numbers below do not
> survive being measured properly: a listing page is **17.8%** cards, not 21%; a
> profile is **119 KB** across 13 samples, not 168 KB from one; the corpus is
> **4.55 GB**, not 6.4; a profile compresses **7.7×** with zlib, not 9.4×; and the
> compressed projection is **~90 MB**, not 660.
>
> The one that mattered is not a number but a cause: its 15.6× is **entirely
> intra-page**. zlib's 32 KB window never sees across a 121 KB page, so the
> cross-page redundancy this entry credits for the ratio was left on the table.
> `zstd` with one real page as a raw dictionary gets **187×** on listings and
> **46×** on profiles — **254×** re-measured through the `zstandard` wheel,
> which is what shipped — and keeps every row independently decompressible. Its *rule* — keep the snapshots — is upheld and
> strengthened. Its *encoding* is not.

**MEASURED 2026-08-20, on the live database.** The contractors cost 342 MB, of which
**320 MB is HTML and 22 MB is data** — 94% of the price is the pages, not the rows.

| | |
|---|---|
| the file on disk | 483 MB *(now 835 MB, with the Arabic half merged)* |
| 864 snapshots | 320 MB, averaging **362 KB a page** |
| 11,059 records | 8.7 MB |
| 17,275 revisions | 13.6 MB |

**Only 21% of a listing page is its contractor cards.** The other 291 KB is nav,
footer, scripts and the city dropdown — a near-identical skeleton repeated 864
times, which is exactly why it compresses so well:

| | | |
|---|---|---|
| 25 pages raw | 9.3 MB | |
| gzip level 6 | 0.6 MB | **15.1x** |
| zlib level 9 | 0.6 MB | **15.6x** |
| lzma | 0.5 MB | 19.1x |

**320 MB would be 21 MB.** And the projection that makes it a decision — one real
profile page was fetched and measured at **168 KB raw, 18 KB compressed (9.4x)**:

| Stage B, 17,402 contractors x 2 languages = 34,804 pages | |
|---|---|
| raw | **~6.4 GB** |
| compressed | **~660 MB** |

**The recommendation is that the rule is right and the encoding is wrong.** "One page
in, one snapshot out" earned itself on 2026-08-20: a defect in the bilingual merge was
repaired from disk with **nothing re-fetched**, where a re-crawl is 2.8 hours — and
[DEC-11](#dec-11--how-to-crawl-muqawil-without-missing-anyone-and-what-it-costs) prices
a *provable* one at 2.7 hours serial or 58 minutes at concurrency 4. So the
snapshots stay. They should be stored compressed — `zlib` is in the standard library
and needs no new dependency.

What was considered and is worse:
- **Trimming to the cards (21%)** saves 4.8x where compression saves 15.6x — three
  times worse, and it spends the ability to re-parse. The defect repaired that day was
  *inside* the card; the next one may not be.
- **Deleting snapshots after approval** spends exactly what saved the day.
- **Keeping a hash and re-fetching on demand** cannot work: the listing reorders every
  thirty seconds, so a page is not reproducible. What is not kept now is not gettable
  later.
- **A shared-dictionary compressor (trained zstd)** would beat 15.6x, since the
  skeleton repeats 864 times — but it adds a dependency for a margin we do not need.

**The cost, and why it is the owner's call:** `html_content` becomes a BLOB rather than
TEXT. That is a migration plus every reader of the column.

### DEC-10 · "Fix the parser and re-run over the snapshots" does not actually work

> **RULED 2026-08-21 — [R-40](RULINGS.md#r-40--dec-10-is-built-before-the-profile-crawl-not-after-it):
> built BEFORE the profile crawl.** On 34,834 profile pages a parser defect found
> afterwards costs 11 hours of re-fetching to fix what should be minutes of
> re-parsing, which is a direct contradiction of why the seam exists. Kept here
> rather than deleted, because the measurement below is what produced the ruling.
The seam's stated product is that a wrong parse is re-run against stored snapshots with
nothing re-fetched (`GENERIC-FETCH-SEAM.md`). **It was tried on 2026-08-20 and wrote
nothing at all.**

`approve_candidate` short-circuits on `_approved_ingestion(conn, snapshot_id,
locator)` — same site, same dataset, same `schema_hash` means "already approved", and
it returns `recovered=True` without touching a row. A **corrected parser produces the
same schema and different values**, so all 864 pages came back recovered and the four
empty columns stayed empty. Worse, the caller cannot tell: the return value looks like
success, and the script that drove it reported 864 re-approvals that were 864 no-ops.

The repair only landed because the ARABIC snapshots were merged in the same pass —
a genuinely new `(snapshot, locator)` pair, so a genuinely new approval.

**The gap is that the idempotency key does not include the ROWS.** A candidate hash
alongside `schema_hash` would make a corrected parse a different request — replay of an
identical request still short-circuits, so the tested behaviour is kept — and the
re-ingestion would write revisions, which is what a repair should leave behind. Not
built, because it changes the approval path's atomicity guarantee and that is a ruling.

Until it is built, **re-parsing means approving against a snapshot that has never been
approved**, and that has to be said out loud rather than discovered again.

---

### DEC-8 · The engine's Data page is a PORT, not a rebuild — measured 2026-08-16

**This answers [REQ-07](REQUESTS.md#req-07--the-data-page-must-carry-everything-the-engines-page-carries)**
— his request on the board, which did not cite it in either direction.

**The owner asked directly:** «هل يمكن نقل صفحة data الموجودة فى المحرك بكل مميزتها الى
extension ام يلزم اعادة البناء كامل؟» Answered by measurement, not opinion, and the answer
is a port.

**Why it is a port.** Both pages already run the SAME grid library:

| | |
|---|---|
| `scrapex/webui/static/grid.js` | **3,212 lines**, Tabulator |
| `extension/datatable.js` | **100 lines**, Tabulator |

Tabulator was vendored into the extension in #193, so the difference is not a technology —
it is **~3,100 lines of behaviour written on top of the library we already ship in both
places**. `grid.js:5-9` records why that behaviour is ours rather than bought: the owner
asked for the AG Grid look, and the features in those screenshots — set filter, row
grouping with aggregation, the columns tool panel, Excel export — live in
`ag-grid-enterprise`, whose licence field reads *"Commercial"*. So it was built on the MIT
library instead. **Code we own ports; a licence would not have.**

**And MV3 does not block it.** `eval(`, `new Function` and inline `on*=` handlers in
`grid.js`: **zero**. Those are precisely the three things Manifest V3's CSP forbids, and one
of them would have made a port impossible without a rewrite. There is none.

**Where the real work is, and it is not the grid.** `scrapex/webui/templates/source.html`
carries Jinja on **105 of its lines**, and those lines hold **118 expressions** — 61
`{{ }}` substitutions and 57 `{% %}` control statements, counted 2026-08-20. (The
first version of this entry said "105 Jinja expressions": 105 is the LINE count, and
naming it as expressions understated the work by thirteen.) Half the page is assembled
on the server before it reaches a browser. An extension page is a static file, so
every one of those has to become a request and a render in JS. Mechanical, not inventive. The routes it needs already exist
and already answer: `/api/fields`, `/api/promotable`, `/api/views`, `/api/offer` — and the
extension already calls `/api/table` among them.

**What the gap actually is, with evidence.** The owner sent two screenshots on 2026-08-16.
The engine's page carries Datasets · Views · Grid Features · Columns menus, a filter and a
menu on every column, an ALL/ONE toggle, an **EN/AR toggle**, Excel/CSV/JSON export, a
price rendered with its previous value struck through, row checkboxes, Source overview, and
a last-run line with a Crawl history link. The migrated page carries side-by-side AR and EN
columns, a fold checkbox, Reload, and basic pagination. **The migration carried the word
`bilingual` (`extension/datatable.js:55`) and left the feature** — which is why the owner
stopped at B1: «اشياء كثيرة مفقودة لذلك توقفت عند b1».

**Three pieces of work, in order:**

1. **Port `grid.js`.** The largest piece and close to a copy.
2. **Convert the 118 Jinja expressions** across those 105 lines from server-side
   rendering to fetch-and-draw.
3. **A DOM harness that renders the page in tests** — `tools/tabpage_harness.py` was built
   for exactly this in #194 and extended to serve real ES modules in #200.

**(3) is the one not to trade away.** The Data page has already shipped BROKEN once with
2,460 engine and 398 extension tests green on it (#194: every first load aborted itself,
found only by opening it in a browser). Three thousand ported lines with nothing rendering
them is that failure with more surface.

**And a standing warning:** do not delete the engine's page until the harness proves the
ported one works. *"We migrated it"* has been said once already about a page that was
missing everything in the list above.

## 4. Built, not yet verified

### BV-1 · Crawling several sites at once — IT HAS RUN, and the entry was wrong twice
**Re-measured 2026-08-12 against the live warehouse and the job log.**

Both facts this entry rested on are stale:

- **Not off by default on his machine.** `scrapex_meta` holds
  `setting:crawl_parallel_sources = '3'`. The entry says 1.
- **It has run at width 3, at least twice.** `job_log_entry`, job 120:
  *"2026-08-11T13:12:59Z crawling 12 site(s), up to 3 at a time"*, then MADAR
  13:13:50, ALSWEED 13:13:52, ELBUROJ 13:13:59 all *"fetching — 50 requests so
  far"*, interleaving for minutes. Again at job 112 on 2026-08-05.

**And this entry's own proposed check was wrong and would have misled whoever ran
it.** *"Confirm from `crawl_job` that they overlap"* — `crawl_run` brackets the
**ingest**, not the fetch: run 134 records 3,879 requests between 14:50:00Z and
14:50:02Z. A self-join over all 135 runs finds **zero** overlapping pairs at width
3. Use `job_log_entry` timestamps, not `crawl_run` intervals.

**What is actually unverified is the other half of the sentence — the pause.**
The pause handler clears `crawl_job.control` while other lanes are still in
flight (`scrapex/jobs.py:723-724`, and the twin at `:595`).
**Next action:** stop the pause handler clearing `control` until every lane has
observed it, or have the other lanes read their own copy.

### BV-2 · The WAL / sealed-archive cluster
`234cdc1`, `4103e48`, `4dfb9e8` (plus the integration PR #10). Three of the four faults are
POSIX-only — on Windows an open handle blocks the rename, which is the accident that hid
them. The author is explicit for fault D: *"I could not make D's test fail on this machine,
and did not pretend to. Local SQLite is 3.50.4, where optimize behaves; CI's 3.45 is where
the fault bites."*
**The check that would settle it:** a green CI run on `ubuntu-24.04` for those tests. Look
at the run, don't assume it.

### BV-3 · Settings moved into the extension panel — CONFIRMED, and its warning has come true
**Re-measured 2026-08-12. The "not yet confirmed" half is CLOSED by the live
warehouse**, which shows the whole chain working on the owner's machine in a real
crawl: `extension/app.js:848` posts `crawl_honour_delay` → `scrapex/capture.py:95`
reads it → `scrapex/connectors/base.py:560` emits the sentence → `job_log_entry`
for job 120 carries it. Two settings hold non-default values, so something wrote
them: `crawl_honour_delay = '0'`, `crawl_min_interval_s = '1'`.

**THE WARNING IN THIS ENTRY HAS NOW MATERIALISED, and this is the most
consequential thing in this file.** The log line predicted it:

> *"ELBUROJ: robots.txt asks for a 10s crawl delay — IGNORED at your request;
> this run paces itself at 1.0s and may be rate-limited or blocked by the site"*

And then, five times: `failed: 5 refusals in a row (last: HTTP 429 on
https://alsweed.sa/...)` — 2026-08-11 at 13:30:07Z, 13:39:32Z and after. **A
whole source is failing because the delay is switched off.**

**Next action, and it is the owner's:** `crawl_honour_delay` is still `'0'`. He
chose that (SR-9 says turning it off announces the number it overrides, and it
did). He may not know it has cost him ALSWEED. Show him the 429s.

### BV-4 · Sika's trade tier reaching the warehouse
`436105c` reported 0 of 73,084 observations carrying a trade price. **Re-measured
2026-08-12: 185** observations carry `price_trade` (was recorded as 78). The fix
works and keeps working. ~~`price_trade` reaches `BROWSE_COLUMNS` with no
formatter and no alignment~~ — `059820d` closed that; the clause is struck rather
than deleted so it is not re-raised from the old text.
**The check that would settle it:** open a sikaegshop record in the Data page and look at
the Trade price cell.

### BV-5 · Sources re-activated, then partly switched off
`df34761` activated four connectors that had been built and left off. ~~The
uncommitted manifest edit has since switched five sources off~~ — **re-measured
2026-08-12: that edit is long gone**, the four held, and the manifest and the
warehouse agree exactly (see **OP-2**). Twelve sources, seven active.

What is left is only the last sentence, and it is the owner's: **is seven of
twelve the intended set?** That is **Q-11**. Worth putting in front of him
together with **BV-3** — one of the seven, ALSWEED, is currently being refused
with HTTP 429.

---

## 5. Declared debt — deferred on purpose, with the reason

| ID | Debt | Why it was acceptable |
|---|---|---|
| **DEBT-1** | **Migration `0047`'s coverage guard runs *after* the MADAR upgrade that fills its NULLs**, so it checks a narrower condition than its comment claims. | `0047`'s sha256 is verified on every connection and there is no re-stamp path; replaying it over the real pre-0047 warehouse gives an identical result with or without the fix. Recorded as a **strict xfail** at `tests/test_db.py:194` — this is the "1 xfailed" in every suite line, and it should stay visible. (`c7fa4ea`) |
| **DEBT-2** | **ETag / Last-Modified persistence across runs.** In-memory validators exist in `HttpFetcher`; they are not persisted. | Naive 304-skipping breaks price *confirmations* (`last_confirmed_at`) and the volume canary. It needs a content-cache design, not a flag. Owner approved the deferral 2026-07-22. |
| **DEBT-3** | **`_derive_seen` rebuilds the whole derived timeline of every offer a run touched, unconditionally** (`scrapex/ingest.py:1349-1363` — cited as `:1029-1043` until 2026-08-12). | Gating it on success *was* the incident: one contained error left every offer with an appended observation but no `offer_state` and no `price_period`, and the same-day dedupe then blocked the re-append that would have repaired it. The cost is accepted; ت3's claim that it is ~396,000 operations was never refuted (**OP-6** — and OP-6's row for ت3 pointed at DEBT-4 by mistake; it means this entry). |
| **DEBT-4** | **advancedcastle's Egyptian price is deliberately not crawled.** *(Discharged as intended — re-measured 2026-08-12: the 14 ADVANCEDCASTLE rate rows are there and no converted price is.)* | It is a *conversion*, not a price the merchant set — the EGP/SAR ratio is constant at 11.768 across five probed products. `price_basis` / `original_price` live on `COMMODITY_PRICE`, not `PRODUCT_PRICES`, so recording it honestly is a schema migration and therefore the owner's call. He took it: capture the published **rate**, never the converted price. Note the warehouse *would* keep the two countries apart correctly (`source_offer` is keyed on `country_code_alpha2`) — the reason is the derivation, not a modelling limit. (`e639310`, `b43405c`) |
| **DEBT-5** | **`region` keeps its name in three places on purpose** — the manifest's `default_region` / `extract.regions`, `tax_rule.region`, and `pricekey`'s own field. | They *scope* a row rather than describe it. The column itself did move (`0042`). |
| **DEBT-6** | **`origin` and `spec` are hashed into the price key but no connector supplies them** (`scrapex/ingest.py:898-902` — cited as `:597-599` until 2026-08-12 — its own comment: "Not collected by any connector yet"). | Wired and unreachable. Harmless today; it matters the day a connector starts publishing one, because the field set changing is `fields_changed`, not `price_change`. |
| **DEBT-7** | **Named in the UI as not built:** ~~funnel HMAC signing, adaptive batching,~~ two-way Sheet sync, proxy / anti-bot, connector-drift repair, OTA updater. **Re-measured 2026-08-12: funnel HMAC signing and adaptive batching are BUILT and shipping** — four items remain, not six, and the interface should stop naming two things it has. | Post-release, demand-driven. Saying so in the interface is what keeps it honest. (memory `scrapex-phase5-integrations.md`) |
| **DEBT-8** | **GPP electricity stays on the rank table as converted USD.** | Electricity country pages are a different page type and the site's own JSON-LD there is broken (`EGP 0.000`). It needs its own parser; the rows are honestly marked `price_basis=converted`. Measured: 333 of GPP's 695 offers are still priced in USD. |

---

## 6. Open questions for the owner

Each is phrased as a question with its options. Nothing below can be answered by code.

**~~Q-17~~ · RULED 2026-08-22 — see [R-45](RULINGS.md#r-45--the-site-is-the-only-source-of-truth-and-a-field-the-table-does-not-need-goes-in-the-rows-card).**
He refused both options this question offered. **We never translate** — where the site
publishes no usable English, the node keeps its Arabic identity and no English name.
And the readiness level is **neither a column nor discarded**: fixed columns in the
table, everything else in the **row's own card**, because contractors will have several
sources and a column is a promise every source must keep. The question is kept below,
unedited, because the answer is only legible beside what was asked (**C4**).

### Q-27 · `/api/health` says the databases are `ok` while it also lists two migrations pending

**Asked 2026-08-27 · measured on his live engine, both before and after the `0.4.2` restart**

The same response carries both:

```
"databases": {"ok": true, ...}
"schema_lag": {"pending": ["0002_contract_meta.sql", ...],
               "message": "2 migration(s) on disk are not applied to this database"}
```

`ok` comes from `EngineDatabase.health`, which compares `PRAGMA user_version` against the
`db/engine/migrations` ceiling — and that agrees now (both 13). `schema_lag` is reading a
**second stream**, the one whose names are `0002_contract_meta.sql`, `0010_view_region.sql`,
`0013_marketlens_database_identity.sql`. The two streams share numbers, which is also what
made a `LIKE '0013%'` check report a migration as applied when it was not (`LESSONS` §18).

> *Is `schema_lag` still meaningful, or is it reading a stream this warehouse retired? The
> panel shows one of these two and they disagree — and a warning that is always on is a
> warning nobody reads.*

### Q-26 · For a dataset, does the overview keep four tiles or show two?

**Asked 2026-08-23 · ANSWERED 2026-08-27 · evidence in `OP-63`, whose panel half is closed**

> **HIS ANSWER: (c) — the tile set follows the kind.** A dataset shows its row count and how much has been fetched; a price source keeps all four. Ruled as [R-63](RULINGS.md#r-63--a-datasets-overview-shows-the-tiles-its-kind-has).

`/source/contractors` prints a **`Products 17,304`** tile over a contractor directory, and
three of its four tiles say nothing about a directory at all. The panel half of that noun is
fixed; the engine page is a design question rather than a word.

> *For a dataset like the contractor directory, should the overview show only the row count
> and how much of it has been fetched — or do you want the four tiles kept, with the ones
> that do not apply shown as blank rather than `0`?*

**`0` is the specific problem.** It reads as a measured zero rather than as *"not a thing
this source has"* — the same distinction `last_successful_run` already documents for a crawl
that never ran.

| | what it does | effort | what it costs later |
|---|---|---|---|
| **(a)** do nothing | the tile keeps reading `Products 17,304` over a directory | none | the engine page goes on contradicting the panel |
| **(b)** rename the one tile | `Products` → `Rows` when `kind == dataset` | one line and a guard | **it looks finished while three wrong tiles still stand** |
| **(c)** the tile SET follows the kind | a dataset shows rows and coverage; a price source keeps all four | ~half a day | nothing — and `CLAUDE.md` names two more categories coming |

**Recommendation: (c).** **(b) is the trap:** it is what *"fix the noun"* sounds like, and it
would leave two of the three wrong tiles standing while reading as done.

---

### Q-24 · Which of the two `site_profile` rows for muqawil is canonical?

**Asked 2026-08-26 · ANSWERED 2026-08-27 · found while diagnosing [REQ-45](REQUESTS.md#req-45--the-crawl-button-does-not-work-for-muqawil)**

> **HIS ANSWER: id 2 (`muqawil_org`) is canonical; id 1 closes with `valid_to`.** And it is not a tidy-up on its own — it happens inside [R-62](RULINGS.md#r-62--one-source-registry-site_profile-merges-into-source_site--and-q-24-is-answered-by-that-migration)'s migration, which merges `site_profile` into `source_site` altogether. **One fact the merge must decide rather than copy:** both rows read `lifecycle = 'draft'`, so neither is `active` today.

Measured read-only on the live warehouse:

| id | `site_key` | `base_url` | `crawl_scope` | active rows |
|---|---|---|---|---|
| **2** | `muqawil_org` | `https://muqawil.org/` | `full_then_listing` | **34,675** |
| **1** | `muqawil` | `https://muqawil.org/ar/contractors` | `listing_only` | **0** |

**Three reasons this is a question and not a cleanup:**

1. **It decides what the crawl button sends.** `REQ-45` waits on which registry starts a
   generic crawl; whichever key that names, **one of these rows is the wrong one.** Closing
   the empty one first would settle the question by tidying.
2. **`site_profile` sits behind his review** in `COMPATIBILITY.md`, and the table carries
   `valid_to` — so the pattern is to CLOSE a row, never delete. Even a close asserts which
   key is retired.
3. **The empty row is not obviously the wrong one.** Its `base_url` is the *more precise* of
   the two — `/ar/contractors` is the actual directory, while id 2 holds the site root. *"The
   row with the data wins"* is defensible and not the only answer.

**Neither row is seeded by code:** `'muqawil'` appears in no file under `scrapex/` or `db/`;
both were inserted at runtime by `scrapex/catalog.py:147` and `:171`. And `site_key` is
`NOT NULL UNIQUE`, **which stops two rows sharing a key and does nothing about two keys for
one site** — so this recurs when `jobs` or `tenders` is registered.

---

---

### Q-25 · Is a stored page evidence, or only a parse cache?

**Asked 2026-08-27 · his to answer · lifted off `STORAGE.md` §5, where it had no register entry**

`SR-1` says the source of truth is what the site publishes. A stored page is therefore
**evidence of what it published on a date** — which matters for a disputed row, a contractor
whose classification changed, or a claim about what the directory held before an edit. Or it
is only a cache that saves a re-fetch when a parser is corrected.

**What his answer changes, and it is one row of `STORAGE.md` §4 and no others:** if evidence
over time matters, *"keep a hash and re-fetch"* is out for profiles as well as listings. It
is already out for listings for a different reason — the directory reorders every thirty
seconds, so a listing page is not reproducible at all.

**Why it is registered now rather than left in `STORAGE.md`.** It was asked there, deferred
in the 2026-08-20 muqawil plan's §E, and appeared on no register — the same shape as `REQ-04`,
which sat ruled and unbuilt for sixteen days after dropping out of view and is the reason
`C7` exists. The question has not aged: at **921.5 MB across 57,041 snapshots** the cost of
keeping them is now measured rather than projected (`OP-83`).

---

---

**Q-17 · The licences: a readiness level almost nobody publishes, and three activities the site names wrongly in English.**
Two decisions in one place because they are the same table.
*(a)* `مستوى الجاهزية` is **empty on 1,490 of 1,500 rows** — five distinct values across
the other ten (Gold, Silver, `Dimond` as the site spells it, Basic).
`classification_membership` has no column for a per-membership attribute, so storing it
is a **migration** for a fact 0.7% of rows carry. Options: migrate now; leave it read
and unstored, which is what today does — `read_licensed_activities` returns it either
way, so the day it earns a column it is a re-parse of stored snapshots and not a
re-crawl; or drop it.
*(b)* For the **3 activities of 22** whose English half the site publishes truncated or
simply wrong, the node is stored under its Arabic identity with **no English name**.
Options: leave it empty and let the site fix itself; write our own English, which is a
mapping only you can authorise (**R-02**); or show the raw published string, `Civil
Engineering -`, which is the same string for two different activities.

**Q-18 · Do the two contractor-relation groups still get tables?**
`R-19` ruled child tables for all five groups, on one profile. Measured over 2,419:
`main_contractors` carries rows on **0** pages and `sub_contractors` on **2**. They are
also the only two of the five that are **relations between contractors** rather than
classifications, so `dataset_relationship` — which now has its first tenant — may be
their home rather than the taxonomy. Options: build them now at 2 rows; wait until the
34,834-page crawl finishes and re-measure, which costs nothing because the snapshots
keep the evidence; or rule them out and record it.

**Q-16 · Should anything in CI go red when the published engine falls behind the
source — and the answer got harder the day it was asked.** The repository can prove
that the tag he is *told* to push is the tag the workflow accepts (`OP-32`). It
cannot prove a release happened: the tag list is absent from a `fetch-depth: 1`
checkout and the hub is a network fetch, so a test that looked would either skip
silently or flake, and both are worse than not looking.

**WHAT CHANGED THE QUESTION.** When this was written the source was 0.3.0 and the
published engine was 0.2.1 — two bumps behind, with the newest installable build
silent on a double-click. Hours later he tagged `engine-v0.3.0`, and `R-35`
immediately moved the source to **0.3.1** for migration `0010`. So the steady state
of this
project is **source ahead of published**, by design: `VERSION` moves on a contract
change and releases are cut by hand (Decision 4).

**Which kills option (b) rather than merely weakening it.** A weekly job that fails
whenever published < source would be red in the *normal* case and silent only in the
minutes after a release — the crying-wolf failure
`tests/test_the_published_documents_are_checked_not_announced.py` names in its own
words, reached by arithmetic rather than by bad luck.

**So the live options are:** (a) **nothing** — the gap is expected, and `OP-32`'s
actual defect was three things at once (nothing released across two bumps, a silent
binary, and documents naming a refused tag), none of which a gap alone implies; or
(c) **a threshold rather than a comparison** — red only when the published engine is
behind by more than one minor version, or older than some age, so it distinguishes
*between releases* from *abandoned*. (c) needs a number from him, which is the whole
reason this is a question and not a commit.

*No recommendation on (a) versus (c), because it depends on how often he intends to
release. But (b) is now argued against rather than merely listed.*

**Q-15 · ~~May a session run an unmerged migration against his LIVE warehouse?~~ — ANSWERED 2026-08-27: NO.**

> **It happened twice while this question sat unanswered** — `0007`/`0008` on 2026-08-21 (`OP-33`) and `0011`/`0012` today (`OP-84`), and both times his warehouse ended up ahead of any engine `main` could build. A migration reaches it only after it is on `main`; a session testing one uses a copy. **A backup is not the protection** — both incidents left backups on disk and neither prevented this. He also approved both guards. [R-64](RULINGS.md#r-64--a-migration-reaches-his-warehouse-only-after-it-is-on-main-and-no-tag-is-cut-while-his-warehouse-is-ahead).
Three times on 2026-08-21 his engine database moved ahead of `main` — v8 against v6
in the morning (`OP-33`, closed by #243), and **v9 against v8** in the afternoon
(`OP-40`). Each instance closes by merging; the class does not.

**What it costs when it happens:** `main` cannot open his warehouse, which means the
**shipped** engine cannot either — so the product is uninstallable-for-him until a
merge and a release catch up. That is the same symptom as `REQ-28`'s black screen
arriving by a different road.

**Why it is his call and not a rule I should take.** The alternative is free and
already exists — `SCRAPEX_DATA_ROOT` gives any session a private warehouse in one
environment variable, and `R-24`'s `carry_over` is the path back. But forbidding it
also forbids the thing that keeps finding real defects: #243's own migration was
written *because* running against his real data exposed a fault a fixture never
would, and `R-24` itself came out of exactly that. So the trade is **evidence from
real data** against **his installation staying installable**, and only he can price
it.

**Three shapes, if he wants them:** (a) never — sessions use a private root and
`carry_over` proves the upgrade; (b) only behind a backup, which is what already
happens informally (`pre-ledger-repair`, `pre-reapprove`, `pre-upgrade-*` are all
sitting beside his database now); (c) freely, and accept that `main` lags — with a
rule that the migration must merge the same day.

**Q-14 · ~~What identifies an ACCOUNT, so a database can belong to one?~~ — ANSWERED 2026-08-21: (a), the signed-in address.**
→ [R-34](RULINGS.md#r-34--an-account-is-the-signed-in-address-and-a-warehouse-records-whose-it-is).
He settled it by naming one: «اجعلها تخص حساب muhammad.bayoumi.ali@gmail.com», and
his own warehouse now carries it in `scrapex_meta.account_owner`. The options and
the reasoning are kept below, because the trade-off is the only place the two
rejected halves are written down.

**Q-14 (as asked) · What identifies an ACCOUNT, so a database can belong to one?**
`REQ-26`. He ruled that a database belongs to one account and not to everyone on the
machine, and that two Chrome profiles with two accounts get two databases. Measured:
**no account concept exists** — `DATABASE_ROOT` is `~/.scrapex` per operating-system
user, and a grep for `google_account`, `user_email`, `signed_in` or `def account`
returns nothing. Options:
**(a)** the **Google address** signed into the panel — matches how he described it
(«لو عامل sign in بكذا حساب») and survives a Chrome profile being recreated, but ties
the warehouse's location to an identity the tool does not yet read anywhere.
**(b)** the **Chrome profile** the extension runs in — matches the second half of what
he said, needs no sign-in at all, and is what the native-messaging host already knows;
but two accounts used in ONE profile would share a database, which is the case he
objected to.
**(c)** an **explicit choice in the panel**, a named workspace the user picks. No
guessing, works with no browser at all, and it is the only option that lets one person
keep two warehouses deliberately — at the cost of a first-run question.
*No recommendation offered: this decides where other people's data lands, and (a) and
(b) each fail exactly one half of what he described. It needs his intent, not a
default.*

**Q-13 · R-19: child tables — as five bespoke tables, or as five child DATASETS
referencing a taxonomy?**
He asked for his own ruling to be tested before it was built — *«ادرس حكمى اولا هل هو
صحيح ام هناك الافضل»*, captured as
[REQ-23](REQUESTS.md#req-23--test-my-own-ruling-before-building-it-with-strict-review-criteria)
— against strict criteria. Measured in
[R19-CHILD-TABLES-MEASURED.md](R19-CHILD-TABLES-MEASURED.md): 11 criteria, 5 shapes,
518,490 rows.

**The ruling's substance is upheld.** JSON costs **1,168 ms** on the query R-19 names
against **0.6 ms** for the best shape — 47x worse than even a bespoke table, and
nothing in the measurements favours it.

**What the ruling did not decide** is how the value itself is stored, and one
criterion nobody had raised turns out to be the biggest gap in the table: when the
site **relabels a category**, a shape holding the string per row rewrites **103,698
rows in 5.9 s**; a shape holding it once rewrites **1 row in 0.1 ms** — about
59,000x. A live directory relabels things.

Options:
**(a)** R-19 read literally — five bespoke SQL tables. Five migrations, five read
paths, and bespoke work in the export, the API, the panel and the CLI, because none
of them speak "bespoke table".
**(b)** Five child **datasets** in `generic_record`, value as a `classification_node`
reference. **Zero migrations**; `dataset_relationship` and `classification_node`
already exist and hold **0 rows each**; provenance is *enforced* by
`source_snapshot_id NOT NULL`; one export tab per dataset from machinery already
built. Costs ~235 MB and ~28 s per full re-extraction.
**(c)** `classification_node` + one bespoke link table — **4.7x less storage** and
**7x faster to write** than (b), at the price of (a)'s bespoke work everywhere.
*Recommended: (b). It wins or ties every operational criterion; (c) is the fallback if
the storage figure is judged too high.*

**RULED 2026-08-21 — (b)**, after he asked for the three to be compared **on time**
specifically. → [R-30](RULINGS.md#r-30--r-19-is-built-as-child-datasets-whose-value-references-a-taxonomy).

**Two things found on the way that need his eye regardless of the option chosen:**
R-19's own sample reported the licensed-activities table as *"one row — the header
only"*, and the committed fixture for a different contractor has **six** — so "empty"
was never general. And `dataset_workbook_tables` returns exactly one tab, justified in
its docstring by *"a contractor directory has one flat table"*, **which any of these
options makes false**; no test anywhere references that function.

**Q-6 · Topology: is the TypeScript engine still the plan?**
You chose Topology A on 2026-07-18 and nothing has been built toward it since; the Python
product has instead become the whole thing. Options:
**(a)** Reaffirm A — then Spike 2 (wa-sqlite + OPFS running `db/schema.sql` in MV3) is the
next real piece of work and everything else queues behind it.
**(b)** Defer A explicitly — keep Python as the product, mark MASTER-PLAN as history, and
stop measuring ourselves against a roadmap we are not on.
**(c)** Reverse to B — the study's own recommendation, which is now almost entirely built.
*Recommended: (b) or (c). Either way MASTER-PLAN.md gets corrected in the same session.*

**Q-1 · ANSWERED — Heidelberg Materials Egypt: how should the price matrix be modelled?**
*(Closed 2026-08-12 by re-measurement, and the closure survived a sceptic. Kept
for the reasoning, which is the only place the modelling trade-off is written
down.)*
Their price is a function of product × city(46) × segment(5) × plant(3) × tier(2) and
`PRODUCT_PRICES` has a column for none of the four (`docs/recon/heidelberg-materials-eg.md`
§4.1). Options: **(a)** public price only — one row per product, zero schema change, loses
~95% of what they publish; **(b)** synthetic variants via `variant_axes` — captures
everything with no migration, but calls a pricing context a "variant" and the variant UI
will present them as choices; **(c)** widen the contract with real `city` / `segment` /
`plant` / `qty_tier` columns plus pricekey identity fields — correct, and the largest change.
*Built naively, one product's ~276 prices would read as the same offer changing price
repeatedly inside a single crawl.*

**Q-2 · STILL OPEN — Heidelberg: `maxPrice` (1,950) is never displayed; the site
shows `salePrice30*` (3,950.02).** Record only the displayed one, or both with the
unshown one flagged? *(A 2026-08-12 pass called this closed; the sceptic refuted
it — what exists is declared, not driven, and only part of what the question asks
was settled.)*

**Q-3 · ANSWERED — Heidelberg: which customer segments?** `Y6` is what the public
sees; `YM`/`YT` publish 5 prices each; `YO`/`YR` publish none. *(Closed 2026-08-12
by re-measurement.)*

**Q-4 · STILL OPEN — Heidelberg: VAT.** Record `evidence: stated, rate_pct: 14`
scoped to the order total, or `unknown` for the listing price? ~~*My reading: the
site makes no VAT claim about the per-tonne price, so `unknown` is the honest
answer.*~~ **Struck 2026-08-12:** a `tax:` block is real and on `main`, so that
suggested answer is now wrong and must not be re-proposed from the old text. The
closure was refuted by mutation — the test that would prove the behaviour does
not drive it.

**Q-5 · STILL OPEN — Heidelberg: is a 9-product source worth a bespoke connector
at all?** Two requests for ~211 real Egyptian cement price points — cheap to run,
but it is a new connector class and possibly a contract change.
**Re-measured 2026-08-12:** the connector is **built**, and `sources.yaml` has
`HEIDELBERG_EG` **`active: false`** — so it exists and has never crawled. The
question is now smaller and more concrete: switch it on, or delete it.

**Q-11 · Which sources should actually be running?** ~~Right now the manifest on
disk, the manifest on `main`, and the warehouse give three different answers~~ —
**re-measured 2026-08-12: they now give ONE answer**, twelve sources with seven
active (see **OP-2**). The disagreement is gone; the decision is not.

The question is purely yours now: **is seven of twelve the set you want?** The
five that are off are MADAR, ELBUROJ, SIKAEGSHOP, HEIDELBERG_EG, SPARK_ESHOP.
Worth answering beside **BV-3**: one of the seven that IS on, ALSWEED, is being
refused with HTTP 429 because the crawl delay is switched off.

**Q-9 · Exchange-rate cadence.** ~~~93 fetches per refresh, ~372 requests a day~~
— **re-measured 2026-08-12: 119 currencies, ~476 Google Finance requests a day**
at the 6-hour default. Raised in `c63ec21` rather than quietly changed, because
Google Finance being the rate authority is your ruling.
Options: keep it, or reduce the cadence. ~~Or fetch only the currencies the
*active* sources actually price in~~ — **struck**: it saves nothing while
GPP_ENERGY is active, which it is.

**Q-10 · GPP's country/material pairs with no local price.** ~92 pairs publish a USD figure
and no local price, and your rule is that the local price is the record — so today they are
stored as nothing. On screen, should they be blank, hidden entirely, or shown as "the site
publishes no local price"?

**Q-8 · `/api/native-host/register`.** It has no authentication and replaces the allowlist
rather than joining it. Options: add authentication; make it merge instead of replace; both;
or accept it because it is already unreachable from any web page. *(It cannot simply be
locked down — it is the route that repairs a broken extension link, so it must stay
reachable from an extension whose id the old manifest does not know.)*

**Q-7 · `open` vs `product_url` → `product_link`.** Both target the same name and
`dataset_field` has a UNIQUE constraint. One of the two has to lose; which?

**Q-12 · Branch cleanup.** Delete the stale `codex/*` heads and `saved/unified-ui-design-system`?
`git worktree remove` has to come first for the two under `~/.codex/worktrees/`.

---

## 6a. Entries first recorded on 2026-08-11, and one issue still open

**The in-flight table that opened this section is gone.** It was dated 2026-08-11 and said
of itself *"the only section that goes stale by the hour"*; it then sat sixteen days.
[STATE.md](STATE.md) owns what is in flight, and a second copy of that job is a second thing
to keep true. `git show 8bc6241:docs/BACKLOG.md` has it.

**Checked against GitHub rather than against the table:** [issue
#161](https://github.com/muhammadbayoumi/ScrapeX/issues/161) — *"the panel says closing it
never stops a run"* — is **CLOSED**, so the row reading *"Not started"* was wrong. [issue
#160](https://github.com/muhammadbayoumi/ScrapeX/issues/160) — *"the panel talks about the
engine in the wrong places, and says it twice differently"*, four panel-placement defects —
is **OPEN and recorded nowhere else in this system**, which is why it is written here.

**And one decision from that table, so it is not re-proposed:** the engine stays **unsigned**
by his decision of 2026-08-11 — sole user, so a certificate buys trust from strangers there
are none of.

The entries below were recorded the same day and are live on their own terms.

### OP-18 · A test guard was blind to the thing it was written to find

Found on 2026-08-11 by the session that rebased #152, while hardening a line I
had asked it to look at for a different reason.

`side-panel-startup.test.mjs` stripped script comments with
`.replace(/\/\/[^
]*/g, "")` before asserting the diagnostic page makes no
request. The `//` in a URL reads as a comment marker, so everything after it on
that line is deleted — **including a real `fetch(` on the same line**. Proved
with a probe: `fetch("https://example.invalid/probe")` passed the guard silently
on the old strip and fails loudly on the new one.

~~The strip is now line-by-line: a whole-line comment is dropped, a line
containing any quote is kept verbatim, otherwise a trailing `//` goes.~~

**THAT NEVER LANDED. Re-measured 2026-08-12, and this is the worst error in this
file** — a notebook recording a fix that does not exist is worse than one
recording nothing, because it closes the question.

`extension/tests/side-panel-startup.test.mjs:562-563` on `4fcc14f`:

```js
  const script = read("tests/diagnostic-panel.js")
    .replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/\bfetch\s*\(/.test(script), "the diagnostic page makes a request");
```

That first `replace` is verbatim the blind expression the paragraph above claims
was replaced. Re-run of the entry's own probe — the real
`extension/tests/diagnostic-panel.js` with
`const u = "https://example.invalid/probe"; fetch(u);` appended:

```
guard sees a fetch(  -> false
probe line after strip -> "  const u = \"https:"
```

The `//` inside `https://` eats the rest of the line, `fetch(` never reaches the
assertion, and the suite is green for a page that plainly fetches.

**Next action:** apply the hardening this entry already describes. It is one hunk
in one file, and the description of what it should do is above — the work was
done once and lost, not designed and abandoned.

**And a suggestion of mine was refuted in the same reply, correctly.** I proposed
a fixpoint loop by analogy with the `<!--` strip beside it. Removing an inner
`<!-- -->` joins its two sides into a fresh comment, so that one needs the loop;
the line-comment regex ends at `
`, so two `/` can never be brought together.
Fuzzed 20,000 strings: zero changed on a second pass. Copying the loop would have
been ritual.

**Still open, deliberately:** the `/* */` strip on the following line has the same
class of hazard — a `/*` inside a string literal deletes forward to the next
`*/`. Latent today. Before hardening it, check whether the file contains a block
comment at all: if not, the line is dead code and deleting it is safer than
making it clever.



*Added 2026-08-11 after it appeared NINE times in a single day. Not a task — a
lens to hold while reading everything above.*

**A gate that checks something is DECLARED, not that it WORKS.**

Every instance looked like coverage and was not:

- ~2,200 tests, and **not one starts the built binary**. The engine could ship
  68 MB with `pytest` inside it and pass everything, because the binary *works* —
  it is merely enormous and slow, which no assertion about behaviour notices.
- `source_site.active` was read through `WHERE active = 1`, a filter matching
  every row because nothing ever wrote 0. It looked like maintenance for months.
- A touch target asserted at `>= 48` was **loosened to 47.5 so it would pass**.
  Measured afterwards: the button renders at exactly 48. The relaxation bought
  nothing and lowered an accessibility floor permanently.
- A hover test compared the foreground colour, which the fix never changed. It
  passed with the fix reverted — proved by reverting it.
- An assertion on the finance switch was satisfied by the ENGINE POWER switch
  elsewhere on the page. An assertion another element can satisfy is not a test
  of this one.
- `publish-docs.yml` ended by printing two URLs it never opened.
- The privacy policy's truth is asserted against the shipped manifest — good —
  but nothing checked the page a reader actually loads.
- A ledger exemption was added to `carry_over` with **nothing holding it to
  account**, which is how "these two tables" quietly becomes "and these others".
- The panel's own comment promises that closing it never stops a run (OP-16).

**The test.** For any guard, ask: *if the thing it protects were broken right
now, would this fail?* If you cannot answer without running it, run it — break
the thing, watch it fail, restore. Three tests written on 2026-08-11 exist only
because their first versions passed while guarding nothing.

**And the same discipline applies to diagnosis.** Four hypotheses about the blank
side panel were measured and killed before the right one — Windows occlusion, the
opening strategy, a zero-width layout, the engine's absence. Three mechanisms
were recorded WRONGLY on PR #152 and corrected. The conclusions converged only
because nothing was accepted without a number.

### Measured: what a backup bundle actually weighs — 2026-08-12

Built from the owner's real warehouse (113.6 MB database, 22.4s to build) when
he asked why the backup is zipped at all. The answer is a number, not a
preference:

| | files | size | share |
|---|---:|---:|---:|
| `warehouse.db` | 1 | 113.6 MB | 54.6% |
| `.jsonl` | 34 | 62.0 MB | 29.8% |
| `.csv` | 34 | 28.2 MB | 13.6% |
| `panel.jsonl.gz` | 1 | 4.0 MB | 1.9% |
| **total** | **73** | **207.9 MB** | |

Zipped: **36.0 MB — 17.3%**, in 1.8 seconds. So 1.8 seconds of CPU saves 172 MB
of upload, and with `KEEP = 3` Drive holds 108 MB instead of 624 MB. Uploading
unzipped is not a trade-off, it is six times everything.

**But the question was right about the part that mattered.** `panel.jsonl.gz` is
already gzip, which browsers read natively, and it was locked inside a zip they
cannot open at all. Lifting that one file out beside the archive costs 11% more
upload and removes the need for a zip reader — which is what made the
no-engine Data page reachable.

**Worth recording for later:** the bundle carries the same data three times —
in the `.db`, as `.jsonl` + `.csv`, and as `panel.jsonl.gz`. That is deliberate,
for three different readers, and compression hides it. If space ever becomes a
problem, the 90 MB of `.jsonl`/`.csv` is the part regenerable from the `.db`;
the zip is not the thing to reconsider.

### OP-20 · ~~CI has not executed since 2026-08-19, and the reason is billing~~ — CLOSED 2026-08-23

**CLOSED 2026-08-23 — resolved by him in one command: the repository was made public.**
Measured on `main` the same day: `CI` succeeded again after failing **0-3 seconds with ZERO
steps** on every run since `2026-08-19T14:28Z`. **This was an account setting and only the
owner could clear it** — nothing in the repository could.

**The item worth carrying is what the four red days hid.** `publish-docs.yml` compared a hash
of a shell variable rather than of the served bytes, so it had been failing for **eight days**
while the served copy was byte-identical the whole time. Fixed by writing curl's output to
`$RUNNER_TEMP` and hashing the file, keeping the served-nothing check.

**Why it went eight days unread, and both halves are lessons.** The guard *"cannot fix what it
finds"* by design, so its failure is normal-looking noise on a schedule nobody watches — and
this entry had made **every** red check mean *"unpaid"*, so a red that meant *"broken"* was
invisible. **A guard that cries wolf daily is not a guard**, and this one had never been
exercised against a passing case.

### OP-19 · The chaos test races the startup sweep it is checking — STILL LIVE, re-measured 2026-08-26

> **RE-MEASURED 2026-08-20, and "MOSTLY fixed" is too generous.** Thirteen runs of
> `test_a_killed_engine_does_not_leave_a_job_claiming_to_run` across two
> checkouts: **8 failed, 5 passed.** The `swept=True` marker did not close the race.
>
> It fails on **unmodified `cab69b1`** — 1 of 5 there — so it is not caused by any
> branch in flight; a separate worktree carrying only documentation changes failed
> 7 of 8. That asymmetry is this entry's own thesis rather than a second bug: the
> conditions differed, and **two other sessions were editing this repository at the
> time**, which is precisely the "loaded Windows machine" named below. The failure
> is always the same assertion, `tests/test_the_engine_survives_being_killed.py:266`
> — after crash and restart the job still reads `running`.
>
> The trap described below was walked into again on the way here, and this entry is
> what stopped it: three consecutive failures in the modified worktree looked like
> proof the branch had caused them. Four passes on the unmodified checkout refuted
> that in one command. **Never conclude from runs on one side only.**
>
> **Re-measured again on the evening of 2026-08-20, and this time the load was
> deliberate.** The partitioned muqawil crawl was running — ~1,964 requests against a
> live site — which is the loaded machine this entry names, rather than a coincidence
> of other sessions. Under it: **3 of 3 failures on unmodified `main` at `2366d6d`**,
> same assertion at `tests/test_the_engine_survives_being_killed.py:266`, and the same
> failure inside the branch. Both sides, as this entry demands. So a crawl in progress
> is now a known way to reproduce it fairly reliably — which is worth more to whoever
> fixes it than another run of the flake in quiet conditions.
>
> Consequence unchanged and worth restating: `_source_is_busy` reads that status,
> so a real crash leaves the source blocked from every future crawl with nothing
> anywhere saying why. That is the defect; the flaky test is only how it is seen.
>
> **Re-measured 2026-08-26, and this run adds the one pairing the thirteen did not
> have: the SAME SHA, green in CI and red here.** Seen from
> `fix/the-release-gate-fetches-a-page` at `0e26139`, based on `35962cc`. Full
> suite: **1 failed, 3287 passed** — the failure the same assertion at
> `tests/test_the_engine_survives_being_killed.py:266`. Then that file alone, three
> consecutive runs: **pass, FAIL, FAIL.**
>
> **`35962cc` is green in CI**, and the local failures are on a tree whose engine
> code is byte-identical to it. So this is not "fails on unmodified code" a fourth
> time — it is *the same commit passing on a CI runner and failing on this machine*,
> which is the discriminator the entry has been missing. **A timing-sensitive test
> and a load-exposed race are not distinguished by "it flakes"; they are
> distinguished by whether the machine is the variable.** This says it is.
>
> **And the "never conclude from runs on one side only" rule above was satisfied by
> PROOF rather than by sampling.** Rather than run the unmodified checkout too, the
> branch was shown to be incapable of causing it:
>
>     git diff origin/main --name-only -- scrapex/ db/ packaging/                       -> 0 files
>     git diff origin/main --name-only -- tests/test_the_engine_survives_being_killed.py -> 0 files
>
> Four files change on that branch and none of them is engine code or the test. That
> is stronger than four passes on the other side, because a sample can be unlucky and
> a byte-identical tree cannot. **The rule's intent is "do not conclude from one
> side"; running both sides is one way of obeying it and not the only one.**
>
> Conditions, stated rather than assumed: an engine was listening on `127.0.0.1:8000`
> throughout (a `pythonw` started 07:22 that morning, belonging to another session),
> and several interactive sessions were live on the machine. Whether a crawl was in
> flight was **not** verified, so this is a loaded machine of unknown load — the
> deliberate-crawl measurement of 2026-08-20 above remains the better-controlled one.
>
> The reasoning that led here arrived at this entry's own conclusion independently,
> from the test's failure message alone and with no knowledge of the entry: if load
> can leave a job stuck at `running` in a test, load can leave one stuck in reality.
> **Recorded because agreement reached twice by different routes is evidence, and
> because it is the second time this entry's consequence has had to be re-derived by
> someone who could not see it** — the first was the session that found the entry
> after concluding it. A defect that keeps being rediscovered is under-advertised
> rather than well-documented.

Found 2026-08-11 while removing the engine's Google surface. The suite went red
on `test_a_killed_engine_does_not_leave_a_job_claiming_to_run`, and the first
comparison — one run with the change, one without — said the change had caused
it. **That comparison was worthless and the conclusion was wrong.** Four runs on
the unchanged code failed three times.

`Engine.start()` waits for `/api/health` to answer and nothing more, then the
test reads `crawl_job.status` immediately. The stale-job sweep that clears a
crashed run is a separate startup step, so whether the assertion passes depends
on which of the two lands first. It is a race by construction.

CI has been green all session, which means the sweep reliably wins on the Linux
runner and reliably loses on a loaded Windows machine — the worst arrangement,
because it makes the flake look like "works in CI, broken locally" and invites
exactly the wrong diagnosis.

**The fix was not a sleep.** `reclaim_orphaned_jobs` now records when it
finished, in `scrapex_meta` beside the heartbeat that was already there, and
`Engine.start(swept=True)` waits for that value to change. The marker is written
UNCONDITIONALLY — a marker that appears only when there were orphans would be
absent on every healthy start, and anyone waiting for it would wait for ever on
exactly the machines where nothing had gone wrong.

> **RE-MEASURED 2026-08-19 AND IT IS BACK, under load.** Three consecutive runs of
> `tests/test_the_engine_survives_being_killed.py` on the owner's Windows machine --
> while a full suite and twenty review agents were running -- gave **pass, FAIL,
> FAIL** on an unchanged tree. The marker fix does not hold at this load, so
> "MOSTLY" in the heading is doing real work.
>
> Recorded rather than diagnosed, and deliberately not blamed on the change that was
> in flight: this entry's own warning below is that a with-and-without comparison
> proved nothing here before. What is new is the load. The next step is to find
> whether `Engine.start(swept=True)` is on this path at all, not to add a sleep.

**Four runs in four, green.** And an honest note on the check: removing the wait
again passed three runs in three that afternoon, having failed three in four
that morning. A race that depends on machine load cannot be reproduced on
demand, so the mutation check proved nothing — which is precisely why "it passes
now" was never evidence in the first place. The proof is structural and readable
in the code: health is answered by the HTTP thread the moment the port binds,
and the sweep runs on the worker thread after it connects. Two tests in
`test_jobs.py` hold the marker's two properties deterministically.

**NOT FULLY CLOSED, and saying so is the point.** Later the same day it failed
once more inside a FULL `-m "not extension"` run, then passed the next full run
and every targeted one. So the sweep wait removed the race it was aimed at and
something else in that test is still load-sensitive — the kill/restart cycle
runs real subprocesses and a 90-second health wait, and the whole suite is a
heavier neighbour than any subset.

Recorded rather than declared fixed, because "it passed this time" is exactly
the evidence this entry exists to reject. The next step is to find what ELSE in
the cycle depends on timing, not to run it again until it is green.

## 6c. The extension/engine separation, audited — 2026-08-11

**He asked whether the extension is fully separated from the engine. It is.** Zero `.py` or
`.pyc` under `extension/`; the shipped package is `cp -r extension build/scrapex` minus
`tests/`, `README.md` and `*.pem` (`release-extension.yml:85`), so no Python byte reaches the
store. Two independent release triggers, neither building the other's artifact. Runtime
contact is two narrow paths and nothing else — native messaging for CONTROL, HTTP on
`127.0.0.1:8000` for DATA.

**Four notes were raised and a fifth found by comparing the directories rather than trusting
a tool's list. The verdicts, and what each left behind:**

| | verdict | what remains |
|---|---|---|
| **SEP-1** · the extension's tests are written in Python | **DECISION, not debt** | The Python tests drive real Chrome through Playwright and assert rendered geometry; node cannot without an npm dependency, which this repository refuses on purpose. **The cost is stated rather than paid:** if `extension/` ever moves to its own repository that harness must be ported — a real day of work. Nobody has asked, so it is not debt |
| **SEP-2** · four generated copies did not say they were generated | **FIXED** | `design/tokens.css` said *"canonical source … run the tool after editing this file"* and that sentence was copied verbatim into both generated copies, **where both halves of it become false**. The rule is `ENGINEERING.md` Q1b; the guard is `test_every_generated_copy_says_it_is_one`, mutation-tested by stripping the banner |
| **SEP-3** · `timezone.js` was 493 identical lines with no source | **FIXED** | It is authored in `design/` and generated into both now. **The byte-equality test was never missing** — the first draft of this audit was about to report it as unguarded and re-reading refuted that. What it could not do is say *which* copy is right: its message reads *"copy one over the other"*, and two readers who each just fixed a different copy obey it by reverting each other |
| **SEP-4** · `PROTOCOL_VERSION` stated in two languages | **CORRECT, no change** | JavaScript cannot import Python. `test_native.py` holds them together and asserts the regex **found** the line before comparing, so a reformatted declaration fails rather than passing vacuously. Exactly one literal per side |
| **SEP-5** · *"the engine reads the extension's manifest"* | **WITHDRAWN — my error** | `scrapex/version.py:10` is prose in a docstring saying the extension's number is deliberately **not** there. I read a docstring as code. The only Python that reads that manifest is `tools/panel_harness.py:121`, a harness that never ships. Recorded so the note is not raised a second time |

## 6d. The whole file re-measured — 2026-08-12

Six agents read the code, the git history and the live warehouse one entry at a time, told
never to verify a claim against this file's own prose. A sceptic then tried to refute every
closure, **because striking an item off is the only irreversible move here**: an item wrongly
left open costs a second look, an item wrongly closed is forgotten.

| | |
|---|---|
| items measured | 47 |
| still open, or *changed* — real, but not the problem described | **45** |
| genuinely closed | **2** — `Q-1`, `Q-3` |
| closures claimed and **refuted** | **6** — `OP-2`, `ت2`, `Q-2`, `Q-4`, `Q-5`, `Q-11` |

**What this file got wrong, as a class: not the judgements — the numbers.** Almost every
figure quoted more than once had drifted — `app.py` 2,955 → 3,347 lines, Sika 78 → 185
observations, branches 117 → 148, currencies 93 → 119 requests, sources *"six of twelve"* →
seven. Two entries described fixes that exist and one described a fix that **does not**
(`OP-18`). **The lesson is mechanical, not moral:** a number written down once is a number
nobody re-counts, so every figure now carries the date it was measured
([LESSONS §14](LESSONS.md#14--a-measurement-that-outlives-its-base--and-the-instance-that-was-a-live-process)).

**The three live faults it found are registered by number** — `BV-3` (ALSWEED refused with
HTTP 429 because `crawl_honour_delay` is `'0'`), `OP-6`/`ت2` (Settings says *"Not running"*
while a crawl runs, and the heartbeat freezes under `database is locked`), and `OP-18` (the
diagnostic-page guard is still blind, which this file had claimed was fixed).

**And two failures of mine, recorded because they are the same failure twice.** #177's guards
are string greps over `app.py`'s text, so the code the commit changed has no executing
coverage (`OP-2`); the same day a test I wrote for the spreadsheet chooser passed against its
mutation because it drove the helper rather than the feature — caught before merging, by
attacking my own branch. **A guard must fail when the behaviour is broken, which is only
demonstrable by breaking it.**

---

## 7. Done — newest first, so it is not re-proposed

*This table and `CHANGELOG.md` answer two different questions and neither replaces the
other. Here: what was done, when, and by which commit — the session-level record. There:
which VERSION a capability is guaranteed from, generated from `scrapex/version.py` and
never hand-written (`e9dd17e`). A feature can appear here the day it is built and there
only when a release carries it.*

| when | what | commit |
|---|---|---|
| 08-11 | **The Side Panel opened blank until you clicked elsewhere.** Chrome creates the panel document HIDDEN and reveals it only after `load` (8.9ms and 6.5ms after it, two traces); a hidden document's resource loading is deprioritised, so the panel stayed hidden until `load` and `load` was slow *because* it was hidden. `app.js` is now appended by `boot-app.js` on `load`, and its entry point asks `readyState` instead of waiting on a `DOMContentLoaded` that has already passed. Owner-verified in real Chrome | PR #152 |
| 08-11 | **The engine had not started since the collapse to one database.** `databases.json` still said `mode: split`, and the refusal message named `init-db` — which creates an EMPTY database and has never read `marketlens.db`. Following it would have left 110 MB of prices orphaned. `scrapex carry-over` copies both files read-only, counts distinct source rows against a destination baseline, and moves the pointer only if every table of data agrees. Ran on the owner's data: 338,000 rows, 88,286 price observations, zero short | PR #159 |
| 08-11 | The release built the engine in the same environment that ran the tests, so `pytest` and Playwright shipped inside the binary (193 references to playwright in the published exe). Build moved to a venv with runtime extras only, plus a 45 MB ceiling. **Measured honestly: 67.6 MB → 60.1 MB, eleven per cent — not the two thirds the disk sizes suggested.** A `--splash` covers the unpack, which is the part that actually looked broken | `756fa39` (#154) |
| 08-11 | `source_site.active` said all twelve sources were live while `sources.yaml` had five switched off. The column is written once on insert and never set to 0 — an inactive source is never crawled, so the only code touching its row never runs. Its one reader filtered on `WHERE active = 1`, matching every row. `reconcile_active` writes the manifest's intent on every panel flip; a source the manifest no longer names is left alone, because that is `undeclared_sources`' business | `b90c239` (#155) |
| 08-11 | "Five currencies with no exchange rate" was never five and never currencies: `UNKNOWN` (3,149 obs, all belonging to the deleted SPARK_ESHOP), `USD` (the base), and `SLL`/`ZWD` — retired in 2022 and 2009. The engine asked Google for all three every refresh cycle, failed, and wrote three warnings nobody could act on. Named in `UNQUOTABLE` with a reason and date each | `0010677` (#156) |
| 08-11 | `publish-docs.yml` ended by echoing two URLs. The publish writes through the Contents API; the page reads through raw.githubusercontent.com, and hangs on a `data-sx-doc` attribute in a separate repository. Either half could break with the publish still reporting success — and the first to notice would have been a Google reviewer rejecting the store listing. Both halves are now checked, with a retry for CDN lag and no browser | `bf0912b` (#158) |
| 08-11 | `mypy --strict` over the price files for the first time: 72 findings, 14 correctness-shaped, **10 false and 2 real** — a `None` ruled out only by a raise twenty lines up, and a cache typed `dict[str, object]` feeding a function that needs a `RobotsReport`. Both were mine from the same day. The gate itself is NOT here: 60 of the 72 are annotations, and that churn buys no defect | `1631af8` (#157) |
| 08-11 | robots.txt became the owner's decision per site — follow the tool default, obey that site, or write a rule for it alone | `adf31b2` (#153) |
| 08-11 | The Engine page: status, install disclosure, overflow menu, and a disabled power placeholder. Final review found a touch target loosened from 48 to 47.5 to pass (measured: it renders at exactly 48), a hover test that stayed green with its own fix removed, and eight dead class names the UI-kit gate was right to reject | `db44ce0` (#151) |
| 07-30 | Version management: one version with drift-tested mirrors in `pyproject.toml` and `extension/manifest.json`, a capability ledger whose minimum-extension gate is derived from it, a baseline that fails the build when the capability set moves while the number stands still, and a panel that says which version it is and what that version can do | `e9dd17e` |
| 07-29 | Crawl pace controls moved into the panel; the web page proved display-only by a test that fails if it grows an input | `2253308` |
| 07-29 | A market rate now outranks a storefront's in all four USD subqueries — authority first, then recency | `69e986c` |
| 07-29 | advancedcastle's own published exchange rate captured under `source_kind='shop'`, on a session of its own because the country is a cookie, not a path (188 shop rows live) | `b43405c` |
| 07-29 | Sika's trade tier reaches the warehouse — 78 observations now carry `price_trade`, was 0 of 73,084 | `436105c` |
| 07-29 | The reason advancedcastle's Egyptian price is not crawled, filed beside the source it describes | `e639310` |
| 07-29 | The sealed-archive / WAL cluster: a sealed archive keeps its rows, the in-flight guard reads the seal not a filename, a compaction says "superseded" not "moved", `Repair` really refreshes statistics | `234cdc1`, `4103e48`, `4dfb9e8` (PR #10) |
| 07-29 | Reconnaissance of onlinestore.heidelbergmaterials.eg committed *before* any decision — 23 live requests, three traps recorded, five questions left open | `73af22b` |
| 07-29 | The panel stops storming the engine with N+1 requests and stops stealing the log selection | `f901638` |
| 07-29 | CI made to actually run the guards it had: the 53-test panel suite (with the only XSS guard) had been silently skipping, and `extension/app.js` got its first behavioural tests | `48ec48b` |
| 07-29 | Ten dead native-host commands retired; the HTTP transport states its protocol version; one commit point for where the warehouse lives | `0a2209c` |
| 07-28 | `main` repaired so it starts from a clean checkout: nine defects including magento's half-brand (which read as ~536 price periods closing on prices that never moved), salla/zid honouring Cancel, and `engine.log` finally rotating | `c7fa4ea` |
| 07-28 | The row fold stops merging two countries into one row — measured 628 → 561 with 58 silent country merges | `10dc4ab` |
| 07-28 | Variation folding + `category_leaf` (MADAR 3,322 of 3,417; ADVANCEDCASTLE 163 of 168 across depths 1–6) | `e569753` |
| 07-28 | Edit, rename, stop-tracking and wipe a source, from the panel and from the API, with the rename moving nine tables in one transaction | `412785b`, `8c1d661` |
| 07-28 | Grid sorting that reads the column instead of a list of names, Arabic collation, and a fit that stays fitted | `059820d` |
| 07-28 | The header's buttons and a set filter that means it (numeric filters matched nothing; blanks were unselectable) | `d3bfd21` |
| 07-28 | The crawl-delay switch, shipping *honouring*, announcing the number when overridden; and the rate-refresh lock that was blocking queued jobs | `c63ec21` |
| 07-28 | Per-page resume journalling for zid and hybris | `fd2b6d9` |
| 07-28 | Seven detail groups, generated migration, and a static test that fails when a connector's `group=` hint disagrees with the map | `ba8ee09` (0046) |
| 07-27 | Exchange rates from Google Finance with the date on every number | `5c7f2dc` |
| 07-27 | GPP Libya — it publishes a local price and the parser can now read the page it publishes it on. **Verified today: LY carries DIESEL and GASOLINE at 0.15 LYD, observed 2026-07-29.** This closes the open question in memory `gpp-libya-missing.md` | `292bfea` |
| 07-27 | A web page can no longer drive the local engine (origin lock, three layers) | `3d7d1a9` |
| 07-26 | The bilingual vocabulary sweep: unmarked = English, `_ar` = Arabic, `PAYLOAD_VERSION 2` refusing every pre-sweep payload | `cd5348a` + 0038–0042 |
| 07-21 | GPP rebuilt around the local-currency price each country page publishes; USD list figures demoted to a canary | `ff28f41`, `f769c59`, `7cfa8f2` |
| 07-19/20 | Phases 5 and 6: settings, outputs, retention-by-compaction, and the 17 defects an adversarial review found past 527 green tests | `f8b6d6c` |

*(GPP's ten-year history backfill appears to have run: 62,761 of 73,162 observations carry
`provenance='reported'`, measured today. memory `gpp-local-currency.md` still lists it as an
owner to-do — **inferred**; the check is which run wrote them.)*

---

## Appendix A — where the material for this file came from

- `git log` on `main`, last ~130 commits. The commit messages in this repository are the
  single best record of decisions and their reasoning; most of §1 and §5 came from them.
- `gh pr list --state all` (15 PRs total; #10–#15 all closed or merged on 2026-07-29, and
  no PR is currently open), `git branch -a`,
  `git cherry -v origin/main <branch>` for each unmerged branch.
- `~/.claude/projects/C--Users-User01-source-repos-mbiXaddin/memory/` — the standing rules.
- Every file in `docs/`, and `sources.yaml`'s `notes:` blocks.
- The live warehouse, read-only
  (`sqlite3.connect("file:...?mode=ro", uri=True)`), for every measured number.

## Appendix B — status of every file in `docs/`

| file | status |
|---|---|
| `BACKLOG.md` (this file) | **live** — the tracking document |
| `CANDIDATE-SOURCES.md` (07-31) | **live** — the queue of sites the owner has sent and nobody has probed yet. Deliberately outside `sources.yaml` (SR-13). A row leaves it when the site becomes a manifest entry |
| `SOURCES-REGISTER.md` (07-31) | **live, derived** — the developer's per-source scoreboard, split price capture / generic extraction. Reads out of the manifest, the connector directory and this file; when it disagrees with `sources.yaml`, the manifest wins. Delete a reference in it when the matching `OP-`/`DEC-`/`BV-` closes |
| `MASTER-PLAN.md` (07-18/23) | **stale and misleading** — see DEC-1. Its §8 asks the owner to confirm a topology its own header says he already rejected, and it cites a `spikes/` directory that has never existed in this repo. Keep as a design study; correct the header once Q-6 is answered |
| `column-vocabulary.md` | **live** — the map is the contract; §Status feeds DEC-4 and Q-7 |
| `robots-policy.md` | **live** — SR-8 |
| `data-page-schema.md` | **live** — the Data page ruling |
| `DESIGN-SYSTEM.md` | **live** |
| `recon/heidelberg-materials-eg.md` | **live** — Q-1…Q-5 |
| `COMPATIBILITY.md`, `GENERIC_CATALOG.md`, `archive/db1-domain-database-isolation.SUPERSEDED.md` | **live** — the generic/price split (G0/G1/DB1). Not touched since 07-20; nothing in the last 130 commits builds on them, so their roadmap half is dormant **(inferred)** |
| the two `CLAUDE-after-*` product-brief copies | **deleted 2026-08-27** — 4,811 lines whose own row said *"do not read them"*. `git show d6f4967:docs/CLAUDE-after-price-history-20260720.md` |
| `PLAN.md`, `plan-closing-the-gaps.md`, `REVIEW-2026-07-28.md` | **deleted 2026-08-27** on his answer, after proving all twelve of their live items survive here by number — `DEC-4/5/6`, `DEBT-2`, `Q-10`, `OP-4/5/6/7/12/13/14`. **Every `REVIEW-2026-07-28 §n` and `plan-closing-the-gaps §n` citation still in this file reads against `d6f4967`** |
| `archive/2026-08-05-architecture-and-implementation-plan.SUPERSEDED.md` | **deleted 2026-08-27.** Kept by an earlier instruction of his, lifted on 2026-08-27 ([R-60](RULINGS.md#r-60--a-finished-document-leaves-the-tree-and-git-is-the-archive)). What replaced it is `PLATFORM-PLAN.md` §2 and §7 |
| `MASTER-PLAN.md` | **cut 2026-08-27 to §8.3**, the only section shipping code cites. 523 → 39 lines |

## Appendix C — memory files that are NOT about ScrapeX

These belong to the **mbiXaddin Excel add-in**, a different project. Listed only so they are
not lost when someone sweeps the memory folder:

`arch-review-2026-decisions` · `activation-dialog-redesign` · `sync-version-review` ·
`ndepend-baseline` · `ribbon-button-view-refactor` · `schema-guard-system` ·
`update-system-review-plan` · `codebase-consolidation-campaign` · `systemconstants-slim` ·
`library-menu-plan` · `pipelinelogger-removal-audit` · `identityintelligence-retained` ·
`connectivity-odc` · `logging-v42-plan` · `logging-roadmap` ·
`pipeline-observability-fragmentation` · `pipeline-observability-roadmap` ·
`configpresetentity-planned-removal` · `dead-file-check-by-types` ·
`export-presentation-config` · `config-bag-validation` · `debug-mode-via-build-config` ·
`docs-headers-translation-pass` · `core-test-coverage` · `expert-assessment-backlog`

Cross-project working rules that apply to both: `git-commit-heredoc-quotes` (SR-20),
`present-issues-as-questions`, `explain-before-options`, `always-recommend-option`,
`recommend-as-architect`.
