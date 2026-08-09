# ScrapeX UI / Design System Audit

**Repository audited:** `C:/Users/User01/source/repos/ScrapeX`  
**Scope:** Chrome extension (`extension/`) and local Web UI (`scrapex/webui/`).  
**Rule:** This document is read-only evidence. No production code was modified.

---

## 1. Technology Stack

| Layer | Finding | Evidence |
|---|---|---|
| **Extension manifest** | Chrome Manifest V3 | `extension/manifest.json:2` |
| **Extension entry surface** | Side panel only (`side_panel.default_path: "app.html"`); no popup, no `options_page` | `extension/manifest.json:20-22` |
| **Background runtime** | MV3 service worker | `extension/background.js:1-13` |
| **Frontend framework** | Vanilla JavaScript / ES modules + IIFE helpers; no SPA framework | `extension/app.html:1656`, `extension/app.js` |
| **HTML rendering** | Static HTML shell; JS toggles `hidden`, sets `innerHTML`, and binds listeners | `extension/app.js:40-42`, `extension/app.js:1217-1259` |
| **CSS approach** | CSS custom-property token system; three physical copies of canonical files | `design/tokens.css`, `extension/tokens.css`, `scrapex/webui/static/tokens.css` |
| **Build system** | No build step for the extension; `tools/sync_design_assets.py` copies canonical design assets | `tools/sync_design_assets.py:20-58` |
| **Backend / Web UI** | FastAPI + Jinja2 + static files; optional `JobRunner` thread | `scrapex/webui/app.py:22-28` |
| **State management** | Plain JS `state` object (extension); server-side context + page JS (Web UI) | `extension/app.js:46-64` |
| **Storage / settings** | `chrome.storage.local` for engine backend URL; `localStorage` for appearance/timezone; SQLite `scrapex_meta` for server-side UI settings | `extension/engine.js:10-16`, `extension/appearance.js:150-168`, `scrapex/settings.py` |
| **Icon system** | SVG sprite of Google Material Symbols + custom `x-mark.svg` brand mark | `extension/icons/material-icons.svg`, `design/components.css:126-144` |
| **Browser APIs** | `chrome.sidePanel`, `chrome.runtime` (native messaging, onInstalled), `chrome.tabs`, `chrome.windows`, `chrome.identity.getAuthToken`, `chrome.storage`, `fetch`, `navigator.clipboard` | `extension/background.js:3-12`, `extension/identity.js:71-77`, `extension/transport.js:68-78` |
| **Engine integration** | HTTP health poll to `127.0.0.1:8000` + Chrome Native Messaging for start/repair/upgrade | `extension/engine.js:20-47`, `extension/transport.js:20-150` |

**Classification:** Manifest V3, side-panel entrypoint, service worker, identity, and native messaging are **CHROME-NATIVE**. Vanilla JS + direct DOM updates are **EXTENSION PROFILE**. The token-driven CSS and shared JS modules are **SHARED COMPONENT CONTRACT / GLOBAL SEMANTIC CANDIDATES**.

---

## 2. UI Surface Map

### Chrome Extension surfaces

| Surface | File / Trigger | Notes |
|---|---|---|
| **Side panel** | `extension/app.html` | Always-available control UI opened by toolbar icon via `chrome.sidePanel.setPanelBehavior`. |
| **Onboarding / setup page** | `extension/onboarding.html` | Opened on `chrome.runtime.onInstalled`; engine-status + copyable install commands. |
| **Workspace pages (launcher)** | `extension/app.js:78-106` fallback + `workspace-menu` | Detailed tools open in a full browser tab from the side-panel launcher. |
| **No popup / no options page** | — | Manifest has no `options_page`, `options_ui`, or `browser_action` popup. |

### In-panel destinations (side panel)

Rendered as `role="tabpanel"` sections toggled by the right-side rail (`extension/app.html:26-1490`, `extension/app.js:68-75`):

- `view-profile`
- `view-engines`
- `view-source`
- `view-run`
- `view-data`
- `view-sources` (Library)
- `view-source-edit`
- `view-appearance`
- `view-finance`
- `view-console`
- `view-settings`

### Local Web UI surfaces

The Web UI shell is in `templates/base.html`. Navigation is data-driven by `scrapex/ui_manifest.py`.

| Route / Template | Purpose |
|---|---|
| `overview.html` `/` | Command center / pipeline health |
| `data.html`, `source.html` | Per-source data browser (Tabulator grid) |
| `changes.html` | Recent price / availability changes |
| `history.html` | Past runs and outcomes |
| `review.html` | Resolve proposed record matches |
| `jobs.html` | Start and monitor collection jobs |
| `schedules.html` | Automatic collection times |
| `sync.html` | Google Sheets / Drive sync |
| `excel.html`, `exports.html` | Excel / local export configuration |
| `data_model.html`, `schema.html` | Warehouse docs and column meanings |
| `settings.html` | Runtime, storage, policy |
| `manage.html` | Source management (older, minimal styling) |
| `offer.html` | Single-offer detail |
| `google_finance_dataset.html` | Google Finance rate view |
| `database_unavailable.html` | Database-attention fallback page |

