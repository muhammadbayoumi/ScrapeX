# ScrapeX — Prioritized Implementation Plan (from 78 surviving findings)

Verified by direct read before writing this plan: `scrapex/rowspec.py:31-67` (no `unit` on PRODUCT_PRICES; `unit` exists only on COMMODITY_PRICE), `scrapex/ingest.py:222-237` (offer lookup and INSERT never touch `selling_unit_id`), `scrapex/reports.py:228-238` (14-column EXPORT_HEADER, no unit/category/brand), `scrapex/webui/templates/source.html:94-104` (9 literal `<th>`), `db/migrations/` (latest on disk = `0017_field_paging_index.sql`), and repo grep: `selling_unit` appears in only 2 non-test Python lines, both of which *avoid* writing it; `raw_specs_json` / `raw_options_json` have **zero** Python hits.

---

## 0. What is genuinely DONE (do not rebuild — prove it instead)

| Capability | Evidence | Status |
|---|---|---|
| Two-database physical isolation | `scrapex/database_ids.py:3-4`, `databases/domain.py:434-503`, zero `ATTACH` in repo | ALREADY BUILT |
| Append-only price observations + sealed-lineage retention | `db/schema.sql:217-227`, `db/migrations/0011_retention.sql:1-13`, `storage.py:108-117` | ALREADY BUILT |
| VAT incl/excl **flag** end-to-end (manifest→connector→offer→observation→UI) | `vocab.py:108-110` → `sources.yaml:24` → `gpp.py:134` → `rowspec.py:46` → `ingest.py:223,269` → `source.html:101,127` | ALREADY BUILT |
| Regular vs sale price end-to-end | `woocommerce.py:61-78` → `rowspec.py:46-49` → `ingest.py:264-268,514-519` → `source.html:115-119`; `tests/test_woocommerce.py:47-49` | ALREADY BUILT (only discount % missing — derive, never store) |
| Generic dynamic per-dataset table, full workflow | `db/general/migrations/0002_*.sql`, `extract/service.py:216-268,465-500`, `extract/api.py:84-119`, `datasets.html:87,184-200` | ALREADY BUILT (in General, disconnected from MarketLens) |
| Manage-columns (rename/hide/reorder/reset) incl. write-lock + 409 | `fields.py:21-115`, `app.py:483-501,524-557`, consumed via `fields.py:147-162` → `publish.py:46` | ALREADY BUILT (but over a *constant* 14-key header, and export-only) |
| Database-unavailable state (handler + page + banner + tests) | `app.py:153-166`, `database_unavailable.html:7-41`, `tests/test_database_notification.py:46-122` | ALREADY BUILT |
| Extension Run-view Empty/Filtered-empty/Error/Engine-down | `app.js:104,106,148-150,748`; `tests/test_panel_dom.py:205-237` | ALREADY BUILT |
| Workspace empty states on every list page | `overview.html:12`, `history.html:7`, `jobs.html:5`, `review.html:10`, `logs.html:19`, `excel.html:75,98`; `tests/test_workspace.py:146-159` | ALREADY BUILT |
| Bidi / Arabic-as-data direction handling | `app.html:2,176-178`, `components.css:98`, `base.html:2,127`, `dir="auto"` across 10 templates | ALREADY BUILT |
| Status conveyed by text not colour; focus rings; native radio-cards; native `<details>`/`confirm()` | `app.html:207,93-94,334-335`; `components.css:67,77`; `base.html:83,96-97`; `settings.html:17-172` | ALREADY BUILT |
| GPP positional-parse guard + per-page failure isolation | `gpp.py:60-89,143-160`; `tests/test_gpp.py:57,68,76,110,121,142` | ALREADY BUILT |

**Also already in the requested end-state:** SIKAEGSHOP is already `active: false` (`sources.yaml:141-158`). Section 5's ask — "do not treat as an active pricing source" — is *already in effect*. No code change is needed to comply.

---

## 1. Ranked work items

Ranking rule applied: **data-safety and schema-migration first** (everything downstream would be redone without them), then (pain × value) / effort.

### TIER A — Foundation. Nothing below is safe until these land.

