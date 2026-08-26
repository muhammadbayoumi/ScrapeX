# Plan — what remains of muqawil, after the crawl finished

**Written 2026-08-26 · `main` at `19ea359` · the evidence is
[MUQAWIL-AUDIT-2026-08-26.md](../MUQAWIL-AUDIT-2026-08-26.md)**

He asked for the remainder of the muqawil plan as steps. This is that, ordered — and the
order is argued rather than preferred.

> **THE ORDERING PRINCIPLE, so it can be disagreed with.** Four tiers, in this sequence:
> **(1) whatever has a deadline we do not control · (2) values we PUBLISH that are false ·
> (3) data the site publishes that we do not hold · (4) data we hold that he cannot
> reach.** Then verification debt. Everything in tier 2 is wrong today and stays equally
> wrong; only tier 1 gets worse while we look at something else.

## Status

| # | step | state | gate |
|---|---|---|---|
| 0 | The crawl, the workers, the storage | **DONE** | 34,834 of 34,834; 9.75 h at 1.007 s/page = 100.7% of the politeness floor; 4.40 GB in 80,676,567 bytes |
| 1 | **The poisoned profile schema** | ⛔ **his ruling** | no live row is bound to a `retired` version, and a new site field is RECORDED rather than refusing the page |
| 2 | **`R-52` re-ruled, then the State column fixed** | ⛔ **his ruling** | `absent`/`new`/`updated` computed per RUN, and a confirming pass moves `last_seen_at` on the record |
| 3 | The 263 stranded listing rows | ⛔ **his ruling** (§7-5) | all 263 on schema v2 with `profile_url` and the City/Region split |
| 4 | The two-directional gap: 148 + 81 | ⛔ **his ruling** (`REQ-41`) | one command, or automatic at end of crawl; 148 need zero network |
| 5 | The placeholder pair: map pin + `logo_url` | ⛔ **his ruling** (§7-3, §7-4) | one ruling covering both, or two explicit refusals |
| 6 | Balady Services — 886 pages, 0 rows | **not started** | `balady_services` holds a row per service per contractor, and 406 flattened records are recoverable |
| 7 | The 18,179 unreferenced Arabic snapshots | **not measured** | a decision that rests on knowing whether they carry a field the English page does not |
| 8 | **`R-19`'s query — 397,526 memberships, no surface** | **not started** | he can filter contractors by interest and by licensed activity, from the panel |
| 9 | The record card, for a contractor | **not started** | the card opens on a contractor row (`REQ-32` / `OP-57`) |
| 10 | The audit's own §8 | **debt** | the card census re-run on a random sample; products-side integrity probed |

---

## Tier 1 — the only step with a deadline we do not set

### Step 1 · The poisoned profile schema

**Why it is first and nothing else is.** Every other defect is wrong today and stays
equally wrong. This one **refuses the next page that carries a field the site has not
published before** — and muqawil sets that date, not us. The audit's own words: *"the next
new field the site publishes gets the whole page **refused** rather than recorded."*

**Measured, and re-measured independently by the primary session:**

| | |
|---|---|
| live profile rows bound to schema version **2**, marked `retired` | **17,371 of 17,371** |
| ingestions behind the **approved** version 3 | **14** — the impostor pages `OP-64` retired |
| fields the approved version declares | **39** |
| of those, empty on every live row | **12**, and all twelve are `x_*` **listing** keys |

So the published contract for `contractor_profiles` describes fourteen pages, and the
seventeen thousand real ones are bound to a version marked dead.

**His, per §7-1**, with the three options measured there. **(b) re-approve all 17,371 onto
a clean 27-field v4** is the one that also leaves a correct version history, and it needs
**no network** — every snapshot is on disk.

---

## Tier 2 — values we publish that are false

### Step 2 · Re-rule `R-52` before anything is built on it

**`R-52` is on `main` as of `19ea359`, and the evidence says its plan will not fix the
defect it was written for.** That disagreement is recorded under `C5` rather than acted on,
and the ruling stands until he moves it.

Measured read-only on the live warehouse:

| | |
|---|---|
| profile records whose `last_seen_at` is `2026-08-23` | **17,250** |
| records whose `last_seen_at` is `2026-08-24` | 121 |
| **their memberships** dated `2026-08-24` | **397,526 — all of them** |
| **records OLDER than their own memberships** | **17,259** |

The same pass refreshed a row's memberships and did not move the row's own `last_seen_at`,
because `approve_candidate` returns before the upsert when a row is merely confirmed. So
filling the sighting ledger — which is what `R-52` plans — makes those 17,250 rows compare
a 23 August timestamp against a 24 August run and read **`absent`** instead of
**`unsighted`**.

**One false state replaced by another, and the second is worse.** `unsighted` says *"stored
before the ledger existed"* — confusing, but it claims nothing about the site. `absent`
says *"the site stopped showing this"*, which is a false claim about a real contractor's
standing, on 17,250 of them.

**The root is not in the ledger at all:** a confirmation does not move `last_seen_at` on the
record. Any fix that starts from the ledger is building on a field that does not move.

**Gate:** state is computed against the RUN that wrote the row, not against
`MAX(last_seen_at)` — and a confirming pass moves the record's own `last_seen_at`. `R-52`
already gives a run an identity, which is why this is a correction to its plan and not a
replacement for it.

### Step 3 · The 263 stranded listing rows

Frozen on retired schema v1, missing six keys including `profile_url`, and **the only rows
in the table that never received the City/Region split** — so `DSN-05` is unmet for exactly
these. §7-5 prices four routes; **(c) a fresh listing crawl is 2.7 h serial or 58 min at
concurrency 4** and lands all 263 on v2 with their URLs. (a) is *refused* by
`ExtractionConflict` and writes nothing — do not spend a session discovering that.

