"""One version, its mirrors, and the ledger that says which version has what.

The failure these tests exist to prevent is not a crash. It is a question the
product could not answer: "does the thing in front of me have X?" Twice in two
days the owner asked for a feature that had already shipped — the crawl pace
(`c63ec21`, rendered only on the display-only web page) and crawling several
sites at once (`63dc24b` in the engine, `76a4b14` in the panel eleven commits
later). Both times the version string said 0.1.0, which it had said for 130
commits, and so said nothing at all.

So: a ledger that cannot hold a capability without a version, and a baseline
that cannot let the capability set move while the number stands still.

TWO NUMBERS SINCE 2026-08-05, not one. The engine's version lives here and is
mirrored into `pyproject.toml`, which cannot import Python; the extension's
lives in `extension/manifest.json`, which is the only thing Chrome reads. They
are allowed to differ, and they will: the two ship down separate release paths,
one reviewed by Google and pushed automatically, one published to GitHub and
installed on acceptance. What refuses an incompatible pair is the protocol and
the capability ledger — never a comparison of the two stamps.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from scrapex import settings as settings_module
from scrapex import version
from scrapex.version import (
    CAPABILITIES,
    DEPLOYED,
    MINIMUM_EXTENSION_VERSION,
    UPDATE_INSTRUCTIONS,
    VERSION,
    Capability,
    Surface,
    capability_problem,
    export_vectors,
    is_older,
    missing_capabilities,
    parse_version,
    version_report,
)

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
MANIFEST = ROOT / "extension" / "manifest.json"
PYPROJECT = ROOT / "pyproject.toml"
PANEL_SOURCES = (ROOT / "extension" / "app.html", ROOT / "extension" / "app.js")


# ---- ONE definition, and the copies that may not drift from it ---------------

def test_the_package_reports_the_authority_and_does_not_restate_it():
    import scrapex

    assert scrapex.__version__ == VERSION
    assert "__version__ = " not in (ROOT / "scrapex" / "__init__.py").read_text(
        encoding="utf-8"), (
        "scrapex/__init__.py typed the version again instead of importing it; two "
        "copies in the same package is the drift this whole file is about")


def test_the_installer_carries_the_same_number():
    """setuptools cannot import the package to ask, so pyproject holds a copy."""
    found = re.search(r'^version = "([^"]+)"', PYPROJECT.read_text(encoding="utf-8"),
                      flags=re.M)
    assert found, "pyproject.toml no longer declares a version"
    assert found.group(1) == VERSION, (
        f"pyproject.toml says {found.group(1)} and scrapex/version.py says {VERSION}; "
        "bump both or neither")


def test_the_extension_carries_its_own_number_and_may_differ():
    """THE ASSUMPTION THAT EXPIRED, and the reason this test now asserts the
    opposite of what it used to.

    It read: "the extension and the engine ship from one checkout and carry one
    number", and enforced `manifest["version"] == VERSION`. That was true while
    both shipped together. It stopped being true on 2026-08-05, when the owner
    settled two release paths (PLATFORM-PLAN Decision 21): the extension is
    tagged, uploaded to the Chrome Web Store, REVIEWED by Google, and then
    pushed to every user automatically — while the engine is tagged separately,
    published to GitHub Releases, reviewed by nobody, and installed only when
    the owner accepts.

    Chrome can therefore update the extension tonight while a user's engine is
    last month's. Enforcing one number does not prevent that; it only prevents
    the repository from DESCRIBING it, and a version that cannot describe what
    is running is the exact failure this whole file was written about.

    What replaces the equality is not nothing. Both must still be real versions,
    the manifest is still the only thing Chrome reads, and the refusal rules
    (`capability_problem` and its JS twin) already take the two numbers
    separately and name both in every sentence they produce. The gate was never
    the equality — it is the protocol and the ledger (Decision, 2026-08-05).
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    parse_version(manifest["version"])          # raises if it is not MAJOR.MINOR.PATCH
    parse_version(VERSION)

    assert manifest["version"] != "" and VERSION != ""


# ---- the two numbers, and which one is derived -------------------------------

def test_the_gate_is_derived_from_the_ledger_and_never_typed():
    panel_versions = [c.since for c in CAPABILITIES if Surface.PANEL in c.surfaces]
    assert MINIMUM_EXTENSION_VERSION == max(panel_versions, key=parse_version)
    assert not is_older(VERSION, MINIMUM_EXTENSION_VERSION), (
        "the minimum extension is newer than the release that ships it")


