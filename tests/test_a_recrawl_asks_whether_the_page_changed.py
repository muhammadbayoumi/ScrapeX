"""Validators survive the process, so the second crawl is not the first one again.

WHY THIS FILE EXISTS. He asked whether a new user waits the same hours every time —
«هل سينتظر كل هذا الوقت ايضا ؟ ام هناك استراتجية افضل؟» — and the honest answer was
that they should not, because `HttpFetcher` has done conditional requests all along.
It keeps each response's `ETag` and `Last-Modified`, sends `If-None-Match` next visit,
handles the 304, and counts it. Its docstring promises exactly that.

MEASURED 2026-08-21: `remember_validators` — *"Load validators kept from a previous
crawl"* — and `validators()` — *"The validators to keep for the next crawl"* — had
**zero callers anywhere in the repository.** The dict died with the process, so every
re-crawl asked for full bodies for pages that had not changed, and that promise had
never once been true across two runs.

That is this project's founding failure in miniature, which `CLAUDE.md` records:
`crawl_to_snapshots` was committed with no caller. **A capability with no caller is a
claim.** These tests are what stops this one becoming a claim again.

No network: the round trip is exercised against `HttpFetcher`'s own accessors, which
is the seam that was disconnected.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import validators
from scrapex.connectors.base import HttpFetcher
from scrapex.databases import DatabaseRegistry, EngineDatabase

ETAG = 'W/"5f2a-listing-page-1"'
MODIFIED = "Wed, 21 Aug 2026 10:00:00 GMT"
URL = "https://muqawil.org/en/contractors?region_id=1&page=1"


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


# ---- the round trip that was missing ----------------------------------------

def test_a_validator_kept_by_one_run_is_replayed_by_the_next(conn):
    """THE WHOLE POINT, and the thing no caller did. Two fetchers stand in for two
    processes: what the first learned must reach the second."""
    first = HttpFetcher(min_interval_s=0.0)
    try:
        first._validators[URL] = {"ETag": ETAG}
        validators.save(conn, first.validators())
    finally:
        first.close()

    second = HttpFetcher(min_interval_s=0.0)
    try:
        second.remember_validators(validators.load(conn))
        headers = second._conditional_headers(URL, None)
    finally:
        second.close()

    assert headers.get("If-None-Match") == ETAG, (
        "the second run must ask whether the page changed")


def test_a_url_never_seen_asks_for_the_whole_thing(conn):
    """No validator means no condition — a page we have never read must not be
    asked about as though we had."""
    fetcher = HttpFetcher(min_interval_s=0.0)
    try:
        fetcher.remember_validators(validators.load(conn))
        headers = fetcher._conditional_headers("https://muqawil.org/en/new", None)
    finally:
        fetcher.close()

    assert "If-None-Match" not in headers


# ---- the store's own rules --------------------------------------------------

def test_a_page_with_neither_header_is_not_stored(conn):
    """`has a row` and `has a validator` must stay the same question — migration
    0008's CHECK refuses the other kind, so `save` skips rather than raises."""
    written = validators.save(conn, {
        URL: {"ETag": ETAG},
        "https://muqawil.org/en/nothing": {},
    })

    assert written == 1
    assert list(validators.load(conn)) == [URL]


def test_either_header_alone_is_enough(conn):
    """A site may send one, the other, both or neither, and two of those four are
    still useful."""
    validators.save(conn, {"https://a.test/e": {"ETag": ETAG},
                           "https://a.test/m": {"Last-Modified": MODIFIED}})

    loaded = validators.load(conn)

    assert loaded["https://a.test/e"] == {"ETag": ETAG}
    assert loaded["https://a.test/m"] == {"Last-Modified": MODIFIED}


def test_a_second_visit_replaces_the_validator_rather_than_appending(conn):
    """A validator is the LATEST fact about a url, not a history. Appending would
    grow a row per visit and then need "the newest" on every lookup."""
    validators.save(conn, {URL: {"ETag": 'W/"old"'}})
    validators.save(conn, {URL: {"ETag": 'W/"new"'}})

    assert conn.execute("SELECT COUNT(*) FROM fetch_validator").fetchone()[0] == 1
    assert validators.load(conn)[URL] == {"ETag": 'W/"new"'}


def test_an_etag_replaced_by_a_last_modified_does_not_keep_the_old_one(conn):
    """The upsert writes BOTH columns, so a site that stops sending an ETag must
    not have a stale one replayed at it for ever."""
    validators.save(conn, {URL: {"ETag": ETAG}})
    validators.save(conn, {URL: {"Last-Modified": MODIFIED}})

    assert validators.load(conn)[URL] == {"Last-Modified": MODIFIED}


def test_loading_a_narrowed_set_does_not_read_the_whole_history(conn):
    """A crawl of one cell has no use for another cell's validators, and a
    warehouse accumulates a row per url ever visited."""
    validators.save(conn, {f"https://a.test/{n}": {"ETag": f'W/"{n}"'}
                           for n in range(50)})

    loaded = validators.load(conn, ["https://a.test/7", "https://a.test/9"])

    assert set(loaded) == {"https://a.test/7", "https://a.test/9"}


def test_pruning_drops_only_what_is_older(conn):
    """A stale validator is useless, never wrong — so this is housekeeping, and it
    must not take anything current with it."""
    validators.save(conn, {URL: {"ETag": ETAG}})
    conn.execute("UPDATE fetch_validator SET seen_at = '2020-01-01T00:00:00Z' "
                 " WHERE url = ?", (URL,))
    validators.save(conn, {"https://a.test/fresh": {"ETag": 'W/"f"'}})

    gone = validators.forget_older_than(conn, "2026-01-01T00:00:00Z")

    assert gone == 1
    assert list(validators.load(conn)) == ["https://a.test/fresh"]
