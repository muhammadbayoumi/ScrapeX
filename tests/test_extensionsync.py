"""scrapex/extensionsync.py — keeping the locally loaded extension/ folder in
step with origin/main, without ever discarding uncommitted work.

Every fixture is a real, local, throwaway git repository: a bare `origin` plus
one or more clones. No test reaches the network or the real ScrapeX repository
— `extensionsync.REPO_ROOT` is monkeypatched to the fixture checkout, so the
module under test cannot tell the difference from the real thing except that
everything here is disposable.
"""
import subprocess

import pytest

from scrapex import extensionsync

pytestmark = pytest.mark.extension


def _run(cwd, *args):
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _run(path, "init")
    _run(path, "checkout", "-b", "main")
    _run(path, "config", "user.email", "test@example.com")
    _run(path, "config", "user.name", "Test")
    return path


def _write_extension_file(repo, content):
    ext = repo / "extension"
    ext.mkdir(exist_ok=True)
    (ext / "app.js").write_text(content, encoding="utf-8")


@pytest.fixture
def synced_checkout(tmp_path, monkeypatch):
    """A checkout on `main`, tracking a bare `origin`, with extension/app.js
    committed and pushed — the baseline every test starts from and mutates."""
    origin = tmp_path / "origin.git"
    _run(tmp_path, "init", "--bare", str(origin))

    checkout = _init_repo(tmp_path / "checkout")
    _run(checkout, "remote", "add", "origin", str(origin))
    _write_extension_file(checkout, "v1\n")
    (checkout / "README.md").write_text("readme\n", encoding="utf-8")
    _run(checkout, "add", "-A")
    _run(checkout, "commit", "-m", "init")
    _run(checkout, "push", "-u", "origin", "main")

    monkeypatch.setattr(extensionsync, "REPO_ROOT", checkout)
    return checkout, origin


def _mirror_clone(origin, tmp_path, name="mirror"):
    mirror = tmp_path / name
    _run(tmp_path, "clone", str(origin), str(mirror))
    _run(mirror, "config", "user.email", "test@example.com")
    _run(mirror, "config", "user.name", "Test")
    # EXPLICIT, not assumed: the bare origin's own HEAD symref was never
    # pointed at "main" (only `checkout`'s push created the branch, not the
    # remote's default), so a plain clone can check out an unrelated branch
    # name. Every mirror must sit on the same "main" the fixture pushed.
    _run(mirror, "checkout", "-B", "main", "origin/main")
    return mirror


def _push_new_extension_commit(origin, tmp_path, content, name="mirror"):
    """A second clone pushes a commit touching extension/ to origin/main —
    simulating another session's merge landing on GitHub while the fixture
    checkout sits still, exactly the situation check()/apply() exist for."""
    mirror = _mirror_clone(origin, tmp_path, name)
    _write_extension_file(mirror, content)
    _run(mirror, "add", "-A")
    _run(mirror, "commit", "-m", "extension change")
    _run(mirror, "push", "origin", "HEAD:main")
    return mirror


# ---- check() -------------------------------------------------------------

def test_no_git_when_the_folder_is_not_a_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(extensionsync, "REPO_ROOT", tmp_path)
    assert extensionsync.check() == {
        "ok": True, "state": "no_git",
        "detail": "This install is not a git checkout; there is nothing to sync."}


def test_not_main_refuses_a_feature_branch(synced_checkout):
    checkout, _origin = synced_checkout
    _run(checkout, "checkout", "-b", "some-feature")
    assert extensionsync.check()["state"] == "not_main"


def test_offline_when_the_remote_cannot_be_reached(synced_checkout):
    checkout, _origin = synced_checkout
    _run(checkout, "remote", "set-url", "origin", str(checkout / "does-not-exist"))
    result = extensionsync.check()
    assert result["state"] == "offline"
    assert result["detail"]


def test_up_to_date_when_nothing_new_landed(synced_checkout):
    assert extensionsync.check() == {"ok": True, "state": "up_to_date"}


def test_dirty_refuses_to_touch_uncommitted_extension_edits(synced_checkout):
    checkout, _origin = synced_checkout
    (checkout / "extension" / "app.js").write_text("local edit\n", encoding="utf-8")
    assert extensionsync.check()["state"] == "dirty"


def test_dirty_ignores_edits_outside_extension(synced_checkout):
    """Scope is extension/, not the whole checkout — an uncommitted edit to an
    engine file elsewhere must not block a sync that never touches it."""
    checkout, _origin = synced_checkout
    (checkout / "README.md").write_text("unrelated edit\n", encoding="utf-8")
    assert extensionsync.check() == {"ok": True, "state": "up_to_date"}


