# Reconnaissance — onlinestore.heidelbergmaterials.eg

**Date:** 2026-07-28 · **Status:** investigation only. No connector, no migration, no
`sources.yaml` change was made. **Requests spent:** 23 (self-imposed 2.5 s gap between
every one).

This report answers the owner's four questions: **what** the site shows, **how** it shows
it, **which existing ScrapeX infrastructure** a connector would reuse, and **what would
have to be built** to cover everything the site has.

Every claim about the site is backed by a response actually fetched on 2026-07-28. Every
claim about ScrapeX carries a `file:line`. Where I did not fetch something, the report
says so instead of guessing.

---

## 0. Politeness and robots

`robots.txt` was fetched **first**, on both hosts, before anything else:

| Host | `robots.txt` | Result |
|---|---|---|
| `onlinestore.heidelbergmaterials.eg` | REQ #1 | **404**, zero bytes |
| `onlinestoreapi.heidelbergmaterials.eg` | REQ #3 | **404**, `Content-Length: 0` |

Neither host publishes a `robots.txt`, so there is **no `Crawl-delay` to honour and no
`Disallow` to disclose**. `docs/robots-policy.md` therefore has nothing to bind here, and
`HttpFetcher`'s default `min_interval_s: float = 1.0` (`scrapex/connectors/base.py:175`)
would govern the pace unchanged.

---

## 1. Platform identification — a bespoke app, not a known platform

**Every fingerprint ScrapeX knows returned the identical IIS 404 page:**

| Probe | REQ | Status | Body |
|---|---|---|---|
| `/products.json` (Shopify) | #17 | 404 | `The resource you are looking for has been removed...` |
| `/wp-json/wc/store/products` (WooCommerce) | #18 | 404 | same |
| `/sitemap.xml` | #19 | 404 | same |
| `/graphql?query={storeConfig{store_code}}` (Magento) | #20 | 404 | same |
| `/rest/V1/store/storeConfigs` (Magento REST) | #21 | 404 | same |
| `/api/v2/products` (generic) | #22 | 404 | same |

Salla / Zid / Shopify-CDN / WooCommerce **homepage markers are all absent** — verified by
substring test against the fetched homepage: `salla`, `zid.store`, `cdn.zid`,
`cdn.shopify`, `wp-content`, `woocommerce` → **all `False`**. No SAP Hybris OCC path
(`/rest/v2/...`) is referenced anywhere in the app.

**What it actually is.** The storefront is an **Angular SPA served as static files from
IIS on Azure App Service**, and the data comes from a **bespoke ASP.NET Web API on a
second host**.

Response headers, REQ #2 (`GET /`):

```
Server: Microsoft-IIS/10.0
X-Powered-By: ASP.NET
Last-Modified: Tue, 21 Oct 2025 12:19:35 GMT
ETag: "dfa072f68442dc1:0"
Accept-Ranges: bytes
Set-Cookie: ARRAffinity=...;Domain=onlinestore.heidelbergmaterials.eg
```

`Last-Modified` + `ETag` + `Accept-Ranges` on the homepage means IIS is serving a **file
on disk**, not rendering a page. `ARRAffinity` is the Azure App Service load-balancer
cookie. The document itself:

```html
<!DOCTYPE html><html lang="ar" class="light-style ..." dir="rtl"
  data-assets-path="assets/" data-template="front-pages-no-customizer" data-beasties-container>
<head><base href="/">
<title>متجر هايدلبرج ماتيريالز الالكتروني -  المنتجات</title>
```

