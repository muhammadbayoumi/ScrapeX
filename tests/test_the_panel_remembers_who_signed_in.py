"""The directory of accounts the panel remembers, and what it must never hold.

Multi-account switching arrived on 2026-08-11 WITHOUT breaking the owner's
ruling of 2026-08-05 that nothing is written to disk. What is stored is a
DIRECTORY — the names and addresses the panel already paints on screen — and a
token for any of them is minted at the moment it is needed and kept in memory.

extension/tests/accounts.test.mjs pins that store in isolation. This file pins
the WIRING: that signing in actually reaches it, that signing out leaves the row
behind instead of erasing it, and that nothing on the way in carries a
credential into storage. A store that is correct and never called would pass
every assertion in the other file.
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

# The key accounts.js versions its record under.
ACCOUNTS_KEY = "scrapex-accounts-v1"

# `sub` is Google's stable identifier, and the field the directory keys on. The
# harness returns this dict verbatim as the userinfo response.
ACCOUNT = {"sub": "110001", "name": "Muhammad Bayoumi",
           "email": "madastore1899@gmail.com",
           "picture": "https://lh3.googleusercontent.com/x"}


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
                                       name=f"directory{len(pages)}.html")
        page = browser.new_page(viewport={"width": 400, "height": 900})
        page.goto(page_file.as_uri())
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def _directory(page):
    """What is actually in chrome.storage.local, read from the page itself."""
    return page.evaluate(
        "async (key) => (await window.chrome.storage.local.get(key))[key] || null",
        ACCOUNTS_KEY)


def test_signing_in_puts_the_account_in_the_directory(open_panel):
    """Without this the switcher has nobody to switch to: the store can be
    perfect and never called, and every unit test still passes."""
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#welcome-signed-in:visible")
    page.wait_for_function(
        "async () => (await window.chrome.storage.local.get('scrapex-accounts-v1'))"
        "['scrapex-accounts-v1'] != null",
        timeout=10000)

    held = _directory(page)
    assert [row["id"] for row in held["accounts"]] == ["110001"], (
        "the account that just signed in is not in the directory")
    assert held["currentId"] == "110001", (
        "the panel does not record which account it is acting as")
    assert held["accounts"][0]["email"] == ACCOUNT["email"]


def test_the_directory_carries_no_credential(open_panel):
    """The owner's ruling of 2026-08-05, checked where it can actually be
    broken. accounts.js copies four fields by name; this proves the caller
    hands it an account and not the whole token response it is holding."""
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#welcome-signed-in:visible")
    page.wait_for_function(
        "async () => (await window.chrome.storage.local.get('scrapex-accounts-v1'))"
        "['scrapex-accounts-v1'] != null",
        timeout=10000)

    held = _directory(page)
    assert sorted(held["accounts"][0]) == ["email", "id", "name", "picture"], (
        f"an unexpected field reached storage: {held['accounts'][0]}")

    written = page.evaluate(
        "async () => JSON.stringify(await window.chrome.storage.local.get(null))")
    # The harness hands the panel this token; none of it may land on disk.
    assert "granted-token" not in written, f"a token reached storage: {written}"


def test_signing_out_keeps_the_row_and_stops_acting_as_it(open_panel):
    """Ending a session is not removing an account. The row is the way back in
    without typing the address again — the design draws it as a signed-out row
    with a Sign in beside it. Erasing it here would make Sign out and Remove the
    same button with two names."""
    page = open_panel(signed_in=ACCOUNT)
    page.wait_for_selector("#welcome-signed-in:visible")
    page.wait_for_function(
        "async () => (await window.chrome.storage.local.get('scrapex-accounts-v1'))"
        "['scrapex-accounts-v1'] != null",
        timeout=10000)

    page.click("#signout")
    page.wait_for_selector("#welcome-signed-out:visible")
    page.wait_for_function(
        "async () => (await window.chrome.storage.local.get('scrapex-accounts-v1'))"
        "['scrapex-accounts-v1'].currentId === ''",
        timeout=10000)

    held = _directory(page)
    assert [row["id"] for row in held["accounts"]] == ["110001"], (
        "signing out erased the account instead of ending its session")
    assert held["currentId"] == ""


def test_an_account_without_a_stable_id_is_not_remembered(open_panel):
    """Google should always return `sub`, and the panel must not fall apart on
    the day it does not. An address is not a safe key — people change theirs and
    Workspace admins reassign them — so a row without an id is not written at
    all, and the panel goes on working without a directory entry."""
    page = open_panel(signed_in={k: v for k, v in ACCOUNT.items() if k != "sub"})
    page.wait_for_selector("#welcome-signed-in:visible")
    page.wait_for_timeout(700)

    assert _directory(page) is None, (
        "a row nothing can switch to was written into the directory")
    assert page.text_content("#welcome-name").strip() == ACCOUNT["name"], (
        "the panel stopped painting the account because the directory refused it")
