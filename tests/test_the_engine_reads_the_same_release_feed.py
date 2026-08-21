"""Three readers of one manifest, and they must not drift apart.

`ScrapeX/json/version.json` on the hub is now read by three things:

    .github/workflows/release-engine.yml   WRITES it
    extension/releases.js                 reads it, to offer an install
    scrapex/release.py                     reads it, to fetch an update  <- new

`tests/test_the_two_release_paths.py` already holds the first two together. This
holds the third to them, because the failure it prevents is not a crash: the
engine and the panel would report DIFFERENT verdicts about the same
installation, and the owner would have no way to tell which was lying. That is
worse than either being wrong on its own.

The state vocabulary is checked as well as the URLs. `ok`, `none`, `offline`,
`unreadable` exist because "we do not know the latest engine" has several causes
and only one of them is anybody's fault — and the two surfaces will eventually
be shown side by side.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scrapex import release

# Reads extension/ sources, so it must carry the mark that makes the
# extension-only CI tier run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = [pytest.mark.extension, pytest.mark.docs]

ROOT = pathlib.Path(__file__).resolve().parents[1]
RELEASES_JS = (ROOT / "extension" / "releases.js").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "release-engine.yml").read_text(encoding="utf-8")


def _js_const(name: str) -> str:
    """One `export const NAME = "value";` out of releases.js."""
    found = re.search(rf'export const {name} = "([^"]+)"', RELEASES_JS)
    assert found, f"releases.js no longer exports {name}; this guard must follow it"
    return found.group(1)


def test_the_engine_and_the_panel_agree_where_the_manifest_lives():
    """A release published where the reader does not look is a release nobody sees."""
    assert release.PUBLIC_REPO == _js_const("PUBLIC_REPO")
    assert release.PRODUCT == _js_const("PRODUCT")


def test_the_workflow_publishes_to_the_repository_the_engine_reads():
    """And the writer must agree with both readers."""
    assert f"PUBLIC_REPO: {release.PUBLIC_REPO}" in WORKFLOW, (
        "the release workflow publishes somewhere the engine does not read")
    assert release.PRODUCT in WORKFLOW, (
        "the workflow does not stamp the product name the engine requires")


def test_the_manifest_url_the_engine_builds_is_the_one_the_panel_builds():
    """Built from the repo constant in both places, so this checks the shape too."""
    engine_url = release.manifest_url(29_000_000).split("?")[0]
    assert engine_url == release.VERSION_MANIFEST
    assert "raw.githubusercontent.com" in engine_url, (
        "the engine reads the manifest from somewhere other than raw."
        "githubusercontent.com — api.github.com allows 60 requests an hour per "
        "IP, which one office behind one address exhausts")
    assert release.VERSION_MANIFEST.split("/main/")[-1] in WORKFLOW


def test_the_cache_key_changes_once_a_minute_and_not_once_a_request():
    """The CDN caches this file for ~5 minutes, so a release can be invisible.

    A per-request key defeats the cache entirely, which measurably slowed the
    add-in's own path; a per-minute bucket lets everyone within one minute share
    one entry. Both halves are asserted, because either alone is wrong.
    """
    assert release.manifest_url(100) == release.manifest_url(100)
    assert release.manifest_url(100) != release.manifest_url(101)


@pytest.mark.parametrize("status,body,expected", [
    (404, None, "none"),
    (500, None, "unreadable"),
    (200, None, "unreadable"),
    (200, "not a mapping", "unreadable"),
    (200, {"product": "mbix-addin", "version": "1.0.0"}, "unreadable"),
    (200, {"product": "scrapex-engine"}, "unreadable"),
    (200, {"product": "scrapex-engine", "version": "latest"}, "unreadable"),
    (200, {"product": "scrapex-engine", "version": "1.2"}, "unreadable"),
    (200, {"product": "scrapex-engine", "version": "1.2.3"}, "ok"),
])
def test_every_manifest_answer_lands_in_a_named_state(status, body, expected):
    """No guessing, and no exception either — a bad manifest is a state, not a crash."""
    assert release.read_manifest(status, body).state == expected


def test_a_404_is_not_an_error_because_on_this_endpoint_it_means_nothing_shipped():
    """The branch most likely to be 'tidied' into an error, and it must not be.

    Every fresh installation in the world hits this until the first release. If
    it read as a failure, the product would tell all of them something is broken.
    """
    answer = release.read_manifest(404, None)
    assert answer.state == "none"
    assert "released" in answer.detail.lower()
    assert "error" not in answer.detail.lower()


def test_the_addin_manifest_is_refused_by_name():
    """The hub serves several products from one tree, from sibling folders.

    Reading the Excel add-in's manifest as ours would report a confident, wrong
    version — so the product must be named and must agree.
    """
    answer = release.read_manifest(200, {"product": "mbix-addin", "version": "1.0.76"})
    assert answer.state == "unreadable"
    assert "mbix-addin" in answer.detail


def test_an_installer_without_a_digest_is_reported_but_not_verifiable():
    """Named even when it cannot be trusted, because absent and untrusted differ."""
    body = {"product": "scrapex-engine", "version": "1.2.3",
            "installer": {"url": "https://example.invalid/x.exe", "bytes": 10}}
    answer = release.read_manifest(200, body)
    assert answer.ok
    assert answer.installer is not None
    assert answer.installer.verifiable is False


def test_a_release_with_no_installer_at_all_is_still_ok_but_says_so():
    """A release nobody can install is worth seeing BEFORE pressing Install."""
    answer = release.read_manifest(200, {"product": "scrapex-engine", "version": "1.2.3"})
    assert answer.ok
    assert answer.installer is None


def test_the_digest_is_lowercased_on_the_way_in():
    """So the comparison downstream never has to care what case a tool wrote."""
    body = {"product": "scrapex-engine", "version": "1.2.3",
            "installer": {"url": "https://example.invalid/x.exe",
                          "bytes": 1, "sha256": "AB" * 32}}
    assert release.read_manifest(200, body).installer.sha256 == "ab" * 32


@pytest.mark.parametrize("candidate,installed,newer", [
    ("0.2.2", "0.2.1", True),
    ("0.2.1", "0.2.2", False),
    ("0.2.2", "0.2.2", False),
    # THE ONE STRING COMPARISON GETS WRONG, and getting it wrong offers a
    # downgrade as an update.
    ("0.10.0", "0.9.0", True),
    ("0.9.0", "0.10.0", False),
    ("1.0.0", "0.99.99", True),
    # Unparseable on either side answers False: refusing to claim an update is
    # the safe direction.
    ("latest", "0.2.1", False),
    ("0.2.1", "", False),
])
def test_newer_is_decided_numerically_and_never_as_text(candidate, installed, newer):
    assert release.is_newer(candidate, installed) is newer


def test_the_engine_does_not_borrow_the_crawl_transport_for_its_own_release_feed():
    """`HttpFetcher` is crawl politeness: jitter, a circuit breaker, 1 req/s.

    Applying it to our own release host would put the update check behind a
    governor built for somebody else's website, and inherit a block counter that
    means nothing here. Asserted because "reuse the fetcher" is the obvious
    review comment and it is the wrong one.
    """
    source = (ROOT / "scrapex" / "release.py").read_text(encoding="utf-8")
    assert "HttpFetcher" not in source.replace("NOT `HttpFetcher`", "")
    assert "httpx" in source, "it should still use the dependency the repo has"


def test_the_check_timeout_is_its_own_and_is_short():
    """A stalled fetch to a third party must never delay the thing he opened."""
    assert 0 < release.CHECK_TIMEOUT_S <= 10
    assert release.DOWNLOAD_TIMEOUT_S > release.CHECK_TIMEOUT_S * 10, (
        "the installer download shares the check's timeout, so a real 70 MB "
        "fetch on a home connection will be cut off as though it had stalled")
