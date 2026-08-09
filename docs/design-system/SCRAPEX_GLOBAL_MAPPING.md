# ScrapeX → MbiX Design System Mapping

**Repository audited:** `C:/Users/User01/source/repos/ScrapeX`  
**Purpose:** Map every significant UI/design concept discovered in ScrapeX into the candidate MbiX classification buckets.  
**Rule:** Read-only audit evidence only. No production code modified.

## Classification Buckets

| Bucket | Meaning |
|---|---|
| **GLOBAL BRAND** | Identity-level concepts that could apply across the whole MbiX ecosystem. |
| **GLOBAL SEMANTIC** | Meaning-based concepts (colors, states, roles) that are product-agnostic. |
| **SHARED CONTRACT** | Reusable components, tokens, or sync contracts already shared across ScrapeX surfaces. |
| **EXTENSION PROFILE** | Chrome extension-specific patterns that should stay in the extension domain. |
| **SCRAPEX-SPECIFIC** | Domain model and workflows unique to the ScrapeX product. |
| **CHROME-NATIVE** | Chrome platform APIs and constraints, not design-system concepts. |
| **LEGACY** | Backwards-compatibility or outdated patterns. |
| **PENDING OTHER PRODUCT AUDITS** | Cannot decide globally until mbiXsite, mbiXaddin, Xadd-in, Local Web UI, and mobile are audited. |

---

## 1. Global Brand

| Concept | Evidence | Notes |
|---|---|---|
| ScrapeX teal accent (`#00adb5` / `#35c8ce`) | `design/tokens.css:24` | Strong product-family identifier; candidate for **ScrapeX product brand**, not necessarily umbrella MbiX brand. |
| Custom `x-mark.svg` brand mark | `extension/icons/x-mark.svg`, `scrapex/webui/static/x-mark.svg`, `--brand-mark` | Used as CSS mask logo across surfaces. |
| "Local-first data workspace" tagline | `templates/base.html:82` | Product positioning, not global. |

## 2. Global Semantic

| Concept | Evidence | Notes |
|---|---|---|
| Light / Dark / Device color scheme | `extension/appearance.js:100-106`, `design/tokens.css:161-232` | Generic scheme selection concept. |
| Primary / on-primary / primary-container | `design/tokens.css:121-124` | M3 semantic roles. |
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

## 3. Shared Contract

| Concept | Evidence | Notes |
|---|---|---|
| `design/tokens.css` → `extension/tokens.css` + `scrapex/webui/static/tokens.css` | `tools/sync_design_assets.py:31-34` | Token file sync contract. |
| `design/components.css` → `extension/components.css` + `scrapex/webui/static/components.css` | `tools/sync_design_assets.py:35-38` | Component CSS sync contract. |
| `design/appearance.js` → both surfaces | `tools/sync_design_assets.py:21-24` | Theme engine sync contract. |
| `design/split-button.js` → both surfaces | `tools/sync_design_assets.py:27-30` | Split-button behavior sync contract. |
| Material Symbols SVG sprite | `tools/sync_design_assets.py:39-46` | Shared icon sprite contract. |
| `sx-icon` icon component | `design/components.css:126-144` | Shared icon use pattern. |
| Button primitives (primary, ghost, danger, link, icon, compact) | `design/components.css:345-489` | Shared action contract. |
| Input / select / textarea primitives | `design/components.css:490-540` | Shared form control contract. |
| Card / banner / chip / badge / dot | `design/components.css:295-343`, `328-343`, `575-631`, `616-631` | Shared container/feedback contract. |
| `.srow` list / settings row | `design/components.css:639-654` | Shared row contract. |
| `.empty` empty state | `design/components.css:899-903` | Shared empty-state contract. |
| `.icon-tile` | `design/components.css:210-235` | Shared icon-tile contract. |
| `.appearance-editor` / `.appearance-scheme-picker` / `.appearance-switch` | `design/components.css:953-1301` | Shared appearance-control contract. |
| `.split-button` | `design/components.css:1310-1451` + `split-button.js` | Shared split-button contract. |
| `scrapex/ui_manifest.py` navigation + run modes | `scrapex/ui_manifest.py:58-114` | Shared cross-surface navigation/run-mode data contract. |
| `/api/ui` endpoint | `scrapex/webui/app.py` serves `ui_manifest()` | Shared navigation payload contract. |
| `/api/appearance` + `/api/timezone` | `scrapex/webui/app.py:98-127`, `161-188`, `extension/appearance.js:322-377`, `extension/timezone.js` | Shared preference-sync contracts. |
| `timezone.js` + `_time.html` | `scrapex/webui/templates/_time.html`, `extension/timezone.js` | Shared time-display contract. |
| `ScrapeXUI.icon` helper | `scrapex/webui/static/ui.js` | Shared icon helper. |
| Version/capability contracts (`version-vectors.json`, `capability-baseline.json`) | `contracts/` | Shared cross-language contract. |

