"""His ruling of 2026-08-22: the two machines' warehouses merge, and one holder at a time.

BOTH MACHINES HAVE DEVELOPED muqawil, so neither file may be copied over the other — each
holds work the other does not, and `R-24` says upgrade rather than replace. Drive becomes
the single source of truth for DATA while the repository stays the single source of truth
for CODE.

WHAT MAKES THE MERGE DEFINABLE is that the natural keys exist. Measured on his warehouse:
`generic_page_snapshot` has 20,379 rows and 20,379 distinct `(source_url, content_hash)`,
and `dataset_sighting` and `generic_record` carry UNIQUE constraints already. Without them
a merge would mean remapping every autoincrement key and every foreign key pointing at it,
because both machines hold a `page_snapshot_id = 1` for a different page.

ONLY THE EVIDENCE TRAVELS. Snapshots and sightings cannot be recomputed; everything else is
rebuilt by `--approve` with no network. So nothing that carries a primary key ever crosses.

AND THE TEST THAT MATTERS MOST IS `test_merging_twice_changes_no_value`. The first version
of this merge SUMMED `seen_count`, so three merges of the same file took one id from 4 to 8
to 12 to 16 — while the module's own docstring called the operation idempotent. The test
that missed it counted ROWS and never looked at a value.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.warehousemerge import (
    NotMergeable,
    NotYours,
    claim,
    holder,
    merge,
    release,
)


def _warehouse(path: Path) -> sqlite3.Connection:
    registry = DatabaseRegistry(EngineDatabase(path),
                                pointer_file=path.with_suffix(".json"))
    registry.initialize()
    conn = registry.engine.connect()
    conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url) "
        "VALUES ('muqawil_org','C','https://muqawil.org')")
    conn.commit()
    return conn


@pytest.fixture()
def two(tmp_path: Path):
    """Two warehouses of the same shape, as two machines running the same build."""
    here = _warehouse(tmp_path / "here.db")
    there = _warehouse(tmp_path / "there.db")
    yield here, there, str(tmp_path / "there.db")
    here.close()
    there.close()


def _page(conn, tag: str, *, body: str = "<html/>") -> None:
    conn.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash, "
        " crawl_run_ref) VALUES (?,?,?,?)",
        (f"https://muqawil.org/en/contractors/{tag}/143", body, f"h-{tag}", "run"))
    conn.commit()


def _sighting(conn, external_id: str, *, first: str, last: str, count: int,
              absent: str | None = None) -> None:
    conn.execute(
        "INSERT INTO dataset_sighting (dataset_key, external_id, first_seen_at, "
        " last_seen_at, seen_count, last_absent_at) VALUES ('contractors',?,?,?,?,?)",
        (external_id, first, last, count, absent))
    conn.commit()


def _sighting_of(conn, external_id: str) -> tuple:
    return tuple(conn.execute(
        "SELECT first_seen_at, last_seen_at, seen_count, last_absent_at "
        "  FROM dataset_sighting WHERE external_id = ?", (external_id,)).fetchone())


def _urls(conn) -> set[str]:
    return {row[0] for row in conn.execute(
        "SELECT source_url FROM generic_page_snapshot")}


# ---- the lock, which is the part his plan was missing -------------------------

def test_a_merge_into_an_unclaimed_warehouse_is_refused(two):
    """CLAIM FIRST, ALWAYS. The whole reason the lock exists is that the loser of a race
    must find out BEFORE writing rather than after a day's work is gone."""
    here, _there, path = two

    with pytest.raises(NotYours):
        merge(here, path, machine="work-laptop")


def test_a_second_machine_cannot_take_a_held_warehouse(two):
    """Download → work → upload has nothing else stopping both machines doing it the same
    day, and Drive keeps versions but cannot merge them."""
    here, _there, _path = two
    claim(here, "work-laptop")

    with pytest.raises(NotYours) as raised:
        claim(here, "home-desktop")

    assert "work-laptop" in str(raised.value), "the refusal must name who holds it"


def test_re_claiming_your_own_is_allowed(two):
    """A session that died mid-merge has to be able to pick the same copy back up."""
    here, _there, _path = two
    claim(here, "work-laptop")

    claim(here, "work-laptop")

    assert holder(here) == "work-laptop"


def test_releasing_hands_it_back(two):
    here, _there, _path = two
    claim(here, "work-laptop")

    release(here)

    assert holder(here) is None
    claim(here, "home-desktop")
    assert holder(here) == "home-desktop"


def test_an_unclaimed_warehouse_says_so_rather_than_failing(two):
    """A warehouse written before this feature has no such key, and `None` is the honest
    answer — the alternative is a build that cannot open his existing file."""
    here, _there, _path = two

    assert holder(here) is None


