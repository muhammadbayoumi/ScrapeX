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

pytestmark = [pytest.mark.extension, pytest.mark.docs]

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

    def opener(*, ready="settled", **stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"signin{len(pages)}.html")
        page = browser.new_page(viewport={"width": 400, "height": 900})
        page.goto(page_file.as_uri())
        (harness.wait_until_settled if ready == "settled"
         else harness.wait_until_interactive)(page)
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


# THE ID THE CHROME WEB STORE ASSIGNED, which is the only one that counts. The
# repository carried a different key for a while and everything agreed with it —
# the manifest, both documents, and this constant — so a check that they matched
# each other passed while all four were wrong together. The store item is the
# authority; it was read off the listing on 2026-08-10.
#
# THE ONE PLACE THE ID IS WRITTEN DOWN. Chrome derives it from the manifest
# `key`, the OAuth client is registered against it, and docs/store-listing.md
# tells the owner to abort the listing if what Chrome shows him differs. Three
# copies of a fact is two too many, so the test derives it and compares.
EXTENSION_ID = "ekcgggphcfdbjgfkcmjagehfjhijeang"

ACCOUNT = {"name": "Muhammad Bayoumi", "email": "madastore1899@gmail.com",
           "picture": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAf"
                      "FcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="}


def _visible_img_selector(page):
    """Return the currently visible Google button asset image."""
    return page.locator(".profile-signin-img:not(.hidden)").first


