# Source register — every source, and what is actually finished

For the **developer**. Opened **2026-07-31** on the owner's instruction: «اعمل ملف يضم كل
المصادر (للمطور) بحيث يقدر يتابع ما تم انجازه … قسم الملف مصادر تبع نظام price capture واخرى
general» — *make a file holding every source, for the developer, so he can follow what has
been accomplished … split the file into sources belonging to the price capture system and
others to general.*

**Where this sits among the four files, so none of them is read as the wrong thing:**

| file | what it is | authority |
|---|---|---|
| `sources.yaml` | the extraction **contract** — nothing is collected that is not declared there (SR-13) | the only file the code reads |
| `docs/BACKLOG.md` | project **state** — open problems, decisions, IDs (`OP-`, `DEC-`, `BV-`, `Q-`) | the tracking document |
| `docs/CANDIDATE-SOURCES.md` | the **queue** of sites the owner has sent that nobody has probed | holding pen |
| **this file** | the per-source **scoreboard**: what shipped, what is open, which system it belongs to | derived — see below |

**This file is derived, not authoritative.** Every column was read out of the manifest,
the connector directory or `BACKLOG.md` on 2026-07-31 and carries its `file:line`. When it
disagrees with `sources.yaml`, the manifest is right and this file is stale.

---

## What "price capture" and "generic extraction" actually divide

They are two **isolated SQLite databases**, not two labels. Different `application_id`,
required `database_kind` markers, independent migration ledgers, checksums, locks, backup
and restore. No `ATTACH`, no cross-database foreign key, no distributed transaction; each
refuses a file belonging to the other (`docs/db1-domain-database-isolation.md:1-15`,
`scrapex/databases/domain.py`).

| | **price capture** | **General** |
|---|---|---|
| file | `~/.scrapex/engine/scrapex-engine.db` | `~/.scrapex/engine/scrapex-engine.db` |
| owns | the product and price path — products, offers, price observations, commodity prices | generic **site and dataset definitions**: `site_profile`, `dataset_definition`, `field_definition`, `dataset_relationship` |
| a source there means | a shop or publisher whose **prices** we record | an arbitrary site whose **structures** are described — tables, lists, detail records, trees |
| shipped? | yes — `price_tracking` enabled, stage `partial` (`features.py:44-51`) | **definitions and API only.** `generic_dataset_catalog` **disabled**, stage `foundation` (`features.py:52-57`) |

**So the split has a lopsided answer today, and that is the finding, not a gap in this
file: all 11 declared sources are price capture sources. General has none.** It cannot
usefully have one yet — `generic_extraction` is `not_started` and enabled "only after an
approved non-product extraction reaches generic storage" (`features.py:58-63`), and
`generic_dataset_catalog` may be switched on only after generic **row** storage and the
catalogue UI ship (`docs/GENERIC_CATALOG.md:44-48`). A site registered in General right
now would hold a description of itself and not one row of data.

---

## 1. price capture sources — the eleven

### 1.1 Scoreboard

`A` = `active` in the manifest (scheduled runs only — a manual run from the panel is never
gated). All eleven have a connector **and** its tests: that part is done, uniformly.

| source | AR | family | connector · tests | A | cur/region | VAT | extracts | min rows / max drop |
|---|---|---|---|---|---|---|---|---|
| **MADAR** | المدار | `magento-graphql` | `magento.py` · `test_magento.py` | ✗ | SAR / SA | `incl` | prices + enrichment | 50 / 50% |
| **ALSWEED** | السويد | `salla-html` | `salla.py` · `test_salla.py` | ✓ | SAR / SA | `incl` | prices + enrichment | 50 / 50% |
| **ELBUROJ** | البروج | `salla-html` | `salla.py` · `test_salla.py` | ✗ | SAR / SA | `incl` | prices + enrichment | 20 / 50% |
| **ADVANCEDCASTLE** | القلعة المتقدمة | `zid-html` | `zid.py` · `test_zid.py` | ✓ | SAR / SA | `incl` | prices + enrichment | 20 / 50% |
| **ELSEWEDYSHOP** | السويدي شوب | `shopify-json` | `shopify.py` · `test_shopify.py` | ✓ | EGP / EG | `incl` | prices + enrichment | 50 / 50% |
| **MASDAR** | مصدر | `hybris-occ` | `hybris.py` · `test_hybris.py` | ✓ | SAR / SA | `incl` | prices + enrichment | 200 / 50% |
| **SIKAEGSHOP** | سيكا مصر شوب | `custom-json-api` | `custom_json.py` · `test_customjson.py` | ✗ | EGP / EG | **`excl`** | prices + enrichment | 30 / 50% |
| **HEIDELBERG_EG** | هايدلبرج ماتيريالز مصر | `heidelberg-price-matrix` | `heidelberg.py` · `test_heidelberg.py` | ✗ | EGP / EG | `incl` | prices + enrichment | 60 / 40% |
| **SAMEHGABRIEL** | سامح جبرائيل | `woocommerce-storeapi` | `woocommerce.py` · `test_woocommerce.py` | ✓ | EGP / EG | `incl` | prices + enrichment | 10 / **30%** |
| **GPP_ENERGY** | أسعار الطاقة العالمية | `static-html-table` | `gpp.py` · `test_gpp.py` | ✓ | USD *(fallback)* / `*` | `incl` | **commodity only** | 150 / **20%** |
| **ARAMCO_FUEL_SA** | أرامكو السعودية | `aramco-fuel-page` | `aramco.py` · `test_aramco.py` | ✓ | SAR / SA | `incl` | **commodity only** | 4 / 50% |

