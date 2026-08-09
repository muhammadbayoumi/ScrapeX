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


def _visible_img_selector(page):
    """Return the currently visible Google button asset image."""
    return page.locator(".profile-signin-img:not(.hidden)").first


def test_the_initial_state_is_checking_then_resolves_to_signed_out(open_panel):
    """Before Chrome answers, the page waits. Once Chrome says no, the button
    appears and the checking state is gone."""
    page = open_panel()

    assert page.is_visible("#welcome-signed-out")
    assert not page.is_visible("#welcome-signed-in")
    assert not page.is_visible("#welcome-checking")
    assert page.text_content("#signin-problem").strip() == "", (
        "the silent check reported its own ordinary result as a problem")


def test_a_returning_owner_is_already_signed_in_and_never_sees_the_button(open_panel):
    """Chrome still holds a token, so the panel opens signed in without ever
    opening a consent window."""
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#welcome-signed-in:visible")

    assert not page.is_visible("#welcome-checking")
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


def test_silent_startup_does_not_move_focus(open_panel):
    """A panel that steals focus on open feels broken; the owner did not ask
    for anything yet."""
    page = open_panel()
    active = page.evaluate("() => document.activeElement.id || document.activeElement.tagName")

    assert active not in ("signin", "welcome-summary"), (
        f"focus moved to {active} during the silent startup check")


def test_user_sign_in_focuses_the_signed_in_summary(open_panel):
    """The primary success announcement is moving focus to the new state."""
    page = open_panel()
    page.evaluate(f"""(account) => {{
      chrome.identity.getAuthToken = (opts, cb) => cb("stub-token");
      const original = window.fetch;
      window.fetch = async (url, options) => {{
        if (String(url).includes('oauth2/v3/userinfo')) {{
          return {{ ok: true, status: 200, json: async () => account }};
        }}
        return original(url, options);
      }};
    }}""", ACCOUNT)
    page.click("#signin")
    page.wait_for_selector("#welcome-signed-in:visible")

    active = page.evaluate("() => document.activeElement.id")
    assert active == "welcome-summary", (
        f"sign-in left focus on {active} instead of the signed-in summary")


def test_user_sign_out_focuses_the_google_button(open_panel):
    """The primary sign-out announcement is moving focus back to the control
    that can restore the signed-in state."""
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#welcome-signed-in:visible")

    page.click("#signout")
    page.wait_for_selector("#welcome-signed-out:visible")

    active = page.evaluate("() => document.activeElement.id")
    assert active == "signin", (
        f"sign-out left focus on {active} instead of the Google button")


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


