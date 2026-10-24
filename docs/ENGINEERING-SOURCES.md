<!--
  THE AUTHORITY LIST FOR ENGINEERING AND ARCHITECTURE DECISIONS, and the twin of
  docs/DESIGN-SYSTEM-SOURCES.md, which does the same job for the interface. It is a
  REFERENCE, not a register: it records what a decision RESTS ON, never what work is
  outstanding. Outstanding work is `gh issue list` — see CLAUDE.md.

  ITS COMPANION is CLAUDE.md, which states the rules this product is built by. That file
  says WHAT we do. This one says WHAT THAT RESTS ON, so a rule can be re-argued against
  its source instead of defended by seniority. When they disagree, this file is the
  outside authority and CLAUDE.md is the thing under review — the same relationship
  DESIGN-SYSTEM-SOURCES.md has with DESIGN-SYSTEM.md.

  HOW IT IS MAINTAINED. Add an entry when a decision is taken that an outside source
  governs. Mark one SUPERSEDED when the source changes or a better one is found — never
  delete it, because code cites the number. Every edit says WHAT CHANGED AND WHY in its
  commit message, never in a note here.

  WHY THE NUMBERS ARE PERMANENT. `tests/test_the_code_cites_its_sources.py` reads the
  citations in the code and the entries here and fails when either end breaks. That guard
  exists because the same failure already shipped once on the design side: fifty-three
  comments cited `R-84` for a rule that `R-85` makes, and every other guard in the suite
  was blind to it (`tests/test_the_design_system_cites_its_own_rulings.py`).
-->

# The sources a decision rests on

A rule in `CLAUDE.md` is enforced because it is written there. This file is the separate
question: **what is it right?** — so that changing a rule means arguing with its source
rather than with the session that wrote it.

**This is not a reading list.** An entry earns its place by being cited at a line of code
that would be built differently without it. An entry with no citation is removed, and the
guard fails on one, because a register padded to look complete is a register nobody
trusts — the same argument `docs/UI-KIT.md` makes about its own catalogue.

## How to use it

**Taking a decision an outside source governs:** add an entry below, then cite its number
in a comment at the line that implements it:

```python
# ES-1: a pipeline stage is not a user step. See docs/ENGINEERING-SOURCES.md.
```

**Reading a decision:** the number in the comment is a lookup key. It says the decision
was argued rather than assumed, and it says against what.

**Changing a decision:** find every citation of its number — the guard's own table lists
them — and change them together. If the SOURCE changed rather than our reading of it,
mark the entry superseded and say which entry replaces it. The number stays.

## Source-conflict resolution order

When sources disagree, in this order:

1. **A standard with normative force** — a W3C Recommendation, an RFC, an ISO/IEC/IEEE
   standard, a language or platform specification. These are not opinions and nothing
   below outranks them.
2. **The platform's own documentation** for the platform actually being used — Chrome
   extension APIs, SQLite, Python's standard library.
3. **This product's measured behaviour on his machine.** A number from his warehouse
   outranks a general recommendation about what usually happens. `CLAUDE.md`: *"A real
   `file:line` beats a plausible reading."*
4. **A mature published practice with a named author and a stated rationale** — the
   entries below.
5. **A widely used tool's documented design**, read as evidence of what works at scale,
   not as instruction.
6. **Anything else**, which is to say: not a source. An article without a rationale, a
   blog post restating one of the above, or a practice named without a reference does not
   settle an argument here.

A tie between two sources at the same level is not resolved by preference. Record both,
say what each would have us do, and it becomes a decision for the owner — the same rule
`CLAUDE.md` states for his priorities on timeline, scale and spend.

**For the interface, this file does not apply.** `docs/DESIGN-SYSTEM-SOURCES.md` governs
there, Supabase is its base, and its own precedence order is the one to use.

---

## ES-1 · A pipeline stage is not a user step

**Governs:** whether a job that another job's output makes due is started by the engine or
waited for by the owner.

