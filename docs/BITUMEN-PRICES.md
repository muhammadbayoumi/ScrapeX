# Bitumen 60/70 price sources, seven countries — the owner's verification brief

**QUEUED, NOT STARTED.**

> «مصادر اخرى»
> — 2026-08-20, [REQ-18](archive/REQUESTS.md#req-18--bitumen-6070-prices--the-first-source-that-cannot-be-crawled)

**The brief below is his, stored verbatim.**

---

## This is the first queued source that cannot be crawled at all, and it says so itself

Every other source in the queue is a page to fetch. This one's own executive
conclusion is that **for five of the seven countries there is no public official
price to fetch**:

| | |
|---|---|
| **`quote_required`** | Saudi Arabia, UAE, Oman, Bahrain, Kuwait — no current public 60/70 price located |
| **a dated bulletin, not a live price** | Egypt — `EGP 21,542`/tonne, July 2026 |
| **already expired** | Qatar — `2,925`/tonne, valid 22–31 July 2026, and **the page shows no currency label** |

> **So its acquisition mode is correspondence, not crawling.** His own §"Suggested
> written quotation request" is a letter to send to a producer. That is not something
> this project has ever done, and it is not a gap to close — it is the shape of the
> product. Bitumen 60/70 is bulk B2B: the payable price depends on quantity, customer
> category, loading point, destination, hot-bulk versus packaged, tax, freight and
> quote validity.

**What ScrapeX can do for it is therefore narrower and more valuable than a crawl:**
be the place where a dated, sourced, caveated observation is stored so it is never
mistaken for a current market price. His `verification_status` vocabulary —
`quote_required`, `latest_official_bulletin`, `expired_official_price` — is exactly
that, and it is the most useful column in the design.

## The instruction that matters most is a refusal to compare

> *"Do not flatten these observations into one comparable price list."*

Egypt's official Arabic label is **بيتومين مؤكسد على الساخن 70/60** — which may be a
hot-applied **oxidized** product, not the internationally specified paving
penetration grade at all. Qatar's row carries **no currency label**. Comparing them,
or converting either, would manufacture a number that no official source published.

**This is `SR-1` applied to a harder case.** The source of truth is what the
publisher published; here what was published is *incomplete*, and the honest record
has to carry the incompleteness rather than resolve it. His §11 says it plainly:
**mark expired observations as expired even when they are the newest figures found.**

## Where it agrees with what is already built, and where it does not

**It agrees on the core shape, and independently.** His first design line is *"do not
store a changing price directly on the supplier record; use a separate
price-observation table so every value keeps its source, date range and commercial
basis."* That is `price_observation` — the original spine of this warehouse — arrived
at from the other direction.

**And it collides with `SR-6` in the same way the diesel list does**, but harder.
`SR-6` confirms rather than appends an unchanged price. Here two observations can
carry the **same number and different commercial bases** — ex-refinery versus
delivered, taxed versus not, 25-tonne truck versus sea. Those are **different facts
with equal values**, so a gate that compares only the number would collapse them and
lose the only thing that makes either usable. See [DIESEL-PRICES.md](DIESEL-PRICES.md)
for the period-keyed version of the same problem.

> **Together the two price briefs say the same thing about the append gate: the key
> is not the number.** For diesel it is the period; for bitumen it is the commercial
> basis. `SR-6` needs to be told what "new" means per product class, and this is the
> second measured case for it.

## And one thing here is a hard boundary rather than a task

His §12: **reject any commercial figure that cannot be traced to an official
producer, public authority, signed quote, tender award or official statistical
publication.** Trader advertisements and price-aggregation sites are explicitly
excluded. That is a rule about what may enter the warehouse at all, and it is
stricter than anything currently enforced in code.

---

*Everything below this line is the owner's brief as he sent it, unedited.*

---

# Official Bitumen 60/70 Price Sources — Seven-Country Verification Brief

**Countries:** Saudi Arabia, United Arab Emirates, Egypt, Oman, Qatar, Bahrain, and Kuwait  
**Research cut-off:** 20 August 2026 (Asia/Riyadh)  
**Product requested:** penetration-grade bitumen/asphalt 60/70  
**Purpose:** provide an agent with official sources, the latest official figures found, and a verification workflow suitable for a price database.

## Executive conclusion

Bitumen 60/70 is normally a bulk business-to-business product, not a retail fuel with a single nationwide pump price. The actual payable price may depend on quantity, customer category, loading point, delivery destination, hot-bulk versus packaged supply, taxes, freight, and quote validity.

As of the research cut-off:

- No currently valid, nationwide, public official 60/70 price was confirmed for any of the seven countries.
- Egypt and Qatar have official published figures that can be stored as dated observations, not as today's live market price.
- Saudi Arabia, the UAE, Oman, Bahrain, and Kuwait should be recorded as `quote_required` until a dated written quotation is obtained from the official producer, marketer, or competent public authority.
- Commercial marketplace prices, trader advertisements, and price-aggregation websites must not be labelled as official.

## Latest official figures located

| Country | Latest official figure found | Unit | Official reference period / validity | Status at 20 Aug 2026 | Scope and critical caveats |
|---|---:|---|---|---|---|
| Saudi Arabia | Not publicly located | — | — | `quote_required` | Aramco officially lists **Paving Asphalt**, but no public current 60/70 price table was found. Obtain a customer-specific quotation. |
| United Arab Emirates | Not publicly located | — | — | `quote_required` | SCAD has historically published an item called **Bitumen / 60/70 / Ton** for Abu Dhabi, but no current 2026 item-level value was confirmed. Historical SCAD values must not be presented as current UAE prices. |
| Egypt | **EGP 21,542** | tonne | July 2026 | `latest_official_bulletin`; not a live quote | The official Arabic label is **بيتومين مؤكسد على الساخن 70/60**. The bulletin states that prices come from some producers' lists before discounts, include taxes, and exclude transport. This wording may describe a hot-applied oxidized product rather than an internationally specified paving penetration grade; the specification must be verified before comparison. |
| Oman | Not publicly located | — | — | `quote_required` | OQ confirms bitumen production and provides an official route for “Pricing & purchasing” and domestic refined-products enquiries, but no public current 60/70 price table was found. |
| Qatar | **2,925** | tonne | 22 Jul 2026–31 Jul 2026 | `expired_official_price` | Ashghal's official raw-material price list identifies **Bitumen 60/70**. The page does not display a currency label beside the table. QAR is the expected local currency but must be confirmed before ingesting `currency_code = QAR`. The list's commercial/contractual scope must also be confirmed; it is not proof of a universal retail price. |
| Bahrain | Not publicly located | — | — | `quote_required` | Bapco officially confirms Asphalt penetration grade 60/70 and states that it can be exported in 25-metric-tonne trucks or by sea. No public current price was found. |
| Kuwait | Not publicly located | — | — | `quote_required` | KNPC officially lists bitumen as a specialty product mainly for local demand. A KNPC report confirms PEN 60/70 production, but no current public price was found. |

### Do not flatten these observations into one comparable price list

The Egyptian and Qatari entries have different product wording and commercial scope. Before comparing or converting them, verify all of the following:

1. Penetration-grade paving bitumen versus oxidized/hot-applied bitumen.
2. Bulk hot liquid versus drums, bags, or other packaging.
3. Ex-refinery, ex-works, free-on-truck, delivered, FOB, CFR, or CIF basis.
4. Tax/VAT inclusion.
5. Freight, heating, loading, handling, and insurance inclusion.
6. Minimum order quantity and customer eligibility.
7. Product standard and certificate of analysis.
8. Quote effective dates and price-adjustment mechanism.

## Official sources and quote routes

### 1. Saudi Arabia

- **Official product confirmation:** Saudi Aramco lists **Paving Asphalt** in its product range.  
  https://www.aramco.com/en/what-we-do/customers/products-and-facilities
- **Official customer route:** the same page lists the in-Kingdom Customer Care Center and customer-account route. At the research cut-off it displayed the Saudi toll-free number `800 305 5555`.
- **Official current public price found:** no.
- **Required action:** request a written 60/70 quotation and ask for the loading terminal, price basis, VAT treatment, minimum volume, validity, and product specification.
- **Language:** English and Arabic website navigation were visible. Verify that the relevant product/contact content is available in both languages before marking the record bilingual.

### 2. United Arab Emirates

- **Official statistical methodology:** Statistics Centre – Abu Dhabi (SCAD) states that its Building Materials Price statistics represent average transaction prices for materials in the Emirate of Abu Dhabi.  
  https://www.scad.gov.ae/documents/20122/0/Building%2BMaterials%2BPrices%2BMethodology%2B%281%29.pdf/633becc4-8f63-a5a3-2dad-2b4fa8a4ef2f?t=1739265634403
- **Historical official evidence:** older SCAD publications included **Bitumen / 60/70 / Ton**. These historical observations are useful for schema validation only and must not be treated as 2026 prices.
- **Official refinery contact:** ADNOC Refining contact form and telephone. Product availability and 60/70 grade must be confirmed rather than assumed.  
  https://adnoc.ae/en/adnoc-refining/contact-us/
- **Official current public price found:** no.
- **Required action:** first check the latest SCAD item-level Building Materials Prices release; if no current 60/70 value exists, obtain a written quote from an authorized producer/supplier and retain evidence of authorization.
- **Language:** SCAD and ADNOC offer Arabic and English content, but each exact document/page must be checked individually.

### 3. Egypt

- **Official publication:** Ministry of Housing / affiliated official building-materials price bulletin, Roads and Bridges section.  
  https://drso.gov.eg/drso/upload/BuildingMaterials/AttachmentA/62/%D8%A7%D9%84%D8%B7%D8%B1%D9%82%D9%88%D8%A7%D9%84%D9%83%D8%A8%D8%A7%D8%B1%D9%8A.pdf
- **Latest figure located:** `21,542 EGP/tonne` for July 2026.
- **Exact source label:** `بيتومين مؤكسد على الساخن 70/60`.
- **Published basis:** some producers' list prices, before discounts; taxes included; transport excluded.
- **Official current live quote found:** no. Store the figure as a July 2026 bulletin observation.
- **Required action:** obtain the technical data sheet or certificate of analysis and confirm whether this item is equivalent to the penetration-grade paving bitumen required by the buyer.
- **Language:** the bulletin is primarily Arabic; no complete official English edition was confirmed. Store a faithful English translation separately and retain the Arabic source label.

### 4. Oman

- **Official product confirmation:** OQ's refined-products page confirms a bitumen unit in the Sohar refinery complex.  
  https://oq.com/en/our-business/our-products/refined-products
- **Official pricing/contact route:** OQ's contact page includes “Pricing & purchasing” and “Domestic sales & refined products.” At the research cut-off it displayed `business.center@oq.com` and `+968 2214 3999`.  
  https://oq.com/en/contact-us
- **Official current public price found:** no.
- **Required action:** request a written quotation specifying grade 60/70, bulk/packaging, loading point, quantity, incoterm, taxes, transport, and quote validity.
- **Language:** English and Arabic versions of the contact pages were confirmed.

### 5. Qatar

- **Official price source:** Public Works Authority (Ashghal), Raw Materials Prices.  
  https://www.ashghal.gov.qa/en/Services/Pages/PriceList.aspx?category=2
- **Latest row located:** `Bitumen | Bitumen 60/70 | Tonne | 2925 | 22/07/2026 | 31/07/2026`.
- **Currency warning:** the public table does not visibly label its currency. Do not infer and save `QAR` without an additional official confirmation.
- **Official producer/distributor confirmation:** WOQOD states that it supplies bitumen for road asphalting and construction in Qatar.  
  https://www.woqod.com/website/en/pages/our_story
- **Official product data sheet:** WOQOD's Bitumen 60/70 PDS gives the product code, penetration range, test methods, and contact `bitumen@woqod.com.qa`.  
  https://www.woqod.com/EN/Bitumen/Documents/BITUMEN%2060%2070%20PDS.pdf
- **Current status:** the 2,925 observation expired on 31 July 2026. No August 2026 public row was located by the cut-off date.
- **Required action:** email WOQOD for a current written quote and ask Ashghal to confirm the table currency and framework-price scope.
- **Language:** the Ashghal English page and WOQOD English PDS were confirmed. An equivalent Arabic price row/PDS must be checked before marking the source bilingual.

### 6. Bahrain

- **Official product confirmation:** Bapco Refining states that its Asphalt has a penetration grade of 60/70 and is used for road construction, repairs, and waterproofing products.  
  https://www.bapco.net/en/page/crude-and-petroleum-products
- **Official logistics detail:** Bapco states that road export is in suitable 25-metric-tonne trucks and sea export is available in different cargo sizes.  
  https://www.bapco.net/en/page/loading-facilities
- **Official sales route:** Bapco International Markets manages refined-product sales including Asphalt.  
  https://www.bapco.net/en/page/international-market
- **Official contact:**  
  https://www.bapco.net/en/page/contact-us
- **Official current public price found:** no.
- **Required action:** register or contact the appropriate Bapco sales channel for a written quote. Confirm whether the price is domestic or export, truck or sea, and whether heating/loading charges are included.
- **Language:** English product pages were confirmed; verify the exact Arabic equivalents before setting bilingual availability.

### 7. Kuwait

- **Official product confirmation:** KNPC lists Bitumen as a specialty product, mainly for local demand.  
  https://www.knpc.com/en/our-business/local-marketing/products-services
- **Arabic official equivalent:**  
  https://www.knpc.com/ar/our-business/local-marketing/products-services
- **Grade evidence:** KNPC's official 2018/2019 annual report mentions production of `PEN 60/70` and `MC-70`. This confirms grade capability, not a current price.  
  https://www.knpc.com/getmedia/50fea02f-88de-4244-9796-02eefd380360/annual-report-2018-2019-en.pdf?ext=.pdf
- **Official local marketing route:** the KNPC directory lists the Local Marketing function; verify current personnel/telephone immediately before use.  
  https://www.knpc.com/en/about-us/governance/knpc-directory
- **Official contact form:**  
  https://www.knpc.com/en/contact-us
- **Official current public price found:** no.
- **Required action:** request a dated written quotation from KNPC Local Marketing, including buyer eligibility, loading location, specifications, tax/subsidy treatment, transport, minimum volume, and validity.
- **Language:** Arabic and English product pages were confirmed.

## Recommended database design

Do not store a changing price directly on the supplier/company record. Use a separate price-observation table so every value keeps its source, date range, and commercial basis.

### `bitumen_suppliers`

| Column | Type / example | Notes |
|---|---|---|
| `supplier_id` | UUID | Primary key. |
| `country_code` | `SA`, `AE`, `EG`, `OM`, `QA`, `BH`, `KW` | ISO alpha-2 code; no Arabic duplicate required. |
| `supplier_name` | text | Official English or Latin-script name. |
| `supplier_name_ar` | text, nullable | Official Arabic name only when officially available. |
| `supplier_type` | enum | `state_producer`, `state_marketer`, `government_authority`, `authorized_supplier`. |
| `website_url` | URL | Official domain only. |
| `sales_contact_url` | URL, nullable | Official quote/contact route. |
| `sales_email` | text, nullable | Preserve only if officially published. |
| `sales_phone` | text, nullable | Store in E.164-compatible form where possible. |
| `source_languages` | array | Example: `["ar", "en"]`; verify exact page/document, not merely the site's language switcher. |
| `last_verified_at` | datetime | UTC timestamp. |

### `bitumen_products`

| Column | Type / example | Notes |
|---|---|---|
| `product_id` | UUID | Primary key. |
| `supplier_id` | UUID | Foreign key. |
| `product_name` | `Bitumen 60/70` | Normalized English name. |
| `product_name_ar` | `بيتومين 60/70` | Arabic normalized name. |
| `official_product_label` | text | Exact official English label, if available. |
| `official_product_label_ar` | text, nullable | Exact Arabic source label; do not overwrite with a translation. |
| `grade` | `60/70` | Keep as text. |
| `product_class` | enum | `penetration_grade`, `oxidized`, `cutback`, `emulsion`, `polymer_modified`, `unknown`. |
| `penetration_min` | integer, nullable | Example: `60`. |
| `penetration_max` | integer, nullable | Example: `70`. |
| `test_standard` | text, nullable | Record exactly as published; do not infer a standard. |
| `specification_url` | URL, nullable | Official PDS/COA/specification. |
| `packaging_options` | array, nullable | Examples: `bulk_hot`, `drum`, `bag`, `tanker`, `vessel`. |
| `equivalence_status` | enum | `confirmed`, `possible`, `not_equivalent`, `unverified`. Essential for the Egypt observation. |

### `bitumen_price_observations`

| Column | Type / example | Notes |
|---|---|---|
| `price_observation_id` | UUID | Primary key. |
| `product_id` | UUID, nullable | Nullable until exact product equivalence is confirmed. |
| `country_code` | text | Required. |
| `price_amount` | decimal, nullable | Null when `quote_required`. |
| `currency_code` | ISO 4217, nullable | Example: `EGP`; leave null if the official source does not state the currency. |
| `currency_verification_status` | enum | `explicit`, `confirmed_separately`, `inferred`, `unknown`. |
| `unit` | enum | Prefer `metric_tonne`; retain the source unit too. |
| `source_unit_label` | text | Exact text such as `Tonne` or `طن`. |
| `price_scope` | enum | `official_price_list`, `government_framework`, `official_statistical_average`, `producer_list`, `private_quote`, `general_market`, `unknown`. |
| `price_basis` | text, nullable | Example: `producer list price before discounts`. |
| `price_basis_ar` | text, nullable | Arabic content where available. |
| `incoterm` | text, nullable | `EXW`, `FCA`, `FOB`, `CFR`, `CIF`, etc.; do not guess. |
| `tax_included` | boolean, nullable | Use null when unstated. |
| `transport_included` | boolean, nullable | Use null when unstated. |
| `loading_heating_included` | boolean, nullable | Important for hot bulk bitumen. |
| `minimum_order_quantity_mt` | decimal, nullable | Do not assume Bapco's 25-MT truck size is the commercial MOQ. |
| `customer_category` | text, nullable | Government, contractor, industrial, export, etc. |
| `effective_from` | date, nullable | Required for a valid comparison. |
| `effective_to` | date, nullable | Required where published. |
| `reference_month` | `YYYY-MM`, nullable | For statistical bulletins. |
| `data_status` | enum | `current_quote`, `latest_official_bulletin`, `expired_official_price`, `historical_official`, `quote_required`, `unverified`. |
| `source_title` | text | Official document/page title. |
| `source_title_ar` | text, nullable | Arabic title if officially available. |
| `source_url` | URL | Direct official page/document URL. |
| `source_language` | `ar` or `en` | Language of the actual evidence. |
| `retrieved_at` | datetime | UTC timestamp. |
| `quote_reference` | text, nullable | Official quotation number or tender/framework reference. |
| `evidence_file_hash` | text, nullable | Recommended for archived PDFs/quotes. |
| `notes` | text, nullable | English notes. |
| `notes_ar` | text, nullable | Arabic notes. |

### Arabic-column rule

Add the `_ar` suffix only to translatable text fields. Do **not** duplicate numbers, dates, currency codes, country codes, URLs, booleans, or identifiers into Arabic columns.

Examples:

- `supplier_name` and `supplier_name_ar`
- `product_name` and `product_name_ar`
- `official_product_label` and `official_product_label_ar`
- `price_basis` and `price_basis_ar`
- `notes` and `notes_ar`

No duplicates are needed for `price_amount`, `currency_code`, `effective_from`, `effective_to`, or `source_url`.

## Verification instructions for the agent

For every country, the agent must:

1. Re-open every official URL and record the retrieval timestamp.
2. Check whether a newer publication or price row exists after the dates in this brief.
3. Search the Arabic and English versions independently; do not assume translations contain identical rows.
4. Preserve exact official product labels before translating or normalizing them.
5. Confirm that `60/70` means penetration range and is not a reversed label, oxidized grade, or unrelated product code.
6. Obtain or verify the PDS/COA and its standard, test methods, penetration, ductility, flash point, solubility, and source refinery.
7. Confirm the currency from the official source. This is mandatory for the Qatar Ashghal row.
8. Confirm whether a displayed figure is a framework price, statistical average, producer list price, tender price, subsidized local price, or customer-specific quote.
9. Record the commercial basis: ex-refinery/ex-works/delivered/FOB/CFR/CIF, loading point, freight, heating, handling, tax, and insurance.
10. Record minimum order, packaging, delivery location, customer category, quote number, effective dates, and payment terms.
11. Mark expired observations as expired even if they are the newest official figures found.
12. Reject any commercial figure that cannot be traced to an official producer, public authority, signed quote, tender award, or official statistical publication.

## Suggested written quotation request

> Please provide your current official quotation for penetration-grade Bitumen 60/70. State the currency and price per metric tonne; product specification and applicable standard; supply form (hot bulk/drum/bag); minimum order quantity; loading point and delivery destination; price basis or Incoterm; whether VAT/tax, heating, loading, transport, insurance, and handling are included; customer eligibility; payment terms; and the quote's effective-from and effective-to dates. Please include a quotation reference and current product data sheet/certificate of analysis.

## Initial seed observations

These are safe seed records only if all caveats are retained:

```json
[
  {
    "country_code": "EG",
    "official_product_label_ar": "بيتومين مؤكسد على الساخن 70/60",
    "product_class": "unverified",
    "price_amount": 21542,
    "currency_code": "EGP",
    "currency_verification_status": "explicit",
    "unit": "metric_tonne",
    "price_scope": "producer_list",
    "tax_included": true,
    "transport_included": false,
    "reference_month": "2026-07",
    "data_status": "latest_official_bulletin",
    "equivalence_status": "unverified"
  },
  {
    "country_code": "QA",
    "official_product_label": "Bitumen 60/70",
    "product_class": "penetration_grade",
    "price_amount": 2925,
    "currency_code": null,
    "currency_verification_status": "unknown",
    "unit": "metric_tonne",
    "price_scope": "official_price_list",
    "effective_from": "2026-07-22",
    "effective_to": "2026-07-31",
    "data_status": "expired_official_price"
  }
]
```

For Saudi Arabia, the UAE, Oman, Bahrain, and Kuwait, create `quote_required` placeholders without a numeric `price_amount`. A missing official public price must remain null, not zero.