def test_an_engine_only_capability_does_not_make_the_owner_reload_a_browser():
    """The distinction that keeps the gate honest, and the reason `surfaces`
    exists at all: what the engine does alone costs the extension nothing.

    Same reasoning as the payload contract's additive changes being free — a
    gate that fires for every change is a gate people learn to click past.
    """
    engine_only = [c for c in CAPABILITIES if Surface.PANEL not in c.surfaces]
    assert engine_only, "the ledger no longer has an engine-only capability to prove it"
    doctored = tuple(
        replace(c, since="9.9.9") if c in engine_only else c for c in CAPABILITIES)
    raised = max((c.since for c in doctored if Surface.PANEL in c.surfaces),
                 key=parse_version)
    assert raised == MINIMUM_EXTENSION_VERSION, (
        "an engine-only capability moved the minimum extension version")


def test_a_capability_cannot_be_written_without_the_version_that_introduced_it():
    """The import-time refusal, and the whole mechanism in one line.

    `GENERATION_OF_VERSION[PAYLOAD_VERSION]` does this for a payload bump that
    forgets to declare its kind. Here the required field does it: a capability
    appended without `since` is a TypeError before anything can run.
    """
    with pytest.raises(TypeError, match="since"):
        Capability(key="orphan", summary="no version", surfaces=(Surface.ENGINE,),
                   panel_control="", settings=(), commit="abc1234")


def test_a_capability_from_the_future_stops_the_build(monkeypatch):
    monkeypatch.setattr(version, "CAPABILITIES", CAPABILITIES + (
        Capability(key="not_yet", since="9.9.9", summary="unbuilt",
                   surfaces=(Surface.ENGINE,), panel_control="", settings=(),
                   commit=""),))
    monkeypatch.setattr(version, "CAPABILITY_BY_KEY",
                        {c.key: c for c in version.CAPABILITIES})
    with pytest.raises(ValueError, match="newer than this build"):
        version._validate_ledger()


def test_a_capability_the_panel_runs_must_name_the_control_it_runs_from(monkeypatch):
    monkeypatch.setattr(version, "CAPABILITIES", CAPABILITIES + (
        Capability(key="invisible", since=VERSION, summary="unreachable",
                   surfaces=(Surface.PANEL,), panel_control="", settings=(),
                   commit=""),))
    monkeypatch.setattr(version, "CAPABILITY_BY_KEY",
                        {c.key: c for c in version.CAPABILITIES})
    with pytest.raises(ValueError, match="cannot reach from the side panel"):
        version._validate_ledger()


# ---- the version association a new feature cannot ship without ---------------

def test_every_panel_capability_has_its_control_in_the_panel():
    """INCIDENT TWO, caught at build time rather than by the owner.

    `crawl_parallel_sources` shipped in the engine at 63dc24b and had no field
    in the panel until 76a4b14. The engine queued two jobs at once and the owner
    asked why. A capability that claims the panel executes it and names a
    control the panel does not contain fails here — before the release, not
    after the question.
    """
    panel = "\n".join(path.read_text(encoding="utf-8") for path in PANEL_SOURCES)
    for capability in CAPABILITIES:
        if Surface.PANEL not in capability.surfaces:
            continue
        assert capability.panel_control in panel, (
            f"capability {capability.key!r} says the panel executes it from "
            f"{capability.panel_control!r}, and neither extension/app.html nor "
            "extension/app.js contains that. A capability the owner cannot reach "
            "from the side panel is a capability he does not have (SR-10)")


def test_every_crawl_setting_the_engine_accepts_belongs_to_a_capability():
    """The other half of incident two: the engine grew the knob first.

    Scoped to the crawl family on purpose. That is where the incident happened
    and where the panel is the execution surface; the excel/google/funnel
    settings are configured on their own web pages, and moving them is section 2
    work this issue does not open.
    """
    claimed = {key for capability in CAPABILITIES for key in capability.settings}
    crawl_settings = {key for key in settings_module.SETTINGS if key.startswith("crawl_")}
    unclaimed = crawl_settings - claimed
    assert not unclaimed, (
        f"{sorted(unclaimed)} can be set on the engine and belong to no capability, "
        "so nothing says which version introduced them and nothing checks the panel "
        "can reach them. Add them to a capability in scrapex/version.py")


def test_every_setting_a_capability_claims_is_a_setting_the_engine_has():
    for capability in CAPABILITIES:
        for key in capability.settings:
            assert key in settings_module.SETTINGS, (
                f"capability {capability.key!r} claims setting {key!r}, which "
                "scrapex.settings.SETTINGS does not have")


