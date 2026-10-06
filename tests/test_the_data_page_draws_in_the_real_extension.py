"""The Data page, opened in the real extension against a real engine (#1198, PR 5 of 6).

WHY A REAL EXTENSION, when tests/test_tab_page_dom.py already draws this page.
That harness builds `data.html` into a file:// page and stubs `fetch`. It cannot
see what only an installed extension does:
- MV3's content security policy, which refuses an inline script and any script
  the package does not carry;
- `chrome.storage`, where `backend.js` reads the engine's address;
- a file the page names that the package does not carry.
The engine's origin check (`RefuseForeignOrigins` in `scrapex/webui/app.py`) is
not among them yet. Measured: an extension page's GET carries no `Origin` header
(`sec-fetch-site: none`, the extension holds a host permission for 127.0.0.1),
and the check passes a request without one. Only a write carries the origin, and
this page makes none until PR 6.
This page shipped broken once with every static test green (#194, named where
`start()` in `extension/data.js` resolves the address), so #1198's gate opens it
here as well. The page runs the engine's own grid.js, and this file is what says
it draws there, icons and all.

THE FENCE, because the extension's default engine is the owner's. `DEFAULT_BACKEND`
is http://127.0.0.1:8000, and installing the extension opens `onboarding.html`,
which asks that address for `/api/health` before any line of a test runs. So the
browser starts with every request routed to a recording proxy that answers 403,
except the one port this file's own engine listens on. `<-loopback>` takes
loopback out of Chromium's built-in bypass, and it must come FIRST in the list:
measured on Chromium 149, a port rule written before it is ignored and the
engine's own requests reach the proxy. Playwright's `proxy=` option writes it
last, so the two flags are passed by hand.

THE PROFILE LIVES IN A SHORT PATH. `chrome.storage` is a LevelDB four levels
under the profile. Measured on Windows, a profile at a 187-character path failed
`storage.local.set` with "IO error: .../LOCK: File not found", because the
LevelDB's own files then pass Windows' 260-character path limit.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import socket
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest

# Guards the extension: this file reads extension/ sources, so a change there
# must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

pytest.importorskip("playwright", reason="needs the browser extra")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extension"
PRICE_SOURCE = "ELSEWEDYSHOP"
DATASET = "contractors"
#: The sprite every icon on the page points into.
SPRITE = EXTENSION / "icons" / "material-icons.svg"


def _extension_id() -> str:
    """The id Chrome derives from the manifest's `key`, as tests/test_signing_in_says_what_happened.py derives it."""
    key = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))["key"]
    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


