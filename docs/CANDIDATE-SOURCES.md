# Candidate sources — the queue, not the contract

Opened **2026-07-31**, on the owner's instruction: «ضيفه فى list واترك امور المعالجة
للمستقبل لكن اريد الاحتفاظ به حتى لا يضيع … اعمل ملف ضيف فيه كل المصادر الى هبعتهالك
وهنبقى نشوف الاداة تقدر تشتغلهم ولا محتاجه تعديل مستقبلا» — *put it in a list and leave
the processing for the future, but I want it kept so it does not get lost; make a file
holding every source I send you, and we will see later whether the tool can run them or
needs changes.*

**This file is a holding pen. It is not `sources.yaml`.** Nothing listed here is declared,
crawled, or promised. SR-13 stands: nothing is collected that is not declared in the
manifest, so a site sits here until somebody deliberately moves it — and moving it is the
work this file exists to defer, not to hide.

**Where a site goes when it leaves:** `docs/SOURCES-REGISTER.md` is the developer's
scoreboard for sources that already exist, split by system (price capture = the product and
price warehouse; General = the generic dataset catalogue, which has no sources yet and
whose extraction features are off). Every row here is also summarised there under
*§3 Not yet assigned*.

**Nothing in this file has been probed. No request has been made to any host in it**, by
ScrapeX or by me. So there is no `platform` column: it is unknown for every row, and the
day a row is probed its status becomes `probed → <family>` with the evidence beside it.

**Every annotation is the owner's own, quoted and not interpreted.** Where he wrote
`trusted` / `not rated`, a blank means he said nothing — which is **not** the same as
`not rated`, a judgement he did make.

**Totals: 37 unprobed hosts · 3 leads with no URL · 2 already known to the project.**

---

## Queue A — individual leads

Sent 2026-07-31 as single URLs with per-site annotations.

| # | site | system | rating | prices? | what is known |
|---|---|---|---|---|---|
| 1 | <https://khamato.com/> | — | — | yes | Later annotated by the owner: «منصة بيع تجزئة/جملة لعدة مصانع» — *a retail/wholesale platform for several factories*, listed under **cement · Egypt** in Queue B. |
| 2 | <https://bulk.khamato.com/> | market | — | — | **Subdomain of #1**, labelled `bulk` — consistent with the wholesale half of that annotation. |
| 3 | <https://bnaia.com/> | market | not rated | — | Nothing fetched. |
| 4 | <https://sphinx-store.com/> | market | not rated | — | Nothing fetched. |
| 5 | <https://www.cmbegypt.com/> | market | **trusted** | **maybe none** | Owner: «market (maybe prices not included)». |
| 6 | <https://ahrambc.com/> | market | not rated | — | Nothing fetched. |
| 7 | <https://www.ahmedelsallab.com/> | market | **trusted** | — | Nothing fetched. |
| 8 | <https://www.sebakashop.com/> | market | not rated | — | Nothing fetched. |
| 9 | <https://mashreqy.com/> | market | **trusted** | — | Nothing fetched. |
| 10 | <https://polygroup-eg.com/> | market | — | **maybe none** | Owner: «market (maybe prices not included)». No rating given. |
| 11 | <https://nile-cement.com/en/products/> | **— not stated** | **trusted** | **maybe none** | Not a homepage: a listing path *and* the `en` locale. The Arabic path is a separate fact to find, never to build from this one (SR-2; precedent at `sources.yaml:422-427`, where the AR and EN aliases of one page share no stem). |
| 12 | <https://darbuildgroup.com/> | **general** | — | — | Nothing fetched. |
| 13 | <https://readymixconcreteguide.com/> | **general** | — | — | Named as a *guide*, consistent with the general designation. |
| 14 | <https://cementegypt.com/> | market | — | — | Nothing fetched. |
| 15 | <https://yellowpages.com.eg/> | **general** | — | — | A business **directory** by name — records and listings, not product prices, which is what General is for. |

*Append, never reorder — the number is how a site is referred to in a later session.*

### Carried in from `BACKLOG.md` DEC-5

| # | site | received | status |
|---|---|---|---|
| 0 | **TABLER** (URL not recorded) | before 2026-07-25 | **not probed.** Named in `plan-closing-the-gaps` §5.4 and DEC-5 as never probed. Its URL is written down nowhere in the repo and needs recovering from the owner. |

