# A contractor source, and a table of its own

Opened **2026-08-16** on the owner's instruction: «اريد اضافة مصدر مقاول (جدول منفصل تماما
جدول سيكون لهذا المصدر فقط) جدول منفصل تماما عن جداول المنتجات» — *I want to add a
contractor source (a completely separate table, a table that will be for this source only),
a table completely separate from the product tables.*

**Nothing here is declared or crawled.** SR-13 stands: nothing is collected that is not in
`sources.yaml`, and this is not in `sources.yaml`. This file exists so the specification the
owner wrote by hand does not live only in a chat transcript — he works from two machines,
and everything this work depends on goes in the repository.

## What makes this different from every source before it

Every source in this project so far produces **offers** — a product, a price, a currency, a
moment. The warehouse, the ingest path, the Data page and the panel's cards are all built
around that shape.

A contractor is not an offer. It is a **company**: one row per organisation, ~60 columns,
several of them hierarchical and multi-valued, and no price at the centre of it. The owner
has asked for a table of its own rather than an attempt to bend the offer tables around it,
and the reasoning is his: *«جدول منفصل تمامًا عن جداول المنتجات»*.

## The columns, as the owner specified them

He reviewed the results page and the detailed contractor profile **in both languages** and
wrote the grouping below. `[ar]` means the column carries the Arabic value of the same
field — not a translation made here, but the value the site itself publishes in Arabic.

| group | columns |
|---|---|
| **Identity** | Contractor ID, Company Name, Company Name [ar], Logo URL |
| **Links** | Profile URL, Profile URL [ar], Contract Request URL, Contract Request URL [ar], Map Location URL |
| **Membership** | Membership Level, Membership Level [ar], Account Status, Account Status [ar], Membership Number, Membership Type, Membership Type [ar], Member Since |
| **Size and training** | Company Size, Company Size [ar], Training Credit Hours |
| **Contact** | Organization Mobile Number, Organization Email |
| **Location** | City, City [ar], Region, Region [ar], Address, Address [ar] |
| **Rating, overall** | Customer Rating Score, Customer Rating Count, Customer Rating Grade, Customer Rating Grade [ar] |
| **Rating, detail** | Quality Rating Score, Schedule Rating Score, Environment Health and Safety Rating Score, Value Rating Score, Communication and Responsiveness Rating Score |
| **Classification and relations** | Contractor Classification, Contractor Classification [ar], Contractor Classification Grade, Main Contractor Count, Subcontractor Count |
| **Company** | Company Description, Company Description [ar] |
| **Programmes and services** | Qualification Programs, Qualification Programs [ar], Balady Services, Balady Services [ar] |
| **Licences and readiness** | Licensed Activities, Licensed Activities [ar], Readiness Level, Readiness Level [ar] |
| **Activities and interests** | Interests, Interests [ar] |
| **Contractor relations** | Main Contractors, Main Contractors [ar], Subcontractors, Subcontractors [ar] |
| **Technical rating** | Technical Rating by Activity, Technical Rating by Activity [ar], Technical Rating by Company Size, Technical Rating by Company Size [ar] |
| **Contracts and projects** | Standard Contracts Count, Registered Contracts Count |
| **Self-build prices** | Self-Build Price per sqm (&lt;5 Projects), Self-Build Price per sqm (5–10 Projects), Self-Build Price per sqm (&gt;10 Projects) |
| **Addendum, 2026-08-16** | Is Saudi Contractor, Latitude, Longitude |

The addendum also named `Membership Type`, `Membership Type [ar]` and
`Map Location URL`; all three were already in the groups above and are not repeated.
`Is Saudi Contractor` is the boolean behind `Membership Type`, whose two values are
`Saudi Contractor` / *مقاول سعودي* and `Non-Saudi Contractor` / *مقاول غير سعودي*.

Where each half lives: the **results card** carries name, membership, size, training hours,
status, location, rating, contracting relations and classification. The **detailed profile**
adds contact, address, activities, licences, projects and the rest.

## The owner's own notes, which are design rulings and not asides

1. **`Interests` is hierarchical and multi-valued.** Store it as JSON or in a table of its
   own — **not** as `Activity 1, Activity 2, …`. The same applies to **Licensed Activities**,
   **Qualification Programs**, **Balady Services**, and the **contractor relations**
   (Main Contractors / Subcontractors).
2. **Commercial Registration Number** is offered as a way to SEARCH, but he did not find it
   displayed as a public field on the profiles he read. It may be added as an optional
   column — it is not promised.
3. **The Saudi / non-Saudi contractor counts at the top of the page are site-wide
   statistics**, not per-contractor columns. They do not belong in this table.
4. **Many fields are optional and will be missing for some contractors** — especially the
   description, the address, the licences, the readiness level, the prices and the technical
   rating. A column that is absent is not a fault to report.

