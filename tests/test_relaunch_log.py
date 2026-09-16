"""The engine log has four writers and had no ceiling on any of them.

It is also the file every failure message in the panel points the owner at
("Open Logs to see why"), so the one state it may not reach is too large to
open — and the rotation that prevents that may never be what stops an engine
from starting.

The second half is the helper those writers exist for (`#962`): seventeen
statements nothing had ever executed, because they only run in a detached
process no test drives. It is the only thing standing between the owner and an
engine that never comes back.
"""
from __future__ import annotations

from pathlib import Path

from scrapex import relaunch


def test_a_log_under_the_cap_is_left_exactly_as_it_is(tmp_path: Path):
    log = tmp_path / "engine.log"
    log.write_bytes(b"a line\n")
    assert relaunch.rotate_engine_log(log) is False
    assert log.read_bytes() == b"a line\n"
    assert not (tmp_path / "engine.log.1").exists()


def test_a_log_past_the_cap_is_rolled_aside_and_the_history_kept(tmp_path: Path):
    log = tmp_path / "engine.log"
    log.write_bytes(b"x" * (relaunch.MAX_ENGINE_LOG_BYTES + 1))

    assert relaunch.rotate_engine_log(log) is True

    assert not log.exists(), "the live log was not rolled aside"
    rolled = tmp_path / "engine.log.1"
    assert rolled.stat().st_size == relaunch.MAX_ENGINE_LOG_BYTES + 1, \
        "yesterday's log was lost rather than kept"


def test_rotating_twice_keeps_one_generation_not_a_growing_pile(tmp_path: Path):
    log = tmp_path / "engine.log"
    for marker in (b"first", b"second"):
        log.write_bytes(marker + b"x" * relaunch.MAX_ENGINE_LOG_BYTES)
        relaunch.rotate_engine_log(log)
    assert (tmp_path / "engine.log.1").read_bytes()[:6] == b"second"
    assert not (tmp_path / "engine.log.2").exists()


def test_a_missing_log_is_a_first_run_not_a_failure(tmp_path: Path):
    assert relaunch.rotate_engine_log(tmp_path / "engine.log") is False


def test_open_engine_log_creates_the_folder_and_appends(tmp_path: Path):
    log = tmp_path / "nested" / "engine.log"
    handle = relaunch.open_engine_log(log)
    try:
        handle.write(b"one\n")
    finally:
        handle.close()
    handle = relaunch.open_engine_log(log)
    try:
        handle.write(b"two\n")
    finally:
        handle.close()
    assert log.read_bytes() == b"one\ntwo\n", "the log was truncated, not appended to"


def test_a_rotation_that_cannot_happen_never_stops_a_start(tmp_path: Path, monkeypatch):
    """On Windows a detached process still holding the file makes the rename
    fail. Refusing to launch the engine because its log could not be tidied
    would be the housekeeping outranking the point of the housekeeping."""
    log = tmp_path / "engine.log"
    log.write_bytes(b"y" * (relaunch.MAX_ENGINE_LOG_BYTES + 1))

    def _locked(self, target):
        raise OSError(32, "The process cannot access the file")

    monkeypatch.setattr(Path, "rename", _locked)

    assert relaunch.rotate_engine_log(log) is False
    handle = relaunch.open_engine_log(log)      # must still hand back a log
    try:
        handle.write(b"the engine started anyway\n")
    finally:
        handle.close()
    assert log.read_bytes().endswith(b"the engine started anyway\n")


def test_a_log_the_live_engine_is_holding_does_not_block_the_restart(tmp_path, monkeypatch):
    r"""Reproduced on the owner's machine: the button answered 500 with
    "could not start the helper ([Errno 13] Permission denied:
    ...\.scrapex\engine.log)".

    On Windows the running engine holds engine.log through the stdout handle it
    was launched with, and that handle carries no write sharing — so a second
    opener gets EACCES while the file is plainly writable (mode 0o666,
    os.access says yes; measured). And that is the ONLY state a restart ever
    runs in: the engine being replaced is still running. So the one action that
    repairs a stuck engine could never start, on any Windows machine.

    Housekeeping does not outrank the point."""
    from scrapex import relaunch

    log = tmp_path / "engine.log"
    log.write_bytes(b"held by the live engine\n")

    def held(path=None):
        raise PermissionError(13, "Permission denied", str(log))

    monkeypatch.setattr(relaunch, "open_engine_log", held)
    recorded = {}

    class _Popen:
        def __init__(self, command, **kwargs):
            recorded["stdout"] = kwargs.get("stdout")
            self.pid = 4242

    monkeypatch.setattr(relaunch.subprocess, "Popen", _Popen)

    pid = relaunch._spawn_detached(["python", "-c", "pass"], tmp_path, log)

    assert pid == 4242, "the helper did not launch when the main log was held"
    assert recorded["stdout"] is not None, "it launched with nowhere to write"
    assert relaunch._restart_log(log).exists(), (
        "the helper's output has no file beside the one it could not open")


