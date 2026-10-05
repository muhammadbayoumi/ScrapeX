"""The four faces ship as files on both surfaces, each beside its licence, and the stacks
that name them are Supabase's (#1048).

WHAT WAS TRUE. design/tokens.css named Inter, Manrope and Source Code Pro first in its
stacks and shipped none of them, under a comment that said NOTHING IS FETCHED. A machine
without Inter installed drew Segoe UI, and the fallbacks behind the faces (Segoe UI,
-apple-system, BlinkMacSystemFont, Cascadia Code, Consolas) were not Supabase's.

WHAT IS TRUE NOW. #1040 item 4 ships all four: the three Supabase's stacks name
(apps/design-system/styles/globals.css@86c813ec:13-16) and Noto Sans Arabic, which
Supabase has no need of and this product does. He chose the format on 2026-09-24 (#1040,
the roadmap's answers): the full variable TTF files, unsubset. They are google/fonts' own
files at b5efa9c3, authored once under design/fonts/, and tools/sync_design_assets.py
copies them beside each surface's tokens.css, so one relative url() resolves on both.

That each face actually LOADS, and that the Arabic face is the one that draws Arabic, is
measured in a browser by tests/test_the_faces_load_on_both_surfaces.py.
"""
from __future__ import annotations

import hashlib
import re
import struct
import subprocess
from pathlib import Path

import pytest

# Guards files copied into the extension; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"

#: Where each surface keeps its stylesheet, and so where its fonts/ directory sits.
SURFACES = (ROOT / "design", ROOT / "extension", ROOT / "scrapex" / "webui" / "static")

#: The upstream every file is taken from, unmodified.
GOOGLE_FONTS = "google/fonts@b5efa9c32e8f9b63005f5cdb1ad5527a77d2cd04"

#: family: (directory, shipped name, upstream path, bytes, sha256 of the file, sha256 of
#: its OFL.txt with LF line endings).
#:
#: THE SHIPPED NAME DROPS THE BRACKETS, and that is measured, not taste. A quoted CSS url()
#: needs no escape for them, but `[opsz,wght]` is a glob character class:
#: `glob.glob("inter/Inter[opsz,wght].ttf")` returns [] for a file that is there, and the
#: package-data globs, setuptools and this suite's own scans all expand patterns. So each
#: name is upstream's with `[` and `,` turned into `-` and `]` dropped.
#:
#: THE FONT DIGESTS ARE OF THE RAW BYTES, which CLAUDE.md forbids for a repository file --
#: for a TEXT file, whose line endings a Windows checkout rewrites. `*.ttf binary` in
#: .gitattributes keeps git from ever touching these, and the test below asserts git
#: says so, so the raw bytes are what every checkout holds. The licences are text, and
#: are normalised before they are hashed: upstream's sourcecodepro/OFL.txt is CRLF (4,622
#: bytes), and the repository stores it LF (4,529).
FACES = {
    "Inter": ("inter", "Inter-opsz-wght.ttf", "ofl/inter/Inter[opsz,wght].ttf", 876_576,
              "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031",
              "5b9321a4298cfeb6b34354164a1c3afc3db114569984c502b9b35d988fd58c57"),
    "Manrope": ("manrope", "Manrope-wght.ttf", "ofl/manrope/Manrope[wght].ttf", 164_700,
                "3ae11c49db0455a3cc33e37d380f20fdb8c7f8b41dc07625c177e3d87a9d6ae6",
                "58172e0c0fac2cda8a37b348164bb55e44b0e69051e557e92b1d3f6910141f7b"),
    "Source Code Pro": ("sourcecodepro", "SourceCodePro-wght.ttf",
                        "ofl/sourcecodepro/SourceCodePro[wght].ttf", 212_340,
                        "b400fc584e10aff25d0e775ce181b4fc1c5ea1b5dc37b81aeb2084375b945790",
                        "4a4a4179a96b5ef6786186d199f0d049b151352f460b8d2f3c00083792f37dd9"),
    "Noto Sans Arabic": ("notosansarabic", "NotoSansArabic-wdth-wght.ttf",
                         "ofl/notosansarabic/NotoSansArabic[wdth,wght].ttf", 844_676,
                         "63111b5b2e074dd48cc67692e0a2726d86ee94c1c37fe8598257b7b4e87e869e",
                         "07fc70bfeb985cc1a87a8587d0a0c80bab11c86c9dc3fd95b6f0cb332f983e96"),
}

