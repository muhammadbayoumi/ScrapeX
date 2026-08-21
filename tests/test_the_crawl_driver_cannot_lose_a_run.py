"""The driver that runs the listing crawl, and the ways it could throw hours away.

WHY THIS FILE EXISTS. `tools/crawl_muqawil_listing.py` is 452 lines and had **zero
tests** -- `grep -rln crawl_muqawil_listing tests/` returned nothing -- while being
the only way the crawl is ever started. It is also the file where this track's single
Windows-only defect lived, and CI cannot see it: CI is ubuntu-only and `tools/` is not
even in the linted path. Recorded as `OP-28` in `docs/BACKLOG.md`.

The four ways, each of which has happened or was one keystroke away:

  * A LOG LINE KILLS THE RUN. `print("... -> ...")` raises `UnicodeEncodeError` on a
    cp1252 console. The sizing pass completed all 114 requests and then died printing
    its own summary. On the crawl itself that is hours of fetching thrown away.
  * A CRAWL INTO A DATABASE THAT IS NOT THERE. `open_engine` refuses rather than
    letting `connect()` create an empty warehouse beside the real one -- the mistake
    `R-24` exists because of.
  * A MISTYPED `--only` CRAWLS FEWER CELLS and reports success over the ones it did.
  * `--approve` INTERPRETING ANOTHER RUN'S EVIDENCE, because `_` is a `LIKE`
    wildcard and every cell ref is full of them.

No network anywhere here, and nothing touches the live warehouse: `LOG` is redirected
for every test by an autouse fixture, because `say` writes into `~/.scrapex/trial/`
and a suite that writes to a real home is a suite that cannot be trusted twice.
"""
from __future__ import annotations

import importlib.util
import io
import sqlite3
import sys
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.sites.muqawil import MuqawilPartition

DRIVER = Path(__file__).resolve().parent.parent / "tools" / "crawl_muqawil_listing.py"
#: The exact shape of the line that killed a run: U+2192 is not in cp1252.
ARROW = "sized 56 cells → about 1,065 requests"