def test_a_claim_needs_a_name(two):
    here, _there, _path = two

    with pytest.raises(NotMergeable):
        claim(here, "   ")


# ---- the evidence merges, and nothing else does ------------------------------

def test_pages_the_other_machine_has_arrive(two):
    here, there, path = two
    _page(here, "A1")
    _page(there, "B1")
    _page(there, "B2")
    claim(here, "m")

    report = merge(here, path, machine="m")

    assert report.snapshots_added == 2
    assert _urls(here) == {
        "https://muqawil.org/en/contractors/A1/143",
        "https://muqawil.org/en/contractors/B1/143",
        "https://muqawil.org/en/contractors/B2/143"}


def test_a_page_both_machines_hold_is_not_duplicated(two):
    """THE NATURAL KEY DOING ITS JOB. `(source_url, content_hash)` is what makes the same
    page the same page across two files that agree on no primary key at all."""
    here, there, path = two
    _page(here, "SAME")
    _page(there, "SAME")
    claim(here, "m")

    report = merge(here, path, machine="m")

    assert report.snapshots_added == 0
    assert len(_urls(here)) == 1


def test_the_same_url_fetched_with_different_content_is_two_pages(two):
    """HISTORY, NOT A DUPLICATE. A listing page re-read after the site changed is a
    different observation of the same URL, and the content hash is what says so."""
    here, there, path = two
    _page(here, "P", body="<html>monday</html>")
    there.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash, "
        " crawl_run_ref) VALUES (?,?,?,'run')",
        ("https://muqawil.org/en/contractors/P/143", "<html>tuesday</html>", "h-P-2"))
    there.commit()
    claim(here, "m")

    merge(here, path, machine="m")

    assert here.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot "
        " WHERE source_url = 'https://muqawil.org/en/contractors/P/143'"
    ).fetchone()[0] == 2


def test_no_foreign_primary_key_crosses(two):
    """The ids are reassigned here, so nothing downstream can ever reference the other
    machine's numbering. This is the property that removes the whole `OP-30` class of
    problem from the merge."""
    here, there, path = two
    _page(here, "A1")
    for tag in ("B1", "B2", "B3"):
        _page(there, tag)
    claim(here, "m")

    merge(here, path, machine="m")

    ids = [row[0] for row in here.execute(
        "SELECT page_snapshot_id FROM generic_page_snapshot ORDER BY page_snapshot_id")]
    assert ids == list(range(1, len(ids) + 1)), "contiguous, so they were assigned here"


def test_derived_rows_are_named_for_rebuilding_and_never_written(two):
    """ONE RESPONSIBILITY. A function that both merged evidence and re-interpreted it
    would be two operations with one error path — and `--approve` already owns the second
    and needs a run ref this has no business inventing."""
    here, there, path = two
    _page(there, "B1")
    here.execute(
        "INSERT INTO dataset_definition (source_id, dataset_key, original_name, "
        " dataset_kind, discovery_method, locator_json) "
        "VALUES (1,'contractors','c','table','html_table','{}')")
    here.commit()
    claim(here, "m")

    report = merge(here, path, machine="m")

    assert report.rebuild == ("contractors",)
    assert "--approve" in str(report)
    assert here.execute("SELECT COUNT(*) FROM generic_record").fetchone()[0] == 0


# ---- the sighting arithmetic -------------------------------------------------

def test_a_sighting_takes_the_earliest_first_and_the_latest_last(two):
    """A sighting is the only record of what the site showed and WHEN, and the two
    machines watched different moments."""
    here, there, path = two
    _sighting(here, "X", first="2026-08-01T00:00:00Z", last="2026-08-10T00:00:00Z",
              count=4)
    _sighting(there, "X", first="2026-08-05T00:00:00Z", last="2026-08-20T00:00:00Z",
              count=9)
    claim(here, "m")

    merge(here, path, machine="m")

    first, last, count, _absent = _sighting_of(here, "X")
    assert (first, last) == ("2026-08-01T00:00:00Z", "2026-08-20T00:00:00Z")
    assert count == 9, "MAX, not 13 — see the module docstring"


def test_a_proved_absence_on_either_machine_survives(two):
    """`last_absent_at` is written only from a crawl that closed with `D = 0`, so an
    absence proved on either machine is an absence proved."""
    here, there, path = two
    _sighting(here, "X", first="2026-08-01T00:00:00Z", last="2026-08-02T00:00:00Z",
              count=1)
    _sighting(there, "X", first="2026-08-01T00:00:00Z", last="2026-08-02T00:00:00Z",
              count=1, absent="2026-08-19T00:00:00Z")
    claim(here, "m")

    merge(here, path, machine="m")

    assert _sighting_of(here, "X")[3] == "2026-08-19T00:00:00Z"