## The site, PROBED 2026-08-16 — `muqawil.org`, the Saudi Contractors Authority

The owner gave two addresses: `https://muqawil.org/en/contractors` and
`.../ar/contractors`. Four pages were loaded — `robots.txt`, the English listing, one
English profile, and nothing else. **This was a probe, not a crawl.**

### robots.txt says yes to ScrapeX, and this is worth stating precisely

```
User-agent: *
Content-Signal: search=yes,ai-train=no,use=reference
Allow: /
```

`Allow: /` for the general agent, **no `Crawl-delay`, no `Sitemap`**. Nine AI crawlers are
named and disallowed — `ClaudeBot`, `GPTBot`, `CCBot`, `Google-Extended`, `Bytespider`,
`Amazonbot`, `Applebot-Extended`, `meta-externalagent`,
`CloudflareBrowserRenderingCrawler`. **ScrapeX is none of them and is permitted.** Recorded
this way deliberately: the owner asked to "bypass robots.txt", and there is nothing to
bypass — writing that ScrapeX ignores robots would be recording a false thing about a tool
that complies. `ai-train=no` also does not bind a warehouse that trains nothing.

The absence of a declared `Crawl-delay` means the pace is the OWNER's setting, not the
site's — the same finding that made T1's `crawl_honour_delay` a no-op and produced
`crawl_pace_s` (#190).

### What the platform is

**Laravel + Livewire, server-rendered.** `vendor/livewire/livewire.min.js` is loaded and
`window.Livewire` is defined. The contractor rows arrive **inside the HTML**; no JSON API
answers for them. jQuery, bootstrap, select2, jstree and checkboxTree do the widgets — the
hierarchical Interests filter is a `jstree`.

**Cloudflare sits in front of it** — `cdn-cgi/challenge-platform/h/g/scripts/jsd/…` is
fetched and a `POST …/jsd/oneshot/…` follows on every page load in a browser.

**It does not block ScrapeX.** That was the first guess written here and measurement
overturned it within the hour; see §1 below. `Fetcher.HTTP` is enough and Playwright is not
needed — which is an order of magnitude off the crawl cost. The lesson is the one this
project keeps relearning: the presence of a challenge SCRIPT is not the presence of a
challenge.

### The addresses, as observed

| what | shape |
|---|---|
| listing | `https://muqawil.org/{en\|ar}/contractors?page=N` — **871 pages** as of 2026-08-20, 20 rows each and the last one **2**. Both numbers are READ, never assumed: 865 was true on 2026-08-16 and the page count moves as contractors register. See [DEC-11](BACKLOG.md) |
| profile | `https://muqawil.org/{en\|ar}/contractors/{contractor_id}/{143}` |
| logo | `https://muqawil.org/public/contractor/companyLogo/CompanyLogo-{unix_ts}_{name}.{ext}` |
| map page | `https://muqawil.org/{en\|ar}/contractors/map` |

The second path segment was `143` on every row of page 1. **Whether it is constant, a
category, or per-contractor is NOT known** — one listing page is not evidence enough, and
guessing it is how a crawler builds ten thousand dead URLs.

### Latitude and Longitude — found, and not where a data attribute would be

They are in an **inline `<script>` on the profile page**:

```
lat: 24.671699788528482
lng: 46.39415764160163
```

No `data-lat`, no coordinates in any attribute, no map iframe. So the extraction is a script
scrape, and a change to that script breaks it silently — it needs its own guard.

### The card carries most of the specified columns already

Read off the listing: Company Name, rating score and rating count, Membership Number,
Company Size, Training Credit Hours, Status, `City - Region`, Main Contractor count,
Sub Contractor count, classification (`Second Classified 2` … `Unclassified`), and the
Contract Request link. The profile adds Membership Level (`Platinum Membership`),
**`Membership: Saudi Contractor`** — which is the addendum's `Is Saudi Contractor` —
Member Since, mobile, email, City, Region, Address, Activity, the licences-and-readiness
table, the Interests tree, `عدد العقود النموذجية / عدد العقود المسجلة` (455 / 64 on the one
read) and an empty self-build price table.

**The site-wide counters the owner excluded are real and visible**: `122,785 Saudi
Contractor` and `1,640 Non-Saudi contractor` sit above the results. He was right that they
are statistics, not columns. They are also **not** the size of the crawl — 864 listing pages
is.

### The finding that touches ~20 of the specified columns

**`/en/` is only partly English, and one cell can hold both languages.** On the English
profile, whole sections render in Arabic regardless: `التراخيص ومستوى الجاهزية`,
`المقاولين بالباطن`, `المقاولين الرئيسيين`, `التقييم الفني`, `العقود سعر البناء`. And the
Licensed Activities cell stacks the two languages **in the same cell**:

```
تشييد المباني - تشييد المباني - جميع الأنواع
Construction of Buildings - Construction of Buildings – All Types
```

with readiness written `أساسي | Basic`.

So the `[ar]` convention — *"the column holds the Arabic value of the same field"* — is
sound for the fields the site really does localise (name, city, region, membership level,
status), but for these it is **not two pages of the same field**: it is one cell to be
split. Which fields are genuinely bilingual and which are one stacked cell has to be
decided per column, and only the AR page beside the EN page can settle it.

## What is NOT known yet, and blocks the connector

~~The site's address.~~ **Given 2026-08-16 and probed.** All four follow-up questions were
then settled by measurement the same day, with `httpx` carrying ScrapeX's own
`DEFAULT_USER_AGENT` — not by the browser, so what is recorded here is what the CRAWLER
will meet.

### 1. A plain HTTP fetch passes Cloudflare — `fetcher: http`

**This corrects what is written further up this file.** The challenge script is injected
into every page by Cloudflare as a matter of course; its presence is not a block. Measured
on three addresses: **HTTP 200**, full bodies (375 KB, 382 KB, 138 KB), the real
`<title>Contractors | Muqawil Platform</title>`, twenty contractor links per listing page,
and **not one interstitial marker** — no *"Just a moment"*, no `cf_chl_opt`, no *"Checking
your browser"*.

So `Fetcher.HTTP`, and **no Playwright**. That is an order of magnitude off the crawl cost
this file assumed an hour earlier.

### 2. The trailing segment is NOT decorative — it switches a column group on

`/en/contractors/881/143`, `/881/1` and `/881/999` all answer 200 and all show the SAME
contractor, so it plays no part in identity. But diffing the rendered text of `/143`
against `/999` leaves exactly one difference:

```
only in /143: ['العقود سعر البناء (برنامج البناء الذاتي)', 'القيمة']
only in /999: nothing
```

**`143` is what makes the self-build price section render at all.** The owner's last three
columns — Self-Build Price per sqm (<5 / 5–10 / >10 Projects) — exist only under it. A
connector that treated the segment as noise would have shipped those three columns
permanently empty, and nothing would have said so.

Every profile link on listing pages 1 and 2 carried `143`. Whether another value ever
appears is unproven, but the value can be a literal rather than read per row.

### 3. AR against EN, measured on one contractor

| field | EN page | AR page | verdict |
|---|---|---|---|
| Membership | `Saudi Contractor` | `مقاول سعودي` | **two real values** — the addendum's pair, confirmed |
| Company Size | `Small Company Size` | `منشأة صغيرة` | **two real values** |
| City | `RIYADH` | `الرياض` | **two real values** |
| Member Since | `2018/08/25` | `2018/08/25` | identical — a date needs no `[ar]` |
| Address | `الرياض الملقا انس بن مالك` | — | **the EN page prints the ARABIC address.** There is no English one, so `Address` and `Address [ar]` are a single value |
| Training Credit Hours | `308 H` | not found as `308 H` | formatted differently per locale; read it, never assume it |

**Do not extract by label text.** The AR page spells the membership-number label
`رقم العضويه` — with `ه`, not `ة`. A label-matched extractor breaks on a spelling variant
no human reader would notice.

### 4. No page-size parameter is honoured

`per_page`, `perPage`, `limit`, `size`, `page_size` and `take` were each tried at 60
against `?page=2`. All six returned **exactly 20 rows**. So the bound is fixed:

> **871 listing pages, and the arithmetic is `(L−1)×20 + c` where `c` is the last
> page's own count — 17,402 on the morning of 2026-08-20 and 17,403 the same
> afternoon.** Multiplying by 20 throughout overcounts by however few rows the final
> page carries: 15 on 2026-08-16, 2 that morning, 3 that afternoon. The owner said
> the data is live before any of this was measured, and the tail count is where it
> shows. [DEC-11](BACKLOG.md).

Not the 122,785 the site's own counter shows — that is total membership, and the owner was
right to call those counters statistics rather than columns.

### 4a. The page count is published, and every filter is a partition axis

**MEASURED 2026-08-20, 152 requests.** The paginator's last link carries the number:

```html
<li class="page-item"><a href="…?region_id=1&amp;page=322">»</a></li>
```

So **one request sizes any slice**, and `read_last_page` reads it. Two things about that
href are load-bearing:

- the number is inside an **`href`**, not in prose — a looser match reads the page's own
  query string and calls a 322-page region complete after one page;
- it is written **`&amp;page=`**, so the character before `page=` is a **semicolon**.
  Matching `[?&]page=` finds nothing on any filtered listing. That was a live defect
  here, not a site quirk. [DEC-11](BACKLOG.md).

The listing's ten filter parameters, all GET on `/{lang}/contractors`:

| parameter | values | exhaustive |
|---|---|---|
| `region_id` | `0`, `1`…`13` | **yes** — see below |
| `city_id` | 3,953 ids, from an endpoint | no |
| `company_size` | `big` `medium` `small` `verysmall` | **yes** |
| `user_type` | `SC` `NSC` | **yes** |
| `rating_stars` | `1`…`5` | no — 17 contractors carry any rating at all |
| `lc_program_list_id` | 13 programme ids | no |
| `interest_id` | `jstree`, hierarchical, multi-valued | no |
| `balady_service_id` | | no |
| `q` | free text; **matches the membership number exactly** | n/a |
| `my_contractors` | `1` `2` | no — a signed-in user's own list |

**`company_size`, `user_type` and `rating_stars` are radio inputs, not `<select>`s.** A
search for `<select>` misses them entirely, which is how they were once recorded as
absent.

**`city_id` is filled by an endpoint**, which is why its `<select>` is empty in every
stored page:

```js
var citiesUrl = "https://muqawil.org/en/contractors/cities";
```

`GET /{lang}/contractors/cities?region_id=<n>` returns `[{"id":…,"name":…}, …]`. It also
works standalone: `?city_id=3` alone answers 296 pages.

**`region_id=0` returns the contractors who publish no location.** Regions 1–13 sum to
15,966 against a whole of 17,403; `region_id=0` returns exactly the missing **1,437**,
every card blank. Independently: **960 of 11,059 stored records (8.7%)** have a null
`card_city_region`, against 1,437 of 17,403 (**8.3%**).

> **`region_id` × `company_size` is therefore an exhaustive 56-cell partition of the
> directory, verified to the unit** — the basis of the crawl method in
> [DEC-11](BACKLOG.md), and the reason a completeness claim about this site can be a
> proof rather than a hope.

### 5. Found while measuring: the email is obfuscated, and a naive scrape never gets it

`Organization Email` is not in the HTML. What is there is Cloudflare's email protection:

```html
data-cfemail="670e1327140406491406"      →  it@sca.sa
```

The first byte is the XOR key and every following byte is XORed with it. The literal
`it@sca.sa` appears nowhere in the source. **A connector that does not decode
`data-cfemail` stores the string `[email protected]` for every contractor**, forever — and
no test asking "is this column populated?" would ever fail. It needs a guard of its own,
exactly like the coordinates in the inline script.

## What this costs — read 2026-08-16, not guessed

### The house already exists, it has never had a tenant, and it is switched off

`db/engine/schema.sql` already carries a complete entity-shaped path, built as **G1** and
described in `docs/GENERIC_CATALOG.md`:

| table | line | what it holds |
|---|---|---|
| `site_profile` | — | one website |
| `dataset_definition` | 158 | one table / list / detail record on that site |
| `field_definition` | 241 | that dataset's OWN field set — stable keys, original names, display order |
| `dataset_schema_version` · `generic_page_snapshot` | — | which shape a reading was taken against |
| `generic_record` | 287 | one row, as `data_json` — `CHECK (json_valid(...) AND json_type(...) = 'object')` |
| `generic_record_revision` | 307 | the history of one row, keyed `(record, snapshot, content_hash)` |
| `dataset_relationship` · `relationship_field_pair` | — | directed joins, single **and composite** |

`field_definition.data_type` (`:248`) already admits
`'text','integer','decimal','boolean','date','datetime','url','json','unknown'` — **`json`
and `url` are both there.** The owner's ruling that the five multi-valued groups be stored
as JSON or as their own table is not a request for something new: it is the choice this
schema was designed to offer, and `dataset_relationship` is the second half of it.

**Both switches are off** (`scrapex/features.py:52-63`):

- `generic_dataset_catalog` — `False`, stage `foundation`, *"Definitions and API exist;
  enable only after generic rows and the catalogue UI ship."*
- `generic_extraction` — `False`, stage `not_started`, *"Enabled only after an approved
  non-product extraction reaches generic storage."*

A contractor directory **is** an approved non-product extraction reaching generic storage.
It is the tenant those two sentences are waiting for.

### The price path is closed against it, and must stay closed

Bending the offer tables was never available, which is what the owner's instinct already
said. Measured:

- `scrapex/vocab.py:352` — `ExtractKind` has exactly three members. `config.py:58` types
  `ExtractSpec.kind` to it, so a manifest **cannot declare a fourth**: `load_manifest`
  refuses the YAML outright.
- `scrapex/rowspec.py:49` — `PRODUCT_PRICES.required` includes `price`, `currency`,
  `tax_included`. `RowBuilder.row` raises on an empty required field, so a company row
  cannot be BUILT, let alone stored. `COMMODITY_PRICE` (`:265`) still mandates a price.
- `scrapex/connectors/base.py:83` and `scrapex/payload.py:234` — `ScrapedTable.kind` and
  `FunnelPayload.kind` are both typed to the same three, and the payload is the FROZEN wire
  contract shared with the extension and Apps Script.
- `scrapex/ingest.py:989` — the explicit refusal: *"kind … not ingestable"*. `_persist_row`
  (`:1389`) hard-codes product → variant → offer → `price_observation`, whose `price`,
  `currency` and `tax_included` are all `NOT NULL` (`schema.sql:406`). Storing a company
  there means minting a synthetic variant and a synthetic offer for each one — the thing the
  owner refused in the sentence that opened this file.
- `scrapex/ingest.py:1268` — the append gate is keyed on `price_hash` / `price_fields` /
  `price_trade` against an open price period. There is no analogue for *"this company's
  profile is unchanged"*, so a second crawl would write nothing at all. **A directory needs
  its own change detection**, and `generic_record.content_hash` is exactly that.

### The display path gives a directory nothing for free

- `scrapex/reports.py:182` — `_LATEST_PER_OFFER` defines a row as *the newest price
  observation for an active variant of an active offer*. `browse` and the export both build
  on it, so `/api/table/{key}` returns **zero rows and `total: 0`** for a directory.
- `scrapex/reports.py:672` — `BROWSE_COLUMNS` is ~40 keys, every one an offer fact.
  `column_presence` (`:843`) starts from that set and **only ever discards** — it cannot ADD
  a column, so a directory's columns resolve to an empty list.
- `scrapex/reports.py:835` — `ESSENTIAL_COLUMNS = frozenset({"price"})`, stated as *"without
  it the table is not a price list at all"*. That is a floor a company row cannot clear.
- `BILINGUAL_COLUMNS` (`:817`) is a hard-coded product map. **The `[ar]` pairing the owner
  specified for ~20 columns has no per-source declaration anywhere** — this is real new work
  wherever the directory is displayed.

So the Data page cannot show this source through `/api/table`. That is a second surface,
and it should be weighed against finishing B2 first.

### The add-in contract does not block anything

The six sheets are the **Excel add-in's** configuration and the engine's warehouse does not
read them. A contractor entity would only need workbook rows if the owner wants it in Excel.
If he does, two mismatches are worth knowing rather than discovering: `ENTITY_TYPES`
(`addin-vocabulary.js:30`) is cost-shaped and has no `DIRECTORY`/`COMPANY` value — `REF` is
the nearest borrow — and `SEMANTIC_ROLES` (`:23`) has no role for a company attribute, so
every column would be `NONE` and no add-in feature could key off them.

## The markup, read 2026-08-16 while writing the `PageSource`

### The card, and the twenty-first one that is not a contractor

A contractor is `div.section-card`. **A listing page holds twenty-one of them and only
twenty are contractors** — so cards are selected by *holding a profile link*, never by
counting or by position. Selecting by position would be off by one for every row after the
impostor, and a slice would then be chosen from the wrong contractor.

```html
<div class="section-card has-action has-membership platinum-membership"
     data-membership-text=" Platinum Membership ">
  <img class="card-img" src="…/CompanyLogo-1710325829_….jpg"
       onerror="this.src='…/companies/default.jpg'">
  <h2 class="card-title"><a href="…/contractors/20008518/143">Awared General …</a></h2>
  <div class="card-rating" onclick="showRatingModal('1010754424',event)">
    <div class="rater readonly" data-rate-value="5"></div>
    <span class="rating-value">5</span>
    <span class="votes-num">( Number of ratings : 1 )</span>
```

`Membership Level` is an **attribute**, `data-membership-text`, mirrored in the class
(`platinum-membership`). The logo's `onerror` names the placeholder, which is how a
contractor with no logo is told from one whose file failed: if `src` already IS
`default.jpg`, store NULL.

### Key on the ICON, never on the label

Every field is an `.info-box` of `.info-name` + `.info-value`, and each carries an icon
whose class is **identical in both locales**:

| icon class | English label | Arabic label |
|---|---|---|
| `icon-ID` | Membership Number | `رقم العضويه` |
| `icon-company` | Company Size | `حجم المنشأة` |
| `icon-time` | Training credit hours | `عدد الساعات التدريبية` |
| `icon-verifiy` | Status · *and* the classification | `الحالة` · `مصنف درجة ثانية` |
| `icon-locaion` | City – Region | `المدينة - المنطقه` |
| `icon` (bare) | Main Contractor · Sub Contractor | `مقاول رئيسي` · `مقاول من الباطن` |

**This is the answer to the `رقم العضويه` trap** — the Arabic label is spelled with `ه`, not
`ة`, and a label-matched selector breaks on a difference no reader would notice. The icon
does not move between languages.

`icon-verifiy` and `icon-locaion` are **their** spellings of *verify* and *location*. They
are matched exactly. The day the site corrects them, these selectors are what will say so.

**The icon is not unique** — `icon-verifiy` serves both Status and the classification, and
the bare `icon` serves both contractor counts. So the key is icon *plus position*, never the
icon alone.

### Two cells that carry two facts each

1. **City and Region are ONE cell**, dash-separated across a newline and a wall of
   whitespace: `RIYADH\n<spaces>- Riyadh`, and in Arabic `الرياض - الرياض` where the two are
   the same word. So `City` and `Region` are a split, not two fields.
2. **The classification puts the DATA IN THE LABEL.** `.info-name` reads
   `Second Classified` and `.info-value` reads `2` — so `Contractor Classification` comes
   from the name and `Contractor Classification Grade` from the value, which is the reverse
   of every other box on the card.

### A lead on the Commercial Registration Number

`onclick="showRatingModal('1010754424', event)"` carries a **ten-digit number in the Saudi
CR format**, distinct from the nine-digit membership number on the same card. It is a
plausible `Commercial Registration Number` — the field the owner said he could not find
displayed anywhere.

**Recorded as a lead, not a promise.** It appears only on cards that HAVE a rating (two of
the three cards checked had no rating and no modal), so it cannot be a reliable source for
the column even if the identification is right.

**FOUND 2026-08-22 — and not there. The lead above was the wrong trail.** The Commercial
Registration number is the pre-filled `cr` input of the **contract-request form**, which
every profile publishes. Measured over 2,543 profile pairs:

| | |
|---|---|
| pages carrying it | **2,542 of 2,543** |
| shape | **ten digits**, every one |
| distinct values | **2,542 over 2,542 contractors — no two share one** |

So it is a second natural key for this directory, and the first that is a **national**
identifier rather than muqawil's own numbering — which is what a row here can be joined
to Balady, or to a commercial register, on. The rating-modal lead needed a contractor to
have a rating; the form needs nothing. `read_commercial_registration` in
`scrapex/extract/muqawil.py`.

**The same form answers `Contract Request URL`, and the answer is that it is not a
column.** Its action is `https://muqawil.org/init_econtract_draft` — one endpoint,
identical on all 2,479 pages measured. A site-wide constant is not a per-contractor
field.

## The design

### Where it lives: one `dataset_definition`, and the G1 path unchanged

| what | where |
|---|---|
| the site | one `site_profile` row for `muqawil.org` |
| the table | one `dataset_definition`, `dataset_key = "contractors"` |
| the columns | one `field_definition` row per field below |
| a contractor | one `generic_record`, `record_key` = the contractor id, body in `data_json` |
| its history | `generic_record_revision`, one per changed reading |

That is the owner's «جدول منفصل تمامًا … سيكون لهذا المصدر فقط» exactly: **one table, for
this source only**, sharing nothing with `price_observation`.

**The five hierarchical groups go in CHILD TABLES.** Ruled by the owner on 2026-08-20 —
«جداول أبناء للخمس كلّها» — and recorded as
[R-19](RULINGS.md#r-19--the-five-multi-valued-contractor-groups-go-in-child-tables-not-json).

> **This paragraph used to say the opposite, and the superseded reasoning is kept
> rather than deleted, per C4.** It read: *"The five hierarchical groups go in JSON
> inside `data_json`, not in child tables… JSON is chosen because he asked for ONE
> table and child tables would make six; because `generic_record.data_json` already
> carries a `json_valid` + `json_type='object'` CHECK; and because
> `field_definition.data_type` already admits `json`."*
>
> **What changed is a measurement, taken after that was written.** One real profile
> was parsed — شركة عبر المملكة سبك, membership 10001274 — and its Interests are
> **30 values across 6 groups, hierarchical**: a parent category with children
> (building construction 6, roads 4, electrical 5, lifts 5, landscaping 7, sewage 3).
> At ~17,283 contractors that is on the order of **half a million rows**, which an
> indexed child table answers instantly and a JSON blob answers by scanning eleven
> thousand bodies.
>
> The old paragraph's strongest argument also turned out not to distinguish the two:
> it leaned on the grid being one flat table, but the grid cannot render a nested
> JSON array either. **Both shapes need new payload work; only one also gives the
> query.** `Interests` still keeps its real tree shape rather than being flattened
> into `Activity 1, Activity 2, …`, which is what he ruled out from the start.

**`Main Contractors` / `Subcontractors` are edges, and now have the same answer.**
`dataset_relationship` + `relationship_field_pair` exist for exactly that and hold
**0 rows**. Measured on the same profile: both tables render with a header row and no
data, which agrees with the listing counts — `0` for 11,057 of 11,059 stored records.
So the edge machinery has never had a tenant, and this is its first.

### Bilingual: DERIVED from the `_ar` suffix, never a hand-written list

This is why the owner asked for both languages at all: *«صفحة داتا … بتعرض البيانات بلغتين
فى toggle»*. The engine's `grid.js:1900 wireLanguageToggle()` builds that toggle from
`payload.bilingual`, which the server fills from `reports.BILINGUAL_COLUMNS` — **a dict
written out by hand, product-only, with no per-source declaration anywhere.**

So for this dataset the pairing is **derived**: any `field_definition` whose key ends `_ar`
pairs with the field of the same name without it. It matches what products already do
(`product_name` / `product_name_ar`), it cannot go stale when a column is added, and it is
the rule this repository keeps choosing — *a guard that lists its subjects fails on the one
nobody added to the list*.

### The fields

`sc` = the search card · `pr` = the profile page · `js` = an inline script · `u` = built
from the id, not fetched. Types are `field_definition.data_type`.

| field_key | type | from | note |
|---|---|---|---|
| `contractor_id` | text | sc | the identity; also `record_key` |
| `company_name` / `company_name_ar` | text | sc | genuinely two values |
| `logo_url` | url | sc | absent for some; the site falls back to `default.jpg`, which must be stored as NULL and never as the placeholder |
| `profile_url` / `profile_url_ar` | url | u | `/{lang}/contractors/{id}/143` |
| `contract_request_url` / `_ar` | url | u | |
| `map_location_url` | url | pr | |
| `membership_number` | text | pr | **NOT unique on the profile page.** The listing's `card_membership_number` is: 17,304 rows, 17,304 distinct, none blank. The profile field has 3 repeated values across 13,347 rows, and 14 contractors disagree with their own listing card — traced to the site answering a dead id with the LISTING page (`OP-64`), not to data entry |
| `latitude` · `longitude` | decimal | **js** | inline script only |
| `membership_level` / `_ar` | text | pr | e.g. `Platinum Membership` |
| `account_status` / `_ar` | text | sc | e.g. `Account Verified` |
| `membership_number` | text | sc | **text, not integer** — leading zeros are real |
| `membership_type` / `_ar` | text | pr | `Saudi Contractor` / `مقاول سعودي` |
| `is_saudi_contractor` | boolean | pr | derived from the pair above |
| `member_since` | date | pr | identical in both languages |
| `company_size` / `_ar` | text | sc | `Small Company Size` / `منشأة صغيرة` |
| `training_credit_hours` | integer | sc | formatted per locale — parse, never assume |
| `organization_mobile_number` | text | pr | text: a leading `+` or `0` is real |
| `organization_email` | text | pr | **Cloudflare-obfuscated — must decode `data-cfemail`** |
| `city` / `city_ar` · `region` / `region_ar` | text | sc | |
| `address` | text | pr | **one value.** The EN page prints the Arabic address; there is no English one, so there is no `address_ar` |
| `customer_rating_score` | decimal | sc | |
| `customer_rating_count` | integer | sc | |
| `contractor_classification` / `_ar` | text | sc | e.g. `Second Classified` |
| `contractor_classification_grade` | integer | sc | the numeral beside it |
| `main_contractor_count` · `subcontractor_count` | integer | sc | |
| `standard_contracts_count` · `registered_contracts_count` | integer | pr | 455 / 64 on the one read |
| `interests` | **json** | pr | the tree, nested as published |
| `licensed_activities` | **json** | pr | each entry `{ar, en, readiness_ar, readiness_en}` |
| `qualification_programs` | **json** | pr | |
| `balady_services` | **json** | pr | |
| `main_contractors` · `subcontractors` | **json** | pr | edges; see the deferred question |
| `technical_rating_by_activity` | **json** | pr | |
| `technical_rating_by_company_size` | **json** | pr | |
| `self_build_price_under_five_projects` · `_five_to_ten_projects` · `_over_ten_projects` | text | pr | **THREE COLUMNS, not one JSON object — corrected 2026-08-22.** This row used to read "the three bands as one object". Measured over 2,419 pairs: exactly three labels and no fourth, values numeric with no currency or separator, and the three arrive **in different orders on different pages**, so they are read by label. Three fixed scalars are not a multi-valued group — the same reasoning `write_groups` already applied to the contract counts. `R-19` overruled JSON for the five *hierarchical* groups, and this is not one of them |
| `model_contract_count` · `registered_contract_count` | text | pr | **NEW 2026-08-22.** Two scalars from the card titled `Previous Projects` / `المشاريع السابقة`, whose table holds contract counts and not projects — so the reader keys on the table's headers and never on the card's title. 92 of 2,419 pages, always exactly one row |
| `commercial_registration_number` | text | pr | **FOUND 2026-08-22 — 2,542 of 2,543 pages, ten digits, all distinct.** The old verdict here, "optional and unobserved", was true of four profiles and false of the site. See the section above |
| `company_description` / `_ar` | text | — | unobserved on four profiles |

**`licensed_activities` is NOT an `[ar]`/non-`[ar]` pair.** The site stacks both languages
in ONE cell —

```
تشييد المباني - تشييد المباني - جميع الأنواع
Construction of Buildings - Construction of Buildings – All Types
```

— with readiness written `أساسي | Basic`. So it is one JSON field carrying both, not two
columns. The same holds for every section that stays Arabic on the `/en/` page.

**CORRECTED 2026-08-22, and the correction is the interesting part.** The dashes in that
cell are **NOT** language separators — they are **hierarchy** separators, inside each
language. `تشييد المباني - تشييد المباني - جميع الأنواع` is a three-level path, and its
English half is the same three levels. The language boundary is the **first Latin
letter**, and that is provable rather than plausible: measured over 1,500 rows, the
script-run signature of every activity cell is `AL` — Arabic then Latin, exactly one
transition, 1,500 of 1,500.

So it is neither one JSON field nor two columns. It is a **taxonomy** — 1,685 rows over
228 pages, drawn from a closed vocabulary of **22 distinct activities** — which is what
[R-19](RULINGS.md#r-19--the-five-multi-valued-contractor-groups-go-in-child-tables-not-json)
ruled and `R-38` shaped. `contractors.write_groups` writes it as of 2026-08-22.

**And the site's own English is wrong on 100 of those 1,685 rows** — 30 truncated to
`Civil Engineering -`, which is the same string for two different activities, and 70
naming a *different activity* entirely. All three cases change the number of levels, so
comparing level counts catches every one. Where they disagree the Arabic path is stored
alone and the English name is left **empty**, which is the state `taxonomy.ensure_path`
already repairs the moment a page with a usable English half arrives. Measured across the
corpus, that repair leaves exactly **3 of 29 nodes** without an English name — the three
the site never publishes correctly.

### What CANNOT be filled from public pages — measured, not assumed

| specified column | verdict |
|---|---|
| Quality / Schedule / Environment Health and Safety / Value / Communication Rating Score | **not published per contractor.** Absent from four profiles, including three that HAVE ratings. The five names appear only on `/contractors-rate/info`, which describes the criteria. Behind login, or not published at all |
| `Customer Rating Grade` / `[ar]` | not found on any profile read |
| `Company Description` / `[ar]` | not found on four profiles — already called optional by the owner |
| ~~`Commercial Registration Number`~~ | **FOUND 2026-08-22 on 2,542 of 2,543 pages.** Struck rather than deleted, per **C4**: the verdict was reached honestly on four profiles, and the lesson is that four profiles is not the site. It is in the contract-request form, not on the card |

**Nine specified columns therefore have no public source.** They stay in the field list as
nullable and are simply never written — a column that exists and is empty is a fact; a
column quietly removed is a question nobody thinks to ask.

### The second crawl, and history

`generic_record.content_hash` over the normalised `data_json` is the change detector. It
replaces nothing: the price path's `_still_the_same_price` gate is keyed on `price_hash` and
has no meaning here. An unchanged contractor moves `last_seen_at` and writes **no**
revision; a changed one writes a `generic_record_revision`; one that stops appearing becomes
`status = 'unavailable'` rather than being deleted.

**History is kept**, because a classification, a rating, a readiness level and a membership
level are exactly the things whose CHANGE is the answer worth having.

### The crawl

`fetcher: http`, ScrapeX's own user agent, the owner's pace (the site declares no
`Crawl-delay`). **871 listing pages**, then **17,402 profiles**, each in two languages —
roughly **35,500 requests** for a full pass, about ten hours at one per second.

The listing pages alone are ~1,730 requests and carry most of the card fields. **A
listing-only first pass is a real option** and is worth weighing before committing to the
profiles.

### Two guards this design needs, because both failures are silent

1. **The email.** A connector that does not decode `data-cfemail` stores the literal
   `[email protected]` for every contractor, and any test asking *"is the column populated?"*
   passes forever. The guard must assert a decoded address, not a non-empty string.
2. **The coordinates.** They come from an inline script, so a change to that script yields
   no error — just permanently NULL columns. The guard must assert a plausible latitude and
   longitude, not merely presence.

## Open, and for the owner to rule on

Recorded here rather than decided quietly; see `docs/BACKLOG.md` for how decisions are
numbered when they are taken.

- **JSON column or child table** for the five multi-valued groups. The owner allowed either.
  The trade is queryability against one table instead of six.
- **Does this entity also belong in the mbiXaddin workbook** — a `1.TableDefinition` row and
  its `2.SchemaRule` columns — or is it engine-only until it has proved itself?
- **Refresh shape.** A directory is re-read whole rather than watched for price changes, so
  the append-gate reasoning that governs `price_observation` does not apply. What DOES a
  second crawl of an unchanged contractor write?
- **Retention.** Offers are kept as history because a price has a date. Does a contractor's
  profile keep history, or is the latest reading the only one?
