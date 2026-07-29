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
# Named here so the exemption is a decision on the record, not a loophole.
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


def test_the_crawl_pace_is_reachable_from_the_panel():
    """The specific controls that were unreachable, now where they belong."""
    panel = PANEL.read_text(encoding="utf-8")

    for control in ("crawl_honour_delay", "crawl_min_interval_s",
                    "crawl_timeout_s", "crawl_user_agent"):
        assert f'id="{control}"' in panel, f"{control} is not in the side panel"


def test_the_web_page_still_shows_what_the_engine_holds():
    """Display-only is not the same as blank: moving the controls must not
    take the VALUES away, or the page stops being able to answer the one
    question it exists for — what is this engine actually set to?"""
    web = WEB_SETTINGS.read_text(encoding="utf-8")

    for setting in ("crawl_min_interval_s", "crawl_honour_delay",
                    "crawl_timeout_s", "crawl_user_agent"):
        assert f"settings.{setting}.value" in web, (
            f"{setting} stopped being displayed as well as editable")