Counts: **7 active, 4 not** · 9 shops, 1 aggregator (GPP), 1 official (ARAMCO) · 6 Saudi,
5 Egyptian · 9 product sources, 2 commodity sources · **10 connectors** for 11 sources —
`salla.py` serves ALSWEED and ELBUROJ, which is why a Salla fix is a two-source fix.

> **Read the `A` column with OP-2 in hand.** On 2026-07-29 there were *three* different
> answers to "which sources are active": `main`, an **uncommitted** `sources.yaml`, and
> `source_site.active` in the live warehouse, which said all of them. The tree is clean at
> 2026-07-31, so the column above is now single-valued — it is main's. Whether the live
> warehouse still disagrees is **not measured here**; OP-2 and **Q-11** stay open.

### 1.2 Per source — what is finished, what is open

**MADAR** · `sources.yaml:22` — Price semantics settled per product **shape**, and settled
without arithmetic: SimpleProduct (399) and GroupedProduct (33) store `vat_included=1`,
ConfigurableProduct (328) carries `vat_included=0` because the shop's own API hands back
the figure it names `finalPriceExclTaxKey`. Two source-wide uplifts were tried and removed;
the second removal deleted 3,312 prices no madar page had ever printed. GroupedProduct
stores one row per member, 28/28 matched.
*Open:* business-segment prices and per-branch availability need a session capture, not a
connector change — **DEC-6**. Not active.

**ALSWEED** · `:115` — Live since the Salla connector landed. Enrichment contracted
2026-07-30, closing 1,203 products that had landed with no picture while every page
published one (15/15 sampled live).
*Open:* variant prices publish `offers.price=0` in JSON-LD — needs the options XHR or an
extension capture (**DEC-6**). Canonical slug URLs only; short `/-/p{id}` URLs
redirect-loop.

**ELBUROJ** · `:143` — Second Salla source. Enrichment contracted from a **captured
fixture**, with no request made to the live site, because a full crawl was running at the
time.
*Open:* the English-name second pass — **DEC-5**, measured at 3,874 products against
`Crawl-delay: 10` ≈ **eleven hours**. Not active. Its crawl delay is honoured
automatically (SR-8/F5).

**ADVANCEDCASTLE** · `:175` — Needs a browser `user_agent` (403 otherwise), declared in
the manifest. Images: **0/168 → 168/168** products in one crawl after 2026-07-29
(435 image rows, 771 enrichment rows), at zero extra requests — same JSON-LD as the price.
Bilingual: the English alternate is read for `product_name` and `category_path`.
*Settled, do not re-litigate:* the Egyptian price is **deliberately not crawled** — it is a
conversion, not a merchant price (owner-confirmed 2026-07-30, `sources.yaml:242-250`).
*Open:* the page gallery names 124 images against JSON-LD's 109 on a 42-product sample —
reading the gallery too is an owner call.

**ELSEWEDYSHOP** · `:253` — `products.json` + `collections.json` open; `updated_at` drives
change detection. Enrichment costs nothing: 1,442 pictures across all 932 products, every
product covered (live census 2026-07-30).
*Open:* **DEC-2** — shopify cannot resume per page as it stands.