---

## 3. Component Inventory

All primitives live in the canonical `design/components.css`, copied to `extension/components.css` and `scrapex/webui/static/components.css`.

### Actions

| Component | Class(es) | States / Variants | Classification |
|---|---|---|---|
| Primary button | `button`, `.button` | default, hover, active, disabled / `aria-disabled="true"` | SHARED CONTRACT |
| Ghost / secondary | `.ghost` | hover, active, disabled | SHARED CONTRACT |
| Danger | `.danger` | hover, active | SHARED CONTRACT |
| Link button | `.link` | hover | SHARED CONTRACT |
| Icon button | `.icon-button` | `.compact` | SHARED CONTRACT |
| Section toggle | `.sect` | full-width disclosure row | SHARED CONTRACT |
| Split button | `.split-button` + `.split-button-primary` / `.split-button-trigger` | open/closed menu, primary + menu items | SHARED CONTRACT |

### Forms

| Component | Class(es) / Markup | Notes |
|---|---|---|
| Text / URL / number / search / time / textarea | `input`, `select`, `textarea` | Full-width; token borders; `aria-invalid` styling. |
| Checkbox / radio | Native inside `.check` wrapper | Native controls, custom wrappers for selectable rows. |
| Custom single-select | `.sx-select` + `.sx-select-trigger` + `.sx-select-list` | Hidden native `<select>`; custom listbox with keyboard support. |
| Switch / toggle | `.appearance-switch` (compact WhatsApp-style) | Native checkbox hidden, visual thumb/track. |
| Segmented control | `.appearance-scheme-picker` | Light / Dark / Device with sliding indicator. |

### Containers

| Component | Class(es) | Notes |
|---|---|---|
| Card | `.card`, `.card.hi`, `.card.warn` | Default surface with border, shadow, hover lift on `a.card`. |
| Banner | `.banner`, `.banner.info`, `.banner.danger` | Status / attention block. |
| Settings row / list row | `.srow` | Bordered, rounded, hover state. |
| Source identity | `.source-identity` (+ compact variant) | Domain → English/Arabic name → key → metric. |
| Icon tile | `.icon-tile` | Tinted square icon marker; accent/amber/danger variants. |

### Navigation

| Component | Class(es) / Markup | Notes |
|---|---|---|
| Right-side rail | `nav.side-rail`, `.rail-item` | Chrome side panel only; grouped tablists. |
| Workspace sidebar | `.workspace-sidebar`, `.wsnav-links` | Web UI left rail; grouped by `ui_manifest.py`. |
| Settings category nav | `.settings-nav`, `.settings-nav-item` | Vertical tablist in `settings.html`. |
| Page header | `.view-heading`, `.page-header` | Sticky headings in panel, hero headers in workspace. |

### Feedback / Status

| Component | Class(es) | Notes |
|---|---|---|
| Dot | `.dot`, `.dot.on`, `.dot.off` | 9px circular status indicator. |
| Chip / badge | `.chip`, `.badge` | Pill labels; accent/amber/danger/off variants. |
| Empty state | `.empty` | Centered muted message block. |
| Skeleton | `.skeleton` | Loading placeholder. |

### Overlays

| Component | Implementation | Notes |
|---|---|---|
| Workspace launcher sheet | `#workspace-menu` + `#workspace-backdrop` | Fixed sheet with focus management. |
| Custom select dropdown | `.sx-select-list` | Positioned listbox. |
| Split-button menu | `<details class="split-button-menu">` | Native disclosure enhanced with roles. |
| Confirmation flows | `window.confirm` / `window.prompt` | Used for destructive actions. |

---

## 4. Navigation Architecture

### Side panel (extension)

- **Page shell:** CSS Grid `1fr` content + `--panel-rail-width` (3.5 rem) rail. Body `overflow: hidden` (`extension/app.css:11-15`).
- **Right-side rail:** `nav.side-rail` with three semantic groups — extension-owned pages (Profile, Engine), engine-owned pages (Source, Run, Data, Google Finance), utility/settings (Appearance, Library, Console, Settings) — plus the Workspace launcher (`extension/app.html:1517-1632`).
- **Active state:** A sliding accent indicator (`#rail-indicator`) and `is-rail-active` class; `aria-selected`, `aria-current="page"`, `tabindex` managed in JS (`extension/app.css:1002-1018`, `extension/app.js:143-150`, `219-228`).
- **Keyboard:** Arrow Up/Down/Home/End move focus and change view (`extension/app.js:3434-3445`).
- **Workspace launcher:** Fixed sheet with backdrop; focus moves to first link on open, returns to toggle on close; Escape closes (`extension/app.js:156-186`).
- **Scroll containment:** Most views are self-scrolling (`overflow-y: auto`); Run/Finance/Settings use a nested `.view-scroll`; Data/Sources keep headings fixed and scroll lists inside cards (`extension/app.css:204-277`, `314-337`).
- **Width assumptions:** Designed for a minimum panel width of ~320 px; `* { min-width: 0; }`; responsive breakpoints at 340/390/430 px (`extension/app.css:17-18`, `738-751`, `1825-1844`).

