"""The first install is handed to `chrome.downloads`, not thrown at a URL.

`R-36` part 1 is a LIMIT, measured rather than assumed: `extension/manifest.json`
granted `activeTab, identity, nativeMessaging, sidePanel, storage, tabs` and no
`downloads`, so `extension/app.js` could only call `window.open(installer.url)` —
hand a URL to the browser and let go. No progress, no completion, no idea whether
71 MB ever arrived. On a slow connection that is a button that appears to do
nothing, which is close to how the owner met the engine in the first place.

WHAT THE PERMISSION BUYS AND WHAT IT STILL CANNOT: a real download the panel can
watch and reveal. It does NOT buy reading the file, so the panel still cannot
verify the SHA-256 — which is why the engine does that for every update after the
first (`scrapex/update.py`) and why the number on screen is now labelled as the
reader's to compare rather than left sitting there as an implied guarantee. That
last point is `R-36`'s own words: a number nothing checks is worse than no number.

These tests read the sources rather than driving a browser, because what has to
stay true is a property of the code: the permission is declared, the API is the
one that reports progress, and the checksum is attributed. The panel DOM suite
drives the rendering.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

pytestmark = [pytest.mark.extension]

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
APP_JS = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
APP_HTML = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")
LISTING = (ROOT / "docs" / "store-listing.md").read_text(encoding="utf-8")


def test_the_downloads_permission_is_declared():
    """Without it every `chrome.downloads` call below throws at runtime."""
    assert "downloads" in MANIFEST["permissions"], (
        "the downloads permission is gone, so the panel is back to handing a URL "
        "to the browser and letting go")


def test_no_permission_was_traded_away_to_get_it():
    """A new permission must be an ADDITION.

    Every permission in this list is load-bearing — `nativeMessaging` is the
    engine bridge, `identity` is sign-in, `sidePanel` is the panel itself — and
    a store review that asks about `downloads` is not a reason to drop one of
    those to keep the count the same.
    """
    for needed in ("activeTab", "identity", "nativeMessaging",
                   "sidePanel", "storage", "tabs"):
        assert needed in MANIFEST["permissions"], f"{needed} was dropped"


def test_the_installer_is_fetched_with_the_api_that_reports_progress():
    """`chrome.downloads.download`, and `search` — which is where the bytes are.

    `onChanged` alone fires on state transitions, not per byte, so a percentage
    needs `search()`. Asserting both stops someone simplifying to `onChanged`
    and leaving a bar that jumps 0 → 100.
    """
    assert "chrome.downloads.download(" in APP_JS
    assert "chrome.downloads.search(" in APP_JS, (
        "nothing reads bytesReceived, so there is no percentage to show")
    assert "bytesReceived" in APP_JS


def test_it_reveals_the_file_when_it_finishes():
    """A 71 MB file in Downloads that the panel will not point at is half a job."""
    assert "chrome.downloads.show(" in APP_JS


def test_a_failed_download_says_why_and_offers_to_retry():
    """"Download failed" sends somebody to check their engine.

    The browser's own reason — `SERVER_FORBIDDEN`, `NETWORK_FAILED` — sends them
    to the right place, so it must be shown rather than swallowed.
    """
    # ASSERTED ON THE STRING THAT REACHES THE SCREEN, not on the identifier
    # appearing somewhere in the file. The first version of this test grepped for
    # `item.error` and a mutation that replaced one of its two occurrences with
    # `false` survived — the name was still in the source, and the reason was
    # gone from the label.
    # `.` does not match a newline without DOTALL, so this stays on one line
    # without needing an escape the writing tools keep mangling.
    assert re.search(r"Download failed.*\$\{item\.error\}", APP_JS), (
        "the failure label no longer interpolates the browser's own reason, so "
        "'Download failed' is all the reader gets")
    # AND THE BRANCH IS CHOSEN BY IT. Pinning only the template above left a
    # mutation alive: replacing the ternary's CONDITION with `false` takes the
    # else branch every time while the template sits there unreached. A grep
    # cannot see a dead branch, so the condition is pinned too.
    assert re.search(r"item\.error\s*\?", APP_JS), (
        "the failure label no longer branches on whether there IS a reason, so "
        "the reason is unreachable even though the text for it remains")
    assert re.search(r'state === "complete"', APP_JS), (
        "completion is not distinguished from interruption")


def test_window_open_survives_only_as_a_fallback():
    """The old path is kept for the case that needs it, and only that case.

    `chrome.downloads` is absent when the panel is loaded in a plain page by the
    DOM tests, and a first install failing because a permission was declined is
    exactly when the old behaviour is worth having. But it must not be the
    primary route any more.
    """
    assert "window.open(installer.url" in APP_JS, (
        "the fallback is gone; a declined permission now has no route at all")
    # The button's own handler must be the new function, not the old call.
    assert "download.onclick = () => startInstallerDownload(installer);" in APP_JS, (
        "the Download button no longer routes through the downloads API")


def test_the_checksum_on_screen_says_who_checks_it():
    """R-36: a number nothing verifies is worse than none — it reads as a promise.

    The panel cannot verify it (no file read), so the markup must say what the
    number is for and who does check it. Asserted on the note's presence AND on
    it naming the Engine, because an empty reassurance would satisfy the first
    half alone.
    """
    assert 'id="engine-checksum-note"' in APP_HTML, (
        "the SHA-256 sits on screen unattributed again")
    note = re.search(r'id="engine-checksum-note">(.*?)</p>', APP_HTML, re.S)
    assert note, "the note element has no text"
    text = " ".join(note.group(1).split())
    assert "Engine" in text, f"the note does not say who verifies it: {text!r}"
    assert "check" in text.lower()


def test_the_saveas_dialogue_is_suppressed_deliberately():
    """A Save-As on a file the owner already pressed a button for is one more
    thing to get wrong, and `show()` takes him to it anyway."""
    assert re.search(r"saveAs:\s*false", APP_JS), (
        "the download now opens a Save-As dialogue for a file already chosen")


def test_the_store_listing_does_not_claim_something_this_code_makes_false():
    """THE PROSE WENT FALSE THE MOMENT THE CODE CHANGED, and nothing said so.

    `docs/store-listing.md` justified `nativeMessaging` with a sentence in
    capitals: *"This extension does not download, install, execute or update
    it."* Adding `chrome.downloads.download` made the first verb untrue. The
    listing is what gets submitted to Google, so an untrue claim there is not a
    documentation defect — it is a rejected submission at best.

    `test_the_privacy_policy_is_true.py` caught the MISSING justification for the
    new permission, which is how this was found. It could not catch the false
    claim, because a sentence about what the code does not do is invisible to a
    check that only reads the permission list. This is that check.
    """
    downloads_something = "chrome.downloads.download(" in APP_JS
    # Whitespace-collapsed, because the sentence is wrapped in the source and a
    # substring check against the raw file would miss it across the line break.
    flat = " ".join(LISTING.split())
    claims_it_does_not = "not download" in flat
    assert not (downloads_something and claims_it_does_not), (
        "app.js calls chrome.downloads.download while the store listing still "
        "claims the extension does not download the engine. One of the two is "
        "wrong, and the listing is the one Google reads.")


def test_the_listing_still_promises_the_things_that_ARE_true():
    """Correcting one clause must not quietly soften the rest.

    These three are the load-bearing promises about the engine, and they are all
    still true: the panel does not install it, does not run it, and does not read
    what it downloaded. Losing any of them while editing the sentence above would
    be a bigger problem than the one being fixed.
    """
    for promise in ("does not install it", "does not execute it",
                    "never reads the contents"):
        assert promise in LISTING, (
            f"the listing no longer promises {promise!r} — either the code "
            f"changed or a true claim was dropped while editing a false one")