def test_oauth2_not_granted_uses_neutral_authorization_required_copy(open_panel):
    """Chrome's own message says "revoked", but the panel must not claim to
    know that. The only truth is that access is not currently granted."""
    page = open_panel(signin_error="OAuth2 not granted or revoked.")
    page.click("#signin")
    page.wait_for_function(
        "() => document.getElementById('signin-problem').textContent !== ''",
        timeout=8000)

    problem = page.text_content("#signin-problem")
    assert "isn’t currently granted" in problem
    assert "revoked" not in problem.lower()


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
        const img = document.querySelector('#signin .profile-signin-img:not(.hidden)');
        if (!img) return null;
        const r = img.getBoundingClientRect();
        return {w: img.naturalWidth, h: img.naturalHeight,
                drawn: r.width, drawnH: r.height};
    }""")

    assert box, "the sign-in button has no visible mark"
    assert box["w"] > 0 and box["h"] > 0, (
        "the Google mark did not load — the button is drawn with a hole in it")
    ratio = box["w"] / box["h"]
    drawn_ratio = box["drawn"] / box["drawnH"]
    assert abs(drawn_ratio - ratio) < 0.01, (
        f"the mark is drawn at {drawn_ratio:.3f} against an intrinsic {ratio:.3f}"
        " — it is stretched")
    assert 39 <= box["drawnH"] <= 41, (
        f"the mark is {box['drawnH']}px tall, not the official 40px")


def test_the_google_button_has_a_48px_click_target(open_panel):
    """The visual asset is 40px tall; the native wrapper must make the whole
    target at least 48px."""
    page = open_panel()
    box = page.evaluate("""() => {
        const btn = document.getElementById('signin');
        const r = btn.getBoundingClientRect();
        return {w: r.width, h: r.height};
    }""")

    assert box["h"] >= 48, f"click target height is {box['h']}px, not 48px"
    assert box["w"] >= 180, f"click target width is {box['w']}px"


def test_the_google_button_is_busy_while_signing_in(open_panel):
    """While the consent flow is in progress the button is disabled, busy, and
    a status appears outside the Google image."""
    page = open_panel()
    page.evaluate(f"""(account) => {{
      chrome.identity.getAuthToken = (opts, cb) => {{
        setTimeout(() => cb("stub-token"), 300);
      }};
      const original = window.fetch;
      window.fetch = async (url, options) => {{
        if (String(url).includes('oauth2/v3/userinfo')) {{
          return {{ ok: true, status: 200, json: async () => account }};
        }}
        return original(url, options);
      }};
    }}""", ACCOUNT)
    page.click("#signin")
    page.wait_for_function(
        """() => {
          const btn = document.getElementById('signin');
          return btn.disabled && btn.getAttribute('aria-busy') === 'true';
        }""",
        timeout=2000)

    assert "Signing in" in page.text_content("#signin-status")

    page.wait_for_function(
        "() => document.getElementById('signin').disabled === false",
        timeout=10000)
    assert page.get_attribute("#signin", "aria-busy") == "false"
    assert page.is_visible("#welcome-signed-in")


def test_the_google_button_switches_light_and_dark_assets(open_panel):
    """The official light and dark assets are both shipped; the visible one
    follows the effective colour scheme."""
    page = open_panel()
    page.evaluate("""() => {
      window.ScrapeXAppearance.set({mode: 'manual', scheme: 'dark'});
    }""")

    assert page.is_visible('.profile-signin-img[data-scheme="dark"]:not(.hidden)')
    assert not page.is_visible('.profile-signin-img[data-scheme="light"]:not(.hidden)')

    page.evaluate("""() => {
      window.ScrapeXAppearance.set({mode: 'manual', scheme: 'light'});
    }""")

    assert page.is_visible('.profile-signin-img[data-scheme="light"]:not(.hidden)')
    assert not page.is_visible('.profile-signin-img[data-scheme="dark"]:not(.hidden)')


def test_the_welcome_mark_is_visible_in_dark_scheme(open_panel):
    """The black raster mark was replaced with a theme-aware CSS mask so it
    remains visible on dark surfaces."""
    page = open_panel()
    page.evaluate("""() => {
      window.ScrapeXAppearance.set({mode: 'manual', scheme: 'dark'});
    }""")

    mark = page.locator("#welcome-signed-out .welcome-mark")
    assert mark.is_visible()
    box = mark.evaluate("""el => {
      const s = getComputedStyle(el);
      return {
        maskImage: s.maskImage || s.webkitMaskImage,
        background: s.backgroundColor,
      };
    }""")
    assert "data:" in (box["maskImage"] or ""), "the mark has no mask image"
    assert "0, 0, 0" not in box["background"], "the mark is still drawn black"


def test_a_missing_email_hides_the_email_paragraph(open_panel):
    """Google may return an account without an email. The signed-in state must
    not show an empty labelled paragraph."""
    account = {**ACCOUNT, "email": ""}
    page = open_panel(signed_in=account)
    page.wait_for_selector("#welcome-signed-in:visible")

    assert page.is_visible("#welcome-name")
    assert not page.is_visible("#welcome-email")


def test_the_rail_label_reflects_sign_in_state(open_panel):
    """The rail button is icons-only, so its accessible name must say signed
    in / signed out without leaking the account name or email."""
    page = open_panel()
    page.wait_for_selector("#welcome-signed-out:visible")
    assert page.get_attribute("#tab-profile", "aria-label") == "Profile, signed out"

    page2 = open_panel(signed_in=ACCOUNT)
    page2.wait_for_selector("#welcome-signed-in:visible")
    assert page2.get_attribute("#tab-profile", "aria-label") == "Profile, signed in"


def test_a_401_account_lookup_clears_the_cached_token(open_panel):
    """A 401 means the token Chrome was holding is no longer valid. The panel
    must drop it and return to signed-out, not retry silently or auto-open a
    consent window."""
    page = open_panel()
    page.evaluate("""() => {
      chrome.identity.getAuthToken = (opts, cb) => cb("stub-token");
      const original = window.fetch;
      window.fetch = async (url, options) => {
        if (String(url).includes('oauth2/v3/userinfo')) {
          return { ok: false, status: 401, json: async () => ({}) };
        }
        return original(url, options);
      };
    }""")
    page.click("#signin")
    page.wait_for_selector("#welcome-signed-out:visible")

    problem = page.text_content("#signin-problem")
    assert "isn’t currently granted" in problem
    assert page.get_attribute("#signin", "aria-label") == "Sign in with Google"


def test_retryable_account_failures_show_a_retry_button(open_panel):
    """Timeout, network, 429, and 5xx keep the signed-in state and offer a
    retry that re-fetches account details only."""
    page = open_panel()
    page.evaluate(f"""(account) => {{
      chrome.identity.getAuthToken = (opts, cb) => cb("stub-token");
      const original = window.fetch;
      window.fetch = async (url, options) => {{
        if (String(url).includes('oauth2/v3/userinfo')) {{
          window.__userinfoCalls = (window.__userinfoCalls || 0) + 1;
          if (window.__userinfoCalls === 1) {{
            return {{ ok: false, status: 429, json: async () => {{}} }};
          }}
          return {{ ok: true, status: 200, json: async () => account }};
        }}
        return original(url, options);
      }};
    }}""", ACCOUNT)
    page.click("#signin")
    page.wait_for_selector("#retry-account:visible")

    status = page.text_content("#account-detail-status")
    assert "rate-limiting" in status or "Try again" in status

    page.click("#retry-account")
    page.wait_for_function(
        "() => document.getElementById('welcome-email').textContent !== ''",
        timeout=5000)

    assert page.text_content("#welcome-email") == ACCOUNT["email"]
    assert page.evaluate("() => window.__userinfoCalls || 0") >= 2


def test_non_retryable_account_failures_do_not_show_retry(open_panel):
    """A 403 is not a transient error; retrying would not help."""
    page = open_panel()
    page.evaluate("""() => {
      chrome.identity.getAuthToken = (opts, cb) => cb("stub-token");
      const original = window.fetch;
      window.fetch = async (url, options) => {
        if (String(url).includes('oauth2/v3/userinfo')) {
          return { ok: false, status: 403, json: async () => ({}) };
        }
        return original(url, options);
      };
    }""")
    page.click("#signin")
    page.wait_for_selector("#welcome-signed-in:visible")

    status = page.text_content("#account-detail-status")
    assert "refused" in status or "403" in status
    assert not page.is_visible("#retry-account")


def test_network_error_on_account_lookup_is_retryable(open_panel):
    """A thrown fetch is a network problem, not a revoked token."""
    page = open_panel()
    page.evaluate(f"""(account) => {{
      chrome.identity.getAuthToken = (opts, cb) => cb("stub-token");
      const original = window.fetch;
      window.fetch = async (url, options) => {{
        if (String(url).includes('oauth2/v3/userinfo')) {{
          window.__userinfoCalls = (window.__userinfoCalls || 0) + 1;
          if (window.__userinfoCalls === 1) throw new TypeError('offline');
          return {{ ok: true, status: 200, json: async () => account }};
        }}
        return original(url, options);
      }};
    }}""", ACCOUNT)
    page.click("#signin")
    page.wait_for_selector("#retry-account:visible")

    status = page.text_content("#account-detail-status")
    assert "Could not reach Google" in status

    page.click("#retry-account")
    page.wait_for_selector("#welcome-email:visible")
    assert page.text_content("#welcome-email") == ACCOUNT["email"]


def test_malformed_account_response_is_not_retryable(open_panel):
    """If the JSON cannot be read, retrying the same bytes will not help."""
    page = open_panel()
    page.evaluate("""() => {
      chrome.identity.getAuthToken = (opts, cb) => cb("stub-token");
      const original = window.fetch;
      window.fetch = async (url, options) => {
        if (String(url).includes('oauth2/v3/userinfo')) {
          return { ok: true, status: 200, json: async () => { throw new Error('bad'); } };
        }
        return original(url, options);
      };
    }""")
    page.click("#signin")
    page.wait_for_selector("#welcome-signed-in:visible")

    status = page.text_content("#account-detail-status")
    assert "unreadable" in status
    assert not page.is_visible("#retry-account")
