"""Publishing a document and printing its URL are not the same as it working.

THE CHAIN THE STORE LISTING HANGS ON, and every link in it is in a different
repository:

    Chrome Web Store refuses a listing without a WORKING privacy policy URL
      -> the URL is muhammadbayoumi.github.io/mbiXsite/scrapex-privacy.html
      -> that page fetches privacy-policy.md from mbiX-hub AT RUNTIME
      -> publish-docs.yml is what puts it there

The publish step writes through the GitHub Contents API. The page reads through
raw.githubusercontent.com. Those are different systems, and a successful write
says nothing about whether a browser can read the result. The page also depends
on an attribute — `data-sx-doc` — that lives in a SEPARATE repository nobody
here can see, where a redesign could drop it silently.

Before this, the job ended by echoing the two page addresses. If either half
broke, the publish still reported success, the page read "Loading the policy…"
for ever, and the first person to notice would have been a Google reviewer
rejecting the submission with nothing in any log to explain why.

WHY NOT A HEADLESS BROWSER. Checking the RENDERED text would be the truest test
and by far the flakiest — GitHub Pages, a CDN, and a JavaScript module all have
to line up on someone else's schedule. A publish step that cries wolf gets
ignored, which is the exact failure it exists to prevent. Two cheap checks that
cannot flake beat one true check that does.
"""
from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-docs.yml"


@pytest.fixture(scope="module")
def verify_step() -> str:
    assert WORKFLOW.is_file(), f"{WORKFLOW} is gone; this guard must follow it"
    parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = parsed["jobs"]["publish"]["steps"]
    checks = [s for s in steps if "must actually work" in (s.get("name") or "")]
    assert checks, (
        "the step that checks the published pages is gone. Publishing would "
        "succeed while the pages stay blank, and the Chrome Web Store listing "
        "depends on one of them")
    return checks[0]["run"]


def test_the_markdown_is_read_from_the_address_a_browser_uses(verify_step):
    """Not the Contents API this job just wrote through. A write succeeding
    proves nothing about the CDN a reader goes to."""
    assert "raw.githubusercontent.com" in verify_step, (
        "the check reads back through a different path than the website does, "
        "so it can pass while every visitor gets nothing")


def test_the_page_is_checked_for_the_hook_its_loader_needs(verify_step):
    """`data-sx-doc` is what the site's JavaScript looks for. It lives in
    muhammadbayoumi/mbiXsite — another repository, another session, no test of
    ours runs there."""
    assert "data-sx-doc" in verify_step, (
        "nothing checks that the page still carries the attribute its loader "
        "hooks onto, so a redesign in mbiXsite would silently leave a heading "
        "with no policy under it")


def test_both_documents_are_checked_and_not_only_the_privacy_one(verify_step):
    """The store needs the policy; a person needs the support page. Checking
    one and publishing two is how the unchecked one rots."""
    for doc in ("privacy-policy", "support"):
        assert doc in verify_step, f"{doc} is published but never checked"


def test_a_slow_cdn_is_not_reported_as_a_broken_page(verify_step):
    """The write went through the API seconds earlier and raw.githubusercontent
    is a cache in front of it. Without a retry this step would fail on timing
    alone — and a check that fails at random gets switched off."""
    assert "sleep" in verify_step and "for attempt in" in verify_step, (
        "there is no retry, so normal CDN lag would be reported as a broken "
        "page and the step would be disabled within a week")


def test_a_failure_says_which_repository_to_go_and_fix(verify_step):
    """The documents published fine; what broke is downstream, in a repository
    this workflow cannot touch. A message that does not say so sends the reader
    looking here."""
    assert "mbiXsite" in verify_step, (
        "a failure does not name where the break actually is, so whoever reads "
        "it will search this repository for a fault that is not in it")


def test_the_step_fails_the_job_rather_than_only_printing(verify_step):
    """The defect being fixed is precisely a step that printed and passed."""
    assert "exit 1" in verify_step, (
        "the check reports problems without failing, which is the behaviour it "
        "was written to replace")
