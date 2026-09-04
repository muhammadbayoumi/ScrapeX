# UAE contractors and engineering consultants — the owner's source survey

**QUEUED THIRD, NOT STARTED. The order is his:**

> «ضيف هذا الملف ليكون المصادر التالية **بعد الانتهاء الكامل من مصدر مقاول ومصدر
> بلدية**»
> — 2026-08-20, [REQ-15](archive/REQUESTS.md#req-15--the-uae-sources-third-in-the-queue)

So: muqawil, then [Balady](BALADY-ENG-OFFICES.md), then this. **The survey below is
his, stored verbatim**, for the same reason as Balady's — a specification that lives
only in a conversation cannot be checked, and he had to re-send the muqawil column
spec once already because he could not tell whether it had survived.

---

## What is structurally different about this one

**It is not a source. It is a portfolio of them**, and that changes the shape of the
work rather than only its size.

> **Its key finding is a negative one, and it is the most important line in the
> file:** no single public federal directory covers every emirate. Registration and
> classification are per-emirate, so **the emirate and the regulatory authority are
> part of every record's identity**, not decoration.

That is why his proposed schema opens with `country`, `emirate`,
`regulatory_authority`, `source_system` — and why a "UAE contractors" table is not
one crawl the way `contractors` was. His own priority order (§8) is the sequencing,
and it is already sorted by suitability rather than by emirate.

## Three things this project has already measured that bear on it

Recorded now, while it is cheap, so the work does not open by rediscovering them.

**1 · Abu Dhabi DMT publishes both languages in ONE record — and that is a
materially cheaper source than muqawil.** His survey notes it as an advantage; it is
worth naming exactly how much of one. On muqawil the Arabic half costs a **second
full crawl** — 871 listing pages and 17,403 profiles again — and the values are
matched **by page-order index, never by label**, because the same field is spelled
`رقم العضويه` with `ه` in one place and a label-matched extractor breaks on it
([LESSONS.md](archive/LESSONS.md)). A record that carries `firm_name` and `firm_name_ar`
together costs **half the requests and removes the index-matching risk entirely.**
If DMT holds up, it is the best-shaped source this project has seen.

**2 · His §11.2 — "check for an official API, open-data download, CSV, Excel, PDF or
JSON source before using browser automation" — should gate everything else.** It is
the cheapest question available and it can delete the crawl. On muqawil the
equivalent question was answered late and the answer was no: `/sitemap.xml` holds
**20 static pages**, the map page carries **zero** contractor markers, and no sort
parameter exists — three dead ends recorded in [DEC-11](archive/BACKLOG.md) so nobody spends
the requests twice. These are government portals; here the answer may be yes.

**3 · His §11.7 — "treat grades, ratings, classification categories and evaluation
results as separate concepts" — is a lesson this repository learned by getting it
wrong.** muqawil publishes `contractor_classification`,
`contractor_classification_grade`, `customer_rating_score` and
`customer_rating_count`, and collapsing any two would have lost information that is
already stored. He is right, and the existing schema is the precedent.

## And two of his rules here are already rulings

Stated so nobody re-litigates them when the work starts:

| his rule | where it already lives |
|---|---|
| base column English, `_ar` for Arabic, no `_ar` duplicate for identifiers, numbers, URLs, coordinates, dates, ratings or booleans | `R-12`, and the shape of every column in [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| separate relationship tables for activities, categories, branches, classifications and evaluations | `R-19` — **«جداول أبناء للخمس كلّها»**, his ruling for muqawil's five multi-valued groups |

**One caution he raised himself and should not be lost**: Ras Al Khaimah lists a
company once per project category, and he says explicitly that repeated appearances
must be modelled as a company-category relationship **rather than treated
automatically as duplicates**. That is the same trap as counting a muqawil
contractor twice because they appear on two listing pages, and it is the reason
`dataset_sighting` (#227) counts sightings separately from records.

---

*Everything below this line is the owner's survey as he sent it, unedited.*

---

# UAE Contractors and Engineering Consultants — Official Data Sources

## Purpose

This document lists official UAE government and municipal sources that publish, search, verify, register, or classify engineering contractors and engineering consultancy firms.

The objective is to identify suitable sources for building a database similar to the Saudi `muqawil.org` contractor directory.

## Key Finding

No single public federal directory was identified that provides a complete list of all contractors and engineering consultants across every UAE emirate.

Registration, licensing, and classification are generally managed at emirate or municipality level. A national database should therefore preserve the emirate and regulatory authority for every record.

Recommended source fields:

```text
country
emirate
regulatory_authority
firm_type
source_system
source_record_id
source_list_url
source_detail_url
collected_at
last_verified_at
```

## 1. Abu Dhabi

### Engineering Firms with Valid Classification

- Authority: Abu Dhabi Department of Municipalities and Transport — DMT
- Official directory: https://pages.dmt.gov.ae/en/Engineering-Firms
- Arabic directory: https://pages.dmt.gov.ae/ar/Engineering-Firms
- Coverage: Engineering contracting companies and engineering consultancy offices with valid classifications
- Access type: Public searchable directory
- Database suitability: Excellent

Observed fields:

```text
sequence_number
economic_license_number
firm_name
firm_name_ar
firm_type
classification_category
classification_expiry_date
classification_status
evaluation_result
```

Important advantages:

- Official English and Arabic firm names appear in the same record.
- Contractors and consultants are included in one structured directory.
- Firm type distinguishes an `Engineering Contracting Company` from an `Engineering Consultancy Office`.
- Classification category and expiry date are displayed.
- The directory is the strongest initial source for a bilingual database.

### Classification Certificate Inquiry

- Official inquiry: https://pages.dmt.gov.ae/en/Engineering-Firms-Inquiry
- Purpose: Verify the details of an engineering classification certificate
- Access type: Search/inquiry
- Database suitability: Useful for record verification

### Engineering Excellence List

- Official list: https://pages.dmt.gov.ae/en/Excellence-Listing
- Coverage: Selected evaluated engineering contractors and consultants
- Filters may include:
  - Firm type
  - Firm form
  - Classification category
  - Activity domain
  - Activity
  - Evaluation result
- Database suitability: Useful as an enrichment and quality/evaluation source, but not a substitute for the full valid-classification directory

### Classification System Information

- DMT classification information: https://www.dmt.gov.ae/en/adm/Media-Centre/News/01Mar2024
- Current framework update: https://www.dmt.gov.ae/en/Media-Centre/News/DMT-ADGM-Launch-Unified-Engineering-Classification-System-for-Abu-Dhabi

The Abu Dhabi system covers engineering contracting companies, engineering consultancy offices, and licensed engineering professionals. Verify whether ADGM-licensed firms are fully represented in the public directory following the system integration.

## 2. Dubai

### Consultants, Contractors and Suppliers Data

- Authority: Dubai Municipality
- English information page: https://www.dm.gov.ae/municipality-business/consultants-contractors-and-suppliers-data/
- Arabic information page: https://www.dm.gov.ae/التشريعات-والمعلومات/بيانات-الاستشاريين،-المقاولين-والمو/?lang=ar
- Coverage:
  - Registered engineering consultancy offices
  - Registered contracting companies
  - Approved building-material suppliers and manufacturers
- Access type: Official information page linking to the register and Dubai BPS application
- Database suitability: Very good, subject to confirming the available public fields and collection method

Dubai Municipality identifies two relevant datasets:

```text
Database of Registered Engineering Consultancy Offices
Database of Registered Contracting Companies
```

### Dubai Engineering Qualification Portal

- Official portal: https://deqsmart.dm.gov.ae/EisPortal/faces/security/others/Corporate-practice-permit.xhtml
- Purpose: Search or verify professional practice permits for engineering firms registered with Dubai Municipality
- Access type: Interactive web portal
- Database suitability: Requires technical inspection of search behavior, pagination, available fields, and public-access restrictions

### Dubai Building Permits — Dubai BPS

- Dubai Municipality announcement: https://www.dm.gov.ae/new-improved-building-permits-app-launched-for-streamlined-services/
- Purpose: Building-permit services and search for contractors and consultants registered in Dubai
- Reported search/enrichment information may include:
  - Registration status
  - Type of firm
  - Number of active projects
  - Consultant or contractor evaluation
- Access type: Mobile application and connected municipal services
- Database suitability: Potentially valuable for enrichment; verify current public availability and terms before collection

### Licensing Standards

- Official standards page: https://www.dm.gov.ae/municipality-business/consultants-and-contractors-licensing-standards/
- Purpose: Understand classifications, permitted activities, qualification requirements, and professional-practice rules
- Database suitability: Reference data for normalizing activity and classification fields

## 3. Ras Al Khaimah

### Approved Engineering Consultants

- Authority: Ras Al Khaimah Municipality
- Official list: https://sanad.mun.rak.ae/docs/en/approved-consultants
- Coverage: Approved and classified engineering consultancy firms
- Access type: Public list
- Database suitability: Excellent for a public contact and classification dataset

Observed fields:

```text
consultant_name
grade
establishment_date
phone_number
email_address
rating
project_or_building_category
```

The page is available through an English documentation interface, but many establishment names are displayed in Arabic. Do not assume that an official English legal name exists for every listed consultant.

### Approved Contractors

- Authority: Ras Al Khaimah Municipality
- Official list: https://sanad.mun.rak.ae/rakm/docs/en/approved-contractors
- Coverage: Approved and classified construction contractors
- Access type: Public list
- Database suitability: Excellent for a public contact and classification dataset

Observed fields:

```text
contractor_name
grade
phone_number
email_address
rating
project_or_building_category
```

Important data-quality considerations:

- Phone-number formats are inconsistent.
- Some email addresses may contain source-data errors or placeholders.
- A company may appear under more than one project or building category.
- Ratings and grades should be stored separately.
- Repeated appearances should be modelled through a company-category relationship rather than treated automatically as duplicate companies.

### General Approved Professionals Page

- Official overview: https://sanad.mun.rak.ae/docs/en/approved-contractors-consultants-1
- Purpose: Entry point for the municipality's approved contractor and consultant registers

## 4. Sharjah

### Contractor and Engineer Inquiry

- Authority: Sharjah City Municipality
- Official inquiry: https://portal.shjmun.gov.ae/en/eservices/Pages/QryPrjEngContractor.aspx
- Coverage: Contractor and project-engineer verification
- Search inputs observed:
  - Engineer card number
  - Contractor licence number
- Access type: Record-specific inquiry rather than a complete browsable directory
- Database suitability: Limited; useful for verification when identifiers are already known

### Contractor and Consultant Classification Services

- Service directory example: https://shjmun.gov.ae/servicedirectory/details/683d3a96ff3e1753c064e6de
- Coverage: Classification-certificate services for contractors and consultants
- Database suitability: Regulatory reference only unless a separate public list is identified

### Star Rating Registration

- Official service page: https://shjmun.gov.ae/servicedirectory/details/683d3a96ff3e1753c064e6d9
- Purpose: Allows contractors and consultants to register in a star-rating program so their data can be shown to individual customers
- Database suitability: Potential lead for an additional public directory or application; independently verify where the published rated-company list is displayed

## 5. Ajman

### Contractors and Consultants Classification

- Authority: Ajman Municipality and Planning Department
- Electronic services portal: https://online.am.gov.ae
- 2024 English service guide: https://www.am.gov.ae/wp-content/uploads/2024/09/EN-دليل-الخدمات-2024.pdf
- Coverage: Professional-practice accreditation and classification of contractors and engineering consultants
- Access type: Registration and classification service
- Database suitability: Regulatory reference; no comprehensive public list was confirmed during the initial review

Relevant classified-service types include:

- Professional practice accreditation for contractors and consultants
- Raising the classification/ranking of a contractor or consultant
- Temporary contractor or consultant permits

Further verification is required to determine whether the online portal exposes a public search or approved-company list without authentication.

## 6. Fujairah

### Contractor and Consultant Classification Certificate

- Authority: Fujairah Municipality
- Official service: https://portal.fujmun.gov.ae/OnlineEservices/en/eService/ServicePages/service_information.aspx?serviceid=172
- Coverage: Classification certificates for contractors and consultants
- Access type: Application/service page
- Database suitability: Regulatory reference; no comprehensive public list was confirmed during the initial review

### Contractor Registration

- Official service: https://portal.fujmun.gov.ae/OnlineEservices/en/eservice/ServicePages/service_information.aspx?serviceid=174
- Coverage: Registration of local building and construction contractors
- Access type: Application/service page
- Database suitability: Regulatory reference only unless an approved-company inquiry or list is identified

## 7. Umm Al Quwain

No complete official public contractor-and-consultant directory was confirmed during the initial review.

Further investigation should cover:

- Umm Al Quwain Municipality public services
- Contractor and consultant classification services
- Building-permit portals
- Open-data catalogues
- Downloadable approved-company lists

## 8. Recommended Source Priority

For building the first version of the database, use this order:

1. Abu Dhabi DMT Engineering Firms with Valid Classification
2. Dubai Municipality Consultants, Contractors and Suppliers Data
3. Ras Al Khaimah Approved Consultants
4. Ras Al Khaimah Approved Contractors
5. Sharjah verification and star-rating systems
6. Ajman and Fujairah classification systems
7. Umm Al Quwain municipal sources

## 9. Recommended Core Database Fields

```text
firm_id
source_record_id
economic_license_number
professional_license_number

firm_name
firm_name_ar
firm_type
firm_type_ar

country
country_ar
emirate
emirate_ar
city
city_ar

classification_category
classification_category_ar
classification_status
classification_status_ar
classification_expiry_date

rating_value
evaluation_result

phone_number
mobile_number
email_address
website_url
address
address_ar

regulatory_authority
regulatory_authority_ar
source_system
source_list_url
source_detail_url
collected_at
last_verified_at
```

Use separate relationship tables for activities, project/building categories, branches, classifications, and evaluations when one firm can have multiple values.

## 10. Language Rule

Use lowercase English `snake_case` column names.

- Base field: English content, for example `firm_name`.
- Arabic field: Same name with `_ar`, for example `firm_name_ar`.
- Keep the English field `NULL` if no official or verified English value exists.
- Do not automatically translate or transliterate a legal company name and present it as official.
- Store language-independent values only once. Phone numbers, licence numbers, email addresses, URLs, coordinates, prices, dates, ratings, and Boolean values do not need an `_ar` duplicate.

## 11. Verification and Compliance Requirements

Before automated data collection:

1. Confirm the current fields, pagination, filters, and record counts for each live source.
2. Check for an official API, open-data download, CSV, Excel, PDF, or JSON source before using browser automation.
3. Review the site's terms of use, robots policy, rate limits, and republication restrictions.
4. Do not bypass authentication, CAPTCHA, access controls, or technical restrictions.
5. Preserve the exact source value separately from cleaned or normalized values.
6. Record the source URL and collection timestamp for every record.
7. Treat grades, ratings, classification categories, and evaluation results as separate concepts.
8. Test for duplicates across emirates using licence numbers and verified identifiers, not company names alone.
9. Re-verify time-sensitive fields such as classification status and expiry dates periodically.

## 12. Source Status Summary

| Emirate | Contractors | Consultants | Public complete list confirmed | Arabic/English names | Initial suitability |
|---|---:|---:|---:|---:|---|
| Abu Dhabi | Yes | Yes | Yes | Both in the main directory | Excellent |
| Dubai | Yes | Yes | Official registers confirmed; access requires further technical review | Interface available in both languages; record-level bilingual availability must be verified | Very good |
| Ras Al Khaimah | Yes | Yes | Yes, separate lists | Names are frequently Arabic even on the English interface | Excellent |
| Sharjah | Verification available | Classification services available | No complete list confirmed | Requires verification | Limited |
| Ajman | Classification service | Classification service | No complete list confirmed | Requires verification | Regulatory reference |
| Fujairah | Registration/classification service | Classification service | No complete list confirmed | Requires verification | Regulatory reference |
| Umm Al Quwain | Not confirmed | Not confirmed | No | Not confirmed | Further research required |

## 13. Verification Date

Initial source review: 20 August 2026.

All lists, classifications, ratings, and expiry dates are time-sensitive and must be rechecked against the current official source before publication or operational use.
