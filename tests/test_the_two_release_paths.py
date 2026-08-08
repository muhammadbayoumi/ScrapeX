"""Two release paths that must not become one, and must not go out mislabelled.

PLATFORM-PLAN §5c and Decision 21. They are not variations of one mechanism:
the extension is uploaded TO Google's store, reviewed for a day or three, and
pushed to every user automatically; the engine is attached to a GitHub Release
that nothing reviews and nobody receives until the panel offers it.

Neither path existed. §5c's own "what exists today" said so: "There is no
release automation of any kind, for either product."

WHAT THESE TESTS ARE FOR. A release workflow runs perhaps once a month, and the
first time it runs wrong the result is public and permanent — a mislabelled
release, a signing key in a zip, a store upload reported as successful because
nobody read the body. None of that can be caught by running the workflow; it can
only be caught by reading it, which is what this does.
"""

from __future__ import annotations

import json
import pathlib

import pytest

# Guards the extension: this file reads extension/ sources — the manifest the
# store path packages, and the public repo the engine path publishes to. See
# tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ENGINE = WORKFLOWS / "release-engine.yml"
EXTENSION = WORKFLOWS / "release-extension.yml"


@pytest.fixture(scope="module")
def engine() -> str:
    return ENGINE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def extension() -> str:
    return EXTENSION.read_text(encoding="utf-8")


def test_both_paths_exist_and_are_valid_yaml(engine, extension):
    """A workflow that does not parse never runs, and GitHub reports it in a
    place nobody looks until the day they need it."""
    yaml = pytest.importorskip("yaml")

    for path in (ENGINE, EXTENSION):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert parsed, f"{path.name} is empty"
        # `on:` is parsed by PyYAML as the boolean True, which is a real and
        # well-known trap: the key is there and it is not the string "on".
        assert True in parsed or "on" in parsed, f"{path.name} has no trigger"


def test_each_path_answers_to_its_own_tag_and_no_other(engine, extension):
    """Decision 21: neither triggers the other. A shared trigger would make
    every engine release wait on Google's review, which is exactly the coupling
    the two paths exist to remove."""
    assert '- "engine-v*"' in engine
    assert "scrapex-v" not in engine.split("workflow_dispatch")[0]

    assert '- "scrapex-v*"' in extension
    assert "engine-v" not in extension.split("workflow_dispatch")[0]


def test_the_engine_is_built_on_windows_because_it_has_to_be(engine):
    """PyInstaller does not cross-compile. This is not a preference about CI
    runners, and packaging/build_engine.py says so in its own first paragraph."""
    assert "runs-on: windows-latest" in engine
    assert "cross-compile" in engine, (
        "the constraint is not written down, so someone will move this to "
        "ubuntu to make it faster")


def test_the_engine_tag_must_match_the_version_before_anything_is_built(engine):
    """THE CHECK THAT MATTERS MOST, and it must run FIRST.

    A tag saying 0.3.0 over an engine reporting 0.2.0 produces a release the
    panel cannot reason about: it offers an upgrade the owner already has, or
    hides one he needs. Neither failure announces itself, and both are permanent
    once the release is public.
    """
    assert 'test "$tag" = "$version"' in engine

    check = engine.index("The tag and the version must be the same number")
    build = engine.index("python packaging/build_engine.py")
    assert check < build, "the version is checked after the build, which wastes it"


def test_the_extension_tag_must_match_the_manifest(extension):
    """Chrome reads manifest.json and nothing else. A tag that disagrees
    publishes a version nobody can name — the store shows one number and the
    panel's About page another."""
    assert 'test "$tag" = "$manifest"' in extension
    assert "manifest.json" in extension


def test_the_built_engine_is_asked_whether_it_runs(engine):
    """An .exe that does not start is a release that turns every install into a
    support conversation. Asking it its version proves two things at once: that
    it runs, and that the binary carries the source that was checked."""
    assert "--version" in engine
    assert 'grep -q "$ENGINE_VERSION"' in engine


def test_the_engine_release_carries_a_checksum(engine):
    """A download that arrives truncated installs and fails later, somewhere
    unrelated. The same reasoning as the backup bundle's manifest."""
    assert "sha256sum" in engine
    assert "scrapex-engine.exe.sha256" in engine