def test_the_history_a_capability_cites_is_history_that_exists():
    """Do not invent history. Every hash in the ledger is checked against git.

    Skipped on a shallow clone (CI checks out depth 1), because a hash missing
    from a truncated history proves nothing at all.
    """
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    if git("rev-parse", "--is-shallow-repository").stdout.strip() != "false":
        pytest.skip("shallow clone: the cited commits may legitimately be absent")
    for capability in CAPABILITIES:
        if not capability.commit:
            continue
        found = git("cat-file", "-t", capability.commit)
        assert found.returncode == 0 and found.stdout.strip() == "commit", (
            f"capability {capability.key!r} cites {capability.commit}, which is not a "
            "commit in this repository. The ledger's evidence is read out of git log, "
            "never remembered")


# ---- the compatibility rule --------------------------------------------------

def test_a_current_pair_refuses_nothing():
    assert capability_problem("crawl_parallel_sources", extension_version=VERSION,
                              engine_version=VERSION, deployed=DEPLOYED) == ""


def test_a_stale_extension_is_refused_with_both_versions_and_the_way_out():
    problem = capability_problem("crawl_parallel_sources", extension_version="0.1.0",
                                 engine_version=VERSION, deployed=DEPLOYED)
    assert "needs ScrapeX extension 0.2.0" in problem
    assert "this extension is 0.1.0" in problem, "the installed version is missing"
    assert f"the engine is {VERSION}" in problem, "the other side's version is missing"
    assert "chrome://extensions" in problem, "the remedy is missing"


def test_a_stale_engine_is_refused_and_says_something_different():
    """The two directions need different words. A stale extension is fixed by a
    reload; a stale engine is not fixed by touching the extension at all, and a
    message carrying one bare number cannot tell the owner which he is looking
    at — the same reasoning as the payload contract's newer/older refusals."""
    without = {k: v for k, v in DEPLOYED.items() if k != "crawl_parallel_sources"}
    problem = capability_problem("crawl_parallel_sources", extension_version=VERSION,
                                 engine_version="0.1.0", deployed=without)
    assert "not deployed by this ScrapeX engine (0.1.0)" in problem
    assert f"this extension is {VERSION}" in problem
    assert "Update the engine" in problem
    assert "chrome://extensions" not in problem, (
        "a stale engine is not fixed by reloading the extension; saying so sends "
        "the owner after the wrong remedy")


def test_an_engine_that_cannot_say_is_not_an_engine_that_said_no():
    """Silence is not a refusal — the care engine.js already takes with an absent
    protocol_version, kept here."""
    problem = capability_problem("crawl_parallel_sources", extension_version=VERSION,
                                 engine_version="0.1.0", deployed=None)
    assert "too old to say which features it deploys" in problem
    assert "not deployed" not in problem
    assert "0.1.0" in problem and VERSION in problem


def test_a_version_that_is_not_a_version_is_refused_rather_than_treated_as_old():
    """Answering an unreadable number with "everything is missing" would send the
    owner to reload an extension that is perfectly current."""
    for bad in ("", "0.2", "0.2.0.1", "v0.2.0", "0.2.x"):
        with pytest.raises(ValueError, match="not a ScrapeX version"):
            parse_version(bad)


def test_ordering_is_numeric_and_not_alphabetical():
    assert is_older("0.9.0", "0.10.0"), "0.10.0 sorts before 0.9.0 as text"
    assert is_older("1.0.0", "1.0.1") and not is_older("1.0.1", "1.0.0")
    assert not is_older(VERSION, VERSION)


# ---- the report the notification is built from -------------------------------

def test_the_report_names_whose_version_every_number_is():
    report = version_report("0.1.0")
    assert report["engine_version"] == VERSION
    assert report["latest_extension_version"] == VERSION
    assert report["minimum_extension_version"] == MINIMUM_EXTENSION_VERSION
    assert report["installed_extension_version"] == "0.1.0"
    assert report["outdated"] is True
    assert report["update_instructions"] == UPDATE_INSTRUCTIONS
    assert {item["key"] for item in report["missing"]} == {
        c.key for c in CAPABILITIES if Surface.PANEL in c.surfaces}
    # A bare "version" key is exactly the defect: a number with no owner.
    assert "version" not in report


def test_latest_says_where_latest_came_from():
    """There is no remote update server, and the wire must not imply one."""
    report = version_report()
    assert "no remote update server" in report["latest_source"]
    assert report["outdated"] is False and report["missing"] == []
    assert report["installed_extension_version"] is None


