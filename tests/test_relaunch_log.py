"""The engine log has four writers and had no ceiling on any of them.

It is also the file every failure message in the panel points the owner at
("Open Logs to see why"), so the one state it may not reach is too large to
open — and the rotation that prevents that may never be what stops an engine
from starting.
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
