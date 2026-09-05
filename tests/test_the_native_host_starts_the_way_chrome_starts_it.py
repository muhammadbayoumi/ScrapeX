"""The native host answers when launched the way Chrome actually launches it.

`tests/test_native.py` covers the protocol thoroughly — framing, every command, the
refusals. **Nothing covered the LAUNCH**, and that is where it was broken: Chrome
passes the calling extension's origin as a positional argument, and on Windows also
`--parent-window=<handle>`, and `scrapex native-host` accepted neither.

MEASURED 2026-09-03, launching it exactly as Chrome does:

    scrapex: error: unrecognized arguments:
      chrome-extension://ekcgggphcfdbjgfkcmjagehfjhijeang/
    exit: 2

`argparse` exited **before the host read one byte of stdin**, so every launch died
instantly. The panel reported *"Native helper unavailable — restarting through the
engine"* and fell back to HTTP, which is why the fallback looked like the feature.

THE REGISTRATION WAS NEVER THE PROBLEM, and checking it first is what made the real
cause findable: the manifest at `%LOCALAPPDATA%\\ScrapeX\\com.scrapex.engine.json`
existed with two allowed origins, the `HKCU` pointer under
`Software\\Google\\Chrome\\NativeMessagingHosts` matched it, and the `.bat` it named
existed and ran. Every part of the wiring was correct and the endpoint refused its own
arguments.

WHY A SUBPROCESS AND NOT A CALL INTO THE PARSER. The defect lived in the boundary
between what Chrome passes and what the process accepts, and a test that calls
`serve()` directly never crosses it — which is exactly why a thorough protocol suite
missed this for as long as the bridge has existed.
"""
from __future__ import annotations

import json
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

import pytest

from scrapex import nativehost

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: What Chrome hands a native messaging host. The origin is always there; the
#: window handle is Windows-only, and both are passed whether the host wants them.
CHROME_LAUNCHES = [
    pytest.param(["chrome-extension://ekcgggphcfdbjgfkcmjagehfjhijeang/"],
                 id="the-origin-alone"),
    pytest.param(["chrome-extension://ekcgggphcfdbjgfkcmjagehfjhijeang/",
                  "--parent-window=12345"], id="windows-adds-a-window-handle"),
]


def _framed(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return struct.pack("<I", len(body)) + body


def _launch(argv: list[str], message: dict) -> tuple[int, dict | None, str]:
    """Start the host as a process, from a neutral directory, and speak to it.

    `PYTHONPATH` points at THIS tree on purpose. `scrapex` is pip-installed
    editable against the main checkout, so a subprocess started from anywhere else
    imports that copy and the test would report on code it is not testing — a trap
    this repository has recorded and paid for.
    """
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    done = subprocess.run(
        [sys.executable, "-m", "scrapex.cli", "native-host", *argv],
        input=_framed(message), capture_output=True,
        cwd=tempfile.gettempdir(), env=env, timeout=180)
    out = done.stdout
    reply = None
    if len(out) >= 4:
        length = struct.unpack("<I", out[:4])[0]
        if len(out) >= 4 + length:
            reply = json.loads(out[4:4 + length])
    return done.returncode, reply, done.stderr.decode("utf-8", errors="replace")


@pytest.mark.parametrize("argv", CHROME_LAUNCHES)
def test_it_answers_when_launched_with_what_chrome_passes(argv):
    code, reply, stderr = _launch(argv, {"command": "PING"})

    assert code == 0, (
        f"the host exited {code} instead of serving. stderr:\n{stderr[:600]}\n"
        "If this is an argparse usage message, Chrome is passing something the "
        "parser refuses and the bridge cannot start at all — which is the defect "
        "this file exists for, and no protocol test can see it.")
    assert reply is not None, (
        f"the host wrote no framed reply. stderr:\n{stderr[:400]}")
    assert reply.get("ok") is True, reply
    assert reply.get("protocol_version"), (
        "the reply carries no protocol version, so the panel cannot tell whether "
        "it is talking to an engine it understands")


def test_an_unknown_flag_is_not_a_reason_to_refuse_to_start():
    """Chrome's launch arguments are not this host's contract, and a future Chrome
    adding one must not take the bridge down.

    The origin is NOT read here as an authorisation check: `allowed_origins` in the
    manifest is, and Chrome enforces it before the process exists. A second, weaker
    check in a place that cannot be trusted with one is worse than none.
    """
    code, reply, stderr = _launch(
        ["chrome-extension://whatever/", "--parent-window=1", "--some-future-flag=2"],
        {"command": "PING"})

    assert code == 0, (
        f"an unrecognised launch flag stopped the host (exit {code}). stderr:\n"
        f"{stderr[:400]}")
    assert reply and reply.get("ok") is True, reply


def test_the_launcher_this_repo_GENERATES_passes_those_arguments_through(tmp_path):
    """The `%*` forwarding is what made the parser's refusal fatal rather than
    theoretical, so it is the subject of this whole file -- and it was checked
    against an install artifact under the current user's home, which SKIPS on any
    machine that has never installed one. A test that skips exactly where the
    guarantee is not yet established is not protecting it.

    `scrapex/nativehost.py` writes that launcher and this repository owns it, so
    that is what gets asserted. Both branches are covered here regardless of the
    platform the suite runs on, because the shim for the other one is written by
    the same function and would otherwise never be read by anything.
    """
    shim = nativehost.write_launcher(tmp_path)

    assert shim.is_file()
    text = shim.read_text(encoding="utf-8")
    assert "native-host" in text, "the launcher no longer starts the host at all"
    forwards = "%*" if sys.platform == "win32" else '"$@"'
    assert forwards in text, (
        f"the generated launcher no longer forwards Chrome's arguments "
        f"({forwards!r} is gone), so the host would never receive the extension "
        "origin or --parent-window and this file's subject stops existing")


def test_a_launcher_left_by_an_older_install_still_forwards(tmp_path):
    """The reason the host must TOLERATE those arguments rather than merely be
    launched without them: a `.bat` written by a previous install is still on
    disk and still forwards, and nothing rewrites it on upgrade."""
    installed = pathlib.Path.home() / "AppData/Local/ScrapeX/scrapex-native-host.bat"
    if not installed.is_file():
        pytest.skip("no native host installed on this machine")
    text = installed.read_text(encoding="utf-8", errors="replace")
    assert "%*" in text and "native-host" in text, (
        "the launcher already on this machine no longer forwards Chrome's "
        "arguments, which changes what the host has to tolerate")
