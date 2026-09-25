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
    installs it.

    The job's `if` is pinned whole, not by substring: `in` still passes with `|| true`
    appended or with one `&&` turned into `||`, and either reopens what a clause shut.
    - `workflow_dispatch`: a manual run carries no conclusion, so it is admitted by name.
    - `conclusion == 'success'`: a red `main` publishes nothing.
    - `event == 'push'`: `branches: [main]` matches the run's head branch, and CI also
      runs on `pull_request`, whose head branch can be named `main` too.
    - `head_repository.full_name == github.repository`: a fork's `main` must never reach
      a job that holds `contents: write` and dispatches a release that uses a secret —
      said outright, not left to whichever events CI happens to run on today."""
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
    assert " ".join(guard.split()) == (
        "github.event_name == 'workflow_dispatch' || "
        "(github.event.workflow_run.conclusion == 'success' && "
        "github.event.workflow_run.event == 'push' && "
        "github.event.workflow_run.head_repository.full_name == github.repository)"
    ), guard


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


# ---- and the workflow it dispatches must listen (#1131) ---------------------------
# Saying `-f dry_run=false` out loud is worth something only if release-engine.yml
# reads it. It did not: no line read the input, and its "must be newer" refusal only
# warned on a dispatch -- the path every release this workflow cuts goes through.

NEWER_STEP = "This release must be newer than the one already published"

#: The version the step is asked about. Its manifest answers are chosen around it.
ENGINE = "0.5.0"

#: (event, how GitHub renders `${{ inputs.dry_run }}` in a script for it). A push
#: carries no inputs, and a null renders as the empty string.
TAG_PUSH = ("push", "")
DRY_RUN = ("workflow_dispatch", "true")
RELEASING_DISPATCH = ("workflow_dispatch", "false")

#: Published versions this release is NOT newer than. `0.10.0` is here because it
#: sorts BELOW `0.5.0` as a string, so a comparison that stopped being numeric passes it.
NOT_NEWER = pytest.mark.parametrize(
    "published", ["0.5.0", "0.6.0", "0.10.0"],
    ids=["same-as-published", "below-published", "below-a-two-digit-part"])


def test_a_dry_run_publishes_nothing_and_a_release_still_publishes():
    """THE WHOLE CONDITION, PINNED EXACTLY. The tag alone was the condition, so a
    dispatch on an `engine-v*` tag published whatever `dry_run` said, and the test
    above passed against it. A substring check would pass `inputs.dry_run == true`."""
    release = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    condition = " ".join(str(release["jobs"]["publish"]["if"]).split())

    assert condition == (
        "startsWith(github.ref, 'refs/tags/engine-v') && "
        "(github.event_name == 'push' || inputs.dry_run == false)"), condition


def _run_the_newer_step(tmp_path: Path, event: str, dry_run: str,
                        published: str) -> subprocess.CompletedProcess[str]:
    """RUN, NOT READ: the step's own script, invoked the way GitHub runs `shell: bash`.

    `curl` answers with a manifest naming `published`, and `python` is the interpreter
    running this test. Every `${{ }}` in the script is rendered as GitHub renders it,
    and one this function does not know fails here rather than reaching bash verbatim.
    """
    import os
    import shutil

    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is not on PATH, so the step's script cannot be run")

    release = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    found = [s for s in release["jobs"]["build"]["steps"] if s.get("name") == NEWER_STEP]
    assert len(found) == 1, f"{len(found)} steps are named {NEWER_STEP!r}, not one"
    assert found[0].get("shell") == "bash", found[0].get("shell")

    rendered = {"github.event_name": event, "inputs.dry_run": dry_run}
    expression = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")
    script = found[0]["run"]
    unknown = set(expression.findall(script)) - set(rendered)
    assert not unknown, f"the step now reads {sorted(unknown)}; render each one here"
    script = expression.sub(lambda m: rendered[m.group(1)], script)

    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in {
        "curl": f"cat <<'JSON'\n{{\"version\": \"{published}\"}}\nJSON\n",
        "python": f'exec "{Path(sys.executable).as_posix()}" "$@"\n',
    }.items():
        (stubs / name).write_text(f"#!/usr/bin/env bash\n{body}",
                                  encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    step = tmp_path / "step.sh"
    step.write_text(script, encoding="utf-8", newline="\n")

    return subprocess.run(
        [bash, "--noprofile", "--norc", "-eo", "pipefail", step.as_posix()],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
        env={**os.environ, **release["env"], "ENGINE_VERSION": ENGINE,
             "PATH": f"{stubs.as_posix()}{os.pathsep}{os.environ.get('PATH', '')}"})


@NOT_NEWER
@pytest.mark.parametrize("event,dry_run", [TAG_PUSH, RELEASING_DISPATCH],
                         ids=["tag-push", "dispatch-dry_run-false"])
def test_a_release_that_is_not_newer_is_refused_however_it_started(
        tmp_path, event, dry_run, published):
    """`dispatch-dry_run-false` IS HOW EVERY RELEASE STARTS, because this workflow
    dispatches rather than relying on its tag push. That path exited 0 with a warning,
    so a `VERSION` that went backwards on `main` would have been published over a newer
    release, and every installation pointed at it."""
    proc = _run_the_newer_step(tmp_path, event, dry_run, published)

    assert proc.returncode == 1, (
        f"{event} with dry_run={dry_run!r} let {ENGINE} through over the published "
        f"{published}. stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert f"::error::{ENGINE} is not newer than the published {published}." in proc.stdout
    assert "::warning::" not in proc.stdout, proc.stdout


@NOT_NEWER
def test_a_dry_run_that_is_not_newer_warns_and_goes_on(tmp_path, published):
    """A DRY RUN PUBLISHES NOTHING, so refusing it would only stop the build being
    checked from the day a version is released until the next bump."""
    proc = _run_the_newer_step(tmp_path, *DRY_RUN, published)

    assert proc.returncode == 0, (
        f"a dry run was refused over {published}: stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}")
    assert f"::warning::{ENGINE} is not newer than the published" in proc.stdout
    assert "this dry run continues" in proc.stdout, proc.stdout
    assert "::error::" not in proc.stdout, proc.stdout


@pytest.mark.parametrize("event,dry_run", [TAG_PUSH, DRY_RUN, RELEASING_DISPATCH],
                         ids=["tag-push", "dispatch-dry_run-true", "dispatch-dry_run-false"])
def test_a_newer_release_passes_however_it_started(tmp_path, event, dry_run):
    """The refusal must not become the only thing the step does: a newer version passes
    on every path, or no release goes out at all."""
    proc = _run_the_newer_step(tmp_path, event, dry_run, published="0.4.9")

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "published says 0.4.9" in proc.stdout, "the stubbed manifest was never read"
    assert "this release is newer" in proc.stdout, proc.stdout
    assert "::error::" not in proc.stdout and "::warning::" not in proc.stdout