**A1. Price-identity re-baseline protocol (design + migration harness) — BLOCKING**
- **Changes:** `scrapex/pricekey.py:37-39` (`PRICE_KEY_VERSION`), new `db/migrations/0018_price_key_rebaseline.sql`, `scrapex/ingest.py:291-294`.
- **Why first:** Four separate items (unit column, `selling_unit_id`, unit-into-pricekey, offer identity) each independently re-key every offer. `ux_source_offer_identity` (`db/schema.sql:182-185`) includes `COALESCE(selling_unit_id,0)`, so the moment a unit is written, existing offers stop matching, fork into new offer rows, and every product in the warehouse emits a phantom "price changed" into an **append-only** table that cannot be undone. Doing this once, deliberately, is the difference between a clean warehouse and permanently corrupt price history.
- **Verified by:** Run a crawl on a source with existing history *before* and *after* the version bump. Query `change_event` for the window: the count of change events must equal the count of *genuine* price movements (cross-check against `v_latest_price` deltas), **not** the row count of the crawl. If every product reports a change, the re-baseline is wrong — stop.

**A2. Migration 0018: seed `selling_unit`, add `tax_rule`, add `price_observation.tax_rate_pct`**
- **Changes:** new `db/migrations/0018_units_and_tax.sql`. Seeds `selling_unit` (`db/schema.sql:39-44`) with `item, tonne, m3, m, m2, kg, liter, kWh, piece, roll`. Creates `tax_rule(tax_rule_id, source_key, region DEFAULT '*', vat_mode, rate_pct NULL, statement_text, statement_url, statement_lang, verified_at, snapshot_id, valid_from, valid_to)` with `UNIQUE(source_key, region) WHERE valid_to IS NULL` — following the temporal convention already used at `db/schema.sql:418-419` and `:252-253`. Adds `price_observation.tax_rate_pct`.
- **Why here:** Purely additive; touches no existing row; `compaction.py:176` copies columns dynamically so the new observation column carries forward for free. Must precede every unit and tax item below.
- **Verified by:** `PRAGMA user_version` = 18 on both a fresh and an existing database; `SELECT count(*) FROM selling_unit` > 0; existing `price_observation` count unchanged; append-only triggers still fire (attempt an UPDATE, expect ABORT).
- **Note:** Also fix or delete the dead `source_site.default_vat_mode` (`db/schema.sql:101`) — production insert at `ingest.py:131-138` omits it, so **MADAR silently reads back `incl` while `sources.yaml:24` says `excl`**. Prefer deleting the column in favour of `tax_rule(region='*')` so tax truth lives in exactly one place.

**A3. Rowspec widening — the cross-engine contract break, done once**
- **Changes:** `scrapex/rowspec.py:33-54` gains `unit`, `basis_quantity`, `category_path`, `category_external_id`, `specs_json`, `options_json`, `locale`, `product_name_en`. Plus `contracts/funnel-payload.schema.json`, the extension payload builder, and **all nine connectors in the same commit**.
- **Why here:** `RowView.__init__` (`rowspec.py:114-119`) fails loud on a header missing spec columns, and `RowBuilder.row` (`:96-98`) rejects unknown fields. So this is atomic: it lands whole or it breaks replay of the local inbox. Every section-1 and section-2 requirement (unit, category, specs, bilingual) is *structurally impossible* until this ships — a connector literally cannot emit a unit today.
- **Verified by:** Replay a previously captured payload from the local inbox after the change. If replay fails, the tolerance path for additive columns is missing. Then run one connector and confirm a `unit` value survives from HTTP response to `source_offer.selling_unit_id` — not to `option_label`.
- **OWNER DECISION required** — see §3, D1.

### TIER B — Make the unit real (the single loudest owner complaint, and mandatory for every source)

**B1. Wire `selling_unit_id` at ingest**
- **Changes:** `scrapex/ingest.py:222-237` — add a resolve-or-create helper mirroring `_get_offer_id`, set `selling_unit_id` on INSERT, and drop the hardcoded `selling_unit_id IS NULL` from the lookup. `ingest.py:398-424` stops stuffing the commodity unit into `option_label`.
- **Why:** MADAR alone has three genuinely different units (item / tonne / m3, per `MADAR_TRACKER_DELIVERY.md:13`). Today a tonne price and an item price are indistinguishable in the warehouse — which defeats the entire purpose of a price comparison product.
- **Verified by:** Crawl MADAR or GPP, then `SELECT unit_code, count(*) FROM source_offer JOIN selling_unit USING(selling_unit_id) GROUP BY 1` returns a non-trivial distribution, and `v_latest_price` (`db/schema.sql:456,473`) returns a non-NULL `su.unit_code` for every row — it is NULL for **every row ever produced** today.
- **Depends on:** A1, A2, A3.

