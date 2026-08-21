"""How this engine starts another copy of itself — source tree or frozen .exe.

FIVE PLACES START A CHILD ENGINE and four of them got it wrong the same way, which
is why this module exists instead of a fifth variation of the same three lines:

    scrapex/relaunch.py     the engine a relaunch brings back, and the helper
                            that brings it
    scrapex/native.py       the engine Chrome's native host starts
    scrapex/autostart.py    the Startup entry
    scrapex/osschedule.py   the Scheduled Task
    scrapex/nativehost.py   Chrome's launcher — the ONE that was already right,
                            and the precedent this module generalises

THE DEFECT, measured 2026-08-21 (`OP-36`). Each of the four built its child as

    [sys.executable, "-m", "scrapex.cli", "ui", ...]

which is correct for a source install and **silently wrong for the shipped
binary**. Under PyInstaller `sys.executable` is `scrapex-engine.exe`, and its
bootloader does not honour `-m`: those two become ordinary arguments. So
`packaging/engine_entry.py` receives `["-m", "scrapex.cli", "ui", ...]`, strips the
dash-arguments, finds `argv[0] == "scrapex.cli"`, does not recognise it, and falls
through to the Chrome native messaging host — which waits on stdin and prints
nothing. **The engine asks to be replaced and a mute stranger arrives.** It is the
same silent fall-through that shipped as the black window in `engine-v0.2.1`.

WHY A MODULE AND NOT A ONE-LINE FIX IN EACH. Two of the four also need to know
that a frozen build has no `pythonw.exe` beside it and no repository directory to
sit in, and those are the same question asked twice more. One place that answers
"how do I run myself again" answers all three.

NOTHING HERE IMPORTS FROM `scrapex` ITSELF. Every caller is low in the stack —
`autostart` and `osschedule` are reached while the engine is still coming up — so
this module stays at `sys` and `pathlib` and can never be part of an import cycle.
"""
from __future__ import annotations

import sys
from pathlib import Path


def frozen() -> bool:
    """Are we the one-file executable rather than a Python running our source?

    `sys.frozen` is what PyInstaller sets and what `scrapex/nativehost.py:57`
    already tested; this is that test, named once so the other callers stop
    forgetting to make it.
    """
    return bool(getattr(sys, "frozen", False))


def runner(*, windowless: bool = True) -> Path:
    """The program to execute in order to be us again.

    Frozen: the executable itself, and `windowless` is not merely ignored but
    MEANINGLESS — there is no `pythonw.exe` beside `scrapex-engine.exe`, so the
    old `with_name("pythonw.exe")` probe always failed and every caller quietly
    fell back to the console build. That is why a frozen Scheduled Task blinks a
    window every fifteen minutes: the code that exists to prevent it cannot work.
    Hiding the console of a frozen build is a build-time decision
    (`--windowed`), not a runtime one, and pretending otherwise here would be
    the same lie in a new place.
    """
    interpreter = Path(sys.executable)
    if frozen():
        return interpreter
    if windowless:
        candidate = interpreter.with_name("pythonw.exe")
        if candidate.exists():
            return candidate
    return interpreter


def engine_argv(*args: str, windowless: bool = True) -> list[str]:
    """The argv that runs `scrapex <args>` again, whichever way we were started.

    The whole point is the `-m scrapex.cli` pair, which must be present for a
    source install and absent for a frozen one. Callers pass only the
    subcommand and its options and never think about it again.
    """
    program = str(runner(windowless=windowless))
    if frozen():
        return [program, *args]
    return [program, "-m", "scrapex.cli", *args]


def engine_command(*args: str, windowless: bool = True) -> str:
    """The same thing as ONE command line, for `schtasks` and the .bat/.vbs pair.

    Only the program is quoted unconditionally, because it is the part that
    routinely contains a space (`C:\\Program Files\\...`); an argument is quoted
    only when it actually needs it, which keeps these lines readable in the
    Registry and in Task Scheduler where a human has to recognise them.
    """
    program, *rest = engine_argv(*args, windowless=windowless)
    parts = [f'"{program}"']
    parts += [f'"{arg}"' if " " in arg else arg for arg in rest]
    return " ".join(parts)


def working_directory() -> Path | None:
    """Where a child engine should be started, or None when it must NOT be told.

    **None for a frozen build, and this is the sharp one.** A one-file binary
    unpacks itself into a directory under `%TEMP%` and DELETES IT WHEN THE
    PROCESS EXITS, so `Path(__file__).parent.parent` — which is what the callers
    used — names a directory that will not exist the next time anything reads
    the command. A Startup entry built that way points at nothing after the
    first reboot, and `OP-34` is why nobody would ever see why.

    For a source install the repository root is still returned, because that is
    what the existing behaviour is and this module is not the place to change
    it. `-m scrapex.cli` resolves through the interpreter's own site-packages
    (`pip install -e .`) rather than through the working directory, so the value
    is belt-and-braces there rather than load-bearing.
    """
    if frozen():
        return None
    return Path(__file__).resolve().parent.parent
