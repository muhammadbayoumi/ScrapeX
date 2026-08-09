# ScrapeX → MbiX Design System Mapping

**Repository audited:** `C:/Users/User01/source/repos/ScrapeX`  
**Purpose:** Map every significant UI/design concept discovered in ScrapeX into the corrected MbiX classification buckets, reflecting owner decisions from the documentation correction pass.  
**Rule:** Read-only audit evidence only. No production code modified.

---

## Owner Decisions Recorded

1. **Palette registry architecture:**
   - `brand` is the default palette.
   - `alternatives` is an extensible collection of optional palettes.
   - `blue` is the first registered entry inside `alternatives`.
   - Additional alternative palettes may be registered later.
   - Every registered palette provides `light` and `dark` schemes.
   - Device/System selects the effective scheme; it is **not** a palette.
   - Future canonical concept/file: `color-palettes`.
2. **Teal is deprecated.** Any remaining teal values are **legacy color residue / future migration debt**. Teal is **not** ScrapeX brand, MbiX global brand, a future palette, or global token evidence.
3. **Production identifiers:** `whatsapp` and `github` remain untouched **legacy compatibility aliases** for `brand` and the first `alternatives` entry (`blue`).
4. **Components consume semantic roles** (`accent`, `on-accent`, `surface`, `on-surface`, etc.) and must not depend directly on `brand`, `blue`, or future palette identifiers.
5. **Shared inside ScrapeX ≠ global MbiX contract.** Copied CSS/JS files and ScrapeX API endpoints are classified as **SCRAPEX INTERNAL SHARED LAYER**. Concepts that look reusable beyond ScrapeX are classified separately as **SHARED CONTRACT CANDIDATE**.
6. **LOCAL-WEB PROFILE** is explicit for the FastAPI/Jinja workspace surfaces.

---

## Classification Buckets

| Bucket | Meaning |
|---|---|
| **GLOBAL BRAND** | Identity-level concepts that could apply across the whole MbiX ecosystem. (None identified from ScrapeX evidence.) |
| **GLOBAL SEMANTIC** | Meaning-based concepts (colors, states, roles) that are product-agnostic. |
| **SHARED CONTRACT CANDIDATE** | Concepts with existing ScrapeX evidence that could become MbiX-wide shared contracts after comparison with other products. |
| **SCRAPEX INTERNAL SHARED LAYER** | Files, APIs, and modules physically shared between the ScrapeX extension and local Web UI, but not automatically global MbiX contracts. |
| **SCRAPEX PRODUCT INTEGRATION CONTRACT** | Cross-surface contracts that tie the ScrapeX extension and engine/local Web UI to ScrapeX-specific behavior. |
| **EXTENSION PROFILE** | Chrome extension-specific patterns that should stay in the extension domain. |
| **LOCAL-WEB PROFILE** | FastAPI/Jinja local workspace-specific patterns (sidebar, responsive drawer, data pages, logs, jobs, review, schema, exports). |
| **PRODUCT-SPECIFIC** | Domain model and workflows unique to the ScrapeX product. |
| **CHROME-NATIVE** | Chrome platform APIs and constraints, not design-system concepts. |
| **LEGACY** | Backwards-compatibility, outdated patterns, or deprecated values. |
| **PENDING OTHER PRODUCT AUDITS** | Cannot decide globally until mbiXsite, mbiXaddin, Xadd-in, Local Web UI, and mobile are audited. |

---

## 1. Global Brand

| Concept | Evidence | Notes |
|---|---|---|
| *None identified from ScrapeX evidence.* | — | ScrapeX's brand mark (`x-mark.svg`) and `brand` palette are product-level identifiers, not proven global MbiX brand candidates. |

## 2. Global Semantic

