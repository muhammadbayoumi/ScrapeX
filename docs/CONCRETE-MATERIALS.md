# Reinforced-concrete material prices, seven countries — the owner's brief

**QUEUED, NOT STARTED — and he said so himself:**

> «مصادر جديدة ضيفها للقائمة **سياتى دورها يوما ما**»
> — 2026-08-20, [REQ-19](archive/REQUESTS.md#req-19--reinforced-concrete-material-prices-its-turn-will-come)

Cement, reinforcing steel, structural steel sections, sand, coarse aggregate and
water, across Saudi Arabia, the UAE, Egypt, Oman, Qatar, Bahrain and Kuwait.
**The brief below is his, stored verbatim.**

---

## This is the most carefully-typed of the price briefs, and its §3 is the reason

Its source-type table has a column headed **"Can it populate `price_amount`?"**, and
for three of the ten types the answer is **No**:

| type | may it be a price? |
|---|---|
| `official_absolute_price`, `official_dated_price_list`, `official_historical_price` | **yes** |
| `official_utility_tariff` | yes, **in its own table** |
| `commercial_quote` | yes, **never labelled official** |
| `official_price_index` | **no** — an index is not a price |
| `official_approved_source`, `official_specification` | **no** — an approved-supplier list does not establish a market price |
| `authenticated_portal` | only after the exact result is captured and archived |
| `quote_required` | no, until a quotation exists |

> **That is a provenance-typed price model**, and it is stricter than anything this
> warehouse enforces. It is why his design gives `price_index_observations` and
> `water_tariffs` tables of their own rather than a `kind` column on one table.

## Water is the sharpest example in any of the briefs

His §2.2 refuses to store a single water price. The official network tariff is **one
component** of the site cost, beside meter charges, wastewater charges, tanker
filling, transport, storage and testing — and *"a potable-water tariff alone does not
prove technical suitability"* for concrete mixing or curing.

**One number here would be false in both directions:** too low as a delivered cost,
and not evidence of fitness for purpose. So the tariff and the delivered quotation
are two records, and the technical suitability is a third thing again.

## It completes a pattern across three of his briefs, now recorded as a finding

With [DIESEL-PRICES.md](DIESEL-PRICES.md) and [BITUMEN-PRICES.md](BITUMEN-PRICES.md),
this is the **third** independent case that `SR-6` — *an unchanged price is confirmed,
not appended* — keys on the wrong thing:

| brief | what carries the fact |
|---|---|
| diesel | the **period** |
| bitumen | the **commercial basis** |
| **this one** | the **source type** |

Three products, three axes, three briefs written separately. [DEC-12](archive/BACKLOG.md) is
that finding, and it is recorded **before** any of these collections is scheduled,
because the failure it describes is silent and the data is not re-fetchable: dated
bulletins expire, and the Qatar bitumen figure had already expired when he sent it.

## And one honest note about its own coverage

Read its §12 before its §5. Its own bottom line is that **only Saudi Arabia, Egypt
and Qatar have usable official absolute prices**; Oman and Kuwait offer **indices**,
which by its own §3 are not prices; and Bahrain offers approval and specification
evidence, which is not a price either. So for four of seven countries this is a
`quote_required` source in the same sense the bitumen brief is.

**Its §2.1 also flags a scope honesty point that is easy to lose:** structural steel
sections are **not** constituents of reinforced concrete. They are in scope because he
asked for them and they are procured in the same workflow — which is a reason to keep
them a separate material, not to redefine the product.

---

*Everything below this line is the owner's brief as he sent it, unedited.*

---

# Official Sources for Reinforced-Concrete Material Prices in Seven Countries

## Agent Research and Verification Brief

**Countries:** Saudi Arabia, United Arab Emirates, Egypt, Oman, Qatar, Bahrain, and Kuwait  
**Materials:** cement, reinforcing steel, structural steel sections, sand, coarse aggregate, and water  
**Research cut-off:** 20 August 2026  
**Required output language:** English field names, with Arabic content in matching fields suffixed `_ar`

---

## 1. Objective

Build a verified, source-traceable database of official price observations and related official evidence for the listed materials in the seven countries.

The agent must distinguish between:

1. an official absolute price;
2. an official dated price list;
3. an official price index;
4. an official utility tariff;
5. an approved-product, approved-supplier, or specification source; and
6. a commercial quotation.

These are not interchangeable. An index value is not a price, and an approved supplier list does not establish a market price.

---

## 2. Important Scope Notes

### 2.1 What counts as a reinforced-concrete constituent

The primary constituents are cement, fine aggregate, coarse aggregate, water, and reinforcing steel. Admixtures and supplementary cementitious materials may also be used, but they are outside the present scope.

Structural steel sections such as I-beams, H-beams, channels, and angles are **not** constituents of reinforced concrete. They are included because they were explicitly requested and are commonly procured in the same construction-material workflow.

### 2.2 Water must be handled differently

Public agencies normally publish a network-water tariff, not a construction-site “mixing water price.” The effective site cost may include:

- utility tariff;
- fixed or meter charges;
- wastewater charges;
- tanker filling price;
- tanker transport and delivery;
- storage; and
- quality testing or treatment.

Therefore, store a utility tariff separately from a delivered tanker quotation. Also verify that the water complies with the project specification for concrete mixing and curing. A potable-water tariff alone does not prove technical suitability.

### 2.3 Current and historical sources

A source may be official but outdated. Record the date actually shown by the source and never label a historical price as current. If no current official absolute price exists, mark the record `quote_required`; do not estimate or copy a commercial web price into an official-price table.

---

## 3. Source-Type Codes

| Code | Meaning | Can it populate `price_amount`? |
|---|---|---:|
| `official_absolute_price` | A government statistical publication giving a currency amount per unit | Yes |
| `official_dated_price_list` | A government or public-works price list with an explicit validity period | Yes, for that period only |
| `official_historical_price` | An official absolute price whose validity period has ended | Yes, but only as historical data |
| `official_price_index` | A WPI, PPI, CCI, or similar index | No; store in a separate index observation |
| `official_utility_tariff` | A regulated water charge | Yes, in a separate water-tariff table |
| `official_approved_source` | Approved manufacturer, supplier, product, or laboratory list | No |
| `official_specification` | Technical requirements, test methods, or material standards | No |
| `authenticated_portal` | Official data exists behind login or an interactive calculator | Only after the exact result is captured and archived |
| `commercial_quote` | A written supplier or transporter quotation | Yes, but never label it official |
| `quote_required` | No usable current official absolute price was located | No until a quotation is obtained |

---

## 4. Quick Availability Matrix

The entries below describe the best verified public route located by the research cut-off. `Quote` means that a current project-specific quotation is still required.

| Country | Cement | Rebar | Steel sections | Sand | Coarse aggregate | Water |
|---|---|---|---|---|---|---|
| Saudi Arabia | Official national absolute prices | Official national absolute prices by diameter | Index/Quote | Official national absolute prices | Partial absolute series/Quote for exact grading | Official tariff calculator + site-delivery check |
| UAE | Historical official emirate-level prices; current quote | Historical official emirate-level prices; current quote | Coverage must be checked; current quote | Historical official emirate-level prices; current quote | Historical official emirate-level prices; current quote | Emirate-specific utility tariff + tanker quote |
| Egypt | Official monthly bulletin | Official monthly bulletin | Official bulletin category | Official bulletin, including governorate tables in some releases | Official bulletin distinguishes `سن` and `زلط` | Utility/account tariff + tanker quote where applicable |
| Oman | Official price index; Quote | Official price index; Quote | Official price index; Quote | Official price index; Quote | Official price index; Quote | Official non-residential network tariff |
| Qatar | Official list exists, but latest row must be checked | Official dated Ashghal list | Quote | Official historical list; current row must be checked | Official historical gabbro list; current row must be checked | Official Kahramaa category/calculator + tanker check |
| Bahrain | Approved-source/specification evidence; Quote | Approved-source/specification evidence; Quote | Approved-source/specification evidence; Quote | Approved-source/specification evidence; Quote | Approved-source/specification evidence; Quote | Official non-domestic network tariff |
| Kuwait | Official WPI/PPI; Quote | Official WPI/PPI + quality-source directory; Quote | Official WPI/PPI; Quote | Official WPI/PPI; Quote | Official WPI/PPI; Quote | Official sector tariff per 1,000 imperial gallons |

---

## 5. Country Source Register

## 5.1 Saudi Arabia

### Primary absolute-price source

**Authority:** General Authority for Statistics (GASTAT)  
**Publication:** Average Prices of Goods and Services, July 2026, Arabic-English PDF  
**Official URL:**

<https://www.stats.gov.sa/documents/20117/2435267/Average%2BPrices%2Bof%2BGoods%2Band%2BServices%2BJul%2B2026-AR-EN%2B%281%29.pdf/e3a0c7cb-9318-003c-b51e-e6719f37f1cf?download=true&t=1786514996658&version=1.0>

**Geographic scope:** national average  
**Frequency:** monthly  
**Language:** Arabic and English  
**Source type:** `official_absolute_price`

Verified material coverage includes:

- black national cement, 50 kg;
- white national cement, 50 kg;
- reinforcing steel by diameter, per tonne;
- soft white sand, per cubic metre;
- red sand, per cubic metre;
- mixed sand and pebble, per cubic metre; and
- several ready-mix concrete classes.

The July 2026 publication does not provide a clearly identified item-level series for fabricated structural steel sections such as I/H beams, channels, or angles. Obtain a written supplier quotation for the exact section and use an official construction, wholesale, or producer price index only as a movement benchmark.

### Water source

**Authority:** National Water Company (NWC)  
**Source:** official tariff calculator referenced by NWC service guidance  
**Tariff calculator:** <https://ebranch.nwc.com.sa/Arabic/Pages/TariffCalculator.aspx>  
**Service guidance:** <https://sudpprod.nwc.com.sa/publicfiles/ServiceusermanualEn.pdf>  
**Language:** Arabic; English guidance is available  
**Source type:** `official_utility_tariff`

The agent must save the selected customer category, consumption quantity, region if requested, calculation date, and calculator output. For tanker-supplied construction sites, obtain the filling and delivery price separately.

### Saudi verification rules

- Confirm that the first figure extracted is the current-month value, not the previous month or previous year.
- Preserve the original diameter for every reinforcing-steel observation.
- Do not map “mixed sand and pebble” to a specified coarse aggregate without checking the grading and intended use.
- Record the actual national-average scope; do not claim that the value is a city-specific delivered price.

---

## 5.2 United Arab Emirates

There is no single verified public federal table giving a current delivered price for every requested material. Price collection and utility tariffs are emirate-specific.

### Abu Dhabi building-material source

**Authority:** Statistics Centre – Abu Dhabi (SCAD)  
**Source:** Building Materials Prices methodology  
**Official URL:** <https://www.scad.gov.ae/documents/20122/0/Building%2BMaterials%2BPrices%2BMethodology%2B%281%29.pdf/633becc4-8f63-a5a3-2dad-2b4fa8a4ef2f?t=1739265634403>  
**Publication catalogue:** <https://scad.gov.ae/web/guest/related-publications>  
**Geographic scope:** Emirate of Abu Dhabi, not the whole UAE  
**Frequency described by methodology:** monthly  
**Language:** English publication and bilingual SCAD website  
**Source type:** `official_absolute_price` when an item-level monthly release is available; otherwise `official_historical_price`

SCAD groups include cement, aggregates and sand, concrete, and steel. The public catalogue must be checked for the most recent downloadable item-level release. The latest release located during this review was not current to August 2026, so the agent must not present it as a current UAE price.

### Dubai building-material source

**Authority:** Dubai Statistics Center / Digital Dubai  
**Candidate official publication:** Average Building Material Prices 2025  
**Official URL:** <https://www.dsc.gov.ae/Report/Avg-BMP-2025.pdf>  
**Geographic scope:** Dubai only  
**Source type:** `official_historical_price` until a newer official edition is verified

The URL should be re-opened and the PDF archived. If access fails, do not infer its values from search snippets or third-party summaries.

### Dubai water source

**Authority:** Dubai Electricity and Water Authority (DEWA)  
**English:** <https://www.dewa.gov.ae/en/consumer/billing/slab-tariff>  
**Arabic:** <https://www.dewa.gov.ae/ar-AE/consumer/billing/slab-tariff>  
**Geographic scope:** Dubai  
**Language:** Arabic and English  
**Source type:** `official_utility_tariff`

The page gives category- and slab-dependent water tariffs, fuel surcharge information, and tax treatment. Store each component separately. Do not apply a Dubai tariff to Abu Dhabi or another emirate.

### UAE verification rules

- Store `emirate` as a mandatory field.
- Verify whether “steel” means reinforcing bars, structural sections, steel mesh, or another product.
- Record gabbro, crushed aggregate, and natural gravel as different product descriptions unless the official source explicitly combines them.
- For an active project, request a delivered quotation for the exact emirate, quarry/source, grading, and site location.

---

## 5.3 Egypt

### Primary building-material source

**Authority:** Ministry of Housing, Utilities and Urban Communities — Central Administration for Building Materials  
**Methodology:** <https://img.mhuc.gov.eg/images/1abdd0a9-a225-44b2-8d25-b386489ec545.pdf>  
**2026 bulletin example:** <https://img.mhuc.gov.eg/images/7e3119c3-e31c-48e3-a9ef-e2f0749c3c8e.pdf>  
**February 2026 bulletin cover/source:** <https://img.mhuc.gov.eg/images/e9f4bc7c-43e9-425d-b8bc-32652ec3ac48.pdf>  
**Official roads-and-bridges material bulletin example, July 2026:** <https://drso.gov.eg/drso/upload/BuildingMaterials/AttachmentA/62/%D8%A7%D9%84%D8%B7%D8%B1%D9%82%D9%88%D8%A7%D9%84%D9%83%D8%A8%D8%A7%D8%B1%D9%8A.pdf>  
**Language:** primarily Arabic  
**Source type:** `official_absolute_price`

Verified categories across the official bulletin system include:

- reinforcing steel;
- cement;
- structural and metal sections;
- ready-mix concrete;
- sand;
- crushed coarse aggregate, commonly `سن`;
- natural gravel, commonly `زلط`; and
- related road and bridge materials.

The methodology indicates monthly collection around the middle of the month. Many market-price observations are scoped to Greater Cairo. Some basic-material tables provide governorate-by-governorate prices. Taxes and transport treatment must be captured from the note attached to the specific table; do not assume one note applies to the entire bulletin.

### Historical governorate comparison source

**Authority:** same ministry  
**Official URL:** <https://img.mhuc.gov.eg/images/feb46b50-153d-4349-af33-100fb528fdf4.pdf>  
**Use:** demonstrates official coverage of sand, `سن`, and `زلط` by governorate  
**Source type:** `official_historical_price`

This source is historical and must not be used as an August 2026 price.

### Water sources

**Authority:** Holding Company for Water and Wastewater (HCWW)  
**Commercial sector:** <https://www.hcww.com.eg/%D8%A7%D9%84%D9%82%D8%B7%D8%A7%D8%B9-%D8%A7%D9%84%D8%AA%D8%AC%D8%A7%D8%B1%D9%8A/>  
**Non-domestic water connection service:** <https://www.hcww.com.eg/%D8%AA%D9%88%D8%B5%D9%8A%D9%84-%D8%AE%D8%AF%D9%85%D8%A9-%D9%85%D9%8A%D8%A7%D9%87-%D8%A7%D9%84%D8%B4%D8%B1%D8%A8-%D8%B9%D8%AF%D8%A7%D8%AF-%D8%B1%D8%A6%D9%8A%D8%B3%D9%8A-%D8%A3%D9%88%D9%84-%D9%85-2/>  
**Language:** Arabic  
**Source type:** official service source; the current tariff must be verified for the local utility, governorate, and activity

The agent must obtain the applicable tariff or actual bill from the local water company. If the construction site uses tanker water, record the tanker volume and delivered price separately.

### Egypt verification rules

- Do not merge `سن` and `زلط`. `سن` generally denotes crushed stone; `زلط` generally denotes natural gravel. Their grading and engineering use can differ.
- Store the governorate or Greater Cairo scope for every record.
- Record whether the price is a producer/company price or a market/consumer price.
- Record minimum-quantity conditions, tax inclusion, and transport exclusion exactly as printed.

---

## 5.4 Oman

### Primary official index source

**Authority:** National Centre for Statistics and Information (NCSI)  
**National statistics portal:** <https://www.ncsi.gov.om/NationalStatistics>  
**Producer Price Index publication, first quarter 2026:** <https://api.ncsi.gov.om/uploads/keyindicators/real_estate_price_index_1782790856.pdf>  
**Language:** Arabic and English  
**Source type:** `official_price_index`

The official index publication includes relevant groups such as:

- stone, sand, and clay;
- glass, cement, and marble products;
- raw and manufactured iron, steel, or aluminium products;
- fabricated iron, steel, or aluminium products; and
- water.

These are index series, not OMR-per-tonne or OMR-per-cubic-metre prices. Store them in an index table and obtain written commercial quotations for the exact cement, rebar, section, sand, and aggregate items.

### Water sources

**Authority:** Authority for Public Services Regulation (APSR)  
**Official URL:** <https://apsr.om/pages/products/water-wastewater>  

**Provider:** Nama Water Services  
**Official tariff page:** <https://nws.nama.om/en-us/Services-and-Products/Services-Tariffs-and-Fees>  
**Language:** Arabic and English  
**Source type:** `official_utility_tariff`

The public non-residential network-water tariff verified during this review was **OMR 1.320 per m³** for commercial and government customers. The agent must re-check the effective date before importing it and must store wastewater or other service charges separately. Tanker and delivery prices require their own quotations.

### Oman verification rules

- Never convert an index point into an absolute material price.
- Require the quarry/source and grading for sand and aggregate quotations.
- Identify whether steel observations refer to raw steel, fabricated products, rebar, or finished structural sections.

---

## 5.5 Qatar

### Primary public-works material price list

**Authority:** Public Works Authority (Ashghal)  
**Source:** Raw Materials Price List  
**Official URL:** <https://www.ashghal.gov.qa/en/Services/Pages/PriceList.aspx?category=2>  
**Language:** English page; Arabic website interface is also available  
**Source type:** `official_dated_price_list`

The public list has included, depending on period:

- reinforcing steel by diameter;
- ordinary Portland and sulphate-resistant cement, bulk or bagged;
- gabbro aggregate;
- washed sand; and
- bitumen.

Coverage is not identical every month. In the 2026 records reviewed, reinforcement-steel entries were available, while current 2026 entries for every cement, sand, and aggregate subtype were not visible. Historical rows prove that a material was once listed, not that its price is current.

Every extracted Ashghal record must include its displayed validity start and end dates. The agent must also verify the currency from an authoritative page or document before setting `currency`; do not infer it solely from context.

No verified item-level structural-section price was located in the list. Obtain a quotation for the exact section profile, grade, length, finish, and delivery basis.

### Official index source

**Authority:** National Planning Council (NPC)  
**Producer Price Index release:** <https://www.npc.qa/en/statistics/Pages/news/05022026.aspx>  
**Language:** Arabic and English website  
**Source type:** `official_price_index`

Use the index only to monitor market movement in basic metals and cement/non-metallic mineral products.

### Water sources

**Authority:** Qatar General Electricity and Water Corporation (Kahramaa)  
**Tariff categories:** <https://www.km.qa/CustomerService/pages/tariff.aspx>  
**Tariff calculator:** <https://www.km.qa/CustomerService/pages/tariffCalculation.aspx>  
**Laws and regulations:** <https://www.km.qa/Pages/LawsRegulations.aspx>  
**Language:** Arabic and English  
**Source type:** `authenticated_portal` or `official_utility_tariff`, depending on the captured result

Kahramaa exposes different customer categories, including commercial, industrial, bulk industrial, and water tanker. Select the category that actually applies. Save the inputs, output, calculation date, and any tariff schedule that supports the result.

### Qatar verification rules

- Treat every Ashghal price as valid only for its stated date range.
- Do not assume that gabbro of one nominal size is interchangeable with another.
- For construction water, check whether the project is billed through a network meter, a bulk supply, or the water-tanker category.

---

## 5.6 Bahrain

No verified public government table providing current absolute prices for all requested construction materials was located. Official Bahrain sources are useful for product approval, supplier qualification, testing, and technical compliance. Current prices still require written quotations.

### Approved civil-material sources

**Authority:** Ministry of Works  
**Approved civil materials/products list, dated 31 October 2024:** <https://www.works.gov.bh/Arabic/Publications/ResearchandReports/DocLib/Pre-Qualification%20List%20for%20Civil%20Materials%20as%20of%2031%20October%202024.pdf>  
**Approved independent testing laboratories, dated 31 January 2026:** <https://www.works.gov.bh/Arabic/Publications/DocLib/Approved%20Independent%20Materials%20Testing%20Laboratories%20as%20of%2031%20January%202026.pdf>  
**Standard construction specifications:** <https://www.works.gov.bh/Arabic/Tenders/Pages/StandardConstruction.aspx>  
**Concrete specification module:** <https://www.works.gov.bh/English/Publications/standards/Documents/APPROVED_Module%2002_Concrete_July%2009/files/6.html>  
**Language:** Arabic and English pages/documents, depending on source  
**Source types:** `official_approved_source` and `official_specification`

These sources support verification of cement, aggregate, reinforcing steel, concrete, and water testing, but they do not establish a current market price. Obtain quotations only from currently qualified and technically acceptable sources, and verify expiry dates because an older approval may no longer be valid.

### Water sources

**Authority:** Electricity and Water Authority (EWA)  
**English tariff page:** <https://www.ewa.bh/en/tariff>  
**Arabic tariff page:** <https://www.ewa.bh/ar/tariff>  
**Tariff information:** <https://www.ewa.bh/en/ewa-tariffs>  
**Language:** Arabic and English  
**Source type:** `official_utility_tariff`

The non-domestic/commercial water tariff verified during this review was **775 fils per m³**, equivalent to **BHD 0.775 per m³**. Re-check the effective date and customer category before import. A delivered tanker price remains separate.

### Bahrain verification rules

- Mark all material price cells `quote_required` unless a new official absolute-price publication is found.
- Use Ministry of Works lists for technical eligibility, not price.
- Verify the current approved-product list rather than relying solely on the 2024 list linked above.

---

## 5.7 Kuwait

### Official price-index sources

**Authority:** Central Statistical Bureau (CSB)  
**Wholesale Price Index, Arabic:** <https://www.csb.gov.kw/Pages/Statistics?ID=35&ParentCatID=3>  
**Wholesale Price Index, English:** <https://www.csb.gov.kw/Pages/Statistics_en?ID=35&ParentCatID=3>  
**Producer Price Index, Arabic:** <https://www.csb.gov.kw/Pages/Statistics?ID=62&ParentCatID=3>  
**Producer Price Index, English:** <https://www.csb.gov.kw/Pages/Statistics_en?ID=62&ParentCatID=3>  
**Latest releases located:** first quarter 2026  
**Language:** Arabic and English  
**Source type:** `official_price_index`

The CSB publishes PDF and Excel releases. These are indices, not current KWD-per-bag, KWD-per-tonne, or KWD-per-cubic-metre prices. They may be used for escalation or market-movement analysis only after the exact item group, base period, and index value are verified.

### Official industrial and quality sources

**Authority:** Public Authority for Industry (PAI)  
**Industrial Directory, seventh edition 2026:** <https://pai.gov.kw/industrial-directory>  
**2026 directory announcement:** <https://pai.gov.kw/news-list/-/asset_publisher/zqcw/content/ann_may_2026_1>  
**Imported-goods conformity page:** <https://ksm.pai.gov.kw/sites/cm/ar/Pages/ImportedConformity.aspx>  
**Language:** Arabic; some English pages are available  
**Source types:** `official_approved_source` and official manufacturer directory

The conformity page identifies mandatory quality requirements for reinforcing steel and Portland cement. The directory can help identify manufacturers, but neither source should populate a price field.

### Water sources

**Authority:** Ministry of Electricity, Water and Renewable Energy (MEWRE)  
**Arabic investor FAQ:** <https://investors.mew.gov.kw/ar/faq-s>  
**English investor FAQ:** <https://investors.mew.gov.kw/en/faq-s>  
**Bilingual tariff PDF:** <https://www.mew.gov.kw/media/ywtfjidr/water-2023.pdf>  
**Language:** Arabic and English  
**Source type:** `official_utility_tariff`

The verified tariff schedule is expressed in KWD per **1,000 imperial gallons**, not per cubic metre. It lists different rates for government, investment/commercial, industrial/agricultural, productive industrial/agricultural, other, and water-filling-station categories.

For example, the official schedule reviewed showed:

| Category | Official tariff basis |
|---|---:|
| Government | KWD 4.000 per 1,000 imperial gallons |
| Investment and commercial | KWD 2.000 per 1,000 imperial gallons |
| Industrial and agricultural | KWD 1.250 per 1,000 imperial gallons |
| Productive industrial and agricultural | KWD 0.750 per 1,000 imperial gallons |
| Water filling stations | KWD 0.500 per 1,000 imperial gallons |

Store the original unit and value before conversion. If converting, use **1 imperial gallon = 0.00454609 m³** and record the conversion factor. The filling-station tariff is not the same as the delivered tanker price.

### Kuwait verification rules

- Do not load CSB WPI or PPI numbers into `price_amount`.
- Obtain commercial quotations for cement, rebar, structural sections, sand, and coarse aggregate.
- Record the local term `صلبوخ` when it appears, but map it to a precise aggregate specification before comparison.
- Check that cement and rebar manufacturers or imported products meet the current PAI quality requirements.

---

## 6. Local Terminology Map

Local names are search aids, not guaranteed technical equivalents.

| Country | Fine aggregate | Coarse aggregate search terms | Important warning |
|---|---|---|---|
| Saudi Arabia | `رمل`, soft white sand, red sand | `بحص`, `ركام خشن`, `حصى` | “Mixed sand and pebble” may not meet a specified concrete grading |
| UAE | `رمل مغسول`, washed sand, dune sand, crushed sand | `ركام`, `بحص`, `gabbro`, crushed stone | Always store emirate and quarry/source |
| Egypt | `رمل` | `سن`, `زلط`, `ركام خشن` | `سن` and `زلط` must remain separate products |
| Oman | `رمل`, washed sand, crushed sand | `ركام`, `حصى`, crushed stone, gabbro | Verify quarry and grading |
| Qatar | washed sand | gabbro aggregate, `ركام`, crushed stone | Nominal size and origin affect price |
| Bahrain | washed sand, dune sand | aggregate, gabbro, crushed stone, `ركام`, `بحص` | Use Ministry of Works approval/specification status |
| Kuwait | `رمل`, washed sand | `صلبوخ`, `بحص`, `ركام`, crushed aggregate | `صلبوخ` still needs size, grading, and source fields |

---

## 7. Required Database Design

Use separate tables for price observations, index observations, water tariffs, sources, and approvals/specifications. This prevents unlike evidence from being mixed.

## 7.1 `materials`

| Column | Type | Notes |
|---|---|---|
| `material_id` | UUID/text | Internal stable identifier |
| `material_class` | enum | `cement`, `rebar`, `structural_steel`, `fine_aggregate`, `coarse_aggregate`, `water` |
| `material_name` | text | English normalized name |
| `material_name_ar` | text | Arabic normalized name |
| `local_name` | text | Local English/transliterated or source wording |
| `local_name_ar` | text | Local Arabic wording |
| `subtype` | text | OPC, SRC, washed sand, gabbro, natural gravel, etc. |
| `subtype_ar` | text | Arabic subtype |
| `grade_standard` | text | ASTM, EN, BS, GSO, national standard, or manufacturer grade |
| `diameter_mm` | decimal | Rebar only |
| `section_profile` | text | I, H, channel, angle, hollow section, etc. |
| `section_dimensions` | text | Exact dimensions; do not translate numeric dimensions |
| `aggregate_nominal_size_mm` | decimal/text | Preserve ranges such as 10–20 mm |
| `aggregate_source_type` | text | Gabbro, limestone, natural gravel, recycled, etc. |
| `water_supply_mode` | enum | `network`, `bulk`, `filling_station`, `tanker_delivered`, `other` |

## 7.2 `material_price_observations`

| Column | Type | Notes |
|---|---|---|
| `price_observation_id` | UUID/text | Primary key |
| `material_id` | FK | Links to exact normalized item |
| `country_code` | CHAR(2) | `SA`, `AE`, `EG`, `OM`, `QA`, `BH`, `KW` |
| `admin_area` | text | Emirate, governorate, city, or national |
| `admin_area_ar` | text | Arabic location |
| `price_amount` | decimal | Never put an index value here |
| `currency` | CHAR(3) | ISO 4217 code |
| `unit` | text | `50_kg_bag`, `tonne`, `m3`, etc. |
| `price_level` | enum | `producer`, `wholesale`, `retail`, `market`, `contract`, `quotation` |
| `effective_from` | date | Exact displayed date |
| `effective_to` | date | Exact displayed expiry, if any |
| `reference_month` | YYYY-MM | Statistical reference month |
| `tax_status` | enum | `included`, `excluded`, `unknown`, `not_applicable` |
| `transport_status` | enum | `included`, `excluded`, `unknown` |
| `minimum_quantity` | decimal/text | Preserve original condition |
| `delivery_location` | text | Required for delivered quotations |
| `delivery_location_ar` | text | Arabic location |
| `source_id` | FK | Source register link |
| `source_type` | enum | Use codes in Section 3 |
| `is_current` | boolean | Derived from dates, not manually assumed |
| `verification_status` | enum | `verified`, `partially_verified`, `unverified`, `rejected` |
| `verification_note` | text | English explanation |
| `verification_note_ar` | text | Arabic explanation if maintained bilingually |
| `retrieved_at` | datetime | Store in UTC |

## 7.3 `price_index_observations`

| Column | Type | Notes |
|---|---|---|
| `index_observation_id` | UUID/text | Primary key |
| `country_code` | CHAR(2) | Country |
| `index_family` | enum | `PPI`, `WPI`, `CCI`, other |
| `item_group` | text | English source label |
| `item_group_ar` | text | Arabic source label |
| `index_value` | decimal | Index points only |
| `base_period` | text | Mandatory |
| `reference_period` | text/date | Mandatory |
| `change_mom_pct` | decimal | If officially published |
| `change_yoy_pct` | decimal | If officially published |
| `source_id` | FK | Source register link |
| `retrieved_at` | datetime | UTC |

## 7.4 `water_tariffs`

| Column | Type | Notes |
|---|---|---|
| `water_tariff_id` | UUID/text | Primary key |
| `country_code` | CHAR(2) | Country |
| `admin_area` | text | Emirate/local utility where applicable |
| `admin_area_ar` | text | Arabic area |
| `provider_name` | text | English authority/provider name |
| `provider_name_ar` | text | Arabic name |
| `customer_category` | text | Commercial, industrial, tanker, etc. |
| `customer_category_ar` | text | Arabic category |
| `supply_mode` | enum | Network, bulk, filling station, tanker delivered |
| `consumption_from` | decimal | Slab lower bound |
| `consumption_to` | decimal | Slab upper bound |
| `tariff_amount` | decimal | Base tariff only |
| `currency` | CHAR(3) | Currency |
| `tariff_unit` | text | Preserve original unit |
| `fuel_surcharge` | decimal | Store separately where applicable |
| `vat_rate_pct` | decimal | Store separately |
| `wastewater_charge` | decimal | Store separately |
| `effective_from` | date | Mandatory if published |
| `effective_to` | date | If published |
| `source_id` | FK | Official tariff source |
| `retrieved_at` | datetime | UTC |

## 7.5 `sources`

| Column | Type | Notes |
|---|---|---|
| `source_id` | UUID/text | Primary key |
| `source_title` | text | English title |
| `source_title_ar` | text | Arabic title when available |
| `authority_name` | text | English authority name |
| `authority_name_ar` | text | Arabic authority name |
| `official_domain` | text | Domain only |
| `source_url` | text | Direct page or file URL |
| `source_language` | array/enum | `ar`, `en`, `ar_en` |
| `publication_date` | date | If shown |
| `reference_period` | text | Period described by data |
| `geographic_scope` | text | National/emirate/governorate/city |
| `geographic_scope_ar` | text | Arabic scope |
| `access_type` | enum | `public`, `interactive`, `login_required` |
| `file_hash_sha256` | text | Required for downloaded files |
| `archive_path` | text | Internal archive location |
| `retrieved_at` | datetime | UTC |
| `source_status` | enum | `active`, `superseded`, `expired`, `unreachable` |

## 7.6 `material_approvals_and_specifications`

| Column | Type | Notes |
|---|---|---|
| `approval_record_id` | UUID/text | Primary key |
| `country_code` | CHAR(2) | Country |
| `material_id` | FK | Material/product |
| `manufacturer_name` | text | English/legal source name |
| `manufacturer_name_ar` | text | Arabic legal name |
| `product_name` | text | English product |
| `product_name_ar` | text | Arabic product |
| `approval_type` | enum | Product, manufacturer, lab, specification |
| `approval_number` | text | If shown |
| `valid_from` | date | If shown |
| `valid_to` | date | If shown |
| `standard_reference` | text | Standard or specification number |
| `source_id` | FK | Official source |
| `verification_status` | enum | Current, expired, unclear |

### Bilingual naming rule

Use `_ar` only for human-language text that can have an Arabic version. Do not duplicate numeric, date, boolean, code, currency, unit, URL, hash, or identifier fields with `_ar`.

Examples:

- `material_name` / `material_name_ar`
- `authority_name` / `authority_name_ar`
- `verification_note` / `verification_note_ar`

Do **not** create fields such as `price_amount_ar`, `currency_ar`, `effective_from_ar`, or `source_url_ar`.

---

## 8. Extraction and Normalisation Rules

### 8.1 Cement

Capture at least:

- cement type: OPC, SRC, white, blended, or other;
- strength class or national designation;
- bagged or bulk;
- bag mass;
- manufacturer if the official source identifies it;
- ex-factory, market, or delivered basis; and
- minimum quantity.

Never compare a 50 kg bag price with a bulk-tonne price without retaining the original observation and documenting the conversion.

### 8.2 Reinforcing steel

Capture:

- bar or coil;
- plain or deformed;
- diameter;
- grade/standard;
- domestic or imported status if stated;
- unit; and
- price basis.

Do not average different diameters unless the official publication itself reports an aggregate and the aggregate is stored as a separate series.

### 8.3 Structural steel sections

Capture:

- profile type;
- exact dimensions and mass per metre;
- steel grade;
- standard;
- length;
- black, galvanized, painted, or fabricated condition;
- fabrication scope; and
- delivery basis.

A generic “steel price” is not acceptable for structural sections.

### 8.4 Sand

Capture:

- washed, natural, dune, crushed, red, or white;
- grading/fineness where available;
- source/quarry;
- moisture basis if relevant; and
- delivered or ex-source basis.

### 8.5 Coarse aggregate

Capture:

- natural gravel, crushed stone, gabbro, limestone, or recycled aggregate;
- nominal size/range;
- grading;
- source/quarry and country of origin;
- density basis where the price is by weight; and
- delivered or ex-quarry basis.

### 8.6 Water

Capture:

- potable network, bulk, filling station, or delivered tanker;
- customer category;
- tariff slab;
- original billing unit;
- fixed charges, surcharges, tax, wastewater, and delivery as separate fields;
- proof of water quality or project acceptance; and
- tanker capacity where applicable.

---

## 9. Agent Verification Procedure

For every country and material:

1. Open the official landing page, not only a search result.
2. Confirm that the domain belongs to the stated government authority.
3. Find the latest publication available as of the research date.
4. Record publication date and data reference period separately.
5. Download the official PDF or spreadsheet where possible.
6. Calculate and store a SHA-256 hash.
7. Preserve the original-language item label before translating or normalising it.
8. Classify the evidence using the codes in Section 3.
9. Verify material specification, unit, currency, geographic scope, tax, transport, minimum quantity, and validity dates.
10. Reject any row whose currency or unit cannot be established.
11. Mark a past validity period as historical, even if the page is still live.
12. Keep utility-water tariffs separate from delivered tanker quotations.
13. Keep index observations separate from absolute prices.
14. For quoted prices, save the dated quotation and supplier legal identity; never label the quote as an official price.
15. Re-check all links at the end of the run and report unreachable or superseded sources.

---

## 10. Required Agent Deliverables

The verification agent should return:

1. `source_register.csv` — one row per official source;
2. `material_price_observations.csv` — absolute or quoted prices only;
3. `price_index_observations.csv` — official indices only;
4. `water_tariffs.csv` — official tariffs and delivered-water quotes kept distinguishable;
5. `material_approvals_and_specifications.csv` — approvals and standards;
6. `unresolved_items.md` — missing current prices, inaccessible pages, ambiguous units, or missing currencies;
7. `verification_report.md` — findings, exclusions, and exact reasons for every `quote_required` status; and
8. an archive of downloaded official files with SHA-256 hashes.

The report must explicitly state, for each country and material, one of:

- `current_official_absolute_price_found`;
- `official_historical_price_only`;
- `official_index_only`;
- `official_tariff_only`;
- `official_approval_or_specification_only`;
- `authenticated_or_interactive_source_requires_capture`;
- `commercial_quote_required`; or
- `not_found_after_verification`.

---

## 11. Final Quality Gates

Do not approve the dataset unless all of the following are true:

- Every numeric price has a currency, unit, source, and reference date.
- Every price is clearly labelled official or commercial.
- No index value appears in an absolute-price field.
- No historical price is presented as current.
- UAE observations identify the emirate.
- Egypt observations identify Greater Cairo or the relevant governorate.
- `سن` and `زلط` remain separate unless an official definition proves equivalence.
- Rebar observations preserve diameter and grade.
- Structural-section observations preserve profile and dimensions.
- Aggregate observations preserve size and source/type.
- Water observations distinguish utility tariff, filling-station price, and delivered tanker price.
- Arabic content uses the matching English column name plus `_ar`.
- Downloaded official evidence has a stored hash and retrieval timestamp.

---

## 12. Bottom-Line Research Assessment

- **Saudi Arabia:** strongest verified national item-level statistical source among the seven for cement, rebar, and selected sand/aggregate descriptions.
- **Egypt:** broad official monthly building-material bulletin system, but geography and table notes must be handled carefully.
- **Qatar:** useful official public-works price list, but material coverage and validity are period-specific.
- **UAE:** official emirate-level statistics exist; do not treat them as federal or automatically current.
- **Oman and Kuwait:** official indices are useful for movement analysis, while current absolute project prices generally require quotations.
- **Bahrain:** official approval and specification sources are strong for compliance, but current material prices generally require quotations.
- **Water in every country:** the official tariff is only one component of site cost and must not be confused with a delivered concrete-mixing-water price.