**B2. Fix what feeds the price key**
- **Changes:** `scrapex/ingest.py:291-294` passes the real `unit` to `pricekey.build(unit=...)` and moves `option_label` to the `spec` slot (`pricekey.py:98`).
- **Why:** `IDENTITY_FIELDS` (`pricekey.py:46`) already includes `unit`, but for products the slot is occupied by a colour/size title. The docstring promise at `pricekey.py:14-15` — that 15 USD/litre and 15 USD/gallon are different series — is true for commodities and **false for products**.
- **Verified by:** Change a product's unit on a fixture and confirm a new price period opens (`db/migrations/0016_price_periods.sql`); change only its variant colour and confirm no unit-driven re-key.
- **Depends on:** B1. Must be in the same re-baseline as A1 — do not bump the version twice.

**B3. Surface the unit everywhere a price appears**
- **Changes:** `scrapex/reports.py:217-222` (browse shape) and `:228-239` (EXPORT_HEADER, append at end), `source.html:116`, `changes.html:79,93-94,159-162`, `extension/app.js:374-375`.
- **Why:** Cheap once B1 lands, and it is the *only* part the owner can see. Today the price cell renders `{{ price }} {{ currency }}` with no unit, the changes timeline and min/max summary render no unit at all, and the extension card has no unit row (`grep unit extension/app.js` → zero hits).
- **Verified by:** Open `/source/MADAR` and the extension panel side by side; every price reads `325 SAR / tonne`. Export the tab and confirm a `unit` column with values.
- **Risk:** Do **not** ship B3 before B1 — rendering `option_label` under a "Unit" header would mislabel variant titles as units, which is worse than showing nothing.

### TIER C — Tax evidence (the honesty gap)

**C1. Manifest `tax:` block → `tax_rule` upsert**
- **Changes:** `sources.yaml` per-source optional `tax: {mode, rate_pct, statement_url, statement_text, verified_at, by_region: {...}}`; `scrapex/config.py:113`; whitelist in `scrapex/manifest_io.py:18`; upsert next to `_get_source_id` (`ingest.py:127`).
- **Why:** Today there is **no field anywhere** for a tax statement or its URL — repo-wide grep for `tax_rate|vat_rate|tax_statement|tax_url` returns zero hits. The only rate in the repo is prose: `sources.yaml:29-31`. Ingest has no input channel, so the schema alone is useless.
- **Verified by:** `scrapex validate-manifest` passes with and without the block (must be optional or CI fails every existing source); after a crawl, `SELECT * FROM tax_rule` shows the seeded evidence.
- **Depends on:** A2.

**C2. `resolve_tax(source_key, region)` with `'*'` fallback, called row-level in GPP**
- **Changes:** `scrapex/connectors/gpp.py:134` → per-row lookup inside the `:150-155` loop, with the rules dict cached per run (169 countries × 5 pages — never query per row).
- **Why:** GPP stamps **one manifest-level flag onto ~169 countries** — and because `sources.yaml:181-201` has no `vat_mode` key at all, `config.py:113`'s default applies, so every GPP row asserts `vat_included=1` on a page that makes no such claim. That is ~845 rows carrying a fabricated tax fact, and every downstream comparison inherits it.
- **Verified by:** Crawl GPP; Norway and Egypt rows carry *different* tax states; a country with no rule renders as **"unverified"**, not as a silent assertion.
- **Hard rule:** Never hardcode a country→VAT lookup table in Python. That is an unsourced assertion at 169× scale and directly violates the note. Every rate arrives with a `statement_url` or is stored NULL/unverified.

**C3. Render tax honestly**
- **Changes:** `source.html:101` header → "Tax"; `:127` → `Incl. 15%` with a superscript link to `statement_url` (use `rel=noopener` like `:131`, escape the third-party clause text) and an explicit "unverified" chip when `rate_pct IS NULL`.
- **Verified by:** **This is the acceptance gate for the whole tax slice.** Seed real evidence for exactly TWO sources (one SA shop at 15%, one GPP country), then confirm a crawl produces observations whose *displayed* rate traces by link to a stored clause URL. Per spec §40, a migration plus a route is **not** progress.

### TIER D — Dynamic per-source columns (the note's headline ask)

