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

`design/` is **canonical**. `extension/components.css`, `extension/icons/`,
`scrapex/webui/static/components.css` and `.../material-icons/` are **distributed
copies**, published by `tools/sync_design_assets.py` and asserted byte-equal by
`tests/test_vendor.py` and `tests/test_design_system.py`.

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

Still open (UI-2b): the tone and text duplication — `color:var(--muted);
font-size:var(--fs-xs)` in 14 places across 5 files, the amber tone in 8, and
page rules that re-implement `.row`/`.cluster` instead of using them. Those need
a naming decision, not a mechanical move.

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