def test_merging_twice_changes_no_value(two):
    """THE TEST THAT WOULD HAVE CAUGHT THE SUM, and the first version of it did not
    because it counted rows. Three merges took one id's `seen_count` from 4 to 8 to 12 to
    16 while the docstring called the operation idempotent."""
    here, there, path = two
    _page(there, "B1")
    _sighting(here, "X", first="2026-08-01T00:00:00Z", last="2026-08-10T00:00:00Z",
              count=4)
    _sighting(there, "X", first="2026-08-05T00:00:00Z", last="2026-08-20T00:00:00Z",
              count=9)
    claim(here, "m")

    merge(here, path, machine="m")
    once = _sighting_of(here, "X")
    merge(here, path, machine="m")
    merge(here, path, machine="m")

    assert _sighting_of(here, "X") == once
    assert here.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot").fetchone()[0] == 1


def test_the_merge_is_commutative(two):
    """WHICH MACHINE RUNS IT MUST NOT MATTER, or his plan produces two different answers
    depending on who happened to open the laptop first."""
    here, there, path = two
    _sighting(here, "X", first="2026-08-01T00:00:00Z", last="2026-08-10T00:00:00Z",
              count=4)
    _sighting(there, "X", first="2026-08-05T00:00:00Z", last="2026-08-20T00:00:00Z",
              count=9)
    claim(here, "m")
    claim(there, "m")

    merge(here, path, machine="m")
    merge(there, str(Path(path).with_name("here.db")), machine="m")

    assert _sighting_of(here, "X") == _sighting_of(there, "X")


# ---- and what it refuses ----------------------------------------------------

def test_two_different_schema_versions_are_refused(two):
    """A v8 file and a v9 one disagree about which tables exist. `R-24` one level up:
    upgrade the older, do not merge across."""
    here, there, path = two
    there.execute("PRAGMA user_version = 3")
    there.commit()
    claim(here, "m")

    with pytest.raises(NotMergeable) as raised:
        merge(here, path, machine="m")

    assert "init-db" in str(raised.value), "it must say how to fix it"


def test_a_failed_merge_still_detaches(two):
    """Or the next call in the same process fails because the name is taken, for a reason
    that has nothing to do with the merge — which is what happened the first time."""
    here, there, path = two
    there.execute("PRAGMA user_version = 3")
    there.commit()
    claim(here, "m")
    with pytest.raises(NotMergeable):
        merge(here, path, machine="m")

    # A SECOND ATTEMPT MUST FAIL ON ITS OWN MERITS. `NotMergeable` again means it got as
    # far as comparing the versions; a stale ATTACH would raise `OperationalError` about
    # the name being taken instead, which is the failure that hid the real one the first
    # time this ran for real.
    with pytest.raises(NotMergeable):
        merge(here, path, machine="m")

# ---- the compression dictionary, which the first version left behind ---------
#
# HIS REAL TRANSFER FAILED HERE, on 2026-08-22: 20,379 pages, every one
# `zstd-raw-dict`, arriving into a warehouse with no dictionaries at all ->
# "FOREIGN KEY constraint failed". The seventeen tests above all passed before the
# fix AND after it, because not one of them stored a compressed page. The merge was
# written on 2026-08-22 and the codec on 2026-08-20; neither knew about the other.


def _compressed_page(conn, tag: str, label: str, *, filler: str = "x") -> str:
    """One page stored the way `snapshotcrawl` stores them, and its plaintext back.

    Goes through `save_snapshot`, not raw SQL, so the row is shaped by the production
    writer rather than by this test's idea of it.
    """
    from scrapex.extract.models import SnapshotCreate
    from scrapex.extract.service import save_snapshot

    html = ("<html><body>" + f"{filler} shared skeleton " * 400
            + f"<main>{tag}</main></body></html>")
    save_snapshot(conn, SnapshotCreate(
        source_url=f"https://muqawil.org/en/contractors?page={tag}",
        html_content=html, body_class=label))
    conn.commit()
    return html


def _decoded(conn, url: str) -> str:
    from scrapex.snapshotbody import decode

    row = conn.execute(
        "SELECT page_snapshot_id, html_content, html_codec, html_dict_id "
        "FROM generic_page_snapshot WHERE source_url = ?", (url,)).fetchone()
    return decode(conn, row)


def test_a_compressed_page_still_decodes_after_it_crosses(two):
    """THE PROPERTY, and it is not "the row arrived".

    A `zstd-raw-dict` body is unreadable without the exact page it was compressed
    against, and that page is stored nowhere else. So a merge that moves the row and
    not the dictionary has not moved the evidence — it has destroyed it and returned
    success.
    """
    here, there, path = two
    wanted = _compressed_page(there, "7", "muqawil.org/listing")

    claim(here, "here")
    merge(here, path, machine="here")

    url = "https://muqawil.org/en/contractors?page=7"
    assert _decoded(here, url) == wanted


