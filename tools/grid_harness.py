"""Load the Data page's grid in a real browser, with its server stubbed.

The grid is 3,000 lines of behaviour — sorting, a set filter, auto-fit, a column
chooser — and until now the only thing testing it was `assert "..." in script`
against grid.js read as TEXT. A substring check catches a renamed literal (it
did, once) and cannot catch a single behavioural regression: every defect the
owner reported was invisible to it.

This is the same trick `panel_harness.py` plays for the extension panel, aimed
at the other surface. It writes ONE self-contained page from grid.js and its
vendored library, hands it a payload through a stubbed `fetch`, and lets a real
browser lay it out — so a test can ask what the table actually did rather than
what the source code says.

The payload is a fixture, not a database. That is the point: a test can hand the
grid a column of numbers with a blank in the first row, or a product name made
of markup, without a crawl, a migration, or a running server.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "scrapex" / "webui" / "static"
TEMPLATES = ROOT / "scrapex" / "webui" / "templates"

# The page chrome grid.js binds to. Kept here as ONE list so the harness and the
# real template cannot drift apart quietly: test_grid_dom asserts every id below
# also exists in source.html, which is the contract this file stands in for.
REQUIRED_IDS = (
    "grid", "grid-note", "grid-chips", "grid-toolbar", "grid-features",
    "offer-panel", "grid-columns-button",
)


def _host_dom(source_key: str) -> str:
    """The minimum page chrome the grid expects, mirroring source.html."""
    return f"""
<div class="data-grid-frame">
  <div class="data-grid-commandbar">
    <details id="grid-features">
      <summary>Grid Features</summary>
      <div class="grid-feature-popover">
        <div class="featuregrid">
          <label><input type="checkbox" data-feature="tree"> Row Grouping</label>
          <label><input type="checkbox" data-feature="rows"> Nested Rows</label>
          <label><input type="checkbox" data-feature="select"> Row Selection</label>
          <label><input type="checkbox" data-feature="rownum"> Row Numbers</label>
          <label><input type="checkbox" data-feature="totals"> Column Totals</label>
          <label><input type="checkbox" data-feature="compact"> Compact Rows</label>
          <label><input type="checkbox" data-feature="wrap"> Wrap Long Text</label>
          <label><input type="checkbox" data-feature="stripe"> Striped Rows</label>
          <label><input type="checkbox" data-feature="statusbar"> Status Bar</label>
        </div>
      </div>
    </details>
    <button type="button" id="grid-columns-button">Columns</button>
  </div>
  <p id="grid-note" hidden></p>
  <p id="grid-chips"></p>
  <div class="data-grid-viewport" data-grid-viewport>
    <div id="grid" class="tablewrap" data-source="{source_key}"></div>
  </div>
  <div id="grid-toolbar" class="toolbar">
    <div class="split-button">
      <button type="button" class="split-button-primary" data-split-action="xlsx">Excel</button>
      <details class="split-button-menu">
        <summary class="split-button-trigger">Export</summary>
        <div class="split-button-options">
          <button type="button" class="split-button-option" data-split-action="csv">CSV</button>
          <button type="button" class="split-button-option" data-split-action="json">JSON</button>
        </div>
      </details>
    </div>
  </div>
  <section id="offer-panel" class="record-panel" tabindex="-1" hidden></section>
</div>
"""


def _stub_fetch(payload: dict, fields: dict, promotable: dict, offer: dict) -> str:
    """Answer the four endpoints the grid calls, and record every POST.

    POSTs are captured rather than applied: a test asserting that unticking a
    column SAVES it should assert on the request, not on a fake server's
    imitation of the real one.
    """
    return (
        "window.__posts = [];\n"
        f"window.__payload = {json.dumps(payload)};\n"
        f"window.__fields = {json.dumps(fields)};\n"
        f"window.__promotable = {json.dumps(promotable)};\n"
        f"window.__offer = {json.dumps(offer)};\n"
        """
