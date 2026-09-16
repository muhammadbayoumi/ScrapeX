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
import json
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


def _recipe():
    """`packaging/build_engine.py`, which is not importable as a package.

    THE SAME LOADER `test_the_frozen_engine_carries_its_own_files.py` USES, and for the
    same reason: the build recipe is a script, and a guard that re-implemented what it
    says would be asserting against its own copy.
    """
    import importlib.util

    recipe = ROOT / "packaging" / "build_engine.py"
    assert recipe.is_file(), f"{recipe} is gone; this guard must follow it"
    spec = importlib.util.spec_from_file_location("scrapex_build_recipe", recipe)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen_bundle(monkeypatch, tmp_path: Path, stamp: str | None) -> dict:
    """Seal as an installed build whose bundle holds `stamp`, and report."""
    monkeypatch.setattr(provenance.enginelaunch, "frozen", lambda: True)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    if stamp is not None:
        (tmp_path / provenance.BUNDLE_STAMP).write_text(stamp, encoding="utf-8")
    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()
    return provenance.report()


def test_a_frozen_build_reports_the_commit_its_bundle_carries(monkeypatch, tmp_path):
    """`R-77` MADE THE COMMIT THE ENGINE'S IDENTITY, AND AN INSTALLED ONE HAD NONE.

    The ruling's first clause is that identity is the commit rather than a number --
    "it is free, it cannot be wrong, and it needs no rule". But `seal()` returned before
    `head` was read whenever the build was frozen, and nothing in the repository stamped
    a commit anywhere, so every installed engine answered `commit: None` and the panel's
    Build row rendered the bare words `installed build`. `engineBuildText` has always
    known how to draw `installed - <sha7>`; the fact was simply never in the bundle.

    AND THE IDENTITY IS A DIFFERENT QUESTION FROM THE COMPARISON, which is why the
    honesty assertions below still hold here: this build now says WHICH code it is and
    still refuses to say whether newer code exists, because it carries no source tree
    to compare against and never will.
    """
    commit = "b" * 40
    report = _frozen_bundle(monkeypatch, tmp_path,
                            json.dumps({"commit": commit, "built_at": "2026-09-02"}))

    assert report["mode"] == "frozen"
    assert report["commit"] == commit, "the bundle carried its commit and it was not read"
    assert report["stale"] is None, "reading a commit taught it something it cannot know"
    assert report["moved"] is None
    assert report["commit_now"] is None


@pytest.mark.parametrize("stamp", [
    None,                                   # a bundle from before the stamp existed
    "",                                     # a truncated write
    "{",                                    # a torn one
    '{"commit": null}',
    '{"commit": ""}',
    '{"commit": "abc123"}',                 # short
    '{"commit": "' + "z" * 40 + '"}',       # 40 characters, not hex
    '{"commit": ' + '["' + "a" * 40 + '"]}',  # the right value, wrong shape
    '["' + "a" * 40 + '"]',                 # not an object at all
])
def test_a_frozen_build_invents_no_commit_it_cannot_read(monkeypatch, tmp_path, stamp):
    """EVERY FAILURE IS A BLANK, NEVER A PLACEHOLDER, and there are eight of them.

    Under `R-77` this string is the engine's identity, so `unknown` or a truncated hash
    in that field is worse than an empty one: the field's whole claim is that it cannot
    be wrong. An engine installed before the stamp existed is the common case and is not
    an error -- it is a build that cannot say, which is what the field already meant.
    """
    report = _frozen_bundle(monkeypatch, tmp_path, stamp)

    assert report["mode"] == "frozen"
    assert report["commit"] is None, (
        f"a stamp reading {stamp!r} produced {report['commit']!r} as this engine's "
        "identity")
    assert "cannot be answered" in report["detail"]


