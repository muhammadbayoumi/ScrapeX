"""Restart the engine from inside the engine (the owner uses no terminal).

There is one fault only new code can repair: a database written by a NEWER
build than the process reading it. The guard is right to refuse — an older
build cannot know what the newer one changed, and letting it write would be
silent corruption — but that leaves exactly one way out, and until now it was a
command in a terminal. The owner does not use one. So the engine restarts
itself.

IT CANNOT DO THIS ALONE. A process cannot free its own port and then bind it,
and if it exits first there is nobody left to start the replacement. So it hands
the job to a small detached helper that outlives it:

    engine  ──spawns──>  helper  ──waits for the port to close──>  new engine
       │
       └── exits a moment later, after its answer has been delivered

The helper is deliberately dumb and patient: it polls the port, starts the
engine, then polls again to confirm something answers. If the engine does not
come back it says so in the log rather than exiting quietly, because the owner's
only other route is the Startup launcher and he needs to know he has to use it.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# How long to wait for the old process to release the port before starting the
# new one. Generous: an engine mid-request keeps the socket a moment, and
# starting a second engine on a busy port is a failure with no recovery.
PORT_FREE_TIMEOUT_S = 30.0
# How long to wait for the new engine to answer before reporting that it did not.
ENGINE_UP_TIMEOUT_S = 90.0
POLL_S = 0.5


def port_busy(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.4)
        return probe.connect_ex((host, port)) == 0


def _engine_command(port: int) -> list[str]:
    """The same engine the Startup launcher runs, windowless where possible."""
    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    runner = windowless if windowless.exists() else interpreter
    return [str(runner), "-m", "scrapex.cli", "ui", "--port", str(int(port)), "--no-open"]


# One file, four writers (this module twice, native._spawn_engine, and the
# autostart launcher's shell redirect), and until now no ceiling on any of them.
# It is also the file every failure message sends the owner to — "Open Logs to
# see why" — so the one thing it may not become is too large to open.
MAX_ENGINE_LOG_BYTES = 5 * 1024 * 1024
ENGINE_LOG_KEEP = 1          # engine.log + engine.log.1: yesterday is enough


def rotate_engine_log(path: Path | None = None) -> bool:
    """Roll the engine log aside if it has grown past the cap. True if rolled.

    Rotation NEVER blocks a start: on Windows a detached process still holding
    the file makes the rename fail, and refusing to launch the engine because
    its log could not be tidied would be the housekeeping outranking the point.
    The failure is not silent either — the caller writes it INTO the log.
    """
    target = path or engine_log()
    try:
        if not target.exists() or target.stat().st_size < MAX_ENGINE_LOG_BYTES:
            return False
        previous = target.with_suffix(target.suffix + f".{ENGINE_LOG_KEEP}")
        previous.unlink(missing_ok=True)
        target.rename(previous)
        return True
    except OSError:
        return False


def open_engine_log(path: Path | None = None):
    """The engine log, rotated if due, opened for append. The ONE way in."""
    target = path or engine_log()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_engine_log(target)
    return open(target, "ab")


def _spawn_detached(command: list[str], cwd: Path, log: Path) -> int:
    """Start a process that survives this one. Its output goes to the engine log."""
    handle = open_engine_log(log)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    try:
        process = subprocess.Popen(command, cwd=str(cwd), stdout=handle, stderr=handle,
                                   creationflags=flags, close_fds=True)
    finally:
        # The child holds its own inherited handle; ours has no further use and
        # an unclosed one keeps the file locked against the next rotation.
        handle.close()
    return process.pid


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def engine_log() -> Path:
    return Path.home() / ".scrapex" / "engine.log"


def spawn_helper(port: int, pid: int | None = None) -> int:
    """Start the detached helper that will bring the engine back. Returns its pid."""
    interpreter = Path(sys.executable)
    command = [str(interpreter), "-m", "scrapex.cli", "relaunch",
               "--port", str(int(port)), "--wait-pid", str(int(pid or os.getpid()))]
    return _spawn_detached(command, repo_root(), engine_log())


def relaunch(port: int, wait_pid: int | None = None) -> int:
    """The helper's whole life: wait for the port, start the engine, confirm it.

    Runs in its own process, detached from the engine that asked for it — so it
    is still alive when that engine exits, which is the entire point.
    """
    say = lambda text: print(f"[relaunch] {text}", flush=True)  # noqa: E731
    deadline = time.monotonic() + PORT_FREE_TIMEOUT_S
    while port_busy(port) and time.monotonic() < deadline:
        time.sleep(POLL_S)
    if port_busy(port):
        # Starting a second engine on a held port would fail to bind and leave
        # the owner with the old build still running and no message.
        say(f"port {port} is still held after {PORT_FREE_TIMEOUT_S:.0f}s — "
            "the old engine did not exit; not starting a second one")
        return 1

    pid = _spawn_detached(_engine_command(port), repo_root(), engine_log())
    say(f"started the engine (pid {pid}) on port {port}")

    deadline = time.monotonic() + ENGINE_UP_TIMEOUT_S
    while not port_busy(port) and time.monotonic() < deadline:
        time.sleep(POLL_S)
    if port_busy(port):
        say("the engine is answering")
        return 0
    say(f"the engine did not answer within {ENGINE_UP_TIMEOUT_S:.0f}s — "
        "start it from the Startup folder (ScrapeX Engine.vbs) or sign out and in")
    return 1