def test_the_initial_state_is_checking_then_resolves_to_signed_out(open_panel):
    """Before Chrome answers, the page waits. Once Chrome says no, the button
    appears and the checking state is gone.

    THE FIRST HALF USED TO GO UNTESTED. Every assertion here was about the END
    state -- signed-out shown, checking hidden -- so deleting the checking state
    from the product entirely would not have failed this test, under a name that
    promises it. `slow=True` holds Chrome's answer back so the waiting state can
    actually be SEEN before it resolves.
    """
    slow_page = open_panel(signin_delay_ms=1200, ready="interactive")
    assert slow_page.is_visible("#welcome-checking"), (
        "the panel never shows a waiting state while Chrome is deciding, so a "
        "slow answer looks like a signed-out account")
    assert not slow_page.is_visible("#welcome-signed-out"), (
        "the sign-in button is offered before Chrome has answered, which is how "
        "an already-signed-in owner gets asked to sign in again")
    slow_page.wait_for_selector("#welcome-signed-out:visible", timeout=15000)
    assert not slow_page.is_visible("#welcome-checking")

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
    nothing changed rather than naming a problem to go and fix.

    It claims no cause (#1544): Chrome's "The user did not approve access." covers
    a closed window and a refusal on Google's screen alike. A press that failed
    is the line under the button, not a box above it (connect-interstitials.mdx)."""
    page = open_panel()
    page.click("#signin")
    page.wait_for_function(
        "() => document.getElementById('signin-problem').textContent !== ''",
        timeout=8000)

    problem = page.text_content("#signin-problem")
    assert problem == "Google sign-in did not finish. Nothing changed."
    assert "closed" not in problem
    assert page.is_visible("#signin-problem-box")
    assert page.is_hidden("#signin-blocked")
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
    page.wait_for_selector("#signin-blocked:visible", timeout=8000)

    # Blocked, not retried: an Admonition above the button (connect-interstitials.mdx),
    # destructive, named by its type as Supabase's Admonition names it.
    assert page.get_attribute("#signin-blocked", "class").split() == [
        "admonition", "destructive"]
    assert page.get_attribute("#signin-blocked", "aria-label") == "Danger"
    assert page.text_content("#signin-blocked-title") == (
        "Google refused this build’s OAuth client")
    problem = page.text_content("#signin-blocked-description")
    assert "Check the client in Google Cloud" in problem
    assert "closed" not in problem and "did not finish" not in problem
    assert page.text_content("#signin-problem") == ""


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


NO_CHROME_ACCOUNT = "The user is not signed in."


def test_a_chrome_with_no_account_is_not_greeted_with_chromes_own_error(open_panel):
    """THE FIRST THING A NEW USER SAW, having pressed nothing.

    The panel checks the account silently on every open, and it shows two of the
    states that check can return — `timeout` and `failed` — so that a panel
    which cannot check says why instead of sitting blank (`#152`). Chrome's
    message for a profile with no Google account matched none of the shapes
    `readTokenResult` knew, fell through to `failed`, and was printed verbatim.
    A browser nobody has signed into is the ordinary first state of the product,
    not a fault to report.
    """
    page = open_panel(signin_error=NO_CHROME_ACCOUNT)
    page.wait_for_selector("#welcome-signed-out:visible", timeout=8000)

    assert page.text_content("#signin-problem").strip() == "", (
        "the silent check reported a browser with no account as a problem")
    assert page.is_hidden("#signin-problem")


def test_pressing_sign_in_with_no_chrome_account_says_what_to_do(open_panel):
    """Silent is not the same as secret. Someone who PRESSED the button is owed
    an answer, and Chrome's raw sentence is not one — it names no next step."""
    page = open_panel(signin_error=NO_CHROME_ACCOUNT)
    page.click("#signin")
    page.wait_for_selector("#signin-blocked:visible", timeout=8000)

    assert page.get_attribute("#signin-blocked", "aria-label") == "Warning"
    # What Chrome said, and no more: "not signed in", not "has no account".
    assert page.text_content("#signin-blocked-title") == "Chrome is not signed in to Google"
    assert page.text_content("#signin-blocked-description") == (
        "Sign in to Chrome, then try again.")
    assert NO_CHROME_ACCOUNT not in page.text_content("#signin-blocked"), (
        "Chrome's own words reached the panel instead of the panel's")


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
    import base64
    import hashlib
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

    # THE ID ITSELF, DERIVED. A truthy `key` only proves the id is stable, not
    # that it is THE id. The key was rotated once in this project's history and
    # the id changed with it, while docs/store-listing.md still told the owner
    # to abort the listing unless Chrome showed him the old one -- a rotation
    # nobody would notice until the store rejected the upload.
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    derived = "".join(chr(ord("a") + int(char, 16)) for char in digest)
    assert derived == EXTENSION_ID, (
        f"the manifest key now derives the extension id {derived}, not "
        f"{EXTENSION_ID}. Every place that names the id is now wrong -- the "
        "OAuth client, docs/store-listing.md and docs/SITE-BRIEF.md -- and "
        "sign-in will fail with a client mismatch nobody can debug from the "
        "error Chrome shows.")

    for doc in ("docs/store-listing.md", "docs/SITE-BRIEF.md"):
        text = (pathlib.Path(__file__).resolve().parents[1] / doc).read_text(
            encoding="utf-8")
        assert EXTENSION_ID in text, (
            f"{doc} no longer names the pinned extension id {EXTENSION_ID}; "
            "the listing instructions and the manifest have drifted apart")
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
    """While the consent flow is in progress the button is busy, and a status
    appears outside the Google image.

    The card stays (#1544): the press used to swap it for the opening splash, so
    the busy button and "Signing in…" were never seen. And the button is
    aria-disabled rather than disabled, so it keeps focus (#1542), undimmed:
    Google's official image is never dimmed."""
    page = open_panel()
    # HELD, NOT TIMED: Chrome's answer waits until the test releases it, so every
    # assertion below reads the press while it is in flight. A 300 ms timer let the
    # press finish before the opacity was read on a fast machine (#670, #1492).
    page.evaluate(f"""(account) => {{
      chrome.identity.getAuthToken = (opts, cb) => {{
        window.__sx_release = () => cb("stub-token");
      }};
      const original = window.fetch;
      window.fetch = async (url, options) => {{
        if (String(url).includes('oauth2/v3/userinfo')) {{
          return {{ ok: true, status: 200, json: async () => account }};
        }}
        return original(url, options);
      }};
    }}""", ACCOUNT)
    # BY KEYBOARD, the pointer parked away: a hover would restore full opacity on its
    # own, and the dim this guards against is the one a keyboard press meets.
    page.mouse.move(0, 0)
    page.focus("#signin")
    page.keyboard.press("Enter")
    page.wait_for_function(
        """() => {
          const btn = document.getElementById('signin');
          return btn.getAttribute('aria-disabled') === 'true'
            && btn.getAttribute('aria-busy') === 'true'
            && document.getElementById('signin-status').textContent !== '';
        }""",
        timeout=2000)

    assert page.text_content("#signin-status") == "Signing in with Google…"
    assert page.is_visible("#signin-status")
    assert page.is_visible("#welcome-signed-out") and page.is_hidden("#welcome-checking")
    assert not page.evaluate("() => document.getElementById('signin').disabled")
    assert page.evaluate("() => getComputedStyle(document.getElementById('signin')).opacity") == "1"

    page.evaluate("() => window.__sx_release()")
    page.wait_for_selector("#welcome-signed-in:visible", timeout=10000)
    assert page.get_attribute("#signin", "aria-busy") == "false"
    assert page.get_attribute("#signin", "aria-disabled") is None


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
    remains visible on dark surfaces. It sits in the card's logo tile, as
    Supabase's own mark sits in its LogoBox (InterstitialLayout.tsx@86c813ec:114-123)."""
    page = open_panel()
    page.evaluate("""() => {
      window.ScrapeXAppearance.set({mode: 'manual', scheme: 'dark'});
    }""")

    mark = page.locator("#welcome-signed-out .signin-logo .brand-logo")
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


def test_the_hover_indicator_hugs_the_google_asset_and_not_the_touch_target(open_panel):
    """WHAT THE OWNER ACTUALLY SAW: a hard square box round a rounded button.

    The hover ring is a box-shadow, and a box-shadow follows the border box and
    the border-radius of whatever element carries it. It was on the WRAPPER --
    180x48, because 48 is the touch target, and `border-radius: 0` -- while the
    thing a person reads as the button is the official asset inside it, 180x40
    with corners painted 2.5px round. So the indicator sat 4px proud of the
    control top and bottom, with square corners. Every CSS-text assertion passed:
    they checked a box-shadow was declared, never where it landed.

    This measures the rendered result, which is the only place the defect was
    visible.
    """
    page = open_panel()
    page.wait_for_selector("#welcome-signed-out:visible")
    page.hover("#signin")
    page.wait_for_timeout(300)

    geometry = page.evaluate("""() => {
      const button = document.querySelector('#signin');
      const image = button.querySelector('img[data-scheme]:not(.hidden)');
      const shadowed = getComputedStyle(image).boxShadow;
      const bare = getComputedStyle(button).boxShadow;
      const b = button.getBoundingClientRect(), i = image.getBoundingClientRect();
      return {
        onImage: shadowed !== 'none',
        onButton: bare !== 'none',
        radius: parseFloat(getComputedStyle(image).borderRadius) || 0,
        overhang: Math.max(i.top - b.top, b.bottom - i.bottom),
      };
    }""")

    assert geometry["onImage"], (
        "hovering paints no indicator on the Google asset, so the button gives "
        "no feedback at all")
    assert not geometry["onButton"], (
        f"the indicator is on the {geometry['overhang']*2 + 40:.0f}px-tall touch "
        "target rather than the 40px asset, so it draws a box standing proud of "
        "the control the owner can see")
    assert geometry["radius"] > 0, (
        "the asset carries no border-radius, so the ring is drawn with SQUARE "
        "corners around a button whose corners are painted round")


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

    # THE THING THIS TEST IS NAMED AFTER. Everything above is the UI landing in
    # the signed-out state, which it would also do if the dead token were left
    # in Chrome's cache -- and then every later sign-in would hand back the same
    # invalid token and fail the same way, with the panel insisting the owner
    # sign in to an account he is already signed in to.
    cleared = page.evaluate("() => window.__sx_removed_tokens || []")
    assert cleared == ["stub-token"], (
        "the 401 did not reach chrome.identity.removeCachedAuthToken, so the "
        f"invalid token is still cached (removed: {cleared!r})")


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


# ---- the sign-in card's states (#1544, his approval of 2026-11-26) ------------------
#
# Each state below is a picture he approved: the stage 4 drawing named in each docstring
# is in the study (#1544). They are checked through the real panel and the real Chrome
# strings (Chromium's identity_constants.h and google_service_auth_error.cc).

OFFLINE = "OAuth2 request failed: Connection failed (-106)."
EMAIL_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
PROFILE_SCOPE = "https://www.googleapis.com/auth/userinfo.profile"


def _late_userinfo_401(page):
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (url, options) => {
        if (String(url).includes('oauth2/v3/userinfo')) {
          return { ok: false, status: 401, json: async () => ({}) };
        }
        return original(url, options);
      };
    }""")


def test_a_failure_that_arrives_late_is_drawn_as_one_on_time_would_be(open_panel):
    """State 05b. The opening check gives up WAITING at 2.5 s, not LISTENING (#2005): a
    failure Chrome reports afterwards is said exactly as the same failure on time."""
    page = open_panel(signin_error=OFFLINE, signin_delay_ms=3500, ready="interactive")
    page.wait_for_selector("#checking-help:not(.hidden)", timeout=3_500)
    page.wait_for_selector("#signin-blocked:visible", timeout=4_000)

    assert page.text_content("#signin-blocked-title") == "Chrome could not check your account"
    assert page.text_content("#signin-blocked-description") == (
        "Could not reach Google. Check your internet connection, then try again.")
    assert page.is_hidden("#checking-help")


def test_a_late_401_drops_the_token_chrome_was_holding(open_panel):
    """State 05c. A late token Google refuses is a dead token: dropped from Chrome's cache
    on the late path as on the on-time one, or the next press is handed it again."""
    page = open_panel(signed_in=ACCOUNT, signin_delay_ms=3500, ready="interactive")
    _late_userinfo_401(page)
    page.wait_for_selector("#signin-blocked:visible", timeout=7_000)

    assert "isn’t currently granted" in page.text_content("#signin-blocked-description")
    assert page.evaluate("() => window.__sx_removed_tokens || []") == ["stub-token"]


def test_a_press_from_under_the_loader_takes_the_button_back_to_the_card(open_panel):
    """State 04b. There is ONE Google button: past the deadline it is moved under the
    loader, and a press there takes it back to the card, busy and still focused."""
    page = open_panel(signin_never_returns=True, ready="interactive")
    page.wait_for_selector("#checking-help #signin:visible", timeout=3_500)
    assert page.locator(".profile-signin").count() == 1, "the Google button exists twice"

    page.focus("#signin")
    page.keyboard.press("Enter")
    page.wait_for_selector("#welcome-signed-out:visible", timeout=2_000)

    assert page.locator("#welcome-signed-out .signin-actions #signin").count() == 1
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "signin"
    assert page.get_attribute("#signin", "aria-busy") == "true"
    assert page.is_hidden("#welcome-checking")


def test_focus_on_the_helps_button_survives_a_late_failure(open_panel):
    """State 05d. When a late answer removes the help, focus that sat on its button lands
    on the card's button (WCAG 2.2 SC 2.4.3), not on <body>."""
    page = open_panel(signin_error=OFFLINE, signin_delay_ms=3500, ready="interactive")
    page.wait_for_selector("#checking-help #signin:visible", timeout=3_500)
    page.focus("#signin")
    page.wait_for_selector("#signin-blocked:visible", timeout=4_000)

    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "signin"
    assert page.locator("#welcome-signed-out #signin").count() == 1


def test_a_partial_grant_is_not_a_sign_in_and_the_next_press_asks_again(open_panel):
    """State 13, his option (a) on #858. A grant without drive.file unlocks nothing sign-in
    is for, so it is a warning on the card, not a sign-in; and the next press first drops
    Chrome's cached partial token, or Chrome would hand it back without asking."""
    page = open_panel(signed_in=ACCOUNT, granted_scopes=[EMAIL_SCOPE, PROFILE_SCOPE])
    page.wait_for_selector("#signin-blocked:visible", timeout=8_000)

    assert page.text_content("#signin-blocked-title") == "Drive access was not granted"
    assert page.is_visible("#welcome-signed-out") and page.is_hidden("#welcome-signed-in")
    assert page.get_attribute("#tab-profile", "aria-label") == "Profile, signed out"
    assert page.evaluate("() => window.__sx_removed_tokens || []") == []

    page.click("#signin")
    page.wait_for_function("() => (window.__sx_removed_tokens || []).length > 0", timeout=4_000)
    assert page.evaluate("() => window.__sx_removed_tokens") == ["stub-token"]


def test_a_failed_revoke_says_the_access_stands(open_panel):
    """State 22. When Google refuses the revoke, Chrome's copy is dropped but the grant
    stands, so the next open signs him back in: the words say that, not "signed out on
    this computer", which the next open would undo."""
    page = open_panel(signed_in=ACCOUNT, revoke_status=500)
    page.wait_for_selector("#welcome-signed-in:visible", timeout=8_000)
    page.click("#signout")
    page.wait_for_selector("#signin-blocked:visible", timeout=8_000)

    assert page.text_content("#signin-blocked-title") == (
        "ScrapeX still has access to your Google Account")
    words = page.text_content("#signin-blocked-description")
    assert words.startswith("Google answered 500 to the revoke request.")
    # ONE NAME FOR ONE PAGE: the note names Google's page as the signed-in control that
    # opens it does. Renaming either one fails here until the other follows.
    assert "remove ScrapeX on your Google Account’s permissions page" in words
    assert page.text_content("#drive-review-permissions .manage-account-row-title") == (
        "Review permissions in Google")
    # True only because this token came from Chrome's own account (getAuthToken).
    assert words.endswith("Until then, the panel signs you in again when it opens.")


def test_our_own_error_after_a_press_is_said_and_keeps_focus(open_panel):
    """State 23b. No silent failure: an exception in the panel's own code while it settles
    an answer is drawn under the button, naming what failed, and focus stays put."""
    page = open_panel()
    page.evaluate("""() => {
      chrome.identity.getAuthToken = (opts, cb) => cb("stub-token");
      chrome.identity.removeCachedAuthToken = () => {
        throw new TypeError("injected fault");
      };
    }""")
    _late_userinfo_401(page)
    page.focus("#signin")
    page.keyboard.press("Enter")
    page.wait_for_selector("#signin-problem-box:visible", timeout=8_000)

    assert page.text_content("#signin-problem") == (
        "Could not check your account. ScrapeX failed: injected fault")
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "signin"
    assert page.get_attribute("#signin", "aria-busy") == "false"


def test_a_consent_that_finishes_after_120_seconds_signs_him_in(open_panel):
    """State 21. A press's own deadline (120 s) is not a reason to drop the token Google
    then sends: two-step verification can take that long."""
    page = open_panel()
    page.evaluate(f"""(account) => {{
      window.__sx_grant_again(account);
      chrome.identity.getAuthToken = (opts, cb) => setTimeout(() => cb("stub-token"), 125000);
    }}""", ACCOUNT)
    page.clock.install()
    page.click("#signin")
    page.clock.run_for(121_000)
    page.wait_for_selector("#signin-problem-box:visible", timeout=4_000)
    assert "did not finish in time" in page.text_content("#signin-problem")

    page.clock.run_for(5_000)
    page.wait_for_selector("#welcome-signed-in:visible", timeout=4_000)
    assert page.text_content("#welcome-name").strip() == ACCOUNT["name"]


def test_offline_on_open_says_so_in_the_card(open_panel):
    """State 12. Chrome's own "Connection failed" on the opening check: nothing was
    pressed, so it is the card's Admonition, not a line under the button."""
    page = open_panel(signin_error=OFFLINE)
    page.wait_for_selector("#signin-blocked:visible", timeout=8_000)

    assert page.text_content("#signin-blocked-description") == (
        "Could not reach Google. Check your internet connection, then try again.")
    assert OFFLINE not in page.text_content("#welcome-signed-out")
    assert page.text_content("#signin-problem") == ""


def test_a_short_panel_keeps_the_focused_button_in_view(browser, tmp_path):
    """State 16a. 320 x 320: an Admonition drawn above a focused button pushes it down a
    card taller than the panel; the card scrolls just enough to keep all of it in view
    (WCAG 2.2 SC 2.4.11), and the document still fits the viewport."""
    page_file = harness.build_page(tmp_path, harness.stub(
        signin_error="OAuth2 request failed: Service responded with error: 'bad client id: 1'"),
        name="short.html")
    page = browser.new_page(viewport={"width": 320, "height": 320})
    try:
        page.goto(page_file.as_uri())
        harness.wait_until_settled(page)
        page.focus("#signin")
        page.keyboard.press("Enter")
        page.wait_for_selector("#signin-blocked:visible", timeout=8_000)
        page.wait_for_timeout(200)
        seen = page.evaluate("""() => {
          const b = document.getElementById('signin').getBoundingClientRect();
          const c = document.getElementById('profile-card').getBoundingClientRect();
          return {inside: b.top >= c.top - 0.5 && b.bottom <= c.bottom + 0.5
                          && b.bottom <= innerHeight + 0.5,
                  focus: document.activeElement.id,
                  fits: document.documentElement.scrollHeight <= innerHeight + 1};
        }""")
        assert seen == {"inside": True, "focus": "signin", "fits": True}, seen
    finally:
        page.close()


def test_our_own_error_on_a_late_answer_is_said_and_keeps_focus(open_panel):
    """State 23c. An exception while settling Chrome's LATE answer is caught and drawn as
    one on time is, not left as an unhandled rejection under a bare loader; and focus that
    sat on the help's button lands on the card's button."""
    page = open_panel(signed_in=ACCOUNT, signin_delay_ms=3500, ready="interactive")
    _late_userinfo_401(page)
    page.evaluate("""() => {
      chrome.identity.removeCachedAuthToken = () => { throw new TypeError("injected fault"); };
    }""")
    page.wait_for_selector("#checking-help #signin:visible", timeout=3_500)
    page.focus("#signin")
    page.wait_for_selector("#signin-blocked:visible", timeout=4_000)

    assert page.text_content("#signin-blocked-title") == "Could not check your account"
    assert page.text_content("#signin-blocked-description") == "ScrapeX failed: injected fault"
    assert page.evaluate("() => document.activeElement && document.activeElement.id") == "signin"