def test_the_fallback_log_sits_beside_the_one_it_replaces(tmp_path):
    """Read by the same person, from the same folder, on the same bad day."""
    from scrapex import relaunch

    log = tmp_path / "engine.log"
    assert relaunch._restart_log(log).parent == log.parent
    assert relaunch._restart_log(log).name.startswith(log.name)


# --- the helper itself: `relaunch()`, which nothing had ever executed ---------
#
# Its three timeouts are real seconds (30s for the port, 90s for the engine),
# so a test that let the clock run would cost two minutes to learn nothing. The
# three stand-ins below replace the only three things it touches outside
# itself: the clock, the socket probe, and the process launcher.


class _Clock:
    """A clock the test drives: sleeping is what moves it, and it costs nothing.

    Stands in for the `time` module rather than patching `time.sleep` on the
    real one, because `relaunch` reads both `monotonic` and `sleep` through its
    module global and the suite runs in parallel — a shared stdlib `sleep` is
    not ours to rebind. Advancing the clock by exactly what was slept keeps the
    timeouts honest: a loop still ends when its real budget is spent.
    """

    # A wait loop that never ends is a defect in `relaunch`; against a clock that
    # moves ONLY when something sleeps it is an infinite loop in the test. This
    # suite runs in parallel and configures no pytest timeout, so one spinning
    # worker takes the whole run down with it and nothing says why. Measured: with
    # `POLL_S = 0.0` — a busy-spin on the socket probe, and a defect a reader
    # would name — pytest hung indefinitely instead of going red. Past this many
    # polls the clock reports the runaway rather than joining it.
    MAX_POLLS = 10_000

    def __init__(self):
        self.now = 0.0
        self.slept = 0.0
        self.polls = 0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.polls += 1
        if self.polls > self.MAX_POLLS:
            raise AssertionError(
                f"the wait loop never ended: {self.polls} polls and the deadline "
                "is still ahead — POLL_S no longer advances the clock")
        self.now += seconds
        self.slept += seconds


class _PortAnswers:
    """`port_busy` with its answers written in advance — one per call, the last
    repeating for ever. No socket is opened, and the wait loops end on an
    answer the test chose rather than on a clock."""

    def __init__(self, *answers: bool):
        self.answers = list(answers)
        self.asked = 0
        # WHICH port, not just how many times. Scripted answers are returned
        # regardless of the argument, so without this a helper that polled a
        # hardcoded port would be handed the right answers about the wrong
        # socket and every test below would still pass.
        self.asked_about: list[int] = []

    def __call__(self, port: int, host: str = "127.0.0.1") -> bool:
        self.asked += 1
        self.asked_about.append(port)
        return self.answers[min(self.asked - 1, len(self.answers) - 1)]


class _Spawns:
    """`_spawn_detached` with the process taken out: it starts nothing, opens
    nothing under `~/.scrapex`, and remembers every time it was asked."""

    def __init__(self, pid: int = 7777):
        self.pid = pid
        self.calls: list[tuple[list[str], Path, Path]] = []

    def __call__(self, command: list[str], cwd: Path, log: Path) -> int:
        self.calls.append((list(command), cwd, log))
        return self.pid


def _drive(monkeypatch, *port_answers: bool):
    """Install the three stand-ins. Returns them in the order they are read."""
    clock, ports, spawns = _Clock(), _PortAnswers(*port_answers), _Spawns()
    monkeypatch.setattr(relaunch, "time", clock)
    monkeypatch.setattr(relaunch, "port_busy", ports)
    monkeypatch.setattr(relaunch, "_spawn_detached", spawns)
    return clock, ports, spawns


