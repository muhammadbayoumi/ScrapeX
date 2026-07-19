# ScrapeX — Chrome extension (the interface)

The **interface** of ScrapeX lives here, permanently installed in Chrome. The
**engine** (Python) runs on your machine and owns the warehouse (`harvest.db`),
the connectors, and the price history. The extension never parses site data — it
drives the engine over its local JSON API.

- **One UI, always available:** click the ScrapeX toolbar icon → the **side panel**
  opens (`app.html`) — the full control panel. From it you add sites, capture
  prices, see your data, and open the deep browse/manage views.
- **Engine detection:** the panel (and `onboarding.html`, opened on first install)
  check `GET /api/health`. If the engine isn't running they show setup steps and
  auto-detect the moment you start it — so you always know you must install/run
  the Python engine.
- **Language:** UI is English; Arabic scraped content renders correctly via
  `unicode-bidi:plaintext`.

## Install

1. Start the engine on your machine (until the one-click installer ships):
   ```powershell
   cd path\to\ScrapeX
   pip install -e .[ui]
   scrapex ui --no-open        # serves http://127.0.0.1:8000
   ```
2. Chrome → `chrome://extensions` → **Developer mode** → **Load unpacked** →
   select this `extension/` folder.
3. Click the ScrapeX icon → the side panel opens. Its header shows the engine
   status + version once connected.

## The control panel (`app.html`, side panel)

- **Add a site** — paste a URL → Check (probe detects the platform) → Add.
- **Current tab** — if you're on one of your sites, a **Capture now** button; if
  not, an **Add this site** shortcut.
- **Your sites** — capture any ready source; price counts per site.
- **Your data** — Browse price tables / Advanced manage (open the engine's views).
- **Engine settings** — point at a different engine URL; the note states data
  never leaves your machine.

## Files

`manifest.json` (side_panel + sidePanel permission) · `background.js` (icon→panel,
onboarding on install) · `app.html`/`app.js` (the control panel) ·
`onboarding.html`/`onboarding.js` (first-run + engine setup) · `engine.js`
(shared `checkEngine`/backend helpers).

## Notes

- The engine is bound to `127.0.0.1` — local only; the extension talks to it over
  `http://127.0.0.1/*` (`host_permissions`). No secrets in the extension.
- Transport today is HTTP-localhost; a **Native Messaging** variant (Chrome
  auto-launches the engine) is a planned upgrade — the UI states are unchanged.
- DOM capture for JS-heavy / logged-in pages (extract the rendered page and POST
  rows) is a later addition; today's capture reuses the Python connectors.
