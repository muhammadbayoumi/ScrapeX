"""Every Drive and Sheets call asks Chrome for a token at the moment it is made (#2028).

WHAT HE SAW, 2026-11-28, on his new PC, signed in as himself: Manage account's
Drive card read "Could not read your Drive — Google refused the token. Sign in
again from the Profile page.", and the backup he made on his old PC could not be
brought over.

THE CAUSE. `state.token` is the token the panel was handed when it opened, and
every Drive and Sheets operation read it. An access token lives about an hour; a
side panel lives as long as its window. Chrome's cache renews a token by itself
-- but only for a caller that asks again, and the panel never did. Nor did a
401 drop the token from Chrome's cache, so a token Google refuses stayed the one
Chrome hands back.

WHY THE HARNESS HAD TO GROW FIRST. `tools/panel_harness.py` answered every Google
request whatever bearer it carried, so a panel reading Drive with a dead token
passed every test there was. `chrome_mints` models Chrome's cache and a Google
that refuses a dead token; its docstring says what each door stands for.

THE THREE STATES, one test each on the screen he was on:
  * an hour passed: Chrome renews by itself, so asking again is the whole fix;
  * the grant ended elsewhere and was granted again: Chrome still hands back the
    refused token, so it has to be dropped from the cache and asked for again;
  * the grant ended and nothing silent can renew it: only then is he told to
    sign in again, and given the control to do it.
Then every other door into Drive and Sheets, after an hour; and an account added
through the switcher, whose token is renewed through its own sign-in and never
through Chrome's, which speaks only for the Chrome profile's primary account.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# Guards the extension: this file reads extension/ sources, so a change there
# must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright", reason="needs the browser extra")

from playwright.sync_api import sync_playwright  # noqa: E402

import panel_harness as harness  # noqa: E402

#: The Chrome profile's own account, the one `getAuthToken` speaks for.
OWNER = {"sub": "1", "name": "Test Owner", "email": "owner@example.com",
         "picture": ""}

#: A second account in the directory, reachable only through the switcher.
SECOND = {"id": "2", "email": "second@example.com", "name": "Second", "picture": ""}

#: What `latest.json` says: one archive, whole, in a format this panel reads.
POINTER = {
    "file_id": "zip-1",
    "name": "scrapex-bundle-20261120-090000.zip",
    "bytes": 8192,
    "sha256": "a" * 64,
    "created_at": "2026-11-20T09:00:00Z",
    "engine_version": "0.4.88",
    "bundle_format": 1,
    "panel_pack": None,
    "light": None,
}

#: His backup folder as Drive lists it: the archive and the pointer naming it.
DRIVE = {
    "folder": "folder-1",
    "files": [
        {"id": "zip-1", "name": POINTER["name"], "size": "8192",
         "createdTime": "2026-11-20T09:00:00Z"},
        {"id": "pointer-1", "name": "latest.json", "size": "300",
         "createdTime": "2026-11-20T09:00:05Z"},
    ],
    "pointer": POINTER,
}

#: A build reply small enough to upload in one chunk (test_panel_dom's shape).
BUNDLE = {
    "name": "scrapex-bundle-20261128-100000.zip",
    "bytes": 8192,
    "sha256": "b" * 64,
    "created_at": "2026-11-28T10:00:00Z",
    "engine_version": "0.4.91",
    "bundle_format": 1,
    "panel_pack": {"bytes": 256},
}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def panel(browser, tmp_path):
    """A panel signed in as OWNER, with Google's tokens modelled."""
    pages = []

    def opener(*, signed_in=True, **stub_kwargs):
        stub_kwargs.setdefault("chrome_mints", ["token-at-open", "token-an-hour-on"])
        page_file = harness.build_page(
            tmp_path, harness.stub(signed_in=OWNER, **stub_kwargs),
            name=f"fresh{len(pages)}.html")
        page = browser.new_page(viewport={"width": 400, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        pages.append(page)
        page.js_errors = errors
        if signed_in:
            page.wait_for_selector("#welcome-signed-in:visible", timeout=10_000)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def an_hour_passes(page) -> None:
    page.evaluate("() => window.__sx_an_hour_passes()")


def drive_bearers(page) -> list[str]:
    """The token on every Drive request, in the order they were sent."""
    return [sent["token"] for sent in page.evaluate("() => window.__sx_bearers")
            if "/drive/v3/" in sent["url"]]


def sheets_bearers(page) -> list[str]:
    return [sent["token"] for sent in page.evaluate("() => window.__sx_bearers")
            if "sheets.googleapis.com" in sent["url"]]


def removed(page) -> list[str]:
    return page.evaluate("() => window.__sx_removed_tokens || []")


def drive_card_verdict(page) -> str:
    """Open Manage account and return what its Drive card settles on."""
    page.click("#manage-account")
    page.wait_for_selector("#view-manage-account:visible")
    page.wait_for_function(
        "() => /Latest backup|Could not read|No backups/.test("
        "document.querySelector('#drive-backups').innerText)", timeout=15_000)
    return page.inner_text("#drive-backups")


def open_drive_settings(page) -> None:
    page.click('[data-view="settings"]')
    page.wait_for_selector("#view-settings:visible")
    page.click('[data-sect="s-output"]')
    page.wait_for_selector("#drive-fetch:visible")


def settled(page, region: str) -> str:
    """The verdict a Google button left in its status line: `out()` wraps it in
    `span.ok` or `span.err`, and the working sentence before it in neither.
    ATTACHED, not visible: the export's line is on the Data page, which is not
    the one on screen when the export is started from here."""
    page.wait_for_selector(f"#{region} span.ok, #{region} span.err",
                           state="attached", timeout=15_000)
    return page.text_content(f"#{region}").strip()


def switch_to_second(page) -> None:
    page.click(f'#accounts-card button.account-switch[aria-label="Use {SECOND["name"]}"]')
    page.wait_for_function(
        "(name) => document.querySelector('#welcome-name').textContent.trim() === name",
        arg=SECOND["name"], timeout=10_000)


# ---- the screen he was on ---------------------------------------------------


def test_manage_account_reads_drive_with_a_token_asked_for_now(panel):
    """AN HOUR PASSED, which is his case: the token the panel opened with is dead,
    and Chrome would hand over a new one to anybody who asked. The card used the
    old one and blamed Google."""
    page = panel(drive=DRIVE)
    an_hour_passes(page)

    said = drive_card_verdict(page)

    assert "Latest backup" in said, (
        f"the card read Drive with the token from when the panel opened: {said!r}")
    assert drive_bearers(page), "the card never asked Drive anything"
    assert set(drive_bearers(page)) == {"token-an-hour-on"}, (
        f"a Drive request went out with a token Google no longer takes: "
        f"{drive_bearers(page)}")


def test_a_refused_token_is_dropped_from_chrome_and_asked_for_once_more(panel):
    """THE GRANT ENDED ELSEWHERE AND WAS GRANTED AGAIN. Chrome does not hear of it
    and goes on handing back the refused token, so asking again alone returns the
    same dead one. Dropping it from Chrome's cache is what makes the next ask a
    new token -- and the request that was refused is sent once more, once."""
    page = panel(drive=DRIVE, chrome_mints=["token-at-open", "token-granted-again"])
    page.evaluate("() => window.__sx_grant_ends_elsewhere({regranted: true})")

    said = drive_card_verdict(page)

    assert "Latest backup" in said, f"a refused token was the end of it: {said!r}"
    assert "token-at-open" in removed(page), (
        "the refused token was left in Chrome's cache, so every later ask hands it "
        f"back: removed {removed(page)}")
    sent = drive_bearers(page)
    assert sent[0] == "token-at-open" and sent.count("token-at-open") == 1, (
        f"the refused request is retried once with a new token, never twice: {sent}")
    assert set(sent[1:]) == {"token-granted-again"}, sent


def test_when_nothing_silent_can_renew_it_the_card_offers_the_sign_in(panel):
    """THE GRANT ENDED, FULL STOP: dropped from the cache, Chrome cannot mint a
    new token without him. Only now is he told to sign in again -- and given the
    control, not a sentence about a page somewhere else. Pressing it asks Google
    with him present, and the card reads Drive."""
    page = panel(drive=DRIVE, chrome_mints=["token-at-open"])
    page.evaluate("() => window.__sx_grant_ends_elsewhere()")

    said = drive_card_verdict(page)
    assert "Latest backup" not in said
    assert "token-at-open" in removed(page), (
        "the dead token stayed in Chrome's cache, so pressing Sign in would hand "
        f"it straight back: removed {removed(page)}")

    sign_in = page.locator("#drive-backups").get_by_role(
        "button", name=re.compile(r"sign in", re.I))
    assert sign_in.count() == 1, (
        f"the card says what to do and offers no control to do it: {said!r}")

    sign_in.click()
    page.wait_for_function(
        "() => /Latest backup/.test(document.querySelector('#drive-backups').innerText)",
        timeout=15_000)
    asks = page.evaluate("() => window.__sx_token_asks")
    assert any(ask["interactive"] for ask in asks), (
        f"the press never asked Google with him present: {asks}")
    assert drive_bearers(page)[-1] == "consented-1", drive_bearers(page)


# ---- every other door into Drive, after the hour ------------------------------


def test_check_the_latest_backup_asks_for_a_fresh_token(panel):
    page = panel(drive=DRIVE)
    an_hour_passes(page)
    open_drive_settings(page)

    page.click("#drive-restore")
    said = settled(page, "drive-msg")

    assert said.startswith("Drive is holding"), said
    assert set(drive_bearers(page)) == {"token-an-hour-on"}, drive_bearers(page)


def test_fetch_the_latest_backup_asks_for_a_fresh_token(panel):
    """THE BUTTON HE NEEDS: it brings his old PC's backup onto this one. The
    engine answers that the archive is already here, which ends the transfer
    after the one question -- the ranged read is drive.js's own suite's."""
    landed = {"received": 8192, "total": 8192, "complete": True,
              "name": "from-drive-aaaaaaaaaaaaaaaa.zip", "already_here": True}
    page = panel(drive=DRIVE, received_bundle=landed)
    an_hour_passes(page)
    open_drive_settings(page)

    page.click("#drive-fetch")
    said = settled(page, "drive-msg")

    assert "already on this computer as from-drive-aaaaaaaaaaaaaaaa.zip" in said, said
    assert set(drive_bearers(page)) == {"token-an-hour-on"}, drive_bearers(page)


def test_back_up_now_asks_for_a_fresh_token(panel):
    page = panel(drive={"folder": "folder-1", "files": [], "pointer": None},
                 bundle=BUNDLE)
    an_hour_passes(page)
    page.click("#manage-account")
    page.wait_for_selector("#view-manage-account:visible")

    page.click("#manage-backup")
    said = settled(page, "manage-backup-msg")

    assert said.startswith("Backed up"), said
    assert set(drive_bearers(page)) == {"token-an-hour-on"}, drive_bearers(page)


def test_the_data_page_read_from_drive_asks_for_a_fresh_token(panel):
    """No engine, so the Data page offers his Drive backup instead. This backup
    carries no panel pack, so the answer is that sentence -- reachable only after
    Drive has been read, which is the whole question here."""
    page = panel(drive=DRIVE, engine_up=False)
    an_hour_passes(page)
    page.click('[data-view="data"]')
    page.wait_for_selector("#browse-offline:visible", timeout=10_000)

    page.click("#browse-offline")
    # Both answers are refusals -- the token's today, the missing pack's once the
    # token is fresh -- and `out()` wraps a refusal in `span.err`.
    page.wait_for_selector("#offline-msg span.err", timeout=15_000)
    said = page.inner_text("#offline-msg").strip()

    assert "refused the token" not in said, said
    assert "made before ScrapeX could show data without the engine" in said, said
    assert set(drive_bearers(page)) == {"token-an-hour-on"}, drive_bearers(page)


def test_a_source_exported_to_a_sheet_is_written_with_a_fresh_token(panel):
    page = panel(export_table={"header": ["sku", "price"], "rows": [["A1", "10"]],
                               "truncated": False, "limit": 40000},
                 sheets={"tabs": []})
    page.evaluate("""() => chrome.storage.local.set({scrapexTargetSheet: {
        id: 'sheet-1', name: 'His sheet',
        url: 'https://docs.google.com/spreadsheets/d/sheet-1'}})""")
    an_hour_passes(page)

    page.evaluate("() => exportSourceToSheet('stub_source')")
    said = settled(page, "datasets-msg")

    assert "rows written to" in said, said
    assert sheets_bearers(page), "nothing was written to the spreadsheet"
    assert set(sheets_bearers(page)) == {"token-an-hour-on"}, sheets_bearers(page)


# ---- an account the switcher added ----------------------------------------------


def test_a_switched_account_is_renewed_through_its_own_sign_in(panel):
    """`getAuthToken` speaks only for the Chrome profile's primary account. Renewing
    a switched account through it would read and write the OWNER's Drive under
    Second's name -- so Chrome is given a token to hand out here, and none of it
    may reach Drive."""
    page = panel(drive=DRIVE, remembered_accounts={"accounts": [SECOND], "currentId": ""},
                 chrome_mints=["token-at-open", "owner-an-hour-on"])
    switch_to_second(page)
    an_hour_passes(page)
    flows_before = len(page.evaluate("() => window.__sx_auth_flows || []"))

    said = drive_card_verdict(page)

    assert "Latest backup" in said, said
    assert set(drive_bearers(page)) == {"minted-for-second@example.com-1"}, (
        f"Second's Drive was read with someone else's token: {drive_bearers(page)}")
    flows = page.evaluate("() => window.__sx_auth_flows")[flows_before:]
    assert flows and all(flow["hint"] == SECOND["email"] and flow["prompt"] == "none"
                         and not flow["interactive"] for flow in flows), flows


def test_choosing_a_spreadsheet_hands_over_the_token_of_the_account_on_screen(panel):
    """The Picker asked afresh already, through `getAuthToken` -- so for a switched
    account it handed the chooser the OWNER's token, and put it in `state.token`
    under Second's name."""
    page = panel(drive=DRIVE, remembered_accounts={"accounts": [SECOND], "currentId": ""},
                 chrome_mints=["token-at-open", "owner-an-hour-on"])
    switch_to_second(page)
    an_hour_passes(page)
    open_drive_settings(page)

    page.click("#sheet-choose")
    page.wait_for_function(
        "async () => Boolean((await chrome.storage.session.get("
        "'scrapexPickerHandoff')).scrapexPickerHandoff)", timeout=10_000)
    handed = page.evaluate(
        "async () => (await chrome.storage.session.get('scrapexPickerHandoff'))"
        ".scrapexPickerHandoff.token")

    assert handed == "minted-for-second@example.com-1", (
        f"the chooser was handed a token for another account: {handed!r}")