**D1. Per-source header + dynamic browse table**
- **Changes:** `scrapex/reports.py:209-224` returns rows keyed by `field_key`; `source.html:94-132` renders `{% for c in columns %}` driven by `fields.visible_columns()`; `app.py:206-207` seeds `ensure_fields` from the *per-source computed* header instead of `export_source_table()`'s constant.
- **Why:** The "Manage columns" panel is fully built and works (`fields.py:21-115`) but manages the **same 14 fixed keys for every source**, and hiding a column changes nothing on the screen where it was clicked — only a later `--schema current` export. This is the highest pain-to-effort ratio in the whole review: the machinery exists, it is wired to the wrong input on both ends.
- **Verified by:** Hide "SKU" on a source, reload the page, the column is gone *there*. A commodity source shows no SKU/variant column at all; a WooCommerce source shows both.
- **Keep:** the `SORTABLE` allow-list (`reports.py:176-183`) as the SQL-injection guard. Dynamic headers must be filtered *through* it, never passed into SQL.
- **Cleanup debt:** `ensure_fields` is additive-only by design (`fields.py:36-43`) with no `delete_field`, so stale keys from the old constant will linger in the manage list. Needs a one-time cleanup path.

**D2. Auto-hide empty columns**
- **Changes:** per-source presence query (non-empty count per column over the current-price set), used to seed `dataset_field.is_hidden` **once at first registration**, plus a "Show hidden" toggle.
- **Why:** Direct answer to the review's key question — *yes, empty columns are still shown*, filled with em-dashes (`source.html:110-114`) and empty strings in export (`reports.py:254-258`). No emptiness analysis exists at any layer.
- **Verified by:** Register a commodity source; SKU/variant/brand columns are absent on first render without any manual action.
- **Risk:** Seed once, never recompute per render, or the owner's manual un-hide gets silently overwritten. A column empty today must reappear when next crawl populates it.

**D3. Make saved views actually apply**
- **Changes:** `?view=<name>` on `GET /source/{source_key}`; resolve via `fields.list_views`; chips at `source.html:66-72` become links, not labels; add view as a third schema mode for export.
- **Why:** Saved views can be created and deleted but **nothing ever reads `config_json`** — grep returns only create/list-for-render/delete. A saved view is a stored blob with no consumer; the chip's only interactive element is its `×`.
- **Verified by:** Save a view, navigate away, click the chip, the table projects to those columns; export with that view produces the same columns.
- **Must:** intersect the stored column list against the live header the way `apply_schema` already does at `fields.py:159`, or a stale view breaks the page.

### TIER E — Product attributes (section 2 / MADAR)

**E1. Long-format enrichment row spec + ingest writers into the existing dead tables**
- **Changes:** define `ExtractKind.ENRICHMENT` (declared at `vocab.py:60`, deliberately undefined — `tests/test_rowspec.py:67` asserts `spec_for` raises); columns `external_product_id, attribute_code, raw_value, numeric_value, unit_raw, value_url, lang, group`. Writers upsert `attribute_definition` and `variant_attribute_value`. Populate `source_product.raw_specs_json` / `source_variant.raw_options_json` as the lossless fallback.
- **Why:** `attribute_definition` / `variant_attribute_value` / `material_attribute_value` (`db/schema.sql:230-270`) and `classification_*` (`:278-312`) already have exactly the right shape — and have **exactly one reference in the entire codebase**: `tests/test_schema.py:76-77`, a table-existence assertion. Claiming ScrapeX "has a spec model" today would be precisely the §40 inflation. Reuse, do not clone the owner's 13 sheets — 6 of them are flat-file artifacts, not entities.
- **Also needs:** `value_url` column on the two attribute-value tables (new migration). WooCommerce attribute terms are links by nature — capture the link in the same pass, or re-scrape every product later.
- **Verified by:** Crawl SAMEHGABRIEL; `SELECT count(*) FROM variant_attribute_value` > 0 with real `attribute_code`s (length, voltage, application) and non-NULL `value_url` where the source provides one.

**E2. Stop discarding data the connector already has**
- **Changes:** `scrapex/connectors/woocommerce.py:60-81` emits a second `ScrapedTable` from the same fetch loop (`:41-52`) carrying categories, tags, description, attributes.
- **Why:** **Zero additional network cost** for most of section 2 — the data is already in the response we fetch and thrown on the floor. `tests/fixtures/woocommerce_products.json:16` proves variations/attributes travel in the same payload; the connector never touches that key. `magento.py:29,112` already demonstrates the code/label pattern in-repo.
- **Verified by:** One crawl, no increase in request count, categories and attributes present in the warehouse.
- **Note:** store sanitized description text plus keep raw HTML in `raw_specs_json`/`raw_snapshot` — do not inflate the wire payload.