`<base href="/">` + `data-beasties-container` (Angular's critical-CSS inliner) +
`main-4XHUPALI.js` / `polyfills-*.js` / `styles-*.css` = Angular. The visual skin is the
commercial Vuexy/Sneat template.

**The API host is a different origin**, hard-coded in the bundle
(`main-4XHUPALI.js`, REQ #5):

```js
BlobSASToken="sp=r&st=2025-02-23T19:47:33Z&se=2026-02-24T03:47:33Z&...";
APIUrl="https://onlinestoreapi.heidelbergmaterials.eg/api";
ProductsUrl="https://saegyonstor001jqkagdbigu.blob.core.windows.net/files/Products";
```

### What `scrapex probe` would say today

Walking `scrapex/probe.py:76-120` against this host: Shopify miss, Woo miss, Magento
GraphQL miss, then the homepage-marker branch finds nothing, so it lands on
`scrapex/probe.py:120` — `evidence: ["reachable, but no known platform markers found"]`,
`family = ConnectorFamily.TBD_PROBE` (`scrapex/probe.py:70`), and because `TBD_PROBE` is
not in `_BUILDERS` (`scrapex/connectors/factory.py:32-42`), `implemented = False`
(`scrapex/probe.py:140`) with the note *"No connector for this family yet."*

The suggestion block it would emit (`scrapex/probe.py:125-139`) is mostly right:
`source_key: "ONLINESTORE"`, `base_url: https://onlinestore.heidelbergmaterials.eg`,
`default_region: "EG"` (from the `.eg` TLD map, `scrapex/probe.py:17`), `currency: ""`,
`vat_mode: "incl"`. Two of those are wrong for this site and are discussed in §4.

> **Note.** `probe()` only ever looks at `base_url`'s own host. It cannot discover
> `onlinestoreapi.` — that host is only knowable by reading the JS bundle, which the probe
> does not do.

---

## 2. What the site publishes, and how

### 2.1 The catalogue: 9 products, one flat array, no pagination

`GET https://onlinestoreapi.heidelbergmaterials.eg/api/Products` (REQ #4) → **200,
anonymous, no token, no cookie**:

```
Content-Type: application/json; charset=utf-8
Access-Control-Allow-Origin: https://onlinestore.heidelbergmaterials.eg
Strict-Transport-Security: max-age=2592000
```

It returns a **bare JSON array of 9 objects** — no envelope, no `page`, no `total`, **no
pagination of any kind**. (The `Access-Control-Allow-Origin` restriction is a browser
rule; a server-side fetch is unaffected, as REQ #4 demonstrates.)

The 9 products, all `isActive: true`, all `productType: Bagged`:

| # | `productLabelEn` | Plant | Company | `sapCode` / `sapCode30` |
|---|---|---|---|---|
| 1 | CEMII / A-P 42,5N SUEZ | Y210 Suez | 1332 | 2122671 / 2112671 |
| 2 | CEMII / A-P 42,5N HELWAN | Y410 Helwan | 1385 | 2122671 / 2112671 |
| 3 | CEM IV/A (P) 42.5N SR / Super | Y410 Helwan | 1385 | 2123932 / 2113932 |
| 4 | CEM IV/A (P) 42.5N SR | Y410 Helwan | 1385 | 2122932 / 2112932 |
| 5 | CEMII / A-P 42,5N TOURAH | Y410 Helwan | 1385 | 2128671 / 2118671 |
| 6 | OASIS MC 22.5X HELWAN | Y410 Helwan | 1385 | 2122714 / 2112714 |
| 7 | OASIS MC 22.5X SUEZ | Y210 Suez | 1332 | 2122714 / 2112714 |
| 8 | CEM IV/A (P) 42.5N SR | Y210 Suez | 1332 | 2122932 / 2112932 |
| 9 | CEMIII / A 42.5N Suez | Y210 Suez | 1332 | 2122052 / 2112052 |

A `Bulk` (`سائب`) product type exists (`GET /api/ProductTypes`, REQ #11) but **no product
currently uses it** — the online catalogue is bagged cement only.

### 2.2 Bilingual: every field is published twice

This site satisfies the standing bilingual rule **completely and structurally** — the
field set is literally paired. All 29 keys of a product object:

```
applicationsAr / applicationsEn
characteristicsAr / characteristicsEn
chemicalCharacteristicsAr / chemicalCharacteristicsEn
physicalCharacteristicsAr / physicalCharacteristicsEn
productLabelAr / productLabelEn
productNameAr / productNameEn
productShortDescriptionAr / productShortDescriptionEn
color, displayOrder, exWorkMaxPrice, id, isActive, isMultiPlant, isOnSale,
mainImage, maxPrice, plantId, plants, productTypeId, productTypes, sapCode, sapCode30
```

…and the nested lookups are paired too: `productTypes{productTypeNameEn, productTypeNameAr}`,
`plants{plantNameEn, plantNameAr}`, `companies{companyNameEn, companyNameAr}`,
`cities{cityNameEn, cityNameAr}`, `companyTypes{companyTypeNameEn, companyTypeNameAr}`.

**But the storefront itself is Arabic-only.** Every single Angular component is suffixed
`-ar` — all 31 of them:

```
app-home-ar, app-products-ar, app-product-info-ar, app-cart-ar, app-checkout-ar,
app-login-ar, app-register-ar, app-profile-ar, app-orders-ar, app-invoices-ar, ...
```

There is no `-en` component and no language switch. So: **the site publishes English in
its data layer and renders none of it.** Under the standing bilingual rule this is a
capture opportunity, not a defect — the English text is published, so we take it.

The two long technical fields are **HTML fragments**, not plain text. Verbatim from
product #1:

```html
"physicalCharacteristicsEn": "<p>Cement Standard Specifications Limits</p>
<p>Initial setting time (min)   ≥60</p>\r\n<p>Soundness (expansion) mm   ≤10</p>
<p>Compressive strength 2D(Mpa)  ≥10</p><p>Compressive strength 28D(Mpa)≥42.5</p>"
```

```html
"chemicalCharacteristicsEn": "<p>Sulphate (SO3) ≤3.5 % </p>
<p>Chloride content (CL-) ≤0.1 % </p>...<p><b>Target Market:</b></p>
<ul><li>Ready mix companies</li><li>General contractors</li>
<li>Precast companies</li><li>Pre-blending companies</li></ul>"
```

**Encoding difference worth knowing:** the live API returns Arabic **HTML-entity encoded**
(`&#1571;&#1587;&#1605;...`), while the same payload embedded in the prerendered HTML is
plain UTF-8. Any connector must run `html.unescape` on API strings or it will file
`&#1571;...` as the Arabic product name.

### 2.3 Prices: public, anonymous, and a six-dimensional matrix

**Prices are NOT login-gated.** The real price endpoint answers anonymously.

The Angular service (`main-4XHUPALI.js`):

```js
getProductsPricesByCityIdAndSegment(n,t){
  return this.http.get(`${this.commonService.APIUrl}/ProductsPrices/GetProductsPricesByCityIdAndSegment?cityId=${n}&segment=${t}`)}
```

The anonymous storefront hard-codes the segment: **`segment="Y6"`**. (For a signed-in
user it becomes `this.segment=n.companyTypes.sapCode`.) REQ #8, anonymous, → 200:

```json
{"id":"331334e0-...","productId":"1000007e-...","cityId":"238d0b01-...",
 "companyTypeId":"204ddc57-...","tonFrom":65,"tonTo":65,"isActive":true,"isOnSale":false,
 "salePriceY210":0.02,"fakePriceY210":0.02,"salePrice30Y210":3950.02,"fakePrice30Y210":0.02,
 "salePriceY220":0.02,"fakePriceY220":0.02,"salePrice30Y220":3950.02,"fakePrice30Y220":0.02,
 "salePriceY410":0.02,"fakePriceY410":0.02,"salePrice30Y410":3950.02,"fakePrice30Y410":0.02,
 "companyTypes":{"companyTypeNameEn":"Individuals","companyTypeNameAr":"أفراد","sapCode":"Y6"},
 "products":{...full product object...},"cities":{...}}
```

**One price is a function of six things:**

| Dimension | Values | Source |
|---|---|---|
| **product** | 9 | `productId` |
| **city / governorate** | **46** in the price table (37 flagged active) | `cityId` |
| **customer segment** | **5** — `Y6` Individuals/أفراد, `YM` Digital corp. sector/شركات المقاولات, `YT` Online Traders/تجار, `YO` Authorized Digital Dealer/موزع رقمي معتمد, `YR` Online Ready Mix/خرسانة جاهزة | `segment` |
| **plant** | **3** — `Y210` Suez, `Y220` Katameya, `Y410` Helwan | column suffix |
| **quantity tier** | **2** — `<30 t` and `>30 t` | field prefix |
| **sale vs list** | `salePrice*` vs `fakePrice*` | field prefix |

Decoded from the Angular template, verbatim:

- `"السعر لأقل من 30 طن"` (price for **less than** 30 tons) → the `salePriceYxxx` fields
- `"السعر لأكثر من 30 طن"` (price for **more than** 30 tons) → the `salePrice30Yxxx` fields
- `" / للطن "` → **the unit is per tonne**
- `"ج م"` → **the currency is EGP**
- `"خصم"` + `(t.fakePrice30Y210-t.salePrice30Y210)/t.fakePrice30Y210*100` → `fakePrice*` is
  the pre-discount / strike-through price, shown only when `isOnSale`
- `" غير متاح"` ("not available"), rendered when `t.salePrice30Y410<=.1` →
  **`0.02` and `0.0` are "no price" sentinels, not prices.** The UI hides anything ≤ 0.1.

`tonFrom` / `tonTo` also appear per row (observed values: `(5,65)`, `(30,65)`, `(65,65)`)
and are used to seed the order quantity input (`this.quants.push(o.tonFrom)`).

**The whole matrix is one anonymous request.** `GET /api/ProductsPrices` (REQ #23,
the generic table read) returns **2,070 rows / 19,038,623 bytes** — 414 rows per segment
× 5 segments; 414 = 46 cities × 9 products. Each row carries 12 price numbers, so
**12,420 price slots**.

**Only 211 of those 12,420 slots (1.7%) hold a real price.** The rest are the `غير متاح`
sentinel. Broken down:

| Segment | Y210 <30t | Y210 >30t | Y220 <30t | Y220 >30t | Y410 <30t | Y410 >30t |
|---|---|---|---|---|---|---|
| **Y6** (Individuals — the public/anonymous segment) | 12 | 64 | 8 | 40 | 14 | 63 |
| YM | – | 1 | – | 4 | – | – |
| YT | – | 1 | – | 4 | – | – |
| YO | – | – | – | – | – | – |
| YR | – | – | – | – | – | – |

So the genuinely published, anonymously reachable price set is **~211 price points, 201 of
them in the public `Y6` segment**. Distinct `>30 t` Suez-plant values observed:
`2400.02, 3030.02, 3070.02, 3900.02, 3950.02, 3980.02, 4800.02` EGP/tonne. Every real
price carries a `.02` fraction; `0.02` alone means "not available".

### 2.4 A trap: `maxPrice` / `exWorkMaxPrice` are never displayed

`/api/Products` also carries `maxPrice: 1950` and `exWorkMaxPrice: 1700` per product.
These look like the obvious price fields and **they are not the price**:

```
occurrences of "maxPrice"       in main-4XHUPALI.js: 0
occurrences of "exWorkMaxPrice" in main-4XHUPALI.js: 0
occurrences of "salePrice"      in main-4XHUPALI.js: 65
```

The storefront **never references them**. Meanwhile the city matrix prices the same
product #1 at `3950.02`. A connector that took `maxPrice` would file a number no page ever
printed, roughly half the real one. **`salePrice*` / `salePrice30*` is the published
price; `maxPrice` is an internal field the API leaks.**

*(Both values are stated by the source; I am not guessing which is "true", only recording
which one the storefront publishes to a visitor. The discrepancy is an owner question —
see §5.)*

### 2.5 VAT — stated, but only on the order total

The only VAT statement in the entire application is:

```
"شامل النقل و ضريبة القيمة المضافة (14%)"
   — including transport and value-added tax (14%)
```

It occurs **three times**, at bundle offsets 579539, 605843, 617545 — which fall in the
`app-order-details-ar`, `app-checkout-ar` and `app-cart-ar` components, each rendered
directly beneath `t.order.total`.

**It does not appear on the catalogue price.** The per-tonne listing price is rendered with
`"السعر لأكثر من 30 طن"` + `" / للطن "` + `"ج م"` and **no tax qualifier at all**. So the
honest reading is: *the site states 14% VAT and transport are included in the order total;
it makes no VAT statement about the listed per-tonne price.* This is exactly the
`evidence: "stated"` vs `"general"` distinction in `scrapex/config.py:92-95`.

### 2.6 Delivery, terms and other published facts

Extracted from the terms component (`app-accept-terms-ar`), verbatim Arabic:

- `"مواعيد التوصيل لجميع الطلبات الحاليه للاسمنت المعبا والسائب تستغرق حد ادني 30 يوما وحد اقصي 60 يوما"`
  — **delivery takes a minimum of 30 and a maximum of 60 days**, bagged and bulk.
- `"الأسعار المعلنة قابله للتعديل واعاده التسعير في أي وقت طبقا لآليات السوق"`
  — published prices may be revised at any time per market mechanisms.
- `"يتم تحديد اسعار بيع الاسمنت ... بناء على سعر بيع الأسمنت في اليوم الذي تتم فيه العملية"`
  — the price is the one in force on the transaction day.
- `"يتم تسليم الشحنة داخل حدود المحافظة المحددة أثناء الطلب"` — delivery is within the
  governorate chosen at order time. *(This is why price is per-city.)*
- `"يعتبر مقياس الشركة هو المرجع الأساسي في الوزن ... الحد المقبول للتباين هو + 2٪"`
  — the company's weighbridge governs, ±2% tolerance per truck.
- `"يتحمل متلقي الأسمنت تكاليف التحميل والتفريغ و الاكراميات"` — loading/unloading at the
  receiver's cost.
- E-invoice is issued to the Egyptian Tax Authority portal.

**Cities** (`GET /api/Cities/GetCitiesByStatus?IsActive=true`, REQ #7) — 37 active, each
bilingual and carrying a SAP ship-to code:

```json
{"id":"238d0b01-...","cityNameEn":"Al Dakahleya","cityNameAr":"الدقهلية",
 "isActive":true,"shipToCode":"2004177"}
```

**Payment methods** (endpoint names only, all auth-gated): `Payments/PayAtFawry`,
`Payments/PayByCard`, `Payments/PayByWallet`.

### 2.7 Images are currently broken site-wide

Image URLs are composed as `ProductsUrl + "/" + filename + "?" + BlobSASToken`, and the
SAS token is **baked into the shipped bundle** with a fixed expiry. Fetching one (REQ #14):

```xml
STATUS 403
<Error><Code>AuthenticationFailed</Code>
<AuthenticationErrorDetail>Signature not valid in the specified time frame:
Start [Sun, 23 Feb 2025 19:47:33 GMT] - Expiry [Tue, 24 Feb 2026 03:47:33 GMT]
- Current [Tue, 28 Jul 2026 14:28:06 GMT]</AuthenticationErrorDetail></Error>
```

**The token expired 2026-02-24 — five months ago.** Product images are 403 for everyone,
including a normal browser. This is the site's own live defect. `GET
/api/ProductImages/GetProductImagesByProductId?id=...` (REQ #12) still returns image
records, but its `imageURL` field is a single space `" "` and only
`imageFileNameAltEn` carries the filename. **ScrapeX cannot capture product images from
this source today**, and no amount of connector work changes that — the asset store
refuses anonymous reads.

### 2.8 No datasheets, no documents

The bundle names exactly nine Azure blob containers: `Products`, `Banners`, `Avatars`,
`Invoices`, `Deposits`, `Banks`, `NationalIDs`, `TaxRegistrations`,
`CommercialRegistrations`. **There is no datasheet/TDS/certificate container**, and no
endpoint serves product documents. The technical data that would live in a PDF elsewhere
is inline HTML in `physicalCharacteristics*` / `chemicalCharacteristics*` /
`applications*` (§2.2). This is the opposite of sikaegshop, which publishes 202 datasheets.

### 2.9 Crawl surface: two static pages and a JSON API

| URL | REQ | Result |
|---|---|---|
| `/` | #2 | 200, prerendered **2025-10-21** |
| `/products` → `/products/` | #15 | 200, prerendered **2025-03-07** |
| `/productinfo/1000007e-...` | #16 | **404** |

**There is no SPA fallback rewrite.** A parameterised route 404s at IIS, so **product
detail pages cannot be fetched by URL at all** — the SPA only reaches them by client-side
navigation. Any "product link" we record is a client-side route, not a fetchable page.

The two prerendered pages embed an Angular transfer-state blob:

```html
<script id="ng-state" type="application/json">
```

which contains the **verbatim `/api/Products` and `/api/Cities` responses** (9 products,
37 cities) as of the prerender date. It carries **no prices** — prices require a city
choice, made client-side. Since these snapshots are 9 and 16 months stale, they are useful
as evidence but **must not be used as a data source**. (Comparing the Oct-2025 snapshot's
`maxPrice` values to today's live ones: identical, no drift.)

### 2.10 The API is a generic REST surface

The bundle's data layer is fully generic:

```js
getTableList(n){return this.http.get(this.APIUrl+"/"+n)}
getRecordByRecordId(n,t,i){return this.http.get(`${this.APIUrl}/${i}/Get${t}By${t}Id?id=${n}`)}
addTableRecord(n,t){return this.http.post(this.APIUrl+"/"+t,n)}
delTableRecordByRecordId(n,t){return this.http.delete(`${this.APIUrl}/${t}/${n}`)}
```

`GET /api/{TableName}` works anonymously for every lookup table I tried — `Products` (#4),
`Plants` (#9), `CompanyTypes` (#10), `ProductTypes` (#11), `ProductsPrices` (#23). The
full anonymous read surface relevant to us:

| Endpoint | Gives |
|---|---|
| `GET /api/Products` | 9 products, all bilingual text, SAP codes, plant, type |
| `GET /api/ProductsPrices` | **the entire 2,070-row price matrix in one call** |
| `GET /api/ProductsPrices/GetProductsPricesByCityIdAndSegment?cityId=&segment=` | one city+segment slice |
| `GET /api/Cities/GetCitiesByStatus?IsActive=true` | 37 cities + ship-to codes |
| `GET /api/Plants`, `/api/ProductTypes`, `/api/CompanyTypes` | the lookups |
| `GET /api/ProductImages/GetProductImagesByProductId?id=` | image records (assets 403) |

Everything else in the bundle — `ApplicationUser/*`, `Orders/*`, `OrderItems/*`,
`Payments/*`, `ClientAddresses/*`, `Deposits/*`, `Notifications/*`, `Invoices` — is
account-scoped and requires a JWT. **We do not touch any of it.**

> **A crawl of this source is 2 requests.** `/api/Products` + `/api/ProductsPrices` yields
> the complete catalogue and the complete price matrix. Not 185 requests, not 37. Two.

---

## 3. What ScrapeX already has that a connector would reuse

Substantial. Nothing here needs building.

| Need | Existing infrastructure |
|---|---|
| Split storefront/API host | **`ApiConfig.base_url`** — `scrapex/config.py:56-64`, added for exactly this ("the data API lives on a DIFFERENT host than base_url"). `MASDAR` already uses it (`sources.yaml:213-214`). |
| Polite fetching | `HttpFetcher` (`scrapex/connectors/base.py:130`) — 1 req/s default (`:175`), robots-aware (`:253`), `Retry-After` honoured (`:374`), retry/backoff. |
| Family dispatch | `_BUILDERS` registry (`scrapex/connectors/factory.py:32-42`) — add one entry. |
| Row contract | `PRODUCT_PRICES` (`scrapex/rowspec.py:49-141`) via `RowBuilder`; ingest reads by name via `RowView` (`:279`). |
| Bilingual name pairs | `product_name`/`product_name_ar`, `brand`/`brand_ar` (`scrapex/rowspec.py:59-67`) — unmarked = English. Matches the site's `*En`/`*Ar` shape exactly. |
| Per-tonne unit | `unit` column (`scrapex/rowspec.py:90`) and `"ton": "tonne"` normalisation (`scrapex/ingest.py:432`). `tonne` is already vocabulary. |
| The HTML technical blocks | `ENRICHMENT` spec (`scrapex/rowspec.py:150-174`) — one row per attribute, `attribute_group` filed under `DetailGroup` (`scrapex/vocab.py:55`). `physicalCharacteristics`, `chemicalCharacteristics`, `applications`, `characteristics` land here in both languages via the `lang` column. |
| The 14% VAT sentence | `TaxEvidence` (`scrapex/config.py:84-112`) — `evidence: "stated"`, `rate_pct: 14`, `statement_text` holding the Arabic sentence verbatim. This is precisely what the block was designed for. |
| Delivery / terms facts | `DetailGroup.STORE` (`scrapex/vocab.py:65-68`) — "facts about THIS store's handling of the product". The 30–60 day lead time and governorate-boundary rule file here. |
| Price-change semantics | `pricehistory` + `pricekey` — real changes only, no daily copies. |
| Anonymous-only rule | Already the standing rule; nothing on this site needs bypassing (§2.3). |

**A note in ScrapeX's favour:** `scrapex/pricekey.py:14` states the design intent almost
word for word — *"50kg of cement from two different factories is not one price series."*
That is literally this source (3 plants). The **intent** is already correct. The
**columns** to express it are not there (§4.1).

### The closest connector family — and why it does not fit

`CUSTOM_JSON_API` is the nearest family, but it is **not a generic configurable JSON
connector**. `CustomJsonConnector` is hard-wired to sikaegshop:

```python
endpoint = f"{base}/api/products"          # scrapex/connectors/custom_json.py:271
```

…and to sikaegshop's field names (`product_id`, `product_arname`, `specail_price`), its
`{success, data[], pagination{}}` envelope, and its `?page=N` paging. Heidelberg shares
none of that: different host, different path casing, no envelope, no paging, and a price
model that is not "a number on the product".

**Verdict: a new connector class is required.** It would be a *new member of an existing
family pattern*, not new infrastructure — closest in spirit to `HybrisOccConnector` (split
API host, lookup tables, code-based identifiers).

---

## 4. What is missing — what would have to be BUILT

Five gaps, in descending order of seriousness.

### 4.1 CRITICAL — the row contract cannot express a city × segment × plant × tier price

This is the one real blocker. `PRODUCT_PRICES` (`scrapex/rowspec.py:51-128`) has one
`price` per row and **no column for any of the four dimensions that make this site's price
what it is**:

| Heidelberg dimension | Column in `PRODUCT_PRICES`? |
|---|---|
| city / governorate (46) | **none** |
| customer segment (5) | **none** — `price_trade` (`:81`) is *one* extra tier, added for sikaegshop's single B2B price, not 5 named segments |
| plant of origin (3) | **none** |
| quantity tier (<30 t / >30 t) | **none** — `basis_quantity` (`:91`) means "how many of `unit` one offer buys", not a bracket boundary |

I verified the city gap is total, not just a naming question:

```
grep -rn "governorate|city_name|\bcity\b" scrapex/*.py   →  no matches
```

**There is no sub-national geography concept anywhere in ScrapeX.**

It gets worse at the price key. `pricekey.build` hashes `MONEY_FIELDS` plus
`IDENTITY_FIELDS = ("region", "unit", "brand", "origin", "spec")`
(`scrapex/pricekey.py:51-56`), and ingest feeds them:

```python
region=r.get("country_code_alpha2", ""),          # scrapex/ingest.py:582  → "EG" for all 46 cities
unit=_unit_with_basis(r),                         # :589
brand=joined_brand(...),                          # :596
origin=r.get("country_of_origin", ""),            # :600
spec=r.get("spec_summary", ""),                   # :601
```

`region` is the **country**, so all 46 cities collapse to `EG`. And `origin` / `spec` read
row keys **that no column in `PRODUCT_PRICES` supplies** — ingest's own comment at
`scrapex/ingest.py:597-599` admits it: *"Not collected by any connector yet."* They are
wired but unreachable.

**Consequence if built naively:** every one of a product's up-to-276 city/segment/plant/tier
prices would hash to the same key differing only in amount, i.e. the same offer appearing
to change price over and over within a single crawl — the ReplaceAll/oscillation failure
mode, now sourced from a single site.

**The one existing escape hatch:** variant identity is keyed on `external_variant_id`, else
`option_fingerprint` (`scrapex/ingest.py:272-274`), and `variant_axes` /`variant_axes_ar`
(`scrapex/rowspec.py:110,121`) exist to carry axes as structured JSON. A connector *could*
mint a synthetic variant per (city, segment, plant, tier) with
`variant_axes = {"city":"Al Dakahleya","plant":"Suez","segment":"Individuals","tier":">30t"}`.

That would work mechanically. It is also a **semantic stretch** — these are not product
variations, they are pricing contexts, and `fold_variants` / the variant UI would present
them as if a customer were choosing between them. **This is an owner decision, not a
technical one**, and it is the single most important question in this report (§5).

### 4.2 The `.02` sentinel needs an explicit rule

`0.02` and `0.0` mean "not available" (`salePrice30Y410<=.1` → `" غير متاح"`). ScrapeX's
`_num` helper in the nearest connector treats non-positive as no-price
(`scrapex/connectors/custom_json.py:109` — *"0 / null / non-numeric all mean 'no price'"*),
but **`0.02` is positive** and would sail through as a two-piastre cement price. A
threshold rule (`<= 0.1` ⇒ unavailable) must be written explicitly, with the site's own
`غير متاح` condition cited as its authority.

### 4.3 No family, no probe recognition

`ConnectorFamily` (`scrapex/vocab.py:280-293`) has no member for this contract, so the
source can only be registered as `TBD_PROBE`, which `build_connector` refuses outright
(`scrapex/connectors/factory.py:56-60`). Needs: a new enum member, a `_BUILDERS` entry,
and — optionally — a probe branch. The probe cannot auto-detect this site at all without
being taught to read the JS bundle for `APIUrl`, which is a much bigger change than it
sounds and is **not** recommended for one source.

### 4.4 `probe()`'s suggestion would be wrong in two places

Not a blocker, but worth stating: `vat_mode` defaults to `INCLUSIVE`
(`scrapex/probe.py:132`) — for this site the inclusive statement covers the **order
total**, not the listed price (§2.5), so an unverified `incl` would be a claim the source
does not make. And `currency` would come back `""` (only the Magento branch fills it,
`scrapex/probe.py:96`); it must be set to `EGP` by hand from the `"ج م"` evidence.

### 4.5 What genuinely has nowhere to go

- **Images** — moot: the assets are 403 for everybody (§2.7). Nothing to build; nothing to
  capture. Worth a source-level note so the absence is not later read as a connector bug.
- **`shipToCode`** per city, **`companyCode`/`companySalesOrg`** per company,
  **`plantCode`** — SAP identifiers the site publishes. No column; they would have to ride
  in `ENRICHMENT` (which is per-product, not per-city) or be dropped. Minor.
- **Delivery lead time (30–60 days)** — a source-level fact, not a per-product one.
  `ENRICHMENT` is keyed on `external_product_id` (`scrapex/rowspec.py:153`), so a
  source-wide fact has no natural home. It could be repeated on every product, which is
  redundant but truthful.

### What is NOT needed

- **No browser rendering.** `BrowserFetcher` (`scrapex/connectors/base.py:410`) exists but
  is unnecessary — the JSON API is directly reachable and the SPA adds nothing.
- **No auth mode.** Prices are anonymous. `auth_required` (`scrapex/config.py:197`) stays
  `false`.
- **No new paging shape.** There is no pagination; both endpoints return complete arrays.
- **No new fetcher, no new transport, no schema migration** for the price *values*
  themselves — only for the dimensions in §4.1, if the owner chooses the columns route.

---

## 5. Questions only the owner can answer

1. **How should the price matrix be modelled?** (§4.1) Three options:
   - **(a) Public price only** — record just `Y6` + a chosen default plant + one tier.
     ~1 row per product, fits `PRODUCT_PRICES` today, zero schema change, and matches what
     an anonymous visitor sees. Loses 95% of the published matrix.
   - **(b) Synthetic variants** — one row per (city, segment, plant, tier) using
     `variant_axes`. Captures everything, no migration, but calls a pricing context a
     "variant".
   - **(c) Widen the contract** — real `city` / `segment` / `plant` / `qty_tier` columns
     plus `pricekey` identity fields. Correct, and the largest change.
2. **`maxPrice` (1950) vs the city matrix (3950.02)** — the storefront displays only the
   latter (§2.4). Record only the displayed one, or both with the unshown one flagged?
3. **Which segments?** `Y6` is what the public sees. `YM`/`YT` publish 5 prices each and
   `YO`/`YR` publish none. Record all five, or the public one?
4. **VAT** — record `evidence: "stated", rate_pct: 14` scoped to the order total, or
   `"unknown"` for the listing price? (My reading: the honest answer is that the site makes
   no VAT claim about the per-tonne price.)
5. **Is a 9-product source worth a bespoke connector?** It is 2 requests for ~211 real
   price points of Egyptian cement — cheap to run, but it needs a new connector class and
   possibly a contract change.

---

## Appendix — request log (23 total, ≥2.5 s apart)

| # | URL | Status |
|---|---|---|
| 1 | `onlinestore…/robots.txt` | 404 |
| 2 | `onlinestore…/` | 200 |
| 3 | `onlinestoreapi…/robots.txt` | 404 |
| 4 | `onlinestoreapi…/api/Products` | 200 |
| 5 | `onlinestore…/main-4XHUPALI.js` | 200 |
| 6 | *(counter skip)* | — |
| 7 | `…/api/Cities/GetCitiesByStatus?IsActive=true` | 200 |
| 8 | `…/api/ProductsPrices/GetProductsPricesByCityIdAndSegment?cityId=…&segment=Y6` | 200 |
| 9 | `…/api/Plants` | 200 |
| 10 | `…/api/CompanyTypes` | 200 |
| 11 | `…/api/ProductTypes` | 200 |
| 12 | `…/api/ProductImages/GetProductImagesByProductId?id=…` | 200 |
| 13 | `…/GetProductsPricesByCityIdAndSegment?…&segment=YT` | 200 |
| 14 | Azure blob product image + SAS | **403 expired** |
| 15 | `onlinestore…/products` | 200 |
| 16 | `onlinestore…/productinfo/{guid}` | **404** |
| 17–22 | `/products.json`, `/wp-json/wc/store/products`, `/sitemap.xml`, `/graphql`, `/rest/V1/store/storeConfigs`, `/api/v2/products` | all 404 |
| 23 | `…/api/ProductsPrices` (full matrix) | 200, 19 MB |
