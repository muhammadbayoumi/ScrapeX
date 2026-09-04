"""R-87's mechanism, held to the four things that make it a mechanism.

He chose a workflow over a guard — «واعمل workflow يقطع الوسم تلقائيا» — so the thing
that can now go wrong is not forgetting to release. It is releasing the wrong commit,
releasing nothing while appearing to work, or a version this file cannot read.

Every assertion below is one of those, and the last is the only one that reads the
workflow's own extraction expression against the real `scrapex/version.py` rather than
looking for a string in a YAML file.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scrapex.version import VERSION

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tag-the-release.yml"
RELEASE = ROOT / ".github" / "workflows" / "release-engine.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW.is_file(), f"{WORKFLOW} is missing, so R-87 has no mechanism"
    # `on` is parsed by PyYAML as the boolean True — YAML 1.1's reserved words, which
    # is why every reader of a GitHub workflow trips on it once.
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(workflow) -> list[dict]:
    return workflow["jobs"]["tag"]["steps"]


def test_it_waits_for_ci_and_never_fires_on_a_bare_push(workflow):
    """IT TAGS WHAT PASSED. A `push` trigger would tag the commit that had just landed,
    before anything ran against it — and a release then repeats that lie to whoever
    installs it."""
    triggers = workflow[True]

    assert "push" not in triggers, (
        "it fires on push, so it can tag a commit nothing has tested yet")
    assert triggers["workflow_run"]["workflows"] == ["CI"], triggers["workflow_run"]
    assert triggers["workflow_run"]["branches"] == ["main"]
    assert "workflow_dispatch" in triggers, (
        "there is no way to release a version that was already sitting unreleased")

    guard = workflow["jobs"]["tag"]["if"]
    assert "workflow_run.conclusion == 'success'" in guard, guard
    assert "workflow_dispatch" in guard, (
        "a manual dispatch carries no conclusion, so it must be admitted explicitly")


def test_it_checks_out_the_commit_ci_ran_on(steps):
    """`github.sha` is whatever `main` is NOW, which on a busy afternoon is not the
    commit that was tested. Five sessions produced seven pull requests in one afternoon
    once (`ORCHESTRATION.md`), so this is not hypothetical."""
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))

    ref = checkout["with"]["ref"]
    assert "workflow_run.head_sha" in ref, ref
    assert checkout["with"]["fetch-tags"] is True, "it cannot see whether a tag exists"


def test_it_asks_the_remote_whether_the_version_is_already_released(steps):
    """The checkout fetches tags, but a tag created by a run that started seconds
    earlier is not in that fetch — `concurrency` serialises those runs, it does not
    prevent them."""
    body = "\n".join(str(s.get("run", "")) for s in steps)

    assert "git ls-remote" in body and "refs/tags/" in body, (
        "it decides whether to cut a tag from a local list, which can be stale")


def test_it_says_dry_run_false_out_loud(steps):
    """THE DEFAULT ON THE OTHER WORKFLOW IS `true`, so omitting the input would build a
    release and publish nothing — a mechanism that appears to work and ships nothing."""
    release = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    default = release[True]["workflow_dispatch"]["inputs"]["dry_run"]["default"]

    assert default is True, (
        "release-engine.yml's dry_run no longer defaults to true; this test and the "
        "comment in tag-the-release.yml both describe a world that changed")

    dispatch = next(s for s in steps if "gh workflow run" in str(s.get("run", "")))
    assert "-f dry_run=false" in dispatch["run"], dispatch["run"]
    assert "release-engine.yml" in dispatch["run"]


def test_it_proves_the_release_started_rather_than_assuming_it(steps):
    """A tag pushed with GITHUB_TOKEN does not start another workflow, which is why the
    dispatch exists at all. If dispatching is ever restricted the same way, the dispatch
    still succeeds and nothing runs — `R-87` satisfied on paper by a tag nobody built.
    That is `OP-124`'s defect exactly: built, mounted, doorless."""
    checker = [s for s in steps if "gh run list" in str(s.get("run", ""))]

    assert checker, "nothing checks that the release actually started"
    body = checker[-1]["run"]
    assert "::error::" in body, "it fails quietly, which is the one thing it must not do"
    assert "exit 1" in body


def test_the_expression_it_reads_the_version_with_actually_reads_it():
    """THE ONLY ASSERTION HERE THAT IS NOT ABOUT A STRING IN A YAML FILE. The workflow
    extracts `VERSION` with a regex in a `python -c`; if that expression is wrong the
    workflow fails at the moment of releasing, which is the worst moment to find out.
    It is run here, against the real file, and compared with the imported value."""
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r'version=\$\(python -c "(?P<code>.+?)"\)', text)
    assert match, "the version-reading step is no longer a `python -c` this can extract"

    code = match.group("code").replace('\\"', '"')
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                          capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == VERSION, (
        f"the workflow would tag engine-v{proc.stdout.strip()} while "
        f"scrapex/version.py says {VERSION}")