def test_a_current_extension_is_missing_nothing():
    assert missing_capabilities(VERSION) == ()
    assert version_report(VERSION)["outdated"] is False


# ---- the frozen vectors both languages are pinned to -------------------------

def test_the_committed_vectors_are_what_python_produces():
    committed = json.loads((CONTRACTS / "version-vectors.json").read_text(encoding="utf-8"))
    assert committed == export_vectors(), (
        "contracts/version-vectors.json is stale — run: "
        "python -m scrapex.cli export-version")


def test_every_vector_case_is_a_different_verdict():
    """A vector set that only covered the happy path would pin the one answer
    nobody needs to read."""
    problems = [case["problem"] for case in export_vectors()["cases"]]
    assert problems.count("") == 2, "the two passing cases moved"
    assert len(set(problems)) == len(problems) - 1, "two cases produce the same words"


def test_the_javascript_copy_reads_the_same_vectors():
    """The JS side is asserted by extension/tests/version-compat.test.mjs, which
    CI runs under node. This only proves it is still pointed at this file — a
    guard nobody has watched fail is a guard nobody knows is wired up."""
    test_js = (ROOT / "extension" / "tests" / "version-compat.test.mjs").read_text(
        encoding="utf-8")
    assert "version-vectors.json" in test_js
    assert "capabilityProblem" in test_js and "../version.js" in test_js


# ---- the baseline: the capability set cannot move while VERSION stands still --

def test_the_baseline_describes_exactly_what_this_version_deploys():
    """ISSUE 32 §1.1, made mechanical: the number moves when the behaviour does.

    Without this, adding a capability costs nothing — write it, give it the
    current `since`, and every other check still passes while the release it
    supposedly shipped in never moved. The baseline is what refuses that.
    """
    baseline = json.loads((CONTRACTS / "capability-baseline.json").read_text(
        encoding="utf-8"))
    assert baseline["version"] == VERSION, (
        f"contracts/capability-baseline.json describes {baseline['version']} and this "
        f"build is {VERSION} — write the new baseline in the same commit: "
        "python -m scrapex.cli export-version")
    assert baseline["capabilities"] == {
        c.key: c.since for c in version.CAPABILITIES}, (
        f"what version {VERSION} deploys changed while {VERSION} stood still. A "
        "functional change gets its own version (issue 32 §1.1): bump "
        "scrapex/version.py:VERSION, then regenerate the baseline")
    assert baseline["minimum_extension_version"] == MINIMUM_EXTENSION_VERSION


def test_the_guard_notices_a_capability_added_without_a_bump(monkeypatch):
    """The test above must be able to FAIL. Add a capability, leave VERSION where
    it is, and the build has to stop."""
    monkeypatch.setattr(version, "CAPABILITIES", CAPABILITIES + (
        Capability(key="smuggled_in", since=VERSION, summary="landed quietly",
                   surfaces=(Surface.ENGINE,), panel_control="", settings=(),
                   commit=""),))
    with pytest.raises(AssertionError, match="stood still"):
        test_the_baseline_describes_exactly_what_this_version_deploys()


def test_the_baseline_is_never_rewritten_for_the_version_it_describes(tmp_path, monkeypatch):
    """A baseline that regenerated itself would guard nothing — the same trap the
    header baseline avoids (tests/test_payload_compat.py)."""
    from scrapex import cli

    monkeypatch.setattr(cli, "CONTRACTS_DIR", tmp_path)
    path = tmp_path / "capability-baseline.json"

    assert "wrote" in cli._write_capability_baseline()
    first = path.read_text(encoding="utf-8")

    # Someone adds a capability and re-runs the exporter hoping for a clean build.
    doctored = json.loads(first)
    doctored["capabilities"]["smuggled_in"] = VERSION
    path.write_text(json.dumps(doctored, indent=2) + "\n", encoding="utf-8")

    assert "kept" in cli._write_capability_baseline()
    assert json.loads(path.read_text(encoding="utf-8")) == doctored, (
        "the exporter overwrote a baseline for its own version; the floor would "
        "move with every change and catch nothing")

    # A version this file has never described DOES get written.
    doctored["version"] = "0.0.1"
    path.write_text(json.dumps(doctored, indent=2) + "\n", encoding="utf-8")
    assert "wrote" in cli._write_capability_baseline()
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(first)


# ---- the readable form of the ledger -----------------------------------------