@pytest.fixture(scope="module")
def driver():
    """The tool, imported by path -- `tools/` is deliberately not a package."""
    spec = importlib.util.spec_from_file_location("crawl_muqawil_listing", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _log_goes_nowhere_real(driver, tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "LOG", tmp_path / "trial" / "listing.log")


@pytest.fixture()
def conn(tmp_path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def snapshot(conn, url: str, body: str, run_ref: str) -> int:
    """One stored page, with every NOT NULL column the real write path fills.

    A fixture that omits one is silently dropped by `INSERT OR IGNORE` elsewhere in
    this repository, which cost three separate hours on this track -- see
    `LESSONS.md`. Written out in full rather than defaulted for that reason.
    """
    cursor = conn.execute(
        "INSERT INTO generic_page_snapshot "
        "  (source_url, content_type, html_content, content_hash, captured_at, "
        "   crawl_run_ref, html_codec) "
        "VALUES (?, 'text/html', ?, ?, '2026-08-21T00:00:00Z', ?, 'plain')",
        (url, body, f"hash-of-{body}", run_ref))
    conn.commit()
    return int(cursor.lastrowid)


# ---- a log line may not kill a crawl ----------------------------------------

def _cp1252_console(monkeypatch):
    """A console exactly as strict as the one that killed the run."""
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict",
                               newline="", write_through=True)
    monkeypatch.setattr(sys, "stdout", console)
    return raw, console


def test_say_does_not_raise_on_a_console_that_cannot_encode_the_line(driver,
                                                                    monkeypatch):
    """U+2192 is not in cp1252, and `print` raises rather than dropping it."""
    raw, console = _cp1252_console(monkeypatch)

    driver.say(ARROW)     # must not raise

    console.flush()
    shown = raw.getvalue().decode("cp1252")
    assert "sized 56 cells" in shown
    assert "→" not in shown          # it could not be shown, and was replaced


def test_the_log_keeps_the_character_the_console_could_not_show(driver, monkeypatch):
    """A log that cannot represent a character must lose the CHARACTER, not the run."""
    _cp1252_console(monkeypatch)

    driver.say(ARROW)

    assert driver.LOG.read_text(encoding="utf-8").strip() == ARROW


def test_a_line_cp1252_can_encode_is_not_mangled(driver, monkeypatch):
    """The guard must not degrade every line to ASCII. Em-dash and guillemets ARE in
    cp1252, and no reviewer can be expected to know which mark is safe."""
    raw, console = _cp1252_console(monkeypatch)

    driver.say("cells 56 — «all of them»")

    console.flush()
    assert raw.getvalue().decode("cp1252") == "cells 56 — «all of them»\n"


# ---- a crawl into a warehouse that is not there ------------------------------

def test_open_engine_refuses_a_database_that_does_not_exist(driver, tmp_path,
                                                            monkeypatch):
    """`R-24`: an absent file must not become an empty warehouse beside the real one.

    `connect()` would CREATE it, the crawl would run for hours, and the rows would
    land somewhere the panel never reads.
    """
    missing = tmp_path / "not-here" / "scrapex-engine.db"

    class _Registry:
        engine = type("_Engine", (), {"path": missing})()

    monkeypatch.setattr(driver.DatabaseRegistry, "defaults",
                        classmethod(lambda cls: _Registry()))

    with pytest.raises(SystemExit) as raised:
        driver.open_engine()

    assert raised.value.code == 2
    assert not missing.exists()
    assert "does not exist" in driver.LOG.read_text(encoding="utf-8")


# ---- a mistyped --only must not quietly crawl less ---------------------------

class _Spy:
    """Stands in for `crawl_partition`, recording what it was asked to crawl."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, *args, **kwargs):
        self.calls.append(kwargs)
        return "an outcome"


def test_only_refuses_an_unknown_label_before_touching_the_database(driver,
                                                                   monkeypatch):
    """`conn` is None here on purpose: the refusal has to come first."""
    spy = _Spy()
    monkeypatch.setattr(driver, "crawl_partition", spy)

    with pytest.raises(SystemExit) as raised:
        driver.crawl(None, MuqawilPartition(), None, None, "run-1", 2,
                     only="region_id_1-company_size_enormous")

    assert "region_id_1-company_size_enormous" in str(raised.value)
    assert spy.calls == []


def test_only_passes_exactly_the_named_cells_and_no_others(driver, monkeypatch):
    """47 of 56 cells were already proven; re-reading them is the cost this avoids.
    Whitespace around a label is tolerated because these are pasted out of a log."""
    spy = _Spy()
    monkeypatch.setattr(driver, "crawl_partition", spy)
    monkeypatch.setattr(driver, "coverage", lambda *a, **k: "coverage")

    driver.crawl(None, MuqawilPartition(), None, None, "run-1", 2,
                 only=" region_id_2-company_size_big ,region_id_5-company_size_small")

    assert [one.label for one in spy.calls[0]["cells"]] == [
        "region_id_2-company_size_big", "region_id_5-company_size_small"]


def test_without_only_the_partition_decides_which_cells_to_crawl(driver, monkeypatch):
    """`cells=None` is how `crawl_partition` is told to use the whole partition."""
    spy = _Spy()
    monkeypatch.setattr(driver, "crawl_partition", spy)
    monkeypatch.setattr(driver, "coverage", lambda *a, **k: "coverage")

    driver.crawl(None, MuqawilPartition(), None, None, "run-1", 2)

    assert spy.calls[0]["cells"] is None


# ---- --approve must read THIS run's evidence and no other run's --------------

def test_pairs_does_not_gather_another_run_because_underscore_is_a_wildcard(driver,
                                                                           conn):
    """`LIKE 'my_run-%'` unescaped also matches `myXrun-...`, and the approval would
    then write another run's pages under this run's name."""
    snapshot(conn, "https://muqawil.org/en/contractors?page=1", "<html>mine</html>",
             "my_run-region_id_1-a1")
    snapshot(conn, "https://muqawil.org/en/contractors?page=2", "<html>theirs</html>",
             "myXrun-region_id_1-a1")

    found = driver._pairs(conn, "my_run")

    assert list(found) == ["https://muqawil.org/contractors?page=1"]


def test_pairs_puts_the_two_locales_of_the_same_page_together(driver, conn):
    """Not by arrival order: the two locales are two requests against a listing that
    reorders, so pairing by snapshot id marries page 7's English to whatever Arabic
    page happened to be stored next."""
    snapshot(conn, "https://muqawil.org/en/contractors?page=7", "<html>en7</html>",
             "r-a1")
    snapshot(conn, "https://muqawil.org/ar/contractors?page=3", "<html>ar3</html>",
             "r-a1")
    snapshot(conn, "https://muqawil.org/ar/contractors?page=7", "<html>ar7</html>",
             "r-a1")

    found = driver._pairs(conn, "r")

    seven = found["https://muqawil.org/contractors?page=7"]
    assert seven["en"][1] == "<html>en7</html>"
    assert seven["ar"][1] == "<html>ar7</html>"
    assert "en" not in found["https://muqawil.org/contractors?page=3"]


def test_pairs_keeps_the_later_read_of_a_page_a_retry_stored_twice(driver, conn):
    """A retried cell stored the same page in two generations, and the later read is
    the one the crawl's own witness was computed against."""
    url = "https://muqawil.org/en/contractors?page=4"
    snapshot(conn, url, "<html>first generation</html>", "r-a1")
    newer = snapshot(conn, url, "<html>second generation</html>", "r-a2")

    found = driver._pairs(conn, "r")

    assert found["https://muqawil.org/contractors?page=4"]["en"] == (
        newer, "<html>second generation</html>")


# ---- the approval the owner's answer stands for ------------------------------

def _field(key: str, name: str):
    return type("_Field", (), {"field_key": key, "source_name": name})()


def test_every_field_is_text_and_only_contractor_id_is_the_identity(driver):
    """Inference would guess `integer` for a rating reading `4.5` on the next page,
    the schema hash would then differ per page, and every approval after the first is
    refused. That is #234's 823 refusals in a different disguise."""
    candidate = type("_Candidate", (), {
        "fields": [_field("contractor_id", "ID"), _field("rating", "Rating")]})()

    approval = driver._approval(candidate)

    assert {one.field_key: one.data_type for one in approval.fields} == {
        "contractor_id": "text", "rating": "text"}
    assert [one.field_key for one in approval.fields if one.identity] == [
        "contractor_id"]


# ---- the command line itself -------------------------------------------------

def test_choosing_no_mode_is_refused(driver, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["crawl_muqawil_listing.py"])
    with pytest.raises(SystemExit) as raised:
        driver.main()
    assert raised.value.code == 2


@pytest.mark.parametrize("mode", ["--crawl", "--approve"])
def test_a_crawl_or_an_approve_without_a_run_ref_is_refused(driver, monkeypatch, mode):
    """The ref is what makes an interruption resumable and what `--approve` reads.
    Without it a re-run re-fetches everything already on disk."""
    monkeypatch.setattr(sys, "argv", ["crawl_muqawil_listing.py", mode])
    with pytest.raises(SystemExit) as raised:
        driver.main()
    assert raised.value.code == 2


def test_coverage_on_an_empty_ledger_says_to_crawl_rather_than_reporting_departures(
        driver, conn, monkeypatch):
    """The window defaults to the ledger's newest sighting. With no sightings that
    default is empty, and an empty window would read as "every contractor departed"."""
    called = []
    monkeypatch.setattr(sys, "argv", ["crawl_muqawil_listing.py", "--coverage"])
    monkeypatch.setattr(driver, "open_engine", lambda: conn)
    monkeypatch.setattr(driver, "report_coverage", lambda *a, **k: called.append(a))

    driver.main()

    assert called == []
    assert "Crawl first." in driver.LOG.read_text(encoding="utf-8")


def _sight(conn, last_seen: str) -> None:
    conn.execute(
        "INSERT INTO dataset_sighting (dataset_key, external_id, first_seen_at, "
        "  last_seen_at, seen_count) VALUES ('contractors','881',"
        "  '2026-08-01T00:00:00Z',?,3)", (last_seen,))
    conn.commit()


def test_coverage_measures_against_the_newest_sighting_without_being_told(
        driver, conn, monkeypatch):
    """So running it straight after a crawl asks "who did THAT crawl not show us"
    with nobody typing a timestamp -- a mistyped one reports everyone as departed."""
    _sight(conn, "2026-08-20T09:00:00Z")
    windows = []
    monkeypatch.setattr(sys, "argv", ["crawl_muqawil_listing.py", "--coverage"])
    monkeypatch.setattr(driver, "open_engine", lambda: conn)
    monkeypatch.setattr(driver, "report_coverage",
                        lambda _conn, since: windows.append(since))

    driver.main()

    assert windows == ["2026-08-20T09:00:00Z"]


def test_an_explicit_window_overrides_the_ledgers_newest(driver, conn, monkeypatch):
    _sight(conn, "2026-08-20T09:00:00Z")
    windows = []
    monkeypatch.setattr(sys, "argv", ["crawl_muqawil_listing.py", "--coverage",
                                      "--not-seen-since", "2026-07-01T00:00:00Z"])
    monkeypatch.setattr(driver, "open_engine", lambda: conn)
    monkeypatch.setattr(driver, "report_coverage",
                        lambda _conn, since: windows.append(since))

    driver.main()

    assert windows == ["2026-07-01T00:00:00Z"]


# ---- the trap CLAUDE.md opens with -------------------------------------------

def test_the_driver_puts_its_own_worktree_on_the_path(driver):
    """`CLAUDE.md`'s first trap: `pip install -e` points at the MAIN checkout, so a
    tool run from a worktree would import main's code and prove nothing about its own.
    """
    assert sys.path[0] == str(DRIVER.parent.parent)


def test_pairs_can_read_a_row_by_column_name(conn):
    """`_pairs` reads `row["source_url"]`. A tuple row factory would raise TypeError
    on the first page, and only ever under `--approve`."""
    assert conn.row_factory is sqlite3.Row
