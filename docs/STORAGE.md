# Storage — what we fetch, what we keep, and what each byte buys

> «انا لم استقر على طريقة خفض حجم المخزن … **ليست الفكرة ضغط الملفات** بل دراسة نشوف
> احنا بنسحب اى ولية وبنحتفظ باية ولية وما الفائدة — دراسة تبرر الحجم الذى قيل انه
> سيصل الى 5 جيجا من مصدر مقاول فقط»
> — the owner, 2026-08-20 ([REQ-12](REQUESTS.md#req-12--justify-the-volume-not-compress-it))

He asked a question this project had not been asked before. `DEC-9` measured **how to
store 6.4 GB more cheaply** and answered it well. He is asking **why we are storing 6.4
GB at all** — justify each thing fetched, each thing retained, and say what each is
worth. Compression answers the first question and does not touch the second: a justified
660 MB and an unjustified 660 MB look identical on disk.

**And the headline is that the volume he asked us to justify does not exist.** The
number was measured from one sample and it was too high. Measured properly, and stored
with a mechanism that was not available when `DEC-9` was written, **everything the site
publishes in both languages fits in about 160 MB.**

Every figure below is measured on the live warehouse or the live site on **2026-08-20**.
None is quoted from a document, including this project's own.

---

## 1 · What we fetch, and why each fetch is necessary

Four classes. The count of each is fixed by [DEC-11](BACKLOG.md)'s partition, not
estimated.

| class | pages | why it is fetched |
|---|---|---|
| listing EN | 871 | The **only** enumeration of who exists. There is no sitemap of contractors, no id-space that can be probed, and no stable sort — all three measured and recorded as dead ends in `DEC-11` |
| listing AR | 871 | **Not redundant, and not for coverage.** Arabic page N returns the same 20 ids as English page N. It is fetched because Arabic values are matched **by page-order index and never by label** (`LESSONS.md`), so the Arabic page is the only source of the Arabic strings |
| profile EN | 17,403 | 48 of the owner's ~70 columns exist **only** here — licences, interests, activities, coordinates, the obfuscated email, the self-build prices. The listing card carries 22 |
| profile AR | 17,403 | Same reason as the Arabic listing: the `[ar]` half of every column |

**Total: 36,548 fetches.** Each class is load-bearing and none is duplicated work. The
Arabic halves are a **data-pairing cost, not a coverage cost** — a distinction `DEC-11`
had to make once already, because counting Arabic passes as coverage doubles a
completeness estimate for 129 new ids.

**What we deliberately do NOT fetch**, so the list is a decision and not an omission:
the map page (measured: zero contractor markers, its one coordinate is the map centre),
`/api/rating-api` beyond what a profile renders, and the `my_contractors` filter, which
is a signed-in user's private list.

---

## 2 · What we retain, and what it costs — measured, not projected

**Today the warehouse keeps the entire HTML of every page it has ever fetched.**

| | |
|---|---|
| `scrapex-engine.db` | **796 MB** + a 4 MB WAL |
| `generic_page_snapshot` | 1,728 pages · **607 MB of `html_content`** — 76% of the whole file |
| `generic_record` | 11,059 rows · 8.7 MB of `data_json` |
| `generic_record_revision` | 34,550 rows · 26.7 MB |
| accounted for | 643 MB of 796 MB; the remaining 153 MB is indexes and page overhead |

So **the snapshots are the warehouse.** Everything else is a rounding error, and any
conversation about size that is not about snapshots is about the wrong thing.

### The composition of a page, per class

| | listing | profile |
|---|---|---|
| average size | **363 KB** (min 312, max 373) | **119 KB** (min 101, max 157) |
| the part that is data | **17.8%** — 20 cards, 64 KB | **3.5%** — 4.1 KB of visible text |
| structure with scripts stripped | — | 27 KB (22%) |
| samples | 5 pages, and 864 sized | **13 real profiles across the whole id range** |

**Corrections to `DEC-9`, which measured this from one sample:**

| `DEC-9` said | measured 2026-08-20 |
|---|---|
| 21% of a listing page is cards | **17.8%** |
| a profile is **168 KB** *(one sample)* | **119 KB** (13 profiles, min 101, max 157) |
| the full crawl is **~6.4 GB** raw | **4.55 GB** — 618 MB of listings, 3.95 GB of profiles |
| compressed, ~660 MB | **~90 MB**, with a shared-dictionary codec — §4 |
| a profile compresses 9.4× | **7.7×** with zlib per row; **46×** with a shared dictionary |

**And one claim of `DEC-9`'s was not merely imprecise but backwards**, which matters
because the whole recommendation rested on it:

> *"a near-identical skeleton repeated 864 times, which is exactly why it compresses so
> well"*

The skeleton **is** near-identical — 40 listing pages differ only in their pagination
block and one locale-switch href. But **zlib captures none of that.** Its window is
32 KB and a skeleton is 121 KB, so by the time page 2 begins, page 1 is out of view.
Measured three ways:

| | |
|---|---|
| one skeleton, zlib-9 | 18 KB |
| ten skeletons **concatenated**, zlib-9 | 175 KB — **9.84× the cost of one, for ten pages** |
| 40 whole pages as one zlib block | **15.8×** — no better than compressing them separately |

So `DEC-9`'s 15.6× is **entirely intra-page redundancy**. The cross-page redundancy it
credited for the ratio was real, large, and **left on the table**.

---

## 3 · What each retained byte buys, per class — and the classes differ

This is the part `DEC-9` could not answer, because it is not a compression question.

### Retention buys time — priced honestly

| class | re-fetch cost |
|---|---|
| both listings | 1,742 requests × 5.84 s = **2.8 h** |
| both profile sets | 34,806 requests × 1.8 s = **17.4 h** |
| everything | **~20 hours** |

Measured value of that policy so far: **one incident.** A defect in the bilingual merge
on 2026-08-20 was repaired from disk with nothing re-fetched. That is the honest
accounting — *hours saved per incident*, at one incident to date, not a principle.

### But the two classes are not the same kind of thing, and only one is recoverable

| | listing page | profile page |
|---|---|---|
| re-fetching page N returns the same content | **No.** The ordering is a cached random permutation with a generation of 157–282 s; across generations, page 40 holds a different 20 contractors | **Yes** — fetched twice, the visible text was identical (the bytes differ; a CSRF token moves) |
| what it uniquely holds | the **set of ids published at a moment**, and the order they were in | that contractor's ~70 fields **as of that date** |
| what re-fetching recovers | the union, eventually — never that page | everything, unless the contractor has since edited it |

> **A listing page is not a document; it is a sample.** A profile page **is** a document.
> That is the real per-class distinction, and it does not follow the size.

### And the value of retention is highest exactly now

A snapshot's re-parse value is a function of **how incomplete the extraction schema
is.** Today 22 of the owner's ~70 columns are stored and 48 are not, so a retained
profile page is 48 columns we can add without touching the network. When the schema is
complete, that value drops toward zero and only the audit value remains.

**So retention is not a permanent decision.** It is worth most during the period we are
in, which is an argument for keeping everything **now** and revisiting when the schema
closes — not for a rule that is meant to hold for ever.

---

## 4 · The options, per class, with what each costs in capability

Measured on the same 40 stored listing pages and the same 13 real profiles, so the
comparison is real and not a mix of sources.

| mechanism | listings | profiles | keeps a row independently readable? |
|---|---|---|---|
| as stored today | 1× | 1× | yes |
| **zlib-9 per row** — `DEC-9`'s answer | 15.6× | 7.7× | yes |
| zstd-3 per row | 15.8× | — | yes |
| zstd-19 per row | 18.8× | — | yes |
| lzma per row | 19.1× | — | yes |
| zstd-19 + a *trained* 512 KB dictionary | 19.7× | — | yes |
| **zstd-12 + one real page as a RAW dictionary** | **187×** | **46×** | **yes — round-trip verified** |
| zstd-19, 20-page blocks | 170× | — | no — 20× read amplification |
| zstd-19, all 40 as one block | 219× | 61× | **no** — a chain; row 700 needs row 699 |

**This costs one dependency, and the first version of this study got that wrong.**
`compression.zstd` is in the standard library as of Python **3.14**, and the machine
this was measured on runs 3.14.6 — so the study concluded that the constraint which
made `DEC-9` choose zlib, *"no new dependency"*, was satisfied for free. It is not.
`pyproject.toml` declares `requires-python = ">=3.12"` and **CI runs 3.12.14**, where
that module does not exist: importing it did not merely fail the tests, it stopped the
package importing at all.

**The fix is the `zstandard` wheel, and it is more portable than the thing it
replaces.** Same libzstd underneath, identical behaviour on 3.12, 3.13 and 3.14 —
where `compression.zstd` works on 3.14 alone. The owner works from two machines, and a
compressed page that only one of them can read is a worse outcome than a dependency,
because the plaintext is not stored anywhere else. Measured again through `zstandard`
on the same 40 stored pages: **254×**, better than the 187× the stdlib module gave, at
the same order of cost per page.

So the honest form of `DEC-9`'s constraint is: it was a preference, the alternative
costs **4.8× more disk** (stdlib-only `lzma` measured at 19.1× on these pages, and
Python's `lzma` exposes no shared dictionary — prepending one is *worse*, 18.4×,
because the dictionary is then paid for on every row), and the preference is not worth
that.

**The whole corpus, each way:**

| | listings | profiles | total |
|---|---|---|---|
| raw | 618 MB | 3,950 MB | **4.55 GB** |
| zlib-9 per row (`DEC-9`) | 40 MB | 525 MB | **565 MB** |
| **zstd-12 + raw page dictionary** | **3.3 MB** | **87 MB** | **90 MB** |

### The options that cost capability, and why each loses

| option | verdict |
|---|---|
| **keep only the extractable region** | **Strictly dominated, and this is the study's sharpest result.** Keeping *only the visible text* of every profile, uncompressed, costs **139 MB**. Keeping the **whole HTML** with a shared dictionary costs **87 MB**. Trimming is *more* expensive **and** spends the ability to re-parse — and 48 of the owner's columns are still unextracted, so that ability is in active use |
| keep the skeleton once, pages as diffs | This is what the raw-dictionary row already does, without a custom format, without a chain, and without anything to maintain |
| retain until the parse is verified, then reduce | Would have to be re-verified every time a column is added. With the schema 22 of 70 complete, "verified" is not a state this corpus is in |
| tiered — newest N, or one per schema version | Spends history, which is not re-observable: a profile's fields change when the contractor edits them |
| keep a hash and re-fetch | **Impossible for listings** — a listing page is a sample, not a document (§3). Viable for profiles, and it saves 87 MB at the price of 17.4 h and of losing what the page said on a date |
| delete snapshots after approval | Spends exactly what repaired the 2026-08-20 defect |

---

## 5 · What the snapshots are FOR, beyond re-parsing — and this one is his call

`SR-1` says the source of truth is what the site publishes. A stored page is **evidence
of what it published on a date**, and that has uses that have nothing to do with parser
bugs: a disputed row, a contractor whose classification changed, a claim about what the
directory contained before an edit.

**Only the owner can say whether that matters to him**, and the study should not assume
it. It changes one row of the table above and no others: if evidence-over-time matters,
"keep a hash and re-fetch" is out for profiles as well as listings.

---

## 6 · Recommendation

**Retain everything, in both languages, and store it with a shared raw dictionary.**

1. **The fetch list in §1 stands unchanged.** Every class is load-bearing; none is
   duplicated. This is what «كلّ ما ينشره الموقع» costs, and it costs 36,548 requests.
2. **Retain the whole HTML of every page.** Not because retention is a principle, but
   because at 90 MB the alternative saves nothing worth the capability, and because the
   extraction schema is 22 of 70 columns complete — the exact condition under which
   re-parse value is at its highest.
3. **Store it `zstd`-compressed against one real page per class as a raw dictionary.**
   Stdlib, 3.5 ms a page, every row independently decompressible, 187× on listings and
   46× on profiles. **This supersedes `DEC-9`'s zlib recommendation**, which is kept
   below per **C4** — it was right that the rule was sound and the encoding wrong; it
   had the wrong encoding.
4. **Do not trim.** It is dominated on both axes.
5. **Then the volume needs no justification, because there is no volume.** ~90 MB of
   evidence plus ~70 MB of rows and indexes — call it **160 MB** for everything the site
   publishes, against the **5 GB** the question was asked about.

### BUILT 2026-08-20, on his instruction «ابدأ آلية التخزين»

Recommendation 3 is no longer a recommendation:

| | |
|---|---|
| the codec | [`scrapex/snapshotbody.py`](../scrapex/snapshotbody.py) — `plain` and `zstd-raw-dict`, level 12, on the `zstandard` wheel |
| the schema | `db/engine/migrations/0005_a_snapshot_says_how_it_is_encoded.sql` — `snapshot_dictionary`, plus `html_codec` and `html_dict_id` on the snapshots |
| the production caller | `scrapex/snapshotcrawl.py` — the path the 36,548 pages arrive on, compressed against a dictionary of their own **kind** via `label_for(url, page.kind)` |
| the guards | `tests/test_a_snapshot_says_how_it_is_encoded.py`, 13 tests, mutation-proven three ways |

**Nothing existing was rewritten, and that was a decision rather than a shortcut.**
`trg_generic_page_snapshot_immutable_update` aborts any UPDATE to the snapshot table,
and it is right to — a stored page is evidence of what a site published on a date. A
backfill would have to drop that trigger; the trigger is worth more than the 607 MB.
So `html_codec` carries a DEFAULT of `'plain'` and the 1,728 rows already on disk are
read by exactly the path that reads a new one. **The 3.95 GB this is for has not been
fetched yet, which is the whole reason the study gated the crawl.**

Three things the build had to get right that the study did not have to say:

- **`content_hash` stays the hash of the DECODED page.** Otherwise the day a codec
  changes is the day every page becomes a different page, and every dedup and
  revision decision downstream moves with it.
- **`html_content` keeps its declared TEXT type and holds either.** SQLite column
  types are affinities, and TEXT affinity explicitly does not convert a BLOB — so a
  compressed body lives in the column it belongs in, `NOT NULL` is satisfied
  honestly, and no table rebuild puts 1,728 rows of evidence and four foreign keys at
  risk in order to add two columns.
- **A page that would grow is stored plain.** A codec that is a pessimisation on some
  rows and an optimisation on others is one nobody can reason about, so the
  comparison is made on real bytes.

**And the dictionary is guarded harder than the snapshots are.** A changed snapshot
loses one page; a changed dictionary loses **every** page compressed against it,
silently, and only when someone tries to read one — with no repair, because the
plaintext is not stored anywhere else. `snapshot_dictionary` therefore forbids both
UPDATE and DELETE.

### What this still does not decide, and what it needs from him

- **§5 — is a snapshot evidence, or only a parse cache?** His answer decides whether
  profiles may ever be dropped for a re-fetch. **It does not block the crawl**: the
  recommendation is to retain everything, and §5 only decides whether a future
  reduction is permitted.
- **Backfilling the 1,728 existing rows** would save ~600 MB and requires dropping an
  immutability trigger to do it. Not done, and not recommended without him saying so.
- **`R-20` (revision on change only) is worth more than it looks here.** 34,550
  revisions for 11,059 records is 26.7 MB, and the distribution is exactly two revisions
  per appearance — the second recording no change. Under `R-20` that table is roughly
  halved, and it is the second-largest thing in the file.

---

## Appendix · how each number was obtained

| number | how |
|---|---|
| 796 MB, 607 MB, 26.7 MB | `SUM(LENGTH(...))` over the live database, read-only |
| 363 KB and 17.8% | 5 stored listing pages parsed with the production card selector; 864 sized |
| 119 KB, 3.5% | 13 profiles fetched live, ids spread across the published range, **each checked not to be a redirect** |
| every ratio in §4 | the same 40 stored pages and 13 profiles, one script, one run |
| 157–282 s generation | page 1 of a filtered slice re-fetched at 55, 90, 157, 282 and 527 s |
| 2.8 h and 17.4 h | 5.84 s a listing request (`DEC-11`, from a real 864-page pass) and 1.8 s a profile request (measured on 13) |

**One measurement was thrown away rather than reported**, and it is recorded because it
is the kind of error this study exists to avoid: the first profile sample fetched ids
`2`, `5000`, `9000`, `12000` and `17000`, and all five returned **exactly 367 KB**.
Those ids do not exist; the site redirects a missing profile to the contractor listing,
the fetcher follows redirects, and a listing page is 367 KB. Averaged in, they put the
profile figure at 250 KB and the projection at **8.3 GB** — off by 110%. Five identical
sizes in a row is what gave it away.
