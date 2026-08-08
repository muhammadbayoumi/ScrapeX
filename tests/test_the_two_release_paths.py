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
import os
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest

# Guards the extension: this file reads extension/ sources — the manifest the
# store path packages, and the public repo the engine path publishes to. See
# tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ENGINE = WORKFLOWS / "release-engine.yml"
EXTENSION = WORKFLOWS / "release-extension.yml"
HELPER = WORKFLOWS / "put-to-hub.sh"


def step_order(text: str, job: str) -> list[str]:
    """The job's step NAMES, in order, parsed rather than searched.

    Ordering asserted with `text.index("Some step")` is weaker than it looks: a
    step renamed to `zzz Some step` still contains the substring, so the
    assertion passes while the order it describes has changed. Caught by
    mutation, twice — once here and once on `"concurrency:" in engine`.
    """
    yaml = pytest.importorskip("yaml")
    return [s["name"] for s in yaml.safe_load(text)["jobs"][job]["steps"]
            if "name" in s]


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

    steps = step_order(engine, "build")
    assert (steps.index("The tag and the version must be the same number")
            < steps.index("Build")), (
        "the version is checked after the build, which wastes it")


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


# ---- what was learned on the add-in's release path ---------------------------
# mbiXaddin has cut seventy-six releases through a workflow of the same shape.
# Three of its guards exist because something went wrong without them, and all
# three apply here unchanged. The rest of that workflow — a self-hosted runner,
# an imported signing certificate — exists because the add-in needs Office and a
# signed ClickOnce manifest, and is deliberately NOT copied.

def test_a_release_must_be_newer_than_the_one_already_published(engine):
    """THE GUARD THIS PATH DID NOT HAVE, and the only one that looks OUTWARD.

    Every other check asks whether the release is consistent with itself. This
    asks whether it makes sense next to what users already have, and both ways
    it can fail are silent: an equal version is published and never offered,
    and a lower one tells every installation it is ahead of the newest engine.

    Its wording is taken from the add-in's own comment, because that is where
    the failure was paid for.
    """
    assert "Clients would never update, or would be told to downgrade" in engine

    # It must run BEFORE the build. The manifest is public and needs no token,
    # so the check costs seconds — and after the build it costs ten minutes of
    # PyInstaller to learn something that was knowable at the start.
    steps = step_order(engine, "build")
    guard = steps.index("This release must be newer than the one already published")
    build = steps.index("Build")
    assert guard < build, (
        "the published version is checked after the build, which wastes it")


def test_two_releases_at_once_cannot_race_on_the_published_manifest(engine):
    """One file decides what every panel is offered. Two runs finishing minutes
    apart would both rewrite it, and the one that finished LAST would win —
    which is not the same as the one with the higher version. Every check in
    this file would have passed."""
    # PARSED, NOT SEARCHED. `"concurrency:" in engine` passed against a file
    # where the key had been renamed to `x-concurrency:` — the substring was
    # still there, and GitHub would have ignored the block entirely. Caught by
    # mutation; the lesson is that a workflow key is a key, not a word.
    yaml = pytest.importorskip("yaml")
    parsed = yaml.safe_load(engine)

    assert parsed.get("concurrency"), "no concurrency group: two releases can race"
    assert parsed["concurrency"].get("group")
    assert "cancel-in-progress: false" in engine, (
        "a cancelled release can be cancelled between publishing the release "
        "and pointing the manifest at it")


def test_the_manifest_is_written_from_the_engine_and_not_typed(engine):
    """`minimum_extension_version` and `protocol_version` are published so the
    panel can say "this needs a newer extension" BEFORE anything is downloaded.
    Typing them would let the manifest advertise a floor the binary does not
    enforce — the same shape of lie as a tag that disagrees with its version,
    one layer further out."""
    assert "from scrapex.version import VERSION, MINIMUM_EXTENSION_VERSION" in engine
    assert "from scrapex.native import PROTOCOL_VERSION" in engine
    assert '"product": "scrapex-engine"' in engine, (
        "the manifest does not name its product, so the panel cannot tell it "
        "from the add-in's manifest one folder away")


def test_the_manifest_is_pointed_at_the_release_only_after_it_exists(engine):
    """A manifest written before the assets were attached points every
    installation at a download that 404s. This order makes the worst case a
    published release nobody is offered yet, which one re-run fixes."""
    steps = step_order(engine, "publish")
    assert (steps.index("Publish to the public site")
            < steps.index("Point the manifest at it"))


