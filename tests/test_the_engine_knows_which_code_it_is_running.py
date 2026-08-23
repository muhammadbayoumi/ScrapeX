"""A running engine must be able to say that the disk has moved past it.

THE INCIDENT, MEASURED 2026-08-23, and every number here was re-derived from this
repository rather than remembered:

    the engine answering 127.0.0.1:8000 started        07:35:44
    the checkout moved 451468d -> 31c369e at           07:39:03  (reflog)
    delta                                              +199 seconds

The owner's panel said "no successful crawl yet" over 17,304 crawled rows. #255
(`bcb8f6e`) had fixed exactly that two days earlier and the fix was on `main`. Run
`git show 451468d:scrapex/webui/app.py` and line 650 of THAT commit still reads
`"last_success": None` — the literal #255 removed. (Not written as a
`path:line` citation: on disk today that line is a bare `continue`, so the shape that
means "current" would send a reader nowhere. `docs/LESSONS.md` §14.) **Python imports
a module once**, so the process kept serving the tree it had imported while the disk
went on without it.

AND NOTHING COULD TELL, WHICH IS WHAT THESE TESTS ARE FOR. `/api/health` and
`/api/version` both answered `"version": "0.3.0"`, truthfully: `git rev-parse
engine-v0.3.0` is `451468d`. Measured here rather than asserted -- **ten distinct
commits report `VERSION = "0.3.0"`**, every tree from `e963269` (#247) through
`31c369e`'s parent (#257), one of them the release tag. A string ten trees share
cannot name one of them, and it was the only self-description the engine had.

WHY #244's GATE COULD NOT CATCH THIS, since its own title is *"the gate could not
tell"*. Its gate is a release-workflow step (`.github/workflows/release-engine.yml`,
*"And it must speak when a person double-clicks it"*) that runs the just-built .exe
and greps three sentences out of its stdout. The step beside it claims more than it
can deliver: *"the answer must be the number on the tag -- which also proves the
binary carries the source that was checked above, and not a stale build."* That is
true only INSIDE that job, because the binary was built from that checkout seconds
earlier. Both checks are build-time, one-shot, and their subject is a freshly
started subprocess. Neither has any representation inside the long-lived process the
build produces, and `VERSION` cannot distinguish trees anyway. So #244 proved a NEW
ARTEFACT SPEAKS; it added nothing that lets a RUNNING PROCESS say which bytes it
loaded.

THE FAILURE FAMILY, recorded in `docs/LESSONS.md` §14: a measurement that outlives
its base and reads as current. Its other instances are a document, a table, a test
log and a build. **This one is a live process**, which is why no citation guard could
have found it: there is no line of prose to check. The check has to live in the
artefact and answer at run time, which is what `scrapex/provenance.py` does.

WHAT IS PROVED BY CONSTRUCTION BELOW. `test_a_module_changed_on_disk_after_the_seal_is_reported`
builds the exact condition -- a module loaded into this process, then rewritten on
disk -- and requires the report to say so. The honesty tests are the other half:
a frozen build answers `None` and never `False`, because an installed build cannot
compare itself to a source tree it does not carry.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

from scrapex import provenance

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _restore_snapshot():
    """Every test seals, so every test must put the process's own seal back.

    Without this, one test's temp-directory snapshot leaks into the next and into
    any other test in the session that reads `/api/health` -- which would make this
    file a source of false greens elsewhere, the failure it exists to prevent.
    """
    saved = provenance._SNAPSHOT
    yield
    provenance._SNAPSHOT = saved


def _fake_module(name: str, path: Path) -> types.ModuleType:
    """A module of the package, loaded, with a real file behind it.

    A REAL ENTRY IN `sys.modules`, because that is the authority `provenance`
    reads and a stub that only looked like one would prove nothing about the
    mechanism. Registered under the package's own namespace so it is in scope.
    """
    module = types.ModuleType(name)
    module.__file__ = str(path)
    return module


@pytest.fixture
def loaded(tmp_path, monkeypatch):
    """A package directory with one loaded module in it, and a clean seal.

    `_package_root` is redirected at `tmp_path` so the test owns every file it
    measures. Editing a real `scrapex/*.py` to prove staleness would work and would
    also be a test that writes into the checkout it is running from.
    """
    pkg = tmp_path / "scrapex"
    pkg.mkdir()
    target = pkg / "webui_app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(provenance, "_package_root", lambda: pkg)
    name = "scrapex.__provtest_app"
    monkeypatch.setitem(sys.modules, name, _fake_module(name, target))
    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()
    return types.SimpleNamespace(pkg=pkg, target=target, name=name)


# ---- the defect itself ------------------------------------------------------

def test_a_clean_source_run_reports_level_and_says_so(loaded):
    """THE CONTROL, and it is not decoration: it is what makes the next test mean
    something. A report that said `stale` on an untouched tree would fire on every
    engine always, and a warning that is always on is one the owner learns to
    scroll past."""
    report = provenance.report()

    assert report["mode"] == "source"
    assert report["stale"] is False
    assert report["changed"] == []
    assert report["sealed_at"] is not None
    assert "level with the code on disk" in report["detail"]


def test_a_module_changed_on_disk_after_the_seal_is_reported(loaded):
    """THE 2026-08-23 DEFECT, BUILT RATHER THAN DESCRIBED.

    The module stays exactly as it was imported -- nothing reloads it, which is the
    whole point -- and only the file underneath it changes. That is precisely what
    happened at 07:39:03 to a process that had started at 07:35:44.
    """
    loaded.target.write_text("VALUE = 2   # the fix the process never saw\n",
                             encoding="utf-8")

    report = provenance.report()

    assert report["stale"] is True, (
        "a loaded module was rewritten on disk and the engine reported itself "
        "current -- this is the incident, and the guard did not see it")
    assert loaded.name in report["changed"]
    assert "not the code on disk" in report["detail"]
    assert "Restart" in report["detail"], (
        "the report names the fault and must also name the remedy: the engine "
        "already has POST /api/engine/restart and nothing pointed at it")


def test_a_module_deleted_under_a_running_engine_is_a_divergence_too(loaded):
    """A file that is gone is not a file that agrees. `stat()` raising is the one
    branch where the cheap check cannot fall through to the digest, so it is stated
    rather than left to the `except`."""
    loaded.target.unlink()

    report = provenance.report()

    assert report["stale"] is True
    assert loaded.name in report["changed"]


def test_a_module_imported_after_the_seal_is_not_a_blind_spot(loaded):
    """THE GAP `seal()` HAS BY CONSTRUCTION, and it had to be closed rather than
    documented.

    This repository imports modules inside route handlers, so a module can first be
    loaded while serving a request — long after the reference point. It is therefore
    absent from the snapshot, and the comparison loop cannot see it at all. If that
    file was written AFTER the process sealed, the process is running a mix of pre-
    and post-edit code, which is worse than being uniformly behind.

    Found by asking what the mechanism does not cover, not by a failure. A guard
    that does not know its own blind spot is the defect this module exists for.
    """
    late = loaded.pkg / "late.py"
    late.write_text("LATE = 1\n", encoding="utf-8")
    import os
    # RELATIVE TO THE SEAL THIS TEST JUST TOOK, never to a module-level constant.
    # The first draft used `time.time() + 3600` computed at IMPORT, which is a flake
    # waiting for a slow suite: collection happens once and this test runs much
    # later, so a run that took over an hour to reach here would be comparing
    # against a moment already in the past. That is a measurement outliving its
    # base -- in the test file whose whole subject is that failure.
    after_seal = provenance._SNAPSHOT.sealed_at + 60
    os.utime(late, (after_seal, after_seal))
    name = "scrapex.__provtest_late"
    sys.modules[name] = _fake_module(name, late)
    try:
        report = provenance.report()
    finally:
        del sys.modules[name]

    assert report["stale"] is True, (
        "a module imported after the seal, from a file written after the seal, "
        "was invisible — the snapshot cannot hold it, so the check must look")
    assert name in report["changed"]


def test_a_module_imported_after_the_seal_from_older_code_is_not_stale(loaded):
    """THE OTHER HALF, and it is what stops the check above crying wolf. A module
    the process imports late from a file that has NOT been touched since the seal is
    ordinary lazy importing, which happens on most requests. Only a file written
    after the reference point proves a mixed state."""
    late = loaded.pkg / "old_late.py"
    late.write_text("OLD = 1\n", encoding="utf-8")
    import os
    os.utime(late, (1_600_000_000, 1_600_000_000))   # long before the seal
    name = "scrapex.__provtest_oldlate"
    sys.modules[name] = _fake_module(name, late)
    try:
        report = provenance.report()
    finally:
        del sys.modules[name]

    assert report["stale"] is False, (
        f"ordinary lazy importing was reported as a reason to restart: "
        f"{report['changed']}")


def test_a_file_rewritten_to_the_same_content_is_not_a_reason_to_restart(loaded):
    """THE CRY-WOLF CASE, and it is why the digest exists at all.

    `git checkout` and `git pull` rewrite mtimes. On the owner's machine, which is
    the machine sessions pull into all day, an mtime-only check would raise
    "Restart needed" over a tree that is byte-identical. The repository has already
    written down what that costs: *"A publish step that cries wolf gets ignored,
    which is the exact failure it exists to prevent."*
    """
    original = loaded.target.read_bytes()
    stat = loaded.target.stat()
    loaded.target.write_bytes(original)
    import os
    os.utime(loaded.target, (stat.st_atime + 120, stat.st_mtime + 120))
    assert loaded.target.stat().st_mtime != stat.st_mtime, \
        "the fixture failed to move the mtime, so this test proves nothing"

    report = provenance.report()

    assert report["stale"] is False, (
        f"an untouched file with a new mtime reported as changed: "
        f"{report['changed']}")


def test_the_digest_ignores_the_line_ending_and_nothing_else(tmp_path):
    """`.gitattributes` sets `* text=auto`, so the repo stores LF and Windows
    checks out CRLF -- and hashing raw bytes has already shipped as a real outage
    here (`docs/LESSONS.md` §1). Both reads happen on one machine, so this is
    belt-and-braces rather than the live bug; it is pinned because a future edit
    dropping the normalisation would look harmless."""
    lf = tmp_path / "lf.py"
    crlf = tmp_path / "crlf.py"
    lf.write_bytes(b"A = 1\nB = 2\n")
    crlf.write_bytes(b"A = 1\r\nB = 2\r\n")

    assert provenance._digest(lf) == provenance._digest(crlf)
    # And it is a real digest of the normalised form, not a constant.
    assert provenance._digest(lf) == hashlib.sha256(b"A = 1\nB = 2\n").hexdigest()


# ---- the honest unknown ----------------------------------------------------

def test_a_frozen_build_answers_unknown_and_never_false(monkeypatch):
    """AN INSTALLED BUILD CANNOT ANSWER THIS, AND SAYING `False` WOULD BE A GUESS.

    A PyInstaller one-file .exe carries no `.git` and no source tree; its modules
    live in a per-run temp directory that says nothing about whether newer code
    exists. `False` there would tell the owner his engine is current on the one
    build where we cannot know -- a guessed answer is the defect, and this is the
    assertion that refuses one.
    """
    monkeypatch.setattr(provenance.enginelaunch, "frozen", lambda: True)
    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()

    report = provenance.report()

    assert report["mode"] == "frozen"
    assert report["stale"] is None, "a frozen build claimed to know it was current"
    assert report["stale"] is not False
    assert report["moved"] is None
    assert report["commit_now"] is None
    assert "cannot be answered" in report["detail"]


def test_an_engine_that_never_sealed_says_it_does_not_know(monkeypatch):
    """The mechanism's own failure mode, stated rather than defaulted. If nothing
    ever called `seal()` the process has no reference point, and `False` would be a
    claim resting on nothing."""
    provenance._SNAPSHOT = provenance._Snapshot()

    report = provenance.report()

    assert report["stale"] is None
    assert report["sealed_at"] is None
    assert "never recorded which code it loaded" in report["detail"]


def test_a_report_that_cannot_be_computed_is_unknown_rather_than_clean(monkeypatch):
    """`report()` is reached from a timed poll, so it must not raise -- and the
    swallowed failure must not become a clean bill of health. This is the same rule
    `/api/health`'s worker block already follows: *"Unknown is now said as unknown,
    and the reason for not knowing travels with it."*"""
    def boom() -> dict:
        raise RuntimeError("the disk went away")

    monkeypatch.setattr(provenance, "_report", boom)

    report = provenance.report()

    assert report["stale"] is None
    assert report["mode"] == "unknown"
    assert "the disk went away" in report["detail"]