---

## Queue B — the coverage matrix

Sent 2026-07-31 in the owner's own structure: **material × country**, with a note on each
site saying whether it publishes a price at all. That structure is preserved rather than
flattened, because it is what makes the *gaps* visible — a flat list hides a missing
country.

Markets: **EG · SA · AE · QA · KW · BH · OM**. Materials so far: **fuel · cement ·
steel/rebar · bitumen**, plus one official price bulletin covering building materials
generally.

### B1 · Fuel / retail energy

| country | site | owner's note | status |
|---|---|---|---|
| EG | <https://www.petroleum.gov.eg> | — | not probed · **ministry** |
| SA | <https://www.aramco.com/en/what-we-do/energy-products/retail-fuels> | — | **ALREADY DECLARED AND ACTIVE — `ARAMCO_FUEL_SA`**, monthly, `authority: official` (`sources.yaml:665`). The manifest reads the **`/ar/`** path, not the `/en/` one sent here. Nothing to add but the EN alternate (SR-2). |
| AE | *لجنة أسعار الوقود الإماراتية* | — | **NO URL GIVEN** |
| QA | <https://www.qatarenergy.qa> | — | not probed · state-owned |
| KW | <https://www.kpc.com.kw> | — | not probed · state-owned |
| BH | *لجنة تسعير ومراقبة الوقود* | — | **NO URL GIVEN** |
| OM | <https://www.oq.com> | — | not probed · state-owned |

### B2 · Cement

| country | site | owner's note | status |
|---|---|---|---|
| EG | <https://www.egyptian-cement.com/products/products-prices> | «أفضل مصدر — منتج مباشر بسعر منشور EGP/طن» — *best source; direct producer with a published EGP/tonne price* | not probed · deep path, straight at the price page |
| EG | <https://www.khamato.com> | «منصة بيع تجزئة/جملة لعدة مصانع» — *a retail/wholesale platform for several factories* | = **Queue A #1/#2** |
| SA | <https://www.youmats.com/building-material/cement> | «منصة موردين حقيقية — نطاق سعر الكيس معلن» — *a real supplier platform; the bag price is published as a RANGE* | not probed · **range, not a price — Q-G** |
| AE | <https://www.fepy.com/building-material/cement-concrete/cement> | «أفضل مصدر — أسعار حية لكل منتج بالدرهم» — *best source; live per-product prices in AED* | not probed |
| QA | <https://www.qatarcement.com> | «المُنتِج المباشر — بدون سعر منشور، طلب عرض سعر» | **NO PUBLISHED PRICE — Q-F** |
| KW | <https://www.kuwaitcement.com> | same | **NO PUBLISHED PRICE — Q-F** |
| BH | <https://www.falcon-cement.com> | same | **NO PUBLISHED PRICE — Q-F** |
| OM | <https://www.raysutcement.om> · <https://www.occ.om> | «المُنتِجان الرئيسيان — بدون سعر منشور، طلب عرض سعر» | **NO PUBLISHED PRICE — Q-F** · `.om` TLD, see Q-J |

### B3 · Steel / rebar

| country | site | owner's note | status |
|---|---|---|---|
| EG | <https://www.ezzsteel.com> | «المُنتِج الأكبر» — *the largest producer* | not probed |
| EG | <https://elkayansteel.com> | «نطاق سعر الطن معلن يوميًا: 36,200–40,369 جنيه» — *the tonne price is published daily as a range* | not probed · **range, and DAILY — Q-G** |
| SA | <https://www.youmats.com/steel-iron/reinforcing-iron> | «نفس منصة الأسمنت — أسعار حديد لكل صنف وسمك ظاهرة» | **SAME HOST as B2·SA — Q-H** |
| AE | <https://www.fepy.com/building-material/steel-rebar-accessories/rebar> | «نفس منصة الأسمنت — سعر الطن ظاهر فعليًا شامل الضريبة» — *tonne price actually shown, VAT included* | **SAME HOST as B2·AE — Q-H** · a stated tax position |
| QA | <https://www.qatarsteel.com.qa> | «المُنتِج المباشر» | not probed |
| QA | <https://www.teyseerbm.com/principals/qatar-steel> | «موزّع معتمد لقطر ستيل والأسمنت الوطنية» — *authorised distributor for Qatar Steel and the National Cement Co.* | not probed · a **distributor** standing in for two producers — `authority` question (Q-A) |
| KW | <https://www.kwtsteel.com> | «المُنتِج المباشر» | not probed |
| BH | <https://foulath.com> | «مجموعة فولاذ — SULB للحديد الإنشائي» | not probed |
| OM | <https://jazeerasteel.com> | «الجزيرة للحديد — المُنتِج الرئيسي» | not probed |

