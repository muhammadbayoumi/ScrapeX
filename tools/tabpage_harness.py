"""Build a runnable copy of an extension TAB page, for DOM tests.

WHY THIS EXISTS, and it is not symmetry with panel_harness.py. The Data page
shipped with a defect that every static guard passed: `load()` read the backend
generation BEFORE `backendBase()` had resolved the address, resolving it bumped
the generation, and the freshness guard then decided a different engine was
authoritative and returned WITHOUT PAINTING. Every first load did that. The page
said "Reading…" for ever, in production, and 2,460 engine tests plus 398
extension tests were green on it — because no test had ever RENDERED the page.

It was found by opening it in a browser. This is what makes that repeatable.

WHAT IT DOES NOT DO. It is not the extension. `chrome.*` is a stub and the
engine is a fixture, so this proves the page's own behaviour — its ordering, its
sentences, what it draws — and proves nothing about Chrome's permissions, the
service worker, or a real 127.0.0.1. Saying so matters: a harness mistaken for
the product is how "it passed the tests" starts meaning less than it should.

THE MODULE GRAPH IS NEVER RE-DECLARED, by either of the two mechanisms here.
The Data page is FLATTENED — imports stripped, `export` removed — the same
choice panel_harness.py makes, for the same reason: a test-only re-declaration
of a function tests the re-declaration. The Console is SERVED instead and loads
its real modules, because flattening it is not possible; see the section at the
foot of this file for the nineteen name collisions that decide it.
"""
from __future__ import annotations

import contextlib
import functools
import json
import re
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"

#: In dependency order, because flattening removes the imports that expressed it.
#: startup.js first (backend.js calls its deadline helpers), then engine.js
#: (backend.js calls getBackend), then backend.js, then the page's own modules.
DATA_PAGE_MODULES = ("startup.js", "transport.js", "engine.js", "backend.js",
                     "datatable.js", "data.js")


def flatten(source: str) -> str:
    """One module's code with its imports and `export` keywords removed."""
    source = re.sub(r"^import[\s\S]*?;\s*$", "", source, flags=re.M)
    return re.sub(r"\bexport\s+", "", source)


def stub(payload: dict | None = None, *, backend: str = "http://127.0.0.1:8000",
         status: int = 200, fail: str = "") -> str:
    """The two things a plain browser tab cannot have: chrome, and an engine.

    `fail` makes the engine unreachable the way a stopped engine is — a rejected
    fetch rather than an HTTP error — because those reach the page by different
    paths and the page says different things about them.
    """
    body = json.dumps(payload or {}, ensure_ascii=False)
    return f"""
window.__ASKED__ = [];
window.chrome = {{
  storage: {{local: {{
    get: async () => ({{backend: {json.dumps(backend)}}}),
    set: async () => {{}},
  }}}},
  runtime: {{getURL: (path) => path}},
  tabs: {{create: () => {{}}}},
}};
window.fetch = async (input, options) => {{
  const url = String(input && input.url ? input.url : input);
  window.__ASKED__.push(url);
  if ({json.dumps(bool(fail))}) throw new TypeError({json.dumps(fail or "failed to fetch")});
  return new Response({json.dumps(body)}, {{
    status: {status},
    headers: {{"Content-Type": "application/json"}},
  }});
}};
"""


def build_data_page(tmp: Path, stub_js: str, name: str = "data.html") -> Path:
    """A single self-contained file that runs the real Data page.

    WHICH SOURCE IT SHOWS IS NOT SET HERE. Open it with a query string —
    `page.goto(path.as_uri() + "?source=KEY")` — because a file:// URL carries
    one perfectly well and `window.location.search` then reads exactly what the
    shipped page reads. The first version of this redefined `window.location`
    instead; that property is not configurable, the assignment threw, and the
    page fell back to "no source" while looking like a harness fault.
    """
    html = (EXT / "data.html").read_text(encoding="utf-8")
    body = html.split("<body>", 1)[1].split("<script", 1)[0]

    css = "\n".join((EXT / sheet).read_text(encoding="utf-8") for sheet in
                    ("tokens.css", "components.css", "data.css"))
    grid_css = (EXT / "vendor" / "tabulator.min.css").read_text(encoding="utf-8")
    grid_js = (EXT / "vendor" / "tabulator.min.js").read_text(encoding="utf-8")
    modules = "\n".join(flatten((EXT / m).read_text(encoding="utf-8"))
                        for m in DATA_PAGE_MODULES)

    page = tmp / name
    page.write_text(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<style>{grid_css}</style><style>{css}</style></head>"
        f"<body>{body}"
        f"<script>{stub_js}</script>\n"
        f"<script>{grid_js}</script>\n"
        f"<script>{modules}</script>"
        "</body></html>",
        encoding="utf-8")
    return page


