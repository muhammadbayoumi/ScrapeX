# R-19 measured — five shapes for the multi-valued contractor groups

**Written 2026-08-21, at the owner's instruction to test his own ruling before
building it:** *«ادرس حكمى اولا هل هو صحيح ام هناك الافضل ضع معايير صارمة للمراجعة
مثل الاداء والسرعة والاحترافية»* — study my ruling first, is it right or is there
something better; set strict review criteria.

**The verdict in one line: his ruling is right about the thing it decided, and it
decided only half the question.**

[R-19](archive/RULINGS.md#r-19--the-five-multi-valued-contractor-groups-go-in-child-tables-not-json)
chose child tables over JSON. Measured, JSON loses by 47× on the query he named. But
"child tables" read literally means five bespoke SQL tables, and the measurements say
the same intent is better served by machinery this warehouse **already contains and
has never used**.

R-19 also states its own evidence limit — *"The limit of this evidence, stated
plainly: one contractor"* — which is why this document exists.

---

## 1 · What the data actually is

Measured from the committed fixture `tests/fixtures/muqawil/profile-en.html`, not
from memory. The licensed-activities table holds six data rows, and each value is
**a two-level path, bilingual, in one cell**:

```
التشغيل والصيانة - مكافحة الآفات والتطهير البيئي
        Operations and Maintenance Activities - Pest Control & Environmental Disinfection
```

Three properties drive every result below, and all three are visible in one profile:

| property | consequence |
|---|---|
| **the parent repeats** — `التشغيل والصيانة` appears **3 times in one contractor's six activities** | a value repeating inside one row's data repeats across 17,283 of them |
| **the value is long** — ~120 characters, carrying both levels and both locales | storing it per row, per contractor, is the dominant cost |
| **the leaf name is not unique** — `الصرف الصحي` sits under more than one parent | an identity built from the leaf name **merges two different activities** |

**And R-19's own sample disagrees with this one.** R-19 measured membership 10001274
and reported the licensed-activities table as *"one row — the header only. Empty for
this contractor."* The committed fixture is a different contractor with **six**. So
"empty" was never general — exactly the limit R-19 flagged.

---

## 2 · The strict criteria

Set before the measurements, so a shape cannot be judged on whichever number
flattered it:

| # | criterion | why it is on the list |
|---|---|---|
| C1 | **the named query** — "which contractors operate sewage networks" | R-19 names it as the thing JSON cannot do |
| C2 | **the sheet row** — every value for one contractor | this is what the export and the profile screen need on every render |
| C3 | **the analytic** — how many contractors per value | the question that turns a directory into a market view |
| C4 | **the hierarchy roll-up** — everyone under a parent category, children included | the data is a tree; a shape that cannot walk it has lost information |
| C5 | **storage** | the warehouse is already the subject of `DEC-9` |
| C6 | **write cost** for one full load | re-extraction is from disk and will be re-run often |
| C7 | **a value gets relabelled** by the site | a directory's taxonomy is not frozen, and this is where duplication is paid for |
| C8 | **new tables and migrations** | every one is a permanent maintenance surface |
| C9 | **provenance** — can a row say which snapshot it came from | the repository's founding rule, `GENERIC-FETCH-SEAM.md` |
| C10 | **publishing** — how it reaches the Google Sheet | R-19 calls this *"the real work and it is not yet designed"* |
| C11 | **identity correctness** — can two different values collide | measured: they can, see §1 |

---

## 3 · The five shapes

| | where the rows live | how the value is stored |
|---|---|---|
| **A** | five bespoke SQL tables (R-19 read literally) | the published string, per row |
| **C** | a JSON array inside the parent's `data_json` (the overruled design) | the published string, per element |
| **D** | `classification_node` + a bespoke link table | a reference to a taxonomy node |
| **E** | a child **dataset** in `generic_record` | the published string, per row |
| **F** | a child **dataset** in `generic_record` | a reference to a taxonomy node |

**R-19 framed the choice as A-versus-C.** But "where the rows live" and "how the
value is stored" are independent axes, and the ruling only settled the first.

### The machinery that already exists, and holds zero rows

Measured against the live warehouse on 2026-08-21:

| table | what it is | rows |
|---|---|---|
| `classification_node` | a **generic self-referencing taxonomy** — `parent_node_id`, `external_id`, `node_name`, `node_name_ar`, `level` | **0** |
| `classification_scheme` | its owner, with `scheme_type = 'source'` for a site's own taxonomy | **0** |
| `dataset_relationship` | **dataset-to-dataset** parent/child, with cardinality and a review status | **0** |
| `relationship_field_pair` | field-to-field, ordered | **0** |
| `generic_record` | any dataset, `data_json`, its own schema version, and **`source_snapshot_id NOT NULL`** | 1,172 (one dataset) |

`classification_node` is the exact shape the hierarchical groups need, and nothing
has ever used it. That is the finding that produced shapes D and F.

---

## 4 · The measurements

518,490 value rows — 17,283 contractors × 30, which is R-19's own arithmetic. A
240-leaf taxonomy, each contractor holding 30 of them, so the target value is held by
**2,161 of 17,283 (12.5%)**: selective enough for an index to matter.

| | A flat table | C JSON in parent | D taxonomy + link | E child dataset | **F child dataset + taxonomy** |
|---|---|---|---|---|---|
| **C1** the named query | 25.0 ms | **1,168.3 ms** | 20.2 ms | 1.0 ms | **0.6 ms** |
| **C2** the sheet row | 0.2 ms | 0.2 ms | 0.3 ms | 0.3 ms | 0.4 ms |
| **C3** the analytic | 8,990 ms | 9,490 ms | 5,679 ms | 4,946 ms | **2,373 ms** |
| **C4** hierarchy roll-up | 612 ms, by `LIKE` | **impossible** | **543 ms, real tree** | needs `LIKE` | 1,320 ms, real tree |
| **C5** storage | 269.9 MB | 203.5 MB | **43.3 MB** | 765.4 MB | 205.7 MB |
| **C6** write, full load | 6.9 s | 4.9 s | **3.9 s** | 47.0 s | 27.5 s |
| **C7** relabel a value | 5,906 ms, **103,698 rows** | — | **0.1 ms, 1 row** | 401 ms, 2,161 rows | **0.1 ms, 1 row** |
| **C8** new tables | **5 + migrations** | 0 | 1 | **0** | **0** |
| **C9** provenance | to be built | inherited | to be built | **enforced** | **enforced** |
| **C10** publishing | new payload work | new payload work | new payload work | **one tab, exists** | **one tab, exists** |
| **C11** identity | manual | n/a | node id | **collided in test** | **node id, cannot collide** |

Three results are worth reading twice.

**C1 vindicates the ruling and then overtakes it.** JSON costs 1,168 ms against
25 ms — R-19 was right, and by a wider margin than it claimed. But the fastest shape
is not a bespoke table: it is a **partial expression index** on a child dataset,
`CREATE INDEX … ON generic_record(json_extract(data_json,'$.node_id')) WHERE
dataset_definition_id = 2`, which SQLite plans as
`SEARCH … USING INDEX ix_gr_child_node (<expr>=?)` — 0.6 ms. That is the same
mechanism whose absence made `OP-27` cost 49.7 s, applied deliberately this time.

**C7 is the criterion nobody had asked about, and it is the largest gap in the
table.** When the site relabels a category, a shape that stores the string per row
rewrites **103,698 rows in 5.9 seconds**; a shape that stores it once rewrites **one
row in 0.1 ms**. That is ~59,000×, and a live directory relabels things.

**C5 is where F pays.** 205.7 MB against the pure taxonomy's 43.3 MB, because
`generic_record` requires `record_key`, `content_hash`, `source_locator`, two
timestamps and a status on every row. **Stated honestly: production would be higher
still** — `record_key` is a SHA-256 in production and a short key in this fixture, so
add roughly 30 MB, call it ~235 MB.

### Two defects in the measurement itself, recorded because they were mine

**The first fixture had no selectivity.** It built a 30-leaf taxonomy and gave every
contractor 30 values, so every contractor held every leaf and C1 answered "all
17,283". What looked like a comparison of three queries was three ways of scanning a
whole table — and a selective lookup is the entire reason an index exists. The
storage and relabel figures survived it (they depend on row count and string length);
the query figures did not, and were re-measured.

**The identity collision was found by a crash.** Keying a child row on
`contractor:leaf_name` was refused by `UNIQUE (dataset_definition_id, record_key)`,
because leaf names repeat across branches. It failed loudly only because that
`INSERT` is not `OR IGNORE`. Behind an `INSERT OR IGNORE` the same mistake **drops
the row and reports success** — the trap `LESSONS.md` records three times over. This
is `C11`, and it is why a node id beats a string as an identity.

---

## 5 · Publishing, which R-19 correctly called undesigned

`scrapex/publish.py`'s `dataset_workbook_tables` returns **exactly one tab**, and its
docstring justifies that in so many words: *"a contractor directory has one flat
table and inventing three empty tabs beside it would be the empty tables written as
a header nobody can use"*.

**R-19 makes that sentence false.** Under any of A, D, E or F the contractor dataset
is not one flat table, and the export has to grow tabs.

Under **E or F this is nearly free**: `workbook_tables` already returns a list of
tabs for the price path, and a child dataset is a dataset — one tab each, driven by
the confirmed rows of `dataset_relationship`. Under **A or D** the export, the API,
the panel and the CLI each need bespoke work, because none of them speak "bespoke
table".

And the blast radius is small: **no test anywhere references
`dataset_workbook_tables`** (measured — `grep -rc` over `tests/` returns nothing).
That is itself worth noting as test debt, not as convenience.

---

## 6 · Recommendation

**Adopt F: a child dataset per group, whose value is a reference into
`classification_node`.**

This is a refinement of R-19, **not a reversal**. The ruling's substance — child
tables, not JSON — is upheld by every measurement. What changes is the
implementation:

| R-19 as written | recommended |
|---|---|
| five bespoke SQL tables | five child **datasets** in `generic_record` — zero migrations |
| the value is the published string | the value is a `classification_node` reference; the string is stored once |
| the payload work is undesigned | one tab per dataset, from machinery already built |
| — | `dataset_relationship` gets its first tenant after holding 0 rows |
| — | provenance is **enforced** by `source_snapshot_id NOT NULL`, not remembered |

**What it costs, stated plainly:** ~235 MB for the interests group at full scale, and
~28 s for a full re-extraction. The pure taxonomy (D) is 4.7× smaller and 7× faster
to write, and if either number is judged too high, D is the fallback — at the price
of bespoke work in the export, the API, the panel and the CLI.

**What is still unmeasured, and it is the same limit R-19 named:** one profile. The
taxonomy's real size, and how many values a typical contractor holds, come from the
profile crawl. **The recommendation does not depend on those numbers** — it depends
on the parent repeating, which one profile already proves three times over — but the
storage figures will move when they arrive.

**Not built. Awaiting his ruling**, recorded as a question in
[BACKLOG.md](archive/BACKLOG.md).

---

## 7 · Measured after the recommendation: interests are not a table

**2026-08-21, while building the reader both candidate shapes need.** This document and
the plan both assumed the five groups arrive through `detect_html_tables`. Measured
against `tests/fixtures/muqawil/profile-en.html`:

| | |
|---|---|
| `<table>` elements on the page | **5** |
| …of which are Interests | **0** |
| Interests is | a nested `<ul class="list list-numerical">` inside `div.section-card` |
| tables with no data rows for this contractor | **3** of 5 |
| names `detect_html_tables` returns | `Table 1` … `Table 5` |
| tables sharing one nearest heading | **3** |

**The recommendation is unaffected and one of its arguments is strengthened.** Shape F
turns on the parent repeating and on the leaf name not being an identity; the interests
markup shows both directly — three levels deep, and `Construction of buildings` appearing
as a level-1 node and again as a level-2 node beneath itself.

**What changes is the build.** Interests are the largest of the five and cannot be read
by the table detector at all, so a build following the old premise would have produced
four groups and missed the biggest. `read_interests` in `scrapex/extract/muqawil.py`
returns every node as a path from the root, which is the input either shape needs.

**And a naming rule is now an open sub-question.** The detector returns positional names,
and the nearest heading is shared by three of the five tables — so "which group is this"
cannot be answered from either. Whatever shape is ruled will need that rule.

**One locale trap, recorded because it nearly shipped.** Selecting the card by its
heading text read 25 nodes from English and **0 from Arabic**: the Arabic heading is
`الأنشطة` — "Activities" — not a translation of "Interests". Selection is structural now.
