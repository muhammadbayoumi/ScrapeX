# A contractor source, and a table of its own — muqawil.org

## Context

The owner asked for a contractor directory with **a table entirely of its own**, separate
from the product tables — «جدول منفصل تماما عن جداول المنتجات». He specified ~66 columns
himself after reading the site in both languages, then added `Is Saudi Contractor`,
`Latitude`, `Longitude`. He wants the crawl **staged like `GPP_ENERGY`**, and both languages
pulled because the Data page shows them behind a toggle.

Every source ScrapeX has ever had produces **offers**. A contractor is a **company**. This is
the first source of a different kind.

**The decisive finding: this is not new architecture. It is M6 step 3 and step 4 of a plan
the owner already wrote, whose named target is this exact site.**
`docs/GENERIC-FETCH-SEAM.md:3` — *"M6 needs muqawil.org crawled automatically. Today nothing
can."* Its `:70` gives the example `?page=1..860`.

The full specification, every measurement, and the field-by-field design are already in
**`docs/CONTRACTOR-SOURCE.md`**, committed. This file is the order of work.

---

## What is already built (measured, not assumed)

**G1 is live code, not scaffolding.** Nine tables with real writers, HTTP routes, and
behavioural tests:

| piece | where |
|---|---|
| `register_site` / `register_dataset` / `register_field` | `scrapex/catalog.py:147, 240, 309` |
| `save_snapshot` → `generic_page_snapshot` | `scrapex/extract/service.py:74` |
| `approve_candidate` → `generic_record` + `_revision` | `scrapex/extract/service.py:383, 404` |
| HTTP: catalogue (8 routes) + extraction (6 routes) | `scrapex/webui/catalog_api.py`, `scrapex/extract/api.py` |
| tests that assert real behaviour (revisions, Arabic round-trip, rollback, idempotent replay) | `tests/test_extract_storage.py`, `tests/test_extract_api.py`, `tests/test_catalog.py` |

**The seam's two hardest halves are shipped and tested:**
`scrapex/pagesource.py` (`PageSource` protocol, `FetchedPage`, `PageKind`) and
`scrapex/pagewalk.py` (`PageWalker.walk(base_url, scope, *, slice_of, max_requests, on_page)`),
with `scrapex/crawlscope.py` (`CrawlScope`, `plan()`, `is_expensive()`, `SliceRequired`).

**What is missing is exactly three things:**
1. no concrete `PageSource` exists — `PageWalker` has **zero production callers**;
2. the walker is **never wired to `save_snapshot`**, which is the seam doc's central rule;
3. `site_profile.crawl_scope` / `crawl_slice` (`db/engine/migrations/0003_…sql:16-17`) have
   **no reader in Python**.

**The price path stays untouched.** `ExtractKind` is a closed enum of three
(`vocab.py:352`); `ExtractSpec.kind` is typed to it, so the manifest cannot declare a fourth.
`capture_source` (`capture.py:199`) is the price seam and is **not** the seam for this.

## What the site actually is (measured 2026-08-16)

| | |
|---|---|
| robots.txt | `User-agent: *` → `Allow: /`, no `Crawl-delay`. Nine AI crawlers named; **ScrapeX is none of them and is permitted** |
| Cloudflare | present and **does not block** — HTTP 200, full bodies, no interstitial. **`fetcher: http`, no Playwright** |
| listing | `?page=1..865`, **20 rows/page**, no page-size parameter honoured (six tried) |
| **reach** | **≈17,300 contractors** — *not* the 122,785 counter, and **not PLATFORM-PLAN M6's 121,157 estimate.** The public listing exposes only what pagination reaches |
| profile | `/{lang}/contractors/{id}/143` — the segment plays no part in identity but **`143` is what renders the self-build price section** |
| tables | listing has **zero** `<table>`; profile has **5** (licences, prices, contracts, technical rating) |
| coordinates | inline `<script>`, `lat:` / `lng:` — no attribute, no iframe |
| email | **Cloudflare-obfuscated**; `data-cfemail` XOR-decodes. Plain text is nowhere in the source |
| AR vs EN | genuinely two values for membership type, size, city. **The EN page prints the ARABIC address** — there is no English one |
| unavailable | **nine specified columns have no public source**: the five rating criteria, `Customer Rating Grade`, `Company Description`, `Commercial Registration Number` |

## The owner's rulings

1. **A muqawil-specific parser first**, generalised to a card detector later.
2. **`LISTING_ONLY` first**, then widen.
3. **The missing bilingual toggle belongs to the paused B1 work**, not here — «اشياء كثيرة
   مفقودة لذلك توقفت عند b1 … ومنها ايضا هذه المشكلة».

---

## The steps

### 1 · `MuqawilPageSource` — the seam's missing step 3
**New:** `scrapex/sites/muqawil.py`. Implements the `PageSource` protocol from
`scrapex/pagesource.py` — **only** `listing_urls`, `detail_urls`, `belongs_to_slice`. It may
not touch the database or count requests; that is the walker's job (`pagesource.py:78`).