**MASDAR** · `:277` — SAP Hybris OCC v2, data host `api.masdaronline.com` ≠ storefront.
1,354 SKUs from one `fields=FULL` search; real EAN/GTIN. `vat_mode` was **backwards** until
2026-07-20 and is now derived from the payload rather than trusted from the line. Pictures:
560 of 640 priced products, three sizes, same response.
*Open:* **OP-10** — nine English names missing on a bilingual source (SR-2 makes that a
defect, not a nicety).

**SIKAEGSHOP** · `:325` — The one **`excl`** source: the listing is net and the cart adds
14%, owner-verified in the shop's own cart. `specail_price` (78/87) is a **trade tier** for
`customerTypeId 2`, carried as enrichment and never as a discount; `flash_sale_price` is a
nullable number, null on all 87. Enrichment knowingly costs **87 extra requests** (8 → 95
per crawl) because the list publishes one attachment of eleven and no SKU at all.
*Open:* **DEC-3** the interruption rescue cannot survive an interruption · **DEC-6** the
trade tier an anonymous crawl can never be charged · **BV-4** trade tier reaching the
warehouse is built, not verified. Not active.

**HEIDELBERG_EG** · `:389` — The heaviest contract and the newest: **three hosts**. The
storefront is a static Angular app that 404s every API path, so `api.base_url` is declared
rather than guessed; a **third** host carries the only real taxonomy (5 cement families,
both languages) because the store API's own `productTypes` has two values and all 9
products are `Bagged`. Price is not a number on a product but a row in a matrix keyed by
governorate, plant, quantity tier and segment — which is why `custom-json-api` could not
serve it. VAT 14% inclusive, proven transitively from the cart's own arithmetic; the
`statement_url` is the content-hashed **bundle**, deliberately, and will change on redeploy.
Whole source = **3 requests, ~16 seconds**, one 19 MB body.
*Open:* recon questions **Q-1…Q-5** (`docs/recon/heidelberg-materials-eg.md`) · raising
`authority` from `shop` to `official` is the owner's call. Not active.

**SAMEHGABRIEL** · `:540` — WooCommerce Store API; attributes, categories, tags and
measurements ride the price response.
*Open:* **split-brain domain** — the homepage serves advancedcastle content and the shop
may be mid-migration to Zid. `max_drop_pct: 30` is deliberately tight so the migration
announces itself by failing a run loudly.

**GPP_ENERGY** · `:567` — 5 weekly pages, ~180 countries × 5 energy types.
`scope: latest_only` is a **licence obligation** (SR-14, tested T6): the latest published
price only, never their paid historical series — our history accumulates from our own
weekly observations. One tax rule per **energy type**, each read off that type's own page.
`ELECTRICITY_BUSINESS` was added after the connector had defined it for a manifest that
never contracted it — ~125 rows nobody was collecting. `currency: USD` is a **fallback**
covering only the site's own USD conversions, marked `price_basis=converted`; fuel rows
carry the currency each country page prints.
*Open:* **OP-3** — five currencies have no exchange rate after a page-shape change ·
positional parsing must assert `len(labels)==len(values)` (**Q4**).

**ARAMCO_FUEL_SA** · `:665` — The only `official` source, monthly. Parses the Arabic retail
fuels page from **reading-order text, not selectors** (React class names churn, the words
do not); the heading month is the source's own dating and rides `source_date`.
Publishes 91/95/98, diesel, kerosene — **not LPG**. Writes Saudi fuel rows only.

### 1.3 Cross-source work that is nobody's single source

- **DEC-6 · authenticated capture** — MADAR's business segment, ALSWEED's variants,
  SIKAEGSHOP's trade tier. All three need an **extension session capture**; none is a
  connector change. Decided in principle, unbuilt.
- **DEC-5 · Sika datasheets** want a connector of their own. The family exists in the
  vocabulary (`datasheet-enrichment`) with **no builder**, so no manifest entry may declare
  it — `test_no_manifest_entry_declares_a_family_nothing_can_build` enforces that. What the
  source is and why the old entry was removed live in `BACKLOG.md` DEC-5; the stale header
  comment it left above ARAMCO_FUEL_SA in `sources.yaml` is gone.
- **SR-2 bilingual debt** — OP-9 (154 names with no Arabic character in the Arabic column),
  OP-10 (MASDAR), OP-11 (2,385 attribute rows with no language mark).

---

## 2. General sources — none yet

