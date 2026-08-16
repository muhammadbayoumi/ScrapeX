"""Signing out of an account the panel is not holding a token for.

WHAT WAS WRONG, both halves owner-reported and both confirmed by reading:

  1. The per-row ⋮ menu had never once offered "Sign out". `accountMenu` guards
     the item with `if (signedIn)` and `renderAccountsCard` called it with
     `{signedIn: false}` written out literally — so the branch was unreachable.
     #199 fixed the argument `accountRow` gets and left this one, which is why a
     row could offer a switch while its own menu could not offer a sign-out.

  2. "Sign out of all accounts" signed out exactly ONE. It pressed `#signout`,
     which revokes the CURRENT account's grant; every other account kept its
     standing Google grant — the very thing that makes a silent mint succeed —
     so they were still signed in, and still drawn that way.

THE LOCKOUT THIS COULD HAVE BEEN, and the reason these tests exist rather than a
node suite. The panel holds exactly ONE token and it belongs to the CURRENT
account. The obvious implementation — hand `state.token` to `revokeToken` —
would end the wrong grant: press Sign out on somebody else's row and be signed
out of your own. `test_signing_out_of_another_account_does_not_sign_out_of_this
_one` is the guard for precisely that, and nothing in the suite covered it
because no test had ever driven the per-row menu.

WHY THE HARNESS HAD TO GROW FIRST. `tools/panel_harness.py` stubbed only
`getAuthToken` and `removeCachedAuthToken`, so `identity.js:authorize()` fell
into its `getRedirectURL()` try/catch and returned state "failed" under every
panel test ever written. The entire multi-account surface was unreachable, and
silently — a test could press the button and read a plausible error. It also had
no route for Google's revoke endpoint, so every sign-out driven here took the
`local-only` path on a 404 and no test ever looked.
"""
from __future__ import annotations

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

#: The account Chrome answers `getAuthToken` for — the panel's current one.
#: `sub` is Google's stable identifier and the field the directory keys on.
OWNER = {"sub": "1", "name": "Test Owner", "email": "owner@example.com",
         "picture": ""}

