"""The engine says which Python it runs, and whether it is below the pin (#1321).

His engine runs from source, through a native-host launcher that names its interpreter
once, when it is registered (`scrapex/nativehost.py`, `write_launcher`). So a pin move,
routine since #1267's weekly reminder, moves CI and the release build and leaves his
engine on the old Python, below `requires-python`. pip enforces that floor only at
install time, so the engine keeps starting, and nothing said so.

The floor is `.python-version`, the one place the engine's Python is named; see
`scrapex/interpreter.py` for why it is not `requires-python`. His request of 2026-10-07:
«اريد اضافة صف مثل صف sql يوضح ان المحرك مبني على نسخة كام من python».
"""
from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet

from scrapex import interpreter

ROOT = Path(__file__).resolve().parents[1]

# Every boundary of the rule, as (interpreter, floor, verdict).
CASES = [
    ((3, 13, 9), (3, 14), "below"),           # the last minor before the floor
    ((3, 14, 0), (3, 14), "ok"),              # the floor itself
    ((3, 14, 6), (3, 14), "ok"),              # his engine, 2026-10-05
    ((3, 15, 0), (3, 14), "ok"),              # ahead of the pin
    ((4, 0, 0), (3, 14), "ok"),               # a major ahead, with a lower minor
    ((2, 7, 18), (3, 14), "below"),           # a major behind, with a higher minor
    ((3, 14, 8), (3, 15), "below"),           # the pin moves and his engine stays
    ((3, 15, 0, "alpha", 1), (3, 15), "ok"),  # pip reads 3.15.0a1 as 3.15.0
    ((3, 14, 99, "final", 0), (3, 15), "below"),
]


@pytest.mark.parametrize(("version", "minimum", "expected"), CASES,
                         ids=[f"{'.'.join(map(str, v))}-vs-{m[0]}.{m[1]}"
                              for v, m, _ in CASES])
def test_the_rule_judges_the_floor_as_pip_judges_requires_python(version, minimum, expected):
    assert interpreter.verdict(version, minimum) == expected
    # The oracle is PEP 440 itself, fed the way pip feeds it: `requires-python` is
    # `>=MAJOR.MINOR` (tests/test_one_python_version.py) and pip compares
    # `sys.version_info[:3]` against it.
    met = SpecifierSet(f">={minimum[0]}.{minimum[1]}").contains(
        ".".join(map(str, version[:3])))
    assert (expected == "ok") is met, "the expected verdict is not the one pip gives"


def test_the_floor_is_the_pin_file_of_this_checkout():
    assert interpreter.PIN_FILE == ROOT / ".python-version"
    major, minor = (ROOT / ".python-version").read_text(encoding="utf-8").strip().split(".")
    assert interpreter.floor() == (int(major), int(minor))


@pytest.mark.parametrize("text", ["3.14", "3.14\n", "3.14\r\n", " 3.14 \n"])
def test_the_pin_reads_as_a_checkout_writes_it(tmp_path, text):
    """`.gitattributes` sets `* text=auto`, so Windows checks the file out as CRLF."""
    pin = tmp_path / ".python-version"
    pin.write_bytes(text.encode("utf-8"))
    assert interpreter.floor(pin) == (3, 14)


@pytest.mark.parametrize("text", [
    "3.14.6",                 # a patch would stop patch releases arriving on their own
    "3", "3.x", "", "py314", ">=3.14", "3.14\n3.15", "3.14t",
    "٣.١٤",    # Arabic-Indic digits, which `\d` and `int` both accept
    "﻿3.14",             # a byte-order mark, which PowerShell writes
])
def test_a_pin_of_any_other_shape_is_refused(tmp_path, text):
    pin = tmp_path / ".python-version"
    pin.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=r"MAJOR\.MINOR"):
        interpreter.floor(pin)


def test_the_report_is_this_interpreter_against_the_pin():
    """No verdict is expected here: after a pin move this interpreter is below the real
    pin, a correct "below", because pip checks `requires-python` only at install."""
    minimum = interpreter.floor()
    assert interpreter.report() == {
        "version": platform.python_version(),
        "floor": f"{minimum[0]}.{minimum[1]}",
        "verdict": interpreter.verdict(sys.version_info, minimum)}


def _pin(tmp_path: Path, minors_ahead: int) -> tuple[Path, str]:
    """A pin this many minors ahead of this interpreter: 0 is level with it, and 1 is the
    state a pin move leaves him in. Written from the interpreter, never read from the
    checkout, so each test means the same on a machine still below the real pin."""
    text = f"{sys.version_info.major}.{sys.version_info.minor + minors_ahead}"
    pin = tmp_path / "pin" / str(minors_ahead) / ".python-version"
    pin.parent.mkdir(parents=True, exist_ok=True)
    pin.write_text(text + "\n", encoding="utf-8")
    return pin, text


def test_a_pin_level_with_this_interpreter_reads_ok(tmp_path, monkeypatch):
    pin, level = _pin(tmp_path, 0)
    monkeypatch.setattr(interpreter, "PIN_FILE", pin)
    assert interpreter.report() == {
        "version": platform.python_version(), "floor": level, "verdict": "ok"}


def test_a_pin_ahead_of_this_interpreter_reads_below(tmp_path, monkeypatch):
    pin, ahead = _pin(tmp_path, 1)
    monkeypatch.setattr(interpreter, "PIN_FILE", pin)
    assert interpreter.report() == {
        "version": platform.python_version(), "floor": ahead, "verdict": "below"}


@pytest.mark.parametrize(("content", "reason"), [
    (None, "FileNotFoundError"),       # a bundle built without it
    ("3.14.6\n", "ValueError"),        # a pin of the wrong shape
])
def test_a_pin_that_cannot_be_read_is_said_as_unknown_with_the_reason(
        tmp_path, monkeypatch, content, reason):
    """Never a raise: the panel polls this, and health must survive what it reports."""
    pin = tmp_path / ".python-version"
    if content is not None:
        pin.write_text(content, encoding="utf-8")
    monkeypatch.setattr(interpreter, "PIN_FILE", pin)
    body = interpreter.report()
    assert body["version"] == platform.python_version()
    assert body["floor"] is None and body["verdict"] == "unknown"
    assert reason in body["detail"], body["detail"]


# ---- /api/health ---------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex import db as dbmod
    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(path, manifest_path=manifest))


def test_the_health_poll_carries_the_report(client):
    assert client.get("/api/health").json()["python"] == interpreter.report()


def test_the_verdict_is_the_pin_at_the_moment_it_is_asked(client, tmp_path, monkeypatch):
    """Read per poll, not at import: a pin move pulled into the checkout shows at once."""
    pin, level = _pin(tmp_path, 0)
    monkeypatch.setattr(interpreter, "PIN_FILE", pin)
    python = client.get("/api/health").json()["python"]
    assert (python["floor"], python["verdict"]) == (level, "ok")
    pin, ahead = _pin(tmp_path, 1)
    monkeypatch.setattr(interpreter, "PIN_FILE", pin)
    python = client.get("/api/health").json()["python"]
    assert (python["floor"], python["verdict"]) == (ahead, "below")


def test_it_answers_when_the_database_cannot_be_read(client, tmp_path):
    """Health must survive the thing it reports on, and this fact needs no database."""
    for leftover in tmp_path.glob("harvest.db*"):
        leftover.write_bytes(b"not a database")
    response = client.get("/api/health")
    assert response.status_code == 200, response.text
    assert response.json()["python"] == interpreter.report()