def test_what_the_workflow_writes_is_what_the_panel_can_read(engine, tmp_path):
    """THE ONLY TEST HERE THAT RUNS ANYTHING, and the only one that can catch a
    disagreement between the two halves.

    Every other assertion in this file reads the workflow. But the workflow
    WRITES a manifest and the panel READS one, and they are a hundred lines and
    two languages apart. A renamed field — `installer.size` for
    `installer.bytes`, `min_extension` for `minimum_extension_version` — would
    leave both sides individually correct, both suites green, and the Engines
    page saying "the release manifest could not be read" on the first real
    release, at the one moment nothing can be un-published.

    So the workflow's own Python is lifted OUT OF THE YAML and run, and its
    output is handed to the real reader.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")

    # Lifted rather than copied. A copy would be a second thing to update, and
    # it would pass while the workflow rotted.
    body = engine.split("python - <<'PY' > dist/version.json\n", 1)[1]
    body = body.split("\n          PY\n", 1)[0]
    body = textwrap.dedent(body)

    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "scrapex-engine.exe").write_bytes(b"not really an engine")

    written = subprocess.run(
        [sys.executable, "-c", body], cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ,
             "PUBLIC_REPO": "muhammadbayoumi/mbiX-hub",
             "PUBLISHED_AT": "2026-08-08T00:00:00Z",
             "PYTHONPATH": str(ROOT)})
    assert written.returncode == 0, written.stderr
    manifest = json.loads(written.stdout)

    check = tmp_path / "check.mjs"
    check.write_text(
        # A file:// URL, not a path: node's ESM loader refuses a Windows
        # absolute path outright ("Received protocol 'c:'").
        "import { readVersionManifest } from "
        f"{json.dumps((ROOT / 'extension' / 'releases.js').as_uri())};\n"
        f"const r = readVersionManifest(200, {json.dumps(manifest)});\n"
        "if (r.state !== 'ok') { console.error(r.detail); process.exit(1); }\n"
        "console.log(JSON.stringify(r));\n", encoding="utf-8")

    read = subprocess.run([node, str(check)], capture_output=True, text=True)
    assert read.returncode == 0, (
        f"the panel cannot read what the release workflow writes: {read.stderr}")

    got = json.loads(read.stdout)
    # Not just "readable" — the fields the page actually shows must arrive.
    assert got["version"] == manifest["version"]
    assert got["installer"]["bytes"] == manifest["installer"]["bytes"]
    assert got["minimumExtension"] == manifest["minimum_extension_version"]
    assert got["protocol"] == manifest["protocol_version"]


def test_a_workflow_that_runs_pytest_installs_the_extra_that_provides_it(
        engine, extension):
    """THE DEFECT THIS EXISTS FOR ACTUALLY HAPPENED, on the first real dispatch.

    The engine path installed `.[ui,local,commodity]`, spent five minutes doing
    it, and then died on `No module named pytest` — because pytest lives in the
    `dev` extra and nothing named it. Every assertion in this file passed: the
    step was there, it was ordered correctly, it named the right environment
    variable. It simply could not run.

    So the extra is not typed here. It is READ OUT OF pyproject.toml — whichever
    extra declares pytest is the one a workflow that runs pytest must install —
    and moving pytest to a different extra tomorrow moves this guard with it.
    """
    tomllib = pytest.importorskip("tomllib")
    extras = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["optional-dependencies"]

    providing = sorted(name for name, deps in extras.items()
                       if any(d.split(">=")[0].split("[")[0].strip() == "pytest"
                              for d in deps))
    assert providing, "no extra declares pytest, so nothing here can be checked"

    for label, text in (("engine", engine), ("extension", extension)):
        if "python -m pytest" not in text:
            continue
        install = next((line for line in text.splitlines()
                        if "pip install -e" in line), "")
        assert any(f"{name}" in install for name in providing), (
            f"the {label} path runs pytest but installs {install.strip()!r}, "
            f"which brings in none of {providing} — the step will die on "
            f"'No module named pytest' AFTER the install has spent its minutes")


def test_the_documents_the_store_requires_are_published_with_the_release(engine):
    """THE STORE WILL NOT ACCEPT A LISTING WITHOUT A PUBLIC PRIVACY POLICY URL,
    and the website renders these two rather than keeping its own copy.

    They go out WITH THE RELEASE, and that is what keeps them honest: the
    policy's promises are asserted against the shipped manifest by
    tests/test_the_privacy_policy_is_true.py. A copy published on some other
    schedule would describe a different build, which is the drift those tests
    exist to stop.
    """
    for doc in ("privacy-policy", "support"):
        assert (ROOT / "docs" / f"{doc}.md").is_file()
    assert "for doc in privacy-policy support" in engine
    assert 'put_to_hub "ScrapeX/docs/$doc.md" "docs/$doc.md"' in engine

    # Before the manifest, which is the switch that makes the release visible.
    steps = step_order(engine, "publish")
    assert (steps.index("Publish the documents the store listing links to")
            < steps.index("Point the manifest at it"))


def test_putting_a_file_into_the_hub_is_written_once(engine):
    """Three files go into the hub through the same awkward two-step — read the
    blob's sha, then send the content with it, or without one if the file is
    not there yet. Three copies of that is three places for the create-versus-
    replace branch to be got wrong, and the one that is wrong is the one that
    runs a month from now on a file that happens to exist."""
    assert HELPER.is_file()
    assert engine.count(". .github/workflows/put-to-hub.sh") == 2, (
        "the helper is sourced somewhere other than the two publishing steps")
    assert "gh api" not in engine.split("Publish the documents")[1], (
        "a publishing step calls the API directly instead of the helper")


def test_the_helper_creates_and_replaces_and_survives_the_missing_file(tmp_path):
    """RUN, NOT READ. The create branch depends on `gh` exiting non-zero for a
    file that is not there, under `set -euo pipefail` — which kills a script
    on exactly that. Getting it wrong fails the FIRST release only, when
    nothing has been published yet and there is no sha to find."""
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is not on PATH")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$3" = "--jq" ] && [ "$4" = ".sha" ]; then\n'
        '  if [ -n "${SHA_EXISTS:-}" ]; then echo abc123; exit 0; fi\n'
        '  echo \'{"message":"Not Found"}\' >&2; exit 1\n'
        "fi\n"
        'echo "PUT $*" >&2\n'
        "echo ok\n", encoding="utf-8", newline="\n")
    (bin_dir / "gh").chmod(0o755)
    (tmp_path / "payload.json").write_text('{"hello":1}', encoding="utf-8")

    def run(sha_exists: bool):
        return subprocess.run(
            [bash, "-c",
             "set -euo pipefail\n"
             f". {HELPER.as_posix()}\n"
             'put_to_hub "ScrapeX/json/version.json" payload.json "a message"'],
            cwd=tmp_path, capture_output=True, text=True,
            env={**os.environ,
                 "PATH": f"{bin_dir.as_posix()}{os.pathsep}{os.environ['PATH']}",
                 "PUBLIC_REPO": "muhammadbayoumi/mbiX-hub",
                 **({"SHA_EXISTS": "1"} if sha_exists else {})})

    first = run(sha_exists=False)
    assert first.returncode == 0, (
        f"the FIRST release cannot publish anything: {first.stderr}")
    assert "creating" in first.stdout
    assert "-f sha=" not in first.stderr, (
        "a sha is sent when creating, which the API rejects")

    again = run(sha_exists=True)
    assert again.returncode == 0, again.stderr
    assert "replacing" in again.stdout
    assert "-f sha=abc123" in again.stderr, (
        "no sha is sent when replacing, which the API rejects as a conflict")


def test_the_panel_and_the_workflow_name_the_same_file(engine):
    """Two constants describing one path is one chance to move a single one of
    them, and the symptom would be a panel reading a file nothing writes —
    which reports "no engine has been released yet" forever."""
    import re

    read = re.search(
        r'`https://raw\.githubusercontent\.com/\$\{PUBLIC_REPO\}/main/([^`]+)`',
        (ROOT / "extension" / "releases.js").read_text(encoding="utf-8")).group(1)

    assert f"MANIFEST_PATH: {read}" in engine, (
        f"the panel reads {read} and the workflow writes somewhere else")


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
    steps = step_order(extension, "upload")
    assert steps.index("Upload to the Chrome Web Store") < \
        steps.index("Submit for review")


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
    skipping tests.

    THIS DOCSTRING WAS TRUE AND THE ASSERTION UNDER IT WAS NOT. It required the
    filter it says must not be there, and the workflow carried a comment arguing
    against the very flag it passed — three statements of intent, two of them
    contradicting the code. Nothing caught it because everything agreed with the
    thing that was wrong.

    tests/test_version.py holds the capability ledger the compatibility floor is
    derived from and tests/test_native.py holds PROTOCOL_VERSION. Both are
    marked `extension`, and both decide whether this binary can be spoken to.
    """
    assert 'run: python -m pytest -q\n' in engine, (
        "the release filters its own suite; the two extension-marked files that "
        "guard the ENGINE would be skipped at the moment of shipping")
    assert "SCRAPEX_FULL_MIGRATIONS" in engine, (
        "the release does not replay the real migration stream, so it ships "
        "against the test-only schema template")