| Concept | Evidence | Notes |
|---|---|---|
| Light / Dark scheme selection | `extension/appearance.js:100-106`, `design/tokens.css:161-232` | Generic scheme concept. Device/System selects the effective scheme. |
| Primary / on-primary / primary-container / on-primary-container | `design/tokens.css:121-124` | M3 semantic roles. |
| Surface / on-surface / surface-subtle / surface-raised | `design/tokens.css:12-15`, `114-116` | Generic elevation/surface roles. |
| Outline / outline-variant | `design/tokens.css:119-120` | Generic border roles. |
| Success / ready | `.dot.on`, `.ok-text`, `.badge.ok` | Candidate global status semantic. |
| Warning | `.card.warn`, `.banner`, `.chip.amber`, `.badge.off`, `.dot` default | Candidate global status semantic. |
| Error / danger | `.card.warn`, `.banner.danger`, `.chip.danger`, `.badge.danger`, `.dot.off` | Candidate global status semantic. |
| Info | `.banner.info`, `.card.hi` | Candidate global status semantic. |
| Disabled | `button:disabled`, `.button[aria-disabled="true"]` | Candidate global action state. |
| Focus | `--focus`, `focus-visible` outline | Candidate global interactive state. |
| Loading / pending | `.skeleton`, checking states, indeterminate progress | Candidate global feedback state. |
| Running | Job running / miniplayer | Candidate global execution state. |
| Connected / disconnected / offline | Engine reachability states | Candidate global connectivity state. |
| Ready | Engine connected + compatible + DB healthy | Candidate global readiness state. |

## 3. Shared Contract Candidate

Concepts that already exist in ScrapeX and could become MbiX-wide contracts once other products are audited.

| Concept | Evidence | Notes |
|---|---|---|
| Button primitives (primary, ghost, danger, link, icon, compact) | `design/components.css:345-489` | Generic action vocabulary. |
| Input / select / textarea primitives | `design/components.css:490-540` | Generic form control vocabulary. |
| Checkbox / radio row wrappers | `design/components.css:531-540`, `.source-selection-row` | Generic selection pattern. |
| Switch / toggle | `.appearance-switch` (`design/components.css:1215-1277`) | Generic on/off control. |
| Segmented control | `.appearance-scheme-picker` (`design/components.css:1001-1077`) | Generic single-select group. |
| Extensible palette registry concept | `color-palettes` with `brand` default + `alternatives` collection | Generic theme architecture candidate; `blue` is first alternative entry in ScrapeX. |
| Card | `.card`, `.card.hi`, `.card.warn` (`design/components.css:295-326`) | Generic surface/container. |
| Banner / alert | `.banner`, `.banner.info`, `.banner.danger` (`design/components.css:328-343`) | Generic status block. |
| Chip / badge / dot | `.chip`, `.badge`, `.dot` (`design/components.css:575-631`, `616-631`) | Generic status/label indicators. |
| List / settings row | `.srow` (`design/components.css:639-654`) | Generic row container. |
| Empty state | `.empty` (`design/components.css:899-903`) | Generic empty feedback. |
| Icon button / icon tile | `.icon-button` (`design/components.css:445-461`), `.icon-tile` (`210-235`) | Generic icon-driven affordances. |
| Split button | `.split-button` + `split-button.js` (`design/components.css:1310-1451`) | Generic primary + menu action. |
| Semantic token vocabulary | `design/tokens.css:11-143` | Roles such as surface, on-surface, line, focus, disabled. |
| Reference token vocabulary | `design/tokens.css:57-111` | Spacing, radii, typography, motion, z-index. |
| M3 semantic aliases | `design/tokens.css:113-129` | `primary`, `on-primary`, `surface-container`, `outline`, `switch-track`, etc. |
| Focus-visible outline pattern | `design/components.css:557-567` | Generic accessible focus style. |
| Reduced motion / forced-colors support | `design/components.css:925-948` | Generic accessibility behavior. |

## 4. ScrapeX Internal Shared Layer

Files, modules, and endpoints physically shared between the ScrapeX extension and the local Web UI. These keep the two ScrapeX surfaces consistent but are not automatically MbiX global contracts.

