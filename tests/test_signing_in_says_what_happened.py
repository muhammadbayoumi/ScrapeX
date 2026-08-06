"""Sign-in, and the four different things "it didn't work" can mean.

M1c. The extension owns the token and lends it to the engine — the owner's
ruling of 2026-08-05 — so Chrome holds it, refreshes it, and scopes it to this
extension's own OAuth client. Nothing is written to disk here.

WHY EVERY REFUSAL GETS ITS OWN SENTENCE. chrome.identity reports failure the
same way every time: no token, and a message in runtime.lastError. A caller
that checked only the token would turn "the owner closed the consent window"
into "signed in as undefined"; a caller that printed one "sign-in failed" for
all of them teaches the owner to press the button again and learn nothing —
which is right for a closed window and useless for a mismatched OAuth client,
the one failure pressing again can never fix.

THE SILENT CHECK ON OPEN is what stops a returning owner ever seeing the button
again, and it is deliberately non-interactive: a panel that opened a consent
window every time it was opened is indistinguishable from a broken extension.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright  # noqa: E402

import panel_harness as harness  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def open_panel(browser, tmp_path):
    pages = []

    def opener(**stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"signin{len(pages)}.html")
        page = browser.new_page(viewport={"width": 400, "height": 900})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()

ACCOUNT = {"name": "Muhammad Bayoumi", "email": "madastore1899@gmail.com",
           "picture": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
                      "FcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="}


def test_a_machine_nobody_has_signed_in_on_shows_the_button_and_no_error(open_panel):
    """The ordinary first state, and the one a too-eager error message ruins.

    The panel asks Chrome on open and Chrome says no. That is not a failure to
    report — it is the state every machine is in before anyone signs in.
    """
    page = open_panel()

    assert page.is_visible("#welcome-signed-out")
    assert not page.is_visible("#welcome-signed-in")
    assert page.text_content("#signin-problem").strip() == "", (
        "the silent check reported its own ordinary result as a problem")


def test_a_returning_owner_is_already_signed_in_and_never_sees_the_button(open_panel):
    """Chrome still holds a token, so the panel opens signed in without ever
    opening a consent window."""
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#welcome-signed-in:visible")

    assert not page.is_visible("#welcome-signed-out")
    assert page.text_content("#welcome-name").strip() == ACCOUNT["name"]
    assert page.text_content("#welcome-email").strip() == ACCOUNT["email"]


def test_the_account_photo_reaches_the_rail_button(open_panel):
    """The owner asked for this directly: «وعندما يتم تسجيل الحساب عمل لوج ان
    بجوجل تتحول الى صورة اكونت جوجل».

    setProfileAvatar was built and tested in advance precisely so that M1 would
    add a CALLER and not a feature. This is that caller, asserted end to end.
    """
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#profile-avatar:visible")

    assert not page.is_visible("#profile-avatar-fallback"), (
        "the generic account mark is still drawn over the owner's own photo")
    assert page.get_attribute("#profile-avatar", "src") == ACCOUNT["picture"]


def test_closing_the_consent_window_changes_nothing_and_says_so(open_panel):
    """The commonest refusal by far, and the one that must not look like a
    fault. Pressing again is exactly the right remedy, so the sentence says
    nothing changed rather than naming a problem to go and fix."""
    page = open_panel()
    page.click("#signin")
    page.wait_for_function(
        "() => document.getElementById('signin-problem').textContent !== ''",
        timeout=8000)

    assert "closed before it finished" in page.text_content("#signin-problem")
    assert "Nothing changed" in page.text_content("#signin-problem")
    assert page.is_visible("#welcome-signed-out")


def test_a_mismatched_oauth_client_is_not_reported_as_a_closed_window(open_panel):
    """THE ONE FAILURE PRESSING AGAIN CAN NEVER FIX.

    Chrome refuses when the extension's ID does not match the OAuth client's —
    which is exactly what happens if the manifest's pinned `key` is changed, or
    the client was created against a different Item ID. Telling the owner to
    try again there is telling him to repeat something that cannot work.
    """
    page = open_panel(signin_error="Invalid client id or unknown Chrome app.")
    page.click("#signin")
    page.wait_for_function(
        "() => document.getElementById('signin-problem').textContent !== ''",
        timeout=8000)

    problem = page.text_content("#signin-problem")
    assert "do not match" in problem
    assert "closed" not in problem


def test_signing_out_puts_the_machine_back_where_it_started(open_panel):
    """Chrome's cached token is dropped, the account mark comes back, and the
    button returns. A sign-out that left the photo on the rail would be a lie
    on the one control that says who you are."""
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#welcome-signed-in:visible")

    page.click("#signout")
    page.wait_for_selector("#welcome-signed-out:visible")

    assert not page.is_visible("#welcome-signed-in")
    assert page.is_visible("#profile-avatar-fallback")
    assert not page.is_visible("#profile-avatar")


def test_the_scopes_asked_for_are_the_scopes_agreed(open_panel):
    """Decision 20's promise in the panel's own words: "Only the files it
    creates. It never asks for the rest of your Drive."

    A scope added quietly is a promise broken quietly — `drive` instead of
    `drive.file` would be the whole of someone's Drive, and nothing else in the
    repository would notice.
    """
    import json
    import pathlib

    manifest = json.loads(
        (pathlib.Path(__file__).resolve().parents[1] / "extension" /
         "manifest.json").read_text(encoding="utf-8"))
    scopes = set(manifest["oauth2"]["scopes"])

    assert scopes == {
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/spreadsheets",
    }, f"the scopes changed: {sorted(scopes)}"
    assert "https://www.googleapis.com/auth/drive" not in scopes, (
        "full Drive access — the panel promises only the files ScrapeX creates")


def test_the_client_is_named_and_the_id_it_is_bound_to_is_pinned():
    """A Chrome Extension OAuth client has no secret, and Chrome will only mint
    a token for the extension whose ID matches the client. That makes the
    client id safe to ship — and makes the manifest's `key` load-bearing: drop
    it and the ID changes, and every sign-in fails with the one error pressing
    again cannot fix."""
    import json
    import pathlib

    manifest = json.loads(
        (pathlib.Path(__file__).resolve().parents[1] / "extension" /
         "manifest.json").read_text(encoding="utf-8"))

    assert manifest["oauth2"]["client_id"].endswith(".apps.googleusercontent.com")
    assert "client_secret" not in json.dumps(manifest), (
        "a secret in a shipped manifest is a published secret")
    assert manifest.get("key"), (
        "the extension's ID is no longer pinned, so it changes between machines "
        "and the OAuth client stops matching it")
    assert "identity" in manifest["permissions"]


def test_the_mark_actually_renders(open_panel):
    """READ THE PAGE, NOT THE MARKUP.

    Every other assertion about this button reads app.html and the asset on
    disk, and all of them passed while the panel drew a BROKEN IMAGE — the
    harness builds its page in a temporary directory with no icons/ beside it,
    so the src resolved to nothing. It was found by looking at a screenshot,
    which is twice in this session that a picture caught what the suite could
    not.

    naturalWidth is zero for an image that failed to load and non-zero for one
    that did. It is the only assertion here that can tell them apart.
    """
    page = open_panel()

    box = page.evaluate("""() => {
        const img = document.querySelector('#signin .google-signin-mark');
        if (!img) return null;
        const r = img.getBoundingClientRect();
        return {w: img.naturalWidth, h: img.naturalHeight,
                drawn: r.width, drawnH: r.height};
    }""")

    assert box, "the sign-in button has no mark"
    assert box["w"] > 0 and box["h"] > 0, (
        "the Google mark did not load — the button is drawn with a hole in it")
    # NOT SQUARE, and finding that out is why this test exists. The published
    # asset is 200x204, and the button drew it in a 20x20 box — a 2% stretch of
    # a logo the guidelines say must never be stretched. Every markup-reading
    # assertion passed through that.
    ratio = box["w"] / box["h"]
    drawn_ratio = box["drawn"] / box["drawnH"]
    assert abs(drawn_ratio - ratio) < 0.01, (
        f"the mark is drawn at {drawn_ratio:.3f} against an intrinsic {ratio:.3f}"
        " — it is stretched")
    assert 19 <= box["drawnH"] <= 21, (
        f"the mark is {box['drawnH']}px tall, not the 20 the button specifies")
