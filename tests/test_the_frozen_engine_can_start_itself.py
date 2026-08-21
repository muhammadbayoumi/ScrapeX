"""A shipped engine must be able to start itself, and to be asked anything.

TWO DEFECTS, ONE ROOT, both measured 2026-08-21 and both invisible to the ~2,600
tests that came before them: every one of those runs the SOURCE tree, where
`sys.executable` is a Python and `-m scrapex.cli` means what it says. In the
shipped binary it does not, and nothing had ever checked.

`OP-36` — FOUR of the five places that start a child engine built it as

    [sys.executable, "-m", "scrapex.cli", "ui", ...]

Under PyInstaller `sys.executable` is `scrapex-engine.exe`, whose bootloader does
not honour `-m`: those two become ordinary arguments, `argv[0]` comes out as
`"scrapex.cli"`, the entry point does not recognise it, and it falls through to
`serve()` — the Chrome native messaging host, which waits on stdin and prints
nothing. **The engine asks to be replaced and a mute stranger arrives.**
`scrapex/nativehost.py` was the one that had it right all along, and
`scrapex/enginelaunch.py` is that three-line test generalised.

`OP-35` — the entry point kept a HAND-WRITTEN copy of the CLI's subcommand names
to decide "CLI or Chrome". The copy drifted to half: twelve names listed, twenty-
four in the parser. Measured against the published 0.2.1 artifact, with a
control: `status` (listed) answered in **94 bytes**; `database-status` and
`autostart` (not listed) printed **zero**. `database-status` is the one command
that explains a warehouse the engine will not open.

WHY THESE TESTS NEED NO BINARY. Both defects are decided by `sys.frozen` and
`sys.executable`, which a test can set. That is the whole reason they were
reachable at all — and the reason there was never an excuse for not testing them.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from scrapex import autostart, enginelaunch, osschedule, relaunch
from scrapex import cli as scrapex_cli

ROOT = Path(__file__).resolve().parents[1]

#: Every module that starts a child engine, and the callable that builds it.
#: `nativehost` is absent because it answers a different question (one executable
#: path for Chrome's manifest, not an argv) and was already correct.
BUILDERS = (
    ("relaunch._engine_command", lambda: relaunch._engine_command(8000)),
    ("relaunch.spawn_helper's argv",
     lambda: enginelaunch.engine_argv("relaunch", "--port", "8000",
                                     "--wait-pid", "1", windowless=False)),
    ("native._spawn_engine's argv",
     lambda: enginelaunch.engine_argv("ui", "--port", "8000")),
)


@pytest.fixture
def frozen(monkeypatch):
    """Be the shipped binary: a `sys.frozen` flag and an .exe for an executable."""
    exe = r"C:\Users\Someone\Downloads\scrapex-engine.exe"
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", exe)
    return exe


# --------------------------------------------------------------------- OP-36

def test_a_frozen_engine_never_puts_dash_m_in_front_of_itself(frozen):
    """THE DEFECT, PINNED. `-m scrapex.cli` handed to an .exe is two dead words.

    Asserted on every builder rather than on the helper alone, because the helper
    being right is not the thing that broke — four callers not using it was.
    """
    for name, build in BUILDERS:
        argv = build()
        assert argv[0] == frozen, f"{name} does not run the shipped binary: {argv}"
        assert "-m" not in argv, (
            f"{name} still passes -m to a frozen executable, which ignores it and "
            f"turns the child into a silent native messaging host: {argv}")
        assert "scrapex.cli" not in argv, (
            f"{name} passes the module path as an argument: {argv}")


def test_the_source_tree_still_gets_dash_m(monkeypatch):
    """And the fix must not break the case that was working.

    The mirror of the test above. A change that made the frozen path right by
    making the source path wrong would pass that one and break every developer.
    """
    monkeypatch.setattr("sys.frozen", False, raising=False)
    monkeypatch.setattr("sys.executable", r"C:\Python312\python.exe")
    for name, build in BUILDERS:
        argv = build()
        assert argv[1:3] == ["-m", "scrapex.cli"], f"{name} lost its -m: {argv}"


def test_the_subcommand_survives_the_translation(frozen):
    """The argv must still SAY what to do, in the place the entry point looks.

    `engine_argv` could satisfy every assertion above by returning `[exe]` and
    dropping the arguments, and the engine would start and do nothing. So the
    subcommand is checked where `engine_entry.main` reads it: the first
    non-dash argument.
    """
    argv = relaunch._engine_command(8000)
    positional = [a for a in argv[1:] if not a.startswith("-")]
    assert positional and positional[0] == "ui", (
        f"the frozen relaunch does not ask for `ui` first: {argv}")
    assert "8000" in argv, f"the port was dropped in translation: {argv}"


def test_a_frozen_startup_entry_does_not_cd_into_a_directory_that_will_be_deleted(frozen):
    """autostart's THIRD bug, and the one with the longest fuse.

    Its command was `cmd /c cd /d "{repo}" && ...` where `repo` was
    `Path(__file__).parent.parent`. Inside a one-file build that is the
    PyInstaller unpack directory under %TEMP%, **deleted when the process
    exits** — so a frozen install that enabled autostart wrote a Startup entry
    naming a directory that would not exist at the next boot. It would fail
    silently, at boot, once, months later.
    """
    assert enginelaunch.working_directory() is None, (
        "a frozen build still claims a working directory; the only one it has is "
        "the unpack dir, and that is gone by the time anything reads this")
    command = autostart._command(8000)
    assert "cd /d" not in command, f"the frozen Startup entry still cds: {command}"
    assert "scrapex-engine.exe" in command
    assert "-m scrapex.cli" not in command, f"still passing -m: {command}"


def test_a_source_startup_entry_keeps_its_working_directory(monkeypatch):
    """The mirror again: the source install's `cd` was not a bug and stays."""
    monkeypatch.setattr("sys.frozen", False, raising=False)
    monkeypatch.setattr("sys.executable", r"C:\Python312\python.exe")
    assert enginelaunch.working_directory() == ROOT
    assert "cd /d" in autostart._command(8000)