**Cited at:** `scrapex/datasetjob.py:12`, `scrapex/directoryjob.py:791`.

**Measured** in #1042: the step this removes, timed on his warehouse.

### The sources

| source | what it contributes |
|---|---|
| [GOV.UK Service Manual — *Design around user needs, not government structures*](https://www.gov.uk/service-manual/design) | A service is what the person is trying to do. "Crawl, then interpret" is two of our stages, not one of his tasks. The same manual's *"do the hard work to make it simple"* is the cost side: the complexity does not vanish, it moves to us. |
| [Dagster — Software-Defined Assets](https://docs.dagster.io/guides/build/assets) | Declare the **asset** and what it depends on; the system works out what must run. `_work_waiting` already computes that condition, and the card only drew a line about it. |
| [Apache Airflow — DAG dependencies](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html) | A downstream task runs when its upstream succeeds. Sequencing is declared once, not remembered by an operator each time. |
| Hohpe & Woolf, *Enterprise Integration Patterns* — **Process Manager** | A multi-step process holds its own state, and a step's failure is handled inside the process rather than reported to whoever started it. This is what preserves the next paragraph. |

### What it does NOT overturn

`scrapex/datasetjob.py`'s own argument for two jobs stands, and the entry is written to
keep it:

> *interpretation fails on its own terms — a parser that cannot read a page, a schema that
> moved — and a failure reported as the crawl's would send the next session looking at the
> network. It is also a thing worth doing WITHOUT a crawl … Two jobs, two verdicts.*

Every word of that is about **jobs**, and none of it is about **buttons**. A chained job
still reports its own verdict, still runs without a crawl when asked, and still takes no
politeness reservation. What changes is who starts it.

**Decided** by the owner in #1042, from three costed options.

`CLAUDE.md`'s *"never start a run you cannot watch to the end"* still holds: the chained
run is visible and stoppable from the surface it appears on, which is what that rule
protects.

### How to re-open this

If a chained interpret is ever measured holding the write lock long enough to block a
crawl he started, entry 3 of the precedence order applies — a number from his machine
outranks the practice above — and this entry is superseded rather than argued with.

---

## ES-2 · An unreachable robots.txt is complete disallow

**Governs:** what a crawl does when a site's robots.txt cannot be read — by status class.

**Cited at:** `scrapex/robots.py`, `scrapex/connectors/base.py`, `scrapex/webui/app.py`,
`scrapex/directoryjob.py`, `scrapex/contractors.py`, `scrapex/connectors/heidelberg.py`.

### The source

| source | what it contributes |
|---|---|
| [RFC 9309 — Robots Exclusion Protocol, §2.3.1.3 and §2.3.1.4](https://www.rfc-editor.org/rfc/rfc9309#section-2.3.1.3) | §2.3.1.4: *"If the robots.txt is unreachable due to server or network errors, this means the robots.txt is undefined and the crawler MUST assume complete disallow."* §2.3.1.3: on a 4xx (*"unavailable"*) the crawler *"MAY access any resources on the server"*. |

### What it decides

A 5xx, or a network failure (`httpx.TransportError`), on the last of the read's attempts
**pauses** the site's run (`RobotsUnreachable`, a `CrawlBlocked`) and no page of that host
is fetched, under every robots choice. The read is retried as a page is first. A 4xx other
than 404, or a failure that is not the network's (too many redirects — §2.3.1.2 — or a body
that will not decode), keeps #1413's answer: crawled under the tool's own rules, said once
at WARNING. A 404 is no file. `GET /api/sources/{key}/robots` reads through the crawl's
own fetcher (`HttpFetcher.read_robots`) and classifies with the same function,
`robots.is_unreachable`, so it gives the same answer.

**Decided** by the owner on #1585, replacing that part of the #1413 ruling.

### How to re-open this

Level 1 of the precedence order: nothing below an RFC outranks it. A later RFC that
updates 9309 supersedes this entry rather than being argued with.

§2.3.1.4 also says that after 30 days unreachable a crawler MAY use a cached copy or
crawl as if there were no file. That is a MAY, not taken today; taking it is his decision.

## ES-3 · A tender is kept as OCDS releases, and its current state is compiled from them

**Governs:** how a tender is stored: every release kept whole and never changed, and the
typed tables rebuilt from the releases by OCDS's merge rule.

**Cited at:** `scrapex/tenderstore.py`, `db/engine/migrations/0025_tenders_kept_as_ocds_releases.sql`.

### The source

| source | what it contributes |
|---|---|
| [Open Contracting Data Standard 1.1.5, *Releases and records*](https://standard.open-contracting.org/1.1/en/primer/releases_and_records/) | A **release** is what a publisher said about a contracting process at a point in time, and is never changed. A **record** is the current state, compiled by merging the releases in date order: a field a later release states replaces the earlier value, and a field it leaves out keeps it. |
| [OCDS 1.1.5 codelists](https://standard.open-contracting.org/1.1/en/schema/codelists/) | `releaseTag`, `tenderStatus`, `method`, `procurementCategory`, `partyRole`, `awardStatus`: the vocabularies the typed columns are held to. |
| [OCDS bid statistics and details extension](https://github.com/open-contracting-extensions/ocds_bid_extension) | `bids.details`: a bid's id, its tenderers, its one `value`, its `rank`, and the `bidStatus` codelist (`invited`, `pending`, `valid`, `disqualified`, `withdrawn`). |
| [OCDS beneficial owners extension](https://github.com/open-contracting-extensions/ocds_beneficialOwners_extension) | `parties[].beneficialOwners`: a natural person with an id, a name and `nationalities` as ISO 3166-1 codes. It has no field for the control a person holds. |

### What it decides

`tender_releases` keeps each release as JSON, append-only by trigger; `tenders`,
`tender_parties`, `tender_items` and the rest are compiled from them by
`tenderstore.compile_process`, which deletes and re-inserts them because they are derived.
A notice read twice is one release. A notice that changed is a new version of the same
release, under the notice's own id, and only each id's newest version is compiled, so a
field the revision stopped stating does not survive. A field a later release sets to null
is removed, as OCDS's merge removes it. Persons stay out of the releases (his ruling on
#1647) so they can be removed; the store refuses a contact point or beneficial owners
anywhere in a payload.
The award tables (`tender_awards`, its suppliers, contracts and bids) are compiled the
same way once part 4 of milestone 51 brings their writer; until then they stand empty.

**Decided** by the owner on #1616 and #1647, 2026-10-10, and on #1658, 2026-10-17 and
2026-10-18.

### How to re-open this

Level 4 of the precedence order: a published practice with a named author, the Open
Contracting Partnership. **Provisional, by his ruling on #1614**: a reference is where a
design starts, not a rule it bends to. Each departure is recorded with its reason beside
the line that departs. 0025 records these: sectors kept in the source's own terms; a
country kept as the source's code when it has no ISO one; a deadline kept as a date and
a local time, because the source states no instant; the Bank's US-dollar figure kept
beside the signed price; a contract's duration in months, as ISO 8601; a bid's two
evaluated prices and its scores; a beneficial owner's nationality, residence and
control as the source writes them; and a revised notice kept as a new version of the
same release id, where OCDS requires an id unique within its ocid. That last one is his
ruling on #1658: the history keeps the Bank's own notice id, and the compile reads each
id's newest version (`tenderstore.compile_process`). OCDS 1.2, when it is released, is
read against this entry.

## ES-4 · New tables follow Supabase's Postgres style, as far as SQLite allows

**Governs:** the names and shape of every table created from migration 0025 on. Tables
created before it keep their own style, by his ruling on #1616.

**Cited at:** `db/engine/migrations/0025_tenders_kept_as_ocds_releases.sql`, `tests/test_tenders_kept_as_ocds_releases.py`.

### The source

| source | what it contributes |
|---|---|
| Supabase, *Postgres SQL Style Guide*, `examples/prompts/code-format-sql.md` at the pinned commit `86c813ec` (`design/supabase.NOTICE.txt`) | snake_case; plural table names and singular column names; an `id` key on every table; a comment describing every table; a foreign key named after the singular of the table it references, with an `_id` suffix. |
| [SQLite, *STRICT Tables*](https://www.sqlite.org/stricttables.html) | Declared types enforced on write, the nearest SQLite comes to Postgres's typing. |

### What it decides

An `id INTEGER PRIMARY KEY` stands in for Postgres's identity column, and a comment line
above each `CREATE TABLE` stands in for `comment on table`, which SQLite does not have.
#1616 adds two rules of its own: `STRICT` on every table, and an index on every foreign
key. A second key to the same table puts its role before the singular
(`compiled_from_tender_release_id`). `tests/test_tenders_kept_as_ocds_releases.py` holds
every rule for the tables it lists.

**Decided** by the owner on #1616, 2026-10-10.

### How to re-open this

Level 5 of the precedence order: a widely used tool's own convention. **Provisional, by
his ruling on #1614.** When the pin moves, the guide is read again at the new commit, and
any rule that changed is shown to him before a table follows it.

## ES-5 · A fact is stored once, in a table keyed by what it depends on

**Governs:** where a value a listing repeats on every row is kept, when it depends on less
than the row's key. The first case is TVTC's licence, which every training-plan row carries
for its establishment.

**Cited at:** `scrapex/directories.py`, `scrapex/contractors.py`, `scrapex/extract/tvtc_plans.py`.

### The source

| source | what it contributes |
|---|---|
| E. F. Codd, *Further Normalization of the Data Base Relational Model*, IBM Research Report RJ909, 1971 | **Second normal form:** a non-key attribute depends on the whole key, never on part of it. One that depends on part of the key belongs in a relation keyed by that part, so each fact is stated once and cannot disagree with a second copy of itself. |

### What it decides

The plans listing is keyed by (establishment, plan). Its establishment's licence depends on the establishment alone. Measured over the census: 0 of the 2,145 establishments the listing carries showed two different licences across their plans.

So the licence is not a plans column. It is a dataset of its own, `tvtc_establishment_licences`:
- one row per establishment, keyed by `establishment_id`;
- built from the same plans pages by a `DerivedReader` (`scrapex/directories.py`), which `contractors.approve` runs on the page pair the listing has just approved;
- the join to `tvtc_training_establishments` is that key.

A page whose plans carry two different licences for one establishment is refused by name, because this dataset exists only because they never differ.

**A licence row never departs** (his ruling on #1758, 2026-10-20). When its establishment's plans leave the listing, the site has stopped publishing the licence, not ended it. The row stays, and its `last_seen_at` says when the site last showed it. Two pages of one run reading one establishment's licence differently is announced by name in the approval log. That is the case that would re-open this entry.

It is not merged into `tvtc_training_establishments` either, though that table has the same key. A table written by two crawls has two freshnesses and no single date. Keeping each table to one writer keeps "when did this change" answerable; the cost is one join.

**Decided** by the owner on #1716, 2026-10-19, choosing this over storing the licence on every plan or merging it into the establishments table, after the census and this source were put to him.

### How to re-open this

Level 4 of the precedence order: a published practice with a named author and a stated rationale. The measured functional dependency (level 3) is what makes it apply here, and a census that found one establishment with two licences would re-open it. The source does not decide the second half, one writer per table; that is this repository's own reason, stated above.

## ES-6 · A stored JSON document is binary JSON, unless its exact text is the point

**Governs:** how the tender history keeps a release (`tender_releases.payload`), from
migration 0026 on. A table that keeps the exact bytes a source sent keeps them as
evidence instead (`fetched_responses`), compressed.

**Cited at:** `db/engine/migrations/0026_tender_history_kept_as_jsonb.sql`, `scrapex/tenderstore.py`, `tests/test_tender_history_kept_as_jsonb.py`.

### The source

| source | what it contributes |
|---|---|
| [SQLite, *JSON Functions And Operators*, §3.2 JSONB](https://sqlite.org/json1.html) | Since 3.45.0, JSON stored as SQLite's parse tree, a BLOB: "smaller and faster than text JSON". Every JSON function accepts it, `json()` reads it back as text, and it is treated as an opaque BLOB. |
| [Supabase, *Managing JSON and unstructured data*](https://supabase.com/docs/guides/database/json) | "The recommended type is jsonb for almost all cases": json keeps an exact copy that each read reparses, jsonb is "significantly faster to process". |
| [PostgreSQL, *JSON Types*, §8.14](https://www.postgresql.org/docs/current/datatype-json.html) | "most applications should prefer to store JSON data as jsonb, unless there are quite specialized needs, such as legacy assumptions about ordering of object keys." |

### What it decides

The release is stored as JSONB, and its CHECK holds it to one well-formed JSONB object
(`json_valid(payload, 8)`). PostgreSQL's exception, the exact text, does not apply: the
source's own bytes are kept in `fetched_responses`, and the dedup key is the sha256 of the
release's canonical text, taken in Python before the write. Measured on the six real
World Bank releases, 100,000 rows, SQLite 3.50.4: 1,462 bytes a release against 1,643,
`json_extract` 2.2 to 2.4 times faster on four paths, the compile's own read unchanged,
and `json()` returns the canonical text exactly.

**Decided** by the owner on #1733, 2026-10-20: "the best, not the cheapest, with a
reference".

### How to re-open this

Level 2 of the precedence order for SQLite's documentation, level 5 for Supabase's and
PostgreSQL's. A change to SQLite's JSONB format is read against its own promise: the
format is SQLite's, and a database that holds it is read by any SQLite since 3.45.0.

## ES-7 · The engine tells Windows it is not background work

**Governs:** the Quality of Service Windows schedules the engine's process at.

**Cited at:** `scrapex/cli.py`.

### The sources

| source | what it contributes |
|---|---|
| [Microsoft Learn — SetProcessInformation, Remarks and Examples](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation) | A process that sets no `PROCESS_POWER_THROTTLING_EXECUTION_SPEED` policy has its QoS level inferred by the system's heuristics. The HighQoS example sets `ControlMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED` and `StateMask = 0`. |
| [Microsoft Learn — Quality of Service](https://learn.microsoft.com/en-us/windows/win32/procthread/quality-of-service) | A process that descends from a window-owning process takes the QoS of that window: High in focus, Low minimized or occluded. Background services are Utility. Eco always schedules to efficient cores, and Low and Utility do so on battery. A process that tags itself with `SetProcessInformation` is High. |

### What it decides

The `ui` command makes the HighQoS call on itself as it starts, before it touches a database (`_opt_out_of_eco_qos`). The panel starts the engine through the native host, so the engine descends from Chrome, and Chrome is rarely the window in focus.

Measured on his machine on 2026-10-24, on AC power (#1767). A windowless `pythonw` launched with no focused ancestor spent 4.4x the CPU-s of the same work launched under a focused one, from 6 s after it started. With the call made, it spent 1.0x. This machine throttles on AC as well, which is more than the table above promises, so the measurement decides it here and not the table. Timer resolution, priority class, memory priority and I/O priority each measured the same in every arm, so the engine sets none of them.

**Decided** by the owner on #1767, 2026-10-20, knowing it costs battery. The cost lasts as long as the engine runs, because its job worker never idles: on the copy at HighQoS it spent 0.11–0.15 CPU-s every second (#1768 lowers that). The battery cost is not yet measured.

### How to re-open this

Level 2 of the precedence order: the platform's own documentation. A QoS level Windows adds or retunes re-opens it, and so does a measured battery cost he will not pay. Either way the call is one line to remove.
