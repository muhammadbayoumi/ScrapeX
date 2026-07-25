# The plan: close what is open, then draw the model

Written 2026-07-25 from a live audit, not from memory — every count in it was
measured against the running warehouse the day it was written.

Ordered by one rule: **what is already paid for comes first.** Work that is
written, tested and merely not delivered is finished before anything new is
started, because unfinished work is the most expensive kind.

---

## Phase 0 — Finish what is already built (hours, not days)

Four items. All the code exists; none of it has reached the owner.

**0.1 Ingest the MADAR crawl.** The bilingual variation shipped and the crawl
ran; nine payloads sit in the inbox and the warehouse still shows 0 variants
with an English variation against 3,011 with Arabic. One ingest, then verify
that «العرض (ملم): 610» and "Width (mm): 610" both exist on one variant.

**0.2 Correct the false line in `sources.yaml`.** SIKAEGSHOP's enrichment
comment still says the details "cost no extra request". They cost 87. A wrong
sentence in the manifest is worse than none, because the manifest is where the
next person checks.

**0.3 See MADAR's pictures in the panel.** 1,233 image rows are stored and the
API returns them for a record; nobody has watched the gallery draw for this
source. Proven for sika, assumed for madar — and the difference between those
two words is this project's whole method.

**0.4 The panel's engine message.** It says "the launcher is not installed"
when the launcher IS installed, the native host answers `PING`, and
`START_ENGINE` replies `ok: true`. The real failure is a 14-second wait against
a cold start. Split the two cases, lengthen the wait, and delete the word
"terminal" from every branch.

**Done when:** madar shows both languages, the manifest tells the truth, a
madar record draws its gallery, and the panel never blames a component that is
working.

---

## Phase 1 — Give the owner the buttons (no terminal, ever)

The rule the owner set: anything that needs a terminal is a missing button.
Today's whole outage came from two of them.

**1.1 Restart engine.** A button that starts a fresh engine and retires the old
one. This is the fix for "the build is older than the database" — a state the
guard is right to refuse and only new code can resolve.

**1.2 Upgrade database.** The database-attention page currently prints
`python -m scrapex.cli init-db`. It becomes a button that runs the migration
and reloads.

**1.3 Repair the native host.** The panel sends its own extension id; the
engine re-registers the host for it. Removes a whole class of "it stopped
working after I reloaded the extension" for good.

**Done when:** every instruction on any error page is a control, not a command.

---

## Phase 2 — The Data Model page (the owner's ask)

Inside `/schema`, a Power BI-shaped view of the warehouse.

**2.1 Table cards.** One card per table: its name, its purpose, its live row
count, and its key columns. Grouped by the four layers the schema page already
uses — what the source said, what it costs, your unified layer, what ran.

**2.2 Relationships, drawn.** The real foreign keys, read from the schema
itself (`PRAGMA foreign_key_list`) so the diagram cannot disagree with the
database. Each line labelled with its cardinality: a site has many products, a
product has many variants, a variant has many offers, an offer has many
observations.

**2.3 The path from a site to a spreadsheet.** One horizontal flow:

    site → connector → row contract → payload → ingest gates
         → source-local layer → offers → observations
         → derived history (periods · state · changes)
         → reads → the table · the record panel · the export

with what each hop guarantees, and where the owner's own rules bite (nothing is
computed into a price; presence is per source; append-only).

**2.4 Every table clickable** to the columns it owns, so the model and the
column list are one page, not two.

Derived throughout, like the rest of the page: names, counts and relationships
are read; only the purpose sentence is authored.

---

## Phase 3 — The data defects that are still real

**3.1 The variation's URL.** All 108 Sameh Gabriel variants share one product
URL ending `?attribute_pa_color=yellow`, so five of every six links point at
the wrong colour. The URL is stored on the product and the variation has no
home for its own. Needs a migration and the connector to fill it.

**3.2 The parent SKU.** `source_product.external_sku` holds the LAST variant's
sku rather than the product's. The display was covered by adding `product_id`;
the stored value is still wrong.

**3.3 Apps Script carries prices only.** The local workbook and the Google push
both send details and history; the funnel sends the price table alone. Same
data, three destinations, two answers.

---

## Phase 4 — The vocabulary sweep (one contract change, once)

Approved and written in `docs/column-vocabulary.md`, not yet applied.

Two rules produce every name: the key and the label are the same word, and a
name states the LANGUAGE of its content — English unmarked, Arabic marked
`_ar`. Today `product_name` holds Arabic, which is the reverse of where it is
going.

It lands as ONE change because it touches one contract: storage, the payload,
every connector, the reads, the UI, the export header, saved views, and the
tests. Splitting it would mean rewriting the same contract twice.

**Preconditions:** finish the storage-layer inventory (four of the five layers
are mapped; storage and the final plan were lost to a session limit and resume
from cache), then:

1. the migration, with the five version pins rolled together;
2. `PAYLOAD_VERSION` bumped, so a payload written under the old meaning is
   refused rather than read wrong — `product_name` keeps its NAME and changes
   its CONTENT, which nothing else can catch;
3. saved views and hidden-column choices migrated with the keys;
4. every test whose assertion changes MEANING re-argued, not merely re-passed.

**Then, and only then:** the column ORDER the owner picks, applied once to the
table, the export and the sheet together.

---

## Phase 5 — Sources and outputs

**5.1 Activate what is proven.** ALSWEED, ADVANCEDCASTLE, ELSEWEDYSHOP and
MASDAR are live-verified and still `active: false`.

**5.2 ELBUROJ's English names** need a second pass on a 10s-delay crawl.

**5.3 SIKA datasheets** want their own connector.

**5.4 TABLER** has never been probed.

**5.5 GPP:** decide what the 92 country/material pairs with no local price
should look like on screen, and whether the ten-year history backfill runs.

**5.6 ETag persistence**, deferred by the owner to keep the crawl light.

---

## What this plan will not do

- It will not convert a price. Not once, not "approximately", not for ranking
  inside a source. The one time that rule was broken it put 3,312 figures in
  the warehouse that no page had ever printed.
- It will not fill the unified layer by guessing. Materials stay empty until
  the owner curates them; an automatic match is a claim nobody made.
- It will not split the vocabulary sweep to look faster.
- It will not mark anything done that has not been seen working against the
  live warehouse.