#: Supabase's three stacks, verbatim from apps/design-system/styles/globals.css@86c813ec:13-16.
#: Their `var(--font-inter)` and `var(--font-source-code-pro)` are next/font's handles on
#: the same face (apps/studio/fonts/index.ts@86c813ec:10-44) and are followed by its own
#: name; here an @font-face declares the face under that name, so the handle has nothing
#: to point at and is dropped. Their heading is `var(--font-manrope, var(--font-sans))`:
#: Manrope, and the sans stack behind it.
SUPABASE_SANS = "var(--font-inter), Inter, Helvetica Neue, Helvetica, ui-sans-serif, system-ui, sans-serif"
SUPABASE_MONO = "var(--font-source-code-pro), 'Source Code Pro', ui-monospace, Menlo, monospace"

#: CSS Fonts 4 §2.1.3's generic families. `system-ui` and `ui-sans-serif` are generic
#: families too, and that is what decides where the Arabic face goes, below.
GENERIC = {"serif", "sans-serif", "cursive", "fantasy", "monospace", "system-ui", "emoji",
           "math", "fangsong", "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded"}

#: Every way a stylesheet or a script can name a monospace face without the token.
MONO_NAMES = re.compile(r"\b(?:ui-monospace|monospace|Consolas|Courier New|Menlo|Cascadia"
                        r"(?: Code)?|Source Code Pro|SFMono-Regular)\b", re.IGNORECASE)


def _uncommented(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _families(value: str) -> list[str]:
    """A font-family list as names, quotes off. A comma inside a var() fallback is not a
    separator, so the split counts parentheses."""
    names, depth, current = [], 0, ""
    for char in value:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            names.append(current)
            current = ""
        else:
            current += char
    names.append(current)
    return [" ".join(name.strip().strip("\"'").split()) for name in names if name.strip()]


def _declared(name: str) -> str:
    """The one value design/tokens.css declares for `name`. Once, because a second
    declaration in a media or theme block would win where it applies and this file
    would be checking the loser."""
    found = re.findall(rf"(?<![\w-]){re.escape(name)}\s*:\s*([^;]+);", _uncommented(
        TOKENS.read_text(encoding="utf-8")))
    assert len(found) == 1, f"design/tokens.css declares {name} {len(found)} times, not once"
    return found[0]


def _font_faces(sheet: Path) -> list[dict[str, str]]:
    blocks = re.findall(r"@font-face\s*\{([^}]*)\}", _uncommented(sheet.read_text(encoding="utf-8")))
    faces = []
    for block in blocks:
        descriptors = {}
        for declaration in block.split(";"):
            if declaration.strip():
                key, _, value = declaration.partition(":")
                descriptors[key.strip().lower()] = " ".join(value.split())
        faces.append(descriptors)
    return faces


def _font_tables(data: bytes) -> dict[str, bytes]:
    """The sfnt table directory (OpenType 1.9, "Organization of an OpenType font")."""
    assert data[:4] == b"\x00\x01\x00\x00", "not a TrueType-outline sfnt"
    count = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for index in range(count):
        tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * index:28 + 16 * index])
        tables[tag.decode("ascii")] = data[offset:offset + length]
    return tables


def _axes(fvar: bytes) -> dict[str, tuple[float, float]]:
    """Each variation axis's (min, max), from the `fvar` table's axis records."""
    axes_offset, _, count, size = struct.unpack(">HHHH", fvar[4:12])
    axes = {}
    for index in range(count):
        record = fvar[axes_offset + index * size:axes_offset + index * size + 16]
        tag, low, _, high = struct.unpack(">4siii", record)
        axes[tag.decode("ascii")] = (low / 65536, high / 65536)
    return axes


def _family(name_table: bytes) -> str:
    """The typographic family (name ID 16), else the family (ID 1), in Windows English."""
    _, count, strings = struct.unpack(">HHH", name_table[:6])
    found = {}
    for index in range(count):
        platform, _, language, name_id, length, offset = struct.unpack(
            ">HHHHHH", name_table[6 + 12 * index:18 + 12 * index])
        if platform == 3 and language == 0x409 and name_id in (1, 16):
            found[name_id] = name_table[strings + offset:strings + offset + length].decode("utf-16-be")
    return found.get(16, found.get(1, ""))