# ---- the git half, which gives the answer words -----------------------------

def _init_repo(path: Path) -> str:
    """A real repository, because the point is to read what git actually writes.

    A hand-built `.git` would pass whatever `_read_head` happens to do. Two
    commits so HEAD can move, and `-c` settings so this works on a machine with no
    global git identity.
    """
    def run(*args: str) -> str:
        return subprocess.run(("git", "-C", str(path), *args), check=True,
                              capture_output=True, text=True).stdout.strip()

    subprocess.run(("git", "init", "-q", "-b", "main", str(path)), check=True,
                   capture_output=True)
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (path / "one.txt").write_text("1\n", encoding="utf-8")
    run("add", "one.txt")
    run("commit", "-q", "-m", "one")
    return run("rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    pytest.importorskip("subprocess")
    if not _git_available():
        pytest.skip("git is not on PATH")
    work = tmp_path / "checkout"
    work.mkdir()
    first = _init_repo(work)
    pkg = work / "scrapex"
    pkg.mkdir()
    monkeypatch.setattr(provenance, "_package_root", lambda: pkg)
    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()
    return types.SimpleNamespace(work=work, pkg=pkg, first=first)


def _git_available() -> bool:
    try:
        subprocess.run(("git", "--version"), check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def test_the_commit_the_process_started_on_is_recorded(repo):
    report = provenance.report()

    assert report["commit"] == repo.first
    assert report["commit_now"] == repo.first
    assert report["moved"] is False


def test_a_checkout_that_advanced_under_a_running_engine_is_reported(repo):
    """THE OTHER HALF OF 07:39:03, and the half that gives the owner words.

    "started at 451468d, the checkout is now 31c369e" is a sentence he can act on;
    "stale" on its own is not. This fires even when nothing the process imported
    happened to change, which `stale` cannot see.
    """
    (repo.work / "two.txt").write_text("2\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(repo.work), "add", "two.txt"),
                   check=True, capture_output=True)
    subprocess.run(("git", "-C", str(repo.work), "commit", "-q", "-m", "two"),
                   check=True, capture_output=True)
    moved_to = subprocess.run(
        ("git", "-C", str(repo.work), "rev-parse", "HEAD"),
        check=True, capture_output=True, text=True).stdout.strip()
    assert moved_to != repo.first, "the fixture did not move HEAD"

    report = provenance.report()

    assert report["moved"] is True
    assert report["commit"] == repo.first
    assert report["commit_now"] == moved_to
    assert "moved to another commit" in report["detail"]


def test_an_engine_started_from_a_worktree_can_still_name_its_commit(tmp_path,
                                                                    monkeypatch):
    """THE CASE THIS REPOSITORY ACTUALLY RUNS IN, and the one a naive reader of
    `.git` gets wrong. In a worktree `.git` is a FILE reading `gitdir: <path>`, the
    branch pointer lives in the SHARED repository, and `commondir` is what joins
    them. Reading only the worktree's own gitdir reports "no commit" for every
    session working the way this project works."""
    if not _git_available():
        pytest.skip("git is not on PATH")
    main = tmp_path / "main"
    main.mkdir()
    first = _init_repo(main)
    tree = tmp_path / "wt"
    subprocess.run(("git", "-C", str(main), "worktree", "add", "-q",
                    str(tree), "-b", "side"), check=True, capture_output=True)
    assert (tree / ".git").is_file(), "the fixture did not produce a worktree"
    pkg = tree / "scrapex"
    pkg.mkdir()
    monkeypatch.setattr(provenance, "_package_root", lambda: pkg)
    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()

    report = provenance.report()

    assert report["commit"] == first, (
        "a worktree's HEAD was not readable, so an engine started from one "
        "cannot name the commit it is running")
    assert report["moved"] is False


def test_no_repository_at_all_is_not_a_reason_to_stop_answering(tmp_path,
                                                               monkeypatch):
    """A pip install from a tarball has no `.git` and is still a source run whose
    modules can go stale. The commit half goes unknown; the staleness half must
    keep working, because it is the half that proves the fault."""
    pkg = tmp_path / "nogit" / "scrapex"
    pkg.mkdir(parents=True)
    target = pkg / "mod.py"
    target.write_text("V = 1\n", encoding="utf-8")
    monkeypatch.setattr(provenance, "_package_root", lambda: pkg)
    name = "scrapex.__provtest_nogit"
    monkeypatch.setitem(sys.modules, name, _fake_module(name, target))
    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()
    target.write_text("V = 2\n", encoding="utf-8")

    report = provenance.report()

    assert report["commit"] is None
    assert report["moved"] is None
    assert report["stale"] is True, \
        "the staleness check must not depend on git being present"


# ---- reaching the owner ----------------------------------------------------

def test_the_report_only_names_modules_of_this_package(loaded, monkeypatch):
    """A DISCOVERY PATTERN WHOSE OUTPUT NOBODY READ is a recurring defect here
    (`docs/LESSONS.md` §7). This prints the boundary rather than trusting it:
    something loaded from outside the package directory, and something with no
    file at all, must both be out of scope."""
    stray = loaded.pkg.parent / "elsewhere.py"
    stray.write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "scrapex.__provtest_outside",
                        _fake_module("scrapex.__provtest_outside", stray))
    nofile = types.ModuleType("scrapex.__provtest_nofile")
    monkeypatch.setitem(sys.modules, "scrapex.__provtest_nofile", nofile)
    monkeypatch.setitem(sys.modules, "not_scrapex_at_all",
                        _fake_module("not_scrapex_at_all", loaded.target))

    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()
    seen = sorted(provenance._SNAPSHOT.loaded)

    assert seen == [loaded.name], seen


def test_the_summary_for_the_timed_poll_carries_no_growing_list(loaded):
    """`/api/health` is polled every few seconds behind a 2,500 ms deadline that
    this product has already blown once. The verdict rides the poll; the evidence
    does not."""
    loaded.target.write_text("V = 2\n", encoding="utf-8")

    summary = provenance.summary()

    assert "changed" not in summary
    assert summary["stale"] is True
    assert set(summary) == {"mode", "sealed_at", "commit", "commit_now",
                            "moved", "stale", "detail"}


def test_the_named_list_is_capped(loaded, monkeypatch):
    """Evidence, not a work queue: the remedy is one restart whether one module
    moved or forty, and `/api/version` is JSON somebody has to read."""
    fake = {f"scrapex.m{i}": (loaded.target, 0.0, 0, "nope")
            for i in range(provenance.NAMED_LIMIT + 5)}
    monkeypatch.setattr(provenance._SNAPSHOT, "loaded", fake)

    report = provenance.report()

    assert report["stale"] is True
    assert len(report["changed"]) == provenance.NAMED_LIMIT


# ---- and it reaches the wire ------------------------------------------------

def test_the_two_endpoints_carry_it(tmp_path):
    """THE FACT MUST LEAVE THE PROCESS, or it is a test talking to itself.

    `/api/health` is the only endpoint the panel polls on a timer, which is why
    `REQ-35` asks for one field on it. `/api/version` carries the module list
    because it is fetched once.
    """
    pytest.importorskip("fastapi", reason="needs the ui extra")
    from fastapi.testclient import TestClient

    from scrapex.databases import DatabaseRegistry
    from scrapex.databases.domain import EngineDatabase
    from scrapex.webui.app import create_app

    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "marketlens" / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json")
    registry.initialize()
    client = TestClient(create_app(databases=registry))

    health = client.get("/api/health").json()
    assert "build" in health, (
        "the panel polls this and nothing else on a timer; a fact that is not "
        "here reaches the owner only if he goes looking for it")
    assert health["build"]["mode"] in ("source", "frozen", "unknown")
    assert "changed" not in health["build"]

    version = client.get("/api/version").json()
    assert "provenance" in version
    assert "changed" in version["provenance"]
    # `create_app` seals on its last line, so a real client has a real reference
    # point. An endpoint answering `sealed_at: null` means that call was dropped.
    assert version["provenance"]["sealed_at"] is not None, \
        "create_app did not seal, so the engine cannot answer for itself"


def test_the_seal_happens_on_the_apps_last_line():
    """WHERE IT IS SEALED IS THE DESIGN, so it is pinned rather than left to a
    comment. Sealing earlier misses `webui.app` -- the module the incident was
    about. Sealing lazily takes the baseline AFTER the edit it exists to notice,
    which is worse than not checking at all.

    IT READS `create_app`, NOT THE FILE. The first draft of this test asserted on
    the last two lines of `app.py` and failed on correct code, because `app.py`
    carries module-level helpers after the factory. A guard pointed at the wrong
    subject is the defect this repository keeps recording; the function is the
    subject, so `inspect` is what finds it.
    """
    pytest.importorskip("fastapi", reason="needs the ui extra")
    import inspect

    from scrapex.webui.app import create_app

    tail = inspect.getsource(create_app).rstrip().splitlines()[-2:]

    assert any("provenance.seal()" in line for line in tail), (
        "create_app must seal on its last lines, after every module it serves "
        f"with is imported. Its tail is: {tail}")


def test_the_version_string_cannot_do_this_job(loaded):
    """THE MEASUREMENT THAT JUSTIFIES THE WHOLE MODULE, kept as a test so nobody
    proposes deleting it in favour of `VERSION`.

    `R-35` moves the engine's number on a CONTRACT change, so many trees share one
    number BY DESIGN. Ten commits report `0.3.0` -- `e963269` through `31c369e`'s
    parent -- and one of them is the `engine-v0.3.0` tag. Counted from git here
    rather than written down, so it cannot go stale the way the thing it describes
    did.
    """
    if not _git_available():
        pytest.skip("git is not on PATH")
    shown = subprocess.run(
        ("git", "-C", str(ROOT), "rev-list", "--count", "e963269^..31c369e^"),
        capture_output=True, text=True)
    if shown.returncode != 0:
        pytest.skip("this history is not present in a shallow clone")

    trees = int(shown.stdout.strip())

    assert trees > 1, (
        "if one tree per version were true, a version string would have been "
        "enough and this module would be unnecessary")
    tagged = subprocess.run(
        ("git", "-C", str(ROOT), "rev-parse", "engine-v0.3.0^{commit}"),
        capture_output=True, text=True)
    if tagged.returncode == 0:
        assert tagged.stdout.strip().startswith("451468d"), \
            "engine-v0.3.0 is not the commit this file's account rests on"
