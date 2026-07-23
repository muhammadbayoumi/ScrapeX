"""The OS task that makes a schedule fire with everything closed.

Nothing here may create a real Scheduled Task: schtasks is stubbed and the
COMMAND LINE is the thing under test, because the command line is the whole
contract — get one flag wrong and the owner gets an elevated task, a console
that blinks every quarter hour, or a tick that quietly does nothing.
"""
from __future__ import annotations

import subprocess
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scrapex import osschedule


class _Schtasks:
    """Stands in for schtasks.exe: records every argv, answers from a script."""

    def __init__(self, *answers: tuple[int, str, str]) -> None:
        self._answers = list(answers) or [(0, "", "")]
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        code, out, err = self._answers[min(len(self.calls) - 1, len(self._answers) - 1)]
        return subprocess.CompletedProcess(list(argv), code, out, err)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


@pytest.fixture()
def windowless(tmp_path, monkeypatch):
    """An interpreter folder where pythonw.exe genuinely exists.

    Asserting "the windowless one" against THIS machine's interpreter would
    pass for the wrong reason on a box that has no pythonw; a fake pair makes
    the choice itself the thing under test.
    """
    folder = tmp_path / "interp"
    folder.mkdir()
    (folder / "python.exe").write_bytes(b"")
    (folder / "pythonw.exe").write_bytes(b"")
    monkeypatch.setattr(osschedule.sys, "executable", str(folder / "python.exe"))
    return folder / "pythonw.exe"


def _stub(monkeypatch, *answers: tuple[int, str, str]) -> _Schtasks:
    fake = _Schtasks(*answers)
    monkeypatch.setattr(osschedule.subprocess, "run", fake)
    return fake


# ---- install -----------------------------------------------------------------

def test_install_builds_the_exact_schtasks_command(home, windowless, monkeypatch):
    fake = _stub(monkeypatch)

    assert osschedule.install() == "ScrapeX schedules"

    argv = fake.calls[0]
    assert Path(argv[0]).name.lower() in {"schtasks.exe", "schtasks"}
    assert argv[1:] == [
        "/Create",
        "/TN", "ScrapeX schedules",
        "/TR", f'"{windowless}" -m scrapex.cli run-due',
        "/SC", "MINUTE",
        "/MO", "15",
        "/RL", "LIMITED",
        "/F",
    ]
    # The two properties the owner would never notice going wrong:
    assert argv[5].startswith(f'"{windowless}"'), "a console interpreter would blink every tick"
    assert "HIGHEST" not in argv and "/RU" not in argv and "/RP" not in argv, \
        "this task must never elevate and never run as another account"


def test_install_honours_the_interval_and_is_idempotent(home, windowless, monkeypatch):
    fake = _stub(monkeypatch)

    osschedule.install()
    osschedule.install(interval_minutes=30)

    assert fake.calls[1][fake.calls[1].index("/MO") + 1] == "30"
    # /F is what makes a re-install replace rather than stack, the same way
    # autostart re-writes its one launcher file.
    assert "/F" in fake.calls[1]


def test_install_makes_the_log_home_before_the_first_tick_needs_it(home, windowless, monkeypatch):
    _stub(monkeypatch)

    osschedule.install()

    assert (home / ".scrapex").is_dir()


def test_an_interval_windows_cannot_express_is_refused_here(home, windowless, monkeypatch):
    fake = _stub(monkeypatch)

    with pytest.raises(osschedule.ScheduleTaskError) as refused:
        osschedule.install(interval_minutes=1440)

    assert "1..1439" in str(refused.value)
    assert fake.calls == [], "a bad interval must never reach the task store"


def test_a_refusal_is_reported_verbatim_never_as_success(home, windowless, monkeypatch):
    _stub(monkeypatch, (1, "", "ERROR: Access is denied."))

    with pytest.raises(osschedule.ScheduleTaskError) as refused:
        osschedule.install()

    message = str(refused.value)
    assert "ERROR: Access is denied." in message, "the owner must see what Windows said"
    assert "/Create" in message, "and the command that said it, to reproduce"


def test_an_unreachable_schtasks_says_so_instead_of_pretending(home, windowless, monkeypatch):
    def explode(argv, **kwargs):
        raise FileNotFoundError("schtasks")

    monkeypatch.setattr(osschedule.subprocess, "run", explode)

    with pytest.raises(osschedule.ScheduleTaskError) as refused:
        osschedule.install()

    assert "run-due" in str(refused.value), "give the owner the command to schedule by hand"


# ---- remove ------------------------------------------------------------------

def test_remove_reports_honestly_when_nothing_was_installed(home, monkeypatch):
    fake = _stub(monkeypatch, (1, "", "ERROR: The system cannot find the file specified."))

    assert osschedule.remove() is False, "removing nothing must say so, not lie"
    assert all("/Delete" not in call for call in fake.calls), \
        "nothing was there — do not ask Windows to delete it"


def test_remove_deletes_the_task_it_finds(home, monkeypatch):
    fake = _stub(monkeypatch, (0, "TaskName: \\ScrapeX schedules\n", ""), (0, "", ""))

    assert osschedule.remove() is True
    assert fake.calls[1][1:] == ["/Delete", "/TN", "ScrapeX schedules", "/F"]


# ---- status ------------------------------------------------------------------

