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

THE MODULE GRAPH IS FLATTENED, not re-declared. Imports are stripped and
`export` removed, so the files that run here are the files that ship — the same
choice panel_harness.py makes, for the same reason: a test-only re-declaration
of a function tests the re-declaration.
"""
from __future__ import annotations

import json
import re
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
