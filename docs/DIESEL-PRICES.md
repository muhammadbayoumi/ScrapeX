# Official retail diesel prices, seven countries — the owner's source list

**QUEUED, NOT STARTED.**

> «مصادر اخرى لاسعار الديزل فقط مصادر منتجات ضيفها لقائمة المصادر»
> — 2026-08-20, [REQ-17](archive/REQUESTS.md#req-17--official-diesel-prices-a-product-source-not-a-firm-directory)

**The list below is his, stored verbatim.**

---

## This one is not like the other four, and the difference is structural

He named it himself — **«مصادر منتجات»**, product sources. The other four queued
surveys are **firm directories**: they describe companies, and they land in
`generic_record` through the generic-dataset seam that muqawil pioneered. This one
describes **a product's price over time**, and that is the *original* spine of this
project: `price_observation`, the `db/migrations/` PRICE chain, `SR-6`.

> **So it is the first queued source that touches the half of the warehouse muqawil
> never went near.** That is good news for scheduling and it is a warning about one
> specific mechanism, below.

## It is also, by a wide margin, the smallest thing in the queue

| source | requests to collect once |
|---|---|
| muqawil, everything the site publishes | **36,548** |
| the UAE, Egypt/Gulf surveys | 32+ sources, unmeasured |
| **this** | **7 pages, ~14 with both locales** |

**Roughly fourteen requests a month.** It does not compete with finishing muqawil in
any meaningful sense — it is an afternoon, not a track. The order is his to set; this
is recorded so the decision is made with the size in view rather than by position in
a list.

## The one mechanism that will silently drop his data, and it is measured

His collection rule §3 is *"keep `effective_from` and `effective_to`; **never
overwrite a previous price** when a new month or quarter begins."* That is exactly
what `price_observation` is for. But `SR-6` says:

> **an unchanged price is confirmed, not appended.**

Those two rules disagree, and the disagreement is not theoretical. Oman published
`0.258 OMR/litre` in August. If July was also `0.258`, the append gate sees no change
and **writes nothing** — so the August *period* never exists, `effective_from` is
never recorded for it, and his §3 is silently violated by a rule that is otherwise
correct.

> **A period-keyed price must key the append gate on the PERIOD, not only on the
> value.** `SR-6` was written for a scraped shelf price where an unchanged number
> carries no new information. A published official price for a *named month* carries
> new information even when the number is identical: it says the ministry set it
> again.

This is the same shape as a defect already recorded here — a new
`price_observation` column stays NULL because the append gate never learned to notice
it. The gate decides what history exists, and it has to be told what "new" means for
each kind of price. **Settle this before the first collection, not after a month is
missing.**

## Two more things in his list that need something we do not have

**Bahrain publishes the price as an IMAGE.** His own note says an automated collector
must preserve a screenshot or image hash and use OCR **only as a candidate
extraction**, with manual verification against the dated committee announcement
before publication. This project has **no OCR path at all**, and his instruction is
the right one anyway: the image is the evidence, the number is a claim about it. So
Bahrain is one source that cannot be fully automated on his own terms, and that is a
property of the source rather than a gap in the plan.

**Kuwait's page is stale in a way that would poison the dates.** He observed the
correct diesel value beside an **out-of-date validity note**, and says explicitly not
to derive the effective dates from the static product page. A collector that trusted
the page would store a right price under wrong dates — the worst of the two failures,
because it looks complete.

## What is already settled and should not be re-decided

| his rule | where it already lives |
|---|---|
| no USD conversion in the stored value; any conversion in a separate table with its rate source and date | `SR-1` — the source of truth is what the publisher published |
| `_ar` only where the content is language-bearing; not for prices, currency codes, or dates | `R-12` |
| store the official value and unit unchanged | the same rule his Gulf survey states as `source_registration_number_raw` |

And his §4 — automotive retail diesel kept separate from marine, industrial bulk,
subsidised fisheries and commercial-delivery prices — is a **product identity** rule.
It is why his schema carries `fuel_type`, `fuel_grade` and `customer_category` in the
record key, and it is the same reason Bahrain's general pump price and its supported
fishermen category are two rows and not one.

---

*Everything below this line is the owner's list as he sent it, unedited.*

---

# Official Retail Diesel Prices — Seven Countries

## Scope

This list covers automotive retail diesel, also called `diesel`, `gas oil`, or `solar`, in Saudi Arabia, the United Arab Emirates, Egypt, Oman, Qatar, Bahrain, and Kuwait.

Review date: **20 August 2026**.

Prices are stated per litre in local currency. They are not converted to USD because exchange-rate conversion would make the stored value time-dependent and would no longer represent the official domestic pump price.

## Current Price List

| Country | ISO code | Official product name | Price per litre | Minor-unit equivalent | Effective period or observation date | Official publisher/source |
|---|---|---|---:|---:|---|---|
| Saudi Arabia | `SA` | Diesel | **SAR 1.79** | 179 halalas | August 2026 | Saudi Aramco retail-fuels page |
| United Arab Emirates | `AE` | Diesel | **AED 3.80** | 380 fils | Current August 2026 price retrieved 20 August 2026 | ADNOC Distribution; price includes VAT |
| Egypt | `EG` | Solar / Diesel | **EGP 20.50** | 2,050 piastres | Effective from 10 March 2026 | Ministry of Petroleum and Mineral Resources |
| Oman | `OM` | Diesel | **OMR 0.258** | 258 baisa | August 2026 | Oman Oil Marketing Company retail-fuel page |
| Qatar | `QA` | Diesel | **QAR 2.05** | 205 dirhams | 1–31 August 2026 | QatarEnergy announcement reported by Qatar News Agency |
| Bahrain | `BH` | Diesel | **BHD 0.229** | 229 fils | Effective from 2 August 2026 | Fuel Price Determination and Monitoring Committee; official Ministry of Oil and Environment price page |
| Kuwait | `KW` | Gas Oil / Diesel | **KWD 0.115** | 115 fils | 1 July–30 September 2026 | KNPC / state Subsidy Review Committee pricing |

## Official Source Details

### Saudi Arabia

- Official Arabic source: https://www.aramco.com/ar/what-we-do/energy-products/retail-fuels
- Official English source: https://www.aramco.com/en/what-we-do/energy-products/retail-fuels
- Published value: `1.79 SAR/litre`
- Published period: August 2026

### United Arab Emirates

- Official ADNOC Distribution retail-fuel page: https://www.adnocdistribution.ae/consumer-fuel
- Published value retrieved on the review date: `3.80 AED/litre`
- Tax note: The page states that the displayed price includes VAT.
- Update frequency: Monthly. Store the applicable month and retrieve the page again after each monthly announcement.

### Egypt

- Official Ministry decision: https://www.petroleum.gov.eg/ar-eg/media-center/news/news-pages/Pages/mop_10032026_02.aspx
- Official Ministry price display: https://www.petroleum.gov.eg/ar-eg/Pages/HomePage.aspx
- Published value: `20.50 EGP/litre`
- Effective from: 10 March 2026 at 03:00

### Oman

- Arabic retail-price source: https://oomco.om/ar/motorists/%D8%A7%D9%84%D9%88%D9%82%D9%88%D8%AF
- English retail-price source: https://oomco.om/for-drivers/fuel
- Ministry of Energy and Minerals FAQ directing users to the National Subsidy System for monthly prices: https://mem.gov.om/en-us/FAQ/PgrID/710/PageID/3
- Published value: `258 baisa/litre`, equal to `0.258 OMR/litre`
- Published period: August 2026

### Qatar

- Official Qatar News Agency announcement: https://qna.org.qa/en/news/news-details?date=31%2F07%2F2026&id=qatarenergy-sets-fuel-prices-for-august
- QatarEnergy official fuel-price history PDF: https://www.qatarenergy.qa/en/Documents/Fuel%20Prices.pdf
- Published value: `2.05 QAR/litre`
- Published period: August 2026

The QatarEnergy history PDF can lag the latest monthly announcement. Use the dated QatarEnergy announcement or the official QNA report for the new month, then use the PDF for historical backfilling after it is updated.

### Bahrain

- Official Ministry of Oil and Environment price page, Arabic: https://www.moo.gov.bh/moo/ar/GasolinePrices.aspx
- Official Ministry of Oil and Environment price page, English: https://moo.gov.bh/moo/GasolinePrices.aspx
- Published committee value for August 2026: `0.229 BHD/litre`
- Effective from: 2 August 2026

The Ministry page publishes the price table as an image, so an automated collector must preserve a screenshot or image hash and use OCR only as a candidate extraction. The number must be manually verified against the committee's dated announcement before publication.

### Kuwait

- Official KNPC products and fuel-prices page, Arabic: https://www.knpc.com/ar/our-business/local-marketing/products-services
- Official KNPC products and fuel-prices page, English: https://www.knpc.com/en/our-business/local-marketing/products-services
- Published value: `115 fils/litre`, equal to `0.115 KWD/litre`
- Current confirmed period: 1 July–30 September 2026

The KNPC product page displayed the correct diesel value during review but retained an old validity-period note. The collector must therefore save the dated quarterly KNPC or Subsidy Review Committee announcement as the period-specific evidence and must not derive the effective dates from the static product page alone.

## Recommended Database Columns

Use one record per country, product, price period, and customer category.

```text
fuel_price_id
country_code
country_name
country_name_ar

fuel_type
fuel_type_ar
fuel_grade
fuel_grade_ar
customer_category
customer_category_ar

price_per_liter
currency_code
minor_unit_name
minor_unit_name_ar
price_includes_tax

effective_from
effective_to
announced_at
retrieved_at

publisher_name
publisher_name_ar
source_url
source_language
source_evidence_type
verification_status
notes
notes_ar
```

## Collection Rules

1. Store the decimal price in the major local currency, for example `0.258` OMR rather than only `258` baisa.
2. Use ISO 4217 currency codes: `SAR`, `AED`, `EGP`, `OMR`, `QAR`, `BHD`, and `KWD`.
3. Keep `effective_from` and `effective_to`; never overwrite a previous price when a new month or quarter begins.
4. Store automotive retail diesel separately from marine diesel, industrial bulk diesel, subsidized fisheries diesel, and any commercial-delivery price.
5. Treat a price shown on a live page without a visible month as a snapshot. Save `retrieved_at` and obtain a dated announcement where possible.
6. Preserve the official source value and unit. Any USD conversion must be stored in a separate calculated table with the exchange-rate source and date.
7. For Bahrain, keep the general pump price separate from the supported fishermen category.
8. Recheck monthly sources on the first or second day of every month and Kuwait's quarterly source before each new quarter.

## Verification Status

| Country | Price verified from an official current page or dated official announcement | Follow-up needed |
|---|---:|---|
| Saudi Arabia | Yes | Recheck monthly page |
| United Arab Emirates | Yes | Archive the monthly committee announcement in addition to the live distributor page |
| Egypt | Yes | Monitor new Ministry pricing decisions |
| Oman | Yes | Archive the National Subsidy System monthly evidence if accessible |
| Qatar | Yes | Recheck QatarEnergy/QNA monthly announcement |
| Bahrain | Official price page confirmed; record value requires dated image/announcement evidence | Archive the Ministry image and committee announcement |
| Kuwait | Official KNPC price confirmed; static page validity note is stale | Archive the Q3 2026 KNPC/committee announcement and recheck Q4 |
