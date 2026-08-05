"""Record every element's computed style, so a CSS refactor can prove it changed nothing.

WHY NOT SCREENSHOTS: eight of the workspace's twenty-eight pictures differ
between two consecutive runs of tools/screenshot_workspace.py with no code
change at all — Changes, Data, History and Settings→Storage print times, and
the text moves. A pixel diff on those pages reports a difference that is not
one, which is worse than no proof, because it trains the reader to ignore it.

Computed styles do not move with the text. This records the properties that
carry a component's LOOK — colour, box, type, layout — and deliberately not its
geometry, so "3 minutes ago" becoming "4 minutes ago" is invisible here while a
changed padding, a lost border or a different background is not.

    python tools/style_snapshot.py before.json     # on the current tree
    …refactor…
    python tools/style_snapshot.py after.json
    python tools/style_snapshot.py --diff before.json after.json

Requires the ui + browser extras:
    python -m pip install -e ".[ui,browser]"
    python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

#: The properties that describe how a component LOOKS. Geometry (width, height,
#: inset, transform) is left out on purpose: it moves with the text, and the
#: text on four of these pages is a clock.
PROPERTIES = (
    "display flex-direction flex-wrap align-items justify-content gap "
    "grid-template-columns place-items "
    "background-color color border-top-color border-top-width border-top-style "
    "border-radius box-shadow outline-color opacity "
    "font-family font-size font-weight font-style line-height letter-spacing "
    "text-align text-transform text-decoration-line white-space direction "
    "padding-top padding-right padding-bottom padding-left "
    "margin-top margin-right margin-bottom margin-left "
    "fill stroke visibility overflow-x overflow-y"
).split()

#: A stable identity for an element that does not depend on text: its tag, its
#: class list, and its index among siblings. Two runs of the same page give the
#: same keys; a refactor that ADDS a class changes the key, which is reported as
#: a moved element rather than being silently matched to the wrong one.
IDENTITY = """
  (el) => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const i = n.parentElement ? [...n.parentElement.children].indexOf(n) : 0;
      parts.unshift(n.tagName.toLowerCase() + (n.className && typeof n.className === 'string'
        ? '.' + n.className.trim().split(/\\s+/).join('.') : '') + `[${i}]`);
    }
    return parts.join('>');
  }
"""

COLLECT = """
  ([props, identity]) => {
    const id = eval(identity);
    const out = {};
    for (const el of document.querySelectorAll('*')) {
      if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') continue;
      const s = getComputedStyle(el);
      const row = {};
      for (const p of props) row[p] = s.getPropertyValue(p);
      out[id(el)] = row;
    }
    return out;
  }
"""


def _workspace_pages(browser) -> dict:
    """Every server-rendered page, on a throwaway warehouse."""
    import screenshot_workspace as ws

    tmp = Path(tempfile.mkdtemp(prefix="scrapex-style-"))
    db_path, manifest = tmp / "harvest.db", tmp / "sources.yaml"
    from scrapex.config import MANIFEST_FILE

    shutil.copy(MANIFEST_FILE, manifest)
    ws._seed(db_path)
    port = ws._free_port()
    server = ws._serve(db_path, manifest, port)
    base = f"http://127.0.0.1:{port}"

    snapshot = {}
    try:
        for name, path in ws.PAGES:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(base + path, wait_until="networkidle")
            snapshot[f"ws:{name}"] = page.evaluate(COLLECT, [PROPERTIES, IDENTITY])
            page.close()
    finally:
        server.should_exit = True
    return snapshot


def _panel_pages(browser) -> dict:
    """The extension panel, every view, through the same harness the tests use."""
    import panel_harness as harness

    tmp = Path(tempfile.mkdtemp(prefix="scrapex-style-panel-"))
    page_file = harness.build_page(tmp, harness.stub("http://127.0.0.1:8000"))

    snapshot = {}
    page = browser.new_page(viewport={"width": 400, "height": 900})
    page.goto(page_file.as_uri())
    page.wait_for_timeout(600)
    views = page.eval_on_selector_all(
        "nav.side-rail button[data-view]", "els => els.map(e => e.dataset.view)")
    for view in views:
        page.click(f'nav.side-rail button[data-view="{view}"]')
        page.wait_for_timeout(300)
        snapshot[f"panel:{view}"] = page.evaluate(COLLECT, [PROPERTIES, IDENTITY])
    page.close()
    return snapshot


def collect(target: Path) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        snapshot = _panel_pages(browser)
        snapshot.update(_workspace_pages(browser))
        browser.close()

    target.write_text(json.dumps(snapshot, indent=0, sort_keys=True), encoding="utf-8")
    elements = sum(len(v) for v in snapshot.values())
    print(f"{len(snapshot)} pages, {elements} elements -> {target}")
    return 0


#: `div.card.hi[2]` -> `div[2]`. Promoting a component means ADDING a class to
#: the markup, which changes every key on the path and reports the whole subtree
#: as replaced. The strict key is the default because it never mismatches two
#: different elements; this is for the one case where the class list is the
#: thing that changed on purpose, and the question is whether the LOOK survived.
STRIP_CLASSES = re.compile(r"\.[^>\[]*(?=\[)")


def _rekey(page: dict, ignore_classes: bool) -> dict:
    if not ignore_classes:
        return page
    out: dict[str, dict] = {}
    for key, row in page.items():
        out.setdefault(STRIP_CLASSES.sub("", key), row)
    return out


def diff(before: Path, after: Path, *, ignore_classes: bool = False) -> int:
    a = json.loads(before.read_text(encoding="utf-8"))
    b = json.loads(after.read_text(encoding="utf-8"))
    if ignore_classes:
        print("comparing by position only: class lists are ignored, so a "
              "promotion that adds a class is compared on its LOOK alone.")

    changes: list[str] = []
    for page in sorted(set(a) | set(b)):
        old = _rekey(a.get(page, {}), ignore_classes)
        new = _rekey(b.get(page, {}), ignore_classes)
        for key in sorted(set(old) | set(new)):
            if key not in new:
                changes.append(f"{page}  GONE      {key}")
                continue
            if key not in old:
                changes.append(f"{page}  NEW       {key}")
                continue
            for prop in sorted(set(old[key]) | set(new[key])):
                if old[key].get(prop) != new[key].get(prop):
                    changes.append(
                        f"{page}  {prop}: {old[key].get(prop)!r} -> "
                        f"{new[key].get(prop)!r}\n      {key}")

    if not changes:
        print("no computed style changed on any element of any page")
        return 0
    print(f"{len(changes)} differences:")
    for line in changes[:200]:
        print(f"  {line}")
    if len(changes) > 200:
        print(f"  … and {len(changes) - 200} more")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, nargs="?")
    parser.add_argument("--diff", type=Path, nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument(
        "--ignore-classes", action="store_true",
        help="match elements by position only, for a refactor that adds a class "
             "on purpose and is claiming the look did not change")
    args = parser.parse_args()
    if args.diff:
        return diff(*args.diff, ignore_classes=args.ignore_classes)
    if not args.target:
        parser.error("give a file to write, or --diff BEFORE AFTER")
    return collect(args.target)


if __name__ == "__main__":
    raise SystemExit(main())
