"""Start-with-Windows launcher: one visible file, three verbs, no elevation.

The launcher must reproduce EXACTLY what the native host spawns (same module,
same working dir, same log), because two "start the engine" paths that drift
apart fail on different days in different ways.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import autostart


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_install_writes_a_self_explaining_launcher(home):
    target = autostart.install()

    assert target.exists()
    assert target.name == "ScrapeX Engine.vbs"
    assert "Startup" in str(target.parent)
    text = target.read_text(encoding="utf-8")
    # The command is the native host's spawn, verbatim in cmd form.
    assert "-m scrapex.cli ui" in text
    assert "--port 8000" in text
    assert "engine.log" in text
    # VBS escapes interior quotes by doubling; an unescaped path with spaces
    # would break the launcher exactly on machines like this one.
    assert '.Run "cmd /c cd /d ""' in text
    # The file tells its reader who wrote it and every way to turn it off.
    assert "scrapex autostart remove" in text
    assert autostart.status() == {"installed": True, "path": str(target)}


def test_install_is_idempotent_and_honours_the_port(home):
    autostart.install()
    target = autostart.install(port=8123)          # re-install just rewrites

    launchers = list(target.parent.glob("*.vbs"))
    assert len(launchers) == 1, "re-installing must never stack launchers"
    assert "--port 8123" in target.read_text(encoding="utf-8")


def test_remove_deletes_and_reports_honestly(home):
    autostart.install()

    assert autostart.remove() is True
    assert autostart.status()["installed"] is False
    assert autostart.remove() is False, "removing nothing must say so, not lie"


def test_the_log_home_exists_before_the_first_boot_needs_it(home):
    """cmd's append-redirect creates the FILE but not the directory: on a
    fresh machine the first logon would fail before the engine ever ran."""
    autostart.install()

    assert (home / ".scrapex").is_dir()


# ---- the native verbs the panel toggle drives --------------------------------

def test_native_set_autostart_installs_and_removes(home):
    from scrapex import db as dbmod
    from scrapex.native import handle

    conn = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)

        r = handle(conn, {"command": "SET_AUTOSTART", "enabled": True,
                          "protocol_version": 1})
        assert r["ok"] and r["installed"] and Path(r["path"]).exists()

        r = handle(conn, {"command": "AUTOSTART_STATUS", "protocol_version": 1})
        assert r["ok"] and r["installed"]

        r = handle(conn, {"command": "SET_AUTOSTART", "enabled": False,
                          "protocol_version": 1})
        assert r["ok"] and not r["installed"]
        assert not Path(r["path"]).exists()
    finally:
        conn.close()