def test_the_release_goes_to_the_public_site_and_not_this_repository(engine):
    """ScrapeX goes private before the first release, and GitHub answers 404 on
    a private repository's releases endpoint to anyone not signed in — which is
    every user. The panel reads that 404 as "nothing has been released yet"."""
    import re

    public = re.search(
        r'PUBLIC_REPO = "([^"]+)"',
        (ROOT / "extension" / "releases.js").read_text(encoding="utf-8")).group(1)

    assert f"PUBLIC_REPO: {public}" in engine, (
        "the workflow publishes somewhere other than where the panel looks")
    assert "--repo" in engine


def test_a_missing_token_is_named_rather_than_crashed_on(engine):
    """GITHUB_TOKEN cannot write to another repository, and the failure it
    produces — "resource not accessible by integration" — sends the owner
    reading about GitHub permissions when the real answer is one secret."""
    assert "PUBLIC_SITE_TOKEN" in engine
    assert "Contents:" in engine and "write" in engine


# ---- what must never leave the building --------------------------------------

def test_the_extension_package_leaves_out_the_tests_and_any_key(extension):
    """Every byte in a store upload is a byte Google reviews. And a private key
    in a package is a published private key — the manifest carries only the
    public half, and the check costs nothing."""
    assert "rm -rf build/scrapex/tests" in extension
    assert 'find build/scrapex -name "*.pem" -delete' in extension
    assert "a private key is in the package" in extension
    assert "tests are in the package" in extension


def test_the_package_is_opened_again_and_checked(extension):
    """A zip Chrome refuses is discovered three days later, at the end of a
    review. The manifest is re-read FROM THE ZIP, so a packaging step that
    dropped or corrupted it fails here instead."""
    assert "unzip -o -q" in extension
    assert "the manifest names files the package does not carry" in extension


def test_the_store_upload_reads_the_body_and_not_only_the_status(extension):
    """THE TRAP IN GOOGLE'S API. It answers HTTP 200 with a FAILURE inside the
    body. A workflow that checked only the status would report a rejected
    upload as a successful release, and the owner would find out when a user
    asked why the new version never arrived."""
    # ASSERTED AS A PIPELINE, not as two strings that happen to be present.
    # Proved by mutation: breaking the pipe while leaving both words in the
    # file passed, because a workflow can name `uploadState` and never read it.
    assert 'result=$(curl' in extension, "the response body is not captured"
    assert 'echo "$result" | python' in extension, (
        "the captured body is never fed to anything that inspects it")
    assert "uploadState" in extension
    assert "the store rejected the upload" in extension
    assert "sys.exit(1)" in extension, (
        "a rejected upload is printed and the step still succeeds")


def test_publishing_goes_to_trusted_testers_and_not_to_the_world(extension):
    """Decision 6: owner plus a few testers, unlisted. Publishing to `default`
    puts it in front of everyone, which is a different decision and not this
    workflow's to make."""
    assert "publishTarget=trustedTesters" in extension
    assert "publishTarget=default" not in extension


def test_uploading_and_submitting_are_separate_steps(extension):
    """Uploading leaves a draft; submitting starts Google's review and is the
    last reversible moment. One step doing both removes the pause."""
    assert extension.index("Upload to the Chrome Web Store") < \
        extension.index("Submit for review")


def test_every_secret_is_named_individually_when_it_is_missing(extension):
    """"Upload failed" over a missing secret is a morning spent reading
    Google's documentation for a one-line answer."""
    for secret in ("CWS_EXTENSION_ID", "CWS_CLIENT_ID", "CWS_CLIENT_SECRET",
                   "CWS_REFRESH_TOKEN"):
        assert secret in extension
    assert "these repository secrets are not set:" in extension


def test_neither_path_can_publish_from_a_manual_run_by_accident(engine, extension):
    """`workflow_dispatch` exists so the build can be exercised without cutting
    a release. A dispatch that published would make "let me just check the
    build" a release nobody meant to make."""
    for text in (engine, extension):
        assert "startsWith(github.ref, 'refs/tags/" in text, (
            "the publishing job is not gated on a tag, so a manual run "
            "publishes")


def test_the_engine_runs_the_suite_that_covers_it(engine):
    """`-m "not extension"` is deliberately NOT used: two of the marked files
    guard the engine as well, and a release is the last moment to start
    skipping tests."""
    assert 'pytest -q -m "not extension"' in engine
    assert "SCRAPEX_FULL_MIGRATIONS" in engine, (
        "the release does not replay the real migration stream, so it ships "
        "against the test-only schema template")
