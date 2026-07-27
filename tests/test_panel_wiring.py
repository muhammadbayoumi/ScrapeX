"""The panel's markup and its script must actually refer to each other.

This exists because of a real defect: the Add Site form was replaced by a Source
picker, the picker was never wired to anything, and the working form was left in
the markup behind `hidden aria-hidden="true"` with NOTHING in app.js referencing
it. Every test passed, the screenshots looked right, and a new owner could not
register a site at all.

These are static checks over the two files. They cannot prove the panel behaves
correctly — that needs the DOM harness — but they do prove the two halves are
still connected, which is exactly what silently came apart.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parent.parent / "extension"
HTML = (EXT / "app.html").read_text(encoding="utf-8")
JS = (EXT / "app.js").read_text(encoding="utf-8")

# Ids the markup defines, PLUS ids the script itself renders into the page —
# several rows are built with innerHTML and bound immediately afterwards, which
# is legitimate and must not be reported as a dangling reference.
DEFINED = set(re.findall(r'\bid="([\w-]+)"', HTML)) | \
    set(re.findall(r'\bid="([\w-]+)"', JS))
REFERENCED = set(re.findall(r'\$\("([\w-]+)"\)', JS)) | \
    set(re.findall(r'getElementById\("([\w-]+)"\)', JS))


def test_every_element_the_script_reaches_for_exists():
    """`$("x")` on an id no template renders returns null and the handler dies,
    usually taking every later binding in the same function with it."""
    missing = sorted(REFERENCED - DEFINED)
    assert not missing, f"app.js reaches for ids that app.html does not define: {missing}"


def test_the_add_site_form_is_reachable_from_the_script():
    """The exact regression: a complete form nothing could ever reveal."""
    assert "source-detail" in DEFINED, "the confirm-and-add form is gone"
    assert "source-detail" in REFERENCED, \
        "nothing in app.js reveals the add-site form — a new owner cannot add a site"


def test_no_element_is_permanently_hidden_from_assistive_tech():
    """`aria-hidden` on a container that becomes visible lies to a screen reader.

    Hiding is done with the `hidden` class, which JavaScript removes; aria-hidden
    would stay behind and keep the revealed form invisible to assistive tech.
    """
    stuck = re.findall(r'<div id="([\w-]+)"[^>]*\baria-hidden="true"[^>]*>', HTML)
    assert not stuck, f"these containers are hidden from assistive tech forever: {stuck}"


@pytest.mark.parametrize("handler", ["cur-use", "urls-check", "check", "add-btn"])
def test_every_source_entry_point_has_a_listener(handler):
    """Each way into the add-site flow must be bound, not merely present."""
    assert re.search(rf'\$\("{handler}"\)\.addEventListener', JS), \
        f"#{handler} is rendered but nothing listens to it"


def test_the_unbuilt_file_source_is_disabled_not_silent():
    """A control that looks ready and does nothing is worse than one that says so."""
    block = HTML[HTML.index('id="source-file"'):HTML.index('id="source-detail"')]
    assert "Not built yet" in block
    for action in ("file-upload", "screenshot-capture"):
        assert re.search(rf'disabled data-integration="{action}"', block), \
            f"the {action} button is enabled but nothing implements it"


def test_the_interface_stays_english():
    """Spec 1: Arabic is data, never interface. The panel's own markup carries
    no Arabic — the stress fixtures that do live in the screenshot harness."""
    arabic = re.findall(r"[؀-ۿ]+", HTML)
    assert not arabic, f"Arabic leaked into the panel markup: {arabic[:3]}"


# ---- run modes are offered according to the DATA -----------------------------
#
# "Update existing data" over sites with no data is not an update of anything,
# and a rebuild has nothing to archive; "Initial crawl" over sites that all
# have data already happened. The owner's rule: the choices follow the data.
# Static pins over the wiring — the behaviour itself runs in the DOM.

def test_mode_availability_is_computed_from_the_selected_sources_data():
    assert "syncModeChoices" in JS
    assert "Number(s.observations) > 0" in JS, (
        "availability no longer consults the sources' data")
    # It must run on every selection change, and refreshRunButton is the one
    # funnel every selection path already goes through.
    assert re.search(r"function refreshRunButton\(\) \{\s*syncModeChoices\(\);", JS), (
        "syncModeChoices is not wired into the selection funnel")


def test_every_mode_the_select_offers_is_covered_by_the_availability_map():
    """A new <option> that the map does not know would be enabled forever —
    silently exempt from the owner's rule."""
    offered = set(re.findall(r'<option value="([\w-]+)"', HTML.split('id="run-mode"')[1]
                             .split("</select>")[0]))
    mapped = set(re.findall(r"(update|initial_crawl|full_rebuild|history_backfill):\s", JS))
    assert offered <= mapped, f"modes without an availability rule: {offered - mapped}"