_QUERY_OUTPUT = """
Folder: \\
HostName:                             OWNER-PC
TaskName:                             \\ScrapeX schedules
Next Run Time:                        23/07/2026 10:15:00
Status:                               Ready
Logon Mode:                           Interactive only
Schedule Type:                        One Time Only, Minute
Repeat: Every:                        0 Hour(s), 15 Minute(s)
Run Level:                            Limited
"""


def test_status_reflects_the_task_store(home, monkeypatch):
    _stub(monkeypatch, (0, _QUERY_OUTPUT, ""))

    assert osschedule.status() == {
        "installed": True, "path_or_name": "ScrapeX schedules", "interval": 15,
    }


def test_status_says_not_installed_when_the_query_finds_nothing(home, monkeypatch):
    _stub(monkeypatch, (1, "", "ERROR: The system cannot find the file specified."))

    assert osschedule.status() == {
        "installed": False, "path_or_name": "ScrapeX schedules", "interval": None,
    }


def test_an_unreadable_interval_is_None_rather_than_a_guess(home, monkeypatch):
    """A localized Windows prints that row in its own words. Reporting 15 there
    would be indistinguishable from having read it."""
    _stub(monkeypatch, (0, "TaskName: \\ScrapeX schedules\nWiederholen: Alle: 15 Min.\n", ""))

    state = osschedule.status()
    assert state["installed"] is True
    assert state["interval"] is None


# ---- the tick the task fires -------------------------------------------------

class _Manifest:
    """Every source active — `active` gating is scheduler.fire_due's own test."""

    def get(self, key):
        return SimpleNamespace(source_key=key, active=True)


def _warehouse(tmp_path, *, due_source: str | None = None) -> Path:
    from scrapex import db as dbmod
    from scrapex.scheduler import upsert_schedule, utcnow

    db_path = tmp_path / "marketlens.db"
    conn = dbmod.connect(db_path)
    try:
        dbmod.migrate(conn)
        if due_source:
            upsert_schedule(conn, due_source, frequency="daily", run_at="00:00")
            conn.execute(
                "UPDATE schedule SET next_run_at = ? WHERE source_key = ?",
                ((utcnow() - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 due_source))
            conn.commit()
    finally:
        conn.close()
    return db_path


def test_run_due_fires_what_is_due_and_starts_something_to_run_it(tmp_path, monkeypatch, capsys):
    from scrapex import cli, db as dbmod, native
    from scrapex.jobs import list_jobs

    db_path = _warehouse(tmp_path, due_source="GPP_ENERGY")
    spawned: list[int] = []
    monkeypatch.setattr(native, "_engine_listening", lambda port: False)
    monkeypatch.setattr(native, "_spawn_engine", lambda port: spawned.append(port))
    monkeypatch.setattr(cli, "load_manifest", lambda *a, **k: _Manifest())

    assert cli.main(["run-due", "--db", str(db_path)]) == 0

    conn = dbmod.connect(db_path)
    try:
        assert len(list_jobs(conn)) == 1
    finally:
        conn.close()
    assert spawned == [8000], "a job queued with no worker draining it never runs"
    assert "queued 1 job" in capsys.readouterr().out


def test_run_due_leaves_a_running_engine_to_its_own_loop(tmp_path, monkeypatch, capsys):
    """The engine's worker already calls fire_due twice a second. Firing again
    from here would race it into two jobs for one slot."""
    from scrapex import cli, db as dbmod, native
    from scrapex.jobs import list_jobs

    db_path = _warehouse(tmp_path, due_source="GPP_ENERGY")
    monkeypatch.setattr(native, "_engine_listening", lambda port: True)
    monkeypatch.setattr(native, "_spawn_engine",
                        lambda port: pytest.fail("a live engine must not be respawned"))

    assert cli.main(["run-due", "--db", str(db_path)]) == 0

    conn = dbmod.connect(db_path)
    try:
        assert list_jobs(conn) == []
    finally:
        conn.close()
    assert "already running" in capsys.readouterr().out


def test_run_due_exits_cleanly_when_the_write_lock_is_held(tmp_path, monkeypatch, capsys):
    """Contention is normal on a clock — whatever is due stays due for the next
    tick. A non-zero exit here would paint the task red over nothing."""
    from scrapex import cli, db as dbmod, native

    db_path = _warehouse(tmp_path, due_source="GPP_ENERGY")
    monkeypatch.setattr(native, "_engine_listening", lambda port: False)
    monkeypatch.setattr(native, "_spawn_engine",
                        lambda port: pytest.fail("nothing was queued, so nothing needs a worker"))
    monkeypatch.setattr(cli, "load_manifest", lambda *a, **k: _Manifest())
    monkeypatch.setattr(cli, "RUN_DUE_LOCK_TIMEOUT_S", 0.2)

    with dbmod.write_lock(db_path):
        code = cli.main(["run-due", "--db", str(db_path)])

    assert code == 0
    assert "skipped this tick" in capsys.readouterr().out


def test_run_due_says_nothing_was_due(tmp_path, monkeypatch, capsys):
    from scrapex import cli, native

    db_path = _warehouse(tmp_path)
    monkeypatch.setattr(native, "_engine_listening", lambda port: False)
    monkeypatch.setattr(native, "_spawn_engine",
                        lambda port: pytest.fail("nothing was due; nothing to run"))
    monkeypatch.setattr(cli, "load_manifest", lambda *a, **k: _Manifest())

    assert cli.main(["run-due", "--db", str(db_path)]) == 0
    assert "no schedules were due" in capsys.readouterr().out
