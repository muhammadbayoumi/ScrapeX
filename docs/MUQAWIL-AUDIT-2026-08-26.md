# muqawil — the audit, measured after the crawl finished

> **READ THE BASE BEFORE THE FINDINGS. This was measured against `5722b6f`, which is the
> tip of `docs/two-counts-and-the-gap-between-them` (PR #267) — NOT `main`.** The measuring
> session said so itself and chose that tree deliberately, because it is the code the owner
> has installed and the code that wrote the warehouse. `origin/main` at the time of filing
> was `99a32fa` and contains **neither `OP-68` nor `R-52`**.
>
> So: **check any `file:line` below with `git show 5722b6f:<path>`, never against `HEAD`.**
> A citation that does not resolve on `main` has not rotted — it is a reading of a tree that
> is still there.
>
> **It is deliberately outside `tests/test_the_documents_cite_what_they_claim.py`'s
> `DOCUMENTS`, for the same reason `ENGINE-ROLE-MEASURED.md` is:** a guard re-deriving these
> against `HEAD` would report hundreds of false failures and teach the next session that the
> guard is noise. **A known gap, named, beats a guard pointed at the wrong tree.**
>
> **Thirty-two agents across six passes**, every defect put to an independent refutation
> pass. **Fifteen claims were refuted and are not listed as defects** — they are in §5, so
> the calibration is visible rather than implied.
>
> **The warehouse was opened read-only throughout** (`?mode=ro`), nothing was written, no
> migration ran, and port 8000 was not touched.

### Four numbers from this document that the primary session re-measured independently

Different queries, same warehouse, arrived at without reading the lens that produced them:

| claim | independent re-measurement |
|---|---|
| the default map pin stored as each contractor's location | **14,621 of 17,371 (84.2%)** share `24.4493518, 46.6220053` exactly |
| the approved profile schema declares fields no row carries | **12 of 39** empty on **17,371 of 17,371** — and all twelve are `x_*` listing keys |
| every live profile row bound to a retired schema version | **17,371** on version 2 (`retired`); the approved version 3 has **14** ingestions behind it |
| the declared `one_to_one` is broken | **229** ids on one side only — 81 listed with no profile, 148 profiled and not listed, union **17,452** |

**And one claim the primary refuted by reading the module's own docstring:** that hiding a
column loses data. `scrapex/fields.py` states the opposite — *"a hidden column keeps filling
up so un-hiding it later shows a complete history, not a gap"*, and there is deliberately no
`delete_field()`. The export does follow the hidden set (`scrapex/reports.py:2183`), which is
a real surprise and a fair design question, but it is **not** data loss. It was the only
`data-loss` claim in the whole audit and it did not survive.

---

**Measured 2026-08-26 against commit `5722b6f`** (main checkout `C:/Users/User01/source/repos/ScrapeX`, branch `docs/two-counts-and-the-gap-between-them`; `origin/main` is `99a32fa` and contains **neither** `OP-68` nor `R-52`). Warehouse read **read-only only** (`file:C:/Users/User01/.scrapex/engine/scrapex-engine.db?mode=ro`), 1,305,468,928 bytes, `PRAGMA freelist_count = 0`, `user_version = 10`, newest migration `0010_a_membership_carries_what_the_site_said_about_it.sql`. Nothing was written, no migration ran, port 8000 was not touched by this pass. Every `file:line` below is a **main-checkout** path at `5722b6f`.

Six independent passes ran (five lenses plus a completeness critic). Every defect was put to a refutation pass; **15 claims were refuted and do not appear as defects below** — they are in §5 so you can calibrate how much to trust the rest.

---

## 1 · Are there problems?

Yes — **28 confirmed defects: 11 that publish a false value, 7 that withhold data the site does publish, 10 declared debt** — and separately **9 classes of impossible-but-genuine values the site itself publishes**, which under `R-45` are not our bugs and are listed apart. The crawl itself is sound and better than promised: **34,834 of 34,834 pages**, both locales at exactly 17,417 each, `2026-08-22T10:27:32Z → 2026-08-23T13:43:52Z`, zero fetch failures, zero decode failures, 80,676,567 bytes stored for 4.40 GB of HTML. **The single worst defect is the `State` column: 34,364 of 34,689 published rows (99.06%) carry a sentence that is false** — 16,993 contractors read *"The most recent crawl did not show this row"* about a crawl that read all of them, and all 17,371 profiles read *"Stored before the sighting ledger existed"* about rows first written 2026-08-22. It is already registered (`OP-68`) and already ruled (`R-52`) — and this audit's new finding is that **the ruled fix will not fix it**: `approve_candidate` returns before the upsert when a row is merely confirmed (`scrapex/extract/service.py:503-511`), so 17,264 records still say `last_seen_at = 2026-08-23` while all 397,526 of their memberships say `2026-08-24`; filling the sighting ledger as `R-52` plans flips those 17,264 rows from one false state (`unsighted`) to another (`absent`). The largest **unregistered** defect is second: the 14 impostor rows `OP-64` retired had already poisoned the schema before they were retired, and the currently **approved** profile schema is theirs — 39 fields of which 12 are empty on 17,371 of 17,371 live rows, with every live row bound to a version marked `retired`, and the next new field the site publishes gets the whole page **refused** rather than recorded.

---

## 2 · Is the muqawil plan finished?

| deliverable | state | evidence |
|---|---|---|
| **Step 1 · workers for `--details`** | **done** | `scrapex/contractors.py:611-635` (`ThreadPoolExecutor`, per-worker `connect()`, results read in frontier order). Active crawl time 35,092 s = **9.75 h at 1.007 s/page**; the politeness floor at `--pace 1.0` (`contractors.py:1338`) for 34,834 requests is 9.676 h, so the run came in at **100.7% of the floor** — the latency is fully hidden and no further worker can shorten a re-crawl |
| **Step 2 · the profile crawl, 34,834 pages** | **done** | run-ref `profiles-2026-08-22`: 34,834 rows, 34,834 distinct `source_url`, 17,417 `/ar/` + 17,417 `/en/`, `min captured_at 2026-08-22T10:27:32Z`, `max 2026-08-23T13:43:52Z`, all `html_codec='zstd-raw-dict'`. Wall 27.27 h of which 17.52 h was three idle gaps — the resume worked |
| **DEC-9 · the storage mechanism** | **done** | 34,834 pages in 80,676,567 bytes (76.9 MiB) against a projected ~87 MB. Corpus-wide: 36,358 profile pages, 4,402,991,594 raw → 85,275,180 stored = **51.6×** against 46× claimed |
| **Step 3 · the profile parser** | **partly done** | 27 profile keys present on 17,371 of 17,371 rows and 28 listing keys on 17,304 — **54 distinct site keys live**. Every profile field's fill matches what the stored pages publish to within 8 records (§3). Not finished: Balady's 8 services are flattened into `activity`; 105 of 1,497 published addresses are absent; `map_location_url` (`docs/CONTRACTOR-SOURCE.md:562`) is unbuilt and the site publishes a real map URL on **1 of 17,417** pages, so the resolution is a doc correction and not a build |
| **his ~70 specified columns** | **partly done** | 9 of the specified columns are measured **not published by the site** and `docs/CONTRACTOR-SOURCE.md:640` already says so («Nine specified columns therefore have no public source»): the five detail-rating scores, `Customer Rating Grade` ±ar, `Company Description` ±ar. Four Technical-Rating columns: `contractor-tab4` holds zero tables on 2,360 of 2,360 pages. `Qualification Programs` and `Balady Services` were filed as absent — **Balady is on 886 pages** (defect 15) |
| **Step 4 · `R-19`'s five multi-valued groups** | **2 of 5 wired** | `generic_record_node` = 397,526 memberships: `interests` 389,428 over 17,371 records / 214 nodes; `licensed_activities` 8,098 over 1,334 records / 22 nodes. `contract_counts` correctly demoted to two columns (`model_contract_count`, `registered_contract_count`, 205 rows each). `main_contractors` / `sub_contractors` measured empty and the full population agrees — `card_main_contractor='1'` on **2 of 17,304** and `card_sub_contractor` non-zero on **6** — so 8 relations exist in the whole directory. `balady_services` holds **0** rows against 886 pages that publish it |
| **`R-19`'s query, reachable** | **not started** | `scrapex/taxonomy.py:198 memberships(` is the only match for `memberships(` in all of `scrapex/`, and `generic_record_node` is referenced in exactly one production file. No route, no payload column, no export tab |
| **DEC-10 / `R-40` · row-aware idempotency** | **done for its case** | `scrapex/extract/service.py:259-288` and the gate at `:503-511`. It permits a re-parse whose **field set is unchanged**; `:481-489` refuses one that adds columns, which is exactly what the 263 stranded rows need |
| **DSN-05 · split City / Region** | **partly done** | Exact where it ran: **15,577 of 15,577** non-empty `card_city_region` values partition on `' - '` back to precisely `(card_city, card_region)`, 0 anomalies. Absent as a **key** on 263 rows, 252 of which hold a splittable string |
| **DSN-04 · the URL columns** | **partly done** | `profile_url` / `_ar` non-empty on 17,041 of 17,041 where present, absent as a key on 263. `contract_request_url` correctly earns no column; what replaced it, `commercial_registration`, is 100% populated |
| **`R-45` · a field is not a column** | **partly done** | The readiness level **is** stored — 52 memberships, `attribute_label 'مستوى الجاهزية'`, values Basic 20 / Gold 15 / Silver 10 / Dimond 7 — and is not a column. But the card it must live in never opens for a contractor: `scrapex/webui/static/grid.js:1870` filters the selection on `row.offer_id`, and 0 of 17,304 and 0 of 17,385 rows carry that key. That is `REQ-32` / `OP-57`, open |
| **`R-47` · one card, two crawls** | **partly done** | The two `dataset_definition` rows stay two. But `dataset_relationship.evidence_json` still reads `"704 profile rows, 704 distinct contractor_id"` (updated 2026-08-22T10:46:07Z) against 17,371 today, and the card's freshness line is 47 h stale |
| **`R-52` · a generic crawl is a run** | **not started** | `user_version = 10`, newest migration `0010`, `dataset_sighting` has no `last_run_ref`, `crawl_run`'s 160 rows carry `source_id` / `products_discovered` and no dataset column. `docs/plans/2026-08-24-a-generic-crawl-is-a-run.md` exists as a plan |
| **`OP-68` · an honest `State` column** | **not started** | 34,364 of 34,689 rows false (defect 1) |
| **Undo the impostor schema damage** | **not started, and in no register** | `OP-64`'s "What it needs" asks only for the rows, and the rows were done. `docs/RULINGS.md:2370` claims the non-decision half «now rests on the sighting ledger's own `last_absent_at`»; `scrapex/sightings.py:398` still reads `if last_seen_at is None or last_seen_at < newest: return STATE_ABSENT`, and `last_absent_at` is NULL on all 17,417 sightings |
| **Retention for the contractor data** | **not started** | `grep -c`: `scrapex/retention.py` → `price_observation` 16, `generic_record` 0, `generic_page_snapshot` 0; `scrapex/compaction.py` → 7 / 0 / 0. `retention_run` 0 rows; `retention_policy` one row `('*', 3650, 'keep_all')` |
| **`Q-18` · the two relation groups** | **his ruling, none exists** | 8 relations in 17,304 contractors is now the number to rule on, measured at full population instead of 2,419 pages |
| **`STORAGE.md` §5 and `O-2`** | **his ruling, none exists** | §5 is now concrete: 1,728 pre-codec snapshots hold **636,779,275 bytes = 48.8% of the file** |
| **A path from the panel to muqawil** | **not started** | outside this audit's scope; not re-measured |

**What is genuinely left:** the collection is finished and provably complete at the page level — what remains is (a) undoing the schema damage the 14 impostor pages caused, (b) making the `State` column true, which needs one more fix than `R-52` plans, (c) giving the 397,526 memberships a read path, and (d) four decisions that are yours (§7); everything else on the list is either done, correctly closed by measurement, or debt that costs nothing today.

---

## 3 · The data, measured

### Population

| | count |
|---|---|
| `generic_page_snapshot` total | **57,041** — `zstd-raw-dict` 55,313 rows / 284,736,903 B; `plain` 1,728 rows / **636,779,275 B** |
| run `profiles-2026-08-22` | **34,834** snapshots, 34,834 distinct URLs, `ar` 17,417 + `en` 17,417, 80,676,567 B |
| `generic_record` · `contractors` | **17,304 active** — 263 on schema v1 (**retired**), 17,041 on v2 (**approved**) |
| `generic_record` · `contractor_profiles` | **17,371 active + 14 retired** — all 17,371 active rows on schema v2 (**retired**); the 14 retired rows are the only holders of v3 (**approved**) |
| rows the table publishes (no status filter, `R-27`, `service.py:906`) | contractors **17,304** · contractor_profiles **17,385** |
| `generic_ingestion` | dataset 1 → 3,883 · dataset 2 → **18,089** (`2026-08-22T07:20:55Z` … `2026-08-24T11:47:30Z`) |
| `generic_record_revision` | contractors **52,439** · profiles **18,089** |
| `generic_record_node` | **397,526** — `interests` 389,428 / 17,371 records / 214 nodes; `licensed_activities` 8,098 / 1,334 records / 22 nodes |
| `classification_node` / `classification_scheme` | 243 / 2 |
| `dataset_sighting` | `contractors` **17,417** · `contractor_profiles` **0** |
| the two datasets joined on `contractor_id` | both **17,223** · listing-only **81** · profile-only **148** · **union 17,452** |
| distinct contractor ids with a profile-URL snapshot on disk | **17,452** — the union, to the row |
| `crawl_run` / `crawl_job` rows for either contractor dataset | **0** / **0** |

### `contractor_profiles` — every field, 17,371 active rows

All 27 keys are present on all 17,371 rows; nothing is absent. The "site publishes" column was measured by decoding the 17,417 stored English snapshots of the run and counting `div.info-name` / `div.info-value` pairs (17,378 real profiles, 39 impostor pages).

| field | filled | fill % | distinct | site publishes | verdict |
|---|---:|---:|---:|---:|---|
| `contractor_id` | 17,371 | 100.00 | 17,371 | — | unique |
| `membership_number` | 17,371 | 100.00 | **17,371** | 17,378 | unique on active rows; agrees with the listing card on 17,223 of 17,223 |
| `membership_type` / `_ar` | 17,371 | 100.00 | 3 / 3 | 17,378 | Saudi 15,714 / Non-Saudi 1,638 / Affiliate-Organization 19 |
| `is_saudi_contractor` | 17,371 | 100.00 | 2 | derived | **defect 7** — `true` on all 19 Affiliate rows |
| `member_since` | 17,371 | 100.00 | 2,215 | 17,378 | `YYYY/MM/DD` on 17,371 of 17,371; min 2018/08/25, max 2026/08/21; 0 in the future |
| `company_size` / `_ar` | 17,371 | 100.00 | 4 / 4 | 17,378 | clean |
| `training_credit_hours` / `_ar` | 17,371 | 100.00 | 160 / 160 | 17,378 | **numeric on 0 of 17,371** — the unit is inside the value; `'0 h'` on 16,635 (**defect 19**) |
| `organization_email` | 17,371 | 100.00 | 17,347 | 17,378 | decoded from `data-cfemail`; `'@'` on 17,371; 0 literal `[email protected]`; 0 `@muqawil.org`; 1 site typo |
| `commercial_registration` | 17,371 | 100.00 | **17,342** | 17,378 | 29 values shared by 58 rows; 10 digits on 17,369, 11 on 1, 12 on 1 |
| `latitude` / `longitude` | 17,352 | 99.89 | 2,650 / 2,641 | 17,378 | **defect 4** — 14,621 hold the site's default pin; true coverage 2,731 = **15.72%** |
| `city` / `city_ar` | 15,891 | 91.48 | 308 / 304 | 15,898 | correct — the shortfall is the site's |
| `region` / `region_ar` | 15,891 | 91.48 | 13 / 13 | 15,898 | correct |
| `organization_mobile_number` | 5,791 | 33.34 | 5,542 | 5,799 | correct; 984 match no plausible SA shape (**the site's**) |
| `address` | 1,392 | 8.01 | 1,350 | **1,497** | **defect 16** — 105 absent (97 NULL + 8 whole records); 13 carry `email protected` (**defect 8**) |
| `activity` / `_ar` | 885 | 5.09 | 318 / 328 | 886 | **defect 15** — this is Balady Services, 8 values, stored as one delimited string; trailing `' ,'` on 885 of 885 |
| `self_build_price_under_five_projects` | 294 | 1.69 | 70 | 295 | correct — 1,105 contractors are in the programme and have not priced it |
| `self_build_price_five_to_ten_projects` | 293 | 1.69 | 80 | 294 | correct; max 522,625,231 (**the site's**) |
| `self_build_price_over_ten_projects` | 293 | 1.69 | 76 | 294 | correct |
| `model_contract_count` | 205 | 1.18 | 19 | 205 | correct |
| `registered_contract_count` | 205 | 1.18 | 26 | 205 | correct |
| **not a field: `x_city_region`, `x_city_region_ar`, `x_status`, `x_status_ar`, `x_main_contractor`, `x_sub_contractor`, `x_unclassified`, `x_first`/`x_second`/`x_fourth`/`x_fifth`/`x_sixth_classified`** | **0** | **0.00** | — | 0 real pages | **defect 2** — 12 phantom columns served by `dataset_schema_fields` and written into the workbook |

### `contractors` (the listing) — every field, 17,304 active rows

| field | present | filled | fill % | distinct | verdict |
|---|---:|---:|---:|---:|---|
| `contractor_id` | 17,304 | 17,304 | 100.00 | 17,304 | unique |
| `card_membership_number` | 17,304 | 17,304 | 100.00 | 17,304 | unique, none blank |
| `company_name` | 17,304 | 17,304 | 100.00 | 17,179 | 3 rows are the literal `[email protected]` (**defect 8**) |
| `company_name_ar` | 17,304 | 17,077 | 98.69 | 16,995 | 227 EN-only — the site reordered its listing between the two requests (§5) |
| `logo_url` | 17,304 | 17,304 | 100.00 | 4,263 | **defect 20** — bare directory on 13,042 (75.37%), a raw space on 2,743; **15,785 of 17,304 (91.2%) unusable as a URL**; `default.jpg` on **0** |
| `card_status` / `_ar` | 17,304 | 17,304 / 17,107 | 100.00 / 98.86 | **1 / 1** | one value, `Account Verified`, on every row |
| `card_company_size` / `_ar` | 17,304 | 17,304 / 17,107 | 100.00 / 98.86 | 4 / 4 | clean |
| `card_training_credit_hours` / `_ar` | 17,304 | 17,304 / 17,107 | 100.00 / 98.86 | 160 / 159 | numeric on **0 of 17,304** |
| `card_main_contractor` | 17,304 | 17,304 | 100.00 | 2 | `'1'` on **2** rows |
| `card_sub_contractor` | 17,304 | 17,304 | 100.00 | 3 | non-zero on **6** rows |
| `contractor_classification` / `_ar` | 17,304 | 17,303 / 17,106 | 99.99 / 98.86 | 7 / 7 | `Unclassified` on 11,905 (68.8%); exactly 1 row empty |
| `contractor_classification_grade` | 17,304 | 8,238 | 47.61 | 8 | the site publishes a grade on 8,237 cards — **correct**. `''` on 9,066 and `'0'` on 2,839 under the same label; `2147483647` on 1 (**the site's**) |
| `card_city_region` / `_ar` | 17,304 | 15,829 / 15,647 | 91.48 / 90.42 | 313 / 309 | 1,475 rows have no location at all — `region_id=0`, **the site's** |
| `card_city` / `card_region` | **17,041** | 15,577 | 90.02 | 302 / 13 | **absent as a key on 263** (**defect 12**); where present, 15,577 of 15,577 splits exact |
| `card_city_ar` / `card_region_ar` | **17,041** | 15,402 | 89.01 | 295 / 13 | absent as a key on 263 |
| `profile_url` / `_ar` | **17,041** | 17,041 | 98.48 | 17,041 | **absent as a key on 263, with no fallback anywhere in the row** |
| `membership_level` / `_ar` | 17,304 | 18 | 0.10 | 3 / 3 | the site sets `data-membership-text` on exactly **18 of 17,296** cards — **correct, not our defect** |
| `customer_rating_score` / `_count` | 17,304 | 17 | 0.10 | 7 / 5 | exactly **17 of 17,296** cards carry a rating — **correct** |

**Reading of the two tables:** of 54 distinct site keys, **not one is empty on every row**, and every low fill rate on the profile side matches what the site publishes to within 8 records. The columns that are empty and should not be are the **12 `x_*` phantoms** (0 of 17,371) and the **6 keys missing from 263 listing rows**.

---

## 4 · Confirmed defects, worst first

### A · Published values that state something false — 11

**1 · The `State` column is false on 34,364 of 34,689 published rows (99.06%), and the ruled fix will replace one false state with another.** *Ours.*
Reproduced by re-implementing `sightings.row_state` exactly: `contractors` → `absent` 17,221, `unsighted` 35, `confirmed` 48 of 17,304, with `newest = MAX(last_seen_at) = 2026-08-22T07:39:56Z` and **1,034 distinct `last_seen_at` values** across a crawl written over 17 minutes; of the 17,041 rows that crawl actually wrote, **16,993 read `absent`** and 48 read `confirmed` — the ones written in the final second. `contractor_profiles` → `unsighted` 17,371 + `retired` 14, because `dataset_sighting` holds **0** rows for that key. `last_absent_at` is NULL on all 17,417 sightings, so the ledger records no absence at all while the column asserts 17,221. Code: `scrapex/sightings.py:398` — `if last_seen_at is None or last_seen_at < newest:` → `return STATE_ABSENT`.
**The new half:** `approve_candidate` returns at `scrapex/extract/service.py:503-511` **before** `catalog.register_site` and therefore before the upsert, while `scrapex/contractors.py:1217-1224` runs `write_groups` afterwards regardless. Measured: **17,264 of 17,371** profile records carry `last_seen_at = 2026-08-23` while **all 397,526** memberships carry `2026-08-24`. The docstring at `service.py:601-603` asserts the opposite («`last_seen_at` still moved: the upsert above sets it unconditionally»), which is true of the write path and false of the recovered path. So filling the sighting ledger as `R-52` plans turns those 17,264 rows from `unsighted` into `absent`, not into `confirmed`.
**Cost:** `scrapex/publish.py:89` turns every payload column into a workbook column, so the sentence is a published column, not a screen. This is the one defect that is wrong on 99% of your rows.
**And `R-52`'s own text is wrong about it:** `docs/RULINGS.md:2370` reads «`absent` now rests on the sighting ledger's own `last_absent_at`» — the code at `5722b6f` does not, and a session reading the ruling will believe that half is done.

**2 · The approved schema of `contractor_profiles` is the 14 impostor rows', it advertises 12 phantom columns, and it has LOCKED the dataset against the next real field.** *Ours. Not in any plan, ruling or backlog entry.*
`dataset_schema_version` for dataset 2: v1 (21 fields) retired; **v2 (27 fields) `retired` at 2026-08-23T13:59:07Z and holding all 17,371 ACTIVE rows**; **v3 (39 fields) `approved`, `valid_to IS NULL`, and its only rows are the 14 whose status is `retired`**. `v3 − v2` is exactly the 12 `x_*` fields, and `data_json` carries them on **0 of 17,371** active rows and **14 of 14** retired ones. They were minted from a dead id's listing page by `scrapex/extract/muqawil.py:1175` (`fields[key or f"x_{_slug(label)}"] = value`) and `:1712`.
Consumers: `dataset_schema_fields` selects `WHERE sv.dataset_definition_id = ? AND sv.valid_to IS NULL` (`scrapex/extract/service.py:827`) and is called by `dataset_table_payload` at `:887` — so the grid and the workbook get **39 columns of which 12 are phantom**, and `dataset_field` for `contractor_profiles` holds all 39, so the column chooser offers them too.
**The lock, which is new:** a 27-field parse hashes to v2's existing hash and short-circuits at `service.py:353-359` (a lookup with **no status filter**), which is why every live row sits on a retired version. But a parse that gains one new label produces a hash that does not exist, falls through to `_retire_or_refuse` against **v3**, computes `lost = the 12 x_*`, and raises `ExtractionConflict` («A field the site still publishes must not be retired by one page's sample», `service.py:328-336`). `scrapex/contractors.py:1227-1230` catches it, rolls back and appends to `refused`. Measured: **0 of 17,417** stored English profile pages carry an undeclared label today — the trap is armed and unsprung.
**Cost:** the shape that describes all 17,371 rows is marked dead, the shape marked live describes 14 rejected rows, 12 invented slugs are published as if muqawil produced them (which `R-45` forbids by name: «A mapping we invent is our claim dressed as the site's data»), and the day muqawil adds a field the crawl silently refuses those pages instead of recording the news.

**3 · The 14 retired impostor rows are on your screen and in your workbook, carrying another contractor's facts in the 12 phantom columns.** *Ours.*
`service.py:906` counts with **no status filter** and its comment says why («a row stays on screen whatever the crawl saw» — `R-27`), so the profile table publishes **17,385** rows. All 12 `x_*` fields are populated on **14 of 14** retired rows = **168 cells**, e.g. `x_status='Account Verified'`, `x_city_region='SAMTAH - Jizan'`, while that row's own city, region, address and coordinates are NULL. **12 of the 14 share `membership_number` `117511752`.** `scrapex/contractors.py:972-977` argues the case against exactly this state («A row that cannot be trusted is worth less than no row, because no row is visibly absent and this one is invisibly false») and then sets `status='retired'`, which `R-27` puts straight back on the screen.
**Cost:** it is also why `docs/CONTRACTOR-SOURCE.md:564`'s note that `membership_number` is not unique is still true of the table you see, and false of the 17,371 rows you have.

**4 · 14,621 of 17,371 profile rows (84.17%) store the site's unset map default as a location.** *Ours — the sentinel is the site's, treating it as a place is ours.*
All 14,621 hold `latitude='24.4493518'` and `longitude='46.6220053'`; only 2,659 distinct pairs exist. `scrapex/extract/muqawil.py:1755-1763` already names this exact constant as an unset default and rules «ABSENT RATHER THAN CORRECTED … a table whose purpose is to be believed cannot say the second» — then the guard at `:1765` fires only when a **half** is zero (`if english.latitude is not None and english.latitude and english.longitude:`), which correctly drops 19 pages publishing `lng: 0` and stores the 14,621 publishing the default **pair**. The default share is 81.9%–89.9% in every one of the 14 regions, up to 1,100 km apart, which no real coordinate distribution can be.
**Cost:** the column reports 99.89% fill; true per-contractor coverage is **2,731 of 17,371 = 15.72%**. Any map or distance query puts 14,621 companies at one point south of Riyadh, including every contractor in Jizan and Tabuk.

**5 · The two wired taxonomies use opposite conventions, so a category rollup returns 0 of 1,334 for licensed activities and is correct for interests.** *Ours. New.*
`interests`: of 358,304 non-root memberships, **0** lack their parent on the same record — every ancestor is materialised. `licensed_activities`: of 8,098 non-root memberships, **8,098** lack their parent, and all 4 level-1 nodes of scheme 2 are held by **0** of the 1,334 licensed contractors. Both go through one writer (`scrapex/contractors.py:952-956`), which links only the node `ensure_path` returns.
**Cost:** «which contractors are licensed under تشييد المباني» answers 0 of 1,334 while the identical question on interests is right, and nothing on the table or in the repository distinguishes the two.

**6 · Half the Interests vocabulary is the site's "No Data" placeholder, stored as a first-class level-1 activity node.** *The site's string; our shape.*
`classification_node` 111: `node_name 'No Data'`, `node_name_ar 'لا يوجد بيانات'`, level 1, parent NULL, no children, **held by 8,755 of 17,371 (50.4%)** — and for all 8,755 it is their **only** interest membership. So `interests` reads 17,371 of 17,371 (100%) coverage where **8,616 (49.6%)** publish a real activity, and it outranks `Construction of buildings` (7,442). The `licensed_activities` scheme has no equivalent. `grep` over `docs/*.md`, `muqawil.py`, `contractors.py`, `taxonomy.py` and `tests/` for `No Data` / `لا يوجد بيانات` returns nothing.
**Cost:** every coverage or membership figure computed off `generic_record_node` is inflated by 8,755 rows, and the first facet UI built on this tree will offer "No Data" as a category.

**7 · `is_saudi_contractor` is `true` on the 19 Affiliate-Organization rows, which the site never says.** *Ours.*
Crosstab over 17,371 active rows: `Saudi Contractor/true` 15,714 · `Non-Saudi Contractor/false` 1,638 · **`Affiliate-Organization/true` 19**. `scrapex/extract/muqawil.py:1751-1754` derives it as `str("non" not in membership.lower()).lower()` under a comment promising the two fields «can never disagree». A boolean derived by substring from a three-valued enum is right on two values of three.

**8 · Sixteen values carry an undecoded Cloudflare placeholder as data.** *Ours.*
`company_name` is exactly `[email protected]` on **3** active listing rows (all three have a real Arabic name in `company_name_ar`); `address` contains `email protected` on **13** profile rows. `read_listing` reads the card title through `_text` and never calls `read_email`, which is wired only into `read_profile`. The module's own docstring (`muqawil.py:18-22`) is built around this exact failure: «A parser that does not decode stores that literal for every contractor in the country, and a test asking "is this column populated?" passes forever.»

**9 · `dataset_relationship` asserts `one_to_one` / `confirmed` / confidence 1.0 while 229 ids break it, and its stored evidence is 24× out of date.** *Ours.*
One row: `('contractor_profile', parent=1, child=2, 'one_to_one', 'confirmed', 1.0)`, `evidence_json` = `"measured":"704 profile rows, 704 distinct contractor_id"`, `updated_at 2026-08-22T10:46:07Z`. Measured today: 17,223 in both, **81 listing-only, 148 profile-only**, and profiles ÷ listing = **100.39%**. `R-47` calls this join «the thing that makes the single card honest», so the one string justifying the single card is 24× stale and reads as a measurement.

**10 · The engine page prints "Latest price per offer" as the heading over 17,371 contractors.** *Ours. Recorded nowhere.*
`scrapex/webui/templates/source.html:148` — `<h2>Latest price per offer</h2>`, unconditional; `grep -n is_dataset` over that template returns nothing. This is the page the panel's card click opens. `grep -rn 'Latest price per offer' docs/` returns nothing, and `OP-63` covers only the *"products"* noun elsewhere on the page. Under `R-32` this is the price-tracker framing built in rather than merely written down.

**11 · Two row counts for one dataset, and a "Last crawled" date 47 hours older than the crawl the card stands for.** *Ours.*
`/api/sources` coverage says `stored=17371` and the menu tooltip promises «The 17,371 rows of Contractor profiles»; `/api/table/contractor_profiles` then returns `total=17385`. Both are correct under their own rule (`_dataset_rows` filters `status='active'`; `dataset_table_payload` deliberately does not, per `R-27`) and neither says which it means. Separately the folded muqawil card's `last_success.started_at` is `2026-08-21T17:56:31Z` — the **parent's** value — while the child's own is `2026-08-23T16:44:38Z`, so the 34,834-page crawl is invisible on the card that represents it.

### B · Data the site publishes that we do not hold, or cannot reach — 7

**12 · 263 of 17,304 listing rows are frozen on retired schema v1, `profile_url` is absent on all 263, and re-approval from disk is REFUSED — not free.** *Ours.* **A correction was applied to this finding.**
263 rows on `schema_version_id=1` (22 fields) against 17,041 on the approved v2 (28). `v2 − v1` is exactly `card_city, card_city_ar, card_region, card_region_ar, profile_url, profile_url_ar`, and all six are **absent as keys**, not NULL. All 263 came from 228 distinct **Arabic** snapshots, `crawl_run_ref IS NULL`, captured **2026-08-20**, and **all 263 of those snapshots already carry a v1 ingestion for dataset 1** — so a re-parse hits `ExtractionConflict` at `scrapex/extract/service.py:481-489` and writes nothing. DEC-10 permits a re-parse whose field set is unchanged; adding six columns is precisely what these rows need.
**Corrections applied:** the audit first reported this as 263 rows losing their city and as repairable from disk. Measured: **252** of the 263 hold a splittable `card_city_region` (`'TUMAIR - Riyadh'`); the other 11 publish no location at all and are the `region_id=0` class, which under `R-45` is the site's truth. For **217** of the 263 the separated city and region are already in `contractor_profiles` and agree with the split of the listing string on 217 of 217. And there is a second signal: 227 of the 263 were re-sighted on 2026-08-21 while `generic_record.last_seen_at` for all 263 is still 2026-08-20 — the sighting ledger advanced and the record path did not.
**Cost:** 1.52% of the published contractor table has no profile link at all, and the repair is a decision (§7.5), not a chore.

**13 · 148 sighted contractors have a profile row and no listing row, and all 148 are recoverable from pages already on disk with zero network requests.** *Ours.* **New — this closes an explicitly-open question.**
148 ids are active in `contractor_profiles` and absent from `contractors`; every one has a `dataset_sighting` row with `seen_count` 2–13, so the site showed each of them between two and thirteen times. Decoding all 20,683 stored listing snapshots: **148 of 148** appear on at least one **English** listing snapshot, and **148 of 148** have such a snapshot with no ingestion row for dataset 1 — so `_approved_ingestion` returns None, no conflict can fire, and the write path runs. **16,800 of 20,683** listing snapshots have never been ingested at all. This is `REQ-41`, captured 2026-08-23, still awaiting your choice of mechanism.

**14 · 397,526 memberships have no read path — no route, no payload column, no export tab, and `REQ-32` as written would render zero of them.** *Ours.* **A correction was applied.**
`scrapex/taxonomy.py:198 memberships(` is the only match for `memberships(` in `scrapex/`, and `generic_record_node` is referenced in exactly one production file. `dataset_table_payload` never reads it. `scrapex/publish.py:89-92` builds the dataset workbook from `payload["columns"]` alone and returns **one tab**; both downloaded workbooks have exactly 1 sheet. `REQ-32` step 1 specifies «every field the row carries that is not a visible column» — measured, that set is **empty** for both datasets (27 keys, 27 columns), so a card built to its spec renders 0 of the 397,526 memberships and 0 of the 52 readiness values (which live in `generic_record_node.attribute_value`, not in `data_json`).
**Correction:** the first framing said these facts «reach NO surface» and implied `REQ-32` covers them. It does not — the gap is an endpoint plus a card, and the plan is one piece short.
**Cost:** `R-19`'s entire justification was the query «which contractors operate sewage networks». It is unanswerable from any surface.

**15 · Balady Services is published on 886 profile pages and stored as one delimited string instead of memberships, and three documents say it is not on the page at all.** *Ours — a normalisation gap plus a documentation defect.* **A correction was applied.**
The info-box labelled `Activity` / `الخدمة` is on **886 of 17,417** English pages; on all 886 its icon is `.../baladyServices/icon-tag.png` and its values are separated by `<span class="info-value-balady"> , </span>`. Splitting gives a **closed vocabulary of exactly 8** services, matching `balady_service_id`'s 8 filter values. `PROFILE_FIELDS` maps the label to one scalar (`muqawil.py:156`), so the box lands whole in `activity` (885 rows, trailing `' ,'` on 885 of 885, a comma-bearing service name on 406). `generic_record_node` holds **0** balady rows.
**Correction:** the first framing called this data loss and said 406 rows cannot be recovered. They can — splitting on `' , '` reproduces the site's value list exactly on **885 of 885** rows including all 406, because the site's delimiter is its own element and the values' internal commas are comma-space. Nothing is lost; what is missing is the child-table shape `R-19`/`R-38` and `docs/CONTRACTOR-SOURCE.md:62-64` require («**not** as `Activity 1, Activity 2, …`»), and it is a re-parse of stored snapshots, not a re-crawl.
**The documentation half is a real, separate defect:** `docs/RULINGS.md:591` concludes Balady is not on the profile page from a marker test for the string `Balady Services`, which occurs on 39 of 17,417 pages and only ever as the HTML comment `<!-- Balady Services -->` in the listing filter form. `GROUPS_NOT_LOCATED` (`muqawil.py:540-542`) repeats it. Third instance of `LESSONS` §9 — a search for one spelling of a feature is not a measurement of the feature.

**16 · 105 of the 1,497 addresses the site publishes are not in the warehouse, and 8 contractors have both pages on disk and no row at all.** *Ours, and a ruled trade-off.*
The site publishes an address for 1,497 contractors (1,376 on the English page, plus 121 the Arabic page prints and English does not); the warehouse holds 1,392. The shortfall is exactly **97** rows that exist with `address` NULL (English omits two boxes, so which one Arabic carries cannot be named) plus **8** contractors with no record of any status: ids `1089, 2079, 3957, 20003723, 20020974, 20025894, 20044979, 20060354`. On all 8 the Arabic page is the shorter side by exactly one info-box — `R-51` predicted this to the row («Eight stay refused: Arabic is the shorter side», `docs/RULINGS.md:2301-2303`). Not a new defect; the count and the direction are what was not stated.

**17 · The offline pack carries 12 price shops and 0 of 34,675 contractor rows.** *Ours — `R-50` / `REQ-40`, unchanged.*
Your bundle `scrapex-bundle-20260823-130954.zip` (345,141,533 bytes, created 2026-08-23T13:10:46Z, the day the crawl finished): 12 `datasets/` folders and 12 manifest keys, all price shops; `panel.jsonl.gz` has **121,658 lines** across those 12 keys and **0** contractor lines. Cause unchanged at `5722b6f`: `scrapex/bundle.py:140` → `available = [s.source_key for s in list_sources(conn)]` → `scrapex/reports.py:104` → `SELECT source_key FROM source_site`, and `source_site` holds 12 rows, none a contractor key (muqawil lives in `site_profile`).

**18 · The panel offers no export for a dataset, and the only working export is a button on the surface being ported away.** *Ours — `R-48` / `R-50`.*
`GET /api/export/contractors` → **404**, `{"detail":"no source called 'contractors' …"}` — the route validates against `app.state.manifest.sources`, which names only the 12 price shops. The extension's dataset card correctly hides the action (`extension/app.js:4755` filters on `RESOLVES_A_DATASET`) and its Data page has no export control. The one path that works is `grid.js:3136` → `/export/contractors.xlsx`, measured 200 / 3,417,513 bytes / 9,601 ms, a valid single-sheet workbook `openpyxl` reads clean at 17,304 data rows.

### C · Declared debt — 10

**19 · Every contractor field is declared `text`, so nothing validates.** `field_definition.data_type` is `text` on **28 of 28** and **39 of 39** fields, including `latitude`, `longitude`, `member_since`, `training_credit_hours` and every count — against `docs/CONTRACTOR-SOURCE.md:565-583`, which declares them `decimal`, `date` and `integer`. `_convert` (`service.py:152`) therefore never parses or rejects. Consequences: `training_credit_hours` is numeric on **0 of 17,371** (`'0 h'` on 16,635) and `card_training_credit_hours` on **0 of 17,304**, so a column the doc calls an integer cannot be summed or sorted in the grid or in Excel. *Ours.*

**20 · The no-logo guard tests a string the corpus never contains, and two documents state a mechanism the corpus contradicts.** **A correction was applied.** `muqawil.py:1230` — `row["logo_url"] = "" if source.endswith("companies/default.jpg") else source` — is unreachable: `default.jpg` appears in `src` on **0 of 17,304** stored values and 0 of 42,202 cards. The site's real no-logo encoding is the base path with an empty filename, on **13,042 of 17,304 (75.37%)**, plus **2,743** values containing a raw space, making **15,785 (91.2%)** unusable as a URL without percent-encoding. `docs/CONTRACTOR-SOURCE.md:421-423` and `:560` describe an `onerror` fallback that is present on every card including every card **with** a logo, so it cannot distinguish the two. **Correction:** the stored values are not corrupt — they are the site's bytes on 17,290 of 17,290 verifiable rows, and whether to store NULL instead is your ruling (§7.3), because `:560` says NULL and `R-45` says never modify. Zero consumers render the field today. *Ours, on the guard and the docs.*

**21 · 11 price-path keys are still registered against the `contractors` dataset.** `dataset_field` holds **39** rows for `source_key='contractors'` against **28** live fields; the 11 extras are `price, tax, stock_quantity, curation, display_method, minimum_quantity, quantity_increment, category_leaf, category_leaf_ar, price_changed_on, last_confirmed_on`. `R-45` recorded 11 and it is still 11 — nothing was repaired (`OP-58`). `contractor_profiles` holds 39 rows matching its 39 live fields, i.e. including all 12 phantoms. `is_hidden=1` on 0 of 78 rows; `arranged_at` set on 0. *Ours.*

**22 · 67 of 67 column headings are raw `snake_case` keys, and the dataset export carries no provenance tab.** `field_definition.display_name = field_key` on **28 of 28** and **39 of 39** rows, so only the 6 platform columns get English labels; the workbook headers read `card_training_credit_hours_ar`, `self_build_price_five_to_ten_projects`, `x_unclassified`. And `publish.py:92` returns one tab where the price path appends `"… — about"` whose own docstring says «A spreadsheet outlives the screen it was exported from and gets mailed to people who never saw it». Confirmed: both contractor workbooks have exactly 1 sheet, so a 17,385-row spreadsheet carries no source, no site and no exported-at. *Ours.*

**23 · Per-field change history is unrecorded, and 12,046 pre-gate revision rows sit behind a delete trigger.** `generic_record_field_change` holds **0** rows warehouse-wide, across two schema transitions in 24 hours — the exact transition its own DDL comment was written for. Separately, of the listing's 52,439 revisions, **12,046 are consecutive byte-identical repeats** on 4,531 records — all of them written **2026-08-17 (5,963)** and **2026-08-20 (6,083)**, and **0 on 2026-08-22**, the first pass after the `R-20` gate; `contractor_profiles` has 18,089 revisions and **0** consecutive duplicates. So `R-20` works and this is a bounded historical backlog, not a live defect — and `trg_generic_record_revision_append_only_delete` means removing it needs a schema exception. *Ours.*

**24 · Contractor evidence has no retention path, and 48.8% of the file is pre-compression bytes.** `retention.py` → `price_observation` 16 / `generic_record` 0 / `generic_page_snapshot` 0; `compaction.py` → 7 / 0 / 0. `retention_run` **0 rows** — retention has never run for any dataset — and the only policy is `('*', 3650, 'keep_all')`, keyed on a `source_key` that resolves through `source_site`, where muqawil has no row. And it is forbidden rather than merely absent: `trg_generic_page_snapshot_immutable_delete BEFORE DELETE … RAISE(ABORT, 'saved HTML snapshots are immutable')`. The bill, measured: **1,728 pre-codec snapshots hold 636,779,275 bytes = 48.8% of the 1,305,468,928-byte file** at 368 KB a page, against 2,316 bytes a page for the compressed profile crawl; and 35,069 snapshots (240.8 MiB) are referenced by nothing, including all 18,179 Arabic profile pages. `STORAGE.md` §5 already holds this question open for you. *Ours, and deliberate.*

**25 · A crawl's identity is nullable free text, and the corpus already contains a run named `R`.** `generic_page_snapshot.crawl_run_ref` is `TEXT`, no FK, no NOT NULL; 142 distinct values, 1,728 NULL, and one value is **`R`** — 2 pages, contractor 20074580, both locales, `2026-08-24T06:11:13Z`, almost certainly a truncated `--run-ref`. Those 2 pages are unreachable by the real run's resume query. `R-52`'s table is unbuilt, so the only record that the 34,834-page crawl happened is an unconstrained string column plus two log files under one machine's home directory. *Ours.*

**26 · Hiding a column on a contractor table is a latent data-loss path.** `dataset_table_payload` returns `columns` minus the hidden set and puts the hidden ones in `moved_to_details` (`service.py:1036`); `publish.py:89` builds the workbook from `columns` only; and the sole consumer of `moved_to_details` anywhere is `grid.js:2933`, inside the card that never opens for a dataset. Today `moved_to_details` is `[]` for both datasets and `is_hidden=0` on all 78 rows, so nothing is lost yet — the first tidy of the 45-column profile grid removes the field from the screen and the spreadsheet at once. `OP-54` closed the silent no-op, and working is what makes it destructive. *Ours.* **Not measured end to end** — proving it needs a `POST /api/fields`, which this pass would not do.

**27 · Eleven statements in the documents and docstrings are measurably false.** `C2` makes each a bug:

| statement | where | measured |
|---|---|---|
| «THE READINESS LEVEL IS READ AND NOT STORED … five distinct values» | `contractors.py:908-913` | **stored** on 52 memberships, **four** values (Basic 20, Gold 15, Silver 10, Dimond 7) |
| «no command targets specific ids today» | `contractors.py:1036-1037` | `--ids` exists at `:1323`, validated by `_named_ids` at `:1041`, passed at `:1472` |
| «`absent` now rests on the sighting ledger's own `last_absent_at`» | `RULINGS.md:2370` | `sightings.py:398` compares against `newest`; `last_absent_at` NULL on all 17,417 |
| «Balady Services appears on 0 of 2,419 pages» | `RULINGS.md:591`, `muqawil.py:540` | 886 of 17,417, under the label `Activity` |
| «391,761 memberships» / schema «v9» | `STATE.md:113`, `:115` | **397,526** / `user_version = 10` |
| «the profile crawl — ready to run / not yet run / profiles never crawled» | 6 statements across `plans/*.md` and `STATE.md:1144`, `:1202` | finished 2026-08-23T13:43:52Z; `STATE.md` contradicts itself 1,091 lines apart |
| `R-39`'s «87 hours» / «11–14 hours» | `RULINGS.md:1030-1060`, `contractors.py:490,494,1447` | measured **9.75 h active** at 1.007 s/page; the amended range is 13–44% high |
| `self_build_prices` on 713 of 2,419 (29.5%); `contract_counts` on 92 of 2,419 | `muqawil.py:772-780` | 1,401 of 17,417 (8.0%) and 205 of 17,417 (1.18%) — the 2,419 sample was the head of the frontier |
| «`map_location_url` \| url \| pr» | `CONTRACTOR-SOURCE.md:562` | the site publishes a real map URL on **1 of 17,417** pages |
| «2,542 over 2,542 contractors — no two share one … a second natural key» | `CONTRACTOR-SOURCE.md:478-484` | **17,342 distinct over 17,371**; 29 values shared by 58 rows; two values not ten digits |
| `evidence_json` «704 profile rows» | `dataset_relationship` | 17,371 |
| «+ 133 ms transfer = 616 ms … 12% of it» | `service.py:877-878` | server halves reproduce (484 ms), but a real Chrome on loopback is 2,333 ms = **47%** of the 5,000 ms deadline, and the payload is uncapped at 23.14 MiB |

**28 · The production crawl log cannot be read as an audit trail.** `~/.scrapex/contractors.log` (1,140 lines) interleaves test-suite output with production: `refused https://example.test/…`, `AssertionError: NETWORK CALLED` (100 lines), `OperationalError: no such table: snapshot_dictionary`, and one impostor block repeated verbatim three times. Two of the file's three `failed N` lines are those test runs. A reader who greps `failed` concludes 102 pages failed; the real answer for every production run is **0**. *Ours.*

### What the site publishes that is impossible — reported, never corrected (`R-45`)

These are **not our defects**. They belong in a declared type and a documented sentinel, not in an edit.

| what | count | note |
|---|---:|---|
| profile pages the site no longer serves — it answers with the listing at HTTP 200, ~372 KB | **73 ids** | 176 of 36,358 stored pages; both locales for all 73; each links 20 strangers and itself never. **All 73 have an active listing row** — the contractor is listed, the detail page is gone. 49 have been re-asked once and 48 came back as the listing again; the 49th (`20074983`) returned a real profile and is now an active row |
| contractors with no location box at all (`region_id=0`) | **1,475 of 17,304** | `card_city_region` empty; their profile pages independently confirm it |
| coordinates outside Saudi Arabia, in the site's own inline script | **3** | `20143988` at (43.148, −110.393) — Wyoming, city `AL SIRR`; `20039081` at (38.679, 19.969) — Adriatic; `20109993` at (16.889, 56.549) — off Oman |
| `contractor_classification_grade = 2147483647` (INT32_MAX) | **1** | contractor 20075537, whose classification label is the empty string — the one row of 17,304 with a NULL classification |
| `''` vs `'0'` under the identical label `Unclassified` | 9,066 vs 2,839 | the site's own inconsistency |
| `organization_mobile_number` matching no plausible SA shape | 984 of 5,791 | 28 are all zeros; the longest is 35 characters |
| self-build prices per m² of 0, 1, and 522,625,231 | 4–5 / 3 / 1 | contractor 2905 quotes 110,000 / 522,625,231 / 41,144,444 |
| commercial registrations shared by two rows | 29 values / 58 rows | 22 are the same company registered twice with adjacent ids; 7 are different names |
| the spelling `Dimond`, and `المنطقه` with `ه` | 7 / all pages | kept verbatim, which `R-45` requires and `R-51` depends on |
| a logo filename whose bytes do not decode | 1 | `…CompanyLogo-1766325831_<U+FFFD><U+FFFD>لوقو معدل<U+FFFD>.JPG` — the site's own filename |

---

## 5 · Refuted claims — what the audit thought it found and why it was wrong

Fifteen claims were put up and knocked down. They are here because they are how you judge the twenty-eight above.

1. **"13,042 `logo_url` values are corrupted data."** They are the site's bytes on 17,290 of 17,290 verifiable rows. The defect is a guard that tests a string the corpus never contains and two documents describing a mechanism the corpus contradicts — and whether to store NULL instead is your ruling. Re-filed as defect 20.
2. **"406 Balady rows cannot be split back into their services."** Splitting on `' , '` reproduces the site's value list exactly on **885 of 885** rows, all 406 included, because the site's delimiter is its own element. Nothing is lost; it is a normalisation gap plus a doc defect. Re-filed as defect 15.
3. **"The listing and the profile disagree on city for 217 contractors."** Zero disagreements. `card_city_region` is in both schema versions and non-empty on 252 of the 263; the correct comparison over the 17,223 shared ids yields **0**.
4. **"The 263 stranded rows are the cheapest open item — the snapshots are on disk and DEC-10 makes a re-parse safe."** All 263 snapshots already carry a v1 ingestion for dataset 1, so a re-approve raises `ExtractionConflict` and writes nothing. The repair is a decision with three priced options, not a free query.
5. **"175 listing rows are missing their Arabic city and it is our bug."** The site reordered its listing between our English and Arabic requests (0/20 id overlap on 22 of 25 pages), and 174 of the 175 already have the Arabic city in `contractor_profiles`.
6. **"`R-20` is unbuilt and the surplus has grown to 12,582 revisions."** `R-20` is built and holds: all 12,046 consecutive byte-identical rows were written on 2026-08-17 and 2026-08-20 and **0 on 2026-08-22**, the first pass after the gate; profiles have 0. Filing it as unbuilt would have sent a session to rebuild working code.
7. **"The listing compression is 4.07× worse than documented, so `STORAGE.md`'s 160 MB headline is false."** On the corpus the study actually measured, the shipped `zstandard` wheel gives **253.66×** on 40 pages and **260.71×** over all 1,728, beating the projection. The doc already records 254×. The measured 46× was over a *different* corpus — 18,955 partition re-crawl pages the study never priced. The real finding underneath is new and unrecorded: `label_for` (`snapshotbody.py:104-105`) reads only `netloc`, so both locales share one English dictionary, costing ~118 MB of the 284.7 MB stored.
8. **"All 98 pages of the `gap-2026-08-23` re-fetch are the listing, so the run produced nothing."** 96 of 98. The 49th id returned a real profile and became active `generic_record 34568` at 2026-08-23T16:49:00Z. A re-fetch of a listing-answering id is not always futile.
9. **"59 dead ids have no row at all."** 59 have no *profile* row; **73 of 73 have an active listing row.** The contractor is in the warehouse; only the detail page is gone.
10. **"Retention being forbidden by trigger is a defect."** It is a deliberate schema decision `STORAGE.md:249` argues for explicitly, and the question is open for you. The number that matters is not "no retention" but 636,779,275 bytes in 1,728 pre-codec rows.
11. **"397,526 facts reach no surface."** Narrowed: they have no *read path*, and `REQ-32` as written would render zero of them because none is a `data_json` field. Also a trap avoided: the payload does serve a column called `activity`, which reads like the group and is a third vocabulary.
12. **"Neither dataset holds the population and the 17,452 lives nowhere."** `SELECT COUNT(DISTINCT json_extract(data_json,'$.contractor_id')) FROM generic_record` returns 17,452 today. What is missing is a **named** surface stating it — `saved_view` holds 0 rows, and `--coverage` answers per dataset.
13. **"The false `State` sentence has reached the Google Sheet the mbiX add-in reads."** Not measured as having happened: the last Apps Script push was 168 rows on 2026-08-03 and the last Excel write 87 rows on 2026-07-26, both predating the dataset. The correct claim is that `publish.py:137` would carry it on the **first** push of `contractors`.
14. **"The missing record card is a new defect."** It is `REQ-32` / `OP-57`, open and ruled, and re-confirmed live today. It withholds **0 of 34** and **0 of 45** site fields — `moved_to_details` is empty on both payloads and every column is visible.
15. **"`docs/CONTRACTOR-SOURCE.md:564`'s membership_number note is stale."** It is correct once the 14 retired rows are counted — and those rows are on your screen. It is a symptom of defect 3, not a doc bug.

---

## 6 · What is clean, and exactly what was checked

- **Mechanical integrity.** `PRAGMA integrity_check` → the single string `ok`, run twice over all 318,715 pages (2.2 s and 4.3 s), covering the whole 1.3 GB file; `PRAGMA foreign_key_check` → **0 rows**; `freelist_count = 0`. Nine hand-written orphan probes all **0**: `generic_record`→`dataset_definition`, →snapshot; `generic_ingestion`→snapshot; `generic_record_revision`→record, →snapshot; `generic_record_node`→record, →node, →snapshot; `classification_node`→parent. Verified independently in this pass: 0 orphan memberships, 0 memberships with a NULL `source_snapshot_id`.
- **No duplicates, on three keys.** 17,304 active listing rows carry 17,304 distinct `contractor_id` **and** 17,304 distinct `card_membership_number`; 17,371 active profile rows carry 17,371 distinct of each; `contractor_id` equals the URL path segment on 17,385 of 17,385; and for the 17,223 contractors in both datasets the membership number agrees **17,223 of 17,223**.
- **Nothing has ever been deleted.** `count == max(id)` with gap 0 in all six of `generic_page_snapshot` (57,041), `generic_ingestion` (21,972), `generic_record` (34,689), `generic_record_revision` (70,528), `classification_node` (243), `dataset_sighting` (17,417).
- **The crawl.** 34,834 of 34,834 pages, 34,834 distinct URLs, both locales at exactly 17,417, **0** fetch failures in the logs, **0** decode failures over all 36,358 profile pages and all 18,955 listing pages, **0** profiles anywhere in the corpus with only one locale half stored, and 34,756 of 34,834 pages linking only to their own contractor.
- **Field presence.** All 27 profile keys present on all 17,371 rows; all 28 listing keys present on 17,041 and 22 on all 17,304. The only absent keys are the 6 on 263 rows (defect 12).
- **Bilingual pairing.** `contractor_profiles`: 6 pairs, **0** half-only rows and **0** pairs whose halves are the same string. `contractors`: 175–227 English-only rows, explained by the site's listing reordering, with 174 of 175 Arabic cities present in the profile table.
- **The email decode.** 17,371 of 17,371 contain `@`; **0** literal `[email protected]` in that column; **0** `@muqawil.org`; 17,347 distinct; 1 syntactically invalid and it is the site's typo. On all 14 multi-`data-cfemail` pages located precisely, the first attribute sits inside the Organization Email box.
- **Text hygiene.** **0** HTML entities, **0** HTML tags, **0** script fragments, **0** newlines or tabs in any value of any field of all 34,675 active rows; **0** mojibake in any parsed text field (the single U+FFFD is inside a filename the site itself published). `member_since` is `YYYY/MM/DD` on 17,371 of 17,371, min 2018/08/25, max 2026/08/21, none in the future.
- **Taxonomy structure.** 2 schemes, 243 nodes at levels {1:12, 2:39, 3:192}, **0** nodes shared by two `group_keys`, **0** roots carrying children from two schemes, 3 of 29 scheme-2 nodes without an English name — exactly what `CONTRACTOR-SOURCE.md:627` predicts. Idempotency proven by a real second pass: `seen_count` 2 on 367,619 rows, **0** duplicate rows, the composite primary key held.
- **Fill rates against the source.** Every one of the 27 profile fields matches what the stored pages publish to within 8 records, and the three listing fields that look alarming are the site's: `membership_level` filled on 18 because the site sets the attribute on 18 of 17,296 cards; the rating pair on 17 because 17 cards carry a rating; `contractor_classification_grade` on 8,238 because 8,237 cards publish one.
- **The two flat surfaces work.** `/api/table/contractors` → 200, 17,304 rows, 34 columns, `truncated=false`, 24,265,034 bytes, 1,765–2,022 ms server-side. Both `.xlsx` exports are valid single-sheet workbooks `openpyxl` opens clean at 17,304 and 17,385 data rows.
- **Nothing claims to be running.** `crawl_job`: 91 completed, 25 failed, 19 cancelled, 4 partial, 1 with errors, **0 running or claimed**, every row with `finished_at` and `last_heartbeat_at`. `crawl_run`: 159 success + 1 failed, all finished. `generic_ingestion`: 21,972 all `success`.
- **What was NOT checked in this pass:** the products side (no targeted probe on `price_observation`, `source_offer`, `change_event`, `price_period`); the Arabic profile pages' content; the values inside the two taxonomies node by node; and every trigger's actual firing (the inventory is read from `sqlite_master` and `schema.sql`; nothing was written to test one).

---

## 7 · Decisions only you can make

**1 · The poisoned profile schema.** Three ways out, each measured.
(a) Re-open v2 as approved and retire v3 — 17,371 rows immediately match their declared shape, the 12 phantom columns leave the grid and the workbook, the lock lifts, and the 14 retired rows lose their declared columns. (b) Re-approve all 17,371 rows onto a clean 27-field v4 — same result plus a correct version history, and it writes 17,371 rows and 17,371 revisions with no network (the snapshots are on disk). (c) Leave it — the grid keeps 12 columns that are empty on 100% of rows, the next new muqawil field is refused rather than recorded, and `R-31`'s subset rule will refuse any future 27-field parse that ever needs to open a version.

**2 · The 14 retired impostor rows on your screen.** `R-27` says «a row stays on screen whatever the crawl saw», and `contractors.py:972-977` argues the opposite for exactly these rows. (a) Delete them — the table publishes 17,371 and the 168 foreign cells go; you lose the visible record that 14 pages lied. (b) Publish `retired` rows behind a filter — the record stays and the false cells leave the default view; it is a surface change. (c) Leave them — `membership_number` remains non-unique on the table you see, and 12 of 14 rows keep another contractor's membership number.

**3 · `logo_url`: the site's bytes or an honest NULL.** `CONTRACTOR-SOURCE.md:560` says the placeholder «must be stored as NULL»; `R-45` says never modify what the site publishes. They point opposite ways on this one field. (a) Store NULL for the bare directory — the column becomes honestly 24.63% populated and nothing recoverable is lost, because a filename-less path carries no information. (b) Keep it — the column stays 100% non-empty and 91.2% unusable, and any test asking "is it populated?" passes forever. Zero consumers render it either way, so there is no user-visible urgency.

**4 · The default map pin.** The repository has already applied «absent rather than corrected» to the `lng: 0` case, on 19 rows. (a) Extend the same reasoning to the default **pair** — coordinate coverage becomes an honest 2,731 of 17,371 (15.72%) and one comparison costs it. (b) Keep it — the column reports 99.89% and places 14,621 companies at one point, including all of Jizan and Tabuk.

**5 · The 263 stranded listing rows.** Four priced options. (a) Re-approve the 228 stored snapshots — **refused**, `ExtractionConflict`, writes nothing. (b) Wipe and re-approve from disk (`R-28` option (a)) — works, ~20 minutes, no network, and `R-40` says it «destroys history every time». (c) A fresh listing crawl — DEC-11 prices a provable pass at **2.7 h serial / 58 min at concurrency 4**, and it lands all 263 on v2 with their `profile_url`. (d) Derive the six values in place from data already in the same row — zero network, zero refusal, and it leaves those rows frozen at a 2026-08-20 `last_seen_at` while the sighting ledger says 2026-08-21.

**6 · The 148 profile-only contractors.** `REQ-41`, captured 2026-08-23 in your words, still awaiting your choice between automatic-at-end-of-crawl and a command. Cost measured: **148 of 148 need zero network requests** — they are on English listing snapshots already stored, among the 16,800 listing pages never ingested. The other side of the gap is not yours to close: 73 of the 81 listing-only ids are dead at source and 8 are `R-51`'s ruled residue, so the reconcilable population is **at most 156, and 148 of them are free**.

**7 · `Q-18` — do the two relation groups get tables?** The evidence is now full-population instead of 2,419 pages: **2** main-contractor relations and **6** sub-contractor relations exist in the entire 17,304-contractor directory. Building them costs a scheme, a node table and a link path for 8 rows; not building leaves two of `R-19`'s five groups permanently unwired and needs a line saying so.

**8 · `STORAGE.md` §5 — is a snapshot evidence or a parse cache?** Now concrete rather than hypothetical. Keeping everything: **636,779,275 bytes (48.8% of the file)** in 1,728 pre-codec listing pages plus 240.8 MiB in 35,069 snapshots nothing references, and the bundle you carry between machines stays 345 MB. Re-encoding the 1,728 would recover ~600 MB and requires dropping an immutability trigger to do it. What that evidence bought is not hypothetical either: `R-51`'s recovery of 121 rows and this audit's entire page-level verification ran with zero network because the pages were still there.

**9 · Should `interests` and `licensed_activities` answer the same query shape?** `interests` materialises every ancestor (0 of 358,304 non-root memberships missing a parent); `licensed_activities` stores only the leaf (8,098 of 8,098 missing theirs). (a) Materialise the licensed ancestors — a category rollup answers both groups identically, and 8,098 memberships become roughly 20,000. (b) Leave it and document the asymmetry — the rollup stays right for one group and silently empty for the other.

**10 · Is "No Data" a category?** The site publishes the string, so `R-45` says store it. (a) Keep it as a node — `interests` reports 100% coverage, 8,755 contractors are filed under an absence, and a facet UI offers it as a choice. (b) Treat it as the absence it is — coverage reads an honest 8,616 of 17,371 (49.6%), and 8,755 memberships leave the table.

**11 · Declared types.** 67 of 67 fields are `text` against a spec declaring `decimal`, `date` and `integer`. (a) Declare the real types — `training_credit_hours` needs its unit parsed off 34,675 values, and the grid and Excel can sum and sort. (b) Leave `text` — nothing validates, and `2147483647` and `'0 h'` continue to pass every populated-ness test.

**12 · Retention for the contractor dataset.** It has never run for anything (`retention_run` = 0 rows, the only policy is `keep_all`). A second identical profile crawl adds 34,834 rows and 76.9 MiB with no path to remove either — that half is cheap. The expensive half is item 8.

---

## 8 · Not measured

- **The live site.** Every figure labelled *"the site publishes"* was read from the stored snapshots of `profiles-2026-08-22` (captured 2026-08-22T10:27:32Z–2026-08-23T13:43:52Z) and the listing snapshots behind the active rows. **No network request was made.** If muqawil changed a label or a template after 2026-08-23, every ours-versus-the-site attribution is as old as those pages.
- **`scrapex` could not be imported.** `scrapex/extract/models.py:6-7` does `from pydantic import AnyHttpUrl` and this machine's Python 3.14 has pydantic 2.13.4, which raises `ImportError: cannot import name 'AnyHttpUrl'`. Every page-level measurement is therefore a re-implementation of the parser's logic (`_slug`, `_text`, `_boxes`, `decode`, and `OP-64` layer 1 transcribed from source and validated by reproducing stored `record_key`s and `content_hash`es exactly) — **not the parser itself**. All warehouse-level measurements are unaffected. This is itself worth filing: the CLI cannot be imported on this machine's default interpreter, and whether the installed engine runs on a different one was not checked.
- **Nothing was written, so nothing was executed.** `contractors --approve` was not run, so the 148-row recovery and the 263-row refusal are read off the code path (`_approved_ingestion` at `service.py:244-256`, the conflict at `:481-489`, the write path at `:563-611`) combined with the measured ingestion and `schema_hash` state. The 148 case additionally needs each id's paired Arabic snapshot for the `_ar` halves; that pairing was not verified page by page.
- **No trigger was fired.** The trigger inventory is read from `sqlite_master` and `db/engine/schema.sql:961-1143`. The zero id-gaps in all six append-only tables is the strongest indirect evidence that they have been holding.
- **Whether the 12 phantom columns render end to end in the panel.** Proven server-side by running `dataset_schema_fields`' exact SQL and getting all 39, and by reading the call site at `service.py:887` and the `_ar` pairing rule at `:845-852`. `/api/fields` was not called and no engine was started by this pass.
- **Whether hiding a dataset column really loses it.** Proving it needs a `POST /api/fields`, which read-only forbids. The claim rests on the producer, the sole consumer and the export path.
- **The 18,179 Arabic profile pages' content.** All are stored and referenced by nothing; none was decoded here, so whether they carry a field the English page does not is still open — and `R-51` gives reason to think the address box does.
- **`Company Description` ±ar, `Customer Rating Grade` ±ar and the five detail-rating scores.** The card census found **0** undeclared data-carrying cards, but over 1,200 of 34,834 pages, and that sample is **not random** — it is the first 1,200 snapshot ids, i.e. the lowest contractor ids. `undeclared_cards` also has a documented blind spot for text-only cards, and a Company Description would be one. `CONTRACTOR-SOURCE.md:630-641` records these nine as unpublished from four profiles; that verdict has not been retested at full scale.
- **Why the 2026-08-24 re-approve pass ran.** The mechanism is established from the code and the data (121 records changed, 397,405 memberships confirmed), but the invoking command was not found in any log, so whether it was a deliberate corpus-wide `R-51` recovery or a narrower run is unknown.
- **The 81 listing-only contractors from the other direction.** The disk search was run for the 148; the equivalent for the 81 (whether anything is recoverable from the 18,179 unreferenced Arabic snapshots) was not.
- **The bytes of the 12,046 pre-gate revisions**, and whether compacting them is worth a schema exception.
- **Products-side integrity.** `integrity_check` and `foreign_key_check` cover the whole file, but no targeted duplicate or orphan probe was run on `price_observation` (94,664), `source_offer` (17,543), `source_product` (9,270), `source_variant` (13,682), `change_event` (145,442) or `price_period` (23,569).
- **No test was run.** The claim that no test pins a dataset's active schema version rests on a `grep` of `tests/` for `valid_to IS NULL` against `dataset_schema_version` returning no match, not on a run.
- **The engine's four overview tiles for a dataset** (`OP-63`'s open half), and cold-engine timings — the engine was not restarted.
- **Query performance and index health on the contractor tables.** `dbstat` is not compiled into this SQLite build, so the 1.3 GB file could not be attributed to tables and indexes beyond `html_content`'s measured 921,516,178 bytes (70.6%).