## 4. Extension Profile

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

## 5. ScrapeX-Specific

| Concept | Evidence | Notes |
|---|---|---|
| Source / offer / dataset / observation / crawl domain | `scrapex/`, `sources.yaml` | Core product domain. |
| Source identity display order | `design/components.css:661-772`, `templates/_source_identity.html` | Domain-specific identity component. |
| Run workflow (update / initial crawl / full rebuild / history backfill) | `scrapex/ui_manifest.py:100-114`, `extension/app.html:89-119` | Product workflow. |
| Site selection checklist | `extension/app.html:57-76`, `extension/app.js:1217-1259` | Run-view selection pattern. |
| Activity panel / live log / job progress | `extension/app.html:122-183`, `extension/app.js:2120-2406` | Crawl monitoring UI. |
| Google Finance rate UI | `extension/app.html`, `extension/app.js:730-968` | Domain-specific integration. |
| Capability ledger keys | `scrapex/version.py:113-193` | Product capability model. |
| Schema-lag banner | `extension/app.js:366-386` | Product migration state. |
| Excel / Apps Script / Google Drive destination UI | `templates/sync.html`, `excel.html`, `exports.html` | Product output integrations. |
| Review queue / changes / price history | `templates/review.html`, `changes.html`, `history.html` | Product curation workflows. |
| Compaction / retention / storage settings | `templates/settings.html`, `_storage.html`, `_retention.html` | Product lifecycle UI. |
| Data model / schema documentation pages | `templates/data_model.html`, `schema.html` | Product warehouse docs. |
| Tabulator-based source data grid | `scrapex/webui/static/grid.js`, `grid-theme.css` | Domain-specific data grid skin. |
| Database unavailable fallback page | `templates/database_unavailable.html` | Product DB error surface. |

## 6. Chrome-Native

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

## 7. Legacy

| Concept | Evidence | Notes |
|---|---|---|
| `scrapex-appearance-v1` localStorage key | `extension/appearance.js:5`, `150-155` | Backwards-compatibility fallback. |
| Grid localStorage v1 → v2 key migration | `scrapex/webui/static/grid.js` (reported by explore) | Old saved preferences. |
| `ensure_schema()` single-file warehouse migration | `scrapex/db.py` (reported by explore) | Old DB shape support. |
| Hard-coded px/rem values in page CSS | `pages/*.css`, `webui.css` | Pre-token styling residue. |
| Undefined `--font-sans` usage | `extension/app.css:1605, 1742, 1782` | Mistyped / stale token. |
| `::root` typo | `extension/onboarding.css:1` | Invalid selector. |
| Outdated vendor README (Tabulator usage claim) | `scrapex/webui/static/vendor/README.md` | Documentation drift. |

## 8. Pending Other Product Audits

| Concept | Why Pending |
|---|---|
| Exact global accent color | Need comparison with mbiXsite/mbiXaddin brand colors. |
| Global typography scale (font family, sizes, weights) | Website uses monospace as profile characteristic; ScrapeX uses Segoe UI. Need reconcile. |
| Global density profile | Website is comfortable/editorial; ScrapeX is compact/dense. Need decide if global system supports multiple density profiles. |
| Global radius / shadow language | ScrapeX radii may be product-specific; need compare. |
| Global button shape (pill vs rounded rect) | Website uses pill CTAs; ScrapeX uses rounded rect (`--radius`). Need decide. |
| Global navigation pattern (rail vs sidebar vs top nav) | Need see mbiXaddin / Local Web UI / mobile. |
| Global icon system (Material Symbols vs custom) | Need compare with mbiXsite iconography. |
| Global theme palette strategy (device colors, fixed palettes) | Need see how mbiXsite handles color styles. |
| Global status component names (Banner vs Alert vs Status) | Need compare vocabulary across products. |
| Global form control sizing / touch targets | Need compare add-in and mobile requirements. |

---

## Summary Matrix

| Category | Count of Concepts | Strongest Examples |
|---|---|---|
| **GLOBAL BRAND** | 2 | ScrapeX teal, x-mark logo |
| **GLOBAL SEMANTIC** | 16 | primary/on-primary, surface, success/warning/error, ready/pending/disabled |
| **SHARED CONTRACT** | 24 | tokens, components.css, appearance.js, split-button, ui_manifest.py, /api/appearance |
| **EXTENSION PROFILE** | 12 | right-side rail, launcher sheet, miniplayer, 48 px targets, onboarding |
| **SCRAPEX-SPECIFIC** | 18 | source identity, run workflow, activity log, Google Finance, capability ledger |
| **CHROME-NATIVE** | 11 | MV3, sidePanel API, native messaging, identity, storage |
| **LEGACY** | 7 | appearance-v1, hard-coded values, `--font-sans`, `::root` typo |
| **PENDING** | 10 | accent color, typography, density, radius, nav pattern, icon system, palettes |

---

*End of SCRAPEX_GLOBAL_MAPPING.md*
