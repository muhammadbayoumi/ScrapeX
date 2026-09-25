"""Every control an EDITORS spec will reach for exists on the page.

WHY A SECOND GUARD, when tests/test_panel_wiring.py already asks every page
whether it has the ids its scripts reach for: that guard reads LITERAL calls —
`$("sources-list")`. The Console's editors do not write literals. They build
every id from the spec:

    const control = (spec, name) => `${spec.prefix}f-${name}`;
    const noteId  = (spec, name) => `${spec.prefix}n-${name}`;

so a spec that lists a field the card has no input for is INVISIBLE to it. The
failure is not a crash either: `edit()` does `const node = $(control(spec,
name)); if (!node) continue;` — the field is silently skipped, the editor opens
looking complete, and the column it could not show is the one silently left at
whatever the sheet already had.

This guard was written with 5.ExportViews and 6.RibbonControls, and it covers
the four editors that came before them too — they had been correct by hand.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Guards the extension: this reads extension/ sources, so a change there must
# run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

EXT = Path(__file__).resolve().parent.parent / "extension"
CONSOLE_JS = EXT / "console.js"
CONSOLE_HTML = EXT / "console.html"

#: Built once per editor from `spec.prefix`, at the line numbers named in the
#: docstring above. A new one added to console.js and not added here would not
#: be checked, which is why the last test asserts the list is complete.
PER_EDITOR_SUFFIXES = ("editor-where", "editor-verdict", "editor-save",
                       "editor-cancel")

#: (editor, field) pairs whose note is fixed prose rather than a slot for a finding,
#: because nothing validates the field and so no finding can exist for it. Each is
#: re-checked below: once console.js names the field outside its editor's field list,
#: the exemption fails and the field needs its slot.
NOTED_IN_PROSE = {
    ("source", "VERSION_TAG"): "nothing validates it; its note at console.html:662-665 says so",
}


def _specs() -> dict[str, dict]:
    """The EDITORS registry, read as text rather than executed.

    console.js imports chrome APIs and cannot be run here, so the spec is parsed
    out. Only what this guard needs: the card id, the prefix, and the fields.
    """
    source = CONSOLE_JS.read_text(encoding="utf-8")
    found: dict[str, dict] = {}
    for name, body in re.findall(
            r"\n  (\w+): \{\n(.*?)\n  \},", source, flags=re.S):
        card = re.search(r'card:\s*"([\w-]+)"', body)
        # `*`, not `+`: the source editor's prefix is "" (console.js:422), and `+`
        # skipped it, so every test below ran on five of the six editors (#846).
        prefix = re.search(r'prefix:\s*"([\w-]*)"', body)
        fields = re.search(r"fields:\s*\[(.*?)\]", body, flags=re.S)
        if not (card and prefix and fields):
            continue
        found[name] = {
            "card": card.group(1),
            "prefix": prefix.group(1),
            "fields": re.findall(r'"(\w+)"', fields.group(1)),
        }
    assert found, "no editor spec was parsed out of console.js; the shape moved"
    declared = len(re.findall(r'\bcard:\s*"', source))
    assert len(found) == declared, (
        f"console.js declares {declared} editor cards and {len(found)} specs were "
        "parsed; the rest are skipped by every test in this file")
    return found


def _ids() -> set[str]:
    return set(re.findall(r'\bid="([\w-]+)"',
                          CONSOLE_HTML.read_text(encoding="utf-8")))


@pytest.mark.parametrize("name", sorted(_specs()))
def test_every_field_an_editor_lists_has_an_input_and_a_note(name):
    """A field with no input is skipped in silence and never shown."""
    spec = _specs()[name]
    ids = _ids()

    missing = [f"{spec['prefix']}f-{field}" for field in spec["fields"]
               if f"{spec['prefix']}f-{field}" not in ids]
    assert not missing, (
        f"the {name} editor lists fields the card has no control for: "
        f"{missing}. `edit()` skips a missing control rather than failing, so "
        "the editor would open looking complete and quietly refuse to show "
        "those columns")

    # The note is where a finding lands. A field with an input and no note is
    # worse than no field at all: it takes a value and never says what the
    # add-in will make of it.
    noteless = [f"{spec['prefix']}n-{field}" for field in spec["fields"]
                if f"{spec['prefix']}n-{field}" not in ids
                and (name, field) not in NOTED_IN_PROSE]
    assert not noteless, (
        f"the {name} editor has controls with nowhere to put their finding: "
        f"{noteless}")


@pytest.mark.parametrize("name,field", sorted(NOTED_IN_PROSE),
                         ids=[f"{name}-{field}" for name, field in sorted(NOTED_IN_PROSE)])
def test_a_field_noted_in_prose_is_still_validated_by_nothing(name, field):
    """An exemption from the note slot holds only while nothing can produce a finding
    for the field: once one can, `judge()` skips the missing slot and drops the finding
    in silence (console.js:633-634)."""
    spec = _specs()[name]
    assert field in spec["fields"], f"{field} is no longer a {name} field; drop its exemption"
    assert f"{spec['prefix']}n-{field}" not in _ids(), (
        f"{spec['prefix']}n-{field} exists now; drop it from NOTED_IN_PROSE")
    word = re.compile(rf"\b{field}\b")
    assert len(word.findall(CONSOLE_JS.read_text(encoding="utf-8"))) == 1, (
        f"console.js names {field} beyond the {name} editor's field list; if something "
        f"validates it now, give it an n-{field} slot and drop the exemption")
    validating = [path.name for path in sorted(EXT.glob("*-rules.js"))
                  if word.search(path.read_text(encoding="utf-8"))]
    assert not validating, (
        f"{validating} name {field}, so a finding for it can exist; give it an "
        f"n-{field} slot and drop the exemption")
    html = CONSOLE_HTML.read_text(encoding="utf-8")
    assert re.search(rf'id="{spec["prefix"]}f-{field}"[^>]*>\s*<p class="field-note">\s*Nothing validates',
                     html), f"the note beside {field} no longer says nothing validates it"


@pytest.mark.parametrize("name", sorted(_specs()))
def test_every_editor_has_its_card_and_its_four_shared_controls(name):
    spec = _specs()[name]
    ids = _ids()

    assert spec["card"] in ids, (
        f"the {name} editor names a card that is not on the page")
    missing = [spec["prefix"] + suffix for suffix in PER_EDITOR_SUFFIXES
               if spec["prefix"] + suffix not in ids]
    assert not missing, f"the {name} editor is missing {missing}"


def test_the_two_late_sheets_have_editors_at_all():
    """A4's own definition: the Console edits all six sheets, not four.

    Named rather than left to the parametrised tests above, because those pass
    perfectly well on a registry that simply does not mention these sheets.
    """
    source = CONSOLE_JS.read_text(encoding="utf-8")
    tabs = set()
    for name in _specs():
        body = re.search(rf"\n  {name}: \{{\n(.*?)\n  \}},", source, flags=re.S)
        tab = re.search(r'tab:\s*"([\w.]+)"', body.group(1)) if body else None
        if tab:
            tabs.add(tab.group(1))

    for tab in ("5.ExportViews", "6.RibbonControls"):
        assert tab in tabs, f"no editor is registered for {tab}"


def test_this_guard_knows_every_id_shape_the_editor_builds():
    """If `edit()` learns a fifth per-editor control, this list has to learn it.

    Without this the guard would keep passing while a new control went
    unchecked — the same shape of blindness it was written to remove.
    """
    # READ THE TEMPLATE, NOT THE CALL AROUND IT. The first version of this
    # matched `$(`${spec.prefix}…`)` and so missed `editor-verdict`, which is
    # reached through `say(...)` — the guard had the very blind spot it exists
    # to close, and only a mutation showed it.
    source = CONSOLE_JS.read_text(encoding="utf-8")
    built = set(re.findall(r"`\$\{spec\.prefix\}([\w-]+)`", source))
    built |= set(re.findall(r"`\$\{spec\.prefix\}([\w-]+)\$\{", source))

    unknown = sorted(built - set(PER_EDITOR_SUFFIXES) - {"f-", "n-"})
    assert not unknown, (
        f"console.js builds {unknown} from the prefix and this guard does not "
        "check it; add it to PER_EDITOR_SUFFIXES")