# ---- the Console -------------------------------------------------------------
#
# A DIFFERENT MECHANISM, and not by preference. The Data page above is FLATTENED,
# and the Console cannot be: its fourteen modules declare NINETEEN colliding
# top-level names between them. Six of the rule modules each declare `finding`,
# `text` and `same`; two declare `SHEETS`, `RANK`, `BAGS`, `KEY_LIMIT` and
# `checkBag`. Concatenated into one scope, the first duplicate `const` is a
# SyntaxError before a single line runs.
#
# So the Console is SERVED and loaded as the real module graph — which is the
# stronger arrangement anyway. Nothing is rewritten, the browser resolves the
# imports the shipped page declares, and the files under test are the files on
# disk rather than a transformation of them. The reason to prefer flattening is
# that it needs no server; the reason to prefer this is everything else.


class _QuietHandler(SimpleHTTPRequestHandler):
    """`SimpleHTTPRequestHandler`, minus a log line per module fetched."""

    def log_message(self, *args, **kwargs):
        pass


@contextlib.contextmanager
def serve_extension() -> Iterator[str]:
    """The shipped `extension/` directory over http. Yields its base URL.

    ES modules will not load over file:// — the browser refuses every import as
    cross-origin and the page stays blank, which looks exactly like the kind of
    defect this file exists to catch. NOTHING IS COPIED: the directory served is
    the one that ships, so a module deleted from the repository is a module
    missing from the test.
    """
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(EXT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def console_stub(rows: dict[str, list[dict]] | None = None, *,
                 title: str = "mbiX Configuration", token: str = "harness-token",
                 remembered: str | None = "FILE-1",
                 tabs: dict[str, str] | None = None, fail: str = "") -> str:
    """Chrome and Google, for a page that has neither. Feed to `add_init_script`.

    THE CONTRACT IS NOT RESTATED HERE, and that is the whole design of it. The
    two answers this stub gives — which tabs the file has, and what is in
    them — are built from `addin-contract.js` and `workbook.js`, imported at
    call time from the same directory the page was served from. A harness that
    typed the six gids and the column order out again would keep passing after
    the add-in's contract moved, which is the one thing it exists to notice.

    `rows` is keyed by tab name and holds plain dicts: {"4.DataMap": [{...}]}.
    Each is placed into the columns `workbook.js` declares for that sheet, so a
    test says what it means and never counts commas.

    `tabs` is MERGED OVER the real ids rather than replacing them, so
    {"1.TableDefinition": "999"} is a workbook with all six tabs and one wrong
    id — the case worth forcing. Replacing the map wholesale would make every
    other tab *absent* instead, and the Console reports those two states
    differently and correctly.
    """
    return f"""
window.__ASKED__ = [];
window.__ROWS__ = {json.dumps(rows or {}, ensure_ascii=False)};
window.__TABS__ = {json.dumps(tabs) if tabs else "null"};

window.chrome = {{
  identity: {{
    getAuthToken: (options, callback) => callback({json.dumps(token)}),
    removeCachedAuthToken: (options, callback) => callback(),
    getRedirectURL: () => "https://harness.chromiumapp.org/",
    launchWebAuthFlow: (options, callback) => callback(""),
  }},
  // ANSWERS FOR WHATEVER KEY IS ASKED. console.js remembers the chosen workbook
  // under a name of its own, and a harness that hard-coded that name would go
  // quietly inert the day it changed.
  storage: {{local: {{
    get: async (key) => ({json.dumps(bool(remembered))}
      ? {{[key]: {{fileId: {json.dumps(remembered)}, name: {json.dumps(title)}}}}}
      : {{}}),
    set: async () => {{}},
  }}}},
  runtime: {{lastError: null, getURL: (path) => path, id: "harness"}},
  tabs: {{create: () => {{}}}},
}};

window.fetch = async (input, options) => {{
  const url = String(input && input.url ? input.url : input);
  window.__ASKED__.push(url);
  if ({json.dumps(bool(fail))}) throw new TypeError({json.dumps(fail or "failed")});
  const answer = (body) => new Response(JSON.stringify(body),
    {{status: 200, headers: {{"Content-Type": "application/json"}}}});

  // The add-in's own six tab ids, so the Console's identity check passes for
  // the reason it is meant to pass and not because the check was skipped.
  if (url.includes("fields=properties.title")) {{
    const {{ SHEET_GIDS }} = await import("./addin-contract.js");
    const tabs = {{...SHEET_GIDS, ...(window.__TABS__ || {{}})}};
    return answer({{
      properties: {{title: {json.dumps(title)}}},
      sheets: Object.entries(tabs).map(
        ([name, sheetId]) => ({{properties: {{title: name, sheetId}}}})),
    }});
  }}

  // Sheets answers a GRID, header first — and TRUNCATES trailing blanks, which
  // is what `parseWorkbook` pads for. Building the grid from the sheet's own
  // declared columns keeps this honest in both directions.
  if (url.includes("values:batchGet")) {{
    const {{ SHEETS }} = await import("./workbook.js");
    return answer({{valueRanges: SHEETS.map((spec) => ({{
      range: `'${{spec.tab}}'!A1:CA2000`,
      values: [spec.columns, ...(window.__ROWS__[spec.tab] || []).map(
        (row) => spec.columns.map((name) => row[name] ?? ""))],
    }}))}});
  }}
  return answer({{}});
}};
"""
