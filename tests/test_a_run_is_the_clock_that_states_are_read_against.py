"""The run is the clock. `R-54`'s second half, guarded.

WHY A GUARD AND NOT A REVIEW. The defect this replaces was invisible for a reason worth
keeping: `MAX(last_seen_at)` over the whole dataset ANSWERED for every row, always, and
answered plausibly. Nothing was ever NULL, nothing ever raised, and the wrong answer
looked exactly like the right one. The only way that fails loudly is if something asserts
the state a specific row gets from a specific pair of runs -- which is what this file is.

The states these tests name are his, ruled on 2026-08-29: a row the latest run did not
touch is `absent`; a row stored before run identity existed is `unsighted` and NOT
`absent`, because `absent` claims the site stopped publishing a contractor it still lists.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import runs
from scrapex.catalog import register_site
from scrapex.catalog_models import SiteCreate
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.sightings import row_state
from scrapex.vocab import RunStatus


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        register_site(connection, SiteCreate(site_key="a_site", display_name="A site",
                                             base_url="https://example.test"))
        yield connection
    finally:
        connection.close()


def test_a_run_cannot_be_opened_for_a_source_nobody_registered(conn):
    """The alternative is a run whose `source_id` points at nothing, and `crawl_run` would
    take it -- SQLite does not enforce a foreign key unless it is asked to."""
    with pytest.raises(runs.UnknownSource):
        runs.open_run(conn, "a_source_that_was_never_registered", kind="listing")


def test_an_open_run_is_running_and_a_closed_one_is_not(conn):
    run_id = runs.open_run(conn, "a_site", kind="listing")
    status, finished = conn.execute(
        "SELECT status, finished_at FROM crawl_run WHERE run_id = ?", (run_id,)).fetchone()
    assert (status, finished) == (RunStatus.RUNNING.value, None)

    runs.close_run(conn, run_id, status=RunStatus.SUCCESS, rows_seen=7)
    status, finished, seen = conn.execute(
        "SELECT status, finished_at, rows_seen FROM crawl_run WHERE run_id = ?",
        (run_id,)).fetchone()
    assert status == RunStatus.SUCCESS.value and seen == 7
    # THE PAIR MOVES TOGETHER OR NOT AT ALL. `finished_at` is written in the same
    # statement as `status` precisely so "when did it end" cannot disagree with "is it
    # still running", which two separate UPDATEs would allow between them.
    assert finished is not None


def test_a_run_does_not_commit_itself(tmp_path: Path):
    """A run that committed would survive a crawl that then rolled back -- a row saying
    `running` for ever with nothing behind it. Every writer here leaves the transaction
    to its caller, and this asserts `open_run` is not the exception."""
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    writer = registry.engine.connect()
    try:
        register_site(writer, SiteCreate(site_key="a_site", display_name="A site",
                                         base_url="https://example.test"))
        writer.commit()
        runs.open_run(writer, "a_site", kind="listing")
        writer.rollback()
    finally:
        writer.close()
    reader = registry.engine.connect()
    try:
        assert reader.execute("SELECT COUNT(*) FROM crawl_run").fetchone()[0] == 0
    finally:
        reader.close()


def test_the_latest_run_is_asked_through_the_rows_and_not_off_the_source(conn):
    """THE DIFFERENCE IS THE WHOLE POINT, and `MAX(run_id)` for the source would pass every
    other test in this file. A listing sweep stores no profile page, so if the profile
    dataset compared its rows against the newest run OF THE SOURCE, every profile row
    would read `absent` the moment a listing crawl finished -- while the site still lists
    every one of them."""
    dataset = _a_dataset(conn, "profiles")
    profile_run = runs.open_run(conn, "a_site", kind="profiles")
    _a_row(conn, dataset, run_id=profile_run, url="https://example.test/p/1")

    # A LATER run of the same source that wrote nothing this dataset can see.
    listing_run = runs.open_run(conn, "a_site", kind="listing")
    assert listing_run > profile_run

    assert runs.latest_run_for(conn, "profiles") == profile_run


def test_a_dataset_no_run_has_written_has_no_latest_run(conn):
    """Every dataset is in this state until a crawl has run since `0016`, and his ruling
    for it is `unsighted` rather than a guess."""
    _a_dataset(conn, "untouched")
    assert runs.latest_run_for(conn, "untouched") is None


def test_started_at_is_none_for_a_run_that_does_not_exist(conn):
    assert runs.started_at_of(conn, None) is None
    assert runs.started_at_of(conn, 999_999) is None


# --- the states, read against the run ------------------------------------------------

WAS = "2026-08-01T00:00:00Z"
RUN_BEGAN = "2026-08-29T00:00:00Z"
DURING = "2026-08-29T04:00:00Z"


def _state(**over):
    base = {"status": "active", "first_seen_at": WAS, "last_seen_at": DURING,
            "sighted_at": DURING, "row_run": 5, "latest_run": 5,
            "run_started_at": RUN_BEGAN, "changed_at": WAS}
    return row_state(**{**base, **over})


def test_a_row_the_latest_run_did_not_touch_is_absent():
    assert _state(row_run=4) == "absent"


def test_a_row_stored_before_run_identity_existed_is_unsighted_not_absent():
    """1,728 snapshots on his warehouse predate `0016` and name no run. Calling them
    `absent` would claim the site stopped publishing a contractor it still lists."""
    assert _state(row_run=None) == "unsighted"


def test_a_dataset_with_no_run_at_all_is_unsighted_rather_than_confirmed():
    """The nastier half: were `latest_run is None` to fall through to `confirmed`, every
    row of an un-crawled dataset would claim to have been seen by this run."""
    assert _state(latest_run=None) == "unsighted"


def test_a_row_first_seen_during_this_run_is_new():
    assert _state(first_seen_at=DURING) == "new"


def test_a_row_changed_during_this_run_is_updated():
    assert _state(changed_at=DURING) == "updated"


def test_a_revision_written_any_time_during_a_long_sweep_belongs_to_that_sweep():
    """The reason the comparison is against the RUN'S START and not a row's own date. His
    profile crawl ran nine hours; a row revised in hour eight is `updated` for that sweep,
    and comparing two row timestamps to each other would have called it merely seen."""
    nine_hours_in = "2026-08-29T09:00:00Z"
    assert _state(changed_at=nine_hours_in, last_seen_at=nine_hours_in,
                  sighted_at=nine_hours_in) == "updated"


def test_retired_and_unavailable_still_win_over_everything_the_run_says():
    assert _state(status="retired", row_run=4) == "retired"
    assert _state(status="unavailable", row_run=4) == "unavailable"


def test_a_row_never_sighted_is_unsighted_whatever_the_runs_say():
    assert _state(sighted_at=None) == "unsighted"


# --- fixtures ------------------------------------------------------------------------

def _a_dataset(conn, key: str) -> int:
    """RAW, and deliberately so for THIS pair of tests. `latest_run_for` is one SELECT
    across three tables, and what it must get right is the JOIN -- so the fixture's job is
    to place rows on both sides of it, not to exercise the writer. The writer is asserted
    separately, below, through `save_snapshot` itself; the lesson that raw fixtures once
    hid a real defect is why BOTH exist rather than either alone."""
    return int(conn.execute(
        "INSERT INTO dataset_definition "
        "(source_id, dataset_key, original_name, dataset_kind, discovery_method, "
        " locator_json) "
        "VALUES ((SELECT source_id FROM source_site WHERE source_key='a_site'),"
        "        ?,?, 'table', 'manual', '{}')",
        (key, key)).lastrowid)


def _a_row(conn, dataset_id: int, *, run_id: int, url: str) -> None:
    snapshot = conn.execute(
        "INSERT INTO generic_page_snapshot "
        "(source_url, content_type, html_content, content_hash, html_codec, run_id) "
        "VALUES (?, 'text/html', '<html/>', ?, 'utf-8', ?)",
        (url, f"hash-{url}", run_id)).lastrowid
    version = conn.execute(
        "INSERT INTO dataset_schema_version (dataset_definition_id, version_number, "
        " schema_hash, status) VALUES (?, 1, ?, 'approved')",
        (dataset_id, f"schema-{dataset_id}")).lastrowid
    conn.execute(
        "INSERT INTO generic_record "
        "(dataset_definition_id, record_key, schema_version_id, data_json, "
        " source_snapshot_id, source_locator, content_hash) "
        "VALUES (?,?,?,'{}',?,'row[0]',?)",
        (dataset_id, url, version, snapshot, f"row-{url}"))


def test_the_writer_actually_stores_the_run_on_the_page_it_saved(conn):
    """THE HALF A RAW FIXTURE CANNOT SEE. Every test above can pass while `save_snapshot`
    quietly drops `run_id` on the floor -- and then every row in production reads
    `unsighted` for ever, which is a state the code is entitled to return, so nothing
    raises and nothing looks wrong. `generic_page_snapshot` is immutable by trigger, so a
    dropped `run_id` cannot be backfilled either: it is wrong permanently or it is right
    at INSERT.
    """
    from scrapex.extract import service
    from scrapex.extract.models import SnapshotCreate

    run_id = runs.open_run(conn, "a_site", kind="profiles")
    saved = service.save_snapshot(conn, SnapshotCreate(
        source_url="https://example.test/p/9",
        html_content="<html><body>a page</body></html>",
        run_id=run_id))
    stored = conn.execute("SELECT run_id FROM generic_page_snapshot WHERE page_snapshot_id = ?",
                          (saved["page_snapshot_id"],)).fetchone()[0]
    assert stored == run_id