@pytest.mark.parametrize("family", FACES)
def test_each_face_is_google_fonts_own_file_unmodified(family):
    directory, name, upstream, size, digest, _ = FACES[family]
    data = (ROOT / "design" / "fonts" / directory / name).read_bytes()
    assert len(data) == size, f"{name} is {len(data):,} bytes; {GOOGLE_FONTS} {upstream} is {size:,}"
    assert hashlib.sha256(data).hexdigest() == digest, (
        f"{name} is not {GOOGLE_FONTS} {upstream}. The OFL's Reserved Font Name clause binds "
        "a modified file, and he chose the unsubset file (#1040), so it ships as fetched.")


@pytest.mark.parametrize("family", FACES)
def test_each_face_ships_beside_its_own_licence_on_every_surface(family):
    directory, name, upstream, _, _, licence = FACES[family]
    for surface in SURFACES:
        folder = surface / "fonts" / directory
        assert (folder / name).is_file(), f"{folder.relative_to(ROOT).as_posix()} lacks {name}"
        text = (folder / "OFL.txt").read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(text).hexdigest() == licence, (
            f"{folder.relative_to(ROOT).as_posix()}/OFL.txt is not {GOOGLE_FONTS} "
            f"{upstream.rsplit('/', 1)[0]}/OFL.txt; the OFL asks for its own text beside "
            "every copy of the font")
        assert b"SIL Open Font License, Version 1.1" in text



@pytest.mark.parametrize("family", FACES)
def test_the_sync_tool_carries_each_face_and_its_licence_to_both_surfaces(family):
    """The copies are the tool's, not a hand's: a copy the registry does not list would
    pass every check above today and silently keep its old bytes the day design/fonts/
    changes, because nothing would rewrite it."""
    from tools.sync_design_assets import ASSETS

    directory, name, *_ = FACES[family]
    for file in (name, "OFL.txt"):
        source = ROOT / "design" / "fonts" / directory / file
        assert ASSETS.get(source) == tuple(surface / "fonts" / directory / file
                                           for surface in SURFACES[1:]), (
            f"tools/sync_design_assets.py does not copy design/fonts/{directory}/{file} "
            "to extension/fonts/ and scrapex/webui/static/fonts/")


def test_no_surface_ships_a_font_without_a_licence_beside_it():
    """The other direction: a font file added to any surface's fonts/ tomorrow, under any
    name, is refused until its OFL.txt is beside it -- and the four are all there is."""
    expected = {f"{directory}/{name}" for directory, name, *_ in FACES.values()}
    for surface in SURFACES:
        shipped = {path.relative_to(surface / "fonts").as_posix()
                   for path in (surface / "fonts").rglob("*")
                   if path.suffix.lower() in {".ttf", ".otf", ".woff", ".woff2"}}
        assert shipped == expected, (surface.relative_to(ROOT).as_posix(), sorted(shipped))
        for relative in shipped:
            licence = surface / "fonts" / Path(relative).parent / "OFL.txt"
            assert licence.is_file(), f"{relative} ships on {surface.name} without its OFL.txt"


def test_git_never_rewrites_a_font_byte():
    """`* text=auto` would normalise a file it took for text. A TrueType file holds NUL
    bytes and git's own detection calls it binary, but the digests above depend on it, so
    `*.ttf binary` says it outright and this holds git to it on every copy."""
    paths = [(surface / "fonts" / directory / name).relative_to(ROOT).as_posix()
             for surface in SURFACES for directory, name, *_ in FACES.values()]
    out = subprocess.run(["git", "check-attr", "text", "diff", "--", *paths], cwd=ROOT,
                         check=True, capture_output=True, text=True).stdout
    attributes = {}
    for line in out.splitlines():
        path, attribute, value = line.rsplit(": ", 2)
        attributes[(path, attribute)] = value
    assert len(attributes) == 2 * len(paths) == 24, out
    wrong = sorted(key for key, value in attributes.items() if value != "unset")
    assert not wrong, f"git may rewrite these font files' bytes: {wrong}"


