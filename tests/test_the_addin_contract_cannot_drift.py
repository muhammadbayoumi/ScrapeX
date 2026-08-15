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

So behaviour is pinned to a NUMBER — and that number is BOOKKEEPING, not a
signal from upstream. This file said otherwise until 2026-08-15, and the
correction matters more than the sentence it replaces:

  mbiXaddin HAS NO `behaviourVersion`. It was proposed to them in
  docs/HANDOFF-mbiXaddin-contract-producer.md and has not been built. Both
  numbers — contract/addin-contract.json's and extension/addin-contract.js's —
  live in THIS repository, and the same commit raises both. Their agreement
  proves ScrapeX is internally consistent about which reading generation it is
  on. IT CANNOT DETECT THAT MBIXADDIN CHANGED. Believing it could is what let
  three of this reading's own cited files move unnoticed.

WHAT ACTUALLY LOOKS UPSTREAM is the last test here. The reading records the
COMMIT it was taken against, and the .cs files it cites are its surface — so
"has anything I read moved?" is a real question with a computable answer. That
test needs the add-in's checkout beside this one; where it is absent it SKIPS
AND SAYS SO, because a guard that is quietly green is the defect this file was
written about.
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
    """THE TWO HALVES OF ScrapeX'S OWN RECORD AGREE ON WHICH READING THEY ARE ON.

    extension/addin-contract.js holds what had to be READ rather than reflected
    over — what a blank means, what is dropped, what fails a table. The JSON
    declares which generation of that reading the repository is shipping; the
    module declares which one it was written against. When they disagree, half
    the reading was updated and half was not.

    WHAT THIS DOES NOT DO, stated here because the docstring claimed it for
    three days: it is NOT a signal from mbiXaddin. Both numbers are ours and one
    commit raises both, so nothing here notices the add-in changing. That is
    test_no_cited_addin_file_has_moved_since_the_reading below, and the number
    is the bookkeeping beside it — not a substitute for it.
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
        f"reading was taken against {read_against.group(1)}, so one half of the "
        "record moved without the other. Whichever is behind, the repair is the "
        "same: re-read the behaviour from the add-in's code at the contract's "
        "readAgainstCommit, update extension/addin-contract.js, and raise both "
        "numbers together. Raising them alone makes this test green and proves "
        "nothing — these numbers are ScrapeX's bookkeeping, not mbiXaddin's "
        "signal.")


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
    """The parsed Sheets hosts and the two whole-address parameter markers.

    These moved in mbiXAddin PR #26: host equality replaced a whole-string
    `docs.google.com` substring and added the genuine spreadsheets host. A
    stale single marker would recreate the repaired false positives here."""
    constants = _contract()["constants"]

    assert constants["URI_GOOGLE_SHEETS_HOSTS"] == [
        "docs.google.com", "spreadsheets.google.com"]
    assert constants["URI_TSV_MARKERS"] == ["output=tsv", "format=tsv"]
    assert constants["URI_TAB_MARKER"] == "gid="

    for host in constants["URI_GOOGLE_SHEETS_HOSTS"]:
        assert host == host.lower() and host == host.strip("."), (
            f"{host!r} is not the normalised host SourceUriValidator compares")
    assert constants["URI_TAB_MARKER"] == constants["URI_TAB_MARKER"].lower()
    for marker in constants["URI_TSV_MARKERS"]:
        assert marker == marker.lower()


# ---- the guard that actually looks upstream ---------------------------------
#
# WHERE THE ADD-IN'S CHECKOUT IS EXPECTED. A sibling of this repository, which is
# how the owner keeps them. Absent — on CI, on a fresh clone — the test below
# SKIPS and names what it could not do. That is deliberate: it is the one guard
# here whose subject lives outside the repository, and pretending otherwise is
# the failure this whole file is about.
ADDIN_CHECKOUT = ROOT.parent / "mbiXaddin"
READING = ROOT / "docs" / "reviews" / "mbiXaddin-config-contract-20260812.md"


def _addin_git(*args: str) -> str | None:
    """`git` inside the add-in checkout, or None when it cannot answer."""
    try:
        done = subprocess.run(("git", "-C", str(ADDIN_CHECKOUT), *args),
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def test_no_cited_addin_file_has_moved_since_the_reading():
    """Has anything the Console's reading was taken FROM changed since?

    THIS IS THE ONE THAT LOOKS UPSTREAM, and until 2026-08-15 nothing did. The
    behaviour numbers above are both ours; they cannot notice mbiXaddin moving.
    Measured the day this was written: three of the eighty .cs files this
    reading cites had already moved, and no test anywhere had an opinion.

    THE SURFACE IS THE READING'S OWN CITATIONS. Every answer in
    docs/reviews/mbiXaddin-config-contract-20260812.md carries the file it came
    from, so those files are exactly what the Console believes it has read. The
    whole add-in is the wrong unit — it releases constantly, and a guard that
    fired on every unrelated commit is a guard that gets skipped.

    A file that has moved is a QUESTION, not a verdict. Read it; if it does not
    touch what the Console believes, record it in `reviewedSince` with the blob
    it was dismissed at and why. Pinning the blob is what stops that entry
    becoming a permanent exemption: the next edit changes it and this fires
    again.
    """
    contract = _contract()
    read_against = contract.get("readAgainstCommit", "")
    assert re.fullmatch(r"[0-9a-f]{40}", read_against), (
        "contract/addin-contract.json does not record the 40-character commit "
        "its reading was taken against, so nothing can ask what has moved since")

    if _addin_git("rev-parse", "--git-dir") is None:
        pytest.skip(
            f"the add-in checkout is not at {ADDIN_CHECKOUT} — upstream drift "
            "since " + read_against[:12] + " was NOT checked by this run")
    if _addin_git("cat-file", "-t", read_against) != "commit":
        pytest.skip(
            f"{ADDIN_CHECKOUT} does not contain {read_against[:12]}; fetch it "
            "before trusting a green run here")
    if _addin_git("rev-parse", "--verify", "origin/main") is None:
        pytest.skip(f"{ADDIN_CHECKOUT} has no origin/main to compare against")

    assert READING.exists(), (
        f"{READING.name} is the reading itself — its file:line citations ARE the "
        "surface this guard watches. Moved or deleted, there is nothing left to "
        "compare and the Console's knowledge has no recorded source")
    cited = set(re.findall(r"[A-Za-z0-9_]+\.cs", READING.read_text(encoding="utf-8")))
    changed = _addin_git("diff", "--name-only", read_against, "origin/main", "--", "*.cs")
    # The reading cites bare filenames; git answers with repository paths. Keep
    # the path so the blob below is looked up rather than guessed at.
    moved = {path.rsplit("/", 1)[-1]: path
             for path in (changed or "").splitlines() if path}

    reviewed = contract.get("reviewedSince", {})
    unexplained = []
    for name in sorted(cited & set(moved)):
        entry = reviewed.get(name)
        blob = _addin_git("rev-parse", f"origin/main:{moved[name]}")
        if entry is None:
            unexplained.append(f"{name} — moved and is not in reviewedSince")
        elif not str(entry.get("why", "")).strip():
            unexplained.append(f"{name} — recorded with no reason")
        elif blob is not None and entry.get("blob") != blob:
            unexplained.append(
                f"{name} — dismissed at blob {str(entry.get('blob'))[:12]} and "
                f"has since moved to {blob[:12]}")

    assert not unexplained, (
        "the Console's reading of mbiXaddin cites files that have changed since "
        f"{read_against[:12]}, and this is the only thing that would have said "
        "so:\n  " + "\n  ".join(unexplained)
        + "\n\nRead each one at origin/main. If it does not change what the "
          "Console believes, add or update its entry in the contract's "
          "reviewedSince with the current blob and the reason. If it does, the "
          "reading is stale — re-read it and raise behaviourVersion.")

    stale = set(reviewed) - (cited & set(moved))
    assert not stale, (
        f"reviewedSince still carries {sorted(stale)}, which no longer appear "
        "as moved cited files — either the reading was refreshed past them or "
        "they were never cited. A dismissal list nobody prunes becomes a "
        "permission slip.")


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
    vocabularies = _contract()["vocabularies"]
    # A LOG_TAG is not an error code — there is no ValidationResult behind it —
    # but it IS a string the add-in prints, which is the only property that
    # matters here: an owner can search its log for it and find something.
    known = set(vocabularies["ERROR_CODES"]) | set(vocabularies["LOG_TAGS"])

    borrowed = _js_object(hand_written, "ERROR_CODE") | _js_object(hand_written, "LOG_TAG")
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