**E3. Category paths**
- **Changes:** `classification_node` (`db/schema.sql:285-294`) gains `node_name_en`, `node_path`, `node_path_en`; ONE new table `source_product_classification(source_product_id, node_id, is_deepest, is_primary)` — genuinely needed because `material_classification` hangs off `material_id` and census rows have no material until curation. Magento GraphQL query (`magento.py:20-34`) widened to request `categories{uid name url_path breadcrumbs}`.
- **Verified by:** MADAR crawl produces ~66 category paths matching the owner's `rabt_altasnifat` baseline.
- **Must:** rebuild `node_path` from the parent chain each ingest — never trust a stored denormalized path after a site re-parents.

**E4. Bilingual ar/en**
- **Changes:** `stores` list on `SourceEntry` (`config.py:84-118` — note `extra='forbid'` at `:87` rejects it today); Magento `Store` header in `connectors/base.py:101`; `ALTER source_product ADD source_name_en, description_ar, description_en`; `ALTER source_variant ADD option_label_en`.
- **Why:** Column pairs on the existing uid-keyed rows — **no linking table**, because the Magento uid is locale-stable (owner data: `MjNMzM==`-style uid identical across both language sheets). Do not replicate the owner's `rabt_allughat` sheet.
- **Verified by:** One MADAR product row carries both `source_name` (ar) and `source_name_en`, and total product count is **unchanged** — if it doubled, the second pass minted duplicates instead of updating.

### TIER F — GPP correctness

**F1. Capture the price date (S effort, critical value — do this early, it is nearly free)**
- **Changes:** `gpp.py:169-172` currently passes `observed_label=""` — the field intended for it (`rowspec.py:66`) is hardcoded empty. Parse the h1; formats differ (`DD-Mon-YYYY` for fuels, `Month YYYY` for gas/electricity).
- **Why:** Ingest stamps `business_date` = *our crawl date* (`gpp.py:9-11`), which silently mislabels natural-gas data that is 7 months stale (December 2025 data crawled July 2026) as current. The fixture `tests/fixtures/gpp_diesel.html:5` has the date stripped, so no test can ever notice.
- **Verified by:** A natural-gas row's stored source date reads December 2025, not the crawl date.

**F2. Currency conversion is silently assumed** — `gpp.py:35-41,133` hardcode `USD/liter`; the USD list figure is a *user-selectable display view*, not the source price. The per-country page publishes both (USD 0.40 **and** EGP 20.50 per liter). Add `original_price / original_currency / converted_price / conversion_currency / fx_rate / fx_date`. Cost: ~845 extra requests — needs rate limiting and respect for the `latest_only` licence constraint (`gpp.py:8-11`). **Owner decision on crawl budget (D4).**

**F3. Region vs country** — the column named `region` holds the **country ISO code** (`rowspec.py:61`, `gpp.py:98-112`). The field name creates a false impression that region is handled. Rename to `country_iso`, add `geo_region`; the site publishes per-region pages that give region free from the URL.

**F4. Household vs business segment** — electricity and natural gas publish two materially different prices (USD 0.084 vs 0.076 per kWh); the connector stores one, unlabelled (`gpp.py:39-40`). Add `consumer_segment`.

**F5. Unit is asserted, not observed** — `gpp.py:34-41` embeds the unit as a constant and bundles currency into it (`USD` appears in two columns). Parse from the heading, cross-check against the constant, fail loud on mismatch. Split `unit='liter'`, `currency='USD'`.

### TIER G — Source health and routing

**G1. Real source lifecycle state**
- **Changes:** `SourceEntry` gains `status: available|degraded|unavailable|retired` (mirroring `db/general/schema.sql:29-30`); `source_site` gains `last_reachable_at`, `unavailable_reason`, written from the crawl outcome; `/api/sources` (`app.py:379-386`) returns `last_run`/`last_status` (already computed at `reports.py:53-57`, deliberately omitted from the API); overview iterates the **manifest left-joined to the DB**.
- **Why:** Three flags exist, none means "broken". Worse: `reports.py:73` enumerates `SELECT source_key FROM source_site` — a source that never ran has no row, so **it vanishes from the overview entirely** rather than showing as a problem. And `_is_implemented` (`app.py:1299-1300`) is a pure `family in _BUILDERS` check, so the UI badges SIKAEGSHOP green **"Ready"** on the evidence of a Python import. Rename that badge — it currently asserts working extraction it has not verified.
- **Verified by:** Kill a source's site; after N consecutive failures it shows "unavailable" with a reason and a `last_reachable_at`; a never-run source shows "never run" instead of disappearing.
- **Must:** derived state never silently flips `active` — that stays the owner's decision. Needs a consecutive-failure threshold or transient network blips will misfire.

