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
import posixpath
import re
import sys
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"

#: In dependency order, because flattening removes the imports that expressed it.
#: startup.js first (backend.js calls its deadline helpers), then engine.js
#: (backend.js calls getBackend), then backend.js, then the page's own modules.
#: ORDER IS DEPENDENCY ORDER, because `flatten` strips the imports that would
#: otherwise say so. `taxonomyfilter.js` sits beside `datatable.js` for the same
#: reason it exists: `data.js` reads both and neither reads anything of the page.
DATA_PAGE_MODULES = ("startup.js", "transport.js", "engine.js", "backend.js",
                     "datatable.js", "taxonomyfilter.js", "data.js")

#: The engine address the stub answers for: one nothing listens on (#1264). The stub
#: replaces `window.fetch` only, so a navigation (Excel), a link (a record's Full record)
#: or an image leaves the page by another path. It was the owner's own engine address
#: until #1264, so such a request went to whatever he had running.
BACKEND = "http://127.0.0.1:9"


def flatten(source: str) -> str:
    """One module's code with its imports and `export` keywords removed."""
    source = re.sub(r"^import[\s\S]*?;\s*$", "", source, flags=re.M)
    return re.sub(r"\bexport\s+", "", source)


def stub(payload: dict | None = None, *, backend: str = BACKEND,
         status: int = 200, fail: str = "", fail_when: str = "",
         taxonomy: dict | None = None,
         fields: dict | None = None, promotable: dict | None = None,
         offer: dict | None = None) -> str:
    """The two things a plain browser tab cannot have: chrome, and an engine.

    `fail` makes the engine unreachable the way a stopped engine is — a rejected
    fetch rather than an HTTP error — because those reach the page by different
    paths and the page says different things about them. `fail_when` does the
    same to only the requests whose URL holds it, so a first table can be drawn
    and a narrower one then refused.

    `taxonomy` ANSWERS A SECOND ROUTE, and until issue 543 there was only ever one.
    The Data page now asks `/api/taxonomy/{key}` as well, and a stub that answers
    every URL with the table payload would hand the filter a table — so the filter
    would find no groups, hide itself, and every guard for it would pass against a
    control that was never drawn. Left None, that is exactly what happens, which is
    the right answer for a price source: it has no vocabulary and gets no control.

    IT ANSWERS ONLY THE ENGINE, BY ROUTE (#1198), AND ONLY `fetch`.
    A navigation, a link or an image never reaches it; the tests' fixture aborts those
    (#1264). The engine's grid asks for its
    fields, the details it can promote and one record at a time as well, so each
    route gets its own answer. Any other path on the engine gets a 404, and a
    request that is not to the engine at all is refused — a page that asked the
    extension's own origin, or the internet, for data must fail here, where it can
    be seen, rather than be handed the table. `status` still applies to the table
    and the taxonomy, the two answers the page's own error sentences are about.

    EVERY REQUEST IS RECORDED — method, URL and body — in `window.__REQUESTS__`,
    and kept in sessionStorage too, because the grid reloads the page after some
    of its saves and a test must still be able to read what was asked before.
    `window.__ASKED__` keeps the URLs alone, as the older tests read them.

    SO IS EVERY FILE THAT FAILS TO LOAD, in `window.__LOAD_FAILURES__`. A missing
    stylesheet or script raises no pageerror, and Chromium still lists a missing
    sheet in `document.styleSheets` with its href, so the element's own `error`
    event is the one signal. It does not bubble, so the listener captures it.
    """
    answers = {
        "/api/taxonomy/": taxonomy if taxonomy is not None else {"groups": []},
        "/api/table/": payload or {},
        "/api/fields/": fields if fields is not None else {"fields": []},
        "/api/promotable/": promotable if promotable is not None else {"attributes": []},
        "/api/offer/": offer if offer is not None else {},
    }
    return f"""
window.__ASKED__ = [];
window.__LOAD_FAILURES__ = [];
window.addEventListener("error", (event) => {{
  const target = event.target;
  if (target && target !== window && (target.src || target.href)) {{
    window.__LOAD_FAILURES__.push(target.src || target.href);
  }}
}}, true);
try {{
  window.__REQUESTS__ = JSON.parse(sessionStorage.getItem("__harness_requests__") || "[]");
}} catch (err) {{ window.__REQUESTS__ = []; }}
window.chrome = {{
  storage: {{local: {{
    get: async () => ({{backend: {json.dumps(backend)}}}),
    set: async () => {{}},
  }}}},
  runtime: {{getURL: (path) => path}},
  tabs: {{create: () => {{}}}},
}};
(() => {{
  const BACKEND = {json.dumps(backend.rstrip("/"))};
  const ANSWERS = {json.dumps(answers, ensure_ascii=False)};
  const STATUSED = ["/api/table/", "/api/taxonomy/"];
  const json = (value, code) => new Response(JSON.stringify(value), {{
    status: code, headers: {{"Content-Type": "application/json"}},
  }});
  // THE HARNESS'S OWN ORIGIN IS NOT THE EXTENSION'S. The page is served over http so
  // its modules load, and appearance.js and timezone.js sync with an http page's own
  // origin. The shipped page, on chrome-extension:, never makes those two requests,
  // so they are refused here and kept off the record of what the page asked.
  const PAGE_ONLY = ["/api/appearance", "/api/timezone"]
    .map((path) => window.location.origin + path);
  window.fetch = async (input, options) => {{
    const url = String(input && input.url ? input.url : input);
    const method = String((options && options.method) || (input && input.method) || "GET");
    const body = options && typeof options.body === "string" ? options.body : null;
    if (/^https?:$/.test(window.location.protocol)
        && PAGE_ONLY.some((prefix) => url.startsWith(prefix))) {{
      return json({{detail: "Not Found"}}, 404);
    }}
    window.__ASKED__.push(url);
    window.__REQUESTS__.push({{method, url, body}});
    try {{
      sessionStorage.setItem("__harness_requests__", JSON.stringify(window.__REQUESTS__));
    }} catch (err) {{ /* a log that cannot persist still lives on window */ }}
    if ({json.dumps(bool(fail))}) throw new TypeError({json.dumps(fail or "failed to fetch")});
    if ({json.dumps(bool(fail_when))} && url.includes({json.dumps(fail_when)})) {{
      throw new TypeError("failed to fetch");
    }}
    if (!url.startsWith(BACKEND + "/")) {{
      throw new TypeError("the harness refuses a request that is not to the engine: " + url);
    }}
    const path = url.slice(BACKEND.length).split("?")[0];
    const route = Object.keys(ANSWERS).find((prefix) => path.startsWith(prefix));
    if (!route) return json({{detail: "Not Found"}}, 404);
    return json(ANSWERS[route], STATUSED.includes(route) ? {status} : 200);
  }};
}})();
"""