**Zero sources, and it is the deliberate state, not an omission.** What exists: the
definition tables, their triggers and a typed local API at `/api/catalog`
(`docs/GENERIC_CATALOG.md`, `scrapex/catalog.py`). What does not: generic **row** storage,
the catalogue workflow and its UI, discovery with limits and checkpoint recovery.

Three flags gate it, all off (`scrapex/features.py:52-75`):
`generic_dataset_catalog` *foundation* · `generic_extraction` *not_started* ·
`crawl_frontier` *not_started* · `site_data_model` *not_started*.

A site belongs here — not in price capture — when what we want from it is **not a product
price**: a statistics table, a specification list, a registry, a document index. When such
a site arrives, it waits in `CANDIDATE-SOURCES.md` and its row says General; it cannot be
made to produce data by declaring it.

Notes for whoever opens this section: definitions are **additive** — a disappeared one is
retired with `valid_to`, never deleted or reused for a different meaning. Discovery may
only create relationships with `review_status = suggested`; there is intentionally no
auto-confirm endpoint. `site_profile` may optionally link to an existing price
`source_site`, which is how one site can be described in General while its prices live in
price capture.

---

## 3. Not yet assigned to either system

**37 unprobed hosts, 3 leads with no URL, all sent 2026-07-31 except `TABLER`.** No request
has been made to any of these hosts. The row-by-row detail and the open questions live in
`docs/CANDIDATE-SOURCES.md`, which is the **authority for this section** — what follows is
the developer's view of it: how much work each group implies.

They arrived as two differently-shaped batches, and the shape matters more than the count.
**Queue A** is 15 individual shop-like leads. **Queue B** is a deliberate **coverage
matrix** — *material × country* across EG · SA · AE · QA · KW · BH · OM, for fuel, cement,
steel/rebar and bitumen, plus Egypt's official building-materials price bulletin. Two
entries in it are **already known to the project**: `aramco.com` is the live source
`ARAMCO_FUEL_SA` (so B1·SA is done, and the only new thing there is that the owner sent the
`/en/` path while the manifest reads `/ar/`), and `khamato.com` is Queue A #1.

### The five things Queue B changes for the developer

**1 · `authority` stops being a dormant column and becomes the publish mechanism.** Nine of
the eleven existing sources are shops, so the trust tier has rarely had to decide anything.
Queue B brings **seven government or state-owned publishers** — `petroleum.gov.eg`,
`moci.gov.qa`, `psa.gov.qa`, `mhuc.gov.eg`, `qatarenergy.qa`, `kpc.com.kw`, `oq.com` —
alongside shops and platforms selling **the same material in the same country**. Diesel in
Egypt and cement in Qatar will arrive from a ministry *and* a shop, and `authority` is the
field that decides which figure reaches the sheet. That is the role SR-4 already settled for
exchange rates; it now has to be settled for prices, and it is **Q-A**, an owner decision.

**2 · Nine sites publish no price at all**, five of them stated outright by the owner as
RFQ-only (`qatarcement`, `kuwaitcement`, `falcon-cement`, `raysutcement`, `occ`) and four
flagged *maybe* (`cmbegypt`, `polygroup-eg`, `nile-cement`, plus whatever B4/B5 turn out to
be). Each is an **enrichment-only** source, a General site, or not a source — and the
enrichment reading needs `datasheet-enrichment`, **declared with no builder** and already
wanted by **DEC-5**. **That single unbuilt family is now the most-demanded missing piece in
the queue.**

**3 · Two sites publish a price RANGE and the row has one `price` column** — `youmats`
(bag-price range) and `elkayansteel` (36,200–40,369 EGP/tonne, daily). `COMMODITY_PRICE`
has no min/max pair (`rowspec.py:249-304`); storing a midpoint would be arithmetic no page
ever printed, which is MADAR's uplift mistake again (SR-1, SR-3). **This is a schema
decision that has to precede the connector, not follow it** — **Q-G**.

**4 · The commodity path already generalises past fuel — verified, and it is the good news.**
`material_key` is not a closed enum but a free-form UPPER_SNAKE_CASE column
(`config.py:47-53`) fenced per source by its own `materials` list at ingest
(`ingest.py:92`), so Qatar's `BITUMEN_60_70` is a **manifest declaration with no migration
and no code change**. The row already carries `unit`, `material_label`/`material_label_ar`,
`tax_included` with `tax_evidence`, and `official_source_name`/`official_source_link` — a
field built for "Source: Ministry of …" publishers exactly like these.