- `listing_urls(base)` → `?page=1..N`, N read from page 1's pagination, both locales.
- `detail_urls(page)` → hrefs matching `/(en|ar)/contractors/(\d+)/143`, deduped by id.
- `belongs_to_slice(page, row_index, slice_of)` → city, which the **listing** publishes —
  the whole point of the method (`GENERIC-FETCH-SEAM.md:75`).

**Fixtures, not network.** Commit trimmed HTML for one listing page and one profile per
language under `tests/fixtures/muqawil/`.

### 2 · The muqawil parser
**New:** `scrapex/extract/muqawil.py`, **beside** `html_table.py`, not replacing it — the
profile's five `<table>`s go through the existing `detect_html_tables`.

Two guards, because both failures are silent:
- **`data-cfemail` must be decoded.** Otherwise every contractor stores the literal
  `[email protected]` and any "is the column populated" test passes forever.
- **`lat:`/`lng:` come from an inline script.** A script change yields NULLs and no error.

Assert a decoded address and a plausible coordinate — never mere presence.

### 3 · Wire the walker to `save_snapshot` — the seam's missing step 4
**Edit:** `scrapex/pagewalk.py`'s caller (new, small) — read `crawl_scope` / `crawl_slice`
off `site_profile` (nothing reads them today), call `crawlscope.plan()` rather than
re-checking the scope, and hand every page straight to
`scrapex/extract/service.py:save_snapshot`, **unparsed**.

The rule to keep: *one page in, one `save_snapshot` out.* A wrong parse is then re-run
against stored snapshots with **nothing re-fetched** — which on 1,730 pages is the product.

### 4 · Stage the crawl like `GPP_ENERGY`
Follow `scrapex/connectors/gpp.py`: one unit per page, tokenised; **a failed page is
deliberately NOT tokenised** so a resume retries it (`gpp.py:302`); an **empty tokenised**
unit carries a warning while still advancing the checkpoint (`:309`); `CrawlBlocked` is
re-raised, never swallowed (`:290`).

- **Stage A — `LISTING_ONLY`.** 865 pages × 2 locales = **1,730 requests, ~30 minutes.**
  Token `LIST--{n}`; EN and AR fetched as a pair and merged on the id from the href.
- **Stage B — later.** `LISTING_PLUS_SLICE` (one city) to prove the profile path cheaply,
  then `FULL_THEN_LISTING` (~34,600 requests, ~10 h).

**Unlike GPP, the denominator is knowable** — page 1 declares 865 — so `declare_frontier`
gives a real progress bar. GPP declines one only because its frontier grows.

### 5 · Register the dataset, then approve
`catalog.register_site("muqawil.org")` → `register_dataset(dataset_key="contractors")` →
one `register_field` per field in `docs/CONTRACTOR-SOURCE.md`'s table. Then
`approve_candidate` writes one `generic_record` per contractor, `record_key` = contractor id,
body in `data_json`.

- The five hierarchical groups are **JSON inside `data_json`** — one table, as he asked;
  `field_definition.data_type` already admits `json`.
- Bilingual pairs are **derived** from the `_ar` suffix, never a hand-written list like
  `reports.BILINGUAL_COLUMNS`.
- Change detection is `generic_record.content_hash`; unchanged ⇒ `last_seen_at` only, no
  revision. The price append gate has no meaning here.

### 6 · Only then, the flags
`scrapex/features.py:52-63` gates `generic_extraction` on *"an approved non-product
extraction reaching generic storage."* Stage A satisfies it. Flip it in the same commit as
the first successful run — not before.

---

## Verification

1. `pytest tests/test_muqawil_pagesource.py tests/test_muqawil_parser.py` — fixture-driven,
   no network. Includes the two silent-failure guards.
2. Mutation-test each guard (break `data-cfemail` decoding; break the `lat:` read; drop
   `/143`) and confirm each fails. House standard.
3. `pytest -m extension` and the full suite with `SCRAPEX_FULL_MIGRATIONS=1` — unchanged
   counts prove the price path was not touched.
4. One live **`LISTING_ONLY`** run, paced at the owner's setting. Then pause it mid-run and
   resume, proving no page is re-fetched.
5. `GET /api/general/extract/datasets/{id}/records` returns contractors with Arabic and
   English side by side.

## Open, and the owner's to rule on

- **`Main Contractors` / `Subcontractors` as JSON or as a real edge table.** JSON cannot
  answer *"who subcontracts for X"*; `dataset_relationship` exists for exactly that.
  Deferred, not dismissed.
- **Does a generic crawl share the price job queue?** `GENERIC-FETCH-SEAM.md:169` asks this
  and it is still unanswered. Stage A can run outside it; Stage B probably cannot.
- **PLATFORM-PLAN M6 says 121,157 detail pages; measurement says ~17,300.** Either the
  listing hides most members or the estimate was the membership counter. Worth settling
  before Stage B is costed.
- **The nine unavailable columns** stay in the field list as nullable rather than being
  dropped — a column that exists and is empty is a fact; one quietly removed is a question
  nobody asks.
