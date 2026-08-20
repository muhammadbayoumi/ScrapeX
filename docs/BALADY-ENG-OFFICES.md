# Balady engineering offices — the owner's verification brief

**QUEUED, NOT STARTED. Its own precondition is his:**

> «ضيف هذا الملف ليكون المصدر التالى **بعد الانتهاء الكامل من مصدر مقاول**»
> — 2026-08-20, [REQ-14](REQUESTS.md#req-14--balady-engineering-offices-as-the-next-source-after-muqawil)

So nothing here is worked on until muqawil is finished, and "finished" is his
definition: **«كلّ ما ينشره الموقع»** — every field the site publishes, both
languages, detail pages included. [STATE.md](STATE.md) Track 2 carries where that
stands.

**The brief below is his, stored verbatim.** It is kept in the repository for one
measured reason: he re-sent the muqawil column specification on 2026-08-20 because
he could not tell whether it had survived — «هذا كان طلبى لمصدر مقاول … انا ارسلت
الطلب مرة اخرى ليكون واضح هل كله مسجل ام لا … لان دراسته ربما تكون فقدت». It had
survived, in `CONTRACTOR-SOURCE.md`. A specification that lives only in a
conversation cannot be checked, and he should not have to ask twice.

---

## What this repository already knows that bears on it

Recorded now, while it is cheap, so the work does not start by rediscovering it.

**The brief's own guardrails match this project's, and one of them is a standing
ruling.** It says: *"Do not bypass authentication, CAPTCHA, access controls, rate
limits, or other technical restrictions."* `HttpFetcher` is built to that already —
`SR-8` honours `Crawl-delay`, and the class docstring names user-agent rotation,
proxy rotation, header spoofing and CAPTCHA handling as deliberately absent because
*"those evade a decision the site has made"*. Nothing needs to change to comply.

**Its deliverable 6 — "whether an official public API or downloadable open dataset
exists" — should be answered FIRST**, before any schema work. It is the cheapest
possible question and it can invalidate everything after it: `balady.gov.sa` is a
government service, and if it publishes the directory as an open dataset then there
is no crawl to design. Muqawil's equivalent question was answered late and the
answer was no; here it may be yes, and it costs a handful of requests to find out.

**Two of the brief's requirements are things muqawil taught us the hard way**, and
the lessons transfer directly:

| the brief asks | what muqawil already proved |
|---|---|
| *"Count total records and confirm how pagination affects the count"* | Read the paginator's own last-page link; never assume a page size. The count is live — muqawil's tail page held 15 cards, then 2, then 3 within four days. [DEC-11](BACKLOG.md) |
| *"Do not treat an English interface label as proof that the underlying record is available in English"* | Exactly right, and stronger than it sounds: on muqawil the Arabic values are matched **by page-order index and never by label**, because the same label is spelled `رقم العضويه` with `ه` in one place. [LESSONS.md](LESSONS.md) |

**And its bilingual rule is already this project's rule**, which is worth stating so
nobody re-litigates it: base column English, `_ar` suffix for Arabic, no `_ar`
duplicate for identifiers, numbers, URLs, coordinates, times or booleans. That is
`R-12` and the shape of every column in `CONTRACTOR-SOURCE.md`.

**One thing the brief asks for that muqawil has an open ruling on.** It proposes
`office_working_hours`, `office_activities` and `office_locations` as child tables.
He has already ruled that way for muqawil's five multi-valued groups —
**«جداول أبناء للخمس كلّها»**, `R-19` — so the child-table shape here is consistent
with a decision he has taken, not a new question.

---

*Everything below this line is the owner's brief as he sent it, unedited.*

---

# Balady Engineering Offices Database — Independent Verification Brief

## 1. Objective

Independently inspect and verify all publicly displayed information in the Saudi Balady Engineering Offices Inquiry service, then confirm or correct the proposed database schema in this document.

Primary interactive source:

- https://apps.balady.gov.sa/Eservices/Inquiries/InquiryEngOffices/Index

Related official pages:

- Arabic service description: https://balady.gov.sa/ar/services/الاستعلام-عن-المكاتب-الهندسية
- English service description: https://balady.gov.sa/en/services/inquiry-about-engineering-offices
- English user guide: https://balady.gov.sa/en/services/11114/guide

Do not assume that any preliminary finding in this brief is correct. Verify it directly against the current live service and record evidence for every conclusion.

## 2. Required Agent Deliverables

Produce the following:

1. A verified inventory of every search field, result-list field, detail-page field, filter, pagination control, and available display mode.
2. A determination of which record values are available in Arabic, English, both languages, or neither.
3. A corrected relational database schema using lowercase `snake_case` English column names.
4. A data dictionary containing the source label, English column name, Arabic column name where applicable, data type, nullability, example value, and verification status.
5. A list of discrepancies, duplicate fields, ambiguous values, missing values, and legacy formats.
6. A technical feasibility assessment for collecting the public data, including pagination behavior, stable identifiers, request limits, and whether an official public API or downloadable open dataset exists.
7. A compliance note covering the site's terms of use, robots policy, rate limits, and restrictions on automated collection or republication.
8. A small verified sample covering different regions, classification grades, classified and unclassified establishments, old and new office-code formats, and records with incomplete data.
9. Evidence for the conclusions, using direct official links and screenshots or captured page labels where useful.

Do not bypass authentication, CAPTCHA, access controls, rate limits, or other technical restrictions. Do not infer unpublished personal data.

## 3. Preliminary Findings to Re-verify

### 3.1 Search inputs

The inquiry page appears to provide these search inputs:

- General search / establishment search
- Activity name
- Region
- City
- Search button

Verify the exact matching behavior of each input, including partial matching, Arabic spelling variations, minimum character requirements, and whether filters can be combined.

### 3.2 Result-list fields

The result list appears to display:

- Establishment logo
- Office code
- Establishment name
- Mobile number
- Establishment classification grade
- View-details action

Verify whether the mobile number and classification grade are frequently blank, whether sorting works for each column, and whether all display modes show the same data.

### 3.3 Detail-page fields

The detail page appears to contain these sections and fields:

#### Establishment details

- Establishment name
- Office license number
- Region
- City
- Establishment classification status
- Establishment classification grade
- Establishment logo

#### Contact details

- Mobile number
- Phone number
- Website
- Email address
- Fax number
- Address

#### Working hours

For each day from Saturday through Friday:

- Open 24 hours
- Closed
- First shift start time
- First shift end time
- Second shift start time
- Second shift end time

#### Geographic information

- Location name
- Region
- City
- Amanah/secretariat, if available
- Municipality, if available
- Address, if available
- Latitude and longitude, if exposed
- Map marker or map URL, if exposed
- Location-level mobile number, phone number, and email address

#### Service/activity information

- Activity name
- Minimum price per square metre
- Maximum price per square metre

Verify whether the price unit is always square metres, whether the currency is explicitly stated, and whether zero, blank, and unavailable prices have different meanings.

## 4. Language Availability to Verify

The following preliminary conclusion must be independently verified:

- Balady has an English description page for the service.
- The English description page appears to identify Arabic as the service-delivery language.
- The live interactive directory appears to use an Arabic interface and return establishment names, addresses, and activities in Arabic.
- The live directory does not appear to provide paired official English and Arabic record values.

Test whether English record values become available through any official language selector, English route, query parameter, response field, application state, documented API, downloadable dataset, or other official Balady interface.

Distinguish carefully between:

1. An English translation of the service-description page.
2. English translations of interface labels.
3. Official English values for individual establishments and activities.

Do not treat an English interface label as proof that the underlying record is available in English.

## 5. Bilingual Column-Naming Rule

Use the following convention:

- The base column contains English content: `establishment_name`.
- The same column name with the `_ar` suffix contains Arabic content: `establishment_name_ar`.
- If no verified English value exists, keep the base English field `NULL` and retain the Arabic source value in the `_ar` field.
- Never invent or automatically translate an official company name without recording that it is an unofficial translation.
- Identifiers, numbers, URLs, email addresses, coordinates, prices, dates, times, and Boolean values do not need an `_ar` duplicate.

Examples:

| English content | Arabic content |
|---|---|
| `establishment_name` | `establishment_name_ar` |
| `region` | `region_ar` |
| `city` | `city_ar` |
| `classification_status` | `classification_status_ar` |
| `address` | `address_ar` |
| `activity_name` | `activity_name_ar` |
| `day_of_week` | `day_of_week_ar` |

For any translated or externally sourced English value, verify whether provenance fields are needed, for example:

- `english_translation_status`
- `english_translation_source`
- `english_translation_verified_at`

## 6. Proposed Relational Schema

### 6.1 `engineering_offices`

```text
office_id
source_office_id
office_code
office_license_number

establishment_name
establishment_name_ar

region
region_ar
city
city_ar
amanah
amanah_ar
municipality
municipality_ar

classification_status
classification_status_ar
classification_grade

mobile_number
phone_number
email_address
website_url
fax_number

address
address_ar
latitude
longitude

establishment_logo_url
source_list_url
source_detail_url
collected_at
last_verified_at
```

Recommended checks:

- `office_id` should be an internal primary key.
- `source_office_id` should preserve the source identifier used by the detail-page URL.
- Store `office_code` and `office_license_number` as strings, not integers. Observed formats may contain leading zeros, slashes, or other legacy formatting.
- Verify whether `office_code` and `office_license_number` are always identical. Do not merge them until this is proven across a representative sample.
- Preserve phone and fax numbers as strings to avoid losing leading zeros.
- Normalize website URLs without overwriting the original source value unless a separate raw field is retained.

Suggested normalized values for `classification_status`:

| `classification_status` | `classification_status_ar` |
|---|---|
| `classified` | `مصنف` |
| `unclassified` | `غير مصنف` |
| `unknown` | `غير متاح` |

Verify the complete set of statuses before finalizing this controlled vocabulary.

### 6.2 `office_working_hours`

```text
working_hours_id
office_id

day_of_week
day_of_week_ar

is_open_24_hours
is_closed

first_shift_start_time
first_shift_end_time
second_shift_start_time
second_shift_end_time
```

Verification requirements:

- Confirm that there is one row per office per day.
- Confirm the meaning of checked and unchecked 24-hour and closed controls.
- Determine whether `00:00` means midnight, missing data, or a default placeholder.
- Check for logically conflicting states, such as 24-hour and closed being true simultaneously.
- Confirm whether working times use Saudi local time and whether a `timezone` field should be stored.

### 6.3 `office_activities`

```text
office_activity_id
office_id
activity_order

activity_name
activity_name_ar

minimum_price_per_sqm
maximum_price_per_sqm
currency_code
```

Verification requirements:

- Confirm whether one office can have multiple activities.
- Confirm that `activity_order` is meaningful or only a display sequence.
- Confirm the numeric format, decimal precision, unit, and currency.
- Use `SAR` only if the source or applicable official context supports it.
- Determine whether prices are mandatory, optional, estimates, or establishment-provided figures.

### 6.4 `office_locations`

Create this table only if the service exposes multiple locations or branches for one office.

```text
office_location_id
office_id

location_name
location_name_ar

region
region_ar
city
city_ar
amanah
amanah_ar
municipality
municipality_ar

address
address_ar
latitude
longitude
map_url

mobile_number
phone_number
email_address

is_main_location
```

If every establishment has exactly one location, determine whether these fields should remain in `engineering_offices` instead.

## 7. Fields That Should Not Have an `_ar` Duplicate

Unless the source demonstrates otherwise, do not create Arabic duplicates for:

```text
office_id
source_office_id
office_code
office_license_number
classification_grade
mobile_number
phone_number
email_address
website_url
fax_number
latitude
longitude
minimum_price_per_sqm
maximum_price_per_sqm
currency_code
first_shift_start_time
first_shift_end_time
second_shift_start_time
second_shift_end_time
is_open_24_hours
is_closed
is_main_location
source_list_url
source_detail_url
collected_at
last_verified_at
```

## 8. Required Data-Quality Tests

Perform at least the following checks:

1. Count total records and confirm how pagination affects the count.
2. Identify duplicate office codes, license numbers, names, contact details, and source IDs.
3. Compare the result-list values with the corresponding detail-page values.
4. Test old, short, long, slash-containing, and leading-zero code formats.
5. Measure null rates for every field.
6. Verify whether a classification grade can exist without a classified status, or vice versa.
7. Check malformed mobile, phone, fax, email, and website values without silently correcting source data.
8. Check whether region and city values use a controlled official list.
9. Check whether activity names use a controlled official list.
10. Determine whether geographic coordinates are actually available or only visually represented on a map.
11. Confirm whether the same office can have more than one location, activity, or set of contact details.
12. Check whether records include inactive, expired, historical, contractor, or non-consulting establishments.
13. Verify whether blank values, zero values, and placeholder values are semantically different.
14. Record the retrieval timestamp and the date on which each record was last independently verified.

## 9. Sampling Plan

Use a representative sample rather than validating only one or two records. Include, at minimum:

- Multiple regions and cities.
- Classified and unclassified establishments.
- Several classification grades.
- Records with complete and incomplete contact information.
- Records with and without working hours.
- Records with and without activities or prices.
- Records with modern long numeric codes and legacy short or slash-containing codes.
- At least one apparent duplicate-name case.
- At least one establishment whose official website provides an English legal name, to test the English-name provenance rule.

State the final sample size and explain why it is sufficient for each conclusion.

## 10. Final Report Format

Return the verification report in this order:

1. Executive conclusion.
2. Sources inspected and inspection date.
3. Verified language-availability conclusion.
4. Verified page-field inventory.
5. Corrected database schema.
6. Complete data dictionary.
7. Sample records.
8. Data-quality findings.
9. Collection/API feasibility.
10. Compliance and operational risks.
11. Assumptions that remain unverified.
12. Recommended next actions.

Clearly label every statement as one of:

- **Verified** — directly confirmed from an official source.
- **Inferred** — supported by evidence but not explicitly documented.
- **Unverified** — requires further evidence.
- **Not available** — confirmed absent from the inspected official interfaces.