#: The stylesheets and scripts a page loads, read from its own tags. A page is
#: static HTML, so its tags are the whole of what it loads, and a test that
#: builds it from anything else is testing a page nobody ships.
_SHEET = re.compile(r'<link\s+rel="stylesheet"\s+href="([^"]+)"\s*/?>')
_SCRIPT = re.compile(r'<script\b([^>]*)\bsrc="([^"]+)"([^>]*)>\s*</script>')
#: A script the page's own code adds to itself at run time: `x.src = "grid.js"`.
_INJECTED = re.compile(r'\.src\s*=\s*["\']([\w./-]+\.js)["\']')
#: The module a classic script imports beside itself: grid.js names its renderer so,
#: `new URL("datagrid.js" + ...)`, because a classic script has no static import.
_RENDERER = re.compile(r'new URL\(\s*["\']([\w./-]+\.js)["\']')
#: A module's own relative imports, the rest of the graph the renderer pulls in.
_RELATIVE_IMPORT = re.compile(r'''(?:\bfrom\s*|\bimport\s*)["\'](\.{1,2}/[^"\']+)["\']''')


def _module_graph(root: Path, entries: list[str]) -> list[str]:
    """Every module `entries` reach through their relative imports, entries included.

    Each is a path relative to `root`. A module that is named and missing raises here,
    by name, as a missing tag does.
    """
    seen: list[str] = []
    pending = list(entries)
    while pending:
        relative = pending.pop(0)
        if relative in seen:
            continue
        source = root / relative
        if not source.is_file():
            raise FileNotFoundError(f"a module imports {relative}, which is not in {root}")
        seen.append(relative)
        text = source.read_text(encoding="utf-8")
        for spec in _RELATIVE_IMPORT.findall(text):
            # Normalised, or "a/../b" and "b" are two modules and a cycle never ends.
            pending.append(posixpath.normpath(posixpath.join(posixpath.dirname(relative), spec)))
    return seen


