# ScrapeX Master Plan — From Owner Tool to Public, Decentralized Price Tracker

This plan reconciles five dimension designs and one adversarial critique into a single buildable path. It is opinionated on purpose: the critic is right that the fatal problem is an **unmade topology decision**, and nothing below can be trusted until that is settled. So it is settled first, explicitly, and everything else follows from it.

Ground truth used throughout (verified, not the inflated design numbers): **~133–144 tests green, exactly one real connector (Shopify), state currently lives in the repo, UI is Arabic.** The plan is honest about this everywhere it matters.

---

## OWNER DECISION (2026-07-18) — Topology **A**, with Python kept as the reference oracle

The study below recommended Topology B (local Python app). **The owner chose Topology A**
(browser-native TypeScript MV3 extension as the public product) — *"A, but leave the current
engine running until the new engine is finished."* This is the wisest way to build A: the
**Python engine stays the golden reference**, and the new TS engine must match it byte-for-byte
before it takes over. The Python engine is NOT touched until the TS engine is done.

**Spike 1 (fingerprint parity — the #1 landmine): PASSED — feasibility proven.**
`spikes/fingerprint-parity/` shows JS reproduces Python's `foldDigits` (8/8) and
`optionFingerprint` (5/5) **byte-identically** for adversarial Arabic input; the ONLY gap is
float serialization (`15.0` vs `15`), closed by a known rule: the fingerprint hashes canonical
shared-`normalize` strings, never a language-native float. The scary Arabic-parity risk is
retired; the landmine is now a closed constraint.

**Revised roadmap under A (supersedes §7's B-roadmap):**
- **Phase 0 — de-risk:** ✅ Spike 1 fingerprint parity DONE. ⏳ Spike 2 = `wa-sqlite`+OPFS
  running `db/schema.sql` verbatim (triggers + view) inside MV3, surviving restart. If it holds,
  A is fully de-risked.
- **Phase 1 — TS engine core:** port connectors(Shopify)+normalize+rowspec+ingest to TS; the
  Python fixtures/vectors become the **shared conformance suite** (CI runs both, byte-parity).
  Warehouse = wa-sqlite over the SAME `schema.sql`.
- **Phase 2 — extension UX:** English UI + Arabic content (`dir="auto"`), user-defined sites in
  per-extension storage, paste→check→preview→track wizard, per-site `optional_host_permissions`,
  `activeTab` DOM capture for JS/login pages (A's unique edge), CSV/xlsx browser-download export.
- **Phase 3 — durability + release:** OPFS backup/restore (guard "clear browsing data"), Web
  Store listing, docs/robots/responsibility notice.
- **Python lane (kept):** stays the reference oracle + the power/CI/owner lane (headless cron,
  Playwright, Google/xlsx publish, mbiX add-in). Sections 2–7 below now describe THIS retained
  Python lane, not the primary public product.

Everything from here down is the study's original B-analysis, retained as the design of the
**Python reference lane** that A is validated against.

---

## 1. Vision + The One Central Decision

### 1.1 The six requirements (restated)

1. **Public** — anyone can download and use it; eventually a store/downloadable product.
2. **User-defined sites** — each user supplies and controls their own link list; not an owner-curated central list.
3. **General, multi-engine scraper** — structured as engines; **price engine is the sole focus now**.
4. **Install & operate** — a clear, easy story for non-technical users.
5. **Decentralized** — every user fully independent; no shared backend, no shared data.
6. **i18n** — UI language is English; Arabic scraped **content** must render correctly (RTL/bidi).

### 1.2 The hardest problem, named

There is no agreed **product topology**, and that one gap forks the language of the engine, where the warehouse physically lives, whether the site list is a portable file, how scheduling works, which UI gets i18n, and which code produces exports. Two candidate answers were authored past each other:

- **(A) Browser-native**: a TypeScript MV3 extension running the engine in-browser over a WASM SQLite (wa-sqlite/OPFS) warehouse (dimension D1).
- **(B) Local app**: a locally-installed Python app serving a FastAPI web UI over a filesystem SQLite warehouse (dimensions D3/D4/D5).

### 1.3 Decision: **Topology B — the local Python app is the primary public product. The extension is an optional capture face, not the engine.**

This is the recommended resolution, and it is not a close call given the actual codebase. The reasoning:

- **The crown jewel only runs verbatim on real SQLite.** `db/schema.sql` — the 13-table model with append-only triggers (`trg_price_obs_no_update/no_delete`), FKs, the EAV attributes, the classification trees, and the `v_material_price_tracking` view — runs unchanged on the SQLite already shipped in Python. Topology A's claim that it "runs verbatim under wa-sqlite/OPFS in an MV3 service-worker" is **an unproven, load-bearing assumption** (D1's own top risk). We would be betting the whole product on a spike that hasn't happened.
- **Topology A silently forces a second implementation of the crown-jewel ingest** (connectors + normalize + ingest + probe → TypeScript). That is the opposite of the DRY seam it claims to honor, and it introduces the single worst landmine in the entire critique:
- **Cross-language hash parity.** `spec_fingerprint`/dedup is `sha256` over `json.dumps(ensure_ascii=False, sort_keys=True, separators=(',',':'))` of text pre-folded by a fixed Arabic-digit map (`normalize.py`). For a **shared append-only price-history** warehouse, the fingerprint must be **byte-identical** between Python and JS for *arbitrary* Arabic input — Python's code-point key sort, float `repr`, and fold order are **not** reproduced by `JSON.stringify` for free. A mismatch **silently forks history / duplicates observations**. A "shared fixture suite" cannot prove parity outside its fixtures. We refuse to take on a silent-corruption risk on the product's core asset.
- **Durability.** OPFS is wiped by "clear browsing data" with **no restore path** into a trigger-protected `price_observation` table. A price-**history** product cannot ship its core asset one settings-click from irrecoverable loss. The filesystem `~/.scrapex/harvest.db` is a normal file the user can copy/back up.
- **Almost everything the vision needs is already built in Python:** local single-writer warehouse, probe, ingest, the `SheetSink` publish path with a zero-credential `LocalSink`, `~/.scrapex` home, no telemetry, per-cell bidi CSS. Topology B **keeps all of it**; Topology A **demotes or re-ports all of it**.

**Consequence for the browser extension:** it stays, but as a **thin optional face** — an "Add this site / capture this tab" convenience that deep-links the current URL into the local web UI and can POST a rendered DOM to the local backend. It is **never required** to use the tool, and it is **not** the engine. This preserves D1's one genuinely unique capability (capturing logged-in / JS-rendered pages via `activeTab`) **without** paying for a second engine, a WASM warehouse, or cross-language hash parity.

**What this decision retires from the critique in one stroke:** the engine-language clash, the two-warehouses-no-sync problem, the portable-YAML-vs-chrome.storage clash, the two-export-codebases clash, the "which UI gets i18n" clash, and the "which language do new connectors use" clash. All collapse to: **Python, filesystem, web UI.**

**Honest cost of choosing B:** we give up the "one-click Add to Chrome, zero install" story. A non-technical user must run an installer (§4). That is a real friction tax, and we pay it deliberately because the alternative risks silent data corruption and betting on an unproven WASM path. We buy the friction down with a double-click PyInstaller executable (§4, §7 Phase E).

---

## 2. Target Architecture

Three orthogonal axes, which today collapse because only the price engine exists:

- **Engine** = scraping *domain* (price / listing / table …) — owns its RowSpec(s), ingest mapper, read model, and schema slice.
- **Family** = site *shape* (shopify-json / salla-html / woocommerce-storeapi …) — a connector.
- **Transport** = `HttpFetcher` / `BrowserFetcher`.

```
User URL ─▶ probe(family) ─▶ [engine chosen in UI] ─▶ connector ─▶ ScrapedTable
              │                                                        │
              └────────── manifest (~/.scrapex/sources.yaml) ─────────┘
ScrapedTable ─▶ normalize ─▶ RowSpec ─▶ FunnelPayload(kind) ─▶ ingest_payloads
      └▶ engine_for_kind(kind).ingest() ─▶ harvest.db (per-user, append-only)
harvest.db ─▶ reports (header, rows) ─▶ SheetSink ─▶ {LocalSink .xlsx | GoogleSink | Browser/CSV}
```

### 2.1 Keep / Adapt / Drop

| Component | Disposition | Notes |
|---|---|---|
| `db.py` + `db/schema.sql` (13 tables, WAL, write-lock, append-only triggers, `v_material_price_tracking`) | **KEEP** | The warehouse. Already per-user at `~/.scrapex/harvest.db`. |
| `rowspec.py` / `payload.py` / `vocab.py` (RowSpec/RowBuilder/RowView + `ExtractKind`) | **KEEP mechanics; ADAPT specs' home** | Mechanics stay core; concrete `PRODUCT_PRICES`/`COMMODITY_PRICE` specs move into the price engine (§3). `ExtractKind` stays a central closed enum. |
| `normalize.py` (Arabic digit/separator folding, `ensure_ascii=False`, fingerprint) | **KEEP** | The single shared parser. **Never** re-implemented in another language. |
| `ingest.py` | **ADAPT** | `ingest_payloads` becomes a registry dispatcher; the product/variant/offer/observation body relocates verbatim into the price engine. Removes the hardcoded `kind != PRODUCT_PRICES` gate. |
| `capture.py` (connector→ingest→db, no funnel) | **KEEP** | Already the default local path used by the web API. |
| `probe.py` | **ADAPT** | Return detected **family** (+reachable/implemented/evidence/notes). Stop hardcoding suggested `kind`; engine is chosen in the UI. Keep the pre-filled `SourceEntry` the wizard needs. |
| `connectors/` (`base.py`, `factory.py`, `shopify.py`) | **KEEP + BUILD** | Registry + polite `HttpFetcher` (1 req/s) + the one real connector. Key builders on `(engine, family)`; only the price column populated now. |
| `publish.py` `SheetSink` + `LocalSink` + `GoogleSink` | **KEEP; ADD** | One publish path. Add a CSV/xlsx **BrowserDownloadSink is not needed** under Topology B — `LocalSink` already writes a real `.xlsx` with no OAuth. |
| `manifest_io.py` (`add_source`, append-only) | **ADAPT** | Grow to atomic CRUD (add/update/remove/pause/set_cadence) via load→validate→temp+rename. |
| `config.py` `MANIFEST_FILE` | **ADAPT** | Relocate from the package to `~/.scrapex/sources.yaml`, seeded empty, with tested copy-on-first-run migration of the owner's list. |
| `webui/app.py` + Jinja templates | **ADAPT** | Flip shell to English LTR; `dir="auto"` on data cells; new 3-step wizard; PATCH/DELETE + `/api/preview`. This is the **primary public UI**. |
| `extension/popup.*` (Arabic thin face) | **ADAPT → optional** | English strings; "Add this tab" deep-link into the local wizard; optional DOM capture POST. **Off the critical path.** |
| `gdrive.py` + Google push | **KEEP → demote** | Optional/advanced output that also feeds the owner's mbiX add-in. Not the public default. |
| `funnel.py` + `apps_script/StagingAppScript.txt` + `FUNNEL_TOKEN` + staging sheet | **DROP from default path; keep dormant** | The central SPOF. The local loop already bypasses it. Retained only as a future opt-in "relay"; not deleted, not on the README happy path. Keep its tests green. |
| `.github/workflows/scrape.yml` (owner cron) + `ci.yml` manifest gate | **KEEP as dev/CI; drop as public default** | Owner self-host lane. Not the public automation story. Keep CI pytest gate. |
| Per-cell bidi CSS (`tabular-nums`, logical margins, Noto Sans Arabic) | **KEEP, re-polarize** | Machinery already exists (§6). |

**Net:** no rewrite. One moved constant, one write-surface upgrade, one new wizard, a thin engine boundary, more connectors, one scheduler. Nothing is thrown away; the funnel and Google path are repositioned, not deleted.

---

## 3. The Engine Model

### 3.1 What an engine is

An **engine is a domain capsule** keyed by the `ExtractKind`(s) it owns:

```
Engine = { connectors it uses } + { its RowSpec(s) } + { its ingest mapper }
       + { its read model } + { its schema slice }
```

The seam already exists: every `FunnelPayload` carries a `kind`; `rowspec.py` defines one canonical RowSpec per kind; `publish.py` consumes `(header, rows)` with zero price knowledge. An engine is simply the natural owner of the ingest+read half that today sits loose in `ingest.py`/`reports.py`.

### 3.2 Build the **thin** boundary now — not the full framework

The critic flagged a real contradiction: D2 wants the full registry + bootstrap + per-engine schema slices + relocation built now; D5 says "name the boundary, no framework" (YAGNI). **Resolution: D5 wins for scope, using D2's shapes.** Concretely, ship in Phase D:

- `scrapex/engines/base.py` — an `Engine` Protocol: `engine_id`, `kinds`, `ingest(conn, entry, payloads)`, `current_table(conn, source_key, limit) -> (header, rows)`, `summary(...)`. The engine **owns its RowSpec internally** (critical: a future "table" engine has user-defined columns, so core must not expose a static RowSpec).
- `scrapex/engines/registry.py` — explicit `register(engine)`, builds `kind → engine`, **raises loudly on a kind claimed twice** (mirrors `ConnectorRegistry`). No autodiscovery (security liability for a public tool).
- `scrapex/engines/bootstrap.py` — one line: `register(PriceEngine())`.
- `scrapex/engines/price/` — `engine.py` (thin wrapper), `ingest.py` (the relocated body, byte-for-byte), `rowspec.py` (the concrete price specs), `read.py` (the price queries).
- `ingest.py`'s `ingest_payloads` → group by kind, dispatch to `engine_for_kind(kind).ingest()`. Keep the **top-level signature stable** so `capture.py`/`cli.py`/`webui` barely move. The existing tests + E2E harness pin the motion.

**Do NOT build engine #2.** It is a design proof, not a deliverable. When a second engine is concretely demanded, it adds one `ExtractKind` member + its schema `CHECK` entry + a numbered migration (`0002_engine_*.sql`) creating only its own prefixed tables (e.g. `listing_*`). Only 3 of ~18 tables are engine-agnostic (`source_site`, `crawl_run`, `raw_snapshot`); the other ~15 are the price engine's private schema. There is **no universal schema** — forcing price concepts (offer, VAT, curation) onto a listing engine would be the wrong abstraction.

**Scope honesty:** this boundary delivers zero user-visible progress on reqs 1–6. It is worth doing only because it is cheap relocation that makes req 3 architecturally true and unblocks a future engine. It sits at Phase D, **after** the user-facing work — not before.

---

## 4. User-Defined Sites, Onboarding, Install & Operate (reqs 2 + 4)

### 4.1 The site list becomes the user's own file

- `MANIFEST_FILE` → `~/.scrapex/sources.yaml`, **seeded empty** on first run. The repo's owner-curated `sources.yaml` (MADAR/ALSWEED/…) is reframed as a **dev fixture / optional import catalog**, never shipped as every user's list.
- **Tested copy-on-first-run migration** so the owner does not silently lose the live supplier list. This is a gating requirement, not a nice-to-have.
- `load_manifest` must become **per-entry resilient**: today one bad entry raises for the whole file. A user-owned, UI-editable manifest cannot tolerate all-or-nothing — skip and surface the bad source, don't crash the UI/CLI.
- `manifest_io` grows from append-only to **atomic CRUD** (load → validate with pydantic → temp+rename). Comment preservation is dropped for the machine-owned file (kept only for the import path). YAML stays (human-inspectable, diffable, portable, hand-off-able — the right property for req 2/5).

### 4.2 The onboarding wizard (English, 3 steps, hides all vocabulary)

`manage.html` is rebuilt as **paste → check → preview → track**. `probe.suggested` already decides `family`, `vat_mode`, `authority`, `scope`, and `source_key`, so the wizard shows only: URL box, friendly name, editable currency/country chips. Everything else is stored under the hood. The old raw form survives behind a collapsed **Advanced** disclosure (power users + manual unknown-site path).

- **Step 2 — Check:** reuse `POST /api/probe` verbatim.
- **Step 3 — Preview (new `/api/preview`):** `build_connector` + a **hard-capped** (~10 rows) streaming fetch + `normalize`, **no ingest**. Proves "does it actually work?" before polluting the warehouse. Must reuse `HttpFetcher`'s throttle and the row cap so "just checking" can never become an unpoliced crawl. This is server-side and stays server-side (Topology B) — no MV3 re-implementation needed.
- **`source_key`** is auto-generated from the host (`probe._key_from_host`), hidden, and auto-suffixed (`_2`) on collision — the wizard catches `DuplicateSourceError` rather than showing a raw 409.

### 4.3 The common case is "not supported yet" — design for it

Only Shopify is implemented. **The amber "coming soon" path is the primary flow, not an edge case.** `probe` already returns `implemented=false` with a friendly note. Honor it: *"This looks like a Salla store — support is coming soon; it's saved to your list and will start collecting once support lands."* Never a dead end, never a lie. Register inactive, light up when the connector ships.

For user-added sites, make the volume canary (`min_expected_rows`/`max_drop_pct`) **lenient or omitted**, so a first run doesn't fail with a confusing canary error.

### 4.4 Install (req 4)

- **Tier 1 (non-technical): a one-file PyInstaller `.exe`** that on launch creates `~/.scrapex` + empty manifest, auto-inits the DB (kill the first-run trap), starts uvicorn on `127.0.0.1`, and opens the browser to "add your first site" (the CLI already does threaded `webbrowser.open`). Budget real time here — PyInstaller + FastAPI + openpyxl on Windows can be fiddly (AV flags, cold-start latency, and unsigned-binary SmartScreen). Code-signing is a real future cost.
- **Tier 2 (technical): `pipx install scrapex`** — the reliable fallback that never fights packaging.
- **Extension (optional):** English strings + "Add this tab" deep-link into the local wizard. Not required, not the primary face, off the install critical path.

### 4.5 Operate (scheduling)

- **Default: an in-app asyncio cadence loop** inside `scrapex ui` — fires `/api/capture` for sources whose cadence is due (`last_run` from `crawl_run` vs interval; ingest is append-only + idempotent). Dependency-free, cross-platform, ships first. Drives a per-site "Check: Manually / Daily / Weekly" dropdown writing `cadence` via `set_cadence`. **Honest caveat: runs only while the app is open — do not market it as "set and forget."**
- **Upgrade: `scrapex schedule install`** registers a per-user OS task (Windows Task Scheduler first; cron/launchd later) running `scrapex run-all` while the app is closed. Platform-specific surface with permission cost — deliberately deferred past first release.
- The owner GitHub Actions cron stays as an advanced self-host option in the dev repo, never the public default.

---

## 5. Decentralization + Storage + Privacy (req 5)

The build is already ~70% decentralization-correct; the gaps are concentrated.

- **Drop the funnel from the shipped product.** `funnel.py` + Apps Script + `FUNNEL_TOKEN` + the owner's staging sheet is the one shared backend (the SPOF). `capture_source()` already does connector→ingest→`harvest.db` under the write lock with zero cloud. The decentralized path is built and proven; the funnel is dead weight against req 5. **Keep it dormant** as a future explicit opt-in "team relay" mode (do not silently re-centralize).
- **Per-user everything.** `~/.scrapex/` is the single predictable data+config root: `harvest.db` + `sources.yaml`. "Delete the folder = uninstall your data." **Zero telemetry** already; state it as an explicit no-egress guarantee and rename anything that reads like phone-home (e.g. the `TelemetryOutbox` naming).
- **Three explicit storage tiers, default = nothing leaves the machine:**
- **(a) Warehouse-only** — DEFAULT. Links and data stay local.
- **(b) Local `.xlsx`** via `LocalSink` — zero-credential, one publish path, real workbook.
- **(c) User's own Google Drive** via `GoogleSink` (`drive.file` least-privilege) — opt-in, advanced.
- Publishing is **always an explicit user action**, never automatic.
- **Google OAuth posture (resolve the three-way tension):** for a first public release, keep the **per-user Google Cloud client as the documented advanced path** and make **local `.xlsx` the default**. A shipped published/verified `drive.file` client (D4) is attractive for reach but adds consent-screen verification, puts the owner's Cloud quota in every user's push path (a req-5 tension and a single point of quota failure), and is not the default output — **defer it** unless/until Drive demand is proven. Google stays valuable for the owner's mbiX add-in lane regardless.
- **Legal/abuse posture:** a decentralized tool removes central curation of *what* users scrape. `HttpFetcher` is polite (1 req/s, honest UA) but does not read `robots.txt`. Before public release, add robots awareness + a plain **"you are responsible for the sites you add"** notice at onboarding.

---

## 6. i18n — English UI, Arabic Content (req 6)

The shell is currently backwards: `<html lang="ar" dir="rtl">` with ~40 inline Arabic labels across the Jinja templates + popup. The data path is already excellent: `normalize.py` folds Arabic-Indic/Eastern digits and Arabic separators locale-invariantly, JSON is `ensure_ascii=False`, everything is UTF-8, and per-cell bidi islands already exist. Because Topology B is settled, **there is exactly one primary UI to retrofit** (the Jinja web UI) — no double-counting, no re-solving bidi in a TS UI.

- **Flip, don't rebuild:** `<html lang="en" dir="ltr">`. Move the ~40 Arabic literals into one strings map (`strings.py` for Jinja context, `strings.js` for the popup) behind a trivial `t()` helper. UI language is **fixed** to English, so **no i18n framework** — explicit over clever, no heavy deps.
- **Re-polarize the bidi machinery.** Today numbers were LTR islands inside an RTL shell; now Arabic product names become RTL islands inside an LTR shell. Set every **content-bearing cell** to `dir="auto"` (browser picks direction per value → mixed Arabic-name/Latin-SKU catalogs render row-by-row correctly). Keep `tabular-nums`, logical `margin-inline-start`, Noto Sans Arabic. `normalize.py` is untouched.
- **The harder half is content, not chrome.** The preview table and site list must render Arabic scraped names RTL with mixed LTR SKUs/prices. Add a couple of Arabic-name fixtures to `test_webui` plus a manual RTL pass so mixed-direction rows don't silently regress. Document the known `dir="auto"` first-strong-character limitation (an Arabic name beginning with a Latin brand token renders LTR) rather than building a custom detector.

---

## 7. Phased Roadmap

Principle: **a working tool at every step; the owner is always the first user; price engine only.** Each phase is independently shippable.

### Phase 0 — De-risk + baseline (smallest next step; do this first)
- **Spike the one thing that could still change the plan:** confirm cross-platform behavior is fine (it is, under B) and lock the topology decision in writing. Under B there is **no wa-sqlite spike and no hash-parity spike** — that entire risk class is retired by choosing Python. This is the payoff of the §1 decision.
- Pin the true test count and connector count in the README (kill the 133/144/"9 families" drift).
- **Outcome:** decision recorded; no code churn; nothing broken.

### Phase A — Relocate state + flip the shell (the foundation flip)
Touches ~2 modules but flips the foundation of **three** requirements at once (5, 2, 6).
- `MANIFEST_FILE` → `~/.scrapex/sources.yaml`, seeded empty, **tested copy-on-first-run** migration of the owner's list.
- `load_manifest` per-entry resilient.
- Auto-init DB on first `ui` launch.
- `<html>` → English LTR; labels → `t()`; data cells → `dir="auto"`.
- **Outcome:** owner keeps working on the same `harvest.db`; a stranger now gets an English UI and an empty list they own. Publishable-shaped, not yet published.

### Phase B — Self-serve site management (req 2 complete)
- `manifest_io` → atomic CRUD.
- Wizard (paste→check→preview→track) with Advanced disclosure; auto-key + auto-suffix; amber "coming soon" as the primary path.
- `/api/preview` (dry, capped, no ingest); PATCH/DELETE `/api/sources`.
- In-app cadence loop + per-site "Check every…" dropdown.
- **Outcome:** a non-technical user adds/edits/removes their own sites and schedules checks without ever opening YAML.

### Phase C — Connector breadth (the credibility gate)
The honest gap: **1 of 9 families implemented.** A Shopify-only public release makes reqs 1–4 hollow.
- Land **WooCommerce Store API** and **Magento GraphQL** (pure `httpx`, already probe-detected; owner sources map to them). Then **Salla/Zid** (likely need `BrowserFetcher`).
- Set public expectations to **"strong on Shopify / Woo / Magento,"** not "scrape anything." Static-HTML-table and custom-JSON need per-site config and cannot be fully self-serve.
- **Outcome:** the amber path stops being the *only* outcome for common stores.

### Phase D — Thin engine boundary (req 3, architecturally true)
- Ship `engines/base.py` + `registry.py` + `bootstrap.py` + `engines/price/` (relocate ingest/read/rowspec **verbatim**, tests pin equivalence). Registry dispatch replaces the hardcoded `PRODUCT_PRICES` gate. `probe` returns family only. **No engine #2.**
- **Outcome:** req 3 is real without a speculative framework; a future engine is a proven seam.

### Phase E — Packaging for non-technical install (req 4 complete)
- One-file PyInstaller `.exe` (create `~/.scrapex`, init DB, launch uvicorn, open browser) + `pipx` fallback. Local `.xlsx` as zero-config default output. Budget for AV/SmartScreen; plan code-signing.
- **Outcome:** double-click → add a site → get an `.xlsx`. This is the first build worth publishing.

### Phase F — Public release
- LICENSE, English docs, `robots.txt` awareness, "you are responsible for what you scrape" notice, privacy/no-egress statement. Optional (later) Chrome Web Store listing for the *optional* extension face — narrowly framed, per-site permissions, no blanket `<all_urls>`.
- **Realistic public-release point: end of F, gated on A + B + C(first two connectors) + E.** Not before. Releasing today would ship an Arabic UI, the owner's supplier list, one connector, and a `git clone`+`pip`+`uvicorn`+sideload install — none of reqs 1–6 would hold for a stranger.

### Deferred (post-F, demand-driven)
- OS-level scheduler (`scrapex schedule install`), published Google OAuth client, funnel "relay" opt-in mode, engine #2, extension DOM-capture for JS/login sites.

---

## 8. Open Decisions for the Owner

1. **Confirm Topology B.** This plan recommends the local Python app as the primary public product with the extension optional. If you instead want the browser-native TS extension as primary, **stop and spike two things first** (wa-sqlite/OPFS running `schema.sql` verbatim in an MV3 worker **and** byte-identical `spec_fingerprint` parity over adversarial Arabic input) — the rest of the plan would need reworking and the ingest would be re-implemented in TS. My strong recommendation is B.

2. **Google Drive posture.** Recommended: local `.xlsx` default, per-user Google client as the advanced path, **defer** shipping a published/verified shared client. Confirm you don't need shared-client reach in v1.

3. **Funnel disposition.** Recommended: drop from the default path, keep dormant. Confirm no real workflow currently aggregates many machines into one warehouse. If one does, we design an explicit opt-in "relay" mode rather than leaving the funnel on the default path.

4. **Minimum connector set for public release.** Recommended: Shopify + WooCommerce + Magento as the "credible" bar (Salla/Zid follow). Confirm which platforms your actual target users paste most, so Phase C is ordered by real demand.

5. **Extension scope.** Recommended: optional English capture face, off the critical path. Confirm you don't want to invest in the Chrome Web Store listing until after Phase F.

6. **Owner-list handling.** The repo's curated `sources.yaml` becomes a dev fixture / optional import catalog. Confirm you want a one-time migration of it into your own `~/.scrapex` (so you keep MADAR/ALSWEED/… as your personal list) rather than shipping it to users.

7. **Scheduling ambition for v1.** Recommended: in-app loop only at launch; OS task deferred. Confirm "runs only while the app is open" is acceptable for the first public build.

---

### One-paragraph honest summary

The engine, warehouse, ingest, probe, publish path, and Arabic-content handling are already built and correct — the gap to "public, decentralized, price tracker" is not the engine, it's three facts: state lives in the repo, the UI is Arabic, and only one of nine advertised connectors is real. Choosing the **local Python app** as the primary topology retires the entire cross-language / WASM / two-warehouses risk class, keeps every built asset, and turns the work into a short, safe, additive sequence: relocate state + flip to English (A), make sites self-serve (B), add two or three connectors (C), name the engine boundary (D), package for double-click install (E), then release (F). The browser extension survives as an optional convenience, the funnel and Google path are repositioned rather than deleted, and the price engine stays the sole focus throughout.