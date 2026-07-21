"""Regenerate packaged web assets from the extension design-system sources."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "extension" / "tokens.css"
TARGET = ROOT / "scrapex" / "webui" / "static" / "tokens.css"
GENERATED_HEADER = "/* GENERATED from extension/tokens.css by tools/sync_ui_assets.py. */\n"


def generated_tokens() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    body = source[source.index(":root") :]
    return GENERATED_HEADER + body


def main() -> None:
    TARGET.write_text(generated_tokens(), encoding="utf-8")


if __name__ == "__main__":
    main()
