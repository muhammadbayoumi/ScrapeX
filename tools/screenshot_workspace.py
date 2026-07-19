"""Render the workspace pages and save screenshots (spec 21-23, 28).

The panel harness (screenshot_panel.py) cannot cover these: the workspace is
server-rendered, so it needs a real HTTP server and a real warehouse rather than
a stubbed fetch. This tool builds a throwaway warehouse, serves it on a random
local port, and captures every tab — so a claim about the Exports or Sync page
is backed by a picture rather than by an assertion.

    python tools/screenshot_workspace.py

Output: docs/screenshots/ws-<page>@<width>.png

Requires the ui + browser extras:
    python -m pip install -e ".[ui,browser]"
    python -m playwright install chromium
(PowerShell 5.1 has no `&&` — run the two commands separately.)
"""
from __future__ import annotations

import shutil
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "screenshots"

# The workspace is a desktop surface; 1024 is the narrow end it must still hold.
WIDTHS = (1024, 1280)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _seed(db_path: Path) -> None:
    """A warehouse with two prices for one offer, so Changes has something real."""
    from scrapex import db as dbmod
    from scrapex.ingest import ingest_payloads
    from tests.test_ingest import make_entry, make_payload, one_row

    conn = dbmod.connect(db_path)
    try:
        dbmod.migrate(conn)
        entry = make_entry()
        ingest_payloads(conn, entry, [make_payload([one_row(effective_price="100.00")])])
        ingest_payloads(conn, entry, [make_payload([one_row(effective_price="130.00")],
                                                   scraped_at="2026-07-20T10:00:00Z")])
        conn.commit()
    finally:
        conn.close()


def _serve(db_path: Path, manifest: Path, port: int):
    import uvicorn

    from scrapex.webui.app import create_app

    config = uvicorn.Config(create_app(db_path, manifest_path=manifest),
                            host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    return server


PAGES = [
    ("overview", "/"),
    ("data", "/source/ELSEWEDYSHOP"),
    ("changes", "/changes?source_key=ELSEWEDYSHOP"),
    ("history", "/history"),
    ("review", "/review"),
    ("jobs", "/jobs"),
    ("schedules", "/schedules"),
    ("exports", "/exports"),
    ("sync", "/sync"),
    ("logs", "/logs"),
]


def main() -> int:
    from scrapex.config import MANIFEST_FILE

    tmp = Path(tempfile.mkdtemp(prefix="scrapex-ws-"))
    db_path, manifest = tmp / "harvest.db", tmp / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    _seed(db_path)

    port = _free_port()
    server = _serve(db_path, manifest, port)
    base = f"http://127.0.0.1:{port}"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is missing. Run these TWO commands (PowerShell has no &&):\n"
              '  python -m pip install -e ".[ui,browser]"\n'
              "  python -m playwright install chromium", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, path in PAGES:
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + path, wait_until="networkidle")
                target = OUT / f"ws-{name}@{width}.png"
                page.screenshot(path=str(target), full_page=True)
                # The page itself must never scroll sideways: a wide dataset
                # scrolls inside its own container, not the whole workspace.
                overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth > "
                    "document.documentElement.clientWidth")
                flag = " OVERFLOW!" if overflow else ""
                if errors:
                    flag += f" JS-ERROR: {errors[0][:70]}"
                print(f"  {target.name}{flag}")
                written += 1
                page.close()
        browser.close()

    server.should_exit = True
    print(f"\n{written} screenshots -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