**5 · One thing genuinely does not exist: reading a document.** Egypt's bulletin
(`img.mhuc.gov.eg`, Arabic-path index) is published as **files**, and a search of `scrapex/`
for PDF handling finds one prose comment about Sika's datasheets and no code. That is a new
family plus a file reader. Its *back-issues*, though, are **not** a new problem:
`COMMODITY_PRICE` already separates `provenance` `'observed'` from `'reported'` with
`as_of_date` and `source_date`, written for GPP's own published history
(`rowspec.py:284-292`). SR-6 and SR-14 forbid letting a source's series pass for our
observations — `provenance` is how they stay apart, not a ban on reading one. **Q-K**.

*Also:* Queue B adds AED, QAR, KWD, BHD and OMR to a manifest that has only SAR, EGP and USD
today, and the probe's TLD map has no `om` or `bh` (`probe.py:17`) so the two `.om` producers
would come back `default_region: *` — **Q-J**, a two-entry dictionary fix nobody should
mistake for a fact about those sites.

### Queue A, by the system the owner designated

**Designated price capture — 10.** `bulk.khamato.com` · `bnaia.com` · `sphinx-store.com` ·
`cmbegypt.com` · `ahrambc.com` · `ahmedelsallab.com` · `sebakashop.com` · `mashreqy.com` ·
`polygroup-eg.com` · `cementegypt.com`
→ *Cheapest outcome:* a probe lands on `salla-html`, `zid-html`, `shopify-json` or
`woocommerce-storeapi` — a manifest entry and a crawl, no new code, because those four are
platforms rather than sites. *Most expensive:* `TBD-probe`, i.e. a bespoke site, which is
one new connector with fixture-backed tests each. **Ten connectors were written for eleven
sources — ELBUROJ is the only source that ever reused one that already existed (§1.1) — so
historically a new source has arrived needing new code far more often than not.** That is
history, not a forecast: the four platform families now in the tree did not exist when the
first source on each arrived, so a queue of shops has a better chance than the record
suggests. It is still the wrong direction to plan optimistically in.
Three of these ten (`cmbegypt`, `polygroup-eg`, plus `nile-cement` below) carry the owner's
*"maybe prices not included"* caveat and join the nine of **Q-F** above.

**Designated General — 3.** `darbuildgroup.com` · `readymixconcreteguide.com` ·
`yellowpages.com.eg`
→ **These are blocked on the product, not on a connector.** General holds definitions only:
generic row storage, the catalogue workflow, its UI and the crawl frontier have not shipped
and all four flags are off (§2, `features.py:52-75`). Probing them is still free and still
worth it — it tells us their shape — but nothing can collect from them until that slice is
built. A directory like `yellowpages.com.eg` is the clearest case of why General exists at
all: records and listings, no product price anywhere.

**System not stated — 2.** `khamato.com` (sent alone, unannotated) ·
`nile-cement.com/en/products/` (`trusted`, maybe no prices, no system — **Q-C**).
→ Left blank on purpose. `khamato.com`'s sibling being a price source suggests price capture
but does not establish it (**Q-D**: the two Khamato hosts may be one source or two, and it
turns on whether they price the same product differently).

**Legacy — 1.** `TABLER`, named in **DEC-5** as never probed; its URL was never written
down anywhere in the repo and needs recovering from the owner.

**One annotation is not yet mapped to anything in the code.** The owner rates sites
`trusted` / `not rated`. The manifest's nearest field is `authority`
(`official`/`aggregator`/`shop`), which is **not a label** — it decides which source wins at
publish, so mapping `trusted` onto `official` would silently outrank existing sources. Held
verbatim, unmapped, until the owner settles **Q-A**.

Sites appear in both this section and the queue only while unassigned; once one becomes a
manifest entry it leaves the queue and gets a row in §1 or §2.

---

## How to keep this file honest

1. A source moves out of §3 only after a **probe with evidence** — never after a guess
   about its platform.
2. A new source lands in §1/§2 as `active: false`. It is activated only when its connector
   is in `_BUILDERS` **and** has tests (ENGINEERING T1/T2).
3. When a `BACKLOG.md` item closes, delete the reference here too — a scoreboard that
   still lists a fixed problem is worse than no scoreboard.
4. Never restate a number here that this file did not measure. Copy the claim **and** its
   `file:line`, so the next reader can check it instead of trusting it.
