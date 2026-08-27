"""The two guards `R-64` asked for, and this file drives the local one for real.

`OP-33` (migrations 0007/0008, 2026-08-21) and `OP-84` (0011/0012, 2026-08-27) are the same
fault twice: the owner's warehouse ran ahead of anything `main` could build, and it only
became visible when the released engine was double-clicked and refused. `OP-33` was closed by
a merge rather than by a guard, which is precisely why it returned.

Two guards, and they cover different blind spots:

* **CI** — `release-engine.yml` refuses a tag while any unmerged branch has NUMBERED a
  migration the release does not carry. It is the only thing that can see across branches.
  `migration-authority` in `ci.yml` cannot: it reads the diff of the branch it runs on.
* **This machine** — `.githooks/pre-push` refuses to push an `engine-v*` tag while the local
  warehouse is at a version this code cannot open. CI cannot see a developer's machine.

**The hook is EXECUTED here, not read.** A test that greps a shell script for the word
"refuse" passes against a script that refuses nothing, which is the failure
`tests/test_the_documents_cite_what_they_claim.py` was built for one layer up.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-push"
WORKFLOW = ROOT / ".github" / "workflows" / "release-engine.yml"

#: The step name is asserted verbatim rather than by keyword. A renamed step is a step
#: that may have been replaced by something weaker, and that is worth failing on.
CI_STEP = "No unmerged branch may hold a migration this release does not carry"

HEALTHY = '{"engine": {"ok": true, "status": "Healthy", "schema_version": 12}}'
AHEAD = ('{"engine": {"ok": false, "status": "Needs a newer ScrapeX", '
         '"action": "This database was written by a later version (schema v12; this build '
         'reads v10).", "schema_version": 12}}')


def _bash() -> str:
    """Git Bash on Windows, /bin/bash on a runner. NOT skipped when absent.

    A skip here would report green on the machine that most needs the check -- the owner's,
    which is the only place the hook can ever run. `git` implies a bash on Windows, so an
    absent bash is a broken environment and says so.
    """
    found = shutil.which("bash")
    assert found, ("no bash on PATH, so the pre-push hook cannot be exercised. This is an "
                   "environment fault, not a reason to pass: the hook is the half of R-64 "
                   "that runs on a developer machine.")
    return found


def _run(tmp_path: pathlib.Path, refs: str, *, probe: str | None,
         probe_exit: int = 0) -> subprocess.CompletedProcess[str]:
    """Run the hook with a stubbed `python` and `refs` on stdin.

    `probe=None` means the stub is still installed but records nothing to print, so a test
    can prove the hook never asked -- the marker file is the evidence, not the exit code.
    """
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    marker = tmp_path / "asked"
    stub = stub_dir / "python"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "" >> "{marker.as_posix()}"\n'
        + (f"cat <<'JSON'\n{probe}\nJSON\n" if probe is not None else "")
        + f"exit {probe_exit}\n",
        encoding="utf-8", newline="\n")
    stub.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir.as_posix()}{os.pathsep}{env.get('PATH', '')}"
    proc = subprocess.run(
        [_bash(), HOOK.as_posix()], input=refs, capture_output=True, text=True,
        env=env, cwd=ROOT, timeout=120)
    proc.asked = marker.exists()  # type: ignore[attr-defined]
    return proc


def test_the_hook_exists_and_is_executable():
    assert HOOK.is_file(), f"{HOOK} is missing, so R-64's local half does not exist"
    listing = subprocess.run(
        ["git", "ls-files", "-s", ".githooks/pre-push"], cwd=ROOT,
        capture_output=True, text=True, check=True).stdout
    assert listing.startswith("100755"), (
        f"the hook is committed as {listing.split()[0] if listing else 'nothing'}, not 100755. "
        "git will not run a hook it does not consider executable, and the mode is what "
        "carries across a fresh clone -- a chmod on one machine helps nobody else.")


def test_it_refuses_an_engine_tag_while_the_warehouse_is_ahead(tmp_path):
    proc = _run(tmp_path, "refs/tags/engine-v0.5.0 abc123 refs/tags/engine-v0.5.0 000000\n",
                probe=AHEAD)
    assert proc.returncode != 0, (
        "the hook let an engine tag through while the warehouse reported ok=false. "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert "REFUSED" in proc.stderr
    assert "engine-v0.5.0" in proc.stderr, "the refusal must name the tag it stopped"
    assert "R-64" in proc.stderr, "the refusal must name the ruling, so it can be argued with"


def test_it_passes_an_engine_tag_when_the_warehouse_opens(tmp_path):
    proc = _run(tmp_path, "refs/tags/engine-v0.5.0 abc123 refs/tags/engine-v0.5.0 000000\n",
                probe=HEALTHY)
    assert proc.returncode == 0, (
        "the hook refused a healthy warehouse, which would make every release need "
        f"--no-verify and teach the owner to ignore it. stderr={proc.stderr!r}")
    assert proc.asked, "it answered without asking, so the pass means nothing"


def test_a_broken_probe_refuses_rather_than_passing(tmp_path):
    """Silence must not read as a pass.

    `OP-20` is the measured cost of the opposite: a guard whose failure looked like noise
    went eight days unread. A probe that cannot answer is not an answer.
    """
    proc = _run(tmp_path, "refs/tags/engine-v0.5.0 abc123 refs/tags/engine-v0.5.0 000000\n",
                probe=None, probe_exit=1)
    assert proc.returncode != 0, (
        "the probe failed and the hook passed the tag anyway, so a broken `database-status` "
        "silently disables this guard")
    assert "cannot speak" in proc.stderr


@pytest.mark.parametrize("ref", [
    "refs/heads/main",
    "refs/heads/feat/anything",
    "refs/tags/scrapex-v0.3.3",
])
def test_it_says_nothing_about_anything_but_an_engine_tag(tmp_path, ref):
    """And it must not even ASK, because the probe opens a 1.2 GB database.

    A hook that costs a database open on every `git push` is a hook somebody disables.
    """
    proc = _run(tmp_path, f"{ref} abc123 {ref} 000000\n", probe=AHEAD)
    assert proc.returncode == 0, f"{ref} was blocked by a guard about engine tags"
    assert not proc.asked, (
        f"pushing {ref} ran `database-status`. Every push would pay for a check that "
        "cannot apply to it.")


def test_it_finds_the_engine_tag_among_several_refs(tmp_path):
    """`git push --tags` hands the hook every ref at once, one per line.

    A hook that only reads the first line passes whenever the engine tag is not first, and
    `git push --tags` orders them however it likes.
    """
    refs = ("refs/heads/main a1 refs/heads/main b1\n"
            "refs/tags/scrapex-v0.3.3 a2 refs/tags/scrapex-v0.3.3 b2\n"
            "refs/tags/engine-v0.5.0 a3 refs/tags/engine-v0.5.0 b3\n")
    proc = _run(tmp_path, refs, probe=AHEAD)
    assert proc.returncode != 0, (
        "the engine tag was third of three and the hook did not see it")
    assert "engine-v0.5.0" in proc.stderr


def test_the_ci_half_exists_and_runs_before_the_build():
    """The half that cannot be skipped, and the ordering is the point.

    A guard placed after the build still refuses, and costs a twenty-minute PyInstaller run
    to say what it could have said in seconds.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert CI_STEP in text, (
        f"{WORKFLOW.name} has no step named {CI_STEP!r}, so nothing looks across branches "
        "before a release. R-64 asked for this half explicitly.")
    guard = text.index(CI_STEP)
    suite = text.index("The engine must pass its own tests before it is shipped")
    build = text.index("- name: Build")
    assert guard < suite < build, (
        "the cross-branch check must refuse before the suite and the build, not after")


