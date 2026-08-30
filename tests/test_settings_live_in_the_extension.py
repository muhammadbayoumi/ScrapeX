"""The owner's rule, made mechanical: settings live in the extension.

«لا اريد اى اعدادت على صفحة الويب — الاعدادت كلها على extension بينما صفحة
الويب للعرض فقط» (2026-07-29).

The rule earned itself. `crawl_honour_delay` and `crawl_min_interval_s` had
been built, plumbed all the way to HttpFetcher, and rendered ONLY on the
engine's web page — so from the side panel, where the work actually happens,
they did not exist, and the owner asked for a feature that had shipped weeks
earlier. A rule that lives only in a commit message is a rule that gets broken
by the next person in a hurry; this one fails the build instead.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
WEB_SETTINGS = ROOT / "scrapex" / "webui" / "templates" / "settings.html"
PANEL = ROOT / "extension" / "app.html"

# The engine's OWN lifecycle is not a setting: restarting or upgrading the
# runtime is a repair you may need precisely when the panel cannot reach it.
# So these two may appear on the web page.
#
# What they may NOT do is appear ONLY there. Owner ruling, 2026-08-01: the
# extension is the control room, and a capability the page has and the panel
# lacks is a defect. This set was an exemption list; it is now a parity list,
# and the test below reads it in the other direction too.
RUNTIME_REPAIR_IDS = {"runtime-restart", "runtime-upgrade"}

# THE NINE THE GUARD COULD NOT SEE UNTIL 2026-08-12, and the date matters: they
# are not newly broken, they were newly VISIBLE. The guard read settings.html as
# flat text, `{% include %}` is not expanded that way, and settings.html has no
# controls of its own — so it asserted against an empty set and passed, while
# these nine sat in the two partials it includes.
#
# They are the destructive half of Storage and Retention — move the database,
# start fresh, restore from a backup, prune — and they drive thirteen write
# routes the panel cannot reach at all. app.js opens `/settings#s-storage`
# precisely because of that, which is the violation admitting itself.
#
# They are exempted rather than deleted because deleting them would take away
# the only way to do those things, and moving them is B3 of the migration plan:
# the typed confirmations and the disabled-until-valid interlocks are safety,
# and safety moves WITH the control or not at all.
#
# THIS LIST MAY ONLY SHRINK. A tenth control fails the test below; an entry that
# has been migrated and left here fails the one after it. Both directions,
# because a debt list nobody prunes becomes a permission slip.
MIGRATING_TO_THE_PANEL = {
    # _storage.html
    "backup_folder", "export-folder", "fresh-confirm", "move-folder",
    "restore-pick",
    # _retention.html
    "ret-action", "ret-days", "ret-excluded", "ret-source",
}


def _control_ids(html: str) -> set[str]:
    return {m.group(1) for m in re.finditer(
        r'<(?:input|select|textarea)[^>]*\bid="([^"]+)"', html)}


def _with_includes(template: Path, seen: set[Path] | None = None) -> str:
    """The template AND everything it pulls in, as one string.

    THE GUARD BELOW WAS BLIND FOR MONTHS AND SAID NOTHING, which is worse than
    having been absent. It read settings.html as raw text — and Jinja's
    `{% include %}` is not expanded when a file is read as text. settings.html
    contains ZERO controls of its own, so the assertion passed against an empty
    set, every time, while nine controls sat one line away in its partials:

        settings.html:191  {% include "_storage.html" %}    5 controls
        settings.html:350  {% include "_retention.html" %}  4 controls

    A test that cannot see the thing it forbids is not a weaker test. It is a
    licence, because everyone downstream reads its green as an answer.
    """
    seen = seen if seen is not None else set()
    if template in seen or not template.exists():
        return ""
    seen.add(template)

    text = template.read_text(encoding="utf-8")
    for name in re.findall(r'{%-?\s*include\s+"([^"]+)"', text):
        text += "\n" + _with_includes(template.parent / name, seen)
    return text


def test_the_web_page_offers_no_setting_to_change():
    """It shows what the engine holds. It does not change it."""
    stray = (_control_ids(_with_includes(WEB_SETTINGS))
             - RUNTIME_REPAIR_IDS - MIGRATING_TO_THE_PANEL)

    assert not stray, (
        "the engine's web page grew a control again: "
        f"{sorted(stray)}. Settings belong in extension/app.html — a setting "
        "the owner cannot reach from the side panel is a setting he does not "
        "have. If this is one of the Storage/Retention controls already being "
        "moved, it belongs in MIGRATING_TO_THE_PANEL — but read that list's "
        "comment first: it may only shrink.")


def test_the_guard_above_can_actually_see_into_an_include():
    """The guard's own eyesight, checked — because it had none.

    Written against a synthetic pair rather than against settings.html, so it
    keeps testing the MECHANISM after the real page is cleaned up and its
    includes carry nothing left to find.
    """
    with tempfile.TemporaryDirectory() as directory:
        here = Path(directory)
        (here / "_partial.html").write_text(
            '<input id="a-control-hiding-in-a-partial" type="text">',
            encoding="utf-8")
        (here / "page.html").write_text(
            'no controls of my own\n{% include "_partial.html" %}\n',
            encoding="utf-8")

        found = _control_ids(_with_includes(here / "page.html"))

    assert "a-control-hiding-in-a-partial" in found, (
        "the guard reads the page as flat text again, so a control one "
        "`{% include %}` away is invisible to it — which is exactly how nine "
        "of them lived on the engine's Settings page while this file reported "
        "green")


def test_the_include_walk_survives_a_cycle():
    """A partial that includes its own parent must not hang the suite. Cheap to
    guard, and the failure mode is a run that never finishes rather than one
    that fails."""
    with tempfile.TemporaryDirectory() as directory:
        here = Path(directory)
        (here / "a.html").write_text('{% include "b.html" %}<input id="in-a">',
                                     encoding="utf-8")
        (here / "b.html").write_text('{% include "a.html" %}<input id="in-b">',
                                     encoding="utf-8")

        found = _control_ids(_with_includes(here / "a.html"))

    assert found == {"in-a", "in-b"}


def test_the_migration_list_has_no_entries_that_are_already_gone():
    """THE LIST MUST SHRINK AS THE WORK LANDS.

    An exemption that outlives the thing it exempts is how a debt list becomes
    a permission slip: the next person reads nine names, assumes nine problems,
    and stops looking. So a control that has left the page must leave this list
    in the same commit.
    """
    still_there = _control_ids(_with_includes(WEB_SETTINGS))
    stale = sorted(MIGRATING_TO_THE_PANEL - still_there)

    assert not stale, (
        f"{stale} are exempted here and no longer on the engine's Settings "
        "page. Delete them from MIGRATING_TO_THE_PANEL — the list is a record "
        "of what is left, not of what once was.")


def test_the_panel_can_do_everything_the_web_page_can():
    """The owner's ruling: «مينفعش يكون فى ميزة على الويب لا توجد فى extension».

    The version notice had to tell him to press "Restart engine" on the web
    Settings page, because the panel — the application — had no such button.
    An action that exists on only one of the two surfaces sends the reader
    somewhere else at the exact moment they most need to act.

    Display may live anywhere. Doing may not live only on the page."""
    page = WEB_SETTINGS.read_text(encoding="utf-8")
    panel = PANEL.read_text(encoding="utf-8")

    on_page = {i for i in RUNTIME_REPAIR_IDS if f'id="{i}"' in page}
    missing = {i for i in on_page if f'id="{i}"' not in panel}

    assert not missing, (
        f"the web page can do {sorted(missing)} and the side panel cannot. "
        "Every action on that page must have its equivalent in "
        "extension/app.html, wired to the same endpoint.")


def test_the_panel_repair_buttons_reach_the_same_endpoints():
    """Present is not the same as wired. A button that renders and does nothing
    is worse than an absent one: it looks like the feature is broken rather
    than missing."""
    script = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")

    # Quoted, so the path must END where it is supposed to. A bare substring
    # check passed happily on "/api/engine/restart_DISABLED" — it asserted a
    # prefix, not an endpoint, which is the same shape of mistake as a title
    # that recovers only the part you could already read.
    for endpoint in ('"/api/engine/restart"', '"/api/databases/upgrade"'):
        assert endpoint in script, (
            f"the panel has no call to {endpoint}, so its button cannot work")
    assert "runtime-restart" in script and "runtime-upgrade" in script, (
        "the buttons are in the markup and nothing listens to them")


def test_a_refused_restart_is_shown_and_not_covered_with_good_news():
    """The owner pressed Restart, read "The engine is back.", and nothing had
    happened. The engine had answered 500 with a precise reason — the helper
    could not open the log the live engine was holding — and the panel threw it
    away, because only 404 was treated as an answer worth reading and every
    other status fell through to the health poll. The poll of course succeeded:
    the engine had never gone anywhere.

    A thrown fetch is the success path here, since the process exits mid-answer.
    An ANSWERED fetch that is not ok is its opposite, and the two must not share
    a branch."""
    script = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    block = script.split('"/api/engine/restart"', 1)[1].split("setInterval", 1)[0]

    assert "asked.ok" in block or "!asked.ok" in block, (
        "the panel reads only the 404 and treats every other refusal as success")
    assert "detail" in block, (
        "the engine's reason is discarded, so the owner sees a generic outcome "
        "for a specific fault")


def test_every_caller_of_the_restart_endpoint_reads_the_refusal():
    """Four copies of one handler, and the bug was in all four.

    Each one asked only `status === 404` and let everything else fall through to
    a poll — a poll the refusing engine answers ITSELF, because the engine that
    refused is the one still holding the port. So a hard 500 ("could not start
    the helper ([Errno 13] Permission denied ...)") became "The engine is back."
    on one surface and was printed inside the words "restart requested" on
    another. The owner pressed the button and, correctly, said nothing happened.

    A DROPPED request is the success case here: the restart tears down the
    connection carrying its own reply. A DELIVERED non-2xx is its opposite. Any
    caller that cannot tell them apart will report the failure as progress, so
    the rule is on the class and not on the three copies I happened to fix."""
    callers = {
        "extension/app.js": (ROOT / "extension" / "app.js"),
        "settings.html": (ROOT / "scrapex" / "webui" / "templates" / "settings.html"),
        "database_unavailable.html":
            (ROOT / "scrapex" / "webui" / "templates" / "database_unavailable.html"),
    }
    for name, path in callers.items():
        text = path.read_text(encoding="utf-8")
        if "/api/engine/restart" not in text:
            continue
        for block in text.split("/api/engine/restart")[1:]:
            window = block[:1400]
            assert ".ok" in window, (
                f"{name} calls the restart endpoint and never inspects whether "
                "the answer was ok — only a 404 would be noticed, and every "
                "other refusal reads as a restart in progress")
            assert "detail" in window, (
                f"{name} discards the engine's own reason, so a specific fault "
                "reaches the owner as a generic outcome")


def test_the_panel_has_exactly_one_restart_implementation():
    """`R-80`, made mechanical for the flow that proved it.

    Two implementations of one restart lived in `extension/app.js`, and they were
    not equivalent: one had a preflight, a poll, button disabling and an error
    card, and the other announced `"restart requested"` and ended. Which one the
    owner got depended on which of two buttons he found -- both of them in
    Settings, neither on the Engine screen where the engine's own `Restart needed`
    badge is drawn. Two more callers sat on the engine's own web pages, and
    `test_every_caller_of_the_restart_endpoint_reads_the_refusal` above opens by
    naming all four.

    THE GUARD ABOVE WAS ITSELF HALF-ROTTED BY THE DUPLICATION, which is the sharpest
    argument for this one. It slices `app.js` between the FIRST occurrence of the
    endpoint and the next `setInterval`; with two implementations that window ran
    from the first function to a `setInterval` some 2,800 lines away, and `detail`
    appears roughly seventy times in between from code that has nothing to do with
    restarting. It was passing on other people's text. Deleting the duplicate closed
    the window to about twenty lines -- the survivor's own poll -- so the assertion
    now means what it says.

    Counted on the SOURCE and not in a browser, deliberately: a second copy that is
    never wired would still be a second copy to keep true, and that is what `R-80`
    forbids.
    """
    script = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    panel = PANEL.read_text(encoding="utf-8")

    assert script.count('"/api/engine/restart"') == 1, (
        "extension/app.js calls the restart endpoint more than once. One flow, one "
        "implementation -- a second copy drifts, and the two the panel used to carry "
        "reported the same failure differently")
    assert "restartEngineFromPanel" not in script, (
        "the deleted second implementation is back")
    assert panel.count('id="runtime-restart"') == 1, (
        "more than one restart button in the panel's markup")
    assert 'id="engine-restart"' not in panel, (
        "the second restart button is back in Settings")

    # AND IT IS ON THE ENGINE SCREEN, which is the half of `REQ-50` a count cannot
    # see. The button is only useful beside the badge that asks for it.
    detail = panel.split('id="view-engine-detail"', 1)
    assert len(detail) == 2, "the Engine detail view is gone"
    body = detail[1].split('id="view-console"', 1)[0]
    assert 'id="runtime-restart"' in body, (
        "the restart control is not on the Engine screen, so the `Restart needed` "
        "badge still has no remedy beside it")


# The Windows rituals. Owner ruling, 2026-08-01: «انا مستخدم على قدى غير محترف
# عاوز كل حاجة تتم اتوماتك فى الخلفية بسلاسة كالتطبيقات الاحترافية». A message
# that ends in a four-step keyboard ritual is the application handing its own job
# to a person who did not ask for it.
_RITUALS = ("shell:startup", "Win+R", "sign out and in",
            "ScrapeX Engine.vbs", "double-click")


def test_no_surface_teaches_a_windows_ritual():
    """Six of these were live: two on the settings page, two on the
    database-unavailable page, two in the panel. Each one appeared at the exact
    moment the owner was already stuck, and each one asked him to leave the
    product to repair the product.

    A sentence naming a control that exists is fine. A sentence naming a
    keyboard shortcut, a folder path or a .vbs file is not — and if no control
    exists for that state yet, the honest text says so in one line rather than
    teaching a ritual."""
    surfaces = {
        "extension/app.js": ROOT / "extension" / "app.js",
        "extension/app.html": ROOT / "extension" / "app.html",
        "settings.html": ROOT / "scrapex" / "webui" / "templates" / "settings.html",
        "database_unavailable.html":
            ROOT / "scrapex" / "webui" / "templates" / "database_unavailable.html",
    }
    offenders = []
    for name, path in surfaces.items():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            # A comment explaining WHY something happens may name the folder;
            # what may not is text the owner reads.
            if stripped.startswith("//") or stripped.startswith("#"):
                continue
            for ritual in _RITUALS:
                if ritual in line:
                    offenders.append(f"{name}:{number} — {ritual}")

    assert not offenders, (
        "these send the owner out of the product to repair the product: "
        + "; ".join(offenders))


def test_choosing_columns_is_reachable_from_the_panel():
    """Owner ruling: «مينفعش يكون فى ميزة على الويب لا توجد فى extension».

    /api/fields is the endpoint behind Choose Columns — hide a column, reorder
    them, reset the view — and until now grid.js was its only caller. So the
    control room could not do the thing the owner most often wants to do to a
    table, and the web page could.

    Present is not wired, so the endpoint is asserted too: a section that
    renders and calls nothing looks broken rather than missing."""
    panel = PANEL.read_text(encoding="utf-8")
    script = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")

    for control in ("source-columns-list", "source-columns-reset",
                    "source-columns-origin"):
        assert f'id="{control}"' in panel, f"{control} is not in the side panel"

    assert '"/api/fields/"' in script, (
        "the panel's Columns section calls nothing; the buttons render and the "
        "order never changes")
    for action in ("hidden:", "order}", "reset: true"):
        assert action in script, (
            f"the panel cannot {action.strip(':}')} — the web chooser can do all "
            "three and this one cannot")


def test_the_panel_says_whose_column_order_it_is_showing():
    """An owner who arranged his columns should never have to wonder whether an
    update replaced them, and one who has not should know the order is ours to
    improve. The engine answers it; the panel prints it."""
    script = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    engine = (ROOT / "scrapex" / "webui" / "app.py").read_text(encoding="utf-8")

    assert '"order_source"' in engine, (
        "/api/fields no longer says whose order it returned")
    assert "order_source" in script, (
        "the panel shows an order without saying whose it is")


def test_the_crawl_pace_is_reachable_from_the_panel():
    """The specific controls that were unreachable, now where they belong."""
    panel = PANEL.read_text(encoding="utf-8")

    for control in ("crawl_honour_delay", "crawl_min_interval_s",
                    "crawl_timeout_s", "crawl_user_agent"):
        assert f'id="{control}"' in panel, f"{control} is not in the side panel"


def test_google_finance_control_is_reachable_from_the_panel():
    panel = PANEL.read_text(encoding="utf-8")
    script = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")

    for control in ("google_finance_auto_refresh", "google_finance_refresh_hours",
                    "finance-save", "finance-refresh", "finance-dataset",
                    "finance-converter-currency", "finance-converter-usd"):
        assert f'id="{control}"' in panel
    assert 'id="tab-finance"' in panel
    assert 'id="view-finance"' in panel
    assert 'data-view="finance"' in panel
    assert 'role="switch"' in panel
    # THE FINANCE SWITCH SPECIFICALLY, and this is the second correction to
    # this assertion. It began as `class="finance-m3-switch-track"` matched
    # against the whole document -- and every `finance-m3-switch*` class it
    # named was DEAD MARKUP that no stylesheet ever defined, which
    # `test_ui_kit.py::test_every_class_in_markup_resolves_to_a_rule` says out
    # loud. Removing them is right; asserting on them would have pinned them
    # back.
    #
    # Replacing it with a document-wide search for `m3-switch` was no better:
    # measured, it still passed with the finance switch's own track deleted,
    # because the Engine power switch elsewhere on the page supplies the same
    # class. An assertion satisfied by a DIFFERENT control is not a test of
    # this one. So the markup is narrowed to the finance switch first.
    finance = panel[panel.index('id="google_finance_auto_refresh"'):]
    finance = finance[:finance.index("</label>")]
    for part in ("m3-switch-track", "m3-switch-handle"):
        assert any(part in attribute.split()
                   for attribute in re.findall(r'class="([^"]*)"', finance)), (
            f"the Google Finance switch is missing its `{part}` element, so the "
            "control renders as a bare checkbox rather than a switch")
    assert 'data-sect="s-finance"' not in panel
    assert 'post("/api/rates/google-finance/refresh"' in script


def test_the_web_page_still_shows_what_the_engine_holds():
    """Display-only is not the same as blank: moving the controls must not
    take the VALUES away, or the page stops being able to answer the one
    question it exists for — what is this engine actually set to?"""
    web = WEB_SETTINGS.read_text(encoding="utf-8")

    for setting in ("crawl_min_interval_s", "crawl_honour_delay",
                    "crawl_timeout_s", "crawl_user_agent"):
        assert f"settings.{setting}.value" in web, (
            f"{setting} stopped being displayed as well as editable")