### Local Web UI

- **Shell:** `.workspace-shell` CSS Grid with fixed left sidebar width `--workspace-sidebar-width: 17.75rem` (`scrapex/webui/static/webui.css:68-70`).
- **Sidebar:** Sticky, scrollable, collapses to mobile drawer below 900 px (`scrapex/webui/static/webui.css:116-138`).
- **Navigation source of truth:** `scrapex/ui_manifest.py` `WORKSPACE_DESTINATIONS`; same data served via `GET /api/ui` to the panel.
- **Active state:** `aria-current="page"` on active link (`templates/base.html:33`).
- **Footer status:** Engine / database health links.

**Classification:** Right-side icon rail, narrow panel constraints, and workspace launcher are **EXTENSION PROFILE**. Left sidebar / mobile drawer pattern is a generic **GLOBAL SEMANTIC / SHARED CONTRACT** candidate, though its specific width and grouping are **SCRAPEX-SPECIFIC**.

---

## 5. Forms & Controls

### Buttons (`design/components.css:345-489`)

- **Base:** `min-height: var(--control-height)` (2.5 rem canonical, overridden to 3 rem in extension), `padding: var(--sp-2) var(--sp-4)`, `border-radius: var(--radius)` (0.5625 rem), `font-weight: var(--fw-medium)`.
- **Primary:** `background: var(--button-bg)` (accent), `color: var(--button-text)` (contrast).
- **Ghost:** `background: var(--control-bg)`, `border-color: var(--line)`, `color: var(--text)`.
- **Danger:** `background: var(--red)`, `color: var(--danger-contrast)`.
- **Disabled:** `opacity: 0.5`, `cursor: not-allowed`, `transform: none`.

### Inputs (`design/components.css:490-540`)

- `min-height: var(--control-height)`, `border: 1px solid var(--line)`, `border-radius: var(--radius)`, `background: var(--control-bg)`.
- Focus/hover transition on border and background.
- Invalid state: `border-color: var(--red)` when `aria-invalid="true"`.

### Custom select (extension)

- Implementation: hidden native `<select>` (`tabindex="-1"`, `aria-hidden="true"`) + `.sx-select-trigger` + `.sx-select-list` (`role="listbox"`).
- Trigger `min-height: var(--touch-target)` (3 rem), list max-height `min(17rem, 50vh)`.
- Keyboard: Arrow keys, Home, End, Escape; selection updates `aria-selected` on options (`extension/app.js:1694-1808`).
- **Accessibility note:** No `aria-activedescendant` synchronization while arrowing; trigger has `aria-controls` but no live option id.

### Switch

- `.appearance-switch`: 48 px touch target wrapping a 2.5 rem × 1.5 rem track.
- Uses hidden native checkbox for state; focus-visible outline on span.

### Segmented control

- `.appearance-scheme-picker`: Light / Dark / Device in a pill-shaped container with a sliding `::before` indicator.
- Buttons use `aria-pressed`; `:has()` selector drives indicator position.

**Classification:** Form primitives are strong **SHARED COMPONENT CONTRACT** candidates. The custom select overlay behavior and switch sizing are **EXTENSION PROFILE** influenced by the compact panel.

---

## 6. Cards / Panels / Lists

### Card (`.card`)

- `background: var(--surface)`, `border: 1px solid var(--line)`, `border-radius: var(--radius-lg)` (0.75 rem), `padding: var(--sp-4)`, `box-shadow: var(--shadow-xs)`.
- Variants: `.card.hi` (accent border), `.card.warn` (red-tinted border + red-weak background).
- Anchor cards lift on hover (`translateY(-1px)`, shadow grow).

### Banner (`.banner`)

- `padding: var(--sp-3) var(--sp-4)`, `border-radius: var(--radius-lg)`, default amber-weak background.
- Variants: `.info` (accent-weak), `.danger` (red-weak).

### List row (`.srow`)

- `display: flex`, `justify-content: space-between`, `gap: var(--sp-2)`, `padding: var(--sp-2) var(--sp-3)`, `border-radius: var(--radius)`.
- Hover: border-color and background shift to subtle.

### Source selection row (`.source-selection-row`)

- Grid layout with checkbox + source identity.
- Hover background; focus-visible outline delegated to `:has(input:focus-visible)`.

### Empty / loading

- `.empty`: centered muted block with large vertical padding.
- `.skeleton`: generic loading block (color/shape defined by consumers).

