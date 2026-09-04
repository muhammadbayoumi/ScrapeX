# Egypt, Oman, Qatar, Bahrain and Kuwait — the owner's source survey

**QUEUED FOURTH, NOT STARTED.**

> «المزيد من المصادر ضفها الى القائمة»
> — 2026-08-20, [REQ-16](archive/REQUESTS.md#req-16--egypt-oman-qatar-bahrain-and-kuwait-fourth-in-the-queue)

He said *add them to the list*, without naming a position, so it is **appended in
the order received** — after muqawil, [Balady](BALADY-ENG-OFFICES.md) and the
[UAE](UAE-SOURCES.md). Nothing has started on any of the three queued surveys, so
the order costs nothing to change; it is written down so there is one and not so it
is fixed. [STATE.md](archive/STATE.md) Track 5 carries the queue.

**The survey below is his, stored verbatim**, for the same reason as the other two.

---

## The scale this adds, stated plainly

This is the largest of the three by a wide margin: **five countries, 32 numbered
sources, 933 lines.** Together the queue now reaches **eight countries** — Saudi
Arabia twice over, the seven emirates, and these five.

> **And its most useful content is where it says *no*.** Of the five countries, only
> three have anything resembling a national public directory. Egypt and Kuwait do
> not, and the survey says so in its own executive summary rather than leaving it to
> be discovered.

| country | its own verdict |
|---|---|
| **Oman** | ESNAD / Tender Board `Registered Companies` — *"the closest source found to the Saudi `muqawil.org` use case"* |
| **Qatar** | Monaqasat classified-company profiles — a national-style public procurement directory |
| **Bahrain** | Three separate official lists (Ministry of Works prequalified contractors, Benayat licensed engineering offices, Sijilat for registration) rather than one |
| **Egypt** | **No complete combined directory confirmed.** EFCBC is authenticated; DRSO's consulting-office list is the best public discovery source and is Arabic-only |
| **Kuwait** | **No complete current public list confirmed.** Registration and classification authorities exist; the public surface does not |

**So this file's real instruction is "build federated datasets rather than claiming a
single complete national directory"** — his §45 — and that is a schema requirement,
not a crawl detail. It is why his `firms` table carries `source_system` and
`regulatory_authority`, and why classifications, accreditations and contacts are
separate child tables.

## What this project has already learned that bears on it

**1 · Two of these sources are bilingual at record level, and that is worth more
than it sounds.** Oman's ESNAD and Qatar's Monaqasat each publish Arabic and English
views joined by a stable identifier — PTLC/CR for Oman, the profile file number for
Qatar. On muqawil the Arabic half costs a **second full crawl** (871 listing pages
and 17,403 profiles again) and is matched **by page-order index, never by label**,
because one field is spelled `رقم العضويه` with `ه`
([LESSONS.md](archive/LESSONS.md)). **A stable identifier joining two language views is
strictly better than both** — half the requests of muqawil, and no index-matching
risk at all. His §38.4 and §38.5 already require exactly that join.

**2 · His §39.5 — check for an official API, CSV, Excel, JSON or open-data download
before using browser automation — should gate every one of the 32 sources.** It is
the cheapest question available and it can delete a crawl outright. muqawil's
equivalent was answered late and the answer was no: the sitemap holds **20 static
pages**, the map page carries **zero** contractor markers, and no sort parameter
exists — three dead ends recorded in [DEC-11](archive/BACKLOG.md) precisely so nobody spends
those requests again.

**3 · His §38.8 — "do not merge firms merely because their Arabic or English names
look similar" — is a trap this project has already been bitten by.** The owner named
contractor **10001274** and the warehouse said it did not exist; the answer turned
out to be that a directory can show the same entity in ways a name-based identity
cannot reconcile. `dataset_sighting` (#227) exists because of it, and it counts
sightings separately from records for the same reason his §38.9 wants branches
modelled separately.

**4 · One of his rules here is stricter than ours and should be adopted.** §38.2 asks
for `source_registration_number_raw` — the identifier **exactly as published**, kept
beside any cleaned form. muqawil stores `card_membership_number` as published and
that has held, but the rule is not written down anywhere as a rule. It should be,
before eight countries' worth of identifiers arrive with slashes and leading zeros
in them.

## And his conventions here are already rulings

| his rule | where it already lives |
|---|---|
| base column English, `_ar` for Arabic, never translate a legal name into an official field | `R-12`, and every column in [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) |
| multi-value child tables for classifications, accreditations and contacts | `R-19` — **«جداول أبناء للخمس كلّها»** |
| record nulls honestly; do not manufacture an English value when only Arabic is supplied | `SR-1`, and `LESSONS.md` on what a missing value means |

---

*Everything below this line is the owner's survey as he sent it, unedited.*

---

# Egypt, Oman, Qatar, Bahrain, and Kuwait Contractors and Engineering Consultants — Official Data Sources

## Purpose

This document identifies official or government-operated sources that can be used to build a database of contractors and engineering consultancy firms in Egypt, the Sultanate of Oman, Qatar, Bahrain, and Kuwait.

It is written as a research and verification brief for another agent. The agent must recheck every live source, field, record count, access method, and reuse restriction before implementing automated collection.

Review date: **20 August 2026**.

## Executive Summary

| Country | Best primary source | Contractors | Consultants | Public national-style directory | Record-level Arabic and English |
|---|---|---:|---:|---:|---:|
| Egypt | No single source; use the EFCBC for contractor authority and DRSO plus specialized official registers for consultants | Official registration authority exists, but a complete public browsable member directory was not confirmed | Several public lists exist, but coverage is fragmented | No complete combined directory confirmed | Generally Arabic only; official English record values must be verified source by source |
| Oman | ESNAD / Tender Board `Registered Companies` | Yes | Yes | Yes, for companies registered with the government tender system | Strong: separate Arabic and English views use the same registration identifier |
| Qatar | Ministry of Finance `Monaqasat` Classified Companies Profiles | Yes, within the government procurement classification system | Yes, through engineering-consultancy activity codes; professional licensing must be verified separately | Yes, for classified procurement companies | Strong separate Arabic and English views; the stable record join must be verified |
| Bahrain | Ministry of Works prequalified contractors, Benayat licensed engineering offices, and Sijilat commercial-register verification | Yes, for Ministry of Works prequalified contractors | Yes, through the public licensed-engineering-offices list | Separate public directories rather than one combined list | Directory records are commonly English; official Arabic and English legal names can be sought in Sijilat |
| Kuwait | CAPT/Kuwait Government Online, Kuwait Municipality, and Ministry of Public Works | Registration and classification authorities exist; a complete current public list was not confirmed | Registration and qualification workflows exist; a complete public office directory was not confirmed | No complete combined directory confirmed | Arabic is dominant; CAPT collects both names in some workflows, but public record-level pairing remains unconfirmed |

The Oman ESNAD register is the closest source found to the Saudi `muqawil.org` use case. It is broader than construction because it also includes suppliers, services, IT, vehicle contractors, and other business types. A construction database must filter the registered category, subcategory, and activity instead of importing every record as a contractor or engineering consultant.

Qatar's Monaqasat portal is also a strong national-style public procurement directory, but it is broader than construction and must be filtered by activity and classification. Bahrain provides unusually useful separate official lists for Ministry of Works contractors and licensed engineering offices, with Sijilat supporting commercial-registration verification.

Egypt and Kuwait do not currently expose equally complete combined public directories. Their authoritative data is distributed across registration, qualification, professional-licensing, and sector-specific sources.

---

# Part I — Egypt

## 1. Egyptian Federation for Construction and Building Contractors

- Authority: Egyptian Federation for Construction and Building Contractors, commonly abbreviated EFCBC
- Official portal: https://egypt-efcbc.org/
- Related government explanation of the legal/registration framework: https://www.investinegypt.gov.eg/PublishingImages/Lists/ContentPageDetails/AllItems/Construction%2C%20Building%20and%20Contracting%20Activities.pdf
- Coverage: Contractor registration and classification
- Public access observed: The current portal is principally an authenticated/member portal
- Database suitability: **Authoritative for verification, but poor for public bulk discovery unless a public directory, export, or authorized data-access route is confirmed**

### Finding

No complete, structured, publicly browsable list of all EFCBC members was confirmed during this review. The previous `tasheed.org` site was not reliably accessible during earlier checks and must not be treated as a current source without fresh verification.

### Candidate fields to verify from an official membership record or certificate

```text
membership_number
commercial_registration_number
firm_name_ar
contractor_classification
contractor_classification_ar
contractor_grade
specialization
specialization_ar
registration_status
registration_status_ar
registration_issue_date
registration_expiry_date
```

Do not populate these fields from assumptions or secondary directories. Confirm the exact field labels and definitions from an official EFCBC record, certificate, API, export, or authorized response.

## 2. Ministry of Housing — Construction Research and Studies Fund/Agency

- Official consulting-offices directory: https://drso.gov.eg/offices
- Authority: Construction Research and Studies Fund/Agency under the Ministry of Housing, Utilities and Urban Communities
- Coverage: Consulting offices shown by the Ministry of Housing source
- Access type: Public searchable/list page
- Database suitability: **Best initial public discovery source found for general engineering consulting offices in Egypt**

### Fields observed

```text
firm_name_ar
responsible_engineer_name_ar
affiliation_ar
address_ar
source_detail_url
```

The page displayed office names, responsible engineers or persons, an affiliation such as the Engineers Syndicate, and addresses. The search control observed was based on address and list selection.

### Limitations

- The page is Arabic.
- An official English legal name was not observed for each record.
- The public page does not clearly state that it is the complete current register of every licensed consultancy office in Egypt.
- The agent must confirm pagination, total records, detail-page fields, update date, and inclusion criteria.

## 3. Egyptian Engineers Syndicate

- Official website: https://eea.org.eg/
- Consulting-engineers directory announcement: https://eea.org.eg/NewsDetails.aspx?ID=18629
- Older announcement with more context: https://new.eea.org.eg/Content/%D9%8A%D8%AA%D9%88%D9%81%D8%B1-%D8%A7%D9%84%D8%A2%D9%86-%D8%A8%D9%85%D9%82%D8%B1-%D8%A7%D9%84%D9%86%D9%82%D8%A7%D8%A8%D8%A9-%D8%A7%D9%84%D8%B9%D8%A7%D9%85%D8%A9-%D9%84%D9%84%D9%85%D9%87%D9%86%D8%AF%D8%B3%D9%8A%D9%86?CID=6741&CtID=3&Dir=2&PN=0&PS=0&TId=1027
- Coverage: Professional rules and licensing context for engineers, consulting engineers, consulting offices, multidisciplinary offices, and houses of expertise
- Database suitability: **Regulatory and verification source; no current complete structured public office register was confirmed**

The Syndicate has announced a directory of consulting engineers, but the available announcement is not itself a structured, current public database of engineering firms. Distinguish individual consulting engineers from licensed consulting offices and houses of expertise.

## 4. Egyptian Environmental Affairs Agency — Accredited Practitioners

- Official search: https://www.eeaa.gov.eg/Accreditations/index
- Authority: Egyptian Environmental Affairs Agency
- Coverage: Accredited environmental consultancy offices, consultants, and specialists
- Access type: Public search and detail pages
- Database suitability: **Very good for environmental consulting only**

### Search fields observed

```text
accreditation_type
registration_year
field
search_keywords
```

The search guidance states that keywords may search the name, the responsible manager for consulting offices, or the specialization for consultants and specialists. Clicking a name opens additional information.

### Language status

The reviewed interface and record-search guidance were Arabic. An English language selector exists, but official record-level English values were not confirmed. Store the source values in `_ar` fields and leave the base English fields `NULL` until verified.

### Scope limitation

This is a specialized environmental accreditation register, not a list of every engineering consultancy in Egypt.

## 5. Industrial Development Authority — Accreditation Offices

- Official list: https://www.ida.gov.eg/ar/accreditation-offices
- Authority: Industrial Development Authority
- Coverage: Engineering consulting offices and houses of expertise accredited to review technical matters and industrial licensing documents
- Access type: Public structured list
- Database suitability: **Excellent for the industrial-licensing consultancy subset**

### Fields observed

```text
firm_name_ar
address_ar
contact_person_name_ar
phone_number
email_address
```

The page stated that **9 accreditation offices** were listed at the time of review. Treat this count as time-sensitive and recheck it before use.

### Scope limitation

These are offices accredited for the Industrial Development Authority workflow. The list is not a national register of all engineering consultants.

## 6. Egyptian Survey Authority — Approved Companies and Engineering Offices

- Official list: https://www.esa.gov.eg/certified_comp.aspx
- Authority: Egyptian Survey Authority
- Coverage: Companies and engineering offices approved to provide surveying services
- Access type: Public list with detail links
- Database suitability: **Good for surveying firms and offices**

### Fields observed or to be verified on details

```text
firm_name_ar
firm_type_ar
surveying_accreditation_status
surveying_accreditation_status_ar
source_detail_url
```

The list includes both companies and engineering offices. It is specialized and should be modelled as an accreditation attached to a firm, not as proof that the firm represents every type of consultant or contractor.

## 7. Government Procurement Portal and General Authority for Government Services

- Government procurement portal: https://www.etenders.gov.eg/
- General Authority for Government Services procurement role: https://www.gags.gov.eg/Home/Purchasesindex
- Coverage: Registration of suppliers, contractors, consulting offices, and houses of expertise for government procurement
- Database suitability: **Potential verification and procurement-participation source; no complete public directory was confirmed**

The General Authority page states that it reviews registration applications from suppliers, contractors, consulting offices, and houses of expertise for the government contracting portal. The portal should not be assumed to be a complete public business directory unless an accessible register or authorized data export is identified.

## 8. Egypt Source Priority

1. Use EFCBC data or certificates as the authoritative contractor classification source when access is lawful and verifiable.
2. Use the Ministry of Housing DRSO consulting-offices page for initial general consultant discovery.
3. Add Industrial Development Authority accreditation as a specialized industrial credential.
4. Add Egyptian Environmental Affairs Agency accreditation as a specialized environmental credential.
5. Add Egyptian Survey Authority approval as a specialized surveying credential.
6. Use the Engineers Syndicate and government procurement systems to verify professional or procurement status, not as complete directories unless further public data is confirmed.

## 9. Egypt Language Assessment

| Source | Arabic interface/data | English interface/data | Recommended handling |
|---|---:|---:|---|
| EFCBC portal | Yes | Not confirmed at record level | Verify membership/certificate values; do not invent English names |
| DRSO consulting offices | Yes | No record-level English values confirmed | Populate `_ar`; keep English base fields `NULL` |
| Engineers Syndicate | Yes | English branding exists, but a bilingual office register was not confirmed | Use only verified source values |
| Environmental Affairs accreditation | Yes | English selector exists; bilingual records not confirmed | Populate `_ar` until individual English values are verified |
| Industrial Development Authority accreditation offices | Yes | Page includes some English labels, but firm records are Arabic | Populate `_ar`; emails and phones remain language-neutral |
| Egyptian Survey Authority approved firms | Yes | No record-level English values confirmed | Populate `_ar`; keep English base fields `NULL` |

---

# Part II — Sultanate of Oman

## 10. ESNAD / Tender Board — Registered Companies

- Authority: Projects, Tenders and Local Content Authority, using the Oman Tender Board eTendering/ESNAD system
- English public directory: https://etendering.tenderboard.gov.om/product/ReportAction?CTRL_STRDIRECTION=LTR&PublicUrl=1&eventFlag=RegVendorPublic
- Arabic public directory: https://etendering.tenderboard.gov.om/product/ReportAction?CTRL_STRDIRECTION=RTL&PublicUrl=1&eventFlag=RegVendorPublic
- Coverage: Registered local, SME, international, and other company types across contracting, consulting, supplies, services, IT, and other categories
- Access type: Public searchable and paginated directory
- Database suitability: **Excellent and the primary Oman source**

### Public filters observed

```text
category
subcategory
subcategory_grade
company_name
company_type
ptlc_or_cr_number
```

### List fields observed

```text
sequence_number
firm_name
firm_name_ar
ptlc_or_cr_number_raw
address
address_ar
telephone_number
fax_number
registered_category
registered_category_ar
registration_expiry_date
company_type
company_type_ar
source_detail_url
```

### Important bilingual finding

The English and Arabic views display corresponding records with the same `PTLC / CR Number`. The English view supplies English firm names, categories, and company types, while the Arabic view supplies the Arabic equivalents.

Match the two language versions using `ptlc_or_cr_number_raw` and other stable identifiers. Never join by row position or company name alone.

Some addresses in the English view may remain Arabic or may be blank. Store an address in `address_ar` when its source value is Arabic, even if it was retrieved from the English interface. Leave `address` as `NULL` unless an official English address is present.

### Coverage warning

The register is broader than contractors and engineering consultants. The category `Consulting Offices` also includes non-engineering professions such as legal consulting. To produce a construction and engineering dataset:

1. Filter contractor categories relevant to construction, maintenance, ports, roads, bridges, railways, dams, pipelines, wells, electromechanical work, and telecommunications.
2. Filter `Consulting Offices` by subcategory and activity.
3. Retain the exact category, subcategory, activity code, activity description, grade, and expiry date.
4. Do not label every `Consulting Offices` record as an engineering consultant without validating its activity.

### Multi-value modelling warning

A firm can have several registered categories, with a different expiry date for each category. Do not store all categories in one comma-separated field. Use a child table such as `firm_registrations` or `firm_classifications`.

## 11. Oman Registration and Classification Regulation

- Official regulation PDF: https://www.ptlc.gov.om/en/Document/Guidline/%D8%AF%D9%84%D9%8A%D9%84%20%D8%AA%D8%B3%D8%AC%D9%8A%D9%84%20%D8%A7%D9%84%D8%B4%D8%B1%D9%83%D8%A7%D8%AA.pdf
- Official tender-regulations page: https://www.ptlc.gov.om/ar/Pages/Tender-Regulations.aspx
- Purpose: Defines classification and registration of suppliers, contractors, and consultancy offices in the central register
- Database suitability: **Authoritative reference for the meaning and scope of registration**

The regulation states that the classification and registration certificate enables the holder to compete for government project and procurement tenders. It applies to licensed entities in Oman, subject to the regulation's stated exceptions and treatment of foreign entities.

Use this source to interpret the ESNAD register. Do not use it as a company list.

## 12. Oman Category, Subcategory, and Activity Taxonomy

- Official ESNAD classification PDF: https://etendering.tenderboard.gov.om/product/showTenderDocument?CTRL_STRDIRECTION=RTL&encparam=flag%2CfileName%2CviewPath%2CpublicUrl%2CCTRL_STRDIRECTION%2Crandomno&fileName=Categories_SubCategories_Activities_Classification_Updated_07092021.pdf&flag=viewgeneraldoc&hashval=ef6893018b14bee332d321b78a218998c2aac2ea8aec2133475936d709a0f3fe&publicUrl=1&viewPath=%2FLive%2FGeneralDocFiles
- Coverage: Bilingual category, subcategory, and Ministry of Commerce activity descriptions and codes
- Database suitability: **Excellent reference data, but the published file is dated 7 September 2021 and must be checked against the live taxonomy**

### Fields available in the taxonomy

```text
category
category_ar
subcategory_number
subcategory
subcategory_ar
activity_code
activity
activity_ar
```

The document confirms that `Consulting Offices` contains multiple types of consultancy, including engineering, IT, legal, and other fields. Use activity-level filtering to select engineering consultancies.

## 13. Oman Business Platform — Commercial Registration Verification

- Official platform: https://www.business.gov.om/
- Ministry service directory: https://tejarah.gov.om/service-directory
- Official government confirmation that commercial-register search is a platform service: https://omannews.gov.om/topics/en/80/show/117212
- Authority: Ministry of Commerce, Industry and Investment Promotion
- Coverage: Commercial registrations and business licensing
- Database suitability: **Strong verification/enrichment source; not recommended as the primary bulk-discovery source**

The service supports searching commercial registrations and is useful for confirming a company's legal registration. The live workflow may require CAPTCHA and interactive navigation.

The agent must verify the current public output fields. Candidate fields that may be available include:

```text
commercial_registration_number
firm_name
firm_name_ar
legal_form
legal_form_ar
commercial_registration_status
commercial_registration_status_ar
commercial_registration_expiry_date
registered_activities
registered_activities_ar
```

Do not bypass CAPTCHA or access controls. Prefer an official API, export, open-data source, or approved data-sharing route if systematic collection is required.

## 14. Madayn eMassar — Providers Directory

- Official public directory: https://ems.peie.om/newDir/ProvidersDir.aspx
- Authority: Madayn / Public Establishment for Industrial Estates
- Coverage: Providers registered in the eMassar ecosystem, including contractors, consultants, suppliers, and environmental consultancy companies
- Access type: Public searchable directory
- Database suitability: **Very good supplemental source for bilingual names, provider type, city, website, and phone**

### Filters observed

```text
provider_type
provider_name
```

### Fields observed

```text
provider_type
provider_type_ar
firm_name
firm_name_ar
website_url
city
city_ar
phone_number
```

### Strengths

- Arabic and English company names are displayed in paired columns.
- Arabic and English city names are displayed in paired columns.
- Provider type distinguishes contractors, consultants, suppliers, and environmental consultancy companies.

### Limitations

- This is a provider directory associated with Madayn/eMassar, not the national legal register of every Omani firm.
- Duplicate names and multiple branches or city records may occur.
- Data quality varies; websites, emails, spellings, or phone numbers may be inconsistent.
- Use the ESNAD registration number or commercial registration number for identity resolution whenever available; do not deduplicate only by name.

## 15. Sources Not Confirmed as Complete Public Directories in Oman

### Oman Chamber of Commerce and Industry

- E-services login: https://eservices.chamberoman.om/login

A current complete public trade directory for contractors and consultants was not confirmed during this review. Do not treat old electoral-register PDFs or login-only member services as the primary live directory.

### Ministry of Housing and Urban Planning

- Official website: https://mohup.gov.om/

The Ministry publishes regulatory, project, building-code, and engineering-sector material, but no complete public national list of all engineering consultancy offices was confirmed. Use it for policy and sector context unless a live approved-office register is subsequently found.

## 16. Oman Source Priority

1. ESNAD `Registered Companies` for primary discovery, classification, registration expiry, and bilingual names.
2. ESNAD category/subcategory/activity taxonomy for normalization and engineering-only filtering.
3. Oman Business Platform for commercial-registration verification and legal-status enrichment.
4. Madayn eMassar Providers Directory for bilingual city, provider type, website, and phone enrichment.
5. Sector regulators or utility/vendor lists only as additional accreditations, never as replacements for the central source.

## 17. Oman Language Assessment

| Source | Arabic data | English data | Record matching | Recommended handling |
|---|---:|---:|---|---|
| ESNAD Registered Companies | Yes | Yes | Use `PTLC / CR Number` | Populate both base English and `_ar` fields when the value is genuinely present in each interface |
| ESNAD taxonomy PDF | Yes | Yes | Use category/subcategory/activity codes | Store official bilingual labels and stable codes |
| Oman Business Platform | Search supports Arabic/English business names; live output must be rechecked | Search supports Arabic/English business names; live output must be rechecked | Use CR number | Use only values observed in the official result; never translate a legal name automatically |
| Madayn eMassar Providers | Yes | Yes | No stable company ID was observed in the list; use additional identifiers | Store paired official names/cities; resolve duplicates carefully |

---

# Part III — Qatar

## 18. Ministry of Finance Monaqasat — Classified Companies Profiles

- Authority: Qatar Ministry of Finance, Government Procurement Regulation Department
- Official portal: https://monaqasat.mof.gov.qa/
- Public classified-companies directory: https://monaqasat.mof.gov.qa/ClassifiedCompaniesProfilesList/1
- Contractor-classification service: https://monaqasat.mof.gov.qa/OnlineServices/ContractorClassification
- Coverage: Companies classified or registered for government procurement, including contractors, suppliers, service providers, and consultancy activities
- Access type: Public searchable and paginated directory
- Database suitability: **Excellent primary discovery source, provided that construction and engineering records are selected at activity level**

### Search and list fields observed

```text
company_profile_file_number
company_type
company_type_ar
firm_name
firm_name_ar
commercial_registration_number
trade_license_number
legal_form
legal_form_ar
official_email_address
company_size
company_size_ar
government_entity_rating
activity_sector
activity_sector_ar
source_detail_url
```

The live search also exposed filters for company type, file number, company name, commercial registration number, trade-license number, legal form, company attribute, official email, activity sector, profile activity, company size, and activity classification grade. The verifying agent must capture the exact current labels and distinguish search-only fields from values returned in list or detail records.

### Classification fields

Contractor-classification records may expose:

```text
specialization
specialization_ar
classification_grade
classification_grade_ar
classification_expiry_date
```

Supplier and service-provider activities may expose:

```text
activity_code
activity
activity_ar
classification_grade
classification_grade_ar
classification_expiry_date
```

Engineering-related activities observed during review included code `711010` for engineering and architectural consultancy offices, `71103` for civil-engineering offices, `711032` for several specialist engineering-office activities, and `711050` for surveying and quantity-services offices. These codes and their exact current labels must be rechecked in the live system before collection.

### Bilingual handling

The portal has separate Arabic and English views containing localized company and activity values. Match language versions using `company_profile_file_number` together with the commercial registration number. Do not match by page position or name alone, and verify that the record identifier remains stable across both interfaces.

Monaqasat classification indicates procurement classification or registration. It must not automatically be treated as proof that an engineering office holds every professional or municipal licence required to practise.

## 19. Ministry of Municipality — Engineering Offices Regulatory Framework

- Official English classification/regulatory document: https://www.mm.gov.qa/static/cat_doc/pdf/eng_E_2-ver5-en.pdf
- Official Arabic requirements and fees document: https://www.mm.gov.qa/static/cat_doc/pdf/fees.pdf
- Official Arabic engineering-profession regulation: https://www.mme.gov.qa/static/cat_doc/pdf/org_eng_rule.pdf
- Authority: Engineers and Engineering Consultancy Offices Accrediting and Classifying Committee, Ministry of Municipality
- Coverage: Engineering disciplines, local office categories, foreign offices, classification conditions, required staffing, business volume, and registration rules
- Database suitability: **Authoritative regulatory and taxonomy reference, not a confirmed complete public firm directory**

Use these sources to interpret professional categories and licensing requirements and to design reference tables. No current complete public searchable list of every licensed engineering consultancy office was confirmed during this review.

## 20. Qatar Source Priority

1. Monaqasat Classified Companies Profiles for primary discovery, procurement classification, activities, grades, and expiry dates.
2. Monaqasat activity codes for construction and engineering-only filtering.
3. Ministry of Municipality engineering-office rules for professional classification and licensing interpretation.
4. A Ministry of Municipality licence record, official API/export, or authorized data response for final professional-practice verification if available.

## 21. Qatar Language Assessment

| Source | Arabic data | English data | Recommended handling |
|---|---:|---:|---|
| Monaqasat Classified Companies | Yes | Yes | Join the language views by stable file/CR identifiers and store only official values |
| Monaqasat activities and classifications | Yes | Yes | Store activity codes once and official labels in base and `_ar` fields |
| Municipality engineering-office documents | Yes | Yes, in a separate official document | Use for regulatory taxonomy; do not infer that a bilingual rule creates bilingual company records |

## 22. Qatar Coverage Conclusion

Qatar has a strong public national-style procurement directory that can identify many contractors and engineering consultancy activities. The resulting database must explicitly distinguish procurement classification from professional engineering-office licensing. A claim that the dataset contains every licensed engineering office requires a separate completeness check with the Ministry of Municipality.

---

# Part IV — Bahrain

## 23. Ministry of Works — Contractor Prequalification

- Official service page: https://www.works.gov.bh/English/Services/cost/pages/cedapps2/Default.aspx
- Public category-list example: https://www.works.gov.bh/English/Services/cost/Pages/CedApps2/Listing2.aspx?catId=3&glId=100
- Public report-download example: https://www.works.gov.bh/English/Services/cost/Pages/CedApps2/DownloadReport.aspx?catId=1&glId=0
- Coverage: Contractors currently prequalified by the Bahrain Ministry of Works, grouped by work category and grade
- Access type: Public list and downloadable report views
- Database suitability: **Excellent authoritative source for Ministry of Works prequalification; not a list of every contractor holding a commercial registration**

### Fields observed

```text
firm_name
commercial_registration_number
po_box
telephone_number
fax_number
email_address
contractor_category
contractor_category_ar
contractor_grade
contractor_grade_ar
monetary_limit_or_capacity
prequalification_expiry_date
comments
source_list_url
```

The records observed were largely English. An Arabic interface or Arabic page label does not prove that Arabic firm names are available. Keep `firm_name_ar` and other `_ar` values `NULL` unless the official record actually provides them.

## 24. Benayat — Licensed Engineering Offices

- English public directory: https://www.benayat.bh/building-permits/public/engineering-office?lang=en
- Arabic public directory: https://www.benayat.bh/building-permits/public/engineering-office?lang=ar
- About/licensing context: https://www.benayat.bh/building-permits/public/about?lang=ar
- Supplemental official planning directory, English: https://www.planning.bh/liscensed-engineering-office.html
- Supplemental official planning directory, Arabic: https://planning.bh/ar/liscensed-engineering-office.html
- Coverage: Engineering offices licensed for Bahrain building-permit preparation
- Licensing authority referenced by the service: Council for Regulating the Practice of Engineering Professions, or CRPEP
- Database suitability: **Excellent primary public source for licensed building-permit engineering offices**

### List and detail fields observed

```text
office_license_number
office_category
office_category_ar
firm_name
firm_name_ar
engineering_disciplines
engineering_disciplines_ar
responsible_manager_name
responsible_manager_name_ar
commercial_registration_number
address
address_ar
telephone_number
fax_number
email_address
source_detail_url
```

The Arabic interface localizes interface labels, but the office names, disciplines, addresses, and manager names observed were commonly still English. Therefore, interface language must not be used as evidence of record-value language. Use CR number and office licence number for matching and deduplication.

## 25. Sijilat — Commercial Registration Verification and Bilingual Enrichment

- Public advanced search: https://www.sijilat.bh/public-search-cr/search-cr-2.aspx?advancedSearch=true
- Ministry of Industry and Commerce service overview: https://www.moic.gov.bh/en/node/2724
- Coverage: Bahrain commercial registrations and business activities
- Database suitability: **Strong legal verification and official Arabic/English name-enrichment source**

Search fields observed include CR number, English commercial name, Arabic commercial name, company type, status, CR type, registration dates, nationality, sector and business activities, partner names in English and Arabic, partner identifiers, address, and municipality.

Use `commercial_registration_number` to link Ministry of Works or Benayat records to Sijilat. Retain source provenance so an official legal name from Sijilat is not misrepresented as a name published by the specialist directory.

## 26. Bahrain Supporting and Specialized Sources

- CRPEP official website: https://www.crpep.bh/
- CRPEP executive regulation: https://www.crpep.bh/Executive_Regulation_Final_Version.pdf
- Survey and Land Registration Bureau private survey companies: https://www.slrb.gov.bh/en/private-survey-companies
- Bahrain Tender Board eTendering portal: https://etendering.tenderboard.gov.bh/

CRPEP is the professional licensing authority, but its account portal was not confirmed as a better public bulk-discovery source than Benayat or the planning directory. The SLRB page is a useful specialist list for authorized private surveying companies and must be modelled as a separate accreditation. The Tender Board provides procurement-registration context, but a stable detailed public supplier list suitable for collection was not confirmed during this review.

## 27. Bahrain Source Priority and Language Assessment

1. Ministry of Works lists/reports for prequalified contractors.
2. Benayat, cross-checked with the official planning directory, for licensed engineering offices.
3. Sijilat for legal status, CR identity, activities, and official Arabic/English commercial names.
4. CRPEP for professional-regulatory interpretation.
5. SLRB and other sector lists as separate accreditations.

| Source | Arabic record values | English record values | Recommended handling |
|---|---:|---:|---|
| Ministry of Works contractors | Not consistently observed | Yes | Populate English base fields; use `NULL` for unobserved Arabic values |
| Benayat/planning engineering offices | Interface is Arabic-capable, but Arabic entity values were not consistently observed | Yes | Do not copy English values into `_ar` fields |
| Sijilat commercial registry | Yes | Yes | Use CR number to obtain and preserve the two official commercial names |
| SLRB survey companies | Not consistently observed | Yes | Treat as a specialist accreditation and preserve published values only |

---

# Part V — Kuwait

## 28. Central Agency for Public Tenders and Company Qualification

- CAPT Arabic portal: https://capt.gov.kw/ar/
- CAPT English portal: https://capt.gov.kw/en/
- Kuwait Government Online company-qualification service, English: https://e.gov.kw/sites/kgoenglish/Pages/eServices/CTC/RehabilatedTenderMain.aspx
- Kuwait Government Online company-qualification service, Arabic: https://e.gov.kw/sites/kgoarabic/Pages/eServices/CTC/RehabilatedTenderMain.aspx
- Official Public Tenders Law in English: https://capt.gov.kw/media/filer_public/ed/e8/ede8d640-d366-475a-8806-b3ea6dad59c8/law_no__________of_2016.pdf
- Coverage: Registration and classification of contractors, suppliers, service providers, and consultancy-service providers for public procurement
- Database suitability: **Authoritative, but public record-level directory access and exportability require live verification**

The law provides for registers of suppliers, contractors, and service providers and for contractor classification. The current CAPT navigation includes contractor/supplier/service-provider registration and consultancy-service-provider registration. The Kuwait Government Online service states that users can access company-qualification information. However, this review did not confirm a complete, current, easily browsable public list of all classified contractors or registered consultancy providers.

Candidate fields indicated by official registration workflows include:

```text
firm_name
firm_name_ar
commercial_registration_number
address
address_ar
branch_details
branch_details_ar
telephone_number
mobile_number
fax_number
official_email_address
license_type
license_type_ar
license_expiry_date
authorized_signatory_name
authorized_signatory_name_ar
owners
owners_ar
```

These are candidate schema fields, not confirmation that every value is publicly returned. The agent must record which fields are actually visible without authentication and must not automate around access controls.

## 29. Kuwait Municipality — Contractor and Engineering Office Systems

- Contractor System, English: https://www.e.gov.kw/sites/kgoenglish/Pages/eServices/KM/ContractorsSystem.aspx
- Contractor System, Arabic: https://e.gov.kw/sites/kgoarabic/Pages/eServices/KM/ContractorsSystem.aspx
- Engineering Offices System, Arabic: https://e.gov.kw/sites/kgoarabic/Pages/eServices/KM/EngineerSystem.aspx
- Coverage: Contractor registration, renewal, data updates, category changes, cancellation and related municipal workflows; engineering-office access to planning and building-permit services
- Database suitability: **Authoritative workflow/status-verification source, but not a confirmed public directory**

Do not treat a registration, login, renewal, or permit-service page as a company list. The agent must determine whether the systems expose a public inquiry, approved-office list, API, or official downloadable register.

## 30. Ministry of Public Works — Contractor and Consultant Qualification

- Companies and Contractors page: https://www.mpw.gov.kw/sites/ar/Pages/CompaniesAndContractors/CompaniesAndContractors.aspx
- Kuwait Government Online consultancy-office service, English: https://www.e.gov.kw/sites/kgoenglish/Pages/eServices/MPW/RegistrationUpdateDataFromOfficeConsultant.aspx
- Kuwait Government Online consultancy-office service, Arabic: https://e.gov.kw/sites/kgoArabic/Pages/Services/MPW/UpdateOfficeHouseDataConsultant.aspx
- Coverage: Contractor and consultant qualification, supplier registration, and registration/update of engineering offices and consulting houses
- Database suitability: **Authoritative for qualification workflows, but no complete public firm list was confirmed**

The official service information indicates that engineering offices and consulting houses must maintain registration and meet relevant licensing or committee requirements. Model municipal professional licensing, Ministry of Public Works qualification, Ministry of Finance committee registration, and CAPT procurement classification as separate registrations unless an official rule proves they are the same status.

## 31. Kuwait Specialized and Supporting Sources

- Public Authority for Housing Welfare contractor requirements: https://www.pahw.gov.kw/Contractors_en
- Public Authority for Industry registered consultant directory, English: https://www.pai.gov.kw/en/web/guest/registered-consultant-directory
- Public Authority for Industry registered consultant directory, Arabic: https://www.pai.gov.kw/web/guest/registered-consultant-directory
- Kuwait Direct Investment Promotion Authority listed consulting companies and offices: https://kdipa.gov.kw/investors-service-center/listed-companies-offices/
- Ministry of Commerce and Industry e-services: https://moci.gov.kw/en/e-service/
- Commercial Registry management, English: https://e.gov.kw/sites/kgoenglish/Pages/eServices/MOCI/CommercialRegistryManagement.aspx
- Commercial Registry management, Arabic: https://e.gov.kw/sites/kgoarabic/Pages/eServices/MOCI/CommercialRegistryManagement.aspx

PAHW publishes qualification requirements rather than a confirmed complete contractor list. PAI's directory is specialized for its own consultant purpose and showed no registered consulting offices at the review time. KDIPA lists firms accredited for investor-service applications and is not a general engineering-consultant directory. Ministry of Commerce sources are useful for legal-registration verification if a public inquiry or authorized extract is available, but no Bahrain-Sijilat-style complete public search was confirmed.

## 32. Kuwait Source Priority, Language, and Coverage Conclusion

1. Test the CAPT/Kuwait Government Online company-qualification service for lawful public discovery and stable identifiers.
2. Use CAPT classification as a procurement status, not as a substitute for municipal or professional licensing.
3. Use Kuwait Municipality and Ministry of Public Works sources to verify their distinct registration and qualification statuses.
4. Use PAI, KDIPA, PAHW, utility, or other agency lists only as specialized accreditations with explicit coverage.
5. Seek an official API, export, open-data dataset, or data-sharing agreement if a complete national database is required.

| Source | Arabic data | English data | Recommended handling |
|---|---:|---:|---|
| CAPT and KGO | Strong Arabic support | English interface and some bilingual registration fields exist | Verify actual public record values; do not assume a form field is publicly downloadable |
| Kuwait Municipality | Strong Arabic support | Some English service descriptions | Treat workflow language separately from record language |
| Ministry of Public Works | Strong Arabic support | English service information exists | Keep statuses separate and populate only observed official values |
| PAI/KDIPA specialized lists | Source-dependent | Source-dependent | Do not generalize specialized coverage to the whole market |

No complete combined public directory of every Kuwait contractor and engineering consultancy office was confirmed. A defensible Kuwait dataset will probably require federation of multiple official sources or authorized data access, with provenance and coverage recorded for every row.

---

# Part VI — Recommended Database Design

## 33. Bilingual Naming Rule

Use lowercase English `snake_case` column names.

- Base field: official English content, for example `firm_name`.
- Arabic field: the same column name plus `_ar`, for example `firm_name_ar`.
- If the official source provides only Arabic, store it in the `_ar` field and leave the English base field `NULL`.
- Do not automatically translate or transliterate a legal company name and present it as official.
- If machine translation is required for search, store it in a clearly separate field such as `firm_name_en_machine`, not `firm_name`.
- Language-neutral values such as IDs, dates, phone numbers, email addresses, URLs, coordinates, and Boolean values must be stored only once.

## 34. Recommended `firms` Table

```text
firm_id
country_code

firm_name
firm_name_ar
trade_name
trade_name_ar
firm_type
firm_type_ar
legal_form
legal_form_ar
company_type
company_type_ar

commercial_registration_number
regulatory_registration_number
membership_number
company_profile_file_number
trade_license_number
office_license_number
profession_license_number
source_registration_number_raw

commercial_registration_status
commercial_registration_status_ar
commercial_registration_issue_date
commercial_registration_expiry_date

address
address_ar
governorate
governorate_ar
city
city_ar
postal_code

telephone_number
mobile_number
fax_number
email_address
website_url
government_entity_rating
government_entity_rating_ar

source_system
source_list_url
source_detail_url
first_collected_at
last_collected_at
last_verified_at
```

## 35. Recommended `firm_classifications` Table

Use a child table because one firm can have many classifications, activities, grades, and expiry dates.

```text
firm_classification_id
firm_id
regulatory_authority
regulatory_authority_ar

category_code
category
category_ar
subcategory_code
subcategory
subcategory_ar
activity_code
activity
activity_ar

classification_grade
classification_grade_ar
classification_status
classification_status_ar
classification_issue_date
classification_expiry_date

source_record_id
source_url
last_verified_at
```

## 36. Recommended `firm_accreditations` Table

Use this for specialist approvals such as Egyptian environmental, industrial, or surveying accreditation.

```text
firm_accreditation_id
firm_id
accrediting_authority
accrediting_authority_ar
accreditation_type
accreditation_type_ar
accreditation_number
accreditation_status
accreditation_status_ar
accreditation_field
accreditation_field_ar
issue_date
expiry_date
source_url
last_verified_at
```

## 37. Recommended `firm_contacts` Table

```text
firm_contact_id
firm_id
contact_type
contact_type_ar
contact_name
contact_name_ar
job_title
job_title_ar
telephone_number
mobile_number
email_address
is_primary
source_url
last_verified_at
```

## 38. Identity and Deduplication Rules

1. Prefer national commercial registration numbers and regulator registration numbers over names.
2. Preserve the source identifier exactly as published in `source_registration_number_raw`.
3. Do not split a combined identifier such as Oman's `PTLC / CR Number` until its format has been validated for local, international, SME, and vehicle-contractor records.
4. Match Oman's English and Arabic ESNAD views using the stable registration identifier.
5. Match Qatar's Monaqasat language views by the company-profile file number and confirm with the commercial registration number.
6. Use Bahrain's commercial registration number and professional office licence number to connect specialist directories with Sijilat.
7. Keep Kuwait CAPT classification, municipal contractor or office registration, Ministry of Public Works qualification, and specialist accreditation as distinct source statuses.
8. Do not merge firms merely because their Arabic or English names look similar.
9. Model branches separately when the same legal firm appears in multiple cities or with multiple contacts.
10. Store source values unchanged and put cleaned values in separate normalized columns where necessary.

---

# Part VII — Agent Verification Checklist

## 39. Required Checks Before Collection

The verifying agent must:

1. Open every source listed above and record whether it is live on the verification date.
2. Confirm which organization owns and operates the source.
3. Confirm whether the source is a legal register, professional register, tender register, approved-provider list, accreditation list, or marketing/member directory.
4. Record the exact filters, fields, page size, page count, total records, detail fields, and update date.
5. Check for official API, CSV, Excel, JSON, XML, open-data download, or documented integration before using browser automation.
6. Review terms of use, privacy notices, robots policy, rate limits, and republication restrictions.
7. Do not bypass authentication, CAPTCHA, access controls, or technical safeguards.
8. Verify whether personal contact data may lawfully be collected and republished.
9. Capture one evidence sample for a contractor and one for an engineering consultant from each applicable source.
10. For bilingual sources, confirm that the English and Arabic records refer to the same entity using a stable identifier.
11. Record nulls honestly. Do not manufacture English values when only Arabic is supplied.
12. Separate legal names, trade names, translated names, and machine-generated transliterations.
13. Confirm whether classifications and grades are current and whether each has its own expiry date.
14. Recheck all time-sensitive counts and dates before publication.

## 40. Oman-Specific Verification Tasks

1. Determine the exact live ESNAD category codes for construction contractors.
2. Identify the engineering-consultancy subcategories and activities under `Consulting Offices`.
3. Confirm whether `View Details` is public and list every additional field it exposes.
4. Determine whether approved practical experience fields are public or visible only to government users.
5. Validate all formats used in `PTLC / CR Number` before parsing it.
6. Confirm whether the 2021 taxonomy PDF has been replaced by a newer official version.
7. Test whether category expiry dates map one-to-one with categories when a firm has multiple registrations.
8. Check whether ESNAD exposes an official data export or API.
9. Confirm the live Oman Business Platform commercial-registration fields without bypassing CAPTCHA.
10. Determine whether eMassar exposes a stable company identifier or only names and contact data.

## 41. Egypt-Specific Verification Tasks

1. Ask the EFCBC whether a public or licensed member directory, API, export, or data-sharing service exists.
2. Obtain and verify the exact fields on an official current contractor registration/classification certificate.
3. Confirm the scope, update date, total records, and inclusion criteria of the DRSO consulting-offices page.
4. Confirm whether the Egyptian Engineers Syndicate offers a current electronic directory for consulting offices and houses of expertise, not only individual consulting engineers.
5. Inspect the detail pages in the Environmental Affairs accreditation search and record all fields.
6. Recheck the number and fields of Industrial Development Authority accreditation offices.
7. Inspect every Egyptian Survey Authority detail link and distinguish companies, offices, and public utility information centers.
8. Determine whether the government procurement portal exposes a lawful public supplier/contractor/consultant search or export.

## 42. Qatar-Specific Verification Tasks

1. Record the live Monaqasat result count, page size, pagination behaviour, and update date; treat every count as time-sensitive.
2. Confirm that `company_profile_file_number` and commercial registration number are stable and identical across the Arabic and English views.
3. Capture one contractor and one engineering-consultancy sample in both languages and list every field exposed on their detail/activity views.
4. Recheck the exact engineering-office activity codes, labels, classification grades, and certificate-expiry semantics.
5. Determine whether the Monaqasat classification is active, expired, suspended, or historical and how each state is exposed.
6. Confirm whether an official API or export exists before considering browser automation.
7. Ask the Ministry of Municipality whether it publishes a current complete directory or data service for licensed engineering consultancy offices.
8. Document the legal distinction between procurement classification and professional engineering-office licensing.

## 43. Bahrain-Specific Verification Tasks

1. Enumerate every Ministry of Works contractor category and grade and verify which report URL parameters are stable.
2. Record report generation dates, expired-record handling, monetary limits, and whether all contact fields are current.
3. Compare Benayat and the official planning licensed-office directory for coverage, update timing, stable IDs, and conflicting records.
4. Confirm with CRPEP whether the public licensed-office list is complete and whether suspended or expired licences are shown.
5. Join contractor and consultant samples to Sijilat by CR number and verify the official English and Arabic commercial names.
6. Do not interpret an Arabic interface as Arabic record data; record the actual script/language of every value.
7. Determine whether the Tender Board exposes a stable public supplier list or export that materially adds to the specialist sources.
8. Keep SLRB surveying authorization and other sector approvals as separate accreditations.

## 44. Kuwait-Specific Verification Tasks

1. Test the Kuwait Government Online Company Qualification service and record all publicly returned fields, filters, identifiers, pagination, and exports.
2. Locate and verify any current CAPT public register of classified contractors and any public register of consultancy-service providers.
3. Confirm whether CAPT exposes the four statutory contractor classes and each firm's current class, activities, issue date, expiry date, and status.
4. Determine whether Kuwait Municipality provides a public approved-contractors list and a public licensed-engineering-offices list, rather than only application/login workflows.
5. Determine whether the Ministry of Public Works provides a public qualified-contractors or registered-consultants list or an authorized export.
6. Verify the distinct meanings and identifiers of CAPT classification, municipal licensing, Ministry of Public Works qualification, and Ministry of Finance consulting-house registration.
7. Test whether official Arabic and English legal names are present at record level and identify the stable key used to join them.
8. Confirm whether Ministry of Commerce offers public commercial-registration verification or whether an official extract/data-sharing route is required.
9. Record the narrow scope of PAI, KDIPA, PAHW, and other entity-specific lists and never use them to claim national completeness.
10. Do not bypass login, CAPTCHA, or access controls; request an official API, export, or data-sharing agreement when necessary.

## 45. Final Recommendation

For Oman, start with the ESNAD Registered Companies directory and join the English and Arabic interfaces through the PTLC/CR identifier. For Qatar, use Monaqasat as the primary discovery source, join its language views through stable identifiers, and verify engineering-office licensing separately from procurement classification.

For Bahrain, combine the Ministry of Works prequalified-contractor reports with Benayat's licensed engineering offices and use Sijilat for commercial-registration status and official bilingual legal names.

For Egypt and Kuwait, build federated datasets rather than claiming a single complete national directory. Keep each registration, qualification, licence, and sector accreditation as a separate sourced status with clearly documented coverage. Authorized official data access may be necessary for completeness.

Across all five countries, use activity-level filtering, multi-value child tables, stable official identifiers, and explicit source provenance. Never translate or transliterate a legal name into an official English or Arabic field. All source status, counts, classifications, contacts, and expiry dates are time-sensitive and must be refreshed periodically.
