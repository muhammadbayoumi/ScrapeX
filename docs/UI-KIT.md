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
| Defined but referenced by no markup found | ~167 *(advisory — the detector is naive about JS)* |

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

Before writing a new class, this is the list. All of it lives in
`design/components.css` and works on both surfaces.

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

### UI-1 · The catalogue that cannot go stale

Nobody reuses what nobody can see. §5 above is a start, but a **hand-written
list goes stale the first week**. Build a gallery page that renders every shared
component with its markup, and a guard that fails when a component exists in
`design/components.css` and not in the gallery. Then §5 becomes generated, and
"look before inventing" becomes a link rather than a hope.

### UI-2 · Promote what repeats, delete the copies

Fourteen page-specific stylesheets re-implement the same patterns. Measure the
duplication concretely — same declarations under different names — promote what
is genuinely shared into `design/components.css`, delete the copies. **After
UI-1**, because promoting a component into a catalogue nobody can see just moves
the problem.

### UI-3 · Retire dead CSS with proof

~167 candidates. The detector is naive about JS template literals, so every
candidate is verified against markup, JS and templates before deletion — a class
deleted while a code path still builds it is an invisible regression, which is
the same failure as an undefined class in the other direction. **Last**, because
UI-2 will delete a large share of them as a side effect, and measuring twice is
cheaper than deleting twice.

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