def test_the_dictionary_id_is_remapped_and_not_copied(two):
    """THE FAILURE THAT WOULD HAVE BEEN SILENT, which is why it is asserted separately.

    The old code copied `html_dict_id` verbatim — a foreign machine's PRIMARY KEY, the
    one thing this module's docstring says never crosses. It happened to fail loudly on
    his transfer only because the receiving warehouse had NO dictionaries, so the
    foreign key had nothing to point at. Here the receiving side already holds two, so
    the arriving ids 1 and 2 are legal numbers naming the WRONG bodies — no constraint
    fires, and the pages decode to nothing.
    """
    here, there, path = two
    _compressed_page(here, "1", "ours.example/listing", filler="local-a")
    _compressed_page(here, "2", "ours.example/detail", filler="local-b")
    wanted = _compressed_page(there, "9", "muqawil.org/listing", filler="theirs")

    theirs_id = there.execute(
        "SELECT html_dict_id FROM generic_page_snapshot "
        "WHERE source_url LIKE '%page=9'").fetchone()[0]
    assert theirs_id == 1, "the fixture must reproduce the id collision"

    claim(here, "here")
    merge(here, path, machine="here")

    row = here.execute(
        "SELECT html_dict_id FROM generic_page_snapshot "
        "WHERE source_url LIKE '%page=9'").fetchone()
    assert row[0] != theirs_id, (
        "the arriving page kept the other machine's dict_id, which here names a "
        "different body entirely")
    assert _decoded(here, "https://muqawil.org/en/contractors?page=9") == wanted


def test_one_label_two_bodies_keeps_both(two):
    """Each machine seeds a dictionary from the first page of that kind IT fetched, so
    `muqawil.org/listing` is a different 298,954-byte page on each. `label` is UNIQUE,
    so the arriving one cannot take the name — and it must not be dropped either,
    because its pages would become unreadable."""
    here, there, path = two
    mine = _compressed_page(here, "3", "muqawil.org/listing", filler="mine")
    yours = _compressed_page(there, "4", "muqawil.org/listing", filler="yours")

    claim(here, "here")
    merge(here, path, machine="here")

    labels = sorted(l for (l,) in here.execute("SELECT label FROM snapshot_dictionary"))
    assert len(labels) == 2, f"one of the two dictionaries was lost: {labels}"
    assert _decoded(here, "https://muqawil.org/en/contractors?page=3") == mine
    assert _decoded(here, "https://muqawil.org/en/contractors?page=4") == yours


def test_the_same_dictionary_is_not_stored_twice(two):
    """Commutative and idempotent has to hold for the dictionaries too, or every
    round trip through Drive grows the table by two rows."""
    here, there, path = two
    _compressed_page(there, "5", "muqawil.org/listing")

    claim(here, "here")
    first = merge(here, path, machine="here")
    second = merge(here, path, machine="here")

    assert first.dictionaries_added == 1
    assert second.dictionaries_added == 0
    assert here.execute("SELECT COUNT(*) FROM snapshot_dictionary").fetchone()[0] == 1


def test_a_compressed_page_whose_dictionary_is_missing_rolls_the_merge_back(two):
    """The one way the remap can lose data quietly: it is a lookup, so it yields NULL,
    and the column is nullable for the sake of 'plain' rows. A page that says it is
    compressed and names no dictionary can never be read again, so the merge refuses
    instead of reporting how many rows it added.

    WORTH SAYING WHAT THIS TOOK TO REACH: the donor's own foreign key forbids the row,
    which is the schema doing its job. The state is only reachable through a file
    written with foreign keys off -- which is SQLite's DEFAULT for any connection that
    does not opt in, so it is a real possibility rather than a hypothetical, and it is
    exactly how this fixture builds it.
    """
    here, there, path = two
    _compressed_page(there, "6", "muqawil.org/listing")
    there.commit()

    raw = sqlite3.connect(path)              # foreign_keys defaults to OFF
    raw.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash, "
        " html_codec, html_dict_id) VALUES (?,?,?,?,?)",
        ("https://muqawil.org/en/contractors?page=99", b"not-a-real-frame", "h-99",
         "zstd-raw-dict", 4242))
    raw.commit()
    raw.close()

    claim(here, "here")
    with pytest.raises(NotMergeable, match="could never be decoded"):
        merge(here, path, machine="here")

    assert here.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot").fetchone()[0] == 0, (
        "the merge did not roll back, so a partial transfer is now on disk")
