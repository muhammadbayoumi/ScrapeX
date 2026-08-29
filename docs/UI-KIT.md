# The UI kit — one place to look before inventing

*Written 2026-08-05, after shipping two buttons styled by classes that do not exist.*

---

## 1. Why this document exists

On 2026-08-05 I added an Install button written `class="btn icon-btn"`. Neither
name is defined in any stylesheet in this repository. The codebase already had
`ghost`, `icon-button` and `compact` — the exact three primitives I needed. The
buttons rendered unstyled, every gate stayed green, and the mistake was found by
looking at the page with human eyes.

That is not a personal lapse to apologise for; it is a **structural gap**, and it
will keep happening to every agent and every future session for the same reason:

> There is no place to look, and nothing that objects when you don't look.

The owner named it exactly: *«مش كل مرة ننتج حاجة جديدة ونخترع ونقعد نعدل»* —
stop inventing something new every time and then editing it forever.

## 2. What the UI is actually made of, measured

Counted on 2026-08-05, before any of the work below:

| | |
|---|---|
| Stylesheets | **18** |
| Distinct class names defined | **994** |
| Shared across both surfaces (`design/components.css`) | **98** |
| Statically resolvable class uses in markup | **647** |
| **Used in markup, defined in no stylesheet** | **17** |
| Defined and mentioned nowhere outside a stylesheet | **28** — and only **8** of those were dead; see UI-3 |

Of the 17, **sixteen were dead attributes** carrying meaning that no rule ever
gave them:

- `dataset-group` sitting beside a JS hook that actually reads `[data-dataset-group]`
- `class="primary"` on a button whose base rule is already the primary style —
  toggled in JavaScript for years with nothing behind it
- `my-1`, a utility class from a framework this project does not use
- `appearance-page-heading`, `finance-page-heading`, `source-choice-file`,
  `verdict`, `sync-automation`, `overview-*-panel`, `dataset-identity`, and the rest

**One was real**: `tabs`, used by `nav.tabs button[data-view]` in `app.js`, the
DOM tests and the screenshot tool. It moved to `side-rail` — the class already
on the same element, which is a real rule.

## 3. The rule

> **`class` is for styling.** Every class in markup must resolve to a rule in a
> stylesheet the page loads.
>
> **JavaScript hooks and test selectors use `data-*` or `id`.** They are not
> styling and must not borrow the attribute that is.

`tests/test_ui_kit.py` enforces this. It fails with the class name and the file
it is in. `ALLOWED_WITHOUT_A_RULE` is **empty on purpose** — it was emptied when
the rule was written, and adding to it is a decision that must carry a written
reason, which a second test checks.

**What the guard does not cover, stated rather than implied:** a class added by
JavaScript never appears in markup, so `is-rail-active`, `is-open` and their kind
are invisible to it. That gap is real. It is not closed by pretending otherwise.

## 4. Where a rule belongs

| Scope | File | Test |
|---|---|---|
| Used by both the panel and the web UI | `design/components.css` | any surface |
| Design tokens (colour, spacing, radius, type) | `design/tokens.css` | any surface |
| Belongs to one screen of the panel | `extension/app.css` | one view |
| Belongs to one page of the web UI | `scrapex/webui/static/pages/<page>.css` | one page |

`design/` is **canonical**, and `tools/sync_design_assets.py` is the single source of the
copy map — **nine sources into eighteen destinations**. Read the tool rather than a list
restated here; a restated list goes stale, and this one had.