### B4 · Bitumen — Qatar, official statistics

| country | site | owner's note | status |
|---|---|---|---|
| QA | <https://moci.gov.qa> · <https://psa.gov.qa> | «بيتومين اختراق 60/70» — *penetration bitumen 60/70* | not probed · **ministry + national statistics authority.** A material grade, not a product — see Q-I, which is the good news in this batch. |

### B5 · Egypt — the official building-materials price bulletin

| country | site | what the owner gave | status |
|---|---|---|---|
| EG | `img.mhuc.gov.eg` · index: `mhuc.gov.eg/أرشيف_نشرة_أسعار_مواد_البناء` | the **archive** of the housing ministry's building-materials price bulletin | not probed · **a document archive, not a page — Q-K.** Two hosts: an index page and the `img.` host the files sit on. The index path is **non-ASCII Arabic**, so it needs percent-encoding handled end to end. |

### Leads with no URL

| lead | what is needed |
|---|---|
| «اسعار مواد البناء **القاول** السعودية» — Saudi building-materials prices | **Q-L** — the URL, and what «القاول» names: a site, a platform, a publication, or *المقاول* (the contractor) as a category. Recorded verbatim because guessing which would be inventing a source. |
| UAE — *لجنة أسعار الوقود الإماراتية* (fuel pricing committee) | the URL |
| Bahrain — *لجنة تسعير ومراقبة الوقود* (fuel pricing and monitoring committee) | the URL |

---

## Questions — none of them answerable by guessing

**Q-A · Does «trusted» mean `authority`? This batch makes it urgent.** The manifest's trust
tier has exactly three legal values — `official`, `aggregator`, `shop` (`vocab.py:38-43`) —
and it is **not a label: `authority` decides which source wins at publish.** Until now that
column barely mattered, because nine of eleven sources were shops. Queue B changes that: it
brings **seven government or state-owned publishers** (`petroleum.gov.eg`, `moci.gov.qa`,
`psa.gov.qa`, `mhuc.gov.eg`, `qatarenergy.qa`, `kpc.com.kw`, `oq.com`) alongside shops and
platforms selling **the same materials in the same countries**. So diesel in Egypt, or
cement in Qatar, will arrive from a ministry *and* a shop, and `authority` is the mechanism
that decides which figure the sheet publishes — exactly the role SR-4 already settled for
exchange rates. Also unsettled by the same question: `teyseerbm.com` is a **distributor**
speaking for two producers, which is neither `official` nor plainly `shop`.
Held verbatim, unmapped, until the owner rules.

**Q-F · Nine sites publish no price, and the owner already knows.** Five say so outright —
`qatarcement`, `kuwaitcement`, `falcon-cement`, `raysutcement`, `occ`, all «بدون سعر منشور،
طلب عرض سعر» (*RFQ only*) — and four more are flagged *maybe*: `cmbegypt`, `polygroup-eg`,
`nile-cement`, plus whatever B4/B5 turn out to be. **A site with no published price has
nothing this warehouse can store as a price**, and inventing one from an RFQ is the exact
thing SR-1 forbids. Each is therefore one of: an **enrichment-only** source (specs,
datasheets, technical data attached to products priced elsewhere) — the
`datasheet-enrichment` family, declared at `vocab.py:363` with **no builder** in
`factory.py` and already wanted by **DEC-5**; a **General** site; or not a source at all.
**Nine sites now wait on that one unbuilt family, which makes it the most-demanded missing
piece in the whole queue.** A probe can confirm no price exists; it cannot choose among the
three.

