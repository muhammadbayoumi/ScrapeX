"""Design-system distribution and accessibility guardrails."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_generated_design_assets_are_current() -> None:
    from tools.sync_design_assets import sync

    assert sync(check=True) == []


def test_the_generated_catalogue_is_the_same_on_every_platform() -> None:
    """CI failed on this and the machine that wrote it could not see it.

    The catalogue embeds `design/x-mark.svg` as a data URI, and the first
    version read it with `read_bytes`. Git hands that file CRLF on Windows and
    LF on Linux, so the same source encoded to two different base64 strings:
    the generated block was current on the machine that generated it and stale
    everywhere else — a red build with nothing to see in the diff.

    Reading through universal newlines fixes it, and this is the assertion that
    would have caught it: what is embedded carries no Windows line ending, and
    is byte-identical to the LF form of the asset.
    """
    import base64

    gallery = (ROOT / "design" / "gallery.html").read_text(encoding="utf-8")
    match = re.search(r'url\("data:image/svg\+xml;base64,([^"]+)"\)', gallery)
    assert match, "the catalogue no longer embeds the brand mark"

    embedded = base64.b64decode(match.group(1))
    assert b"\r\n" not in embedded, (
        "the embedded mark carries Windows line endings, so this file is "
        "generated differently on Linux and CI will call it stale")
    assert embedded == (ROOT / "design" / "x-mark.svg").read_text(
        encoding="utf-8").encode("utf-8")


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