// Keys are matched against "<METHOD> <url>", so a test can break the SAVE while
// letting the LOAD succeed: "POST /api/fields/" stops a column choice being
// stored without also stopping the dialog from listing the columns it is
// trying to store. A bare path still matches either method.
window.__fetchFailures = {};
window.fetch = function (url, options) {
  const path = String(url);
  const method = (options && options.method) || "GET";
  const signature = method + " " + path;
  const body = options && options.body ? JSON.parse(options.body) : null;
  if (method === "POST") window.__posts.push({path, body});
  for (const needle of Object.keys(window.__fetchFailures)) {
    if (signature.includes(needle) || path.includes(needle)) {
      return Promise.resolve({ok: false, status: window.__fetchFailures[needle],
                              json: () => Promise.resolve({})});
    }
  }
  const answer = (value) =>
    Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(value)});
  if (path.includes("/api/table/")) return answer(window.__payload);
  if (path.includes("/api/fields/")) return answer(window.__fields);
  if (path.includes("/api/promotable/")) return answer(window.__promotable);
  if (path.includes("/api/offer/")) return answer(window.__offer);
  return answer({});
};
// A rebuild in grid.js ends in location.reload() for anything the SERVER owns.
// Reloading a harness page would drop the test's stubs, so it is recorded
// instead — a test can then assert that a reload was asked for.
window.__reloads = 0;
try {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: new Proxy(window.location, {
      get: (target, key) =>
        key === "reload" ? () => { window.__reloads += 1; } : Reflect.get(target, key),
    }),
  });
} catch (err) { /* some engines refuse; the reload tests then simply skip */ }
"""
    )


def build_page(tmp: Path, payload: dict, *, source_key: str = "TESTSRC",
               fields: dict | None = None, promotable: dict | None = None,
               offer: dict | None = None, name: str = "grid.html") -> Path:
    """Inline the grid's own CSS and JS into one file so file:// can load it."""
    vendor_css = (STATIC / "vendor" / "tabulator.min.css").read_text(encoding="utf-8")
    vendor_js = (STATIC / "vendor" / "tabulator.min.js").read_text(encoding="utf-8")
    tokens_css = (STATIC / "tokens.css").read_text(encoding="utf-8")
    components_css = (STATIC / "components.css").read_text(encoding="utf-8")
    table_css = (STATIC / "table-theme.css").read_text(encoding="utf-8")
    grid_css = (STATIC / "grid-theme.css").read_text(encoding="utf-8")
    ui_js = (STATIC / "ui.js").read_text(encoding="utf-8")
    # The Export control's split button is the SHARED component: its styles live
    # in components.css and its behaviour in split-button.js, so the harness must
    # carry both or grid.js's wireExport calls into an undefined global.
    split_button_js = (STATIC / "split-button.js").read_text(encoding="utf-8")
    grid_js = (STATIC / "grid.js").read_text(encoding="utf-8")

    # The icon helper resolves <use href="/static/..."> against the server. On
    # file:// that 404s silently and every icon renders empty, which is fine for
    # behaviour but breaks measureHeaderWidth's item measurements. Inline the
    # real sprite and point the references at it.
    sprite = (STATIC / "material-icons" / "material-icons.svg").read_text(encoding="utf-8")
    sprite_body = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", sprite, flags=re.S)
    ui_js = ui_js.replace("/static/material-icons/material-icons.svg#", "#")

    stub = _stub_fetch(
        payload,
        fields if fields is not None else {"fields": []},
        promotable if promotable is not None else {"attributes": []},
        offer if offer is not None else {},
    )

    tmp.mkdir(parents=True, exist_ok=True)
    page = tmp / name
    page.write_text(
        "<!doctype html><meta charset='utf-8'><title>ScrapeX grid</title>"
        # A real, bounded viewport: fitColumns and auto-fit both measure against
        # it, so a zero-height body would make every width meaningless.
        "<style>html,body{margin:0;height:100%}"
        ".data-grid-frame{height:100%}.data-grid-viewport{height:80vh}</style>"
        f"<style>{tokens_css}</style>"
        f"<style>{components_css}</style>"
        f"<style>{vendor_css}</style>"
        f"<style>{table_css}</style>"
        f"<style>{grid_css}</style>\n"
        "<svg aria-hidden='true' width='0' height='0' "
        f"style='position:absolute;overflow:hidden'>{sprite_body}</svg>\n"
        f"{_host_dom(source_key)}\n"
        f"<script>{stub}</script>\n"
        f"<script>{vendor_js}</script>\n"
        f"<script>{ui_js}</script>\n"
        f"<script>{split_button_js}</script>\n"
        # grid.js last: it runs its fetch immediately, so the stub above and the
        # library it constructs against must both already exist.
        f"<script>{grid_js}</script>",
        encoding="utf-8")
    return page
