"""tools/checkout_supabase_pin.py, run as a process against a local repository.

The tool exists to fetch Supabase at the pin, and a test cannot reach GitHub. So each case
builds a small repository of its own with two commits and hands the tool its path as the
remote: the rules under test are the tool's, whatever the repository.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "checkout_supabase_pin.py"

# It reads design/supabase.NOTICE.txt for the pin, so a change to that file must run it.
pytestmark = [pytest.mark.docs]


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture()
def upstream(tmp_path: Path) -> dict:
    """A repository shaped like Supabase's, at two commits: the pin and a later one."""
    repo = tmp_path / "upstream"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "t@example.com", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    # A fetch by SHA with a filter is what the tool does against GitHub; a local
    # repository refuses both unless told it may serve them.
    _git("config", "uploadpack.allowFilter", "true", cwd=repo)
    _git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=repo)
    files = {
        "apps/design-system/content/docs/copywriting.mdx": "# Copywriting\n",
        "packages/ui/src/components/shadcn/ui/badge.tsx": "export const Badge = 1\n",
        "apps/studio/components/interfaces/CronJobs/PreviousRunsTab.tsx": "status\n",
        "apps/www/pages/index.tsx": "marketing, never read by a study\n",
        "extra/only-on-request.md": "asked for with --path\n",
    }
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "pin", cwd=repo)
    pin = _git("rev-parse", "HEAD", cwd=repo)
    (repo / "apps/design-system/content/docs/copywriting.mdx").write_text("# Moved on\n")
    _git("commit", "-q", "-am", "later", cwd=repo)
    later = _git("rev-parse", "HEAD", cwd=repo)
    return {"remote": repo.as_uri(), "pin": pin, "later": later}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True)


def test_it_checks_out_the_study_paths_at_the_commit_and_nothing_else(upstream, tmp_path):
    dest = tmp_path / "checkout"
    done = _run("--remote", upstream["remote"], "--commit", upstream["pin"], "--dest", str(dest))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == str(dest)
    # The pin's text, not the later commit's: a study reads at a commit.
    assert (dest / "apps/design-system/content/docs/copywriting.mdx").read_text() == "# Copywriting\n"
    assert (dest / "packages/ui/src/components/shadcn/ui/badge.tsx").exists()
    assert (dest / "apps/studio/components/interfaces/CronJobs/PreviousRunsTab.tsx").exists()
    # Sparse: a path no study reads is not on disk.
    assert not (dest / "apps/www/pages/index.tsx").exists()
    assert not (dest / "extra/only-on-request.md").exists()


def test_a_second_run_reuses_the_checkout_and_widens_it_by_one_path(upstream, tmp_path):
    dest = tmp_path / "checkout"
    first = _run("--remote", upstream["remote"], "--commit", upstream["pin"], "--dest", str(dest))
    assert first.returncode == 0, first.stderr
    second = _run("--remote", upstream["remote"], "--commit", upstream["pin"], "--dest", str(dest),
                  "--path", "extra")
    assert second.returncode == 0, second.stderr
    assert (dest / "extra/only-on-request.md").read_text() == "asked for with --path\n"
    assert _git("rev-parse", "HEAD", cwd=dest) == upstream["pin"]


def test_a_branch_name_is_refused_because_it_moves(upstream, tmp_path):
    done = _run("--remote", upstream["remote"], "--commit", "master", "--dest", str(tmp_path / "x"))
    assert done.returncode != 0
    assert "40-character commit SHA" in done.stderr


def test_a_commit_the_remote_does_not_hold_is_a_failure_not_an_empty_directory(upstream, tmp_path):
    done = _run("--remote", upstream["remote"], "--commit", "0" * 40, "--dest", str(tmp_path / "x"))
    assert done.returncode != 0
    assert "fetching 000000000000 failed" in done.stderr


def test_a_directory_at_another_commit_is_refused_rather_than_mixed(upstream, tmp_path):
    dest = tmp_path / "checkout"
    assert _run("--remote", upstream["remote"], "--commit", upstream["pin"],
                "--dest", str(dest)).returncode == 0
    done = _run("--remote", upstream["remote"], "--commit", upstream["later"], "--dest", str(dest))
    assert done.returncode != 0
    assert "holds a checkout at another commit" in done.stderr
    # Refused, so the pin's checkout is untouched.
    assert _git("rev-parse", "HEAD", cwd=dest) == upstream["pin"]


def test_without_a_commit_it_reads_the_one_the_notice_pins():
    sys.path.insert(0, str(ROOT))
    from tools import checkout_supabase_pin as tool
    from tools.read_supabase_tokens import pinned_commit

    pin = pinned_commit()
    assert tool.default_destination(pin).name == f"supabase-{pin[:12]}"
