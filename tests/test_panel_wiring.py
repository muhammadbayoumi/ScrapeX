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
import shutil
import subprocess
from pathlib import Path

import pytest

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

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


def test_the_dom_harness_inlines_every_module_the_panel_imports():
    """tools/panel_harness.py flattens the module graph by hand, and a module
    left off that list does not fail loudly.

    MET ON 2026-08-11. extension/accounts.js was added and wired into app.js but
    not into the harness, so the harness stripped app.js's imports and every
    call into it raised ReferenceError at the call site. Those calls are wrapped
    in try/catch on purpose — the panel has to survive a storage fault — so the
    remembered-accounts directory was silently never written while every visible
    part of the panel, and every existing test, kept passing.

    A missing module can break a feature outright or, worse, half of one. This
    check is static and cheap, and it is the only thing standing between the two.
    """
    harness = (Path(__file__).resolve().parent.parent
               / "tools" / "panel_harness.py").read_text(encoding="utf-8")
    imported = set(re.findall(r'^import[\s\S]*?from "\./([\w.-]+\.js)";', JS, flags=re.M))
    assert imported, "app.js appears to import nothing, so this guard reads the wrong file"

    inlined = set(re.findall(r'EXT / "([\w.-]+\.js)"', harness))
    missing = sorted(imported - inlined)
    assert not missing, (
        "tools/panel_harness.py does not inline modules app.js imports, so every "
        f"call into them is a ReferenceError inside the harness: {missing}")


