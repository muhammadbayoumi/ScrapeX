# Organization enrichment

Organization enrichment is a third, derived dataset built from approved company or
contractor data. It does not change the source crawl and it does not collapse a listing
and a profile into one physical table.

For Muqawil, the default definition is:

| role | dataset or field |
|---|---|
| Organization source | `contractors` |
| Optional detail source | `contractor_profiles` |
| Stable join | `contractor_id` to `contractor_id` |
| Derived output | `contractor_enrichment` |

The same workspace can use any approved dataset whose fields can supply a stable entity
key and at least one organization name. The UI proposes a mapping, but the owner reviews
it before the definition is created. Dataset identity is the pair `site_key` +
`dataset_key`; a repeated dataset key on another site is never resolved by taking the
first database row.

Field mappings are dataset-qualified, so `source:company_name` and
`detail:company_name` remain distinct. Before saving, preflight rejects empty or duplicate
source identities and duplicate detail join keys, and reports detail join coverage.
Mapping, detail source, providers and output display name are versioned. The source site,
source dataset and output dataset remain fixed. Definitions can be active, paused or
retired; a retired definition remains recoverable and can be reactivated.

## Storage model

The visible result is a normal wide `dataset_definition`, so the existing Data page,
exports and source card can read it. Internal evidence remains normalized:

| table | responsibility |
|---|---|
| `organization_enrichment_definition` | Current versioned mapping and provider selection |
| `organization_enrichment_definition_history` | Replaced immutable configuration versions |
| `organization_enrichment_job` | Captured definition, provider versions and request estimate |
| `organization_enrichment_run_item` | Immutable resumable input; completed JSON is compacted to hashes, snapshot IDs and membership |
| `organization_entity` | Stable source identity and optional reviewed canonical identity |
| `organization_identity_alias` | Source ID, domain, phone or registry identity candidates |
| `organization_merge_event` | Owner-approved cross-source canonical merges |
| `organization_source_record` | Link from an approved source row to that identity |
| `organization_provider_observation` | Per-run outcome, input hash, requests, latency and fields seen |
| `organization_fact` | Versioned value, evidence, validity and confidence dimensions |
| `organization_review_decision` | Audited approve, reject and override actions |

A current fact is unique by organization, field and provider. Seeing the same value again
updates its observation and creates no output revision. A changed value closes the old
fact, opens a new one and changes the materialized row. A successful observation closes
facts that disappeared from that provider; failed, skipped and system-error observations
preserve prior facts. The complete source row remains untouched. Output schema changes are
additive and create a new schema version.

Changing provider selection does not make facts and visible rows disagree immediately.
Facts from a removed provider remain current until the next run reaches each organization;
that run closes them and rematerializes the output in the same record transaction.

Every fact can carry entity-match confidence, extraction confidence and source authority.
The materialized row reports these separately from its combined verification score.
Disagreeing current providers create a conflict. Approve and override decisions create an
authoritative `owner_review` fact; reject closes the candidate while retaining the audit.

Matching domains or phones can propose cross-source identity candidates, but records are
never merged automatically. A canonical merge requires an owner and reason, preserves an
audit event, and refuses duplicates from the same enrichment definition. Every affected
member and its prior canonical link are recorded, so the owner can reverse a merge with a
second audited reason; reversal is refused until any newer dependent merge is reversed.

## Providers and verification

The provider boundary returns field-level facts. It may return no fact, a candidate, a
probable match, a verified match, or a fact that requires review. Null is preferred to a
guess.

- **Official Website** derives a candidate only from a mapped website or a non-generic
  organization email. An email-derived domain is a candidate, not proof of ownership.
  Requests use bounded DNS resolution, reject any non-public address set, connect to the
  validated IP, preserve Host and TLS identity, and verify the connected peer. Credentials
  in URLs, nonstandard ports, HTTPS downgrades and cross-domain redirects are refused.
  `robots.txt` is cached per origin and applied to every requested path. Responses and
  redirects are bounded, discovery stays on the same host, and extra facts require a
  published matching name. ISO numbers are only probable self-claims and require explicit
  positive certification context; a mention, negation, former certification or expired
  certification is excluded. After a probable or verified website identity match, direct
  contact-page, `tel:` and WhatsApp links can become website facts. A `mailto:` address is
  promoted only when its domain matches the official website or the full address exactly
  matches the source email, excluding third-party agency mailboxes. A direct
  `linkedin.com/company/` link published by that site can populate the LinkedIn company
  URL, but its provider remains `website`: the official site attests the link and is not
  counted again as independent LinkedIn evidence.