| Concept | Evidence | Notes |
|---|---|---|
| `design/tokens.css` → `extension/tokens.css` + `scrapex/webui/static/tokens.css` | `tools/sync_design_assets.py:31-34` | Shared token file inside ScrapeX. |
| `design/components.css` → `extension/components.css` + `scrapex/webui/static/components.css` | `tools/sync_design_assets.py:35-38` | Shared component CSS inside ScrapeX. |
| `design/appearance.js` → both surfaces | `tools/sync_design_assets.py:21-24` | Shared theme engine inside ScrapeX. |
| `design/split-button.js` → both surfaces | `tools/sync_design_assets.py:27-30` | Shared split-button behavior inside ScrapeX. |
| Material Symbols SVG sprite copies | `tools/sync_design_assets.py:39-46` | Shared icon sprite inside ScrapeX. |
| `x-mark.svg` and `google-g.png` copies | `tools/sync_design_assets.py:50-57` | Shared brand/third-party assets inside ScrapeX. |
| `scrapex/ui_manifest.py` | `scrapex/ui_manifest.py:58-114` | Single source of truth for ScrapeX navigation and run modes. |
| `/api/ui` endpoint | `scrapex/webui/app.py` serves `ui_manifest()` | Payload consumed by the ScrapeX panel. |
| `/api/appearance` + `/api/timezone` | `scrapex/webui/app.py:98-188`, `extension/appearance.js:322-377`, `extension/timezone.js` | ScrapeX preference-sync endpoints. |
| `timezone.js` + `_time.html` | `scrapex/webui/templates/_time.html`, `extension/timezone.js` | Shared ScrapeX time-display implementation. |
| `ScrapeXUI.icon` helper | `scrapex/webui/static/ui.js` | Shared ScrapeX icon helper. |
| `design/gallery.html` | `design/gallery.html` | ScrapeX-internal UI kit catalogue. |

## 5. ScrapeX Product Integration Contract

Cross-surface contracts that are specifically about integrating the ScrapeX extension with the ScrapeX engine/local Web UI.

| Concept | Evidence | Notes |
|---|---|---|
| `PROTOCOL_VERSION` handshake | `extension/transport.js:25`, `scrapex/native.py:48` | Extension-engine protocol contract. |
| `/api/health` shape (`running`, `version`, `protocol_version`, `databases`, `sources_with_data`) | `extension/engine.js:20-47`, `scrapex/webui/app.py` | Engine health payload contract. |
| `/api/version` + capability report | `extension/version.js`, `scrapex/version.py:318-368` | Version/capability negotiation. |
| `contracts/version-vectors.json` | `contracts/version-vectors.json` | Cross-language capability problem test vectors. |
| `contracts/capability-baseline.json` | `contracts/capability-baseline.json` | ScrapeX capability baseline. |
| Native-host manifest allowlist reused for CORS | `scrapex/webui/app.py:273-296`, `scrapex/nativehost.py:86-104` | Extension-origin access contract. |
| `/api/native-host/register` | `scrapex/webui/app.py:848-881` | Allowlist repair contract. |

## 6. Extension Profile

| Concept | Evidence | Notes |
|---|---|---|
| Right-side icon navigation rail | `extension/app.html:1517-1632`, `extension/app.css:966-1048` | Chrome side-panel navigation pattern. |
| Sliding rail indicator | `extension/app.css:1002-1018`, `extension/app.js:143-150` | Side-panel active-state pattern. |
| Rail keyboard arrow navigation | `extension/app.js:3434-3445` | Side-panel interaction pattern. |
| Workspace launcher sheet | `extension/app.html:1637-1654`, `extension/app.js:156-186` | Extension-to-workpage launcher. |
| Active crawl miniplayer | `extension/app.html:1494-1515`, `extension/app.css:942-963` | Persistent job progress in panel. |
| Narrow panel width constraints (~320 px min) | `extension/app.css:17-18`, `738-751`, `1825-1844` | Side-panel viewport constraint. |
| 48 px touch-target override | `extension/app.css:6` (`--control-height: var(--touch-target)`) | Compact Android-style panel targets. |
| Icon-only rail items with `title` + visually-hidden label | `extension/app.html:1525-1631` | Side-panel icon density pattern. |
| Profile / Engine / Source / Run / Data / Finance panel views | `extension/app.html:26-1490` | Side-panel workflow chrome. |
| Google Identity avatar fallback in rail | `extension/app.html:1533-1537` | Extension-specific account surface. |
| Native-messaging action UI (start engine, upgrade DB, autostart) | `extension/transport.js`, `extension/app.js:3061-3136` | Extension-to-engine control surface. |
| Version notice / refusal card at top of panel | `extension/app.js:446-542`, `2052-2069` | Panel-specific compatibility gate. |
| Onboarding page layout | `extension/onboarding.html`, `extension/onboarding.css` | First-install extension page. |

## 7. Local-Web Profile

