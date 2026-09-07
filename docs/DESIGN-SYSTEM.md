# ScrapeX Design System

## 0 · The design system is Supabase's, and a palette carries colour only

**This is the first thing to read here, and this document did not say it for 37 days.**
It was last edited on 2026-07-23; `R-73` and `R-74` were ruled on 2026-08-28 and shipped in
`208d829`, and the word "Supabase" appeared nowhere below. Corrected 2026-08-29 by
[REQ-49](archive/REQUESTS.md#req-49--review-the-design-system-against-supabases).

[R-74](archive/RULINGS.md#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour)
— *«design system هو supabase ولكن قد ضفنا له استثناء 3 palette الوان»*, and *«واى تعارض
معاها يلغى»*:

1. **`design/tokens.css` IS the Supabase design system.** Shape, typography, spacing,
   elevation, motion and focus geometry are Supabase's, always, and they live in the
   baseline so that every colour choice sits on them.
2. **A user chooses COLOUR and nothing else, and there is exactly one choice.**
   `supabase`. [R-85](archive/RULINGS.md#r-85--the-system-is-supabases-exactly-and-supabase-is-the-only-colour-choice)
   deleted the other three on 2026-08-31 — *«احذف الثلاثة وابق supabase وحده»* — and device
   colour mode with them. `whatsapp`, `brand`, `github` and `blue` survive in
   `design/appearance.js` only as aliases resolving to `supabase`, so a preference stored
   before that date still opens.
3. **A palette entry may contain nothing but colour**, enforced by
   `tests/test_a_palette_may_change_nothing_but_colour.py`. The rule outlived the three
   exceptions it was written for: it governs the palette that remains, and the next one
   added.
4. [R-59](archive/RULINGS.md#r-59--the-palette-registry-brand-is-default-alternatives-is-extensible-teal-is-debt)
   decision 4 still governs: components consume semantic roles, **never** a palette
   identifier.

**Measured 2026-08-29, and the number moved under it.** Rule 3 was verified in the built
product across all eight shipped states — four palettes by two schemes. `R-85` left one
palette by two schemes, so the same guard now covers everything the product ships rather
than a quarter of it. Read `OP-102` before adding a palette.

---

ScrapeX has one authored visual system shared by the browser extension and the
local web workspace. `tools/sync_design_assets.py` is the single source of the copy map,
and it is the file to read rather than any list restated here — **a count is that same
restatement in miniature**, and the one that stood in this sentence went stale exactly as
the sentence warned. The three that carry the rules:

- `design/tokens.css` — semantic colour, type, spacing, shape, elevation,
  control, motion, and layering tokens. **This is the file `R-74` rules on**, and it is
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
3. **Theme-aware by default, and two of these are ours rather than theirs.**
   Light, dark, increased-contrast, reduced-motion, forced-colour, touch and
   keyboard states are all part of the core system. Light and dark are Supabase's.
   **The `forced-colors` block and the `prefers-contrast` accommodation are
   additions above the baseline** — searching their repository for either returns
   nothing — and both are recorded as such in the statement of changes in
   `design/supabase.NOTICE.txt`. **Reduced motion is not an addition**: Supabase
   honours `prefers-reduced-motion` in fourteen places, so respecting it here
   matches them rather than departing from them.
4. **English chrome, any-language data.** Scraped values use `.content`,
   `.name`, or `dir="auto"` so bidirectional text is isolated correctly.
5. **Use native semantics first.** Real buttons, links, labels, fieldsets,
   tables, tabs, and dialogs are preferred; ARIA augments them only where the
   native element cannot express the interaction.
6. **One icon source, and it is a declared departure.** Reuse a symbol from the
   Material sprite instead of embedding an SVG path or drawing a replacement.
   **Supabase's icon set is Lucide**, at size 24 with `strokeWidth` 1.5 and
   `stroke: currentColor`; this product ships a filled Material sprite. Asked on
   2026-09-02 whether to migrate or to record the difference, he chose to record
   it — `R-85`'s exactness instruction was scoped to the values, and an icon set
   is not a colour value. The cost of migrating, and the reason it was not paid,
   are in `design/supabase.NOTICE.txt`.

## Token groups

| Group | Examples |
|---|---|
| Surfaces and text | `--bg`, `--surface`, `--surface-raised`, `--line`, `--text`, `--muted` |
| Brand and status | `--accent`, `--accent-ink`, `--amber`, `--red`, `--focus` |
| Controls | `--button-bg`, `--button-hover`, `--control-bg`, `--control-height` (40px) and `--control-height-sm` (32px), both from the Supabase baseline since `R-85` deleted the panel's 48/40 override; `--touch-target` survives for the places that size for touch deliberately |
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

There are **two** real forms, and the difference is not cosmetic — the extension has no
`/static/` root, so an absolute path there resolves to nothing.

```html
{# web workspace: the macro carries the cache-buster #}
{{ icon('settings') }}

<!-- extension: relative, and the class is sx-icon -->
<svg class="sx-icon" aria-hidden="true">
  <use href="icons/material-icons.svg#settings"></use>
</svg>
```

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

**Two things that guard does NOT do, measured 2026-08-29.** It never opens a `.svg`, so a
colour baked into the sprite at source and synced to both copies passes every check
(`OP-107`). And **this document and `docs/UI-KIT.md` are guarded by nothing at all** —
neither is in the citation guard's `DOCUMENTS`, and no tier resolves a bare backticked
path, which is why the four stale facts corrected above survived (`OP-109`).