**G2. Replace the hand-authored SIKAEGSHOP fixture** — `tests/fixtures/sikaegshop_products.json` (672 bytes) is synthesized, not captured: wrong envelope key (`products` vs live `success`/`data`/`pagination`), wrong field names (`name_en` vs `product_enname`), suspiciously round values (350/300 vs live 325/206.25), and a row literally named "منتج بدون سعر" that exists only to exercise the `if not effective` skip at `custom_json.py:89`. Git shows one commit, never refreshed. **This is the mechanism by which the connector is green-tested and non-functional simultaneously.** Replace with a byte-for-byte capture; the existing tests will fail immediately — that is the correct outcome, and must not be "fixed" by editing the fixture back toward the code. **Audit the sibling fixtures too.**

### TIER H — Accessibility and screen states (cheap, independent, ship anytime)

**H1. Four click-only `<span>`s → `<button type="button">`** — `app.html:248,631,632,633` with mouse-only listeners (`app.js:846,847,850`). Repo grep for `keydown|keypress|tabindex` across the extension returns **one** hit. These are the only in-panel routes to the workspace, so the Settings tab **dead-ends entirely** for keyboard users. Tag swap only — `.link` is already applied to `<button>` at `app.html:529,607,617,624,638`. **Highest value-to-effort item in the entire review.**

**H2. Focus management** — `.focus()` appears **nowhere** in `extension/app.js` or the whole `scrapex/webui` tree, yet `app.js:46-49,347,622,663` swap entire screens. Worst case `app.js:663`: user presses "Test site", ~15 new fields appear, focus stays on the button, nothing announced. Three targeted fixes: focus the revealed `<section>` (`tabindex="-1"` + `preventScroll`), focus `#f-name` on form reveal, focus the dataset heading and restore to `lastTrigger` on back. **No focus trap needed** — there are no custom modals, only native `confirm()` (`_storage.html:190,208`, `review.html:55`). Do not replace `confirm()` with a custom modal; that would *newly introduce* a focus-trap obligation.

**H3. Auth-Expired state — not built anywhere.** `outputs.py:284` is `Path(TOKEN_PATH).exists()` — a revoked token still reports "connected", `:296-300` returns `ready=True`, `sync.html:157` renders a healthy green panel, and `gdrive.py:56-57`'s unwrapped `creds.refresh()` raises `RefreshError` which `app.py:165-166` does not handle → **raw 500 with a Google traceback**. Fix: three-state token check, typed `GoogleAuthExpiredError`, registered handler, Reconnect action. Never log the token; use the cached expiry claim, not a Google round-trip per page render.

**H4. Live-region and ARIA cleanups** — add `role="status" aria-live="polite"` to `#probe-out` (`app.html:460`, the sole feedback for a multi-second probe); add a *summary line* beside `#sites`/`#records` rather than making the lists live (a 50-row rewrite read aloud on every filter keystroke is worse than silence). Extend `fieldError()` to set `aria-invalid`. Give `#err-key` its own `role="alert"` node split from the help text (`app.html:473-474` — its two siblings have the role, it does not, and the format hint is destroyed on error and never restored). Drop `role="tablist"` from `app.html:663` + add `aria-label="Views"`, matching the webui's correct `base.html:185,198` — the children are not tabs and the views are not tabpanels.

**H5. Promote the `datasets.html` state pattern** (`:14,67,79,95,132-157,316`) into a shared `base.html` macro **before** adding new states, so offline/auth-expired get one implementation instead of twelve.

**H6. Workspace health poll** — `base.html:173-209` shows "Databases healthy" with no polling (`grep setInterval` in `base.html` → nothing). A page open when the database dies keeps asserting health indefinitely. An actively false status is worse than none. The widget and wording exist; only the refresh is missing.