**Classification:** Card, banner, list row, empty state are **SHARED COMPONENT CONTRACT** candidates. Source identity is **SCRAPEX-SPECIFIC**.

---

## 7. Status & Feedback States

### Engine / runtime status

| State | UI Presentation | Evidence |
|---|---|---|
| **Engine running** | Green dot + "Ready · engine vX.Y.Z" | `extension/app.js:402-408` |
| **Engine not running / setup required** | Red dot + "Setup required"; setup card with start button | `extension/app.js:402-408`, `extension/app.html:34-54` |
| **Checking / starting** | Onboarding `.status.checking` + spinner dot | `extension/onboarding.html:18-22`, `extension/onboarding.js:42-57` |
| **Connection error** | No answer on `/api/health`; reachable=false path | `extension/engine.js:44-45` |
| **Protocol mismatch** | Refusal card with five facts | `extension/app.js:2001-2011` |
| **Extension too old** | Refusal card + disabled run + missing capabilities list | `extension/app.js:2037-2047` |
| **Database needs upgrade / startup blocked** | Runtime issue card with "Upgrade database" action | `extension/app.js:291-360` |
| **Schema lag** | `#schema-lag` banner | `extension/app.js:366-386` |
| **No sites available** | "No sites yet" muted row | `extension/app.js:1212-1215` |
| **Sites selected** | Count chip; run enabled when engine OK | `extension/app.js:2071-2086` |
| **Job running / queued / paused** | Activity section + miniplayer at bottom | `extension/app.js:2209-2414`, `extension/app.html:1494-1515` |

### Semantic mapping candidates

| ScrapeX Concept | Candidate Global Semantic |
|---|---|
| Engine running + compatible + DB healthy | `ready` |
| Engine stopped / unreachable | `disconnected` / `offline` |
| Reachable but protocol/version/DB issue | `warning` |
| Unreachable / crash / startup blocked | `error` |
| Starting / checking / polling | `pending` / `loading` |
| Action unavailable | `disabled` |
| Job executing | `running` |

**Classification:** The underlying semantics (`ready`, `warning`, `error`, `pending`, `disabled`, `running`) are **GLOBAL SEMANTIC CANDIDATES**. ScrapeX-specific copy ("Setup required", "Schema lag", protocol-version facts) is **SCRAPEX-SPECIFIC**.

---

## 8. Data / Selection Interfaces

### Source identity

- Canonical component: `.source-identity` (`design/components.css:661-772`).
- Display order: domain (primary), English then Arabic name, stable key, contextual metric.
- Handles bidirectional text with `unicode-bidi: plaintext` and `direction: ltr` for domain/key.

### Site selection (Run view)

- Search input + checklist of `.srow` rows with checkboxes.
- Bulk actions: Select all / Clear.
- Selected count displayed; run button disabled until at least one site selected and engine OK.

### Dataset / data browser (Web UI)

- Tabulator grid heavily customized via `grid-theme.css` and `grid.js`.
- Inline source-filter popover (`_picker.html`, `.source-filter-menu`).
- Data model diagram in `pages/data-model.js` (canvas-based).

### Currency / Google Finance

- Google Finance view in side panel (`view-finance`) with rate table, refresh settings, save state.

**Classification:** Source identity and selection flows are **SCRAPEX-SPECIFIC**. The underlying list/checkbox/select patterns are **SHARED CONTRACT** candidates.

---

## 9. Theme Architecture

### Theme selection

- Three scheme modes: **Light**, **Dark**, **Device**.
- Default: `mode: "device"`, `scheme: "light"`, `palette: "github"`, `deviceColors: true` (`extension/appearance.js:100-106`).
- Manual mode sets `data-theme="light"` / `"dark"`; Device mode removes `data-theme` and relies on `prefers-color-scheme` (`extension/tokens.css:197-232`).

### Color styles (palettes)

- Two hard-coded palettes: **WhatsApp** (green) and **GitHub** (blue/neutral).
- Selecting a palette writes ~30 CSS properties inline on `<html>` via `appearance.js` (`extension/appearance.js:188-208`).
- Server validates allowlist: `palette in {"whatsapp", "github"}` (`scrapex/webui/app.py:115-116`).

### Device colors

- When enabled, uses CSS `AccentColor` / `AccentColorText` and derives tonal surfaces with `color-mix` (`extension/tokens.css:149-159`, `241-275`).

### Persistence & sync

- `localStorage` key `scrapex-appearance-v2`; legacy `scrapex-appearance-v1` read as fallback.
- Cross-tab sync via `storage` event.
- Engine sync: `POST /api/appearance` on change, `GET /api/appearance` every 2 s when engine up (`extension/appearance.js:322-377`); stored in SQLite `scrapex_meta` via `scrapex/settings.py`.

### Token sync mechanism

