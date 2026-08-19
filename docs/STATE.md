# State — where the work stands

**Last updated: 2026-08-19.** `main` is at `ac3a5af` — #212, plus one commit
pushed straight to `main` on 2026-08-18 carrying no PR number.

This is the document that is **wrong the moment it is out of date**. Update it
when a phase lands, a PR merges, or the owner rules — in the same pull request as
the work it describes (**C2**, [../CLAUDE.md](../CLAUDE.md)).

**For what the owner has asked for and where each request stands, see
[REQUESTS.md](REQUESTS.md).** This file tracks the *work in flight*; that one
tracks *his requests* through Captured → Ruled → Planned → In flight → Done.

---

## Open pull requests

| PR | branch | state | what it is |
|---|---|---|---|
| **#213** | `the-data-page-port-is-a-port` | **CONFLICTING** — cannot be read until it is rebased | DEC-8: the engine's Data page is a port, not a rebuild, and the measurement says which |

**#210, #211 and #212 have all merged** since this file last spoke. What used to
stand here as "both green, both waiting on the owner" is now history, and the
reason #210 mattered is kept under Track 2 where it belongs.

`ac3a5af` is on `main` without a pull request — a single-parent commit, no review
trail. **It broke `main`, and `main` has been red since 2026-08-18 because of it.**
`extension/app.css:1166` reads `background: light-dark(#FFFFFF, var(--bg));`, and
`tests/test_vendor.py::test_ui_colour_literals_live_only_in_the_canonical_colour_system`
forbids a raw hex literal outside the token system. Reproduced locally on
2026-08-19. Every PR opened since inherits the red, #214 included. **This is what
the missing pull request cost** — CI would have refused it before it reached
`main`. The fix belongs in its own PR and it is a palette-token change, so
[LESSONS.md §5](LESSONS.md#5--the-design-system-a-token-has-four-homes) governs it:
a token has four homes.

---

## Track 1 · The Console migration

**Plan:** [MIGRATION-PLAN.md](MIGRATION-PLAN.md) · **Detailed state:**
[HANDOFF-resume-the-migration.md](HANDOFF-resume-the-migration.md)

> ⚠️ That handoff was last updated at #201 and **does not record #202–#209**, which
> are all Track 2. Read it for Phase A/B detail; read this file for the whole
> picture.

**Done:** Step 0 · A0 (the blind settings guard) · **A1–A4, Phase A complete** —
the Console reads and edits all six sheets (#185–#189, #192) · T1 `crawl_pace_s`
(#190) · B2's foundation — `backend.js` extracted, Tabulator vendored,
`data.html`/`data.js`/`datatable.js` (#193) · the Console rendered in a real DOM
test (#200) · sign-out (#201, ruling [R-13](RULINGS.md#r-13--sign-out-of-all-accounts-must-really-sign-out-all-of-them))

**Resume here — the rest of B2, in this order and the order is reasoned:**

1. **The details drawer — `GET /api/offer/{key}/{id}`.** Least entangled; touches
   nothing the panel uses, so it proves the pattern on a second endpoint at no
   risk. The endpoint was built for this — its docstring says *"for the panel the
   Data page opens INLINE"*. Note its ownership rule: an offer that is not this
   source's answers 404 **without confirming the id exists at all**.
2. **Choose-Columns — `GET`/`POST /api/fields/{key}`. Do not write a second one.**
   The panel already has the whole thing: `loadSourceColumns`
   (`extension/app.js:1590`) and `saveSourceColumns` (`:1629`), speaking the same
   bodies. **Extract** it into a shared module the way `backend.js` was, or the
   two surfaces will disagree about how a column is saved.
3. **Saved views — `POST /api/views/{key}`, `DELETE /api/views/{id}`.**
   **HELD** — see [O-5](RULINGS.md#open--awaiting-the-owners-ruling). Do not start.
4. **Promotion — `GET`/`POST /api/promotable/{key}`.** Its contract was not read;
   read it first.

**Then:** remove the workbook link from the source card — but only once all four
are in. Taking it away before the replacement carries them would be a downgrade
wearing the word "migration".

**Not started:** **B1** (delete pure duplication and the dead routes) · **B3**
(Storage and Retention, the destructive half — every safety interlock moves *with*
its control) · **B4** (the rest, cheapest first) · **B5** (one navigation source
instead of three) · **B6** (the engine's new face: tray icon and log window).

**Phase C deferred:** `127.0.0.1` cannot go until the extension can read SQLite
itself (**DEC-1**, wa-sqlite + OPFS), and jobs cannot move while the heartbeat is
broken under load (**T2**).

---

## Track 2 · The muqawil.org contractor directory

**Design:** [CONTRACTOR-SOURCE.md](CONTRACTOR-SOURCE.md) · **Seam:**
[GENERIC-FETCH-SEAM.md](GENERIC-FETCH-SEAM.md) · **Plan:**
[plans/2026-08-16-muqawil-contractor-source.md](plans/2026-08-16-muqawil-contractor-source.md)
· **Rulings:** [R-10](RULINGS.md#r-10--the-contractor-directory--three-rulings),
[R-11](RULINGS.md#r-11--a-contractor-directory-is-a-separate-table-and-a-table-like-any-other),
[R-12](RULINGS.md#r-12--one-row-with-a-button-that-flips-it)

**Landed:** what muqawil knows about its own pages (#202) · reading a contractor
off the page (#203) · a crawl whose output is evidence (#204) · the declared
frontier was half the crawl (#205) · a per-server governor (#206) · cards become
an approval candidate (#207) · the membership number is unique (#208) · names
stop coming (#209) · a 404 storm must not buy speed (#210) · a dataset is a table
like any other (#211) · the contractors appear among the datasets (#212).

**In flight: nothing. The track is waiting on one decision** — see the two
feature flags below.

> **Why #210 mattered more than its size suggested.** `HttpFetcher` sends
> conditional requests, so an unchanged page answers **304 with no body** — the
> fastest answer a server can give. Without the ratchet, every re-crawl widened
> on its own emptiness: the #206 governor let 404/301/500 fall through as
> `Strain.NONE` and feed the clean run.

**The full `LISTING_ONLY` pass has run, and it is in the warehouse.** Verified
against the live database on 2026-08-19, not taken from a conversation:

```
generic_record            11,059 contractors
generic_page_snapshot        864 pages, 864 of 864 approved, zero rejected
generic_record_revision   17,275
dataset_field                496
engine db                    460 MB + 4 MB WAL
```

**The live database is `~/.scrapex/engine/scrapex-engine.db`**, per
`~/.scrapex/databases.json`. The older `~/.scrapex/marketlens/marketlens.db` is
110 MB, does not carry the generic tables at all, and will mislead anyone who
opens it looking for this data.

**Not in, and named so it is not mistaken for done:** the detail files
(coordinates, email, licences, interests) — a second crawl of ~22,000 requests ·
the Arabic half of the page snapshots (the English were stored; the Arabic values
are **inside the rows**, but their evidence is not) · the sweep that says how many
contractors the listing missed.

**One decision is open and it is the owner's:** both
`FeatureKey.GENERIC_EXTRACTION` and `FeatureKey.GENERIC_DATASET_CATALOG` are still
`False` at [scrapex/features.py:54](../scrapex/features.py) and `:60`. Their own
written condition — *"only after an approved non-product extraction reaches
generic storage"* — is now met by the figures above. Lighting them is what makes
`/datasets` appear in navigation and states the capability out loud.

**Four questions are open and are his** — O-1 to O-4 in
[RULINGS.md](RULINGS.md#open--awaiting-the-owners-ruling).

---

## Track 3 · The version debt

**Ruling:** [R-06](RULINGS.md#r-06--version-moves-with-every-merged-pull-request)
(every merged PR raises `VERSION`) · **Blocked by:**
[R-07](RULINGS.md#r-07--the-engine-keeps-the-version-gate-and-drops-the-advert)

`VERSION` is `0.2.2` at [scrapex/version.py:76](../scrapex/version.py); the
manifest is `0.2.2` too. It last moved at `adf31b2` on **2026-08-10**, and as of
2026-08-19 there are **62 commits since** — the count was 48 when the ruling was
written and 58 two days ago. It grows every time this is deferred.

**The blocker, verified 2026-08-17 and still present:**
`"latest_extension_version": VERSION` at
[scrapex/version.py:477](../scrapex/version.py) and
[scrapex/webui/app.py:1375](../scrapex/webui/app.py), drawn by
[extension/app.js:595](../extension/app.js) and `:629`.

> **Re-verified 2026-08-19, and three of these citations had already drifted.**
> `webui/app.py` was **1355**, now 1375 — #211 and #212 inserted twenty lines
> above it. And `LATEST_SOURCE`/`UPDATE_INSTRUCTIONS` were written as `:289` and
> `:292` when they have been at **282** and **285** all along; `version.py` has
> not been touched since, so those two were wrong the day they were written.
> **This is [REQ-08](REQUESTS.md#req-08--a-guard-against-the-documents-going-stale)
> arguing for itself within 48 hours** — and it is precisely the class option (b)
> catches. Bumping `VERSION` while
that stands makes the panel's *"your extension is older than the engine"* card
**permanent and false**.

**Do this in its own PR:** drop the advert (plus `LATEST_SOURCE` and
`UPDATE_INSTRUCTIONS`), keep the derived gate, add a guard that fails if
the engine ever answers for the extension's head again. Then bumping is
mechanical.

**Two more things belong in that PR:**
- Fix `LATEST_SOURCE` `:282` and `UPDATE_INSTRUCTIONS` `:285` — the drawn numbers,
  not the ones this file used to quote.
- `robots_per_source` is dated 0.2.2 and cites no commit; the ledger's own guard
  fires, correctly. Read out of `git log`, both `-S"crawl_obey_disallow"` and
  `-S"source-edit-robots"` name `adf31b2` alone — write `commit="adf31b2"`.
- ~~[ENGINEERING.md](../ENGINEERING.md) **W4** states the superseded
  per-capability rule.~~ **FIXED 2026-08-17.** It was stale twice: the trigger,
  and a claim that `extension/manifest.json` is an enforced mirror — which PR
  #112 undid and `tests/test_version.py:536` now actively guards against. W4
  would have sent a reader into re-welding the two numbers.

---

## Named gaps — recorded, not forgotten

- **`behaviourVersion` is ScrapeX's own bookkeeping, not a signal.** mbiXaddin has
  no such field; both numbers live here and one commit raises both. The real fix
  is [HANDOFF-mbiXaddin-contract-producer.md](HANDOFF-mbiXaddin-contract-producer.md).
  What *does* look upstream is
  `test_no_cited_addin_file_has_moved_since_the_reading`, which watches the `.cs`
  files the reading cites and has already found three moved.
- **Two OAuth clients, therefore two grants** — sign-out cannot reach the
  Chrome-Extension grant on a primary account, and must not try. See
  [LESSONS.md §6](LESSONS.md#6--two-oauth-clients-therefore-two-grants).
- **HTTP 400 counts as revoked**, and neither `authorize` nor `revokeToken` has a
  deadline. Same section.
- **[REQ-04](REQUESTS.md#req-04--every-setting-moves-into-the-extension) — the ten
  settings move into the extension — is ruled and unbuilt after 16 days.** Parked
  behind a review on 2026-08-01 and then lost from view. It is the entry that
  justified building [REQUESTS.md](REQUESTS.md).
- ~~**Two requests await the owner's ruling:** REQ-08 and REQ-09.~~ **BOTH RULED
  AND BUILT 2026-08-19** — he took both recommendations
  ([R-15](RULINGS.md#r-15--the-documents-are-guarded-by-a-test-not-by-good-intentions),
  [R-16](RULINGS.md#r-16--one-home-for-rulings-and-it-is-this-file)).
  `SR-1`–`SR-23` now live in `RULINGS.md` with every number intact and
  `BACKLOG.md` §1 is a pointer; `tests/test_the_documents_cite_what_they_claim.py`
  guards the citations. **Six citations across four documents were wrong and are
  corrected** — see [LESSONS.md §7](LESSONS.md#7--a-document-can-drift-into-the-opposite-of-the-code).

---

## Where the older plans went

Seven plans and a 1,015-line findings file lived in `~/.claude/plans/` — on one
machine, under one account — until 2026-08-17. They are now in
[plans/](plans/README.md). Read that index before assuming a track has no plan.