def test_the_scheduled_task_runs_the_binary_and_not_a_module(frozen):
    """`schtasks` takes ONE string, so this one is a quoting question too."""
    command = osschedule.task_command()
    assert "-m scrapex.cli" not in command, f"still passing -m: {command}"
    assert "run-due" in command, f"the task forgot what to do: {command}"
    assert command.startswith('"'), (
        f"the program is unquoted, and its path contains spaces on any real "
        f"machine: {command}")


def test_a_frozen_runner_ignores_a_pythonw_that_really_is_there(tmp_path, monkeypatch):
    """The quiet half of OP-36, and it needs a pythonw that EXISTS to mean anything.

    `interpreter.with_name("pythonw.exe")` cannot resolve beside
    `scrapex-engine.exe` on a normal machine, so the console-hiding that
    autostart and the Scheduled Task both document as their reason for existing
    could not work in the build a user installs.

    THE FIRST VERSION OF THIS TEST PASSED FOR THE WRONG REASON, and mutating it
    is what showed that: it pointed `sys.executable` at a path that did not
    exist, so re-adding the probe changed nothing and the assertion held anyway.
    A real `pythonw.exe` beside a real .exe is the only arrangement that can
    tell "frozen returns itself" from "the probe happened to miss" -- and it is
    not far-fetched, since dropping the engine into a Python directory is
    exactly how someone would produce it.
    """
    exe = tmp_path / "scrapex-engine.exe"
    exe.write_bytes(b"MZ")
    decoy = tmp_path / "pythonw.exe"
    decoy.write_bytes(b"MZ")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(exe))

    assert enginelaunch.runner(windowless=True) == exe, (
        "a frozen engine picked the pythonw.exe sitting beside it; that is a "
        "Python interpreter, and handing it our arguments starts nothing")
    assert enginelaunch.runner(windowless=False) == exe
    assert enginelaunch.engine_argv("ui")[0] == str(exe)