class Fence:
    """A proxy that records the request line of every connection and answers 403.

    It forwards nothing, so a request that reaches it has gone nowhere else.
    """

    def __init__(self):
        self.seen: list[str] = []
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(32)
        self.port = self._sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(3)
                try:
                    head = conn.recv(65536).decode("latin-1")
                except OSError:
                    head = ""
                self.seen.append(head.split("\r\n", 1)[0])
                try:
                    conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n"
                                 b"Connection: close\r\n\r\n")
                except OSError:
                    pass

    def close(self):
        self._sock.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _seed(registry) -> None:
    """One price source and one dataset, each written by the code that writes them."""
    from scrapex.ingest import ingest_payloads
    from tests.test_a_dataset_is_a_table_like_any_other import stored
    from tests.test_ingest import make_entry, make_payload, one_row

    conn = registry.engine.connect()
    try:
        entry = make_entry()
        assert entry.source_key == PRICE_SOURCE, entry.source_key
        ingest_payloads(conn, entry, [make_payload([one_row(price="100.00")])])
        stored(conn)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """The engine's real app, on a free port, over a warehouse this file seeded."""
    import uvicorn

    from scrapex.config import MANIFEST_FILE
    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.webui import app as webapp

    home = tmp_path_factory.mktemp("engine")
    registry = DatabaseRegistry(EngineDatabase(home / "scrapex-engine.db"),
                               pointer_file=home / "databases.json")
    registry.initialize()
    _seed(registry)
    manifest = home / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)

    # The engine reads the origins it trusts from the native-host manifest. This
    # one names the extension under test and nothing else, as an installed
    # engine's does, so the test engine never reads this machine's own manifest.
    host_manifest = home / "com.scrapex.engine.json"
    host_manifest.write_text(json.dumps(
        {"allowed_origins": [f"chrome-extension://{_extension_id()}/"]}), encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(webapp.nativehost, "manifest_path", lambda platform=None: host_manifest)
        app = webapp.create_app(databases=registry, manifest_path=manifest)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert time.monotonic() < deadline, "the test engine did not start in 20 s"
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(10)


@pytest.fixture(scope="module")
def fence():
    proxy = Fence()
    try:
        yield proxy
    finally:
        proxy.close()


@pytest.fixture(scope="module")
def extension(engine, fence):
    """The unpacked extension, installed in a fresh Chromium profile, pointed at `engine`."""
    profile = Path(tempfile.mkdtemp(prefix="sx-"))
    port = engine.rsplit(":", 1)[1]
    with sync_playwright() as pw:
        # channel="chromium" is the full browser in new headless mode, the one
        # that loads extensions; the default headless shell does not.
        context = pw.chromium.launch_persistent_context(
            str(profile), headless=True, channel="chromium", viewport={"width": 1280, "height": 800},
            args=[f"--proxy-server=http://127.0.0.1:{fence.port}",
                  f"--proxy-bypass-list=<-loopback>;127.0.0.1:{port}",
                  f"--disable-extensions-except={EXTENSION}",
                  f"--load-extension={EXTENSION}",
                  "--no-first-run"])
        try:
            worker = (context.service_workers[0] if context.service_workers
                      else context.wait_for_event("serviceworker", timeout=30_000))
            extension_id = worker.url.split("/")[2]
            assert extension_id == _extension_id(), (extension_id, _extension_id())
            # Where backend.js reads the address from (`getBackend` in extension/engine.js).
            worker.evaluate("(base) => chrome.storage.local.set({backend: base})", engine)
            # Registered on the context, so it runs in every page before the page's own scripts.
            context.add_init_script("""
              window.__csp__ = [];
              document.addEventListener("securitypolicyviolation", (event) => {
                window.__csp__.push(event.violatedDirective + " " + event.blockedURI);
              });
            """)
            context.extension_id = extension_id
            yield context
        finally:
            context.close()
            shutil.rmtree(profile, ignore_errors=True)


def _engine_answer(engine: str, key: str) -> dict:
    """What the engine serves for `key`, asked directly, so the page's count has a referee."""
    with urllib.request.urlopen(f"{engine}/api/table/{key}?fold=0", timeout=20) as reply:
        return json.load(reply)


def open_data(extension, key: str):
    """Open data.html?source=<key>, wait for its rows or its error, and return what it did."""
    page = extension.new_page()
    seen = {"console": [], "errors": [], "failed": [], "requests": []}
    page.on("console", lambda m: m.type == "error" and seen["console"].append(m.text))
    page.on("pageerror", lambda e: seen["errors"].append(str(e)))
    page.on("requestfailed", lambda r: seen["failed"].append(f"{r.url} {r.failure}"))
    page.on("request", lambda r: seen["requests"].append(r.url))
    page.goto(f"chrome-extension://{extension.extension_id}/data.html?source={key}")
    # A drawn row, the page's own red line, or the grid's note once it says more
    # than that it is loading: whichever comes, the test reads it by name rather
    # than timing out.
    page.wait_for_function(
        """() => {
          const note = document.getElementById('grid-note');
          return document.querySelector('#grid .dg-body .dg-row')
            || document.getElementById('data-blocked').textContent.trim()
            || (note && !note.hidden && !/Loading/.test(note.textContent));
        }""",
        timeout=20_000)
    # The taxonomy answer follows the table's; let every request the load started finish.
    page.wait_for_load_state("networkidle")
    return page, seen


# ---- the fence ------------------------------------------------------------------

def test_the_fence_keeps_the_browser_off_every_other_local_port(extension, fence):
    """A page that asks another loopback port reaches the proxy, never that port."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    port = listener.getsockname()[1]
    page = extension.new_page()
    reached = False
    try:
        page.goto(f"chrome-extension://{extension.extension_id}/data.html")
        # Started, not awaited: a port that accepts and never answers would hold
        # an awaited fetch, and `evaluate` has no deadline of its own.
        page.evaluate("(url) => { window.__probe__ = fetch(url).then("
                      "(reply) => reply.status, (error) => String(error)); }",
                      f"http://127.0.0.1:{port}/probe")
        try:
            connection, _ = listener.accept()
        except TimeoutError:
            pass
        else:
            reached = True
            connection.close()
        status = page.evaluate("window.__probe__")
    finally:
        page.close()
        listener.close()
    assert not reached, "the browser reached a loopback port that is not the test engine's"
    assert f"GET http://127.0.0.1:{port}/probe HTTP/1.1" in fence.seen, fence.seen
    assert status == 403, status


# ---- the page draws -------------------------------------------------------------

@pytest.mark.parametrize("key", [PRICE_SOURCE, DATASET])
def test_the_page_draws_every_row_the_engine_serves(extension, engine, key):
    answer = _engine_answer(engine, key)
    assert answer["rows"], f"the seed gave {key} no rows, so this test would measure nothing"
    page, _ = open_data(extension, key)
    try:
        assert page.locator("#data-blocked").inner_text() == ""
        assert page.locator("#data-source").inner_text() == key
        # The grid draws only the rows near its viewport, so a row count read off
        # the page means "every row" only while the seed fits in it; the page says
        # how many fit.
        holds = page.evaluate("""() => {
            const holder = document.querySelector('#grid .dg-scroller');
            const row = document.querySelector('#grid .dg-body .dg-row');
            return Math.floor(holder.clientHeight / row.offsetHeight);
        }""")
        assert len(answer["rows"]) <= holds, (
            f"the seed gave {key} {len(answer['rows'])} rows and the viewport draws {holds}")
        assert page.locator("#grid .dg-body .dg-row").count() == len(answer["rows"])
        # Every column the engine sent, in its order, after the grid's own
        # row-selection column, which is not a field. The AR|EN switch hides one
        # half of each bilingual pair, and a hidden column is not drawn, so the
        # columns are read from the grid and the titles from the headers on screen.
        columns = page.evaluate("""() => ScrapeXDataGrid.find('#grid').getColumns()
            .map((column) => [column.getField(), column.isVisible()])""")
        assert [field for field, _ in columns] == (
            ["__select"] + [c["key"] for c in answer["columns"]]), columns
        titles = {c["key"]: c.get("label") or c["key"] for c in answer["columns"]}
        headers = [h.strip() for h in page.locator("#grid .dg-col").all_inner_texts()]
        assert headers == [""] + [titles[field] for field, shown in columns[1:] if shown], (
            headers)
    finally:
        page.close()


@pytest.mark.parametrize("key", [PRICE_SOURCE, DATASET])
def test_the_page_loads_within_the_extension_rules(extension, engine, key):
    """No console error, no script error, no CSP refusal, no file missing, no stray request."""
    page, seen = open_data(extension, key)
    try:
        csp = page.evaluate("window.__csp__")
        # A sheet that failed to load throws on `cssRules`; -1 says so without ending the read.
        sheets = page.evaluate(
            "() => [...document.styleSheets].map((sheet) => {"
            " try { return [sheet.href, sheet.cssRules.length]; }"
            " catch (error) { return [sheet.href, -1]; } })")
        linked = page.evaluate(
            "() => [...document.querySelectorAll('link[rel=stylesheet]')].map((link) => link.href)")
    finally:
        page.close()
    assert csp == [], csp
    assert seen["errors"] == [], seen["errors"]
    assert seen["console"] == [], seen["console"]
    assert seen["failed"] == [], seen["failed"]
    here = f"chrome-extension://{extension.extension_id}/"
    stray = [url for url in seen["requests"]
             if not url.startswith((here, engine + "/"))]
    assert stray == [], stray
    assert [href for href, _ in sheets] == linked, (sheets, linked)
    assert all(rules > 0 for _, rules in sheets), sheets


@pytest.mark.parametrize("key", [PRICE_SOURCE, DATASET])
def test_every_icon_points_at_a_symbol_the_sprite_holds(extension, key):
    """The page's own icons and the ones grid.js draws, which ui.js points at the
    sprite `data.html` names. A name the sprite lacks draws an empty box."""
    symbols = set(re.findall(r'<symbol id="([^"]+)"', SPRITE.read_text(encoding="utf-8")))
    page, _ = open_data(extension, key)
    try:
        uses = page.evaluate("() => [...document.querySelectorAll('use')].map((u) => u.href.baseVal)")
    finally:
        page.close()
    here = f"chrome-extension://{extension.extension_id}/icons/material-icons.svg#"
    assert uses, "the page drew no icon, so this test would measure nothing"
    wrong = [use for use in uses if not use.startswith(("icons/material-icons.svg#", here))]
    assert wrong == [], f"icons pointing somewhere other than the extension's sprite: {wrong}"
    missing = sorted({use.split("#", 1)[1] for use in uses} - symbols)
    assert missing == [], f"the sprite has no symbol for {missing}"
