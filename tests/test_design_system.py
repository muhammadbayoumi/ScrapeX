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


# ---------------------------------------------------------------------------
# A `var()` has to resolve to a token, or it is a lie about the colour.
#
# THE INCIDENT, 2026-08-15. `extension/console.css` styled a COMPLETED build
# step with `border-inline-start-color: var(--green)`, and no file in this
# repository has ever defined `--green`. An undefined custom property does not
# fall back to the rule it overrides: the declaration is invalid at
# computed-value time, so the property takes the INHERITED value if it
# inherits and the INITIAL value if it does not. `border-inline-start-color`
# does not inherit, and its initial value is `currentColor` — so a finished
# step drew its edge in the text colour, beside an in-progress step in amber
# and a blocked one in grey. Three states, two of them identical.
#
# `tests/test_ui_kit.py` could not have caught it. It checks that every class
# in markup resolves to a rule, which is the same shape of question asked
# about the other half of a stylesheet; `.build-done` resolved perfectly well
# and painted the wrong colour. Writing this guard found five more: an orphaned
# `--sticky-tabs` left behind when the workspace header bar was removed in
# 4099930, `--font-sans` on two page bodies where the token is `--font`, and
# `--shadow-md` and `--control-active`, which never existed at all.
#
# WHAT THIS DOES NOT CHECK. `var(--x, fallback)` is skipped: a fallback is the
# author saying what happens when the property is absent, and it renders.
# Properties declared inside an HTML `<style>` block are not read either, so a
# stylesheet may not lean on one — `--brand-mark` is declared by each surface's
# own sheet precisely so the shared `components.css` can use it.

#: Custom properties no stylesheet declares because a script sets them on the
#: element itself. Each entry names the source that sets it, and the test below
#: proves the claim rather than trusting it, so this cannot become a quiet
#: parking place for a token nobody defined.
#:
#: A property set only SOMETIMES does not belong here — it belongs in a
#: `var(--x, fallback)`, which is what `--rail-indicator-y` does, because the
#: rail has no indicator position until something is selected. This one is set
#: on every `<i>` at the moment the script creates it, so an element without it
#: is a broken script, not a state worth designing a fallback for.
SET_AT_RUNTIME = {
    "--palette-swatch": "design/appearance.js",
}


def _stylesheets() -> list[Path]:
    """Every sheet either UI loads, canon and distributed copies alike."""
    return (
        sorted((ROOT / "design").glob("*.css"))
        + sorted((ROOT / "extension").glob("*.css"))
        + sorted((ROOT / "scrapex" / "webui" / "static").rglob("*.css"))
    )


def test_every_custom_property_a_stylesheet_reads_is_one_something_defines() -> None:
    """THE GUARD. Declarations are pooled across every sheet, not checked one
    file at a time: the shared `components.css` reads `--brand-mark`, which
    only the per-surface sheets that load it declare, and a per-file check
    would report each of them."""
    declared: set[str] = set()
    used: dict[str, set[str]] = {}
    for path in _stylesheets():
        body = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        declared |= set(re.findall(r"(--[a-zA-Z][\w-]*)\s*:", body))
        for match in re.finditer(r"var\(\s*(--[a-zA-Z][\w-]*)\s*([,)])", body):
            if match.group(2) == ")":
                used.setdefault(match.group(1), set()).add(
                    str(path.relative_to(ROOT)).replace("\\", "/"))

    undefined = {name: files for name, files in used.items()
                 if name not in declared and name not in SET_AT_RUNTIME}
    assert not undefined, (
        "custom properties read with no definition and no fallback:\n"
        + "\n".join(f"  {name:<22} {', '.join(sorted(files))}"
                    for name, files in sorted(undefined.items())))


def test_every_property_excused_as_runtime_set_really_is_set() -> None:
    """An excuse nobody checks is how the guard above stops being a guard."""
    for name, source in SET_AT_RUNTIME.items():
        text = (ROOT / source).read_text(encoding="utf-8")
        assert f'setProperty("{name}"' in text, (
            f"{name} is excused as runtime-set, but {source} never sets it")