| Concept | Evidence | Notes |
|---|---|---|
| FastAPI/Jinja2 server-rendered workspace | `scrapex/webui/app.py:22-28`, `templates/base.html` | Local web app architecture. |
| Fixed left sidebar navigation | `templates/base.html:22-56`, `scrapex/webui/static/webui.css:68-100` | Workspace wayfinding shell. |
| Grouped sidebar nav from `ui_manifest.py` | `scrapex/ui_manifest.py:58-95` | Browse / Automation / Outputs / System grouping. |
| Mobile drawer (< 900 px) | `scrapex/webui/static/webui.css:116-138` | Responsive local-web navigation. |
| Workspace footer with engine/DB health | `templates/base.html:79-101` | Local-web status footer. |
| Wide-page / wrap-wide layout | `scrapex/webui/static/webui.css:16-19` | Local-web content layout. |
| Settings category vertical tablist | `templates/settings.html:28-61`, `scrapex/webui/static/pages/settings.css` | Local-web settings navigation. |
| Tabulator-based data grids | `scrapex/webui/static/grid.js`, `grid-theme.css`, `templates/source.html`, `templates/datasets.html` | Local-web data browsing surface. |
| Data model diagram page | `scrapex/webui/static/pages/data-model.js`, `templates/data_model.html` | Local-web warehouse diagram. |
| Jobs / schedules / logs / review / schema / export pages | `templates/jobs.html`, `schedules.html`, `logs.html`, `review.html`, `schema.html`, `exports.html`, `excel.html` | Deep local-web surfaces. |
| Database unavailable fallback page | `templates/database_unavailable.html` | Local-web DB error surface. |

## 8. Product-Specific

| Concept | Evidence | Notes |
|---|---|---|
| Source / offer / dataset / observation / crawl domain | `scrapex/`, `sources.yaml` | Core ScrapeX domain. |
| Custom `x-mark.svg` brand mark | `extension/icons/x-mark.svg`, `scrapex/webui/static/x-mark.svg`, `--brand-mark` | ScrapeX product logo. |
| "Local-first data workspace" tagline | `templates/base.html:82` | ScrapeX product positioning. |
| Source identity display order | `design/components.css:661-772`, `templates/_source_identity.html` | Domain-specific identity component. |
| Run workflow (update / initial crawl / full rebuild / history backfill) | `scrapex/ui_manifest.py:100-114`, `extension/app.html:89-119` | ScrapeX workflow. |
| Site selection checklist | `extension/app.html:57-76`, `extension/app.js:1217-1259` | Run-view selection pattern. |
| Activity panel / live log / job progress | `extension/app.html:122-183`, `extension/app.js:2120-2406` | Crawl monitoring UI. |
| Google Finance rate UI | `extension/app.html`, `extension/app.js:730-968` | ScrapeX integration. |
| Capability ledger keys | `scrapex/version.py:113-193` | ScrapeX capability model. |
| Schema-lag banner | `extension/app.js:366-386` | ScrapeX migration state. |
| Excel / Apps Script / Google Drive destination UI | `templates/sync.html`, `excel.html`, `exports.html` | ScrapeX output integrations. |
| Review queue / changes / price history | `templates/review.html`, `changes.html`, `history.html` | ScrapeX curation workflows. |
| Compaction / retention / storage settings | `templates/settings.html`, `_storage.html`, `_retention.html` | ScrapeX lifecycle UI. |

## 9. Chrome-Native

| Concept | Evidence | Notes |
|---|---|---|
| Manifest V3 | `extension/manifest.json:2` | Platform version. |
| `side_panel` permission & default path | `extension/manifest.json:20-22`, `30` | Platform API. |
| `background.service_worker` | `extension/manifest.json:26` | Platform runtime. |
| `activeTab`, `identity`, `nativeMessaging`, `storage`, `tabs` permissions | `extension/manifest.json:26-33` | Platform permissions. |
| OAuth2 client id & scopes | `extension/manifest.json:40-47` | Platform identity. |
| `chrome.sidePanel.setPanelBehavior` | `extension/background.js:3-5` | Platform side-panel behavior. |
| `chrome.runtime.sendNativeMessage` | `extension/transport.js:20-150` | Platform native messaging. |
| `chrome.identity.getAuthToken` | `extension/identity.js:71-77` | Platform sign-in. |
| `chrome.storage.local` | `extension/engine.js:10-16` | Platform storage. |
| Host permissions for loopback / Google APIs | `extension/manifest.json:34-39` | Platform security model. |
| Extension origin allowlist / CORS regex | `scrapex/webui/app.py:265-296` | Platform access control. |

## 10. Legacy

