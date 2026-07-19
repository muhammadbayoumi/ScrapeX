# ScrapeX Design System

Single source of visual truth. Tokens live in `extension/tokens.css`; shared
component primitives in `extension/components.css`. Every UI surface (the
extension now, the TS product later, the Python web UI) consumes these — no
hardcoded colors/spacing anywhere (DRY).

## Principles
1. **Consistency over creativity** — one token set, one component set.
2. **Theme-aware by default** — every token has a light + dark value (`prefers-color-scheme`).
3. **English UI, any-language content** — chrome is English; content cells use
   `unicode-bidi:plaintext` / `dir="auto"` so Arabic names render RTL correctly.
4. **Accessible** — visible focus rings, AA contrast, ≥ touch sizing.

## Tokens

| Group | Tokens | Notes |
|---|---|---|
| Surfaces | `--bg` `--surface` `--line` `--text` `--muted` `--chip` | neutral ramp |
| Accent (brand/success) | `--accent` `--accent-ink` `--accent-weak` | brand, accessible accent text, subtle backgrounds |
| Buttons | `--button-bg` `--button-text` | filled-action background and label |
| Amber (warning/soon) | `--amber` `--amber-weak` | "coming soon", cautions |
| Red (error/danger) | `--red` `--red-weak` | errors, engine-down |
| Spacing (4px base) | `--sp-1`…`--sp-5` | .25 → 1.5rem |
| Radius | `--radius-sm` `--radius` `--radius-lg` `--radius-pill` | 6 / 9 / 12 / pill |
| Type | `--font` `--font-mono` `--fs-xs`…`--fs-lg` `--fw-regular` `--fw-bold` | Segoe UI + Noto Sans Arabic |
| Motion | `--dur` | .15s |

Every token ships a dark-mode value; nothing else is themed.

## Components

### Button
| Variant | Use when |
|---|---|
| primary (`button`) | the main action in a context |
| ghost (`button.ghost`) | secondary/inline actions using the same neutral control palette |

| State | Visual | Behavior |
|---|---|---|
| default | `--button-bg` fill with `--button-text` label | — |
| hover | `brightness(.96)` | — |
| disabled | `opacity:.5` | non-interactive (`:disabled`) |
| focus | 2px accent outline, 2px offset | keyboard-visible (`:focus-visible`) |
| loading | caller sets text `…` + `disabled` | (capture buttons) |

**A11y:** real `<button>` elements (keyboard + role free); focus ring always visible.

### Card — `default` · `hi` (accent border) · `warn` (danger bg)
Container for a grouped block. `hi` = "you're on a known site"; `warn` = engine down.

### Chip / badge — `chip` · `chip.off`
Small status pill. `off` (amber) = "support coming soon".

### Status dot — `dot` · `dot.on` · `dot.off`
Engine connection indicator in the header (green = connected, red = not running).

### Input
Full-width; token-styled border/radius; inherits focus ring.

### Source row — `srow`
One site: name (`.name`, bidi-plaintext) + price count (`.n`, tabular-nums) + action.

## Do / Don't
| ✅ Do | ❌ Don't |
|---|---|
| use `var(--token)` for every color/space | hardcode hex or px |
| add new semantic tokens if a real need appears | invent one-off colors in a page |
| keep page `<style>` to layout only | re-declare primitives per page |
| wrap content cells in `.name` / `dir="auto"` | assume LTR for scraped text |