**Q-G · Two sites publish a price RANGE, and the row has one price column.** `youmats`
(«نطاق سعر الكيس معلن») and `elkayansteel` («36,200–40,369 جنيه», daily). `COMMODITY_PRICE`
carries exactly one `price`, with `original_price` meaning the pre-conversion figure and no
lower/upper pair anywhere (`rowspec.py:249-304`). So a range has three possible homes and
they are not equivalent: **store the midpoint** — forbidden, that is arithmetic no page ever
printed, the same error as MADAR's 15% uplift (SR-1, SR-3); **store one bound and record
which** — honest, loses half the published fact; **add a min/max pair** — a schema migration
and therefore the owner's decision. This must be settled **before** a connector is written,
not after it has already chosen.

**Q-H · `youmats` and `fepy` each serve two materials on one host.** Cement and rebar, same
site, different category path. That is **one source with two targeted extracts**, not two
sources: `ExtractSpec` already carries `categories: list[str]` — "source category codes,
when targeting" — beside `materials` and `regions` (`config.py:25-34`). Worth stating now so
nobody registers `YOUMATS_CEMENT` and `YOUMATS_STEEL` and splits one shop's data in two.

**Q-I · Bitumen 60/70 needs no vocabulary change — verified.** `material_key` is **not** a
closed enum: it is a free-form column whose only rule is UPPER_SNAKE_CASE
(`config.py:47-53`), and what a given source may emit is fenced by that source's own
`materials` list, checked at ingest (`ingest.py:92`). So `BITUMEN_60_70` is a manifest
declaration — **no migration, no code change** — and the commodity path already generalises
past fuel. The row model is a better fit than expected: it already carries `unit`,
`material_label` + `material_label_ar` (the site's own words, both languages),
`tax_included` with `tax_evidence`, and `official_source_name`/`official_source_link` for
"Source: Ministry of …" — a field built for exactly this kind of publisher
(`rowspec.py:249-300`).

**Q-K · The Egyptian bulletin needs a document reader, and that is the only thing it
needs.** Two halves, and only one is missing:
- **Missing — reading it.** The bulletin is published as *files* on `img.mhuc.gov.eg`, not
  as an HTML page or a JSON API. **Nothing in ScrapeX reads a document**: a search of
  `scrapex/` for PDF handling finds one prose comment about Sika's datasheets
  (`connectors/custom_json.py:43`) and no code. This is a new family plus a file reader
  (and text extraction, if the bulletins are scans rather than text). The Arabic index path
  needs percent-encoding handled too.
- **Already there — the data model.** Back-issues are **not** the unprecedented problem it
  looks like. `COMMODITY_PRICE` already distinguishes `provenance` `'observed'` vs
  `'reported'` with `as_of_date` and `source_date`, written for exactly this: GPP publishes
  what a price was one month, three months and a year ago, and the row records that those
  are the source's figures and never our observations (`rowspec.py:284-292`). So an archive
  backfill has both a precedent and a mechanism. SR-6 and SR-14 are about never letting a
  source's series pass for our own — `provenance` is the field that keeps them apart, not a
  prohibition on reading one.

**Q-C · #11's system was never stated.** `nile-cement.com` came with `trusted` and the price
caveat but neither `market` nor `general`. Left blank.

**Q-D · Khamato: one source or two?** `khamato.com` and `bulk.khamato.com` are one brand on
two hosts, and the owner's cement note — *a retail/wholesale platform for several
factories* — makes the question sharper, not softer. The manifest can express it either
way: two `source_key`s, or one source with a second host declared (`api.base_url` /
`taxonomy.base_url`, the shape HEIDELBERG_EG uses for three hosts,
`sources.yaml:403-427`). It turns on whether the two publish **different prices for the same
product**; if they do, they must be two sources, so a retail and a wholesale price can never
overwrite each other. If bulk pricing is **quantity-tiered**, the precedent is
HEIDELBERG_EG — a price that is a row in a matrix, not a number on a product.

**Q-E · The three `general` rows are queued for a system that cannot run.** Queue A #12, #13
and #15 need generic **row** storage, the catalogue workflow, its UI and a crawl frontier —
none shipped, all four flags off (`features.py:52-75`). Their blocker is neither a connector
nor a probe: it is a slice of the product nobody has built.

**Q-J · The probe cannot guess an Omani or Bahraini region.** `_TLD_REGION` maps `sa`, `eg`,
`ae`, `kw`, `qa` — and not `om` or `bh` (`probe.py:17`). `raysutcement.om` and `occ.om`
would come back with `default_region: *`. A two-entry dictionary fix when someone gets
there; recorded so the `*` is not mistaken for a fact about the sites.

**Q-B · A "market" site with no prices is not a price source** — folded into Q-F
above.

**What probing the whole queue would cost.** `probe()` makes at most four requests per site
— `/products.json`, `/wp-json/wc/store/products`, `/graphql`, then the homepage
(`probe.py:75-116`). **37 hosts ≤ 148 requests, about two and a half minutes** at the
fetcher's 1 req/s. Classifying this entire queue is cheap; what it cannot do is answer
Q-A, Q-C, Q-F, Q-G or Q-L, which are the owner's to settle.

---

## What each row still needs before it can become a manifest entry

Recorded once, here, so a future session does not re-derive it per site. Every field a
`sources.yaml` entry requires (`sources.yaml:22-45` is the fullest worked example):

| field | who answers it | note |
|---|---|---|
| `source_key` | derived from the host | `probe.py:_key_from_host` — uppercase first label |
| `source_name` (EN) | **required**, English is the primary display language | `sources.yaml:11-18` |
| `source_name_ar` | the site's own Arabic name for itself | a fact about the source, stated — not scraped |
| `base_url`, `family` | the probe | `family` is the whole question this file defers |
| `currency`, `default_region` | the probe, then the owner confirms | probe guesses region from the TLD only — and cannot for `.om`/`.bh` (Q-J). Queue B adds AED, QAR, KWD, BHD, OMR to a warehouse whose manifest has only SAR, EGP and USD today; the five currencies with no rate under **OP-3** are `PEN`, `SLL`, `SYP`, `VEF`, `ZWD`, none of them Gulf, but nobody has checked the Gulf five specifically |
| `authority` | **the owner — Q-A** | decides which source wins at publish |
| `vat_mode` + `tax.evidence` | read off the page, with the sentence it was read from | see MADAR/HEIDELBERG_EG for the standard of proof. `fepy` reportedly states VAT inclusion outright |
| `extract` kinds | the owner decides what is collected | `product_prices` for shops, `commodity_price` for materials by country, `enrichment` for pictures/specs — **both links or neither**: a connector that reads images changes nothing unless the source contracts `enrichment` (`sources.yaml:192-198`) |
| `materials` / `categories` | the manifest, per extract | how one host serves several materials (Q-H) and how a grade like `BITUMEN_60_70` is fenced (Q-I) |
| `min_expected_rows`, `max_drop_pct` | after the first real crawl | guard rails, not guesses |

## How a site leaves this file

1. **Probe it** — `POST /api/probe` in the panel, or `scrapex.probe.probe(url)`. It tries
   each platform's own open API first, then homepage markers, and returns its evidence.
2. **Register it** with `active: false`. The manifest header is explicit: a source is
   activated only once its connector has landed with tests (ENGINEERING T1/T2). `active`
   gates **scheduled** runs only — a manual run from the panel always works.
3. **Connector, if the family is new.** The ten families below already have one; anything
   else is a new connector with its own fixture-backed tests.
4. **Activate** from the panel's Auto switch, which rewrites the manifest surgically.

Then delete the row from this file — a site must not be tracked in two places at once.

## The ten families that already have a connector

So "can the tool run this one?" is answerable without re-reading the code.
Evidence: `scrapex/connectors/factory.py:33-44`.

`shopify-json` · `magento-graphql` · `woocommerce-storeapi` · `salla-html` ·
`zid-html` · `hybris-occ` · `custom-json-api` · `heidelberg-price-matrix` ·
`static-html-table` · `aramco-fuel-page`

Declared in `vocab.ConnectorFamily` but **not** built: `datasheet-enrichment` (Q-F, DEC-5),
and `TBD-probe`, the placeholder a site carries before it has been classified — the panel
refuses to activate one.

Two families in that list are worth knowing about before probing Queue B, because they are
the nearest precedents for material prices by country: **`static-html-table`** (GPP — one
page, many countries, `commodity_price`, `latest_only`) and **`aramco-fuel-page`** (a
producer's own price page parsed from reading-order text rather than selectors, because
"the React class names churn, the words do not"). A ministry or state producer publishing
a monthly figure looks far more like those two than like a Salla shop.
