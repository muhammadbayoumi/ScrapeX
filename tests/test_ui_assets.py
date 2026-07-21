"""Generated UI assets must never drift from their canonical source."""
from __future__ import annotations

from pathlib import Path

from tools.sync_ui_assets import TARGET, generated_tokens


ROOT = Path(__file__).resolve().parent.parent


def test_web_tokens_are_generated_from_extension_tokens():
    assert TARGET.read_text(encoding="utf-8") == generated_tokens()


def test_web_shell_does_not_redeclare_shared_color_tokens():
    base = (ROOT / "scrapex" / "webui" / "templates" / "base.html").read_text(
        encoding="utf-8"
    )
    assert "--accent:#" not in base
    assert '<link rel="stylesheet" href="/static/tokens.css">' in base