- Canonical authored files in `design/` are copied byte-for-byte to `extension/` and `scrapex/webui/static/` by `tools/sync_design_assets.py`.
- Files synchronized: `tokens.css`, `components.css`, `appearance.js`, `split-button.js`, `material-icons.svg`, `google-g.png`, `x-mark.svg`.

**Classification:**
- Light/Dark/Device switching logic and palette concept are **SHARED COMPONENT CONTRACT** candidates.
- WhatsApp/GitHub palettes are user-chosen **SCRAPEX PRODUCT** profiles, not global brand.
- Device-color use of system accent is a **CHROME-NATIVE / GLOBAL SEMANTIC** pattern.
- The `scrapex-appearance-v1` fallback is **LEGACY**.

---

## 10. Visual Foundation

### Brand colors

| Token | Value | Role |
|---|---|---|
| `--accent` | `light-dark(#00adb5, #35c8ce)` | Primary brand / action color (ScrapeX teal) |
| `--accent-hover` | `light-dark(#009ba3, #51d3d8)` | Hover |
| `--accent-active` | `light-dark(#008990, #21b9c0)` | Active |
| `--accent-ink` | `light-dark(#006b70, #69e1e5)` | Text on subtle surface |
| `--accent-contrast` | `light-dark(#062b2d, #071f20)` | Text on accent |
| `--accent-weak` | `light-dark(#d8f4f5, #073a3d)` | Subtle background |

### Semantic colors

| Token | Value | Role |
|---|---|---|
| `--amber` / `--amber-weak` | `#9a5c0a` / `#fff4d6` | Warning |
| `--red` / `--red-hover` / `--red-weak` | `#b8322a` / `#9f2923` / `#fde9e7` | Danger / error |
| `--danger-contrast` | `#ffffff` | Text on danger |
| `--focus` | `light-dark(#007b83, #69e1e5)` | Focus ring base |
| `--selection` | `color-mix(in srgb, var(--accent) 20%, transparent)` | Text selection |

### Neutrals / surfaces

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#f5f7f9` | `#0f1216` | Page background |
| `--surface` | `#ffffff` | `#171b21` | Cards / elevated surfaces |
| `--surface-subtle` | `#f9fafb` | `#1c2128` | Hover / subtle fill |
| `--surface-raised` | `#ffffff` | `#20262e` | Higher elevation |
| `--line` | `#dfe3e8` | `#2c333d` | Borders |
| `--line-strong` | `#c5cbd3` | `#434d5a` | Stronger borders |
| `--text` | `#171a1f` | `#e9edf2` | Primary text |
| `--muted` | `#626c7a` | `#a9b2bf` | Secondary text |
| `--text-subtle` | `#7c8795` | `#8994a3` | Tertiary / placeholder |
| `--chip` | `#edf1f4` | `#242b34` | Pill backgrounds |

### Typography

| Token | Value |
|---|---|
| `--font` | `"Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, "Noto Sans Arabic", sans-serif` |
| `--font-mono` | `ui-monospace, "Cascadia Code", Consolas, monospace` |
| `--fs-2xs` | 0.6875 rem |
| `--fs-xs` | 0.75 rem |
| `--fs-sm` | 0.8125 rem |
| `--fs` | 0.875 rem |
| `--fs-md` | 1 rem |
| `--fs-lg` | 1.125 rem |
| `--fs-xl` | 1.375 rem |
| `--fs-2xl` | 1.75 rem |
| `--fw-regular` | 400 |
| `--fw-medium` | 500 |
| `--fw-bold` | 600 |
| `--fw-heavy` | 700 |
| `--lh-tight` | 1.25 |
| `--lh` | 1.5 |
| `--lh-relaxed` | 1.65 |

### Spacing

4 px base grid: `--sp-1: 0.25rem` through `--sp-8: 3rem`.

### Shape / elevation

| Token | Value |
|---|---|
| `--radius-xs` | 0.25 rem |
| `--radius-sm` | 0.375 rem |
| `--radius` / `--radius-md` | 0.5625 rem |
| `--radius-lg` | 0.75 rem |
| `--radius-xl` | 1 rem |
| `--radius-sheet` | 1.75 rem |
| `--radius-pill` | 999 px |
| `--shadow-xs` | `0 1px 2px rgb(16 24 40 / 0.08)` |
| `--shadow-sm` | `0 2px 8px rgb(16 24 40 / 0.08)` |
| `--shadow-lg` | `0 18px 40px rgb(16 24 40 / 0.16)` |
| `--overlay` | `rgb(15 18 22 / 0.42)` |

### Material 3 aliases

Tokens map global primitives to M3 roles: `--primary`, `--on-primary`, `--primary-container`, `--on-primary-container`, `--surface-container`, `--on-surface`, `--outline`, `--switch-track`, etc. (`design/tokens.css:113-129`).

### Hard-coded / legacy values observed

