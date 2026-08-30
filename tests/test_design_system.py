"""Design-system distribution and accessibility guardrails."""
from __future__ import annotations

import re
from pathlib import Path
import pytest

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension


ROOT = Path(__file__).resolve().parent.parent


def test_generated_design_assets_are_current() -> None:
    from tools.sync_design_assets import sync

    assert sync(check=True) == []


def test_every_generated_copy_says_it_is_one() -> None:
    """A generated file that reads like a source file will be edited like one.

    THE INCIDENT, 2026-08-11. An engine-poll backoff was written straight into
    `extension/appearance.js` — correct code, reviewed, merged. That file is a
    generated copy of `design/appearance.js`, and the next run of
    `tools/sync_design_assets.py` would have erased it with no diff, no failing
    test and nothing at all to notice. It was caught by a second reader, not by
    the repository.

    `test_generated_design_assets_are_current` was already there and could not
    have caught it: it fails when a copy has drifted from its source, and the
    sync run that erases the edit is precisely the run that makes them agree
    again. The guard was working exactly as designed, on the wrong side of the
    event.

    So the thing that was missing is not a comparison. It is a sentence at the
    top of each copy telling the reader where the file they are holding came
    from, BEFORE they start typing. That is what this asserts, on the
    destinations rather than the sources, because the destination is what gets
    opened by mistake.

    `AUTHORED IN design/<name>` names the file to edit instead; `GENERATED COPY`
    names what the reader is holding. Both phrases are asserted rather than the
    surrounding prose, so the wording can be improved without breaking this and
    the two load-bearing facts still cannot be dropped.
    """
    from tools.sync_design_assets import ASSETS

    # Text only. A PNG cannot carry a comment, and nobody hand-edits a binary
    # into a divergent state without noticing.
    readable = {".js", ".css"}
    checked = 0
    for source, destinations in ASSETS.items():
        if source.suffix not in readable:
            continue
        for destination in destinations:
            body = destination.read_text(encoding="utf-8")
            relative = destination.relative_to(ROOT).as_posix()
            assert f"AUTHORED IN design/{source.name}" in body, (
                f"{relative} is generated from design/{source.name} and does "
                "not say so. A reader who opens it has no way to know an edit "
                "here is reverted by the next sync without a word.")
            assert "GENERATED COPY" in body, (
                f"{relative} names its source but never tells the reader that "
                "the file in front of them is the copy.")
            checked += 1

    # A filter that quietly matched nothing would make every assertion above
    # vacuous, and this file's own history is the argument for saying so.
    assert checked >= 10, (
        f"only {checked} generated copies were checked; the asset table or the "
        "suffix filter has changed and this test is no longer covering them")


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


def test_the_supabase_notice_travels_with_the_values_it_covers() -> None:
    """R-74 makes Supabase's design system the baseline, so the borrowing is
    structural and it is owed a notice -- and a notice that exists only in
    `design/` is not carried to anyone who installs the extension or the engine.

    THIS REPOSITORY ALREADY DISCHARGED THE SAME OBLIGATION THREE TIMES FOR A
    SMALLER BORROWING. The Material icons licence is present in three places and
    two of them are asserted below. For the values `design/tokens.css` is built
    from there was, until 2026-08-30, no notice anywhere at all -- `OP-108`.

    Both licences are named on purpose. Their repository root declares Apache-2.0
    under "Copyright 2024 Supabase"; `packages/ui`, which holds every file the
    values were read from, declares MIT in its own package.json and ships no
    licence text. Satisfying both is cheaper than deciding which governs.
    """
    notice_paths = (
        ROOT / "design" / "supabase.NOTICE.txt",
        ROOT / "extension" / "supabase.NOTICE.txt",
        ROOT / "scrapex" / "webui" / "static" / "supabase.NOTICE.txt",
    )
    for path in notice_paths:
        assert path.exists(), f"{path} is missing; run tools/sync_design_assets.py"
        text = path.read_text(encoding="utf-8")
        # Attribution, both licences, and the section 4(b) statement of change.
        # A notice that names neither licence, or that drops the statement, is a
        # file rather than a discharge.
        for required in (
            "Copyright 2024 Supabase",
            "Apache License",
            "MIT LICENSE",
            "STATEMENT OF CHANGES",
            "86c813ec03e340ffbe4aeb97cd0c5bee7a0ead94",
        ):
            assert required in text, f"{path.name} no longer carries {required!r}"


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
