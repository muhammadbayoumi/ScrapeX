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
import argparse
import pathlib
import struct
import subprocess
import sys
import tempfile

import pytest

from scrapex import nativehost

# THE BUDGET THIS FILE ARGUES FROM LIVES IN THE PANEL. `extension/transport.js`
# sets the 5,000 ms a spawn-and-reply gets, and the launch-path test below is
# only meaningful against that number -- so this has to run when the extension
# changes, not only when the engine does.
pytestmark = pytest.mark.extension

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

def test_the_launch_path_never_scans_the_warehouse(monkeypatch, tmp_path):
    """Chrome gives the host five seconds, and a corruption scan is O(file size).

    `_cmd_native_host` used to resolve its path through `_engine_path`, which
    calls `DatabaseRegistry.verify()` -> `health()` with the default
    `integrity=True` -> `PRAGMA quick_check(1)` and `pragma_foreign_key_check`.
    MEASURED on the owner's 1,982 MB warehouse on 2026-09-05, with a crawl
    running: 38,157 ms for the scan against `extension/transport.js:41`'s
    5,000 ms budget, and 0.0 ms for the path the host actually needs. Chrome
    spawns a fresh host per message, so every PING, AUTOSTART_STATUS,
    SET_AUTOSTART, CHECK_STARTUP and UPGRADE_DATABASE paid it, and the panel
    reported "the helper did not answer in time" about a helper that was fine.

    Asserted as BEHAVIOUR rather than by reading the source, because the scan
    can return by more than one spelling: anything that reaches an integrity
    check fails here, however it got there.
    """
    import scrapex.cli as cli
    import scrapex.native as native
    from scrapex.databases import DatabaseRegistry

    scanned = []

    def refuse_to_scan(self, *, integrity: bool = True):
        scanned.append(integrity)
        raise AssertionError(
            "the native host launch path ran a health check. With "
            "integrity=True that is a full-file scan -- 38 seconds on the "
            "owner's warehouse against Chrome's 5-second budget -- and the "
            "host needs only `registry.engine.path`, which costs nothing.")

    monkeypatch.setattr(type(DatabaseRegistry.defaults().engine), "health",
                        refuse_to_scan)
    served = []
    monkeypatch.setattr(native, "serve",
                        lambda path, migrate=False: served.append(path) or 0)

    code = cli._cmd_native_host(argparse.Namespace(db=None))

    assert code == 0
    assert served, "the host never reached serve()"
    assert scanned == [], "a health check ran on the launch path"


def test_an_explicit_db_still_bypasses_the_registry_entirely(monkeypatch, tmp_path):
    """`--db` is the legacy path and must not acquire a registry lookup."""
    import scrapex.cli as cli
    import scrapex.native as native

    served = []
    monkeypatch.setattr(native, "serve",
                        lambda path, migrate=False: served.append((path, migrate)) or 0)

    legacy = tmp_path / "old.db"
    cli._cmd_native_host(argparse.Namespace(db=str(legacy)))

    assert served == [(legacy, True)], (
        "an explicit --db must be served as given, and only THAT case migrates")

# TWO WEAKER DUPLICATES OF THE PAIR ABOVE WERE REMOVED HERE.
#
# They asserted the same property by patching `DatabaseRegistry.verify`, which
# is ONE route to the scan; the pair above patches `health` itself, so anything
# that reaches an integrity check fails however it got there. Same knowledge,
# same reason to change, and the weaker spelling would have gone green on a
# refactor that reached the scan by another name.
