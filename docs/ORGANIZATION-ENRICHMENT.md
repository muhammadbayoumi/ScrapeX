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

## Storage model

The visible result is a normal wide `dataset_definition`, so the existing Data page,
exports and source card can read it. Internal evidence remains normalized:

| table | responsibility |
|---|---|
| `organization_enrichment_definition` | Immutable source, detail, join, role and provider configuration |
| `organization_entity` | Stable organization identity independent of a provider |
| `organization_source_record` | Link from an approved source row to that identity |
| `organization_fact` | Field value, provider, evidence URL, confidence, status and validity interval |
| `organization_enrichment_job` | The definition and provider snapshot used by one resumable job |

A current fact is unique by organization, field and provider. Seeing the same value again
updates `last_seen_at` and creates no output revision. A changed value closes the old fact,
opens a new one and changes the materialized row. The complete source row remains untouched.

## Providers and verification

The provider boundary returns field-level facts. It may return no fact, a candidate, a
probable match, a verified match, or a fact that requires review. Null is preferred to a
guess.

- **Official Website** derives a candidate only from a mapped website or a non-generic
  organization email. It rejects private and non-public network targets, limits response
  size, follows only same-host discovery links and extracts extra facts only after the
  published organization name matches. ISO numbers require an explicit, positive
  certification context; a mention, negation, former certification or expired
  certification is not stored as a certification.
- **Google Places** is optional and enabled by
  `SCRAPEX_GOOGLE_PLACES_API_KEY`. It combines name, coordinate, phone and domain evidence;
  invalid coordinates are omitted, and coordinates are a bias rather than an identity by
  themselves. It is never selected by default, even when configured: the owner must opt in
  for each definition because Google billing, quotas and API terms apply to every enabled
  run. `google_maps_cid_url` remains null unless Google returns a URL that actually carries
  a CID; a Place ID is not relabelled as a CID.
- **LinkedIn** is shown as unavailable until a verified provider is configured. ScrapeX
  does not turn an unverified search result into a company profile or employee count.

The wide output includes source identity, website and domain, specialties, ISO
certifications, careers contact, secondary phone, Google business fields, LinkedIn-ready
fields, decision-maker-ready fields, an overall verification score, provider list,
evidence URLs and timestamps. Arabic appears only when an upstream source publishes an
Arabic value; interface text and field keys remain English.

## Execution and controls

The extension opens `enrichment.html` from **Enrich organizations** on a dataset card.
It creates the definition through `/api/enrichment/definitions`, queues a run, and polls
the normal `/api/jobs/{job_ref}` contract. The engine worker dispatches the job by
`job_kind`, commits at record boundaries and honors the existing pause, resume and cancel
controls. Source records are read in bounded pages of 50 and network clients are reused for
one job. A checkpoint stores the last source record, making retries idempotent.

Only one unfinished job may exist for a definition. Provider failures are recorded per
organization and do not discard successful facts from other organizations. Uncertain
facts are exposed by the definition's review endpoint instead of being silently promoted.
Three consecutive provider-system failures open that provider's circuit for the remaining
organizations, preventing a dead paid or remote service from stalling the whole dataset.
Such a run ends as `completed_with_errors`, and reopening the workspace restores its latest
job and controls rather than presenting a second Run action as if nothing were active.

## Extension points

Adding a provider requires one implementation of the provider result contract and one
availability entry. Adding output fields is an additive schema version operation; it does
not change old facts or rewrite source datasets. Provider credentials remain environment
configuration for the engine and are never stored in the extension or the database.
