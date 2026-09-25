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


def test_every_copy_of_the_mark_ships_tablers_notice() -> None:
    """The mark is Tabler's MIT x-mark, and MIT wants its notice in every copy (#1045).

    The directories are read from the sync map rather than listed here, so a new home for
    the mark that forgets the notice fails too.
    """
    from tools.sync_design_assets import ASSETS

    mark = ROOT / "design" / "x-mark.svg"
    assert "icon-tabler-x-mark" in mark.read_text(encoding="utf-8"), (
        "design/x-mark.svg no longer says it is Tabler's; if the mark changed hands, so does "
        "the notice this test demands")
    homes = [mark, *ASSETS[mark]]
    assert len(homes) >= 3, f"the mark ships to {len(homes)} places; the map is not being read"
    for home in homes:
        notice = home.with_name("x-mark.LICENSE.txt")
        assert notice.is_file(), f"{home.relative_to(ROOT)} ships with no Tabler notice beside it"
        text = notice.read_text(encoding="utf-8")
        assert "MIT License" in text and "Paweł Kuna" in text, (
            f"{notice.relative_to(ROOT)} is not Tabler's MIT notice")


def test_obsolete_custom_source_icons_are_not_shipped() -> None:
    obsolete = {"browser.png", "file.png", "link.png", "shopping-cart.png"}
    assert not {
        path.name
        for directory in (ROOT / "Icons", ROOT / "extension" / "icons")
        for path in directory.glob("*.png")
        if path.name in obsolete
    }


@pytest.mark.parametrize("marker", ["SPRITE_OPEN", "SPRITE_CLOSE", "MARK_OPEN", "MARK_CLOSE"])
def test_a_lost_catalogue_marker_fails_the_check(tmp_path, monkeypatch, marker) -> None:
    """The catalogue check once ran only while the sprite marker was present, so renaming
    that comment switched it off and `--check` called the catalogue current forever (#408).
    Every marker is renamed in turn, on a copy, and the check must name the lost one."""
    import tools.sync_design_assets as sync_tool

    text = sync_tool.GALLERY.read_text(encoding="utf-8")
    lost = getattr(sync_tool, marker)
    assert text.count(lost) == 1, f"design/gallery.html does not carry {marker} once"
    catalogue = tmp_path / "gallery.html"
    catalogue.write_text(text.replace(lost, lost.replace(":", "-")), encoding="utf-8")
    monkeypatch.setattr(sync_tool, "GALLERY", catalogue)
    with pytest.raises(ValueError, match=re.escape(repr(lost.strip()))):
        sync_tool.sync(check=True)


def test_a_missing_catalogue_fails_the_check(tmp_path, monkeypatch) -> None:
    import tools.sync_design_assets as sync_tool

    monkeypatch.setattr(sync_tool, "GALLERY", tmp_path / "gallery.html")
    with pytest.raises(FileNotFoundError):
        sync_tool.sync(check=True)