### Step 4 · The two-directional gap — 148 and 81

`REQ-41` is his request in his own words and awaits one choice: automatic at end of crawl,
or a command. **148 of 148 need zero network requests** — their pages are on disk. The 81 in
the other direction were never searched for; see step 7.

### Step 5 · The placeholder pair — one ruling, not two

**Neither is rendered by any consumer**, so both are questions about honest metrics rather
than about anything he sees:

- **the default map pin** — `24.4493518, 46.6220053` on **14,621 of 17,371 (84.2%)**, which
  places all of Jizan and Tabuk at one point in Riyadh;
- **`logo_url`** — **100% non-empty** and **13,042 of 17,304 (75.4%)** a directory with no
  filename.

The repository has already applied *"absent rather than corrected"* to the `lng: 0` case on
19 rows. **Extending that same reasoning to both is one decision instead of two**, and it is
his because `R-45` and `CONTRACTOR-SOURCE.md:560` point opposite ways on the second.

---

## Tier 3 — data the site publishes that we do not hold

### Step 6 · Balady Services

**886 pages publish it and `balady_services` holds zero rows.** It was filed as
*not published by the site*, and that was wrong. It is currently flattened into one
comma-joined `activity` string, and **406 records cannot be split back** — so this is a
re-parse from disk, not a re-crawl. It is the fourth of `R-19`'s five groups and closes the
gap between "2 of 5 wired" and "4 of 5".

### Step 7 · The 18,179 unreferenced Arabic snapshots

Stored, referenced by nothing, and **never decoded**. `R-51` gives a concrete reason to
think the Arabic address box differs from the English one. **Measure before deciding**: this
step is a measurement whose result decides whether there is work after it, and it is also
where the 81 listing-only contractors of step 4 would be recovered from if they are
recoverable at all.

---

## Tier 4 — data we hold that he cannot reach

### Step 8 · `R-19`'s query, and it is the largest gap of all

**397,526 memberships are stored** — `interests` 389,428 over 17,371 records and 214 nodes;
`licensed_activities` 8,098 over 1,334 records and 22 nodes — and
`scrapex/taxonomy.py`'s `memberships(` is its **only** caller anywhere in `scrapex/`.
**No route, no payload column, no export tab.** The readiness level `R-45` was written about
is in there too: 52 memberships carrying `attribute_label 'مستوى الجاهزية'`.

**Build it in the extension, not on the engine's page.** `R-50` moves any capability the
extension CAN perform, and this is SELECTs over stored rows — so building it on
`/source/{key}` first would be paying twice for one feature.

### Step 9 · The record card, for a contractor

`scrapex/webui/static/grid.js` filters the row selection on `row.offer_id`, and **0 of
17,304 and 0 of 17,371 rows carry that key** — so the card `R-45` asks for opens for a
product and never for a contractor. `REQ-32` / `OP-57`. It is where every field that is not
a fixed column is supposed to live, which makes it the other half of step 8.

---

## Tier 5 — verification debt

### Step 10 · Close the audit's own §8

Two items outrank the rest of that list:

- **The card census sample is not random.** It covered 1,200 of 34,834 pages and they are
  the *first* 1,200 snapshot ids — the lowest contractor ids. `undeclared_cards` also has a
  documented blind spot for text-only cards, and a `Company Description` would be one. **So
  "the site publishes nothing we do not read" is unproven at scale.** Re-run on a random
  sample.
- **Products-side integrity was never probed.** `integrity_check` covers the file, but no
  targeted duplicate or orphan probe ran on `price_observation` (94,664), `source_offer`
  (17,543), `source_product` (9,270), `source_variant` (13,682), `change_event` (145,442) or
  `price_period` (23,569). The contractor side got six lenses; the products side got none.

**And one correction to §8 itself, measured 2026-08-26:** it says `scrapex` cannot be
imported on this machine because `scrapex/extract/models.py` imports `AnyHttpUrl` from
pydantic. **That is false** — Python 3.14.6 with pydantic 2.13.4 imports `scrapex` and runs
`python -m scrapex.cli --help` without error. The audit therefore re-implemented the
parser's logic rather than importing it, and validated that re-implementation by reproducing
stored `record_key`s and `content_hash`es exactly — so **its measurements stand and its
stated reason for taking that route does not.** Any page-level measurement after this date
imports `scrapex.extract.muqawil` instead.

---

## What this plan deliberately does NOT contain

- **The nine impossible values the site itself publishes.** `R-45`: what the site says is
  the only source of truth and we do not correct it. They are recorded in the audit's §4 and
  are not work.
- **The hidden-column export.** `scrapex/fields.py` states that a hidden column keeps
  filling and un-hiding shows a complete history, and there is deliberately no
  `delete_field()`. The export following the hidden set is a fair design question and was
  the audit's only `data-loss` claim; it did not survive measurement.
- **The eleven architecture questions** in [ENGINE-ROLE-MEASURED.md](../ENGINE-ROLE-MEASURED.md) §8.
  They are open and they change nothing in tiers 1–4 — except step 8's *where*, which
  `R-50` already answers.

## Five of the ten steps are blocked on him, and that is the plan's main finding

Steps 1 through 5 are **⛔ his ruling**, and they are the whole of tiers 1 and 2 — every
defect that publishes something false. Steps 6 through 10 can start today without him.
**So the fastest route to a correct dataset runs through five decisions, not through more
crawling**, and the crawling is finished.
