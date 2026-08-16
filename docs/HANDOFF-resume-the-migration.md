# Where the migration stands, and where to pick it up

*Written 2026-08-15. Read this before touching Phase B.*

## The plan is `docs/MIGRATION-PLAN.md`

"ScrapeX — the Console, the migration, and the debt", drafted 2026-08-12 and
moved into this repository on 2026-08-15.

**It was written into `~/.claude/plans/`, and that was wrong twice over.** It
cost a session's opening — nothing under `docs/` matched, and it was found only
by searching the home directory for files touched on the right day. And the owner
works from two machines, morning and night: a plan on one of them does not exist
on the other. Anything this work depends on goes in the repository.

That file is the reasoning. **This one is the state**, and it is the one to keep
current when a phase lands.

## What measurement changed in the plan — read this before trusting it

Two of its statements were wrong, and both were caught by measuring rather than
by reading:

| the plan says | what is true |
|---|---|
| T1's remedy: "restore `crawl_honour_delay`" | It would have done nothing. `alsweed.sa/robots.txt` declares no `Crawl-delay`, and `honour_crawl_delay` only acts when a site declares one. Fixed as `crawl_pace_s` instead (#190). |
| B2: "`/api/records` already exists for it" | It does not. `/api/records` is the PANEL's card endpoint — compact, paginated at 100, *"the panel shows cards, never a table"*. The Data page runs on `/api/table/{key}` plus four more. Building on the card endpoint would have shipped cards and called it the migration. |

One statement checked and **upheld**: `DELETE /api/views/{id}` really has no caller
anywhere, as B1 claims. See the conflict below, though — finishing B2 revives it.

## Done

