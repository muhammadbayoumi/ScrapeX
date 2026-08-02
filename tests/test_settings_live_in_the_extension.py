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
from pathlib import Path

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


def _control_ids(html: str) -> set[str]:
    return {m.group(1) for m in re.finditer(
        r'<(?:input|select|textarea)[^>]*\bid="([^"]+)"', html)}


def test_the_web_page_offers_no_setting_to_change():
    """It shows what the engine holds. It does not change it."""
    stray = _control_ids(WEB_SETTINGS.read_text(encoding="utf-8")) - RUNTIME_REPAIR_IDS

    assert not stray, (
        "the engine's web page grew a control again: "
        f"{sorted(stray)}. Settings belong in extension/app.html — a setting "
        "the owner cannot reach from the side panel is a setting he does not "
        "have.")


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
                    "finance-save", "finance-refresh", "finance-dataset"):
        assert f'id="{control}"' in panel
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
