"""Let Windows hold the clock, so a schedule fires with everything closed.

`autostart` covers "the machine rebooted": the engine comes back with the
session. THIS covers the other half of set-and-forget — the owner is logged in
but the panel and the engine are shut, so `scheduler.fire_due` has no process
to run inside and a 09:00 slot passes unremarked. A per-user Scheduled Task is
the smallest thing on this machine that owns a clock we do not.

The autostart rules, restated rather than relaxed: no elevation (`/RL LIMITED`
runs at the owner's own rights), nothing written outside the owner's own scope
(the task lands in their personal task store, not the machine's), and turning
it off is ONE visible thing — `scrapex schedule remove`, or deleting the task
named below in taskschd.msc.

schtasks.exe rather than the Task Scheduler COM API: it ships with every
Windows, needs no pywin32, and when it refuses it refuses in a sentence we can
hand the owner verbatim instead of an HRESULT nobody can act on.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

TASK_NAME = "ScrapeX schedules"
DEFAULT_INTERVAL_MINUTES = 15
# /SC MINUTE tops out one minute short of a day; anything longer is a different
# /SC and would silently become "once daily" if we let it through.
MAX_INTERVAL_MINUTES = 1439

# schtasks writing to a pipe must not flash a console of its own — the whole
# point of this module is a schedule the owner never sees.
_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


class ScheduleTaskError(RuntimeError):
    """schtasks was unreachable or said no. Carries what it said, verbatim."""


def _schtasks() -> str:
    """The real schtasks.exe where we can name it, else whatever PATH finds.

    Naming the System32 copy keeps the command reproducible in the error
    message we print — "run this yourself" is only useful if `this` is exact.
    """
    system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    if system_root:
        candidate = Path(system_root) / "System32" / "schtasks.exe"
        if candidate.exists():
            return str(candidate)
    return "schtasks"


def _runner() -> Path:
    """The windowless interpreter — the same choice autostart makes.

    A task that fires every 15 minutes under python.exe would blink a black
    window at the owner all day; pythonw.exe has no console to show. Falls back
    to the plain interpreter only where pythonw genuinely does not exist.
    """
    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    return windowless if windowless.exists() else interpreter


def task_command() -> str:
    """The single line Windows runs on every tick.

    Deliberately NOT autostart's `cmd /c cd /d ... >> engine.log` wrapper: cmd
    is a console program, so Task Scheduler would pop a window every interval
    for the owner to watch — the exact thing autostart's VBS run-style 0 exists
    to prevent, and we have no VBS here because schtasks IS the launcher. So the
    interpreter is invoked directly and `run-due` writes its own log line
    instead of relying on a shell redirect. `-m scrapex.cli` resolves through
    the interpreter's own site-packages (`pip install -e .`), which is also how
    the engine is started, so the task needs no working directory of its own.
    """
    return f'"{_runner()}" -m scrapex.cli run-due'


def _refusal(result: subprocess.CompletedProcess, argv: list[str]) -> str:
    """What schtasks actually said, plus the command that said it.

    Never paraphrased: a refusal the owner cannot reproduce is a refusal they
    cannot fix, and a "task installed!" over the top of one would be a lie the
    owner only discovers the morning the crawl did not happen.
    """
    said = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
    return (f"Windows Task Scheduler refused (exit {result.returncode}): {said}\n"
            f"the exact command was: {subprocess.list2cmdline(argv)}")


def _run(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    argv = [_schtasks(), *arguments]
    try:
        # errors="replace": a localized Windows answers in its own code page and
        # a stray byte must never become a traceback in place of the message.
        result = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                                creationflags=_CREATION_FLAGS)
    except OSError as exc:
        raise ScheduleTaskError(
            f"schtasks could not be run here ({exc}). This needs Windows Task "
            f"Scheduler; on another platform, or a system without it, install a "
            f"cron/launchd entry for: {task_command()}") from exc
    if check and result.returncode != 0:
        raise ScheduleTaskError(_refusal(result, argv))
    return result


def install(interval_minutes: int = DEFAULT_INTERVAL_MINUTES) -> str:
    """Create (or replace) the task. Returns its name; raises on any refusal.

    Idempotent through /F, the same way autostart is idempotent through
    rewriting one file: re-installing after a move or a new interpreter fixes
    the command rather than stacking a second task.
    """
    interval = int(interval_minutes)
    if not 1 <= interval <= MAX_INTERVAL_MINUTES:
        raise ScheduleTaskError(
            f"the interval must be 1..{MAX_INTERVAL_MINUTES} minutes "
            f"(Windows' /SC MINUTE range), got {interval}")
    # The log home, before the first tick needs it — same reason autostart makes
    # it: a scheduled run with nowhere to write is undiagnosable the day it fails.
    (Path.home() / ".scrapex").mkdir(parents=True, exist_ok=True)
    _run([
        "/Create",
        "/TN", TASK_NAME,
        "/TR", task_command(),
        "/SC", "MINUTE",
        "/MO", str(interval),
        # LIMITED, never HIGHEST: this runs the owner's own crawls at the
        # owner's own rights. Nothing here has ever needed administrator.
        "/RL", "LIMITED",
        "/F",
    ])
    return TASK_NAME


def remove() -> bool:
    """Delete the task. True when there was one to delete.

    Asks before deleting rather than reading schtasks' "not found" wording,
    which is translated on a localized Windows — matching English text there
    would report a real refusal as "nothing was installed".
    """
    if not status()["installed"]:
        return False
    _run(["/Delete", "/TN", TASK_NAME, "/F"])
    return True


_REPEAT_HOURS = re.compile(r"(\d+)\s*Hour", re.IGNORECASE)
_REPEAT_MINUTES = re.compile(r"(\d+)\s*Minute", re.IGNORECASE)


def _interval_from_query(text: str) -> int | None:
    """Minutes, read back OFF the task instead of remembered next to it.

    A second copy of the interval in our own file would drift the first time
    the owner edits the task in taskschd.msc. None where we cannot read it —
    a localized Windows prints this row in its own words — because guessing 15
    would be indistinguishable from knowing it.
    """
    for line in text.splitlines():
        lowered = line.lower()
        if "repeat" not in lowered or "every" not in lowered:
            continue
        hours = _REPEAT_HOURS.search(line)
        minutes = _REPEAT_MINUTES.search(line)
        total = (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)
        if total:
            return total
    return None


def status() -> dict:
    """{"installed": bool, "path_or_name": str, "interval": int|None}.

    The task store's own answer IS the truth, exactly as the launcher file's
    existence is the truth for autostart — we keep no bookkeeping to disagree
    with. A non-zero /Query means "no such task"; an unreachable schtasks
    raises instead, because "not installed" and "cannot tell" are different
    answers and only one of them invites the owner to install again.
    """
    result = _run(["/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"], check=False)
    if result.returncode != 0:
        return {"installed": False, "path_or_name": TASK_NAME, "interval": None}
    return {"installed": True, "path_or_name": TASK_NAME,
            "interval": _interval_from_query(result.stdout or "")}