| | |
|---|---|
| **Step 0** | #182, #183 merged; the three working-tree files committed |
| **A0** | The blind settings guard — `_with_includes` expands Jinja includes; the nine Storage/Retention controls recorded in `MIGRATING_TO_THE_PANEL`, a list that may only shrink |
| **A1–A4** | **Phase A complete.** The Console reads and edits all six sheets (#185, #186, #187, #188, #189, #192) |
| **T1** | `crawl_pace_s` (#190) |
| — | samehgabriel alive after 12 days dead; the `SourceUriValidator` mirror re-derived after mbiXaddin's own repair; the contract-drift guard given something real to watch (#191) |
| **B2 · foundation** | `backend.js` extracted; Tabulator vendored into the extension; `data.html`/`data.js`/`datatable.js` (#193) |
| — | The Data page's first load, which aborted itself (#194); the Profile page's centred account (#196); a second account no longer looking signed out (#199); the Mappings card (#197) |
| **Console · rendered** | `serve_extension()` + `console_stub()` in `tools/tabpage_harness.py`, and `tests/test_console_dom.py`. The gap below is closed |

## Just landed

**Sign-out — DONE 2026-08-16.** Reviewed, ruled on, built, and mutation-tested.

**A correction first, because the first diagnosis was wrong.** It was reported
here that the row's `Sign out` had become a dead end. It had not: `accountMenu`
was called from exactly ONE place, `renderAccountsCard`, with `{signedIn: false}`
written out literally — so the item inside `if (signedIn)` had **never once been
drawn**, before or after any of this. The earlier pull request repaired the
argument `accountRow` gets and left the menu's, which is why a row could offer a
switch while its own menu could not offer a sign-out. Not a dead end: a missing
button, and the thing the owner asked for in the first place.

What was true: **`Sign out of all accounts` signed out exactly one.** It pressed
the top `#signout`, which revokes only the current account's grant; every other
account kept the standing Google grant that makes a silent mint succeed.

**THE RULING, and what was built: a real sign-out.** `endOtherAccountSession`
mints a token for the account silently (`login_hint` + `prompt=none`) and revokes
THAT token. `signOutOfAllAccounts` walks the others first — one at a time, not
`Promise.all` — and presses `#signout` last, because signing out the current
account clears `state.token` and `renderAccountsCard` returns early without one.

**THE LOCKOUT IT WOULD OTHERWISE HAVE BEEN.** The panel holds exactly ONE token
and it belongs to the CURRENT account. The obvious implementation — hand
`state.token` to `revokeToken` — ends the wrong grant: press Sign out on somebody
else's row and be signed out of your own. `tests/test_signing_out_really_signs
_out.py` guards precisely that, and nothing in the suite covered it before,
because no test had ever driven the per-row menu.

**THE HARNESS HAD TO GROW FIRST, and this is the part worth remembering.**
`tools/panel_harness.py` stubbed only `getAuthToken` and `removeCachedAuthToken`,
so `identity.js:authorize()` fell into its `getRedirectURL()` try/catch and
returned state `failed` under **every panel test ever written**. The whole
multi-account surface was unreachable, and silently — a test could press the
button and read a plausible error message. It also had no route for Google's
revoke endpoint, so every sign-out driven through it took the `local-only` path
on a 404 and no test ever looked at the message. Both are fixed; `silent_for`
and `revoke_status` are the new knobs.

### What sign-out still cannot reach, stated rather than left to be found

**There are TWO OAuth clients in this project, and therefore two grants.**
`manifest.json:oauth2.client_id` is a Chrome-Extension client (used by
`getAuthToken`); `identity.js:WEB_CLIENT_ID` is a Web client (used by
`launchWebAuthFlow`). A Google grant is per client, so `revokeToken` ends only
the grant of the client that minted the token it is given. For an account added
through the switcher that is complete — it only ever had a Web grant. For the
Chrome profile's PRIMARY account, which can hold both, one may survive. The
comment at `identity.js:176-189` is written as though there were one client.
**Not fixed here, and not to be fixed by revoking both**: on an
`admin_policy_enforced` Workspace account, `blocked-by-admin` is the branch that
pressing again cannot fix, so dropping the Chrome-Extension grant could leave an
owner unable to sign back in at all.

Two more found in the same reading and left alone deliberately:

- **HTTP 400 counts as revoked** (`identity.js:205`). Google answers 400 for an
  EXPIRED token as well as an already-revoked one, and an implicit-flow token
  lives about an hour. Sign out after an idle hour and the panel reports a grant
  ended that is still listed.
- **Neither `authorize` nor `revokeToken` has a deadline**, while `getToken` and
  `accountFor` both do. A hung revoke leaves the Sign out button disabled with
  the panel still holding the token.

### One mutation survives, and it is equivalent

Removing the early return AND switching the message from `ended.revoked` to
`ended.state === "ok"` — **both at once** — produces identical behaviour on every
reachable input, because `revokeToken` differs between the two only when handed a
falsy token. Either mutation ALONE is caught. This is recorded rather than
papered over: contorting a test to kill an equivalent mutant would be the lie.

## Resume here — the rest of B2

The Data page today draws the table, the columns, the fold switch and the bound.
Four capabilities of the engine's page are not in it yet. Build them in this
order, and the order is reasoned:

1. **The details drawer — `GET /api/offer/{key}/{id}`.** Least entangled, and it
   touches nothing the panel uses, so it proves the pattern on a second endpoint
   at no risk. The endpoint was BUILT for this: its docstring says *"for the
   panel the Data page opens INLINE"*. Note its ownership rule — an offer that
   is not this source's answers 404 **without confirming the id exists at all**.

2. **Choose-Columns — `GET`/`POST /api/fields/{key}`.** **Do not write a second
   one.** The panel already has the whole thing: `loadSourceColumns`
   (`extension/app.js:1579`) and `saveSourceColumns` (`:1618`), speaking the same
   bodies — `{field_key, hidden}`, `{order}`, `{reset: true}`. EXTRACT it into a
   shared module the way `backend.js` was extracted, or the two surfaces will
   disagree about how a column is saved. It touches the panel, which is why it
   comes after the drawer and not before.

3. **Saved views — `POST /api/views/{key}`, `DELETE /api/views/{id}`.**

4. **Promotion — `GET`/`POST /api/promotable/{key}`.** Its contract was not read;
   read it first.

**And when all four are in, remove the workbook link from the source card.** It
sits beside the new action deliberately: the engine's page still has these four,
and taking them away before the replacement carries them would be a downgrade
wearing the word "migration".

### A decision the owner owes on (3)

B1 lists `DELETE /api/views/{id}` among nine dead routes to delete. Building saved
views **revives it**. So either B1 loses that line, or the new page cannot delete
a saved view. A saved view that cannot be deleted is a defect, not a feature — but
it is the owner's call, and B1's list should be edited rather than quietly
contradicted.

**HELD, 2026-08-16.** The owner has comments on B1 itself and will raise them
first. Do not start step 3 until he has.

## Named gaps, not forgotten

- ~~**No DOM test for the Console.**~~ **CLOSED.** `tests/test_console_dom.py`
  renders `console.html` for real — ten tests, every one of them broken
  deliberately first to prove it fails. It could NOT be built the way the Data
  page's was: the Console's fourteen modules declare **nineteen colliding
  top-level names** between them (six rule modules each declare `finding`, `text`
  and `same`; two declare `SHEETS`), so flattening them into one scope is a
  SyntaxError before a line runs. It is served over http and loads its real
  module graph instead — the stronger arrangement, and the one to copy next time.

  What it found: `showView("inspect")` is the LAST line of `showTable`, so a
  throw anywhere above it means pressing a table does **nothing at all** — the
  sections are built into a view that is never revealed. No error, no half-drawn
  page, no clue.
- **`behaviourVersion` is ScrapeX's own bookkeeping, not a signal.** mbiXaddin has
  no such field; both numbers live here and one commit raises both. The real fix
  is `docs/HANDOFF-mbiXaddin-contract-producer.md`. What DOES look upstream is
  `test_no_cited_addin_file_has_moved_since_the_reading`, which watches the `.cs`
  files the reading cites and found three already moved.
- **`scrapex/version.py` has not moved** through any of this. The capability gate
  is green either way, and #190 set the precedent by not moving it. But *"the
  crawl falls back to product pages when the Store API refuses"* is exactly the
  kind of thing the owner asks *"does my build do that?"* about — which is the
  failure `tests/test_version.py`'s own docstring says the ledger exists to
  prevent.

  **RULED, 2026-08-16: it moves with every new commit.** Not "per user-visible
  capability", which was the old rule and left the judgement to whoever was
  writing — and who kept deciding no. Every commit on `main` is one squashed
  pull request here, so the rule reads: **every merged PR raises VERSION, and
  regenerates the baseline and CHANGELOG in the same commit.**

  **Measured, because the owner said it had never moved and he was right.**
  `git log -G'^VERSION = "'` names three commits in the project's whole life:
  `7ca7a75` created the ledger, `9a0d399` cut 0.2.1, `adf31b2` cut 0.2.2 on
  10 August. **48 commits since** — Phase A entire, T1, B2 — with the number
  standing still. (`-S` finds only one of the three: 0.2.1 → 0.2.2 leaves the
  count of the searched string unchanged. Use `-G` on this file.)

  ### It is NOT just a bump, and this is the blocker

  Raising VERSION to 0.2.3 was tried on 2026-08-16 and reverted the same day.
  Two things happened, and the second is the reason it needs its own PR.

  **The ledger's own guard fired, correctly.** `robots_per_source` is dated
  0.2.2 and cited no commit, and a capability older than the build must cite the
  work that built it. Read out of `git log`, not remembered: both
  `-S"crawl_obey_disallow"` and `-S"source-edit-robots"` name `adf31b2` alone,
  so the setting, the panel control and the ledger line landed together. Write
  `commit="adf31b2"` as part of that PR.

  **THE ENGINE ADVERTISES A NUMBER IT CANNOT KNOW.** `version_report` sends
  `"latest_extension_version": VERSION` (`scrapex/version.py:484`, and again in
  `scrapex/webui/app.py:1355`), so the moment the engine moves ahead of
  `extension/manifest.json` the panel draws *"This ScrapeX extension is older
  than the engine it is talking to"*. Measured at 320x440: the profile page's
  legal line went from 396 to 494 against a 440 viewport — 54px clipped, caught
  by `test_the_signed_in_profile_starts_at_the_top_and_still_fits`.

  Under "bump every commit" that notice becomes PERMANENT and FALSE.

  It is a leftover from before the release paths were unwelded. PLATFORM-PLAN
  Decision 21 (done 2026-08-05, PR #112) is explicit — *"the extension can be
  tagged for the Chrome Web Store, **or** the engine tagged for GitHub Releases,
  with the other number untouched"*, and *"Google reviews the extension and does
  not review the engine"*. #112 unwelded the numbers and CI and left the REPORT
  welded. Three constants still speak the old model: `latest_extension_version`,
  `LATEST_SOURCE` (*"it ships with the extension"*, `:289`) and
  `UPDATE_INSTRUCTIONS` (*"it carries the new extension with it"*, `:292`).

  **The remedy, ruled 2026-08-16: the engine keeps the GATE and drops the
  ADVERT.** `MINIMUM_EXTENSION_VERSION` is a fact the engine owns and is derived
  from the ledger — it stays. "What is the newest extension available" is
  Chrome's answer, not the engine's — it goes, with the two sentences that say
  the engine carries the extension. Then VERSION moves every commit and no false
  card appears, because the floor has not moved.

  **Do NOT instead bump `extension/manifest.json` alongside VERSION.** That
  re-welds precisely what #112 unwelded and breaks its stated "Done when".

  Its own PR. Add a guard that fails if the engine ever answers for the
  extension's head again.

## Phases not started

**B1** (delete pure duplication and the dead routes) · **B3** (Storage and
Retention — the destructive half; every safety interlock moves WITH its control,
not after it) · **B4** (the rest, cheapest first) · **B5** (one navigation source
instead of three) · **B6** (the engine's new face: tray icon and a log window).

**Phase C** stays deferred: `127.0.0.1` cannot go until the extension can read
SQLite itself (**DEC-1**, wa-sqlite + OPFS), and jobs cannot move while the
heartbeat is broken under load (**T2**).