def test_a_meaningless_chosen_mode_is_moved_not_run():
    """If the selection changes under a chosen mode, the run must not quietly
    proceed with a mode that stopped meaning anything."""
    assert 'select.value = withData > 0 ? "update" : "initial_crawl"' in JS


# ---- schedules are EDITABLE from the panel -----------------------------------

def test_the_schedules_section_is_an_editor_not_a_list():
    """The API could create schedules since spec 26; the panel could only read
    them — so the section said "No schedules yet" forever with no way to
    change that, which the owner reported verbatim."""
    assert '/api/schedules/' in JS.replace('"', "'"), "no save path — still read-only"
    # FULL control (owner's ruling: this section is THE central place for
    # scheduling) — every knob the schedule model has must be present.
    for role in ("freq", "weekday", "time", "save", "tz", "mode",
                 "missed", "overlap", "enabled"):
        assert f'data-role="{role}"' in JS, f"the {role} control is missing"
    # The scheduler fires only ACTIVE sources; a schedule that will not fire
    # must say so on its own row.
    assert "Auto is off for this site" in JS
    # 0=Monday, the server's convention — a drifted weekday list would fire
    # runs a day away from what the owner picked.
    assert '"Monday", "Tuesday"' in JS


def test_the_autostart_control_says_which_failure_it_hit():
    """Two silences in one control, both of them shipped.

    The click handlers were `try { await setAutostart(...) } finally { ... }` —
    a try/finally with NO catch — so a host answering ok:false rejected, the
    throw unwound past the re-render, and the label went on saying "off" with
    nothing said anywhere. And the render's own `catch (_)` reported all five
    failure classes as "needs the one-time launcher install", which sends the
    owner to Setup for a `forbidden` (reloaded from another folder) or a
    `timeout` (cold start) that Setup does not repair. transport.js:19-24
    records that exact incident on a machine where the launcher was working.
    """
    block = JS[JS.index("async function renderAutostart"):JS.index("// ---- shell")]

    assert "catch (_)" not in block, \
        "the autostart control still discards the error object it needs"
    assert block.count("catch (err)") >= 3, \
        "both click handlers and the render must each name their failure"
    assert "hostFailureReason" in block, \
        "the kind->sentence mapping must be the shared one, not a second copy"
    # Only `absent` may be reported as a missing install.
    assert '"absent"' in block, "the render no longer distinguishes a missing helper"
    for other in ("forbidden", "crashed", "timeout"):
        assert f'"{other}"' in JS, f"the panel has no message for {other}"


def test_the_host_failure_reason_is_defined_once():
    """A second copy is how the two controls came to disagree about the same
    failure: startEngine branched on all five kinds while the autostart control
    called every one of them 'not installed'."""
    assert JS.count("function hostFailureReason") == 1
    for kind in ("absent", "forbidden", "crashed", "timeout"):
        assert f'kind === "{kind}"' in JS, f"hostFailureReason does not name {kind}"


def test_no_surface_ships_double_encoded_text():
    """Nine strings in the source editor and Sources tab shipped as mojibake -
    an em dash, curly quotes, an ellipsis and a middot that were encoded to
    UTF-8 and then re-decoded as Latin-1, so every empty field painted a
    literal `â€”` on screen. The correct spellings of the same glyphs
    were a few lines away in the same file, which is how a copy-paste from the
    wrong half spreads it."""
    mojibake = ("â€”", "â€œ", "â€",
                "â€¦", "Â·", "â€™")
    for name, text in (("app.js", JS), ("app.html", HTML)):
        for bad in mojibake:
            assert bad not in text, (
                f"{name} ships double-encoded text ({bad!r}) - it renders as garbage")