def test_a_source_runner_does_prefer_pythonw_when_it_is_there(tmp_path, monkeypatch):
    """And the mirror, so the frozen branch cannot be fixed by gutting the probe.

    Without this, deleting the `windowless` handling entirely would satisfy the
    test above and silently give every source install a flashing console.
    """
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"MZ")
    decoy = tmp_path / "pythonw.exe"
    decoy.write_bytes(b"MZ")
    monkeypatch.setattr("sys.frozen", False, raising=False)
    monkeypatch.setattr("sys.executable", str(interpreter))

    assert enginelaunch.runner(windowless=True) == decoy, (
        "a source install stopped preferring pythonw, so autostart and the "
        "Scheduled Task will flash a console at the owner again")
    assert enginelaunch.runner(windowless=False) == interpreter


# --------------------------------------------------------------------- OP-35

def _entry_module():
    """Loaded by path: the repo's `packaging/` is shadowed by the PyPI one."""
    entry = ROOT / "packaging" / "engine_entry.py"
    spec = importlib.util.spec_from_file_location("scrapex_engine_entry_f", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_shipped_binary_can_be_asked_every_command_the_cli_has():
    """THE DRIFT, CLOSED BY DERIVATION RATHER THAN BY A LONGER LIST.

    Extending the literal would have fixed today and drifted again; this asserts
    the two sets are the SAME OBJECT of truth, so a subcommand added tomorrow is
    reachable from the shipped binary the same day.
    """
    known = _entry_module().known_commands()
    real = scrapex_cli.subcommands()
    assert known == real, (
        f"the frozen entry point and the CLI disagree about what a subcommand "
        f"is. Unreachable from the shipped binary: {sorted(real - known)}. "
        f"Accepted but not real: {sorted(known - real)}")


def test_the_twelve_that_were_unreachable_are_named_here_so_a_regression_is_loud():
    """A regression test with the actual casualties in it.

    The set above would still pass if both sides shrank together. These twelve
    were measured missing on the published 0.2.1, and two of them are the ones a
    stuck user and a worried user reach for.
    """
    known = _entry_module().known_commands()
    was_missing = {
        "autostart", "backup-databases", "carry-over", "contractors",
        "database-status", "export-version", "relaunch", "restore-database",
        "run-due", "schedule", "sources", "wipe-source",
    }
    assert was_missing <= known, (
        f"unreachable from the shipped binary again: {sorted(was_missing - known)}")


def test_the_cli_is_the_authority_and_it_is_not_empty():
    """`subcommands()` reaches into argparse's privates; prove it still reaches.

    If argparse changes shape, the sweep finds no subparsers. Returning an empty
    set there would make EVERY argument look like Chrome — the original defect,
    total instead of partial — so it raises instead, and this pins that it does
    not simply come back empty.
    """
    real = scrapex_cli.subcommands()
    assert len(real) >= 20, f"only {len(real)} subcommands found: {sorted(real)}"
    assert "ui" in real and "database-status" in real
    parser = scrapex_cli.build_parser()
    subparsers = [a for a in parser._actions
                  if isinstance(a, argparse._SubParsersAction)]
    assert len(subparsers) == 1, (
        "build_parser no longer has exactly one subparser group; subcommands() "
        "returns the first and would be picking arbitrarily")


def test_relaunch_is_reachable_because_the_engine_spawns_it_by_name():
    """The sharpest single entry on the missing list, and it ties the two OPs.

    `spawn_helper` starts a child with the `relaunch` subcommand. It was not in
    the hand-written set — so even once OP-36 put the right argv on the command
    line, the child would still have been refused and become a native host.
    Fixing one without the other fixes nothing.
    """
    known = _entry_module().known_commands()
    argv = enginelaunch.engine_argv("relaunch", "--port", "8000", windowless=False)
    positional = [a for a in argv[1:] if not a.startswith("-")]
    asked = [a for a in positional if a in known]
    assert asked, (
        f"the engine spawns {positional} and the entry point recognises none of "
        f"it, so the child becomes a silent native host: {argv}")