**H7. Test hardening** — nothing faults the engine behind a rendered page, so `review.html:76` and `manage.html:104,119` ("Couldn't reach the engine") are untestable and would be silently deleted by a template refactor. Reuse the `fail_routes` harness (`tests/test_panel_dom.py:40-47`). Also extend `tests/test_workspace.py:146` to the 8 unpinned empty-state strings. (The empty-state test exists precisely because that deletion already happened once.)

---

## 2. Commit slices and ordering constraints

| Slice | Contents | Hard ordering constraint |
|---|---|---|
| **S0** | Owner decisions D1–D6 answered | Blocks S2, S4, S8 |
| **S1** | A2 migration 0018 (units + tax_rule + tax_rate_pct + kill `default_vat_mode`) | **Must precede S2, S3, S4** |
| **S2** | A3 rowspec widening + contracts + extension payload + all 9 connectors | **Atomic — one commit.** After S1. All sources stay inactive. |
| **S3** | A1 re-baseline + B1 + B2 (unit into offer + price key), version bump **once** | After S2. **B2 must not bump the key version separately from A1.** |
| **S4** | B3 unit display: reports + source.html + changes.html + extension | **Strictly after S3** — shipping first mislabels variant titles as units |
| **S5** | C1 manifest tax block → tax_rule upsert | After S1 |
| **S6** | C2 row-level `resolve_tax` in GPP | After S5 |
| **S7** | C3 tax display + unverified chip | After S6. **Acceptance gate for the whole tax arc.** |
| **S8** | D1 dynamic browse table + per-source seed | After S2 (needs per-source header). Independent of tax. |
| **S9** | D2 auto-hide empty + D3 saved views apply | After S8 |
| **S10** | E1 enrichment rowspec + attribute writers + `value_url` migration | After S2 |
| **S11** | E2 WooCommerce second table (zero extra requests) | After S10 |
| **S12** | E3 categories, **S13** E4 bilingual | After S10 |
| **S14** | F1 GPP price date | **Independent — ship any time.** Smallest critical-value item in the plan. |
| **S15** | F5 unit cross-check, **S16** F3 region/country, **S17** F4 segment, **S18** F2 currency | F2 last (largest crawl-budget change) |
| **S19** | G1 source health/lifecycle | Independent |
| **S20** | G2 real fixtures | **Independent — ship first if you want an honest test baseline before anything else** |
| **S21** | H1 (+H2) — keyboard access | **Fully independent. Ship today.** |
| **S22** | H5 shared state macro | **Before** H3/H6 |
| **S23** | H3 auth-expired, **S24** H6 health poll, **S25** H4 ARIA, **S26** H7 tests | After S22 where noted |

**Suggested first three commits:** S21 (H1 keyboard — minutes, real user impact), S20 (G2 real fixtures — establishes an honest baseline), S14 (F1 GPP date — small, critical, isolated). None require an owner decision. Then S0 → S1 → S2.

---

## 3. OWNER DECISIONS (spec §40 — not code choices)

**D1. Widen `PRODUCT_PRICES` in place, or add a second extract kind?**
Widening breaks `RowView` header validation for every already-captured payload and forces all nine connectors to change together. A second long-format `ENRICHMENT` kind keeps the price contract frozen but means two ingest paths. *Recommendation: widen for the small fixed set (unit, basis_quantity, category, locale) — these are price-identity-relevant; use long-format ENRICHMENT for the open-ended spec bag. But this is your call on contract stability.*

**D2. Approve the price-identity re-baseline.**
Populating `selling_unit_id` and fixing the pricekey unit input will re-key every offer in the warehouse. Options: (a) versioned migration with backfill so existing offers map onto their new identity — no phantom changes, more work; (b) accept a one-time "re-baseline" marker where all offers restart their series. *This writes to an append-only table and cannot be undone. It needs an explicit yes.*

**D3. SIKAEGSHOP — what did you actually observe?**
Live checks on 2026-07-20 (two polite requests) found the site **up**: `GET /` → HTTP 200, 14,695 bytes, and `GET /api/products` → HTTP 200 JSON, 16,640 bytes, `{"total":87,"page":1,"totalPages":8}` — matching the 87 products in `sources.yaml`. What a human sees is a Next.js shell whose entire visible text is "Sika Egypt - Construction Chemicals & Solutions **Loading...**" — the catalogue paints client-side, so a browser with blocked/slow JS stays on "Loading..." forever while HTTP still returns 200. **Question: do you mean (a) the storefront UI is broken for humans, or (b) genuinely retire the source?** Marking a working open JSON API "unavailable" would discard a healthy source. Note the requested end-state is already in effect (`active: false`), so nothing needs to change on the note alone. Also note: HTTP 200 cannot settle *commercial* validity — if you know the shop stopped fulfilling orders, that is your call, not something a status code can answer.