| Concept | Evidence | Notes |
|---|---|---|
| Teal accent (`#00adb5` / `#35c8ce`) | `design/tokens.css:24` | **Deprecated legacy color residue.** Not ScrapeX brand, not global brand, not a future palette. |
| `whatsapp` palette identifier | `extension/appearance.js:8-56` | Legacy implementation alias for the default `brand` palette. |
| `github` palette identifier | `extension/appearance.js:57-99` | Legacy implementation alias for the first `alternatives` entry (`blue`). |
| `scrapex-appearance-v1` localStorage key | `extension/appearance.js:5`, `150-155` | Backwards-compatibility fallback. |
| Grid localStorage v1 → v2 key migration | `scrapex/webui/static/grid.js` | Old saved preferences. |
| `ensure_schema()` single-file warehouse migration | `scrapex/db.py` | Old DB shape support. |
| Hard-coded px/rem values in page CSS | `pages/*.css`, `webui.css` | Pre-token styling residue. |
| Undefined `--font-sans` usage | `extension/app.css:1605, 1742, 1782` | Mistyped / stale token. |
| `::root` typo | `extension/onboarding.css:1` | Invalid selector. |
| Outdated vendor README (Tabulator usage claim) | `scrapex/webui/static/vendor/README.md` | Documentation drift. |

## 11. Pending Other Product Audits

| Concept | Why Pending |
|---|---|
| Exact global accent color | Need comparison with mbiXsite/mbiXaddin brand colors. The ScrapeX `brand` palette is product-level. |
| Global typography scale (font family, sizes, weights) | Website uses monospace as profile characteristic; ScrapeX uses Segoe UI. Need reconcile. |
| Global density profile | Website is comfortable/editorial; ScrapeX is compact/dense. Need decide if global system supports multiple density profiles. |
| Global radius / shadow language | ScrapeX radii may be product-specific; need compare. |
| Global button shape (pill vs rounded rect) | Website uses pill CTAs; ScrapeX uses rounded rect (`--radius`). Need decide. |
| Global navigation pattern (rail vs sidebar vs top nav) | Need see mbiXaddin / Local Web UI / mobile. |
| Global icon system (Material Symbols vs custom) | Need compare with mbiXsite iconography. |
| Global theme palette strategy (default + extensible alternatives registry, device colors) | Need see how mbiXsite handles color styles and whether it supports a `brand` + `alternatives` registry model. |
| Global status component names (Banner vs Alert vs Status) | Need compare vocabulary across products. |
| Global form control sizing / touch targets | Need compare add-in and mobile requirements. |

---

## Summary Matrix

| Category | Count of Concepts | Strongest Examples |
|---|---|---|
| **GLOBAL BRAND** | 0 | None identified from ScrapeX evidence. |
| **GLOBAL SEMANTIC** | 16 | primary/on-primary, surface, success/warning/error, ready/pending/disabled |
| **SHARED CONTRACT CANDIDATE** | 16 | buttons, inputs, cards, banners, chips, badges, switches, segmented controls, semantic/reference tokens |
| **SCRAPEX INTERNAL SHARED LAYER** | 12 | tokens.css, components.css, appearance.js, split-button.js, icon sprite, ui_manifest.py, /api/ui, /api/appearance, /api/timezone |
| **SCRAPEX PRODUCT INTEGRATION CONTRACT** | 6 | PROTOCOL_VERSION, /api/health, /api/version, version-vectors.json, capability-baseline.json, native-host allowlist |
| **EXTENSION PROFILE** | 12 | right-side rail, launcher sheet, miniplayer, 48 px targets, onboarding, refusal card |
| **LOCAL-WEB PROFILE** | 11 | FastAPI/Jinja shell, left sidebar, mobile drawer, Tabulator grids, data model, jobs/logs/review/schema/exports |
| **PRODUCT-SPECIFIC** | 18 | source identity, run workflow, activity log, Google Finance, capability ledger, x-mark brand mark |
| **CHROME-NATIVE** | 11 | MV3, sidePanel API, native messaging, identity, storage |
| **LEGACY** | 10 | teal, whatsapp/github aliases (for `brand` / first `alternatives` entry), appearance-v1, hard-coded values, `--font-sans`, `::root` typo |
| **PENDING** | 10 | accent color, typography, density, radius, nav pattern, icon system, palettes |

---

*End of SCRAPEX_GLOBAL_MAPPING.md*
