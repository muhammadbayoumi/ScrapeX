# ScrapeX Harvester — Chrome extension

The **face** of ScrapeX: capture prices from the page you're on and browse your
warehouse — all driven by the local `scrapex` backend (which owns `harvest.db`,
the connectors, and the price history). The extension never parses site data
itself; it triggers the backend.

## Load it (owner + each team member)

1. Start the local backend on your machine:
   ```powershell
   cd path\to\ScrapeX
   pip install -e .[ui]
   scrapex ui --no-open        # serves http://127.0.0.1:8000
   ```
2. Chrome → `chrome://extensions` → enable **Developer mode** →
   **Load unpacked** → select this `extension/` folder.
3. Click the ScrapeX icon. The header shows **متصل** when it reaches the backend.

## What it does

- **Current site** — if the tab you're on is a known source, a **التقاط** button
  runs that source's connector and ingests into your warehouse.
- **Sources list** — capture any implemented source with one click; shows the
  price count each already has.
- **تصفّح المستودع** — opens the local browse UI (the same FastAPI app).
- **Server settings** — point the extension at a different `scrapex` backend URL
  (default `http://127.0.0.1:8000`) so a team member can use their own local one.

## Notes

- The backend is bound to `127.0.0.1` — local only. The extension talks to it
  over `http://127.0.0.1/*` (declared in `host_permissions`).
- The token/write path stays on your machine; the extension holds no secrets.
- DOM capture for JS-heavy / logged-in pages (extract the rendered page in-browser
  and POST rows) is a later addition — today's capture reuses the Python
  connectors for the sites with open APIs.
