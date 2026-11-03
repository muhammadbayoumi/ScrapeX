---
name: study-a-source
description: How a candidate source is studied before anything is built from it — every field the site publishes and every field it holds and does not show, each with the response it came from. Use before writing a connector, before adding a `sources.yaml` entry, and whenever a host from the candidate queue is picked up.
---

# Studying a source

One question, answered completely: **what can this site actually give us?** Every field it
shows, and every field it holds and does not show. A connector written from whatever the
first page displayed collects whatever that page displayed; the fields nobody went looking
for are lost until somebody studies the site again.

**The study builds nothing.** No connector, no `sources.yaml` entry, no crawl, no
`active: true`. It ends in an issue, and the build reads that issue.

The one worked example is `docs/recon/heidelberg-materials-eg.md` — 650 lines for one site,
23 requests, and it found a price the site never renders anywhere
(`docs/recon/heidelberg-materials-eg.md:299`). Read it before your first study. The passes
below are its shape, generalised.

## The budget, fixed before the first request

- **Say the ceiling out loud before you start**, and count every request against it. A
  study is tens of requests, not thousands. The heidelberg study spent 23 with a
  self-imposed 2.5 s gap (`docs/recon/heidelberg-materials-eg.md:48`).
- **`robots.txt` and the site's terms are read first and recorded, as information, not as
  constraints.** This is his ruling for every study while the tool is under development
  (2026-10-10, #1618): «للعلم وليس للتطبيق فنحن نطور الاداة». Record:
  - every `Disallow` or `Allow` line that touches a path the study used, and any
    `Crawl-delay`, from the file `scrapex/robots.py:206` parses;
  - every clause of the terms on automated access, attribution and redistribution;
  - in the request log, each request made against a `Disallow` line.

  Whether a collector obeys `robots.txt` is his choice for each source, in the panel
  (`scrapex/robots.py:34`), and the study is what lets him make it knowingly. A clause on
  automated collection, redistribution or commercial use is a finding the study states
  plainly, and it blocks nothing: approvals are handled by the team concerned, and the tool
  is not used commercially (his word, 2026-11-01, #1655).
- **Never authenticate, never pay, never bypass a block.** A field behind a login is
  recorded as existing and gated — that is a finding, and getting at it is his decision.
- Every claim about the site cites the response that carries it. Every claim about ScrapeX
  cites `file:line`. Where you did not fetch something, say so instead of guessing.
- **A 200 is not a complete response.** A server can cut a large body off mid-stream and
  still answer 200. Parse every response before counting it, and when one fails, re-ask in
  smaller pages instead of treating the cut-off part as absent.

## Pass 0 · What the site permits

`robots.txt` and terms, recorded rather than applied as the budget above says. Rate
limits, any `X-RateLimit-*` or `Retry-After` header, whether the site 403s a plain client.
Record the user-agent you used and whether it mattered.

## Pass 1 · Identity

`scrapex/probe.py:70` answers one question — which of the ten families in
`scrapex/connectors/factory.py:34` this is, or `TBD-probe` (`scrapex/vocab.py:449`) when it
is none of them. **Run it, then distrust it**: it reads a homepage for markers and stops.
Say in the report what it would answer and where it would be wrong.

A known family means the field inventory is mostly the platform's, and the study is short.
`TBD-probe` means everything below is unknown and the study is the whole job.

## Pass 2 · The reachable surface

Enumerate what exists before reading any of it: `/sitemap.xml` and every sitemap it names,
`/robots.txt`'s own sitemap lines, category pages, the list endpoint, the detail endpoint,
pagination (parameter name, page size, whether a ceiling exists), search, filters, feeds.
**Count the rows the site claims to have** and say how you counted; a catalogue whose total
you cannot state is a catalogue you cannot tell is complete.

## Pass 3 · The visible fields

Everything a human reads on a list row and on a detail page, in the order the page prints
it. For each: the label as printed, a real sample value, the language, and whether it
appears on the list, the detail, or both. A field only the detail page carries changes the
crawl shape from one request per page to one request per product — name it here, not later.

## Pass 4 · The hidden fields — the reason this study exists

A site holds more than it renders. Work the whole list; each line is a place a field has
been found before, and a `no` is a finding as much as a `yes`.

1. **The API behind the page.** Open the network log and take the JSON the page itself
   fetches. Then read **every key in it**, not the ones the page rendered — that is exactly
   how `maxPrice` / `exWorkMaxPrice` were found
   (`docs/recon/heidelberg-materials-eg.md:299`).
2. **Embedded state in the HTML**: `__NEXT_DATA__`, `window.__INITIAL_STATE__`,
   `__NUXT__`, Redux dumps, any `<script type="application/json">`.
3. **Structured markup**: JSON-LD (`Product`, `Offer`, `Organization`), microdata, RDFa,
   OpenGraph and `<meta>`. Often carries GTIN, brand, availability and price the visible
   layout drops.
4. **The platform's own open endpoints**, whether or not the page uses them:
   `/products.json`, `/wp-json/wc/store/products`, `/graphql`, `?format=json`, a `.json`
   suffix on a detail URL, `/api/…`. `scrapex/probe.py:70` tries four of these; try the
   rest by hand.
5. **Parameters that widen the response**: `fields=`, `include=`, `expand=`, `with=`,
   `per_page=`, `limit=`, `lang=`. A REST surface that answers one shape often answers a
   fuller one when asked (`docs/recon/heidelberg-materials-eg.md:421`).
6. **GraphQL introspection**, where there is a GraphQL endpoint: the schema names every
   field the site can serve, including the ones no page requests.
7. **Every filter and facet the site offers is a field it holds**, even when no page prints
   it on the product. That is what `is_site_filter` on `db/engine/schema.sql:519` exists to
   record.
8. **Sort orders**: a sort by something the page never shows is that field, exposed.
9. **Feeds built for somebody else**: Google Merchant / Facebook product feeds, RSS,
   `/feed`, `.xml` exports. They are usually the richest single document on the site.
10. **The second language.** A bilingual site publishes most fields twice
    (`docs/recon/heidelberg-materials-eg.md:175`), and the pair is two fields, not one —
    the warehouse keeps both (`product_name` and `product_name_ar`,
    `db/engine/schema.sql:502`).
11. **List versus detail**: diff the keys of the list response against the detail
    response, both directions. Each side usually has something the other lacks.
12. **Response headers**: `X-Total-Count`, `Link` pagination, `Last-Modified`, `ETag` — a
    change-detection field is a field.
13. **Documents**: datasheets, certificates, price lists, PDFs, spec tables in images.
    Record what exists and whether the numbers in them also appear as text.
14. **Gated fields**: anything that appears only after login, only for a trade segment, or
    only in a quote. Record that it exists, what it is, and that you did not fetch it.
15. **Identifiers you did not ask for**: internal ids, slugs, plant or branch codes, SKUs,
    barcodes, category ids. They are the join keys a later match depends on.
16. **The page's own logic between the buyer and the cart**: calculators, configurators,
    unit converters, quantity steppers. Read the script, not the widget. What it writes into
    the cart's quantity is the unit the price is charged in, and the per-product constants
    it carries are fields. A default it falls back to when a field is missing is the site's
    guess, not a value the site stated. Never store it as one.

**Contacts are first-class: every phone, fax, email, website, address, map link and social
account, with where it lives, its filled count and its shape, and a field the site lacks is
named as absent.** Recommend keeping them (his ruling on #1913, #1916 and #1655, 2026-11-01).
A named individual's value stays out of the issue, as a shape and a count. What a source's terms say about them is
recorded with the other clauses, and it blocks nothing.

For each field found, one row:

| field | where it comes from (URL + path in the response) | sample | rendered on the page? | lands in | lost if dropped |
|---|---|---|---|---|---|
| `exWorkMaxPrice` | `/api/products` → `[].exWorkMaxPrice` | `1725.00` | no | `price_observation` | the ceiling of a tiered price |

**A field the site publishes and we do not take is a decision, not an oversight.** Anything
that can enrich the data is recommended in, and sibling datasets on the domain with it. The
reason against one is measured: it is empty, it is constant, or reading it moves something
on the site.

## Pass 5 · Price and its dimensions (products)

Not "the price" — the dimensions it varies on. City, branch, customer segment, quantity
tier, plant, currency, unit basis, VAT. `docs/recon/heidelberg-materials-eg.md:229` is a
six-dimensional example. For each dimension: how many values, how you enumerate them, and
whether the site states VAT or you are inferring it. **State how you know**; an inferred VAT
mode is a question for him, not an assumption.

**The cart is the measurement, and the label is a claim.** A unit field, a "prices exclude
tax" setting and a "per piece" word on the page can all be wrong. A store's tax setting
describes how prices are displayed, not what is charged. Before any of them is ruled, ask
him whether to test a guest cart; he may run it himself. Add one product from each group the
labels form, for example stated unit, no unit, and a label that looks wrong, then read the
arithmetic: quantity × price = the line, and subtotal + shipping = total, so a missing tax
line is evidence. Stop at the cart page: no checkout, no personal data.

## When the site disagrees with itself

A fact the site states twice (a field, the description text, the name, or a value derivable
from its parts) is checked over the **whole** relevant category, not a sample. A sample is
enough to find fields; a ruling needs counts from the census.

- Before deriving a value for the rows that lack it, test the formula on the rows that
  state it, and report the match rate. The rows that fail are usually the site's own entry
  errors; a second statement, such as dimensions in the name, often repairs them.
- Count agreements and conflicts for every pair of statements.
- **Keep both values, mark where they agree, and recommend with the evidence where they
  do not.** Never pick one silently, and never let a derived value pass as stated.

Nothing is parsed locally. Money, units and Arabic-Indic digits go through
`scrapex/normalize.py:43`, `:236` and `:38`, and a change there proves itself against the
frozen corpora (`scrapex/contract.py:94`).

## Pass 6 · Where every field lands

Every field found gets a destination, or is named as having none.

| what it is | where it lands |
|---|---|
| product identity, names, links, category path, brand | `db/engine/schema.sql:502` |
| an option/variant axis | `db/engine/schema.sql:549` |
| who the price is for, in what unit, with what tax | `db/engine/schema.sql:486` |
| the price reading itself, availability, stock | `db/engine/schema.sql:323` |
| anything else the product page prints, and every filter facet | `db/engine/schema.sql:519` |
| an attribute that has earned a column of its own | `db/engine/schema.sql:479` |
| a non-product dataset's columns | `scrapex/fields.py:21`, `db/engine/schema.sql:201` |
| a company, and a fact about it | `db/engine/schema.sql:734`, `db/engine/schema.sql:751` |

A connector emits one shape whatever the site is — `scrapex/connectors/base.py:186`. A field
that fits nowhere above is listed under **what has nowhere to go**, with what a home for it
would cost. A schema change is his (`CLAUDE.md`).

## Pass 7 · What would have to be built

Split into three, and do not blur them: **reuse** (the family and helpers that already
fit), **build** (a new family, a new parser, a pagination shape nothing handles), and
**blocked** (what cannot be expressed today without a schema change or his ruling). Give
each build item its own size.

## The output: one issue per source

**Never a markdown file in the repository** — `record-it`. `gh issue create`, titled with
the host and what the study settled, and containing, in this order:

1. The host, the date, the request count, and the politeness gap used.
2. What it permits (Pass 0) and what it is (Pass 1).
3. The reachable surface and the row count (Pass 2).
4. **The full field table** — visible and hidden together, with the `rendered?` column
   (Passes 3, 4, 6).
5. Price dimensions (Pass 5).
6. Reuse / build / blocked (Pass 7).
7. **What to take: everything found, each dataset and field on one line with a proposal, for
   him to decide.** The study reports and proposes; what is taken and what is left is his.
8. The questions only he can answer, each with options and the measured cost of each.
9. The request log: every URL, in order, with its status.

Then the source moves in the registry, not in prose: a manifest row at
`family: TBD-probe`, `active: false` is the only way a registry says "on the list, no
collector yet" (`scrapex/vocab.py:449`, `scrapex/sourceboard.py:56`), and validation
refuses to make it active before it is probed (`scrapex/config.py:160`).

**Once the issue is filed, open that domain's build task straight away, one task per domain,**
so finished studies do not pile up: «جلسة دراسة المصادر عندما تنتهى من دراسة مصدر تفتح مباشرة
task لبنائه حتى لاا تتتراكم علينا». It is a card, and nothing runs until he starts it
(`spawn_task`, or `start_session` with `own_initiative`). His click spends a whole session even
if it stops at its first check, so the card's text says what the build waits for. The prompt
stands alone: the issue, his answers so far, and the questions still open, which that session
asks him first.

## Done means

- [ ] Every request is logged, and the total is at or under the ceiling you named.
- [ ] `robots.txt` and the terms were read before the second request and recorded, and
      every request made against a `Disallow` line is marked in the log.
- [ ] All sixteen hidden-field lines are answered — a `no` written down, not skipped.
- [ ] The price's unit and VAT are proved by a cart, or named as unproved in the questions.
- [ ] Every fact the site states twice has its agreement counted over the census.
- [ ] Every field has a sample value taken from a real response, not an example.
- [ ] Every field has a destination, or is named as having none and costed.
- [ ] Everything found is listed with a proposal, and nothing is decided for him.
- [ ] Nothing was authenticated, bought, or bypassed.
- [ ] No connector, no `sources.yaml` edit, no crawl, no `active: true` in this change.
- [ ] The issue exists and the questions for him are at the end of it, with options.
- [ ] The domain's build task is open.
