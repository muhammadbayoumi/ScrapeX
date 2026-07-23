"""Synchronize generated design assets into both independently shipped UIs.

The Chrome extension and the Python package cannot import files from each
other at runtime. Canonical authored assets therefore live in ``design/`` and
are copied byte-for-byte into each distribution surface.

Usage:
    python tools/sync_design_assets.py
    python tools/sync_design_assets.py --check
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

ASSETS = {
    ROOT / "design" / "tokens.css": (
        ROOT / "extension" / "tokens.css",
        ROOT / "scrapex" / "webui" / "static" / "tokens.css",
    ),
    ROOT / "design" / "components.css": (
        ROOT / "extension" / "components.css",
        ROOT / "scrapex" / "webui" / "static" / "components.css",
    ),
    ROOT / "design" / "material-icons.svg": (
        ROOT / "extension" / "icons" / "material-icons.svg",
        ROOT / "scrapex" / "webui" / "static" / "material-icons" / "material-icons.svg",
    ),
    ROOT / "design" / "material-icons.LICENSE.txt": (
        ROOT / "extension" / "icons" / "material-icons.LICENSE.txt",
        ROOT / "scrapex" / "webui" / "static" / "material-icons" / "material-icons.LICENSE.txt",
    ),
}


def sync(*, check: bool) -> list[Path]:
    stale: list[Path] = []
    for source, destinations in ASSETS.items():
        expected = source.read_bytes()
        for destination in destinations:
            if not destination.exists() or destination.read_bytes() != expected:
                stale.append(destination)
                if not check:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
    return stale


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="report stale generated assets without changing them",
    )
    args = parser.parse_args()
    stale = sync(check=args.check)
    if args.check and stale:
        for path in stale:
            print(path.relative_to(ROOT))
        return 1
    for path in stale:
        print(f"updated {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