def build_data_page(tmp: Path, stub_js: str, name: str = "data.html", *,
                    ext: Path = EXT) -> Path:
    """The real Data page, built from its own tags, beside the files it loads.

    WHICH SOURCE IT SHOWS IS NOT SET HERE. Open it with a query string —
    `page.goto(f"{base}/{path.name}?source=KEY")`, where `base` is `serve(tmp)` —
    and `window.location.search` then reads exactly what the shipped page reads.
    The first version of this redefined `window.location` instead; that property
    is not configurable, the assignment threw, and the page fell back to "no
    source" while looking like a harness fault.

    WHAT IT LOADS IS WHAT data.html LOADS (#711, #1198). This used to read three
    stylesheets and Tabulator off disk and inject them whatever the page linked,
    and it never ran appearance.js — so a page that dropped a sheet rendered
    unstyled with every browser test green. Now every `<link rel="stylesheet">`
    and every classic `<script src>` in data.html is copied beside the built page,
    keeping its relative path, and loads from there as it would in the extension;
    so is any script the page's modules add to themselves (`x.src = "grid.js"`),
    and every module such a script imports (grid.js's renderer and the vendored
    modules it imports). A file the page names that does not exist fails HERE, by name.
    THE PAGE IS SERVED (`serve(tmp)`), because those modules will not load over file://. Only three things
    are changed: the stub goes first in <head>; the one module tag is replaced by the
    flattened modules, because file:// refuses a module's imports; and the icon
    sprite is inlined, because file:// refuses a <use> into another file too.
    """
    html = (ext / "data.html").read_text(encoding="utf-8")
    modules = [flatten((ext / m).read_text(encoding="utf-8")) for m in DATA_PAGE_MODULES]

    module_tag = '<script type="module" src="data.js"></script>'
    assert html.count(module_tag) == 1, (
        f"data.html no longer loads data.js as one module tag; this harness replaces "
        f"exactly {module_tag!r} and must learn whatever took its place")
    loads = _SHEET.findall(html)
    loads += [src for before, src, after in _SCRIPT.findall(html)
              if "module" not in before + after]
    loads += [src for source in modules for src in _INJECTED.findall(source)]
    for relative in dict.fromkeys(loads):
        source = ext / relative
        if not source.is_file():
            raise FileNotFoundError(f"data.html loads {relative}, which is not in {ext}")
        copy = tmp / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(source.read_bytes())
    renderers = [spec for relative in dict.fromkeys(loads) if relative.endswith(".js")
                 for spec in _RENDERER.findall((ext / relative).read_text(encoding="utf-8"))]
    for relative in _module_graph(ext, renderers):
        copy = tmp / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes((ext / relative).read_bytes())

    # WHAT A COPIED SHEET NAMES COMES WITH IT (#1048). A url() is read against the
    # sheet that holds it, so tokens.css's faces must sit beside its copy. Without
    # them every face fails to load, the page draws in the platform's face, and every
    # test still passes. A data: URI and a bare fragment name no file. A file that is
    # missing, or outside the extension, fails HERE, by name, like a missing tag.
    for sheet in dict.fromkeys(_SHEET.findall(html)):
        css = re.sub(r"/\*.*?\*/", "", (ext / sheet).read_text(encoding="utf-8"), flags=re.S)
        for named in re.findall(r"""url\(\s*["']?([^"')]+?)["']?\s*\)""", css):
            if named.startswith(("data:", "#")):
                continue
            source = ((ext / sheet).parent / named.split("#")[0].split("?")[0]).resolve()
            if not source.is_file() or not source.is_relative_to(ext.resolve()):
                raise FileNotFoundError(f"{sheet} names {named}, which is not in {ext}")
            copy = tmp / source.relative_to(ext.resolve())
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(source.read_bytes())

    # THE ONE REWRITE OF THE PAGE'S OWN MARKUP (#1198). file:// refuses a <use> into
    # another file, and its error would land in __LOAD_FAILURES__, so the sprite the
    # page names is inlined, hidden, and every <use> points at its symbols: ui.js is
    # given an empty sprite path, which it reads as "the symbols in this page". A
    # spelling of the sprite's path this does not know is left over, and fails here.
    sprite_path = "icons/material-icons.svg"
    if sprite_path in html:
        sprite = (ext / sprite_path).read_text(encoding="utf-8")
        html = html.replace(f'data-icon-sprite="{sprite_path}"', 'data-icon-sprite=""')
        html = html.replace(f'href="{sprite_path}#', 'href="#')
        assert sprite_path not in html, (
            f"data.html names {sprite_path} in a way this harness does not rewrite")
        assert html.count("<body>") == 1, "data.html must have exactly one <body>"
        html = html.replace("<body>", "<body>\n" + sprite.replace("<svg ", "<svg hidden ", 1), 1)

    assert html.count("<head>") == 1, "data.html must have exactly one <head>"
    html = html.replace("<head>", f"<head>\n<script>{stub_js}</script>", 1)
    html = html.replace(module_tag, "<script>" + "\n".join(modules) + "</script>", 1)
    page = tmp / name
    page.write_text(html, encoding="utf-8")
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

    # A module is refused unless it is served as JavaScript, and the platform's own
    # table (on Windows, the registry) is not trusted to say so.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *args, **kwargs):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # The grid's page imports 85 modules, and Chromium opens six connections to one
    # host at once. While the accept thread falls behind, Windows REFUSES the
    # connection that finds the backlog full, where Linux drops the SYN and the
    # client retries. socketserver's default of five passed on ubuntu CI and failed
    # the Windows release runner with ERR_CONNECTION_REFUSED on one module.
    request_queue_size = 128

    def handle_error(self, request, client_address):
        # A test closes its page while a file is still streaming, and the socket goes
        # away under the handler. Anything else is still reported.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


@contextlib.contextmanager
def serve_extension() -> Iterator[str]:
    """The shipped `extension/` directory over http. Yields its base URL.

    ES modules will not load over file:// — the browser refuses every import as
    cross-origin and the page stays blank, which looks exactly like the kind of
    defect this file exists to catch. NOTHING IS COPIED: the directory served is
    the one that ships, so a module deleted from the repository is a module
    missing from the test.
    """
    with serve(EXT) as base:
        yield base


@contextlib.contextmanager
def serve(directory: Path) -> Iterator[str]:
    """`directory` over http on a free loopback port. Yields its base URL.

    The port is chosen by the system, so it is never the owner's engine.
    """
    server = _Server(
        ("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(directory)))
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
