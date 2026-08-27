# Website contact and LinkedIn evidence — measured run of 100

**Request:** [REQ-44](../REQUESTS.md#req-44--use-the-company-website-for-linkedin-and-contact-evidence-then-run-100)  
**Ruling:** [R-51](../RULINGS.md#r-51--the-official-website-can-attest-a-linkedin-url-and-contact-methods-but-is-not-a-second-provider)  
**State:** Measured gate complete on `feat/organization-enrichment`; owner review pending

## Objective

Extend the existing Website provider, then run the real organization enrichment job on a
deterministic sample of 100 Muqawil contractors. The run must measure useful fields,
request cost, latency, operational failures and uncertain matches before the batch grows.

## Sample contract

Select 100 distinct contractors from the prepared 500-record pilot:

| email class | target |
|---|---:|
| corporate candidate | 70 |
| generic | 10 |
| likely typo | 8 |
| missing | 6 |
| disposable | 5 |
| invalid | 1 |

Within each class, select round-robin across regions and rank by the existing deterministic
`selection_score`. This makes the sample reproducible and prevents Riyadh from consuming
the high-scoring cohort.

## Implementation slices

1. Add failing tests for direct LinkedIn company URLs, contact pages, general email,
   telephone and WhatsApp links, lookalike hosts, personal profiles, ambiguous links and
   duplicate specialties.
2. Extend `WebsiteProvider` without creating a second provider identity. Each fact keeps
   the official page URL, confidence dimensions and extraction method.
3. Add output fields additively; existing enrichment definitions upgrade their output
   schema when the next job is queued.
4. Run the production definition, job snapshot, provider observation, fact history and
   materialization code in an isolated engine database seeded with the selected source
   rows.
5. Export the run summary, selected rows, materialized output, facts and observations.
6. Audit false matches, missing contacts, duplicate values, request outliers and provider
   errors. Fix code defects, then rerun only when the changed code can affect the result.

## Acceptance gates

- Exactly 100 source items are snapshotted and completed or completed with visible errors.
- No LinkedIn URL comes from a personal profile, share endpoint or lookalike host.
- Website-derived LinkedIn facts retain provider `website` and do not inflate the provider
  count.
- Every contact collection has a source URL; ambiguous LinkedIn candidates are not chosen.
- Output schema and field-level evidence are queryable through the normal enrichment
  dataset and review paths.
- Focused tests, Ruff and the adversarial result audit pass.

## Measured result — 2026-08-24

The final clean rerun used job `job_c2e766d5d1f3` and the production
`run_enrichment_job_once` service. It processed and materialized all 100 selected records,
made 231 provider requests and retained 26 provider failures as explicit observations.
No manual enrichment values were injected.

| result | count |
|---|---:|
| accepted websites (`probable` or `verified`) | 9 |
| website-attested LinkedIn company URLs | 4 |
| contact pages | 7 |
| contact email sets | 5 |
| contact phone sets | 3 |
| rows needing manual review | 48 |

The first result audit exposed a third-party media-agency mailbox on an official website.
A failing regression test was added, Website-provider email promotion was restricted to
the official registrable domain or the exact source email, and the same 100-record sample
was rerun. The final audit reported zero structural, provenance, canonicalization,
deduplication or same-domain email violations. The owner review workbook is the gate for
changing fields or increasing the batch.