def test_each_face_is_declared_once_from_a_local_file_that_git_tracks():
    """Each surface's tokens.css carries the four @font-face blocks, and each url()
    resolves FROM THAT SHEET to a file git tracks: a relative url() is read against the
    sheet that holds it, so one written for the extension but not the engine would load
    on one surface and silently fall back on the other. No url() is remote: the
    extension's pages load nothing from the network for their own look, and an engine
    with no connection must still draw its own faces."""
    tracked = set(subprocess.run(["git", "ls-files", "--", *(s.relative_to(ROOT).as_posix()
                                                            for s in SURFACES)],
                                 cwd=ROOT, check=True, capture_output=True,
                                 text=True).stdout.splitlines())
    assert "design/tokens.css" in tracked, "git answered for a different tree"
    for surface in SURFACES:
        sheet = surface / "tokens.css"
        faces = _font_faces(sheet)
        assert sorted(face.get("font-family", "").strip("\"'") for face in faces) == sorted(FACES), (
            sheet.relative_to(ROOT).as_posix(), faces)
        for face in faces:
            urls = re.findall(r"url\(\s*[\"']?([^\"')]+)[\"']?\s*\)", face.get("src", ""))
            assert len(urls) == 1, face
            assert not re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", urls[0], re.IGNORECASE), (
                f"{sheet.relative_to(ROOT).as_posix()} fetches a face from {urls[0]}")
            target = (sheet.parent / urls[0]).resolve().relative_to(ROOT).as_posix()
            assert target in tracked, f"{sheet.relative_to(ROOT).as_posix()}: {urls[0]} is not a tracked file"
            directory, name, *_ = FACES[face["font-family"].strip("\"'")]
            assert target == (surface / "fonts" / directory / name).relative_to(ROOT).as_posix()


def test_no_other_stylesheet_declares_a_face():
    """One sheet owns the faces. A second @font-face elsewhere -- or one fetching from a
    host -- would load a face this file never sees."""
    copies = {surface / "tokens.css" for surface in SURFACES}
    elsewhere = [sheet.relative_to(ROOT).as_posix()
                 for folder in (ROOT / "design", ROOT / "extension", ROOT / "scrapex" / "webui")
                 for sheet in sorted(folder.rglob("*.css"))
                 if sheet not in copies and "@font-face" in _uncommented(sheet.read_text(encoding="utf-8"))]
    assert not elsewhere, f"@font-face outside tokens.css: {elsewhere}"


@pytest.mark.parametrize("family", FACES)
def test_each_face_declares_what_its_file_holds(family):
    """The weight range is the file's own `wght` axis, read from its `fvar` table, so a
    request anywhere in it is drawn by the variable face and none is synthesised. The
    family is the name the file gives itself. font-display is Supabase's: every face they
    load is `display: 'swap'` (apps/studio/fonts/index.ts@86c813ec:6,12,30)."""
    directory, name, *_ = FACES[family]
    tables = _font_tables((ROOT / "design" / "fonts" / directory / name).read_bytes())
    assert _family(tables["name"]) == family
    low, high = _axes(tables["fvar"])["wght"]
    face = next(face for face in _font_faces(TOKENS) if face.get("font-family", "").strip("\"'") == family)
    assert face.get("font-weight") == f"{low:g} {high:g}", (family, face, (low, high))
    assert face.get("font-style") == "normal", face
    assert face.get("font-display") == "swap", face
    assert 'format("truetype")' in face["src"], face


def _with_the_arabic_face(stack: str) -> list[str]:
    """Supabase's stack with next/font's handle dropped and Noto Sans Arabic placed
    BEFORE THE FIRST GENERIC FAMILY.

    WHY THERE AND NOT BEFORE `sans-serif`. A family's glyphs are taken in order, one
    character at a time, so the first family that holds an Arabic letter draws it -- and
    `system-ui` is the platform's own face, which on Linux is DejaVu Sans and on Windows
    Segoe UI, and both carry Arabic. Placed after it, the shipped face drew no Arabic
    glyph at all in Chromium here: measured with CSS.getPlatformFontsForNode, 14 of 14
    Arabic glyphs came from DejaVu Sans. Before it, 18 of 18 came from Noto Sans Arabic.
    Supabase's own entries keep their order either way."""
    names = [name for name in _families(stack) if not name.startswith("var(")]
    first = next(index for index, name in enumerate(names) if name in GENERIC)
    return names[:first] + ["Noto Sans Arabic"] + names[first:]


