# ScrapeX Design System

ScrapeX has one authored visual system shared by the browser extension and the
local web workspace. The canonical files are:

- `design/tokens.css` — semantic colour, type, spacing, shape, elevation,
  control, motion, and layering tokens.
- `design/components.css` — reusable controls, cards, banners, lists, badges,
  layout helpers, icon sizing, focus treatment, and accessibility utilities.
- `design/material-icons.svg` — the curated Google Material Icons sprite.

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
3. **Theme-aware by default.** Light, dark, increased-contrast, reduced-motion,
   forced-colour, touch, and keyboard states are part of the core system.
4. **English chrome, any-language data.** Scraped values use `.content`,
   `.name`, or `dir="auto"` so bidirectional text is isolated correctly.
5. **Use native semantics first.** Real buttons, links, labels, fieldsets,
   tables, tabs, and dialogs are preferred; ARIA augments them only where the
   native element cannot express the interaction.
6. **One icon source.** Reuse a symbol from the Material sprite instead of
   embedding an SVG path or drawing a replacement.

## Token groups

| Group | Examples |
|---|---|
| Surfaces and text | `--bg`, `--surface`, `--surface-raised`, `--line`, `--text`, `--muted` |
| Brand and status | `--accent`, `--accent-ink`, `--amber`, `--red`, `--focus` |
| Controls | `--button-bg`, `--button-hover`, `--control-bg`, `--control-height` |
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
- Status and data: `.chip`, `.badge`, `.dot`, `.source-row`, `.content`, and
  `.num`.
- Accessibility: `.visually-hidden`, consistent `:focus-visible`, coarse
  pointer sizing, reduced-motion fallbacks, and forced-colour fallbacks.

Tables use `static/table-theme.css`. Tabulator maps to the same table vocabulary
through `static/grid-theme.css`; renderer-specific overrides stay there.

## Material icons

The sprite is sourced from
[`google/material-design-icons`](https://github.com/google/material-design-icons)
and retains its Apache 2.0 notice in
`scrapex/webui/static/material-icons/LICENSE.txt`.

Use an icon decoratively with an adjacent visible label:

```html
<svg class="material-icon" aria-hidden="true">
  <use href="/static/material-icons/material-icons.svg#settings"></use>
</svg>
```

An icon-only button must also have an `aria-label`. Add a symbol to the
canonical sprite only when the repository contains no suitable symbol already.

## File ownership

- Shared visual values and interaction states: `design/`.
- Web application shell: `scrapex/webui/static/webui.css`.
- One web page's layout: `scrapex/webui/static/pages/`.
- Native and Tabulator tables: `table-theme.css` and `grid-theme.css`.
- Extension panel and onboarding layout: `extension/app.css` and
  `extension/onboarding.css`.

The guard in `tests/test_design_system.py` rejects stale generated assets,
inline style attributes, embedded SVG paths, and a missing Material icon
license.