def test_the_ci_half_compares_ceilings_across_every_branch():
    """Its two load-bearing pieces, named so a rewrite that drops one fails here.

    Reading a workflow is weak evidence and is used only for what cannot be executed in a
    test: that it asks about OTHER refs at all, and that it compares by number.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text[text.index(CI_STEP):]
    step = step[:step.index("\n      - name:")]
    assert "+refs/heads/*:refs/remotes/origin/*" in step, (
        "the step does not FETCH every branch, so the loop below it iterates whatever this "
        "runner happened to have -- on a tag build, nothing. Caught by mutation: an earlier "
        "version of this assertion looked for `refs/remotes/origin`, which appears twice in "
        "the step, so narrowing the fetch to main alone left it green.")
    loop = step[step.index("for ref in"):].splitlines()[0]
    assert "refs/remotes/origin" in loop, (
        "the loop does not iterate the remote-tracking branches the fetch just brought")
    assert "-gt" in step, (
        "the step does not compare migration numbers, so a branch merely BEHIND would "
        "trip it and a branch ahead might not")
    assert "exit 1" in step, "the step reports and does not refuse"


def test_the_install_line_is_in_the_readme():
    """A hook nobody installs is `OP-32`'s shape: every part works and nothing happens."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "core.hooksPath .githooks" in readme, (
        "README does not tell a developer to install the hooks, so the local half of R-64 "
        "is inert on every fresh clone")
