"""An engine the panel cannot run against is refused, with the action to take.

M1's "done when", and the failure it is written against is not hypothetical.
Migration 0061 merged on 2026-08-04 and was never applied. The engine refused to
start — correctly, and with the exact command — on a stderr nobody reads. What
the owner saw was a dead panel.

Until now nothing in the panel checked. `startRun()` posted the job and let
whatever happened happen, so every incompatible pair produced the same thing: a
button that did nothing and no sentence saying why.

FIVE FACTS IN EVERY BRANCH, not four. A refusal that names the extension, the
engine and the minimum but not the two protocol numbers sends the reader to
check the fifth by hand, which is the state this replaces.

THE PROTOCOL IS CHECKED FIRST because it is the only one that makes the others
meaningless: two products that cannot agree how to speak cannot be compared on
features at all. `/api/health` has published `protocol_version` since the
handshake moved onto the transport that carries the traffic, and the panel threw
it away.
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

RUN_TAB = 'nav.side-rail button[data-view="run"]'


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def open_run(browser, tmp_path):
    """Open the panel on Run, with whatever engine the case describes."""
    pages = []

    def opener(**stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"refusal{len(pages)}.html")
        page = browser.new_page(viewport={"width": 400, "height": 900})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(500)
        page.click(RUN_TAB)
        page.wait_for_timeout(400)
        pages.append(page)
        return page

    try:
        yield opener
    finally:
        for page in pages:
            page.close()


def _refusal(page) -> str:
    box = page.locator("#run-refusal")
    return (box.inner_text() if box.is_visible() else "").strip()


def _facts(page) -> dict[str, str]:
    return dict(page.eval_on_selector_all(
        "#run-refusal .kv",
        "els => els.map(e => [e.children[0].textContent, e.children[1].textContent])"))


FIVE = ("Extension", "Engine", "Minimum extension the engine will talk to",
        "Protocol - extension", "Protocol - engine")


def test_a_healthy_pair_is_not_refused(open_run):
    """The overwhelmingly common case, and the one a too-eager gate breaks.

    Nothing is drawn, the button is pressable once a site is chosen, and the
    panel is exactly as it was."""
    page = open_run()

    assert not page.is_visible("#run-refusal")
    assert _refusal(page) == ""
    page.click('input[data-key="LONG_AR"]')
    page.wait_for_timeout(200)
    assert not page.is_disabled("#run")


def test_an_engine_speaking_another_protocol_is_refused_before_the_click(open_run):
    """THE CASE THE MILESTONE IS NAMED FOR.

    The engine answers, reports a version, looks entirely healthy — and speaks
    protocol 2 to an extension that speaks 1. Every feature comparison below
    this point would be arithmetic about two things that cannot talk."""
    page = open_run(protocol_version=2)

    text = _refusal(page)
    assert "different protocol versions" in text
    facts = _facts(page)
    assert all(name in facts for name in FIVE), f"only {sorted(facts)} were named"
    assert facts["Protocol - extension"] == "1"
    assert facts["Protocol - engine"] == "2"
    assert "Chrome updates it from the Web Store" in text, (
        "the engine is NEWER here, so the action must be about the extension")

    page.click('input[data-key="LONG_AR"]')
    page.wait_for_timeout(200)
    assert page.is_disabled("#run"), (
        "the button is pressable, so the panel is dead with an extra click in it")


def test_an_older_engine_is_told_to_be_installed_and_not_reloaded(open_run):
    """The other direction of the same mismatch, and a DIFFERENT action.

    One sentence for both would send the owner to the Chrome Web Store to fix
    an engine, which he cannot do."""
    page = open_run(protocol_version=0)

    text = _refusal(page)
    assert "different protocol versions" in text
    assert "GitHub release" in text
    assert "Web Store" not in text


def test_an_engine_that_says_nothing_about_its_features_is_refused(open_run):
    """Silence is not consent. Three causes — an engine older than feature
    reporting, a failed request, a broken build — and none of them is
    "everything is fine", so it may not be read as a pass."""
    page = open_run(version_reporting=False)

    text = _refusal(page)
    assert "did not say what it supports" in text
    assert all(name in _facts(page) for name in FIVE)
    assert "GitHub release" in text


def test_an_engine_that_is_down_is_refused_with_the_same_five_facts(open_run):
    """It already said "the engine is not running" in one muted line. The five
    facts cost nothing extra and answer the next question — WHICH engine, and
    what would it want — before it is asked."""
    page = open_run(engine_up=False)

    assert "not running" in _refusal(page)
    assert all(name in _facts(page) for name in FIVE)


def test_the_engine_stopping_between_the_render_and_the_click_still_refuses(open_run):
    """Checked twice on purpose. A panel open for an hour renders once; the
    engine can be stopped, upgraded or replaced in that hour, and the click is
    the moment that matters.

    THE POST IS WHAT IS ASSERTED, not the card. The first version of this test
    checked that the refusal appeared and that `state.jobRef` was empty, and it
    passed with the guard deleted — because `startRun`'s own `finally` calls
    `refreshRunButton`, which draws the refusal AFTER the job has already been
    sent, and the stub's reply carries no `job_ref` to notice. It asserted the
    symptom and missed the act.
    """
    page = open_run()
    page.click('input[data-key="LONG_AR"]')
    page.wait_for_timeout(200)
    assert not page.is_disabled("#run")

    page.evaluate("""() => {
        window.__posted = [];
        const real = window.fetch;
        window.fetch = (url, options) => {
            if ((options || {}).method === 'POST') window.__posted.push(String(url));
            return real(url, options);
        };
    }""")

    # The engine goes away, and nothing re-renders.
    page.evaluate("() => { state.engineUp = false; }")
    page.click("#run")
    page.wait_for_timeout(400)

    assert "not running" in _refusal(page)
    posted = page.evaluate("() => window.__posted")
    assert not [u for u in posted if "/api/jobs" in u], (
        f"a job was queued against an engine that is not there: {posted}")
