"""A stored page can say how it is encoded, and 4.55 GB becomes about 90 MB.

`docs/STORAGE.md`, on his instruction — «ليست الفكرة ضغط الملفات بل دراسة نشوف احنا
بنسحب اى ولية وبنحتفظ باية ولية وما الفائدة». The study said retain everything and
pay almost nothing; this is the almost-nothing, and these are the properties it has
to have to be trusted with the only copy of the evidence.

WHAT IS ACTUALLY AT RISK HERE, because it is not disk space. The plaintext of a
compressed page exists nowhere else. If a body cannot be decoded, the page is gone —
and the listing pages are not re-fetchable at all, because the ordering is a cached
random permutation. So the round trip is not a nicety, and neither is the dictionary
being un-deletable.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract.models import SnapshotCreate
from scrapex.extract.service import discover_snapshot, save_snapshot
from scrapex.snapshotbody import (
    PLAIN,
    ZSTD_RAW_DICT,
    UnknownCodec,
    decode,
    encode,
    label_for,
)

pytestmark = pytest.mark.docs


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


def _page(marker: str, rows: int = 40) -> str:
    """A page shaped like the real corpus: a large shared skeleton, small payload.

    THE SHAPE IS THE POINT. A stored muqawil listing page is 363 KB of which only
    17.8% is contractor cards; the other 291 KB is nav, footer, scripts and a city
    dropdown, near-identical across all 871 pages. A fixture of random bytes would
    compress badly and prove nothing about this corpus; a fixture of one repeated
    character would compress absurdly and prove nothing either.
    """
    skeleton = ("<nav>" + "menu item navigation footer script " * 900 + "</nav>")
    cards = "".join(
        f'<div class="section-card"><a href="/en/contractors/{marker}{i}/143">'
        f"company {marker}{i}</a><span>Riyadh</span></div>" for i in range(rows))
    return f"<html><body>{skeleton}<main>{cards}</main>{skeleton}</body></html>"


def _row(conn: sqlite3.Connection, snapshot_id: int) -> sqlite3.Row:
    return conn.execute(
        "SELECT page_snapshot_id, html_content, content_hash, html_codec, "
        "html_dict_id FROM generic_page_snapshot WHERE page_snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()


# ---- the round trip, which is the only thing that matters -------------------

def test_a_compressed_page_comes_back_exactly(conn):
    """Byte-for-byte, not "close enough". The plaintext is not stored anywhere
    else, and a listing page cannot be re-fetched — its ordering is a cached
    permutation, so page 40 tomorrow holds a different twenty contractors."""
    html = _page("a")
    saved = save_snapshot(conn, SnapshotCreate(
        source_url="https://muqawil.org/en/contractors?page=1",
        html_content=html, body_class="muqawil.org/listing"))
    row = _row(conn, saved["page_snapshot_id"])
    assert row["html_codec"] == ZSTD_RAW_DICT
    assert decode(conn, row) == html


def test_the_saved_bytes_really_are_not_the_page(conn):
    """The companion to the round trip, and it has to be asserted separately: a
    codec that stored the plaintext and called itself compressed would pass every
    round-trip test in this file."""
    html = _page("b")
    saved = save_snapshot(conn, SnapshotCreate(
        source_url="https://muqawil.org/en/contractors?page=2",
        html_content=html, body_class="muqawil.org/listing"))
    stored = _row(conn, saved["page_snapshot_id"])["html_content"]
    assert isinstance(stored, bytes), (
        "a compressed body must be stored as bytes, not as text that happens to "
        "look like it")
    assert len(stored) < len(html.encode("utf-8"))


def test_a_page_saved_without_a_class_is_stored_as_it_arrived(conn):
    """The default, and every caller that has not opted in gets it. The engine's
    save-a-page endpoint saves ONE page by hand: it has no class to share a
    dictionary with, and nothing to gain from creating one."""
    html = _page("c")
    saved = save_snapshot(conn, SnapshotCreate(
        source_url="https://example.com/one", html_content=html))
    row = _row(conn, saved["page_snapshot_id"])
    assert row["html_codec"] == PLAIN
    assert row["html_dict_id"] is None
    assert row["html_content"] == html
    assert decode(conn, row) == html


def test_a_row_that_predates_the_codec_still_reads(conn):
    """THE 1,728 ROWS ALREADY ON DISK, and the reason nothing was rewritten.

    `trg_generic_page_snapshot_immutable_update` aborts any UPDATE to this table,
    and it is right to — a stored page is evidence of what a site published on a
    date. So migration 0005 gives `html_codec` a DEFAULT instead of backfilling,
    and this asserts what that default buys: a row inserted with no knowledge of
    the codec at all is read by exactly the path that reads a new one.

    Inserted through raw SQL on purpose. Going through `save_snapshot` would set
    the column and prove nothing about the rows that were written before it
    existed.
    """
    html = "<html><body><p>stored in August, before any of this</p></body></html>"
    conn.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash) "
        "VALUES (?,?,?)", ("https://muqawil.org/en/contractors?page=400", html, "x"))
    row = conn.execute(
        "SELECT page_snapshot_id, html_content, html_codec, html_dict_id "
        "FROM generic_page_snapshot ORDER BY page_snapshot_id DESC LIMIT 1"
    ).fetchone()
    assert row["html_codec"] == PLAIN, (
        "a row inserted without naming a codec must default to 'plain', or every "
        "snapshot stored before 2026-08-20 becomes unreadable")
    assert decode(conn, row) == html


# ---- identity must not move when the encoding does -------------------------

def test_the_hash_is_of_the_page_and_not_of_its_encoding(conn):
    """Two runs that fetch the same page must agree on its content_hash whether
    one compressed it and the other did not. Otherwise the day a codec changes is
    the day every page becomes a different page, and every dedup and revision
    decision downstream moves with it."""
    html = _page("d")
    plain = save_snapshot(conn, SnapshotCreate(
        source_url="https://example.com/plain", html_content=html))
    packed = save_snapshot(conn, SnapshotCreate(
        source_url="https://example.com/packed", html_content=html,
        body_class="example.com/listing"))
    assert _row(conn, plain["page_snapshot_id"])["html_codec"] == PLAIN
    assert _row(conn, packed["page_snapshot_id"])["html_codec"] == ZSTD_RAW_DICT
    assert plain["content_hash"] == packed["content_hash"]


def test_the_extraction_path_reads_a_compressed_page(conn):
    """THE END-TO-END ONE. A codec that round-trips in isolation and is not wired
    into the reader would leave `discover_snapshot` parsing a zstd frame as HTML
    and reporting that the page contains no tables — which is a wrong answer that
    looks like a true one."""
    html = ("<html><body><table><tr><th>Name</th><th>City</th></tr>"
            "<tr><td>Alpha</td><td>Riyadh</td></tr>"
            "<tr><td>Beta</td><td>Jeddah</td></tr></table><div>"
            + "padding " * 4000 + "</div></body></html>")
    saved = save_snapshot(conn, SnapshotCreate(
        source_url="https://muqawil.org/en/contractors?page=9",
        html_content=html, body_class="muqawil.org/listing"))
    found = discover_snapshot(conn, saved["page_snapshot_id"])
    assert found["candidates"], "the compressed page parsed as no tables at all"
    assert found["candidates"][0]["estimated_row_count"] == 2
    assert found["candidates"][0]["sample_records"][0]["name"] == "Alpha"


# ---- the dictionary is load-bearing, so it is guarded ----------------------

def test_one_dictionary_serves_a_whole_class(conn):
    """The saving IS the sharing. A dictionary per page would store each page's
    skeleton beside itself and compress nothing across the corpus, which is
    precisely the failure zlib has here."""
    for page in range(1, 6):
        save_snapshot(conn, SnapshotCreate(
            source_url=f"https://muqawil.org/en/contractors?page={page}",
            html_content=_page(f"p{page}"), body_class="muqawil.org/listing"))
    labels = [r[0] for r in conn.execute("SELECT label FROM snapshot_dictionary")]
    assert labels == ["muqawil.org/listing"]


def test_two_pages_of_one_kind_get_one_label(conn):
    """THE PROPERTY THE WHOLE SAVING RESTS ON, pinned on `label_for` itself.

    The tests below pass their `body_class` as a literal, so none of them touches
    this function — and a `label_for` that returned a per-URL label would leave
    them all green while the corpus compressed at per-page rates. Found by
    mutating it: only the two-kinds test noticed, and only incidentally, because
    the strings it expected no longer matched.
    """
    first = label_for("https://muqawil.org/en/contractors?page=1", "listing")
    second = label_for("https://muqawil.org/en/contractors?page=717", "listing")
    assert first == second == "muqawil.org/listing"
    assert label_for("https://muqawil.org/en/contractors/881/143", "detail") != first
    # A page whose kind nobody supplied still shares with its own sort.
    assert (label_for("https://example.com/a") == label_for("https://example.com/b")
            == "example.com/page")


def test_the_two_page_kinds_do_not_share_a_dictionary(conn):
    """MEASURED, not tidiness: a same-kind dictionary reached 187x on listings and
    46x on profiles. A listing page is 363 KB of directory chrome and a profile is
    119 KB of a different layout; one dictionary covering both is worse than
    either, and keeping them apart costs one row."""
    save_snapshot(conn, SnapshotCreate(
        source_url="https://muqawil.org/en/contractors?page=1",
        html_content=_page("L"), body_class=label_for(
            "https://muqawil.org/en/contractors?page=1", "listing")))
    save_snapshot(conn, SnapshotCreate(
        source_url="https://muqawil.org/en/contractors/881/143",
        html_content=_page("D"), body_class=label_for(
            "https://muqawil.org/en/contractors/881/143", "detail")))
    labels = sorted(r[0] for r in conn.execute(
        "SELECT label FROM snapshot_dictionary"))
    assert labels == ["muqawil.org/detail", "muqawil.org/listing"]


def test_a_dictionary_cannot_be_changed_or_deleted(conn):
    """HARDER THAN THE SNAPSHOT TRIGGERS, and for a stronger reason. A changed
    snapshot loses one page. A changed dictionary loses every page compressed
    against it, silently, and only when somebody tries to read one — with no
    repair available, because the plaintext is not stored anywhere else."""
    save_snapshot(conn, SnapshotCreate(
        source_url="https://muqawil.org/en/contractors?page=1",
        html_content=_page("x"), body_class="muqawil.org/listing"))
    # COMMITTED FIRST, and the first draft of this test did not: the rollback
    # after the failed UPDATE also undid the INSERT that created the dictionary,
    # so the DELETE that followed matched no rows, fired no trigger, and the test
    # reported that deletion was allowed when it was simply never attempted.
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE snapshot_dictionary SET body = X'00' WHERE dict_id = 1")
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        conn.execute("DELETE FROM snapshot_dictionary WHERE dict_id = 1")
    conn.rollback()


# ---- refusing to be silently wrong -----------------------------------------

def test_an_unreadable_codec_raises_rather_than_returning_bytes(conn):
    """Returning the stored bytes would hand a caller a zstd frame to parse as
    HTML. That surfaces as "this page has no data", which sends the next person
    looking for a parser bug in a page that was never decoded."""
    saved = save_snapshot(conn, SnapshotCreate(
        source_url="https://example.com/future", html_content=_page("f")))
    row = dict(_row(conn, saved["page_snapshot_id"]))
    row["html_codec"] = "brotli-2031"
    with pytest.raises(UnknownCodec, match="brotli-2031"):
        decode(conn, row)


def test_a_page_that_would_grow_is_stored_as_it_arrived(conn):
    """A short page can compress to MORE bytes than it started with. A codec that
    is a pessimisation on some rows and an optimisation on others is one nobody
    can reason about, so the comparison is made on the real bytes rather than
    assumed from a ratio measured on 363 KB pages."""
    value, codec, dict_id = encode(conn, "<p>hi</p>", label="example.com/tiny")
    assert codec == PLAIN and dict_id is None and value == "<p>hi</p>"


# ---- and the mechanism has to actually pay ----------------------------------

def test_the_corpus_costs_far_less_than_the_sum_of_its_pages(conn):
    """THE GUARD THAT THE MECHANISM DELIVERS, and the one that would catch a codec
    quietly downgraded to per-page zlib.

    zlib gets 15.6x on this corpus and cannot do better, because its 32 KB window
    never reaches across a 121 KB skeleton — measured: 40 pages as one zlib block
    came to 15.8x, no better than separately. A shared dictionary reached 187x.
    The bar here is deliberately far below 187 and far above anything per-page
    zlib can reach, so it tests the PROPERTY rather than pinning a number that
    depends on the fixture.
    """
    pages = [_page(f"m{i}") for i in range(10)]
    raw = sum(len(p.encode("utf-8")) for p in pages)
    for index, html in enumerate(pages):
        save_snapshot(conn, SnapshotCreate(
            source_url=f"https://muqawil.org/en/contractors?page={index + 1}",
            html_content=html, body_class="muqawil.org/listing"))
    stored = conn.execute(
        "SELECT SUM(LENGTH(html_content)) FROM generic_page_snapshot").fetchone()[0]
    ratio = raw / stored
    assert ratio > 40, (
        f"the shared dictionary bought only {ratio:.1f}x on a corpus of "
        "near-duplicates; per-page compression alone reaches about 15x here, so "
        "this says the dictionary is not being shared")

def test_six_writers_racing_for_one_dictionary_all_get_the_winners(tmp_path):
    """THE RACE A SIX-WORKER CRAWL HITS, forced with a barrier rather than hoped for.

    `label` is UNIQUE, so writers that all miss the SELECT all attempt the INSERT and
    all but one raise IntegrityError. Not hypothetical: the first six-worker
    `--details` run over twenty pages stored 14 and reported 6 failures, and all six
    were this.

    TWO WEAKER VERSIONS OF THIS TEST WERE WRITTEN AND BOTH PASSED WITH THE FIX
    REMOVED, which is the only reason it looks like this:

      * six threads with no barrier -- twenty pages is not enough to force the
        interleaving, so they mostly did not collide;
      * a hand-ordered two-connection version -- B committed BEFORE A's SELECT, so A
        found the row and returned early, never reaching the INSERT the fix is about.

    A `threading.Barrier` fixes both: every thread is released only once all six have
    arrived, and the SELECT is the first thing `_dictionary` does, so all six miss it.

    The losers must end up with the WINNER'S body, never their own seed, because the
    winner's body is what the winner's rows are compressed against.
    """
    import threading

    from scrapex.snapshotbody import _dictionary

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()

    gate = threading.Barrier(6)
    got: list[tuple[int, bytes]] = []
    blew_up: list[Exception] = []
    lock = threading.Lock()

    def racer(n: int) -> None:
        conn = registry.engine.connect()
        try:
            gate.wait()
            found = _dictionary(conn, "muqawil.org/listing", f"page from {n}")
            conn.commit()
            with lock:
                got.append(found)
        except Exception as exc:
            with lock:
                blew_up.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=racer, args=(n,)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not blew_up, (
        f"{len(blew_up)} of six writers raised instead of reading the winner's "
        f"dictionary: {blew_up[0]!r}")
    assert len({dict_id for dict_id, _ in got} ) == 1, (
        f"six writers produced {len({d for d, _ in got})} dictionaries for one label")
    assert len({body for _, body in got}) == 1, (
        "two writers disagree about the body behind one dict_id, so one of them "
        "compressed its pages against a dictionary the row does not name")
    reader = registry.engine.connect()
    try:
        assert reader.execute(
            "SELECT COUNT(*) FROM snapshot_dictionary").fetchone()[0] == 1
    finally:
        reader.close()