#: Two more in the directory, neither of them current. `currentId` is left empty
#: deliberately: the panel fixes it from the token it actually holds.
OTHERS = {
    "accounts": [
        {"id": "2", "email": "second@example.com", "name": "Second", "picture": ""},
        {"id": "3", "email": "third@example.com", "name": "Third", "picture": ""},
    ],
    "currentId": "",
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
    """A signed-in panel with two other accounts listed, on the Profile view."""
    pages = []

    def opener(**stub_kwargs):
        page_file = harness.build_page(
            tmp_path,
            harness.stub(signed_in=OWNER, remembered_accounts=OTHERS,
                         **stub_kwargs),
            name=f"signout{len(pages)}.html")
        page = browser.new_page(viewport={"width": 400, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(page_file.as_uri())
        pages.append(page)
        page.js_errors = errors
        page.wait_for_selector("#welcome-signed-in:visible", timeout=10_000)
        page.wait_for_selector("#accounts-card .account-row", timeout=10_000)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def open_row_menu(page, email):
    """Press the ⋮ on the row for this account and return the open menu."""
    row = page.locator("#accounts-card .account-row").filter(has_text=email)
    row.locator(".account-menu-button").click()
    menu = page.locator("#accounts-card .account-menu")
    menu.wait_for()
    return menu


def revoked(page):
    return page.evaluate("window.__sx_revoked || []")


def directory(page):
    return page.evaluate(
        "async () => (await window.chrome.storage.local"
        ".get('scrapex-accounts-v1'))['scrapex-accounts-v1']")


def test_the_row_menu_offers_sign_out_at_all(panel):
    """The item `accountMenu` has always built and never drawn. It sits inside
    `if (signedIn)`, and the one call site passed a literal `false`."""
    page = panel()
    menu = open_row_menu(page, "second@example.com")

    labels = menu.locator(".account-menu-item").all_inner_texts()
    assert "Sign out" in labels, (
        f"the row menu offers {labels} — the Sign out item is still unreachable")
    assert "Remove from ScrapeX" in labels, "Remove was lost making Sign out work"


def test_signing_out_of_another_account_does_not_sign_out_of_this_one(panel):
    """THE LOCKOUT GUARD, and the reason the token is minted rather than reused.

    `state.token` belongs to the CURRENT account. Revoking it because a
    different row's menu was pressed would sign the owner out of himself, and
    the panel would look exactly as if he had asked for that."""
    page = panel()
    open_row_menu(page, "second@example.com").get_by_text("Sign out").click()
    page.wait_for_function("(window.__sx_revoked || []).length > 0", timeout=8000)

    # The redirect's fragment is URL-decoded on the way back through
    # `readRedirect`, so the token arrives spelled with the address in it.
    ended = revoked(page)
    assert ended == ["minted-for-second@example.com"], (
        f"the token revoked was {ended} — anything but a token minted for "
        "second@example.com means some other account's grant was ended")
    assert "stub-token" not in ended, (
        "the CURRENT account's token was revoked — this is the lockout: the "
        "owner pressed Sign out on somebody else's row")

    assert page.locator("#welcome-signed-in").is_visible(), (
        "the panel signed itself out while signing out of somebody else")
    assert page.text_content("#welcome-name").strip() == OWNER["name"]


def test_the_account_signed_out_of_is_drawn_signed_out(panel):
    page = panel()
    open_row_menu(page, "second@example.com").get_by_text("Sign out").click()
    page.wait_for_function("(window.__sx_revoked || []).length > 0", timeout=8000)

    gone = page.locator("#accounts-card .account-row").filter(
        has_text="second@example.com")
    gone.locator(".account-badge").wait_for(timeout=5000)
    assert gone.locator(".account-badge").count() == 1

    # The account NOT signed out of keeps its switch.
    stays = page.locator("#accounts-card .account-row").filter(
        has_text="third@example.com")
    assert stays.locator(".account-switch").count() == 1, (
        "signing out of one account marked another one signed out too")


def test_a_refused_silent_mint_is_the_answer_rather_than_an_error(panel):
    """`prompt=none` that Google will not answer means there is no live session
    for the account — which is what signed out MEANS. Nothing is revoked because
    there is nothing left to revoke, and the row still becomes the signed-out
    row."""
    page = panel(silent_for=["third@example.com"])
    open_row_menu(page, "second@example.com").get_by_text("Sign out").click()

    row = page.locator("#accounts-card .account-row").filter(
        has_text="second@example.com")
    row.locator(".account-badge").wait_for(timeout=8000)

    assert revoked(page) == [], (
        "a token was revoked for an account Google would not mint one for")

    # THE EXACT SENTENCE, because the failure this catches is not a missing
    # message but a wrong one. Let the refusal fall through to the revoke and
    # `revokeToken` is handed `undefined`: it asks Google nothing, answers
    # `revoked: false`, and the panel prints "…is signed out here. undefined
    # Google may still list…" — doubt cast on a grant that was never asked
    # about, with the word `undefined` in it.
    said = page.locator("#accounts-status").inner_text()
    assert said == "Second is signed out.", said
    assert "undefined" not in said, said
    assert "permissions" not in said, (
        f"the panel raised a doubt about a grant it never asked about: {said!r}")


def test_sign_out_of_all_accounts_signs_out_of_all_of_them(panel):
    """It pressed `#signout` and nothing else, so it ended one session and left
    every other account's Google grant standing — still switchable, still drawn
    signed in, under a button that said `all`."""
    page = panel()
    page.get_by_text("Sign out of all accounts").click()
    page.wait_for_function("(window.__sx_revoked || []).length >= 2", timeout=15000)
    page.wait_for_selector("#welcome-signed-out:visible", timeout=8000)

    ended = revoked(page)
    assert "minted-for-second@example.com" in ended, ended
    assert "minted-for-third@example.com" in ended, ended
    assert "stub-token" in ended, (
        f"the CURRENT account was left signed in by 'all accounts': {ended}")


def test_signing_out_never_erases_a_row(panel):
    """Ending a session is not removing an account — the row is the way back in
    without typing the address again. Remove is a different button, and it asks
    first."""
    page = panel()
    page.get_by_text("Sign out of all accounts").click()
    page.wait_for_function("(window.__sx_revoked || []).length >= 2", timeout=15000)

    # The owner's own row is in there too — signing in put it there — so this
    # asserts that NOTHING was taken away rather than pinning the whole list.
    held = directory(page)
    kept = {account["id"] for account in held["accounts"]}
    assert {"2", "3"} <= kept, (
        f"sign out erased rows from the directory: {held}")
    assert held["currentId"] == "", (
        "the panel is still acting as an account it has signed out of")


def test_a_revoke_google_refuses_is_reported_rather_than_swallowed(panel):
    """`revoked`, not `state`: revokeToken answers `{state: "ok", revoked:
    false}` when it was handed nothing at all, so the state alone cannot tell
    "the grant is gone" from "Google was never asked". Here the browser has
    forgotten the account and Google has not, and the owner can finish it."""
    page = panel(revoke_status=500)
    open_row_menu(page, "second@example.com").get_by_text("Sign out").click()
    page.wait_for_function("(window.__sx_revoked || []).length > 0", timeout=8000)

    said = page.locator("#accounts-status").inner_text()
    assert "500" in said, f"the refusal was swallowed: {said!r}"
    assert "permissions" in said.lower(), (
        f"nothing tells the owner the grant is still listed at Google: {said!r}")


def test_the_silent_mint_names_the_account_it_is_for(panel):
    """`login_hint` is the whole reason this can speak for an account that is
    not the Chrome profile's primary one. Without it Google answers for whoever
    it considers default — which is the current account, again."""
    page = panel()
    open_row_menu(page, "third@example.com").get_by_text("Sign out").click()
    page.wait_for_function("(window.__sx_revoked || []).length > 0", timeout=8000)

    flows = page.evaluate("window.__sx_auth_flows || []")
    assert flows, "no auth flow was opened at all"
    assert flows[-1]["hint"] == "third@example.com", flows
    assert flows[-1]["prompt"] == "none", (
        f"the mint was not silent: {flows[-1]}")
    assert flows[-1]["interactive"] is False