- Google Sign-In button dimensions: `min-height: 40px`, `padding: 0 12px`, `gap: 10px`, `font-size: 14px`, `line-height: 20px` (`design/components.css:254-292`).
- Extension app-specific: `.step-number { width: 20px; height: 20px; }`, `.logbox { max-height: 220px; }`, scrollbar widths `.45rem` (`extension/app.css`).
- Web UI page sheets: arbitrary `border-radius: 10px/12px`, `.84rem`/`.78rem` font sizes (`scrapex/webui/static/webui.css`, `pages/*.css`).
- Undefined `--font-sans` referenced in `extension/app.css` (token is `--font`).
- `extension/onboarding.css` uses invalid `::root` selector (should be `:root`).

**Classification:** Color semantics, spacing, typography, radii, shadows, and M3 aliases are **GLOBAL SEMANTIC / REFERENCE CANDIDATES**. ScrapeX teal is a **GLOBAL BRAND CANDIDATE** *for the ScrapeX product family*. Hard-coded values are **LEGACY / DUPLICATE** or **NEEDS REVIEW**.

---

## 11. Density

### Overall profile

ScrapeX is **compact to dense**, especially the extension side panel, which behaves like a compact Android app.

| Surface | Evidence | Density |
|---|---|---|
| **Extension controls** | `--control-height: var(--touch-target)` (3 rem / 48 px) in `extension/app.css:6` | Dense touch targets |
| **Extension small controls** | `--control-height-sm: 2.5rem` | Compact |
| **Canonical controls** | `--control-height: 2.5rem` in `tokens.css:53` | Compact |
| **Rail items** | 3.5 rem wide rail, 1.5 rem icons | Dense |
| **Side panel cards** | `padding: var(--sp-4)` (1 rem), gap `var(--sp-3)` (0.75 rem) | Compact |
| **Checklist rows** | `.srow` padding `var(--sp-2) var(--sp-3)` (0.5/0.75 rem) | Dense |
| **Web UI sidebar nav** | `min-height: 44px` rows, `.84rem` font | Comfortable-compact |
| **Web UI content** | `padding: var(--sp-5)` hero, larger `page-title` | More open than panel |

### Comparison with website profile

The known mbiXsite profile is **comfortable/editorial**: larger spacing, cream/mint surfaces, pill CTAs, technical grid. ScrapeX is materially denser, especially in the extension, because it must fit actionable controls into a narrow Chrome side panel and satisfy 48 px touch targets.

**Classification:** Density is **EXTENSION PROFILE** / **SCRAPEX-SPECIFIC**. It should not be forced onto the website profile, nor should website density be assumed for ScrapeX.

---

## 12. Motion

### Timing / easing tokens

| Token | Value |
|---|---|
| `--dur-fast` | 0.12 s |
| `--dur` | 0.18 s |
| `--dur-slow` | 0.26 s |
| `--ease` | `cubic-bezier(0.2, 0.8, 0.2, 1)` |

### Used in

- Button hover/active transitions (`background-color`, `border-color`, `color`, `box-shadow`, `transform`).
- Card hover lift (`translateY(-1px)`).
- Custom select menu open animation (`select-menu-in`).
- Split-button menu open animation (`split-button-options-in`).
- Segmented control sliding indicator.
- Switch thumb/track transitions.
- Workspace mobile drawer slide (`transform`, `transition`).

### Reduced motion

- Global `prefers-reduced-motion: reduce` disables animations and transitions (`design/components.css:925-934`; `extension/app.css:1996-2007`).

**Classification:** Motion tokens are **GLOBAL REFERENCE CANDIDATES**. Specific panel animations are **EXTENSION PROFILE**.

---

## 13. Accessibility

### Strengths

- **Semantic HTML:** `main`, `nav`, `section`, `header`, `article`, `fieldset`/`legend`, native labels throughout.
- **Landmark / roles:** `role="tablist"`/`tab`/`tabpanel`, `role="status"`, `role="progressbar"`, `role="listbox"`, `role="menu"`, `role="radiogroup"`, `role="switch"`.
- **ARIA states:** `aria-selected`, `aria-expanded`, `aria-pressed`, `aria-checked`, `aria-controls`, `aria-haspopup`, `aria-current="page"`, `aria-label`, `aria-live="polite"`, `aria-invalid`.
- **Focus-visible:** 3 px outline using `color-mix` with `--focus`; applies to buttons, links, inputs, selects, textareas, summaries, `[tabindex]`.
- **Keyboard navigation:** Rail arrow keys, custom select Arrow/Home/End/Escape, split-button Escape, workspace menu Escape.
- **Visually hidden:** `.visually-hidden` class for screen-reader-only labels.
- **Reduced motion & forced colors:** respected globally.
- **Focus management:** Workspace launcher moves focus to first link and returns on close.
- **Bidirectional text:** `unicode-bidi: plaintext` and `dir="auto"` for Arabic content inside LTR chrome.

### Gaps / needs review