def test_a_source_build_reads_head_and_not_a_bundle(monkeypatch, tmp_path):
    """THE STAMP MUST NOT REACH THE PATH THAT ALREADY HAD AN ANSWER.

    A source checkout reads `HEAD` from the repository, which is exact and live. If a
    stray `_MEIPASS` or a stamp file could influence it, the honest path would start
    answering from a stale artefact -- and `moved` compares `head` at seal against `HEAD`
    now, so a wrong `head` reports a checkout that moved when it did not.
    """
    (tmp_path / provenance.BUNDLE_STAMP).write_text(
        json.dumps({"commit": "c" * 40}), encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    provenance._SNAPSHOT = provenance._Snapshot()
    provenance.seal()

    report = provenance.report()

    assert report["mode"] == "source"
    assert report["commit"] != "c" * 40, (
        "a source build took its identity from a bundle stamp instead of HEAD")


def test_the_stamp_name_is_one_string_and_not_two():
    """WRITTEN BY THE BUILD, READ BY THE RUNTIME, AND THE TWO CANNOT BE IMPORTED
    TOGETHER: `packaging/` is not on the path of an installed engine, so `provenance`
    repeats the name rather than importing it. This is what stops the repetition from
    becoming a drift -- the same failure `RUNTIME_DATA`'s own comment records about
    `pyproject.toml` carrying the same fact twice with nothing comparing them."""
    assert _recipe().STAMP_NAME == provenance.BUNDLE_STAMP


def test_the_builder_stamps_the_commit_it_is_building(tmp_path):
    """A STAMP IS ONLY WORTH ANYTHING IF IT IS THIS TREE'S COMMIT.

    Asserted against `git rev-parse HEAD` run separately, so a builder that wrote a
    constant, an abbreviated hash, or the wrong repository's head fails here rather
    than shipping an engine that misidentifies itself.
    """
    recipe = _recipe()
    stamp = recipe.write_build_stamp(tmp_path / "build")

    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert stamp is not None, "the recipe read no commit inside a repository"
    assert stamp.name == provenance.BUNDLE_STAMP
    written = json.loads(stamp.read_text(encoding="utf-8"))
    assert written["commit"] == head, (
        f"stamped {written['commit']!r} for a tree whose HEAD is {head!r}")
    assert written["built_at"], "the stamp carries no moment, so its claim has no base"


def test_the_stamp_rides_along_in_the_bundle(tmp_path):
    """A RESOURCE ABSENT FROM THE BUNDLE IS DISCOVERED BY A PERSON, ON THEIR MACHINE.

    That sentence is `RUNTIME_DATA`'s own, earned by a published build that started,
    prepared a database and could not serve one page. The stamp cannot join that list --
    every entry there is a tracked path checked for existence before the build, and this
    one is generated per build -- so it is added separately, and this is what says the
    separate path is wired.
    """
    recipe = _recipe()
    stamp = recipe.write_build_stamp(tmp_path / "build")
    arguments = recipe.add_data_arguments(stamp)

    separator = ";" if sys.platform == "win32" else ":"
    assert f"{stamp}{separator}." in arguments, (
        "the stamp was written and not handed to PyInstaller, so the .exe carries "
        f"no commit: {arguments[-4:]}")
    # AND IT IS ABSENT WHEN THERE IS NOTHING TO ADD, rather than passed as an empty
    # argument PyInstaller would reject.
    assert recipe.add_data_arguments(None) == recipe.add_data_arguments()


def test_the_build_ITSELF_passes_the_stamp_and_not_only_the_helper(monkeypatch):
    """ASSERTING THE HELPER WAS NOT ENOUGH, AND A MUTATION PROVED IT.

    `test_the_stamp_rides_along_in_the_bundle` calls `add_data_arguments(stamp)` itself,
    so it says the function can carry a stamp and nothing about whether `build()` hands
    it one. Changing `build()` back to `add_data_arguments()` -- the exact defect, an
    engine stamped on disk and shipped without it -- left that test GREEN.

    So this reads the command `build()` actually assembles. `subprocess.call` is replaced
    rather than the build run: PyInstaller takes ten minutes and is not installed in
    every environment, and what is under test is the argument list, which is complete
    before the call.
    """
    recipe = _recipe()
    seen: list[list[str]] = []
    monkeypatch.setattr(recipe.subprocess, "call",
                        lambda command, *a, **k: seen.append(command) or 0)

    assert recipe.build() == 0
    assert seen, "build() assembled no command at all"
    command = seen[0]

    stamped = [argument for argument in command if recipe.STAMP_NAME in argument]
    assert stamped, (
        "build() never handed the stamp to PyInstaller, so the .exe it produces "
        "reports no commit and its Build row reads `installed build` -- which is the "
        f"whole defect this branch exists for. Command tail: {command[-6:]}")
    separator = ";" if sys.platform == "win32" else ":"
    assert all(one.endswith(f"{separator}.") for one in stamped), (
        f"the stamp is bundled somewhere other than the root, where `provenance` "
        f"reads it: {stamped}")


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

    `R-77` moves the engine's number on a CONTRACT change, so many trees share one
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


# ---- and the remedy the report names ----------------------------------------

class _CapturedThread:
    """Stands in for `threading.Thread` and KEEPS the target instead of running it.

    THIS IS THE ONE THING THIS SECTION MAY NOT GET WRONG. `restart_engine`'s
    thread sleeps 1.5 s and then calls `os._exit(0)` -- a hard exit that runs no
    `atexit` hook, no finaliser and none of pytest's reporting. Let the real
    `threading.Thread` run inside a pytest process and the session does not go
    red, it VANISHES: the dots stop mid-line, there is no summary, and the shell
    is handed exit code 0. Measured, not feared -- moving the call inline while
    only one test patched `os._exit` ended a 38-test run at 36 dots and no report.

    So `scrapex.webui.app.threading` is this for the duration, `start()` records
    that it was asked to run and does nothing, and the target is called
    deliberately -- once, in `test_the_bow_out_answers_first_and_exits_second`.
    """

    def __init__(self, made: list, target=None, daemon=None, **kwargs):
        self.made = made
        self.target = target
        self.daemon = daemon
        self.kwargs = kwargs
        self.started = False
        made.append(self)

    def start(self) -> None:
        self.started = True


@pytest.fixture
def panel(tmp_path, monkeypatch):
    """The real app behind a real client, with every way out of the process shut.

    THE KILLERS ARE DECLAWED HERE AND NOT PER TEST, which is the correction to a
    first draft that patched them only where it meant to call them. A test that
    merely drives the route does not choose whether `os._exit` is real -- the
    route does -- so leaving it real anywhere makes one edit to `app.py` the
    difference between a red and a disappeared run. `time.sleep` goes with it, so
    an inline sleep costs the suite 1.5 s once rather than silently.

    They are recorded rather than merely blocked: `panel.order` is the evidence
    that a route which is supposed to ANSWER first has done nothing else yet.
    Both are patched as single attributes on the real modules, restored by
    `monkeypatch` -- not by swapping the modules out from under `app`, which runs
    middleware entitled to a real `os`.

    `spawn_helper` is NOT given a working default here: its two outcomes are the
    two halves of this route, and a default would quietly supply whichever half a
    test forgot to state. It is replaced with a REFUSAL instead, because the real
    one starts a detached process and appends to `Path.home() / ".scrapex" /
    "engine.log"` -- `relaunch.engine_log` reads no environment variable
    (`scrapex/relaunch.py:145`), so conftest's `SCRAPEX_DATA_ROOT` does not reach
    it and a test that merely forgot to patch would write into the owner's live
    log and leave a real helper polling a real port. The refusal cannot be
    mistaken for either half: the route turns it into a 500 whose detail carries
    this sentence rather than the errno each test supplies.

    The client's `base_url` carries an explicit port on purpose: `restart_engine`
    reads `request.url.port` to tell the helper which port to re-bind, and a client
    with no port in its base_url falls through to the literal 8000 that the body
    also hardcodes as its fallback -- so it could not tell a read from a constant.
    """
    pytest.importorskip("fastapi", reason="needs the ui extra")
    from fastapi.testclient import TestClient

    from scrapex import relaunch
    from scrapex.databases import DatabaseRegistry
    from scrapex.databases.domain import EngineDatabase
    from scrapex.webui import app as app_module

    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "marketlens" / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json")
    registry.initialize()
    api = app_module.create_app(databases=registry)

    def unstated(port: int) -> int:
        raise AssertionError(
            "this test drove /api/engine/restart without saying what spawn_helper "
            "does, and the real one starts a detached process and writes to the "
            "owner's ~/.scrapex/engine.log")

    monkeypatch.setattr(relaunch, "spawn_helper", unstated)

    made: list[_CapturedThread] = []
    order: list[tuple] = []
    monkeypatch.setattr(app_module, "threading", types.SimpleNamespace(
        Thread=lambda **kw: _CapturedThread(made, **kw)))
    monkeypatch.setattr(app_module.time, "sleep",
                        lambda seconds: order.append(("slept", seconds)))
    monkeypatch.setattr(app_module.os, "_exit",
                        lambda code: order.append(("exited", code)))
    return types.SimpleNamespace(
        module=app_module, app=api, threads=made, order=order,
        client=lambda port: TestClient(api, base_url=f"http://127.0.0.1:{port}"))


def test_a_helper_that_cannot_start_leaves_the_engine_running_and_says_where_to_go(
        panel, monkeypatch):
    """THE FAILURE THAT MUST NOT COMPOUND. This route is the only way out of a
    warehouse written by a newer build -- migrations go forward only, so Upgrade
    database cannot help -- and the owner reaches it from a button, never a
    terminal. If the helper does not start and the engine exits anyway, the panel
    is gone, the port is free, and nothing is coming to take it: the one repair
    has become the outage.

    So the order in the body is load-bearing, and both halves are asserted: a 500
    that names the Startup folder (his other way in, and he has to be told to use
    it), AND no bow-out at all. The second is the one a reader would skip;
    scheduling the exit above the `try` passes every string check here.
    """
    from scrapex import relaunch

    def refuses(port: int) -> int:
        raise OSError("[Errno 13] Permission denied: 'engine.log'")

    monkeypatch.setattr(relaunch, "spawn_helper", refuses)

    answer = panel.client(8123).post("/api/engine/restart")

    assert answer.status_code == 500, answer.text
    detail = answer.json()["detail"]
    assert "Startup" in detail, (
        "the owner has exactly one other way to start an engine and this is where "
        f"he is told to use it. Got: {detail}")
    assert "still running" in detail, (
        "he is about to reload the page; the message decides whether he expects "
        f"an engine to be there. Got: {detail}")
    assert "[Errno 13]" in detail, (
        "the cause is carried through rather than swallowed -- no silent failures")
    assert panel.threads == [], (
        "the helper never started, so nothing will bring this engine back and it "
        "must not schedule its own exit")
    assert panel.order == [], (
        f"it exited anyway, with no helper coming. Got: {panel.order}")


def test_the_helper_is_told_the_port_this_request_arrived_on(panel, monkeypatch):
    """A HELPER THAT REBINDS THE WRONG PORT IS A SILENT LOSS. The engine comes
    back, answers nobody, and the panel -- which polls the port it was opened on --
    reports an engine that never returned.

    Two different ports through the same app, because one port cannot tell a read
    from a constant: `8000` is in this function's own body as the fallback, so a
    single-port test would pass against `port = 8000`.
    """
    from scrapex import relaunch

    asked: list[int] = []
    monkeypatch.setattr(relaunch, "spawn_helper",
                        lambda port: asked.append(port) or 4242)

    first = panel.client(8123).post("/api/engine/restart").json()
    second = panel.client(9010).post("/api/engine/restart").json()

    assert [first["port"], second["port"]] == [8123, 9010], (first, second)
    assert asked == [8123, 9010], (
        "the port in the answer is cosmetic; the port the helper was given is the "
        f"one the engine comes back on. Got: {asked}")
    assert first["ok"] is True
    assert first["helper_pid"] == 4242, (
        "the pid is the only handle the owner has on a detached process that "
        "outlives this one")
    assert len(panel.threads) == 2 and all(t.started for t in panel.threads), (
        "a helper is now waiting for this port; an engine that does not exit holds "
        "it until the helper gives up and says so in the log")
    assert all(t.daemon is True for t in panel.threads), (
        "a non-daemon thread would hold the interpreter open for the whole sleep "
        "even where the engine was asked to stop in the meantime")


def test_the_bow_out_answers_first_and_exits_second(panel, monkeypatch):
    """THE ORDER IS THE WHOLE DESIGN -- "This answers FIRST and exits a moment
    later, so the browser gets a reply instead of a dropped connection."

    A dropped connection and a restart look identical from the panel, so getting
    this backwards costs the owner the one message that tells him to wait and
    reload rather than conclude the button is broken.

    "Answers first" is a claim about what has NOT happened by the time the
    response is in hand, so it is asserted while the recorder is already
    listening -- see the fixture, which is what makes `panel.order` evidence
    rather than an empty list compared with itself. An inline `os._exit`, or an
    inline 1.5 s sleep (the other way to get this wrong), puts an entry there
    before the response exists.
    """
    from scrapex import relaunch

    monkeypatch.setattr(relaunch, "spawn_helper", lambda port: 4242)

    answer = panel.client(8123).post("/api/engine/restart")

    assert answer.status_code == 200
    assert "reload" in answer.json()["message"].lower(), (
        "the answer is the only instruction he gets before the page stops "
        "responding")
    assert panel.order == [], (
        "the reply is in hand and the engine has neither slept nor exited: the "
        f"answer beat the exit, which is what the detached thread is for. Got: "
        f"{panel.order}")

    panel.threads[0].target()

    assert panel.order == [("slept", 1.5), ("exited", 0)], (
        "it must wait and then exit: exiting first drops the connection the sleep "
        "exists to protect, and a non-zero code tells the helper's log that the "
        f"engine crashed rather than stood aside. Got: {panel.order}")


def test_a_helper_that_fails_for_any_other_reason_gets_the_same_way_out(
        panel, monkeypatch):
    """AN ERRNO IS NOT THE ONLY WAY THIS FAILS, and the test above proves only that
    one. `spawn_helper` builds its command line first (`enginelaunch.engine_argv`,
    `scrapex/relaunch.py:154`), and a build that cannot work out what to run does not
    raise `OSError`. Measured: with only the errno test present, `except Exception`
    narrows to `except OSError` and the whole file stays green.

    What that costs is not a worse message but no message: an exception the route
    does not catch never becomes an `HTTPException`, so the body carries no `detail`
    at all -- and `detail` is the only thing the three callers read
    (the panel's `app.js`, `settings.html`, `database_unavailable.html` each fall back
    to "The engine refused (HTTP 500)."). The owner is on the one screen he can still
    reach, and it tells him nothing and sends him nowhere.
    """
    from scrapex import relaunch

    def refuses(port: int) -> int:
        raise RuntimeError("cannot work out what to run")

    monkeypatch.setattr(relaunch, "spawn_helper", refuses)

    answer = panel.client(8123).post("/api/engine/restart")

    assert answer.status_code == 500, answer.text
    detail = answer.json()["detail"]
    assert "Startup" in detail, (
        "every failure to start the helper ends at the same one other way in, "
        f"whatever the exception was. Got: {detail}")
    assert "cannot work out what to run" in detail, (
        "no silent failures -- the cause reaches the panel however it was raised")
    assert panel.threads == [] and panel.order == [], (
        f"no helper started, so the engine must still be here to say so. "
        f"Got threads={panel.threads}, order={panel.order}")


def test_a_request_that_names_no_port_falls_back_to_the_engine_default(
        panel, monkeypatch):
    """THE ONE LINE OF THIS ROUTE THE PORT TEST CANNOT REACH. `request.url.port` is
    None whenever the Host header carries no port, and the body answers that with a
    fallback -- so the test above, which sends two explicit ports precisely so a read
    cannot be confused with a constant, never executes the fallback at all. Measured:
    `or 8000` becomes `or 0` and every other test here still passes, while the helper
    is told to bring the engine back on an ephemeral port the panel will never poll.

    The expected value is read from `native.DEFAULT_ENGINE_PORT` rather than written
    again here: that is where the number lives (`autostart` says in a comment that its
    own copy mirrors it), and this route holds a third, bare copy. If they ever
    disagree, this is the test that says so.
    """
    from fastapi.testclient import TestClient

    from scrapex import native, relaunch

    asked: list[int] = []
    monkeypatch.setattr(relaunch, "spawn_helper",
                        lambda port: asked.append(port) or 4242)

    # No port in the base_url, so no port in the Host header -- `localhost` is on
    # LOOPBACK_HOSTS, so TrustedHostMiddleware passes it through to the route.
    answer = TestClient(panel.app, base_url="http://localhost").post(
        "/api/engine/restart")

    assert answer.status_code == 200, answer.text
    assert asked == [native.DEFAULT_ENGINE_PORT], (
        "a request with no port still has to name a real one, and the only sane "
        f"guess is the port the engine starts on. Got: {asked}")
    assert answer.json()["port"] == native.DEFAULT_ENGINE_PORT