def test_behind_counts_and_names_commits_touching_extension(synced_checkout, tmp_path):
    checkout, origin = synced_checkout
    _push_new_extension_commit(origin, tmp_path, "v2\n")
    result = extensionsync.check()
    assert result["state"] == "behind"
    assert result["commits_behind"] == 1
    assert len(result["summary"]) == 1
    assert "extension change" in result["summary"][0]


def test_a_commit_that_never_touches_extension_is_not_behind(synced_checkout, tmp_path):
    checkout, origin = synced_checkout
    mirror = _mirror_clone(origin, tmp_path)
    (mirror / "README.md").write_text("unrelated upstream change\n", encoding="utf-8")
    _run(mirror, "add", "-A")
    _run(mirror, "commit", "-m", "unrelated")
    _run(mirror, "push", "origin", "HEAD:main")
    assert extensionsync.check() == {"ok": True, "state": "up_to_date"}


# ---- apply() ---------------------------------------------------------------

def test_apply_is_a_no_op_when_there_is_nothing_to_apply(synced_checkout):
    assert extensionsync.apply() == {"ok": True, "state": "up_to_date"}


def test_apply_fast_forwards_and_the_file_on_disk_changes(synced_checkout, tmp_path):
    checkout, origin = synced_checkout
    _push_new_extension_commit(origin, tmp_path, "v2\n")

    result = extensionsync.apply()

    assert result["state"] == "applied"
    assert result["head"]
    assert (checkout / "extension" / "app.js").read_text(encoding="utf-8") == "v2\n"
    # The tree is honestly up to date now, not stuck reporting "behind" forever
    # — the failure mode a sparse checkout that never moves HEAD would have.
    assert extensionsync.check()["state"] == "up_to_date"


def test_apply_refuses_when_extension_is_dirty(synced_checkout, tmp_path):
    checkout, origin = synced_checkout
    _push_new_extension_commit(origin, tmp_path, "v2\n")
    (checkout / "extension" / "app.js").write_text("local edit\n", encoding="utf-8")

    result = extensionsync.apply()

    assert result["state"] == "dirty"
    assert (checkout / "extension" / "app.js").read_text(encoding="utf-8") == "local edit\n"


def test_apply_reports_diverged_rather_than_merging_or_rebasing(synced_checkout, tmp_path):
    checkout, origin = synced_checkout
    _push_new_extension_commit(origin, tmp_path, "v2\n")
    # checkout's OWN unpushed commit to extension/: the histories diverge, but
    # `git status` is clean because it is committed — so check() still says
    # "behind", and it is apply()'s merge attempt that must catch this.
    _write_extension_file(checkout, "local commit\n")
    _run(checkout, "add", "-A")
    _run(checkout, "commit", "-m", "local work")
    assert extensionsync.check()["state"] == "behind"

    result = extensionsync.apply()

    assert result["state"] == "diverged"
    assert (checkout / "extension" / "app.js").read_text(encoding="utf-8") == "local commit\n"


def test_apply_surfaces_an_unrecognised_git_failure_rather_than_guessing(
        synced_checkout, tmp_path, monkeypatch):
    checkout, origin = synced_checkout
    _push_new_extension_commit(origin, tmp_path, "v2\n")
    real_git = extensionsync._git

    def fake_git(*args):
        if args and args[0] == "merge":
            return 1, "", "fatal: something git invented tomorrow"
        return real_git(*args)

    monkeypatch.setattr(extensionsync, "_git", fake_git)

    result = extensionsync.apply()

    assert result["ok"] is False
    assert result["error"] == "merge_failed"
    assert "something git invented tomorrow" in result["detail"]


# ---- _git() itself -----------------------------------------------------------

def test_git_helper_reports_a_missing_executable_rather_than_raising(monkeypatch):
    monkeypatch.setattr(extensionsync.shutil, "which", lambda name: None)
    code, _out, err = extensionsync._git("status")
    assert code == 127
    assert "PATH" in err


def test_git_helper_reports_a_timeout_rather_than_hanging(monkeypatch):
    def _raise_timeout(*_a, **_k):
        raise extensionsync.subprocess.TimeoutExpired(cmd="git", timeout=20)

    monkeypatch.setattr(extensionsync.subprocess, "run", _raise_timeout)
    code, _out, err = extensionsync._git("fetch")
    assert code == 124
    assert "timed out" in err