**D4. GPP crawl budget.** Local-currency prices and per-country tax evidence require ~845 extra requests (169 countries × 5 fuels). Language variants (~19 locales) and household/business segments multiply further. *How much crawl volume are you willing to spend, and does the `latest_only` licence constraint permit per-country pages?*

**D5. Which column registry wins?** `schema_version_field` (General — genuinely dynamic and versioned, no presentation controls) or `dataset_field` (MarketLens — rename/hide/reorder/saved views, but static). They live in **different databases** and must not be joined across. *Recommendation: keep both, converge only the rendering — give `dataset_field` a per-source seed and reuse `datasets.html`'s dynamic-table renderer. Do not build per-source dynamic columns a third time.*

**D6. Is "move a source from MarketLens to General" ever needed post-activation?**
It cannot be built as a delete: `price_observation` triggers ABORT (`db/schema.sql:217-227`), General has **no price schema at all**, so a moved price source would *lose* its history rather than relocate it, and the 0011 rule requires the predecessor be sealed forever — the move **costs** disk. *Strong recommendation: make domain classification a pre-activation decision and never build a mover. If you insist, it must be a compaction-style rebuild-verify-promote-seal, and the rows are archived, not transferred — say that plainly.*

**D7. Is "Offline" a required UI state?** The spec references offline only as *scheduling* policy (`CLAUDE.md:1078,1100`), not a UI state. The panel-to-engine hop is loopback and must not be gated on `navigator.onLine`. *Confirm whether you want a UI offline state at all, or just verified missed-run scheduling behaviour.*

---

## 4. Not covered / residual risk

- **No live MADAR run exists.** The manifest is well-specified (`sources.yaml:12-38`) but `active: false`, and the only evidence is a 3-row fixture (`tests/test_magento.py:41-60`). The prior tool produced 730 products / 3182 price states / 40k+ spec values. A manifest entry plus a fixture test is **not** a working workflow. `min_expected_rows: 50` is two orders of magnitude too loose — raise it as the acceptance gate. Everything in Tier E is designed against the owner's *sheets*, not against a verified live response; the GraphQL widening may not survive contact with the real endpoint.
- **Enrichment ingest leg does not exist.** `ingest.py:342-345` rejects everything that is not a price kind. A price-free source today ingests into *neither* database. Shipping domain routing before this leg exists would silently discard payloads into `result.errors`. Tier G1 deliberately does not touch routing for this reason.
- **Fixture trustworthiness is unquantified.** G2 establishes that at least one connector fixture was synthesized from memory. I did not audit the other eight. Until that audit runs, **no connector's green tests are evidence that it works against its live site.**
- **Four of five GPP pages have never had their real markup parsed** — `tests/test_gpp.py:33` returns `gpp_diesel.html` for every URL, and electricity/natural-gas pages are structurally different (segments, different period format).
- **`raw_specs_json`, `raw_options_json`, `selling_unit`, `attribute_definition`, `variant_attribute_value`, `material_attribute_value`, `classification_*` are all provisioned and unwritten.** Do not count any of them as progress until a crawl fills them and a screen shows them.
- **Homeless entirely:** applications/uses data, per-row data-quality issues (currently counted into `crawl_run.errors_count` at `ingest.py:364-370` and discarded), and discount percentage (recommend deriving, never storing — a third source of truth can disagree after a price correction; guard divide-by-zero and `regular < effective`).
- **Biggest residual risk:** the Tier A re-baseline. Four items independently re-key offers against an append-only table. If they land piecemeal — or if the version bump is done twice — the warehouse gets phantom price changes that cannot be deleted, only compacted away by building a successor database and sealing the old one. **Land A1+A2+A3+B1+B2 as one deliberate arc, or not yet at all.**
- **Second-biggest:** `source_site.default_vat_mode` currently contradicts the manifest for MADAR. It is latent (observations take the connector's per-row flag, so live data is correct) but any future reader that trusts `source_site` will be wrong for every `excl` source. Fix or delete it in S1 — do not leave it.