def test_the_sans_stack_is_supabases_with_the_arabic_face():
    assert _families(_declared("--font")) == _with_the_arabic_face(SUPABASE_SANS)


def test_the_heading_stack_is_manrope_then_the_sans_stack():
    """Their `var(--font-manrope, var(--font-sans))` is Manrope with the sans stack behind
    it. Written here as `Manrope, var(--font)`, so the two stacks share one fallback list."""
    heading = _families(_declared("--font-heading"))
    assert heading == ["Manrope", "var(--font)"], heading


def test_the_mono_stack_is_supabases_with_the_arabic_face():
    """The issue's finding: --font-mono had no Arabic face at all, so an Arabic value in a
    code cell fell to whatever the platform had."""
    assert _families(_declared("--font-mono")) == _with_the_arabic_face(SUPABASE_MONO)


def test_no_fallback_outside_supabases_lists_survives():
    stacks = " ".join(_declared(name) for name in ("--font", "--font-heading", "--font-mono"))
    for stale in ("Segoe UI", "-apple-system", "BlinkMacSystemFont", "Cascadia Code", "Consolas"):
        assert stale not in stacks, f"{stale} is in a stack and is not Supabase's"


def _authored(*suffixes: str) -> list[Path]:
    """Every file of these kinds this repository writes for either surface: no vendor
    library, no test, and no tokens.css, which is where the mono stack is declared."""
    tokens = {surface / "tokens.css" for surface in SURFACES}
    return [path for folder in (ROOT / "design", ROOT / "extension", ROOT / "scrapex" / "webui")
            for path in sorted(folder.rglob("*"))
            if path.suffix in suffixes and path not in tokens
            and not {"vendor", "tests", "node_modules"} & set(path.parts)]


def test_no_stylesheet_writes_a_mono_stack_of_its_own():
    """TSS-20: a monospace stack written out in a stylesheet bypasses --font-mono, so it
    never gets Source Code Pro, nor the Arabic face. Two did -- `.source-identity-meta` in
    design/components.css and the snapshot textarea in pages/datasets.css."""
    sheets = _authored(".css")
    assert ROOT / "design" / "components.css" in sheets, "the scan is reading the wrong files"
    found = []
    for sheet in sheets:
        css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"),
                     sheet.read_text(encoding="utf-8"), flags=re.S)
        for match in re.finditer(r"(?<![\w-])font(?:-family)?\s*:\s*([^;}]+)", css):
            if MONO_NAMES.search(match.group(1)):
                found.append(f"{sheet.relative_to(ROOT).as_posix()}:{css.count(chr(10), 0, match.start()) + 1}")
    assert not found, f"monospace stacks written outside --font-mono: {found}"


def test_no_script_or_page_writes_a_mono_stack_of_its_own():
    """The third bypass was a canvas: the data-model page drew its relationship labels with
    `600 12px ui-monospace, Consolas, monospace`, a font string no stylesheet reaches. A
    script reads --font-mono instead, the way it already reads the colour tokens."""
    files = _authored(".js", ".html")
    assert ROOT / "scrapex" / "webui" / "static" / "pages" / "data-model.js" in files
    literal = re.compile(r"""(["'`])((?:(?!\1).)*)\1""")
    found = [f"{path.relative_to(ROOT).as_posix()}:{number}"
             for path in files
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             for match in literal.finditer(line) if MONO_NAMES.search(match.group(2))]
    assert not found, f"monospace stacks written outside --font-mono: {found}"


def test_the_panel_harness_points_each_face_at_the_extensions_own_file(tmp_path, monkeypatch):
    """tools/panel_harness.py inlines tokens.css into a page in a temporary directory, so
    it rewrites each url() onto extension/ -- and refuses a face the extension does not
    ship, since a panel test drawn in the platform's face would pass about the wrong page."""
    from tools import panel_harness

    css = 'src: url("fonts/inter/Inter-opsz-wght.ttf") format("truetype");'
    face = ROOT / "extension" / "fonts" / "inter" / "Inter-opsz-wght.ttf"
    assert panel_harness._point_fonts_at_the_extension(css) == (
        f'src: url("{face.as_uri()}") format("truetype");')

    monkeypatch.setattr(panel_harness, "EXT", tmp_path)
    with pytest.raises(FileNotFoundError, match="fall back to the platform's face"):
        panel_harness._point_fonts_at_the_extension(css)