def test_the_changelog_is_generated_and_not_stale():
    """INCIDENT ONE, answered without reading Python: which version has what.

    Hand-written beside a machine-readable ledger it would be a second truth
    that drifts, and a stale answer to "has this shipped?" is worse than none.
    """
    from scrapex import cli

    committed = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert committed == cli._render_changelog(), (
        "CHANGELOG.md is stale — run: python -m scrapex.cli export-version")


def test_the_changelog_carries_the_evidence_for_the_two_incidents():
    committed = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "c63ec21" in committed, "the crawl pace lost the commit that built it"
    assert "63dc24b" in committed, "crawling several sites at once lost its commit"
    assert f"## {VERSION}" in committed


# ---- the two release paths, and the line that quietly welded them together ----

def test_no_capability_dates_itself_by_the_version_it_is_read_in():
    """THE DEFECT NO TEST COULD SEE, because it made every comparison true.

    All seven capabilities recorded `since=VERSION`. MINIMUM_EXTENSION_VERSION is
    the newest `since` among the panel's capabilities, so the floor was VERSION —
    always, however it was written. MEASURED: move the engine alone to 0.4.0 and
    the floor became 0.4.0, so the engine declared the extension sitting in the
    Chrome Web Store — 0.2.0, reviewed by Google, installed on every machine —
    too old to talk to. Every engine release did that, to an extension that had
    not changed, which is the exact opposite of PLATFORM-PLAN Decision 21.

    Nothing caught it because with `since=VERSION` the floor and the head move
    together and every assertion about them stays true. The defect is in the
    SOURCE, so this is the one guard that has to read the source.

    A capability's `since` is the version it was INTRODUCED in. It is written as
    a literal, once, and never moves again.
    """
    # Comments stripped first: the rule is explained at length beside the
    # constant it protects, and the explanation necessarily quotes the mistake.
    # A guard that reads its own documentation as a violation is a guard that
    # forces the documentation out.
    source = "\n".join(
        line for line in (ROOT / "scrapex" / "version.py").read_text(
            encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#"))

    assert "since=VERSION" not in source, (
        "a capability dates itself by whatever VERSION happens to be, so the "
        "minimum extension version follows the engine's head and every engine "
        "release orphans the published extension")


def test_an_engine_release_does_not_raise_the_floor_under_the_published_extension():
    """The same claim, computed rather than read.

    The floor is derived from the ledger, so a hypothetical newer engine is
    simulated by asking what the floor WOULD be — no monkeypatching of a module
    whose import runs a validator.
    """
    from scrapex.version import CAPABILITIES, MINIMUM_EXTENSION_VERSION, Surface, _newest

    panel_sinces = tuple(c.since for c in CAPABILITIES if Surface.PANEL in c.surfaces)
    assert panel_sinces, "the panel executes no capability at all"
    assert _newest(panel_sinces) == MINIMUM_EXTENSION_VERSION

    # Every `since` is a literal, so the floor is a fact about what the panel
    # NEEDS and not about which engine is reading it. Tagging engine-v0.4.0
    # changes VERSION and nothing here.
    assert all(s != "" for s in panel_sinces)
    assert MINIMUM_EXTENSION_VERSION == "0.2.0", (
        "the floor moved without a capability being added; if that was "
        "deliberate, the published extension must be republished first")


def test_the_extension_may_be_tagged_for_the_store_on_its_own():
    """PLATFORM-PLAN Decision 21: two release paths, neither triggering the other.

    The JavaScript suite asserted `manifest.version === VECTORS.version`, and
    VECTORS.version is the ENGINE's number. Bumping only extension/manifest.json
    — which is exactly what a Chrome Web Store release is — failed with
    `actual: '0.3.0', expected: '0.2.0'`. Python had already dropped that
    equality (see test_the_extension_carries_its_own_number_and_may_differ); the
    JavaScript copy never followed, so CI refused the release path the plan is
    built on.

    This asserts the JS side no longer welds them, from the Python side, because
    the Python suite is the one that runs on every change.
    """
    # Comments stripped, for the same reason: the replacement records the
    # equality it replaced, verbatim, so the next reader knows what expired.
    js = "\n".join(
        line for line in (ROOT / "extension" / "tests" /
                          "version-compat.test.mjs").read_text(
            encoding="utf-8").splitlines()
        if not line.lstrip().startswith("//"))

    assert "assert.equal(manifest.version, VECTORS.version)" not in js, (
        "the extension's manifest is pinned to the engine's version again; a "
        "store release with the engine untouched will fail CI")
    assert "minimum_extension_version" in js, (
        "the manifest is no longer checked against the floor the engine will "
        "talk to, so a build the engine would refuse could be uploaded")