def test_a_port_that_never_frees_never_gets_a_second_engine(monkeypatch, capsys):
    """The path with no recovery, which is why it is the one that matters.

    A second engine on a held port fails to bind and dies, and the owner is
    left with the old build still running and nothing said. So what this
    asserts is the call count, not the return value: a helper that spawns
    anyway can still answer 1."""
    clock, ports, spawns = _drive(monkeypatch, True)      # busy on every poll

    assert relaunch.relaunch(8765) == 1

    assert spawns.calls == [], (
        "a second engine was started on a port the old one still holds")
    assert set(ports.asked_about) == {8765}, (
        f"it waited on a port nobody asked for: {sorted(set(ports.asked_about))}")
    assert clock.slept >= relaunch.PORT_FREE_TIMEOUT_S, (
        "it gave up before the old engine had its full window to exit")
    assert clock.slept >= 30.0, (
        "the window itself was cut. The line above compares the wait only to the "
        "constant that sets it, so gutting PORT_FREE_TIMEOUT_S passes it; shortening "
        "how long a busy engine gets to release the port is his call, not a refactor's")
    said = capsys.readouterr().out
    assert "still held" in said and "not starting a second one" in said, said


def test_the_port_frees_and_the_engine_it_starts_is_the_engine(monkeypatch, capsys):
    # Held on the first poll, free on the next two, then answering.
    _clock, ports, spawns = _drive(monkeypatch, True, False, False, False, True)

    assert relaunch.relaunch(8765) == 0

    assert len(spawns.calls) == 1, "the engine was not started exactly once"
    command, cwd, log = spawns.calls[0]
    assert command == relaunch._engine_command(8765), (
        "it started something other than the engine `_engine_command` builds — "
        "the frozen build's failure mode, a mute native host instead of an engine")
    # And spelled out, because the line above is only ever as strong as
    # `_engine_command` itself: an engine, on the port asked for, quietly.
    assert command[-4:] == ["ui", "--port", "8765", "--no-open"], (
        f"the child is not a quiet engine on the port that was asked for: {command}")
    assert cwd == relaunch.repo_root(), "the engine was started outside the repository"
    # Spelled out for the same reason as the line above the command check: that
    # assertion compares `repo_root()` to itself, so a `repo_root` that returned
    # the filesystem root would satisfy it. This names what a checkout IS.
    assert (cwd / "scrapex" / "relaunch.py").exists(), (
        f"the engine was started somewhere that is not a checkout: {cwd}")
    assert log == relaunch.engine_log(), (
        f"the restart narrates into a file nobody opens: {log}, not "
        f"{relaunch.engine_log()} — the one every panel failure points him at")
    assert set(ports.asked_about) == {8765}, (
        f"it watched a port nobody asked for: {sorted(set(ports.asked_about))}")
    said = capsys.readouterr().out
    assert "started the engine (pid 7777)" in said, said
    assert "answering" in said, said


def test_an_engine_that_never_answers_names_the_startup_folder(monkeypatch, capsys):
    """He works only from the panel, and the panel is exactly what did not come
    back. The one route left him is the Startup launcher, so the last message
    he gets has to name it — a `scrapex ...` line is not an answer to him."""
    clock, _ports, spawns = _drive(monkeypatch, False)     # free, never answers

    assert relaunch.relaunch(8765) == 1

    assert len(spawns.calls) == 1, "it reported a failure it never tried"
    assert clock.slept >= relaunch.ENGINE_UP_TIMEOUT_S, (
        "it called the engine dead before its full window to come up")
    assert clock.slept >= 90.0, (
        "the window itself was cut. As above: the line before it only compares the "
        "wait to ENGINE_UP_TIMEOUT_S, so gutting that constant passes it, and an "
        "engine declared dead early sends him to the Startup folder for nothing")
    said = capsys.readouterr().out
    assert "did not answer" in said, said
    assert "Startup folder" in said and "ScrapeX Engine.vbs" in said, said
    assert "-m scrapex" not in said, (
        "the last thing the owner is told is a terminal command he will not run")


def test_the_port_decides_it_came_back_not_the_pid_it_was_handed(monkeypatch):
    """`cli.py:737` calls this with two positional arguments, the second being
    the pid of the engine being replaced. The helper watches the port and not
    the process, so a pid that is already gone must change nothing."""
    _clock, _ports, spawns = _drive(monkeypatch, False, False, True)

    assert relaunch.relaunch(8765, 2 ** 31 - 1) == 0
    assert len(spawns.calls) == 1
