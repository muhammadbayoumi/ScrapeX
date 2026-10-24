"""The engine tells Windows it is not background work (#1767, ES-6).

Started through the native host, the engine descends from Chrome, and Windows schedules
a windowless process by the window its ancestry owns. Measured on his machine, a
`pythonw` with no focused ancestor spent 4.4x the CPU-s of the same work, and the call
pinned here brought it back to 1.0x.

The fakes check the call on every platform, CI's Linux included. The last test makes the
real call on Windows and reads the process's state back through Windows itself.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import pathlib
import subprocess
import sys

import pytest

from scrapex import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
PSEUDO_HANDLE = 0xFFFFFFFFFFFFFFFF          # what GetCurrentProcess returns on x64


class FakeFunction:
    """A kernel32 export: takes `restype`/`argtypes` like a ctypes one, records calls."""

    def __init__(self, result):
        self.result, self.calls = result, []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class FakeKernel32:
    def __init__(self, *, accepted: bool = True, has_function: bool = True):
        self.GetCurrentProcess = FakeFunction(PSEUDO_HANDLE)
        if has_function:
            self.SetProcessInformation = FakeFunction(1 if accepted else 0)


@pytest.fixture
def on_windows(monkeypatch):
    """`sys.platform` says win32, and `ctypes.WinDLL("kernel32")` is the fake."""
    made: list[FakeKernel32] = []

    def install(kernel32: FakeKernel32, last_error: int = 0):
        def win_dll(name, use_last_error=False):
            assert name == "kernel32" and use_last_error, (name, use_last_error)
            made.append(kernel32)
            return kernel32
        monkeypatch.setattr(cli.sys, "platform", "win32")
        monkeypatch.setattr(ctypes, "WinDLL", win_dll, raising=False)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: last_error, raising=False)
        # Off Windows `ctypes.WinError` does not exist; this is its documented shape.
        monkeypatch.setattr(ctypes, "WinError",
                            lambda code: OSError(None, f"Windows error {code}", None, code),
                            raising=False)
        return made
    return install


def records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_on_windows_the_engine_asks_for_high_qos_with_the_documented_masks(on_windows, capsys):
    kernel32 = FakeKernel32()
    on_windows(kernel32)

    cli._opt_out_of_eco_qos()

    (call,) = kernel32.SetProcessInformation.calls
    handle, info_class, state_ref, size = call
    state = state_ref._obj          # the structure `ctypes.byref` points at
    assert handle == PSEUDO_HANDLE, "the call must be made on the engine's own process"
    assert info_class == 4, "ProcessPowerThrottling is class 4 in processthreadsapi.h"
    assert (state.Version, state.ControlMask, state.StateMask) == (1, 0x1, 0x0), (
        "HighQoS is ControlMask = EXECUTION_SPEED with StateMask = 0; a StateMask of "
        "EXECUTION_SPEED would opt the engine INTO EcoQoS")
    assert size == ctypes.sizeof(state) == 12
    assert kernel32.SetProcessInformation.argtypes[0] is ctypes.c_void_p, (
        "a pointer-sized handle, or x64 passes a truncated -1")
    assert kernel32.GetCurrentProcess.restype is ctypes.c_void_p
    assert capsys.readouterr().err == "", "an accepted call writes nothing"


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_elsewhere_no_windows_call_is_made(platform, monkeypatch, capsys):
    def win_dll(*_args, **_kwargs):
        raise AssertionError("kernel32 was loaded off Windows")
    monkeypatch.setattr(cli.sys, "platform", platform)
    monkeypatch.setattr(ctypes, "WinDLL", win_dll, raising=False)

    assert cli._opt_out_of_eco_qos() is None
    assert capsys.readouterr().err == ""


def test_a_refused_call_is_recorded_and_the_engine_goes_on(on_windows, capsys):
    """An older Windows without ProcessPowerThrottling refuses it with error 87."""
    kernel32 = FakeKernel32(accepted=False)
    on_windows(kernel32, last_error=87)

    cli._opt_out_of_eco_qos()

    assert len(kernel32.SetProcessInformation.calls) == 1
    (record,) = records(capsys.readouterr().err)
    assert record["event"] == "eco_qos_opt_out_failed"
    assert record["error"].startswith("OSError") and "87" in record["error"], record
    assert "efficiency cores" in record["effect"]
    assert record["at"].endswith("Z"), record["at"]


def test_a_kernel32_without_the_function_is_recorded_and_the_engine_goes_on(on_windows, capsys):
    """Before Windows 8 kernel32 has no SetProcessInformation at all."""
    on_windows(FakeKernel32(has_function=False))

    cli._opt_out_of_eco_qos()

    (record,) = records(capsys.readouterr().err)
    assert record["event"] == "eco_qos_opt_out_failed"
    assert record["error"].startswith("AttributeError"), record


def test_a_kernel32_that_will_not_load_is_recorded_and_the_engine_goes_on(monkeypatch, capsys):
    def win_dll(*_args, **_kwargs):
        raise OSError(126, "The specified module could not be found")
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", win_dll, raising=False)

    cli._opt_out_of_eco_qos()

    (record,) = records(capsys.readouterr().err)
    assert record["event"] == "eco_qos_opt_out_failed"
    assert "could not be found" in record["error"], record


def test_the_ui_command_opts_out_after_binding_its_log_and_before_any_database(monkeypatch):
    """After the streams, so a refusal has somewhere to go under pythonw; before the
    registry, because the start's migrations are the heaviest thing it does."""
    pytest.importorskip("uvicorn")
    order: list[str] = []

    class Stop(Exception):
        pass

    def registry():
        order.append("database")
        raise Stop

    monkeypatch.setattr(cli, "_bind_log_streams", lambda: order.append("log"))
    monkeypatch.setattr(cli, "_opt_out_of_eco_qos", lambda: order.append("qos"))
    monkeypatch.setattr(cli.DatabaseRegistry, "defaults", staticmethod(registry))

    with pytest.raises(Stop):
        cli._cmd_ui(argparse.Namespace(db=None, host="127.0.0.1", port=0, no_open=True))
    assert order == ["log", "qos", "database"]


READ_OWN_STATE = """
import ctypes, sys
from ctypes import wintypes
import scrapex.cli as cli
assert hasattr(cli, "_opt_out_of_eco_qos"), cli.__file__
if sys.argv[1] == "call":
    cli._opt_out_of_eco_qos()
class State(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG)]
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.GetCurrentProcess.restype = wintypes.HANDLE
k32.GetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                      wintypes.DWORD]
state = State(1, 0, 0)
ok = k32.GetProcessInformation(k32.GetCurrentProcess(), 4, ctypes.byref(state), 12)
assert ok, ctypes.get_last_error()
print(state.ControlMask, state.StateMask)
"""


@pytest.mark.skipif(sys.platform != "win32", reason="the real call exists only on Windows")
def test_on_real_windows_the_process_reads_back_as_high_qos():
    """Windows' own answer, in a fresh process. Without the call it reads 0 0, which
    proves the read reflects the call rather than a default."""
    def own_state(arg: str) -> str:
        done = subprocess.run([sys.executable, "-c", READ_OWN_STATE, arg], cwd=ROOT,
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        assert done.stderr == "", done.stderr
        return done.stdout.strip()

    assert own_state("none") == "0 0"
    assert own_state("call") == "1 0", "EXECUTION_SPEED controlled, and off: HighQoS"
