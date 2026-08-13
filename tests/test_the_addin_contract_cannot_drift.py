"""The Console's rules and mbiXaddin's code cannot drift apart in silence.

THE PROBLEM THIS EXISTS FOR. mbiXaddin is a separate repository on a separate
release cycle, and it decides everything the Console validates against: which
values a column accepts, what a blank cell means, whether a bad row is dropped
or fails a whole table. The first version of that knowledge was TRANSCRIBED —
seven agents read ~350 .cs files and I typed the answers into a module. Correct
on the day, and silently wrong the moment anyone added an enum value, because
nothing anywhere compared the two.

TWO KINDS OF DRIFT, AND ONLY ONE CAN BE AUTOMATED.

  The VOCABULARIES are mechanical: an enum is an enum. contract/addin-contract.json
  holds them, tools/sync_addin_contract.py generates extension/addin-vocabulary.js
  from it, and the first test below fails if the two disagree — so the generated
  file cannot be hand-edited and the JSON cannot move without regenerating.

  The BEHAVIOUR is not. "A blank IS_ACTIVE means the row is live", "an unknown
  transform is dropped rather than refused", "a source with no mappings hard-fails"
  — none of that is in a type, and no generator will ever find it.

So behaviour is pinned to a NUMBER instead. mbiXaddin raises `behaviourVersion`
when it changes how a fault is handled; extension/addin-contract.js records the
version its reading was taken against; and the second test fails when they
differ. It cannot force anyone to re-read the code. It can make it impossible to
change the behaviour SILENTLY, which is the whole of what a guard can do here.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Guards the extension: this reads extension/ sources, so a change there must
# run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contract" / "addin-contract.json"
GENERATED = ROOT / "extension" / "addin-vocabulary.js"
HAND_WRITTEN = ROOT / "extension" / "addin-contract.js"
GENERATOR = ROOT / "tools" / "sync_addin_contract.py"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_the_generated_vocabulary_is_what_the_contract_would_produce():
    """The mechanical half, and the only test here that can be fully automatic.

    It fails in both directions at once: a hand edit to the generated file, and
    a change to the JSON that nobody regenerated. Either way the Console would
    be validating against something the add-in never said.
    """
    finished = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True, text=True, cwd=ROOT)

    assert finished.returncode == 0, (
        "extension/addin-vocabulary.js is not what contract/addin-contract.json "
        "would produce, so the Console is offering values the add-in does not "
        f"accept, or refusing values it does.\n\n{finished.stdout}{finished.stderr}")


def test_the_generated_file_says_it_is_generated():
    """A file that does not announce itself gets edited by hand, once, by
    someone in a hurry — and the edit survives until the next regeneration
    silently discards it."""
    head = GENERATED.read_text(encoding="utf-8")[:400]

    assert "GENERATED" in head
    assert "sync_addin_contract.py" in head, (
        "the generated file does not name the command that rewrites it, so "
        "whoever finds it wrong has to go looking")


def test_the_behaviour_reading_is_not_older_than_the_contract():
    """THE HALF NO GENERATOR CAN CHECK.

    extension/addin-contract.js holds what had to be READ rather than reflected
    over — what a blank means, what is dropped, what fails a table. When
    mbiXaddin raises its behaviourVersion it is saying one of those answers has
    moved, and this fails until someone goes and looks.

    Raising the number here WITHOUT re-reading would satisfy this test and
    defeat the only mechanism guarding that half. The message says so.
    """
    declared = _contract()["behaviourVersion"]
    read_against = re.search(
        r"READ_AGAINST_BEHAVIOUR_VERSION\s*=\s*(\d+)",
        HAND_WRITTEN.read_text(encoding="utf-8"))

    assert read_against, (
        "extension/addin-contract.js no longer declares which behaviour version "
        "its reading describes, so nothing can tell whether it is current")

    assert int(read_against.group(1)) == declared, (
        f"the contract declares behaviour version {declared} and the Console's "
        f"reading was taken against {read_against.group(1)}. mbiXaddin changed "
        "how it handles a fault or a default — go and re-read that behaviour "
        "from its code, update extension/addin-contract.js, and only then raise "
        "READ_AGAINST_BEHAVIOUR_VERSION. Raising the number alone makes this "
        "test green and the Console wrong.")


def test_every_sheet_the_contract_names_carries_a_gid_and_its_columns():
    """A tab with no gid cannot be found; a tab with no columns cannot be read.
    Both are shapes a hand-edited JSON can take and a generator cannot."""
    for tab, spec in _contract()["sheets"].items():
        assert spec.get("gid", "").isdigit(), f"{tab} has no numeric gid"
        assert spec.get("columns"), f"{tab} declares no columns"
        assert "registryCritical" in spec, (
            f"{tab} does not say whether a fetch failure there aborts the whole "
            "sync — which decides how loudly the Console must complain about it")


def test_no_vocabulary_is_empty():
    """An empty list is the shape a failed extraction takes. It would make the
    Console offer nothing and accept anything, which is worse than refusing to
    start."""
    empty = sorted(name for name, values
                   in _contract()["vocabularies"].items() if not values)

    assert not empty, (
        f"{empty} are empty. A vocabulary the generator could not derive must "
        "be named as a gap, not shipped as an empty list")


def test_the_true_and_false_spellings_do_not_overlap():
    """Measured in the add-in: sixteen spellings across two languages. A value
    in both sets would make one of them unreachable, and which one wins would
    depend on the order the Console happens to check."""
    vocabularies = _contract()["vocabularies"]
    both = sorted(set(vocabularies["TRUE_SPELLINGS"])
                  & set(vocabularies["FALSE_SPELLINGS"]))

    assert not both, f"{both} count as both true and false"


def test_the_arabic_spellings_survived_the_json_round_trip():
    """They are the easiest thing here to lose. An `ensure_ascii` somewhere in
    the pipe turns them into escapes that still WORK and that nobody can read in
    a review — and the day one is wrong, nobody will spot it."""
    vocabularies = _contract()["vocabularies"]

    for spelling in ("نعم", "صح", "صحيح"):
        assert spelling in vocabularies["TRUE_SPELLINGS"], (
            f"{spelling} is no longer accepted as true, and the add-in accepts it")
    for spelling in ("لا", "خطأ", "غلط"):
        assert spelling in vocabularies["FALSE_SPELLINGS"]

    # And in the generated file, as characters rather than as \uXXXX.
    assert "نعم" in GENERATED.read_text(encoding="utf-8"), (
        "the generated module escaped the Arabic spellings; they still work and "
        "nobody can review them")


def test_the_address_markers_are_the_add_ins_own_literals():
    """`SourceUriValidator` searches the whole address for these three, and every
    Console warning about an address is keyed on them. Inline, they drifted
    silently; here, a change to the add-in has to be typed on purpose.

    The lower case matters and is not cosmetic: the add-in lower-cases the
    address before searching, so a marker carrying a capital would never match
    and the Console would fall silent about the mistake its own file header calls
    the commonest one there is."""
    constants = _contract()["constants"]

    assert constants["URI_GOOGLE_SHEETS_MARKER"] == "docs.google.com"
    assert constants["URI_TSV_MARKERS"] == ["output=tsv", "format=tsv"]
    assert constants["URI_TAB_MARKER"] == "gid="

    for name in ("URI_GOOGLE_SHEETS_MARKER", "URI_TAB_MARKER"):
        assert constants[name] == constants[name].lower(), (
            f"{name} is compared against a lower-cased address and would never "
            "match")
    for marker in constants["URI_TSV_MARKERS"]:
        assert marker == marker.lower()


def _js_object(source: str, name: str) -> dict[str, str]:
    """The string values of a flat `export const NAME = {...}` literal.

    Deliberately crude — it reads the declaration as text rather than running it.
    Comments inside the object are skipped, which is why the values are matched
    rather than the whole body scanned."""
    body = re.search(rf"export const {name} = {{(.*?)\n}};", source, re.S)
    assert body, f"{name} is no longer a flat object literal, and this test read it as one"
    return dict(re.findall(r'(\w+):\s*"([^"]+)"', body.group(1)))


def test_every_code_the_console_reports_is_one_the_add_in_can_emit():
    """The Console prints a code so an owner can search BOTH surfaces for it. A
    code the add-in never emits sends them looking through its log for a string
    that is not in it — which is worse than printing no code at all.

    This was wrong on nine DataSource findings: the Console said INVALID_VALUE
    where `DataSourceEntity.Validate()` and `SourceUriValidator` both emit
    ERR_FORMAT. INVALID_VALUE is real, but it lives in `ConfigValidator` and is
    reached only through a JSON config bag."""
    hand_written = HAND_WRITTEN.read_text(encoding="utf-8")
    known = set(_contract()["vocabularies"]["ERROR_CODES"])

    borrowed = _js_object(hand_written, "ERROR_CODE")
    unknown = sorted({code for code in borrowed.values() if code not in known})
    assert not unknown, (
        f"{unknown} are reported by the Console and are not in the add-in's "
        "vocabulary. Either the add-in gained a code and the contract has not "
        "been re-read, or the Console invented one")

    # And the other direction, which is the half that actually went wrong: a
    # finding with no add-in rule must NOT be dressed in one of its codes.
    console_only = _js_object(hand_written, "CONSOLE_ONLY_CODE")
    assert console_only, "CONSOLE_ONLY_CODE is empty; it is the escape hatch this test depends on"
    borrowed_by_mistake = sorted({code for code in console_only.values() if code in known})
    assert not borrowed_by_mistake, (
        f"{borrowed_by_mistake} claim to be Console-only and are the add-in's "
        "own codes. If the add-in now has a rule for that fault, the code "
        "belongs in ERROR_CODE instead")


def test_the_hand_written_half_does_not_redeclare_the_generated_half():
    """Two sources for one list is the defect this whole file exists to prevent,
    and the tidiest place for it to reappear is the module that re-exports the
    other."""
    text = HAND_WRITTEN.read_text(encoding="utf-8")
    declared = set(re.findall(r"^export const ([A-Z_]+)\s*=", text, re.M))
    generated = set(re.findall(r"^export const ([A-Z_]+)\s*=",
                               GENERATED.read_text(encoding="utf-8"), re.M))

    both = sorted(declared & generated)
    assert not both, (
        f"{both} are declared in extension/addin-contract.js AND generated into "
        "extension/addin-vocabulary.js. The generated one is authoritative; the "
        "hand-written copy will drift from it and nothing will say so.")
