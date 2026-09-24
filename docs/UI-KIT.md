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
| Defined and mentioned nowhere outside a stylesheet | **28** — and only **8** of those were dead (`tools/dead_css.py` says why) |

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
copy map. Read the tool rather than any restatement here — **a count is a restatement too**,
and the one that stood in this sentence went stale exactly as the sentence warned.

**The two copies this sentence used to omit are the ones that matter most.**
`design/tokens.css` is the file #1040 rules on ([R-74](archive/RULINGS.md#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour)
before it), and it is published to `extension/tokens.css` and
`scrapex/webui/static/tokens.css`; neither was named. `appearance.js`, `split-button.js`
and `timezone.js` are copied too. All are asserted byte-equal by `tests/test_vendor.py`
and `tests/test_design_system.py`. Corrected 2026-08-29 by
[REQ-49](archive/REQUESTS.md#req-49--review-the-design-system-against-supabases).

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

## 6. Adding a component

1. **Find the Supabase atom, fragment or pattern at the pin first**
   ([the source rule](DESIGN-SYSTEM-SOURCES.md), #1040). Take its values, its icon size
   and stroke, and its motion from it, not from what this repository already has.
2. **Then look in §5 and the gallery.** Composition beats invention: `ghost` +
   `compact` + `icon-button` is three existing rules, not a fourth new one. Only when the
   gallery does not have it is something added: transcribed from what step 1 found, and
   treated as a gap (studied, not invented) when it found nothing. Decide its scope from
   the table in §4.
3. Write it in `design/components.css` if shared, then
   `python tools/sync_design_assets.py`.
4. **Delete the copies it replaces by the whole rule**, first selector to closing
   brace, never by a name inside a selector list: an edit anchored on a unique tail
   re-attaches the names above it to the next rule. Remove only the name you mean,
   then prove nothing moved with `python tools/style_snapshot.py --diff`.
5. Use tokens, never literals — `var(--sp-3)`, not `12px`; `var(--surface)`,
   not `#fff`. A literal is a rule that will not follow the theme, and the
   panel has a light and a dark one.
6. If JavaScript or a test needs to find the element, give it `data-*` or `id`.
   Not a class.
