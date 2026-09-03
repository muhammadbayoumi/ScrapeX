# ScrapeX Design System

## 0 · The design system is Supabase's, and a palette carries colour only

**This is the first thing to read here, and this document did not say it for 37 days.**
It was last edited on 2026-07-23; `R-73` and `R-74` were ruled on 2026-08-28 and shipped in
`208d829`, and the word "Supabase" appeared nowhere below. Corrected 2026-08-29 by
[REQ-49](REQUESTS.md#req-49--review-the-design-system-against-supabases).

[R-74](RULINGS.md#r-74--the-design-system-is-supabases-always-and-a-palette-may-change-nothing-but-colour)
— *«design system هو supabase ولكن قد ضفنا له استثناء 3 palette الوان»*, and *«واى تعارض
معاها يلغى»*:

1. **`design/tokens.css` IS the Supabase design system.** Shape, typography, spacing,
   elevation, motion and focus geometry are Supabase's, always, and they live in the
   baseline so that every colour choice sits on them.
2. **A user chooses COLOUR and nothing else.** Four choices: `supabase` (the default),
   `whatsapp`/`brand`, `github`/`blue`, and `device`.
3. **A palette entry may contain nothing but colour**, enforced by
   `tests/test_a_palette_may_change_nothing_but_colour.py`. `whatsapp` and `github` do not
   represent the brand — they are colour exceptions on top of the system.
4. [R-59](RULINGS.md#r-59--the-palette-registry-brand-is-default-alternatives-is-extensible-teal-is-debt)
   decision 4 still governs: components consume semantic roles, **never** a palette
   identifier.

**Measured 2026-08-29 and worth knowing before you trust the guard:** rule 3 holds in the
built product across all eight shipped states, and is enforced by one unasserted statement.
See `OP-102`, and read it before adding a palette.

---

ScrapeX has one authored visual system shared by the browser extension and the
local web workspace. `tools/sync_design_assets.py` is the single source of the copy map —
nine sources into eighteen destinations — and it is the file to read rather than any list
restated here, because a restated list goes stale. The three that carry the rules:

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
3. **Theme-aware by default, and three of these are ADDITIONS above the
   baseline.** Light, dark, increased-contrast, reduced-motion, forced-colour,
   touch and keyboard states are all part of the core system here — and Supabase
   publishes **no** `forced-colors` block, **no** `prefers-contrast`
   accommodation and only three `prefers-reduced-motion` rules, none of them
   global. Light and dark are theirs; the rest are this repository's own, kept
   deliberately under `R-85` rather than removed by it, and they need a recorded
   rationale rather than a fix.
4. **English chrome, any-language data.** Scraped values use `.content`,
   `.name`, or `dir="auto"` so bidirectional text is isolated correctly.
5. **Use native semantics first.** Real buttons, links, labels, fieldsets,
   tables, tabs, and dialogs are preferred; ARIA augments them only where the
   native element cannot express the interaction.
6. **One icon source, and it is a DECLARED DEPARTURE from Supabase.** Reuse a
   symbol from the Material sprite instead of embedding an SVG path or drawing a
   replacement. **Supabase's set is Lucide** — size 24, `strokeWidth` 1.5,
   `stroke: currentColor`, `fill: none` — and this repository ships filled Google
   Material: 50 symbols, 37 referenced, 173 call sites. He recorded the difference
   rather than migrating it («سجلها خروجا معلنا», 2026-09-02) because
   [R-85](RULINGS.md#r-85--the-system-is-supabases-exactly-and-supabase-is-the-only-colour-choice)
   §4a is «القيم فقط» and an icon set is not a colour value; §6 carries the cost, and
   `design/supabase.NOTICE.txt` carries it where Apache-2.0 §4(b) wants it. **This
   line used to read as a house rule, which is how a divergence stops looking like
   one.**

## Token groups

| Group | Examples |
|---|---|
| Surfaces and text | `--bg`, `--surface`, `--surface-raised`, `--line`, `--text`, `--muted` |
| Brand and status | `--accent`, `--accent-ink`, `--amber`, `--red`, `--focus` |
| Controls | `--button-bg`, `--button-hover`, `--control-bg`, `--control-height` — **40px and 32px, from the baseline.** The panel raised them to 48/40 until `R-85` §5 deleted that override; `--touch-target` survives for the 24 places that size an element for touch deliberately |
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

**Nothing here discharges the Supabase obligation.** `design/tokens.css` carries values
traceable to `github.com/supabase/supabase` — Apache-2.0 at the root, MIT for the
`packages/ui` these came from — and `design/` carries no notice of either. That is
`OP-108`, and it is the one licence gap this repository has not already answered.

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