**The two copies this sentence used to omit are the ones that matter most.**
`design/tokens.css` is the file [R-74](RULINGS.md#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour)
rules on, and it is published to `extension/tokens.css` and
`scrapex/webui/static/tokens.css`; neither was named. `appearance.js`, `split-button.js`
and `timezone.js` are copied too. All are asserted byte-equal by `tests/test_vendor.py`
and `tests/test_design_system.py`. Corrected 2026-08-29 by
[REQ-49](REQUESTS.md#req-49--review-the-design-system-against-supabases).

**Editing a copy is the second mistake I made on 2026-08-05.** Edit `design/`,
then run:

```bash
python tools/sync_design_assets.py
```

## 5. The vocabulary that already exists

**Open `design/gallery.html` in a browser.** No server, no build, no engine —
double-click it. Every component below is on that page as a live example with
its markup beside it, in both themes, and
`tests/test_ui_kit.py::test_every_shared_component_is_in_the_catalogue` fails
the moment a component exists in the sheet and nowhere on that page.

The list below is the index. The page is the truth.

**Buttons** — the bare `<button>` element is already the filled primary style.
Compose, do not invent.

| Class | Effect |
|---|---|
| *(none)* | filled primary |
| `ghost` | outlined, regular weight |
| `icon-button` | square at the full touch-target size |
| `compact` | shorter, smaller type |
| `icon-button compact` | **small** square — added 2026-08-05, because the two together drew a rectangle |
| `split-button` + `split-button-primary` / `-trigger` / `-menu` / `-option` | an action with a menu beside it |

**Surfaces** `card` · `card hi` · `card warn` · `banner` · `grid` · `row` ·
`stack` · `cluster` · `srow` · `section-header` · `page-header` · `page-title` ·
`page-heading` · `page-eyebrow` · `page-description` · `page-actions`

**State and emphasis** `badge` · `chip` · `dot` · `ok` · `err` · `warn` ·
`info` · `danger` · `accent` · `amber` · `muted` · `on` / `off` · `is-active` ·
`hidden` · `empty` · `promise`

**Text** `tech` (monospace value) · `code` · `num` · `name` · `small` ·
`text-sm` · `text-xs` · `text-block` · `visually-hidden`

**Icons** `sx-icon` (1.25rem, `currentColor`) · `sx-icon sm` (1rem) ·
`inline-icon` · `icon-label`. Every symbol comes from
`design/material-icons.svg`; a reference to a missing id renders an invisible
control on a button that is still clickable, and `tests/test_vendor.py` checks
every one.

**Source identity** `source-identity` and its parts — the bilingual name block
used wherever a source is named.

## 5b. Naming a page

> **A page name is singular, and it is a name — not a sentence.**

The rail is read at a glance with the names under one another. One plural among
singulars reads as a different *kind* of destination — a list rather than a
place — and the panel has both, so the difference has to mean something.

Two names moved when the owner stated the rule on 2026-08-05:

| was | is | why |
|---|---|---|
| `Engines` | **`Engine`** | plural |
| `Add or edit sources` | **`Library`** | a sentence, not a name. `Source` next to it does something else — it checks a page and adds it — so the manager needed its own word rather than a plural of that one. |

**One declared exception: `Settings`.** The singular `Setting` means one setting,
or a scene, and is broken English for a page holding dozens; every product that
has this page writes it plural. The exception lives in
`tests/test_panel_dom.py::PLURAL_PAGE_NAMES_ALLOWED` and carries that reason —
a second test fails if any entry there is a bare name.

`tests/test_panel_dom.py::test_every_page_is_named_in_the_singular` enforces the
rule, and a companion asserts the rail button and its page heading are the same
word. That companion keys on the `.view-heading` block rather than a list of
exemptions, so Welcome — deliberately a greeting and a button, with no title at
all — is out of scope, and any page that later GAINS a title is checked from
that moment with nobody having to remember to remove it from a list.

## 6. The plan, and why in this order

The owner asked for the order I actually recommend rather than the one he
listed. This is it, and the reasoning is that **each step makes the next one
cheaper, and the first one stops the bleeding today**.

### UI-0 · Make an unresolvable class a failing test — *done, this PR*

The rule, the guard, and the 17 fixed. First because it costs one test file and
converts an invisible problem into a loud one. Everything after it is safe to do
in any order without silently regressing.

### UI-1 · The catalogue that cannot go stale — *done*

`design/gallery.html`, opened by double-clicking it. Every shared component as a
live example with its markup, both themes, and a guard that fails when a
component is in the sheet and not on the page.

> **"Cannot go stale" is stronger than the mechanism.** Measured 2026-08-29 by
> [REQ-49](REQUESTS.md#req-49--review-the-design-system-against-supabases): the sprite half
> of it is a **gate, not an assertion** — `tools/sync_design_assets.py` regenerates the
> block only `if` its marker comment is present, so tampering with the block is caught and
> tampering with the block *and* renaming the marker passes, after which the tool reports
> the catalogue current forever. And the component check is name-level, not compound-level:
> a variant that exists only as a compound selector has no live example and nothing says so.
> `OP-107`. The claim is true of the common case and it is not a guarantee.

**Building it found four things reading the CSS never would have.** Each is now
written on the page beside the component it belongs to:

- `split-button-menu` is a `<details>`, not a `<div>` with a button beside it.
  Written the other way — which is how I wrote it first — it renders a collapsed
  box with no chevron and options overlapping the page, because every rule is
  written against `summary` and `[open]`.
- `brand-logo` is an **empty `<span>`** with a CSS mask, not an `<svg>`.
- `components.css` uses `--brand-mark` and does not define it. Each surface
  points the token at its own copy of the asset, so a new surface that loads
  the shared sheet and forgets the token gets a **solid black square** — and one
  that sets it to an unreachable file gets an invisible element. Neither looks
  like a missing token; both look like a broken component.
- A `file:` page is its own opaque origin and can load **neither** an external
  `<use href="sprite.svg#id">` nor a CSS mask image. Both are embedded into the
  catalogue by `tools/sync_design_assets.py` and stale-checked like every other
  distributed copy.

A fifth came from the guard rather than the page: `href="#add"` reads as a
three-digit hex colour, so the colour-literal guard in `tests/test_vendor.py`
flagged a sprite reference. Every other page reaches the sprite through a path,
which is why it had never been seen. The guard now ignores fragment references
and still bites on a real literal.

**And a sixth came from a defect the owner photographed** (`REQ-30`, 2026-08-22),
which is the one that concerns anyone PLACING this component: `.split-button-options`
carries `z-index: 120`, and **a consumer that gives the `.split-button` wrapper a
z-index of its own throws that away.** Any numeric z-index on a positioned element
makes it a stacking context, so the menu's 120 is then only compared with its
siblings inside the wrapper. On a list of cards every wrapper tied at `1`, and each
card's button painted through the menu of the card above — the same `⋮` twice on
one screen. Place the wrapper with `position` and offsets alone where you can; where
a layer really is needed, raise it to `var(--z-overlay)` **only while the menu is
open** (`:has(.split-button-menu[open])`), the way `.source-filter-menu[open]` does
in `webui.css`. Raising the 120 does not help and cannot: measured at 1200 and at
2147483647, the card below still won.

### UI-4 · There is no overflow-menu component, and two screens invented one — *gap*

Found 2026-08-22 from `REQ-36`. A `⋮` that opens a menu and has **no
primary action beside it** now exists twice, built two different ways:

| where | built from | how it looks |
|---|---|---|
| Profile, per account row | `button.icon-button.compact` + `.account-menu` positioned in JS | 40px circle, transparent, `--muted` |
| Data, per source card | `.split-button` + `<details>`, with the primary half simply absent | was 48px, `0 8px 8px 0`, filled, bordered, shadowed |

The second is the one he called unprofessional, and the cause is structural rather
than cosmetic: **`.split-button-trigger` is dressed for the half that was not there.**
Its radius is flat on the inner edge because a primary button normally butts against
it. Used bare it draws a lopsided box.

The card's trigger is now brought to the profile row's treatment by rules local to
`.dataset-card` in `extension/app.css`, which is the smallest honest fix and touches
no distributed copy. **What is still missing is the component**: an overflow menu is
a real, repeating need — a trigger with no primary, a menu anchored to it, and the
open/close/aria/escape behaviour `split-button.js` already implements. Promoting one
would let both screens delete their local dress, and it is the same argument §UI-2
makes for `.icon-tile`.

**Two things to keep if it is promoted.** The profile menu is anchored to the CARD
and not to its row, because the rows live in an `overflow-y: auto` scroller that
clips a menu positioned inside one — measured at 61px cut off at 320px. And the
card's menu must keep the stacking fix from §UI-1: a wrapper with a numeric z-index
traps the menu's own z-index inside it.

### UI-2 · Promote what repeats, delete the copies — *first slice done*

**Measured**: 67 declaration blocks are written identically in more than one
sheet. The largest single component was an icon in a tinted square, written
**three times** across Exports, Sync and Overview — fourteen elements, six
identical declarations each, only the size differing. It is now `.icon-tile`,
with the size a custom property the caller sets. Page stylesheets lost 38 net
lines.

**The proof matters more than the change.** `tools/style_snapshot.py` records
the computed style of every element on all 24 pages — panel and workspace,
24,972 elements — and diffs two snapshots. After the promotion: no computed
style changed anywhere.

*Screenshots could not have proved it.* Eight of the workspace's 28 pictures
differ between two consecutive runs with no code change, because four pages
print times and the text moves. A pixel diff there reports a difference that is
not one, which teaches the reader to ignore the tool.

It caught two mistakes of mine that every other gate passed: an edit anchored
on a selector in the MIDDLE of a four-name list, which silently orphaned
`.overview-snapshot-icon` and stripped four tiles on the Overview page; and a
class left in markup after its only rule was deleted. **Anchor a CSS edit on
the whole rule, never on a name inside it.**

**What is left, and why most of it should stay.** 63 declaration blocks are
still written identically in more than one sheet. I measured them and then did
*not* refactor them, which needs saying plainly:

- `background:var(--accent-weak); color:var(--accent-ink)` — 15 places, 10
  sheets, and its amber twin in 9 places across 7. These are **not one component
  written fifteen times**. They are one *tone* applied to fifteen different
  things: a chip, a badge, a dot, a key badge, a hover state, a status
  indicator. Two token references is already the shortest way to say "this is in
  the positive tone", and a `.tone-accent` class cannot be added to a `:hover`
  rule at all. Extracting it would buy indirection and nothing else.
- `color:var(--muted); font-size:var(--fs-xs)` — 14 places, 5 sheets. Almost all
  of them are **element** selectors (`.card small`, `dt`, `p`), not classes on
  an element, so "use the shared class" would mean adding a class to a hundred
  tags. What was genuinely missing was a name for the smallest size:
  `--fs-2xs` had a token and no class, so seven rules wrote it by hand.
  `.text-2xs` now completes the scale — it does not remove those seven, and it
  stops the eighth from inventing a name.

The rule that came out of this: **duplication is worth removing when the same
COMPONENT is written twice, and not when the same two declarations happen to
describe two different things.** `.icon-tile` was the first kind. The tone pairs
are the second.

### UI-3 · Retire dead CSS with proof — *done*

An earlier count of "~167 dead rules" in this document was **wrong**, and wrong
in the dangerous direction. It came from a detector that only looked at markup
and a few JavaScript shapes. `tools/dead_css.py` applies a deliberately crude
and deliberately conservative rule instead — *a class is a candidate only if its
name appears nowhere in the repository outside a stylesheet* — and found **28**.

Twenty of those twenty-eight were alive: eighteen `tabulator-*` names the grid
library writes at runtime, and two `schedule-state-*` names a template builds by
concatenation. Deleting any of them would have broken a page that every test
still passes on. They are now named in the tool with the reason, so the report
is signal rather than a list of traps.

**Eight were genuinely dead**, each removed from the markup in a past redesign
with its rule left behind — `runline`, `picklist`, `step-n`, `step-body`,
`ms-2`, `action-subtle`, `record-selection-kicker`, `sync-run-form`. The commit
that orphaned each is named beside it in the deletion. `picklist` went while its
`pickrow` children stayed, which is why only the one name was removed.

Zero candidates remain, and the style snapshot confirms no computed style
changed. The tool stays a **report, not a gate**: it cannot see a class built by
string concatenation, so deleting what it names still needs a human to look.

### Where this sits against the product plan

`docs/PLATFORM-PLAN.md` runs M0–M8. UI-0..UI-3 belong **between M0 and M1**:
M1 (sign-in), M2 (backup/lease) and M3 (the bare-extension view) are page-heavy
milestones, and every page built before the kit exists is a page that will be
rewritten after it.

## 7. Adding a component

1. **Look in §5 and the gallery first.** Composition beats invention: `ghost` +
   `compact` + `icon-button` is three existing rules, not a fourth new one.
2. If it is genuinely new, decide its scope from the table in §4.
3. Write it in `design/components.css` if shared, then
   `python tools/sync_design_assets.py`.
4. Use tokens, never literals — `var(--sp-3)`, not `12px`; `var(--surface)`,
   not `#fff`. A literal is a rule that will not follow the theme, and the
   panel has a light and a dark one.
5. If JavaScript or a test needs to find the element, give it `data-*` or `id`.
   Not a class.