- **Custom select:** native `<select>` is `aria-hidden`; trigger has `aria-controls` but no `aria-activedescendant` synchronization while arrowing through options.
- **Icon-only rail items:** rely on `title` attributes and visually-hidden spans; `title` is not reliable for touch/keyboard users.
- **`innerHTML` templating:** `app.js` builds many UI strings with `innerHTML` after escaping via `esc()`, but `innerHTML` remains a sink. Any future omission is a potential XSS risk.
- **No observed CSP** in Web UI templates; local-only binding reduces risk but no policy was found.

**Classification:** Accessibility primitives (focus-visible, reduced motion, visually-hidden, semantic roles) are **GLOBAL SEMANTIC CANDIDATES**. Chrome-specific focus management of the rail/launcher is **EXTENSION PROFILE**. The gaps are **NEEDS REVIEW**.

---

## 14. Chrome-Specific Constraints

| Constraint | Evidence | Classification |
|---|---|---|
| MV3 service worker background | `extension/background.js:1-13` | CHROME-NATIVE |
| Side Panel API + `sidePanel` permission | `extension/manifest.json:20-22`, `extension/manifest.json:30` | CHROME-NATIVE |
| Action click opens side panel via `chrome.sidePanel.setPanelBehavior` | `extension/background.js:3-5` | CHROME-NATIVE |
| Permissions: `activeTab`, `identity`, `nativeMessaging`, `sidePanel`, `storage`, `tabs` | `extension/manifest.json:26-33` | CHROME-NATIVE |
| Host permissions for loopback + Google APIs | `extension/manifest.json:34-39` | CHROME-NATIVE |
| OAuth2 / Identity for Google sign-in | `extension/manifest.json:40-47`, `extension/identity.js:14-109` | CHROME-NATIVE |
| Native Messaging host `com.scrapex.engine` | `extension/transport.js:20-150` | CHROME-NATIVE |
| Panel width minimum (~320 px) and overflow containment | `extension/app.css:17-18`, `738-751` | EXTENSION PROFILE |
| No persistent long-lived port; panel re-reads state on reconnect | `extension/transport.js:16-18` | EXTENSION PROFILE |

---

## 15. Global Candidates

### Global Brand Candidates

| Finding | Rationale |
|---|---|
| ScrapeX teal accent (`#00adb5` / `#35c8ce`) | Strong product-family identifier within ScrapeX; may become a **product brand** token, not necessarily the umbrella MbiX brand. |
| Custom `x-mark.svg` brand mark | Used as CSS mask for logo across surfaces. |

### Global Semantic Candidates

| Concept | Evidence |
|---|---|
| `primary` / `on-primary` / `primary-container` / `on-primary-container` | M3 aliases in `tokens.css`. |
| `surface` / `on-surface` / `surface-subtle` / `surface-raised` | Generic elevation roles. |
| `success` / `warning` / `error` / `info` | ScrapeX maps these to accent/amber/red/info banners. |
| `disabled`, `focus`, `border`, `line`, `muted` | Already tokenized. |
| Status semantics: `ready`, `warning`, `error`, `pending`, `loading`, `disabled`, `running` | Engine/runtime state mapping. |

### Shared Component Contract Candidates

| Component | Evidence |
|---|---|
| Button (primary, ghost, danger, link, icon, compact) | `design/components.css:345-489` |
| Input / select / textarea | `design/components.css:490-540` |
| Checkbox / radio (native + row wrappers) | `design/components.css:531-540`, `.source-selection-row` |
| Switch | `.appearance-switch` |
| Segmented control | `.appearance-scheme-picker` |
| Card / banner | `.card`, `.banner` |
| Chip / badge / dot | `.chip`, `.badge`, `.dot` |
| List / settings row | `.srow` |
| Empty state | `.empty` |
| Split button | `.split-button` + `split-button.js` |
| Icon system (`sx-icon`, Material sprite) | `design/components.css:126-144` |
| Appearance editor | `.appearance-editor` |
| Timezone display contract | `timezone.js`, `_time.html`, `/api/timezone` |

---

## 16. Extension Profile Characteristics

These are patterns that belong to the **Chrome extension as a platform client**, not to a global design system.

- **Right-side icon rail** with grouped tablists and sliding indicator (`extension/app.html:1517-1632`, `extension/app.css:966-1048`).
- **Narrow side-panel layout** (min ~320 px, `overflow: hidden`, `* { min-width: 0; }`).
- **Workspace launcher sheet** opening full pages in new tabs.
- **Active crawl miniplayer** fixed at the bottom of the content column (`extension/app.html:1494-1515`).
- **Touch-target override** `--control-height: var(--touch-target)` (48 px) for panel buttons/select triggers.
- **Icon-only rail items** with visually-hidden labels.
- **Profile/Engine/Source/Run/Data/Finance panel workflow** shaped by the side-panel real estate.
- **Google Identity sign-in button** and profile avatar fallback.
- **Native-messaging-driven** start / repair / upgrade actions.

---