def _pages_and_what_their_scripts_reach_for():
    """Every page in the extension, paired with the ids it defines and the ids
    the scripts IT loads reach for. Ids a script renders itself count as defined,
    the same allowance the app-only check above makes."""
    pairs = []
    for page in sorted(EXT.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        defined = set(re.findall(r'\bid="([\w-]+)"', html))
        referenced: set[str] = set()
        for name in re.findall(r'<script[^>]*\bsrc="([\w./-]+)"', html):
            source_file = EXT / name
            assert source_file.exists(), f"{page.name} loads {name}, which is not there"
            source = source_file.read_text(encoding="utf-8")
            defined |= set(re.findall(r'\bid="([\w-]+)"', source))
            referenced |= set(re.findall(r'\$\("([\w-]+)"\)', source))
            referenced |= set(re.findall(r'getElementById\("([\w-]+)"\)', source))
        pairs.append(pytest.param(page.name, defined, referenced, id=page.name))
    return pairs


@pytest.mark.parametrize("page,defined,referenced",
                         _pages_and_what_their_scripts_reach_for())
def test_no_page_reaches_for_an_element_it_does_not_have(page, defined, referenced):
    """THE SAME CHECK AS ABOVE, FOR EVERY PAGE — because the one page it did not
    cover is the one that broke.

    `onboarding.html`'s steps were rewritten for the downloaded engine and the
    `#cmd-host` span went with them. `onboarding.js` still wrote a command into
    it, as the second statement of an async `init()` called from a
    DOMContentLoaded listener — so the TypeError became a silent unhandled
    rejection, every line after it was skipped, and Start engine, Check again and
    Open ScrapeX were all dead on a page that rendered perfectly.

    The panel had this guard from the day the Add Site form came apart the same
    way. Onboarding did not, because the guard named two files instead of asking
    the directory what pages exist.
    """
    missing = sorted(referenced - defined)
    assert not missing, (
        f"{page} loads a script that reaches for ids the page does not have: "
        f"{missing} — the first one to be missing kills every binding after it")


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


@pytest.mark.parametrize(
    "page", sorted(EXT.glob("*.html")), ids=lambda p: p.name)
def test_the_interface_stays_english(page):
    """Spec 1: Arabic is data, never interface. The stress fixtures that do
    carry Arabic live in the screenshot harness.

    EVERY SHIPPED PAGE, not just the panel. This read only app.html until
    2026-08-12, so onboarding.html was never checked and neither would the
    Console have been — and the Console is the page most likely to grow an
    Arabic label, because it edits a workbook whose own DATA is bilingual.

    The panel's own markup is the strictest case and the others follow it, so
    one rule covers all of them rather than a list somebody has to remember to
    extend.
    """
    arabic = re.findall(r"[؀-ۿ]+", page.read_text(encoding="utf-8"))
    assert not arabic, (
        f"Arabic leaked into {page.name}: {arabic[:3]}")


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


def test_every_panel_script_actually_parses():
    """A raw line break inside a "..." string shipped a panel that threw on load
    and rendered nothing below the Sources list.

    It survived a `node --check extension/app.js`, which exits 0 on this file
    whatever it contains - Node treats a lone .js with import statements as
    ambiguous and does not parse it. `--input-type=module` on stdin does parse
    it, and that is the only spelling of the check that works here.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH")
    for script in sorted(EXT.glob("*.js")):
        done = subprocess.run(
            [node, "--input-type=module", "--check"],
            input=script.read_bytes(), capture_output=True)
        assert done.returncode == 0, (
            f"{script.name} does not parse: "
            + done.stderr.decode("utf-8", "replace")[:800])


# ---- every screen loads what it shows --------------------------------------

def _show_view_body() -> str:
    """The body of showView, where a screen says what it needs loaded."""
    start = JS.index("function showView(")
    depth, index = 0, JS.index("{", start)
    for position in range(index, len(JS)):
        if JS[position] == "{":
            depth += 1
        elif JS[position] == "}":
            depth -= 1
            if depth == 0:
                return JS[index:position + 1]
    raise AssertionError("showView has no closing brace")


#: The container each screen fills, and the function that fills it. A screen
#: that paints a skeleton and never replaces it is indistinguishable from a slow
#: engine, so this is asserted rather than left to a reader of two files.
SCREEN_LOADERS = {
    "settings": ["loadSchedules", "loadStorage", "loadOutputs"],
    "data": ["loadDatasets"],
    "sources": ["loadSources"],
}


@pytest.mark.parametrize("screen,loaders", sorted(SCREEN_LOADERS.items()))
def test_every_screen_loads_what_it_shows(screen, loaders):
    """FOUND ON 2026-08-11, and it had been true for a long time.

    `loadOutputs` had exactly one caller: loadRunDestination, which returns
    early unless the current view is "run" AND the engine is up. The
    destinations list lives on the SETTINGS screen. So an owner who opened
    Settings without first visiting Run saw the loading skeleton at
    app.html's #outputs forever, with nothing on the screen to say why — and
    every test passed, because no test asked who loads it.

    This is the panel-wiring twin of the Add Site defect this file was written
    for: two halves that must refer to each other, and nothing checking that
    they do.
    """
    body = _show_view_body()
    branch = re.search(
        r'if\s*\(\s*name\s*===\s*"%s"\s*\)\s*\{(.*?)\n\s{2}\}' % screen,
        body, re.S)
    single = re.findall(r'if\s*\(\s*name\s*===\s*"%s"\s*\)\s*(\w+)\(' % screen, body)
    called = set(re.findall(r"(\w+)\(", branch.group(1))) if branch else set(single)

    missing = [name for name in loaders if name not in called]
    assert not missing, (
        f'showView("{screen}") never calls {", ".join(missing)}, so whatever '
        "that function fills stays as its loading skeleton until some other "
        "screen happens to load it. That is what happened to #outputs.")


# ---- a module nobody imports is a module that does not exist ----------------

#: Every ES module under extension/ that the panel is supposed to USE, not just
#: ship. `bundleview.js` is the reason this list exists: it was written,
#: reviewed, merged and covered by a cross-language test, and app.js never
#: imported it — so the "read your data with no engine installed" feature was
#: complete in every respect except being reachable. drive.js and sheets.js were
#: one commit away from the same fate.
PANEL_MODULES = ["engine.js", "transport.js", "version.js", "releases.js",
                 "identity.js", "startup.js", "drive.js", "sheets.js",
                 "bundleview.js"]


@pytest.mark.parametrize("module", PANEL_MODULES)
def test_the_panel_actually_imports_the_module(module):
    """Written, tested and unreachable is the failure this repository keeps
    making. It is not caught by any suite that tests the module itself: those
    pass perfectly, which is exactly what makes it hard to notice."""
    imported = set(re.findall(r'from\s+"\./([\w.-]+)"', JS))
    assert module in imported, (
        f"extension/{module} is not imported by app.js. Its own tests pass and "
        "nothing it provides reaches the panel — the defect bundleview.js sat "
        "in for months.")


def test_the_offline_reader_is_reachable_from_the_data_page():
    """bundleview.js was written, tested across two languages, and imported by
    nothing for months. The sentinel that used to live here — a test asserting
    it was NOT imported, which would fail the day someone wired it — has done
    its job and is gone.

    What replaces it is narrower and worth more: being imported is not the same
    as being reachable. The offline path has to be OFFERED, and the only place
    it can be is where the engine has just failed."""
    assert "browseFromDrive" in JS, "the offline reader has no entry point"
    assert re.search(r'catch[^}]*?browse-offline', JS, re.S), (
        "the Drive fallback is not offered where the engine request fails, so "
        "a machine with no engine still reaches a dead end — which is the whole "
        "case the bundle format exists for")


def test_no_two_inlined_modules_declare_the_same_top_level_name():
    """The DOM harness concatenates the panel's modules into ONE classic script,
    and two modules declaring the same `const` is a SyntaxError that kills the
    whole page.

    FOUND ON 2026-08-12 the expensive way. drive.js and sheets.js both declared
    `FILES`, `FOLDER_MIME` and `headers`. The harness produced a page that threw
    before anything ran, four account tests timed out after thirty seconds each
    waiting for an element that could never appear, and not one of the messages
    said "SyntaxError" — Playwright reports what it was waiting for, not why the
    page is dead.

    `headers` is the worse half of the pair. Function declarations may be
    redeclared, so it would NOT have thrown: sheets.js's version would silently
    replace drive.js's, and the harness would test error messages that the real
    panel never produces.

    Checked here rather than left to the harness because the failure this
    produces is unreadable at the point it happens, and one name is enough.
    """
    modules = ["startup.js", "transport.js", "version.js", "releases.js",
               "identity.js", "accounts.js", "drive.js", "sheets.js",
               "bundleview.js", "engine.js"]
    seen: dict[str, str] = {}
    clashes: list[str] = []
    for name in modules:
        body = (EXT / name).read_text(encoding="utf-8")
        body = re.sub(r"^import[\s\S]*?;\s*$", "", body, flags=re.M)
        body = re.sub(r"\bexport\s+", "", body)
        for declared in re.findall(
                r"^(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)", body, re.M):
            if declared in seen and seen[declared] != name:
                clashes.append(f"{declared} in both {seen[declared]} and {name}")
            seen.setdefault(declared, name)

    assert not clashes, (
        "two panel modules declare the same top-level name, and the DOM harness "
        "flattens them into one script: " + "; ".join(clashes))


def test_every_source_action_the_menu_offers_is_handled():
    """A menu entry with no branch does nothing and says nothing.

    The Export entry shipped DISABLED on 2026-08-12 with its reason written on
    it, and was enabled the next day when the engine route existed. The risk
    either way is the same: the markup and the handler drift, and the owner
    clicks something that silently is not there. Read from the one list that
    builds the markup, so adding an entry without a branch fails here.
    """
    listed = set(re.findall(r'\{action: "(\w+)"', JS))
    assert listed, "SOURCE_ACTIONS no longer declares any action"

    body = JS[JS.index("async function runSourceAction("):]
    body = body[:body.index("\n}\n")]
    handled = set(re.findall(r'action === "(\w+)"', body))

    missing = sorted(listed - handled)
    assert not missing, (
        f"the source menu offers {missing} and runSourceAction has no branch "
        "for them, so the click does nothing at all")


def test_the_export_action_is_no_longer_advertised_as_unbuilt():
    """It was, deliberately, for one day. Leaving the words behind after the
    thing exists is how a working feature keeps telling people it does not."""
    assert 'action: "sheet"' in JS
    entry = JS[JS.index('{action: "sheet"'):]
    entry = entry[:entry.index("},")]
    assert "ready: false" not in entry, (
        "the export action is still marked unbuilt while the engine route and "
        "the panel handler both exist")
    assert "Not built yet" not in entry
