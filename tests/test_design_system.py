"""Design-system distribution and accessibility guardrails."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_generated_design_assets_are_current() -> None:
    from tools.sync_design_assets import sync

    assert sync(check=True) == []


def test_ui_templates_do_not_embed_svg_paths() -> None:
    files = [
        *ROOT.joinpath("extension").glob("*.html"),
        *ROOT.joinpath("scrapex", "webui", "templates").glob("*.html"),
    ]
    offenders = [
        path.relative_to(ROOT)
        for path in files
        if re.search(r"<(?:path|circle|rect|ellipse)\b", path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_ui_templates_do_not_use_inline_style_attributes() -> None:
    files = [
        *ROOT.joinpath("extension").glob("*.html"),
        *ROOT.joinpath("scrapex", "webui", "templates").glob("*.html"),
    ]
    offenders = [
        path.relative_to(ROOT)
        for path in files
        if re.search(r"\sstyle\s*=", path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_material_icons_keep_their_license() -> None:
    license_paths = (
        ROOT / "extension" / "icons" / "material-icons.LICENSE.txt",
        ROOT
        / "scrapex"
        / "webui"
        / "static"
        / "material-icons"
        / "material-icons.LICENSE.txt",
    )
    assert all(
        "Apache License" in path.read_text(encoding="utf-8")
        for path in license_paths
    )


def test_obsolete_custom_source_icons_are_not_shipped() -> None:
    obsolete = {"browser.png", "file.png", "link.png", "shopping-cart.png"}
    assert not {
        path.name
        for directory in (ROOT / "Icons", ROOT / "extension" / "icons")
        for path in directory.glob("*.png")
        if path.name in obsolete
    }
