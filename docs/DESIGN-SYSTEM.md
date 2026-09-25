# ScrapeX Design System

## 0 · The design system is Supabase's at the pinned commit; where Supabase is silent, a named official source governs

**This is the first thing to read here.** The ruling is #1040. It corrects
[R-74](archive/RULINGS.md#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour)
and [R-85](archive/RULINGS.md#r-85--the-system-is-supabases-exactly-and-supabase-is-the-only-colour-choice),
which stay in the archive as the rulings it replaced, not as the rule.

1. **Supabase governs everything it specifies**, at the value layer and the component
   layer: colours, component shapes and sizes, patterns, motion, focus geometry, icons and
   copy. The basis is commit `86c813ec`, the one `design/supabase.NOTICE.txt` pins. It
   does not govern the implementation layer (React, Radix, Tailwind, a build step): what a
   Supabase value or class string says is transcribed into CSS. **Anything that differs is
   corrected, even where an earlier ruling or decision allowed it.** Where an atom's value
   comes through Tailwind,
   [the source rule](DESIGN-SYSTEM-SOURCES.md#tokens-and-visual-implementation) says which
   value that is.
2. **A conflict exists only where Supabase specifies something different.** Where it is
   silent, nothing is deleted. Every named gap is listed once, with the sources it is
   studied against and its issue, in
   [the source rule](DESIGN-SYSTEM-SOURCES.md#gap-sources-studied-not-adopted). R-85's
   Arabic exception (§4b) is now one of those gaps.
3. **No second source is chosen for anything Supabase covers.** A Supabase value that
   fails WCAG ships for now. A different source enters only when he asks for a specific
   change, by a mandate as narrow as that request, recorded on its issue and under
   [Mandates](DESIGN-SYSTEM-SOURCES.md#mandates).
4. **The basis is re-pinned only deliberately**, at the start of a phase, through #1018's
   gate, and it never tracks master. The live site follows master and is illustrative only.

**`design/tokens.css` carries Supabase's values, and `design/components.css` its component
anatomy.** Where either differs today, an open issue says so. Neither is yet Supabase's on
every axis, so read the design-system milestones before treating a value as theirs.

**What stays from the earlier rulings:**
- There is one colour choice. Its id stays `supabase`, and #740 changes its label to ScrapeX.
  `whatsapp`, `brand`, `github` and `blue` survive in `design/appearance.js` only as
  aliases resolving to `supabase`, so a preference stored before R-85 still opens.
- A palette entry may contain nothing but colour, enforced by
  `tests/test_a_palette_may_change_nothing_but_colour.py`. Read `OP-102` before adding one.
- Components consume semantic roles, never a palette identifier
  ([R-59](archive/RULINGS.md#r-59--the-palette-registry-brand-is-default-alternatives-is-extensible-teal-is-debt)
  decision 4).

---

ScrapeX has one authored visual system shared by the browser extension and the
local web workspace. `tools/sync_design_assets.py` is the single source of the copy map,
and it is the file to read rather than any list restated here — **a count is that same
restatement in miniature**, and the one that stood in this sentence went stale exactly as
the sentence warned. The three that carry the rules:

- `design/tokens.css` — semantic colour, type, spacing, shape, elevation,
  control, motion, and layering tokens. **This is the file #1040 rules on** (`R-74` before
  it), and it is
  copied byte-for-byte to `extension/tokens.css` and
  `scrapex/webui/static/tokens.css`.
- `design/components.css` — reusable controls, cards, banners, lists, badges,
  layout helpers, icon sizing, focus treatment, and accessibility utilities. Copied to
  `extension/components.css` and `scrapex/webui/static/components.css`.
- `design/material-icons.svg` — the curated Google Material Icons sprite.

`design/` holds ten files, not three; the other seven are `appearance.js` (the palette
engine), `gallery.html` (the catalogue), `split-button.js`, `timezone.js`, the Material
licence text, `google-g.png` and `x-mark.svg`.

The extension and the Python package need physical copies of these files
because they ship independently. Never edit those generated copies directly:

```powershell
python tools/sync_design_assets.py
python tools/sync_design_assets.py --check
```

## Principles

1. **Semantic tokens first.** Components consume `--surface`, `--text`,
   `--accent`, `--control-height`, and similar intent-based values rather than
   page-specific colour literals.
2. **Shared behavior is a component concern.** Hover, active, focus-visible,
   invalid, and disabled states live in `components.css`. A page stylesheet
   should normally contain layout only.
3. **Theme-aware by default, and two of these are gaps rather than departures.**
   Light, dark, increased-contrast, reduced-motion, forced-colour, touch and
   keyboard states are all part of the core system. Light and dark are Supabase's.
   **Supabase is silent on `forced-colors` and `prefers-contrast`**: searching its
   repository for either returns nothing. So both blocks stay, recorded in the
   statement of changes in `design/supabase.NOTICE.txt`, and they are studied as
   [the gap table](DESIGN-SYSTEM-SOURCES.md#gap-sources-studied-not-adopted) says.
   **Reduced motion is Supabase's**: it honours `prefers-reduced-motion` in fourteen
   places. What it leaves unguarded is a gap, in the same table.
4. **English chrome, any-language data.** Scraped values use `.content`,
   `.name`, or `dir="auto"` so bidirectional text is isolated correctly. Supabase is
   silent on bidirectional text, so this is a gap, studied in #1073 against the sources
   [the gap table](DESIGN-SYSTEM-SOURCES.md#gap-sources-studied-not-adopted) names.
5. **Use native semantics first.** Real buttons, links, labels, fieldsets,
   tables, tabs, and dialogs are preferred; ARIA augments them only where the
   native element cannot express the interaction.
6. **Icons are Lucide 0.436.0, and the Material sprite is a known conflict, not a
   departure.** Supabase's icon set is Lucide (`packages/ui/package.json@86c813ec:28`,
   `^0.436.0`, resolved by `pnpm-lock.yaml@86c813ec:2576-2578`), at Lucide's root
   defaults: stroke 2, `currentColor`, fill none. The exception is an atom that sets
   an icon's size or stroke itself: `packages/ui/src/components/Button/Button.tsx@86c813ec:127-133`
   sizes by button size, and `packages/ui/src/components/shadcn/ui/select.tsx@86c813ec:62`
   draws its chevron at `strokeWidth` 1.5. Size 24 with `strokeWidth` 1.5 is the default
   of Supabase's own custom icons (`icons.mdx@86c813ec:48`, under *Custom icons*), not of
   Lucide. Until #1057 moves the product to Lucide, reuse a symbol from the Material
   sprite rather than embedding an SVG path or drawing a replacement.

## Copy

Supabase's copywriting page governs the words (#1040):
`apps/design-system/content/docs/copywriting.mdx@86c813ec`. Read it before writing or
reviewing any user-facing text.

- **Page names are title case**: the rail and Console items, their accessible names and
  tooltips, and each page's `h1` (`copywriting.mdx@86c813ec:128-130`, `:232`).
- **Section labels and in-page headings are sentence case** (`:140-146`, `:231`).
- **A loading state names what is happening**: "Saving changes…", never "Please wait…",
  "Processing…" or a bare "Loading…" (`:180-191`).
- **No marketing words**: "easily", "simply", "powerful" (`:215-219`).
- **Spelling stays as it is.** Supabase's U.S. English rule does not change ScrapeX copy
  (#1040, recorded in the source rule).

`tests/test_the_interface_words_follow_supabases_copywriting.py` checks those four
mechanically, over the panel's HTML and JavaScript and the web UI's templates. Today's
offenders are listed there by name, and the list only shrinks; #1071 and #743 fix them. The
rules that need judgement are the review's, not the test's: declarative page descriptions,
headings that describe the page, empty states that name the next action, confirmations that
state their consequence, active voice, and specific verbs.

## Token groups

| Group | Examples |
|---|---|
| Surfaces and text | `--bg`, `--surface`, `--surface-raised`, `--line`, `--text`, `--muted` |
| Brand and status | `--accent`, `--accent-ink`, `--amber`, `--red`, `--focus` |
| Controls | `--button-bg`, `--button-hover`, `--control-bg`, `--control-height` (40px) and `--control-height-sm` (32px). **Neither is on Supabase's scale**, which is 26/34/38/42/50 (`packages/ui/src/lib/constants.ts@86c813ec:61-65`); #1050 moves them. `--touch-target` survives for the places that size for touch deliberately |
| Spacing | `--sp-0` through `--sp-8` on a 4 px base |
| Shape and elevation | `--radius-xs` through `--radius-pill`, `--shadow-xs` through `--shadow-lg` |
| Typography | `--font`, `--font-mono`, `--fs-2xs` through `--fs-2xl`, weight and line-height tokens |
| Motion and layering | duration/easing tokens and `--z-sticky`, `--z-overlay`, `--z-modal` |

If a recurring need cannot be represented by an existing token, add one
semantic token to the canonical file. Do not create a page-local colour system.

## Reusable primitives

- Buttons: default primary, `.ghost`, `.danger`, `.link`, `.icon-button`,
  `.compact`, and `.sect`.
- Inputs: text controls, selects, textareas, checkboxes, radios, invalid and
  disabled states.
- Containers: `.card`, `.banner`, `.empty`, `.stack`, `.cluster`, and `.grid`.
- Status and data: `.chip`, `.badge`, `.dot`, `.srow`, `.content`, and `.num`.
  (**This list said `.source-row`, which is not a shared primitive** — it resolves only in
  the extension's own stylesheets. The shared name is `.srow`. Corrected 2026-08-29.)
- Accessibility: `.visually-hidden`, consistent `:focus-visible`, coarse
  pointer sizing, reduced-motion fallbacks, and forced-colour fallbacks.

Tables use `static/table-theme.css`. Tabulator maps to the same table vocabulary
through `static/grid-theme.css`; renderer-specific overrides stay there.

## Material icons

The sprite is sourced from
[`google/material-design-icons`](https://github.com/google/material-design-icons)
and retains its Apache 2.0 notice in
`scrapex/webui/static/material-icons/material-icons.LICENSE.txt`. **The path in this
sentence used to read `LICENSE.txt`, which does not exist**; all three copies do
(`design/`, `extension/icons/`, `scrapex/webui/static/material-icons/`) and two of the
three are guarded. Corrected 2026-08-29 by `REQ-49`.

**The Supabase obligation is discharged, and this paragraph said the opposite for two
days.** `design/tokens.css` carries values traceable to `github.com/supabase/supabase` —
Apache-2.0 at the root, MIT for the `packages/ui` they came from — and since 2026-09-04
`design/supabase.NOTICE.txt` carries both licences, pins the source commit `86c813ec`,
names the files the values came from, and states the changes Apache-2.0 §4(b) asks for. It
is synced to `extension/` and `scrapex/webui/static/` like every other design asset.

What was open until 2026-09-07 was not the notice's absence but its accuracy: **four of
its five colour entries were false**, because `R-85` restored `--line-strong`, `--amber`
and `--focus` to Supabase's own values and deleted the device path the fourth described.
**And the fifth was never a departure either**, which took a further review pass to find:
`--accent-contrast` ships Supabase's own `--primary-foreground` resolved — `oklch(0.1 0 159)`
= `#030303` in light and `oklch(0.19 0.00225 159)` = `#131413` in dark, from the scalars
their own theme files declare. **No colour value in `design/tokens.css` is a deliberate
departure**; every one belongs to *resolved, not copied*.

`tests/test_the_notice_describes_the_values_it_ships.py` now pins those five values and
asserts the harder thing — that the tokens the notice **names** as replaced are exactly the
tokens the guard pins — because the failure was never a value moving. It was a value moving
while the notice kept its old sentence. **What that guard does not do is assert every value
borrowed from Supabase**; that is the wider gap, and it is open.

Use an icon decoratively with an adjacent visible label:

There are **three** real forms, and the difference is not cosmetic. The extension has no
`/static/` root, so an absolute path there resolves to nothing. And the Side Panel may
not point into another file at all: since Chrome 150 a `<use>` that does holds the
panel's `load`, and the panel stays blank until a click somewhere else (issue #1110).

```html
{# web workspace: the macro carries the cache-buster #}
{{ icon('settings') }}

<!-- the Side Panel, extension/app.html: a symbol the page carries itself -->
<svg class="sx-icon" aria-hidden="true">
  <use href="#icon-settings"></use>
</svg>

<!-- extension pages that open as tabs: relative, and the class is sx-icon -->
<svg class="sx-icon" aria-hidden="true">
  <use href="icons/material-icons.svg#settings"></use>
</svg>
```

In the panel's JavaScript, `icon("settings")` and `iconHref("settings")` in
`extension/app.js` build that reference; never write it by hand. The panel's symbols are
generated from `design/material-icons.svg` by `tools/sync_design_assets.py`, with an
`icon-` prefix, because the panel's own ids share its document: its Test site button's id
is `check`.

**The authoring class is `sx-icon`, not `material-icon`.** This block previously showed
`class="material-icon"` on an absolute path — a form neither surface uses. Corrected
2026-08-29 by `REQ-49`.

An icon-only button must also have an `aria-label`. Add a symbol to the
canonical sprite only when the repository contains no suitable symbol already.

## File ownership

- Shared visual values and interaction states: `design/`.
- Web application shell: `scrapex/webui/static/webui.css`.
- One web page's layout: `scrapex/webui/static/pages/`.
- Native and Tabulator tables: `table-theme.css` and `grid-theme.css`.
- Extension panel and onboarding layout: `extension/app.css` and
  `extension/onboarding.css`.
- Extension console and data pages: `extension/console.css` and
  `extension/data.css`. (**780 lines that this table left with no owner named**, while
  the 33-line `onboarding.css` beside them was named. Added 2026-08-29 by `REQ-49`.)

**The proportion is the thing to keep in mind here.** The shared layer is 2,093 lines and
it governs 9,967 lines of authored CSS outside it — a ratio of roughly 1 to 4.8, and
`extension/app.css` alone is 3,818, nearly twice the whole system.

The guard in `tests/test_design_system.py` rejects stale generated assets,
inline style attributes, embedded SVG paths, and a missing Material icon
license.

**What that guard does NOT do, measured 2026-08-29.** It never opens a `.svg`, so a
colour baked into the sprite at source and synced to both copies passes every check
(`OP-107`).

**The design documents are guarded only in part.** This document, `docs/UI-KIT.md` and
`docs/DESIGN-SYSTEM-SOURCES.md` are in the citation guard's `DOCUMENTS` (#409), which
checks a `path:line` citation into this repository. It does not check a bare backticked
path or an `R-` number (#1076).
`tests/test_the_design_docs_cite_supabase_at_the_pin.py` checks that every link into
Supabase's repository names the pin and a path the pin holds, that every link to the live
design-system site has its pinned source on the same line, and that every `path@commit`
citation and every backticked commit in prose names the pin. It does not check what a
cited line says, or a commit hash written without backticks.