## 17. ScrapeX-Specific Characteristics

These concepts are meaningful only inside the ScrapeX product domain.

- **Source / offer / dataset / observation / crawl** domain model.
- **Source identity component** display order (domain → English → Arabic → key → metric).
- **Run workflow:** Choose sites → Run mode → Start update / crawl / rebuild / history backfill (`scrapex/ui_manifest.py` `RUN_MODE_OPTIONS`).
- **Activity panel / live log / job miniplayer** specific to crawl monitoring.
- **Google Finance rate refresh UI**.
- **Capability ledger** (`crawl_pace`, `crawl_parallel_sources`, `crawl_resume`, etc.) and version handshake (`PROTOCOL_VERSION`).
- **Schema-lag banner** and "Database is behind the engine" messaging.
- **Onboarding copy** (install Python, pip install, register native host, start engine).
- **Excel / Apps Script / Google Drive destination UI**.
- **Review queue, changes, price history, compaction, retention** workflows.

---

## 18. Technical Debt / Duplication

| Issue | Evidence | Severity |
|---|---|---|
| Three physical copies of design files | `extension/`, `scrapex/webui/static/`, `design/` | Managed by sync script; intentional but still duplication risk. |
| Hard-coded values in page stylesheets | `pages/*.css`, `webui.css` | Moderate — drift from tokens. |
| Undefined `--font-sans` token | `extension/app.css:1605, 1742, 1782` | Minor — falls back to browser default. |
| `::root` typo in onboarding CSS | `extension/onboarding.css:1` | Minor — invalid selector. |
| Google button fixed px values | `design/components.css:254-292` | Low — third-party brand requirement. |
| Monolithic `grid.js` (~3,200 lines) | `scrapex/webui/static/grid.js` | Moderate — mixes data fetching, table workarounds, rendering, export, a11y patches. |
| Inline `<script>` blocks in templates | `source.html`, `datasets.html`, `excel.html`, `sync.html`, `data-model.html` | Moderate — harder to lint/cache. |
| Outdated vendor README claim | `static/vendor/README.md` says Tabulator is only on Datasets page, but `source.html` also loads it. | Low |
| Generic class names colliding with shared components | `.field`, `.state`, `.toolbar`, `.value`, `.ok`, `.err` in `manage.css` / `datasets.css` | Moderate — clashing risk. |
| `innerHTML` templating in `app.js` | `extension/app.js:18-23`, `1217-1259`, `2426-2435` | Moderate — XSS risk if escaping slips. |

---

## 19. Risks

1. **Premature globalization.** The side-panel density and right-rail navigation are Chrome-extension solutions. Forcing them onto a website or add-in would degrade those surfaces.
2. **Palette confusion.** WhatsApp/GitHub are user-selectable product profiles; treating them as global MbiX brand palettes would create false identity.
3. **Engine-state semantics are useful globally, but copy is not.** "Setup required" and "Schema lag" are ScrapeX-specific. Any global status contract should abstract to `ready`/`warning`/`error`/`pending`.
4. **Accessibility gaps in custom controls.** If the custom select or icon-only rail patterns are promoted to shared contracts, the `aria-activedescendant` and persistent-label gaps must be fixed first.
5. **Hard-coded values in page CSS.** As the design system matures, page-level sheets may silently diverge from tokens.
6. **`innerHTML` + escaping pattern.** A shared component library should avoid `innerHTML` in favor of safer DOM construction.

---

## 20. Recommended Future Mapping

| ScrapeX Evidence | Future Mapping |
|---|---|
| `tokens.css` reference tokens (spacing, radii, typography, motion, z-index) | Adopt as **global reference tokens** after comparison with mbiXsite/mbiXaddin. |
| `tokens.css` semantic tokens (surface, text, line, accent, success/warning/error) | Adopt as **global semantic tokens**, but expect profile-specific values. |
| M3 aliases (`primary`, `on-surface`, etc.) | Keep as a **shared semantic vocabulary**; map to global tokens. |
| Buttons, inputs, cards, chips, badges, empty states | Promote to **shared component contracts**. |
| Custom select, switch, segmented control | Promote behavior to **shared contract** after fixing a11y gaps. |
| Right-side rail, workspace launcher, miniplayer | Keep as **Extension Profile**; do not globalize. |
| Source identity, run workflow, activity log | Keep as **ScrapeX-Specific**. |
| Engine status semantics (`ready`/`warning`/`error`/`pending`/`disabled`) | Extract into a **global status-semantic contract**; presentation stays product-level. |
| WhatsApp/GitHub palettes | Keep as **ScrapeX product profiles**; global theme system should allow profile registration. |
| Device color mode | Keep as **Extension / Platform Profile** capability; concept is reusable. |
| `appearance.js` sync protocol (`/api/appearance`) | Use as a **shared cross-surface theme-sync contract** where applicable. |

---

*End of SCRAPEX_UI_AUDIT.md*