- **Google Places** is optional and enabled by
  `SCRAPEX_GOOGLE_PLACES_API_KEY`. It transiently combines name, coordinate, phone and
  domain evidence; invalid coordinates are omitted, and coordinates are a bias rather
  than an identity by themselves. It is never selected by default, even when configured.
  Durable storage is policy-safe and Place ID-only: `google_place_id` and
  `google_attribution`. Match decisions and scores remain transient. Google names,
  addresses, phones, websites, ratings,
  review counts and Maps URLs are not persisted as facts. Diagnostics report any legacy
  durable Google facts, current output rows and historical output revisions, and require
  an explicit owner cleanup decision.
  This boundary follows the official [Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies)
  and [Place ID storage guidance](https://developers.google.com/maps/documentation/places/web-service/place-id).
- **LinkedIn** remains unavailable as an independent provider until a verified provider
  is configured. ScrapeX does not fetch LinkedIn through the Website provider and does not
  turn search results, personal profiles or share links into a company profile or employee
  count. A company URL published by the matched official site is stored as website
  evidence for later independent confirmation.

The wide output includes source identity, website and domain, specialties, ISO
certifications, careers and general contact methods, secondary phone, WhatsApp,
Place ID-only Google fields,
LinkedIn-ready fields, decision-maker-ready fields, separate confidence scores, provider
list, evidence URLs and timestamps. Reserved Google content columns from the initial
schema remain null in current runs. Arabic appears only when an upstream source publishes
an Arabic value; interface text and field keys remain English.

## Execution and controls

The extension opens `enrichment.html` from **Enrich organizations** on a dataset card.
It creates or versions the definition, queues a run, and polls the normal
`/api/jobs/{job_ref}` contract with bounded retry backoff. Queueing atomically captures all
active source rows and matched detail JSON. An indexed temporary detail lookup keeps that
snapshot operation linear without loading the full profile table into Python memory. The
worker reads immutable run items in bounded pages of 50, commits at record boundaries,
and honors pause, resume and cancel. A crashed running item returns to pending; record
failures retry the same item up to three times. Once a run finishes, completed item JSON is
cleared to prevent every run from duplicating the entire source dataset; its hashes,
snapshot IDs and membership remain for provenance, while failed payloads remain for
diagnosis.

Only one unfinished job may exist for a definition. Provider failures are recorded per
organization and do not discard existing facts. Successful observations expire missing
facts; failed observations do not. Input hashes and provider TTLs avoid unnecessary repeat
requests. Three consecutive shared provider-system failures open that provider's circuit
for the remaining organizations. Job membership controls final output availability, so a
concurrent source crawl cannot create a mixed-generation result. Such a run ends as
`completed_with_errors`, and reopening the workspace restores its latest job and controls.

The extension also exposes cursor-paged fact decisions, cross-source identity candidates,
and reversible canonical-merge history. Diagnostics report provider versions,
observation outcomes, request totals, latency and Google storage compliance.

Operational controls are:

| variable | purpose | default |
|---|---|---|
| `SCRAPEX_ENRICHMENT_REQUEST_BUDGET` | Refuse a run whose upper-bound request estimate exceeds this value; `0` disables the cap | `0` |
| `SCRAPEX_WEBSITE_MIN_INTERVAL_MS` | Minimum process-wide interval per website host | `250` |
| `SCRAPEX_DNS_TIMEOUT_SECONDS` | DNS wait, clamped to 0.1–15 seconds | `3` |
| `SCRAPEX_GOOGLE_PLACES_QPS` | Process-wide Google request rate | `5` |

## Extension points

Providers register a factory, availability rule, version and request-cost estimate in the
provider registry; adding one does not change the job service. Adding output fields is an
additive schema version operation; it does not rewrite source datasets. Provider
credentials remain environment configuration for the engine and are never stored in the
extension or enrichment database.
