"""An older page never overwrites a record whose current evidence is newer.

THE UPSERT TOOK WHICHEVER PAGE ARRIVED LAST, however old. `approve_candidate` writes
`generic_record` with `ON CONFLICT ... DO UPDATE SET data_json=excluded.data_json`, and
nothing asked when the incoming page was captured. The one thing that ever stopped a stale
write was the revision insert colliding with `UNIQUE (generic_record_id,
source_snapshot_id, content_hash)` and rolling the page back -- and R-20 confirms an
unchanged record instead of writing a revision, so most pages never had even that.

MEASURED ON THE OWNER'S WAREHOUSE, 2026-09-26, the day PR #1082 would have made it happen
at scale. A Resume stores new pages under an OLD job's ref, so job 150 holds listing
evidence from 09-03 to 09-12 and job 157 holds 09-05 to 09-06, and any walk that reads 150
before 157 writes the older listing over the newer one:

    listing URLs in job 150 captured after job 157 ended     1,076
      also present in job 157                                1,072
      where job 157's copy has no revision to collide with     236

WHY THESE TESTS BUILD THE OLDER PAGE BY HAND. `save_snapshot` stamps `captured_at` with the
clock and `trg_generic_page_snapshot_immutable_update` forbids changing it afterwards --
rightly, capture time is a fact. So the older page is INSERTED with its capture time, the
way it would have been stored on the day it was fetched, through the same `encode` the
product uses. Everything after that is the real `approve_candidate` on the real schema.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import ApprovalField, CandidateApproval
from scrapex.extract.muqawil import listing_candidate
from scrapex.snapshotbody import encode

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
URL = "https://muqawil.org/en/contractors?page=1"
FIELD = "card_city_region"


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


def _captured(conn, at: str, html: str = LISTING) -> int:
    """A page as it was stored on the day it was fetched, `at` being that day."""
    body, codec, dict_id = encode(conn, html, label=None)
    cursor = conn.execute(
        "INSERT INTO generic_page_snapshot "
        "(source_url, html_content, content_hash, crawl_run_ref, html_codec, "
        " html_dict_id, captured_at) VALUES (?,?,?,?,?,?,?)",
        (URL, body, service._digest(html) + at, None, codec, dict_id, at))
    conn.commit()
    return int(cursor.lastrowid)


def _approval(candidate) -> CandidateApproval:
    return CandidateApproval(
        table_index=0, site_key="muqawil_org",
        site_display_name="Saudi Contractors Authority",
        dataset_key="contractors", dataset_name="Contractors",
        fields=[ApprovalField(field_key=f.field_key, display_name=f.source_name,
                              data_type="text",
                              identity=(f.field_key == "contractor_id"))
                for f in candidate.fields])


def _saying(candidate, value: str):
    """The same page with one column saying `value` -- a card that changed between two
    captures, which is exactly what makes the order of two readings matter."""
    return dataclasses.replace(
        candidate,
        rows=[{**row, FIELD: f"{value} {n}"} for n, row in enumerate(candidate.rows)])


def _approve(conn, snapshot: int, candidate) -> dict:
    result = service.approve_candidate(conn, snapshot, _approval(candidate),
                                       candidate=candidate)
    conn.commit()
    return result


def _values(conn) -> list[str]:
    return [json.loads(row[0]).get(FIELD) for row in conn.execute(
        "SELECT data_json FROM generic_record ORDER BY record_key")]


def _revisions(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]


# ---- the defect ---------------------------------------------------------------

def test_an_older_page_read_after_a_newer_one_keeps_the_newer_value(conn):
    """THE WHOLE DEFECT. The 09-12 reading is written, then the 09-05 reading arrives --
    which is what reading job 150 before job 157 does -- and the record must still say what
    the site said on 09-12."""
    base = listing_candidate(LISTING)
    newer = _captured(conn, "2026-09-12T05:32:37Z")
    older = _captured(conn, "2026-09-05T10:19:21Z")

    _approve(conn, newer, _saying(base, "NEWER"))
    result = _approve(conn, older, _saying(base, "OLDER"))

    assert all(value.startswith("NEWER") for value in _values(conn)), (
        f"an older page overwrote a record whose evidence is newer: {_values(conn)[:3]}")
    assert result["kept_newer"] == len(base.rows), (
        f"the refusal was not counted, so the pass reads as having written everything: "
        f"{result['kept_newer']} of {len(base.rows)}")


def test_the_refused_page_writes_no_revision(conn):
    """A REVISION HERE WOULD RECORD A CHANGE BACK THAT NEVER HAPPENED, in a table that is
    append-only and cannot take it back. The accidental `UNIQUE` protection only ever
    covered pages that had written a revision before -- 534 of job 157's 908 -- so this is
    asserted on a page that has NONE, which is the 374 that had no protection at all."""
    base = listing_candidate(LISTING)
    newer = _captured(conn, "2026-09-12T05:32:37Z")
    older = _captured(conn, "2026-09-05T10:19:21Z")
    _approve(conn, newer, _saying(base, "NEWER"))
    before = _revisions(conn)

    _approve(conn, older, _saying(base, "OLDER"))

    assert _revisions(conn) == before, (
        f"the refused page wrote {_revisions(conn) - before} revision(s): a false "
        f"'change back' is now permanent history")


# ---- what must keep working ---------------------------------------------------

def test_a_newer_page_after_an_older_one_still_overwrites(conn):
    """THE NORMAL ORDER IS UNTOUCHED. Every crawl read in capture order goes through
    here, and the rule must cost it nothing."""
    base = listing_candidate(LISTING)
    older = _captured(conn, "2026-09-05T10:19:21Z")
    newer = _captured(conn, "2026-09-12T05:32:37Z")

    _approve(conn, older, _saying(base, "OLDER"))
    result = _approve(conn, newer, _saying(base, "NEWER"))

    assert all(value.startswith("NEWER") for value in _values(conn)), _values(conn)[:3]
    assert result["kept_newer"] == 0, result["kept_newer"]


def test_the_same_page_re_read_with_a_corrected_parser_still_writes(conn):
    """EQUAL IS ALLOWED, AND IT IS THE CASE THE WHOLE INTERPRET SEAM EXISTS FOR.

    Re-reading one stored page with a corrected parser compares that page with ITSELF.
    Refusing equal would close exactly the door the owner ruled open on 2026-09-26 -- the
    newest run is re-read on every press so a parser fix reaches it."""
    base = listing_candidate(LISTING)
    page = _captured(conn, "2026-09-12T05:32:37Z")

    _approve(conn, page, _saying(base, "FIRST PARSE"))
    result = _approve(conn, page, _saying(base, "CORRECTED PARSE"))

    assert all(value.startswith("CORRECTED PARSE") for value in _values(conn)), (
        f"a corrected parse of the same page was refused as older: {_values(conn)[:3]}")
    assert result["kept_newer"] == 0
    assert result["reparsed"] is True


def test_a_page_captured_in_the_same_second_is_not_refused(conn):
    """`captured_at` HAS ONE-SECOND RESOLUTION, so two different pages of one record can
    share a stamp. Neither can be proved older, so neither is refused -- the rule refuses
    only what it can prove, and today's behaviour stands for the rest."""
    base = listing_candidate(LISTING)
    first = _captured(conn, "2026-09-12T05:32:37Z")
    second = _captured(conn, "2026-09-12T05:32:37Z", html=LISTING + "<!-- b -->")

    _approve(conn, first, _saying(base, "FIRST"))
    result = _approve(conn, second, _saying(base, "SECOND"))

    assert all(value.startswith("SECOND") for value in _values(conn)), _values(conn)[:3]
    assert result["kept_newer"] == 0


def test_the_predicate_reads_capture_times_through_the_covering_index(conn):
    """THE INDEX IS THE WHOLE COST OF THE RULE, and no assertion about a returned value
    can defend it -- removing `INDEXED BY` changes no answer. `LAST_EVIDENCE_SQL` measured
    390x from the same index for the same reason: `captured_at` sits beside the page body,
    and a row read drags the HTML with it."""
    plan = " ".join(str(row[-1]) for row in conn.execute(
        "EXPLAIN QUERY PLAN INSERT INTO generic_record "
        "(dataset_definition_id, record_key, schema_version_id, data_json, "
        "source_snapshot_id, source_locator, content_hash) VALUES (1,'k',1,'{}',1,'l','h') "
        "ON CONFLICT(dataset_definition_id, record_key) DO UPDATE SET "
        "data_json=excluded.data_json "
        f"WHERE {service.NOT_OLDER_THAN_CURRENT_SQL}"))
    # BOTH LOOKUPS, BY ALIAS. Asserting the index name once passed with it dropped from
    # one of the two -- the other still named it -- which is how this guard first survived
    # its own mutation.
    for alias in ("p", "q"):
        assert f"SEARCH {alias} USING COVERING INDEX ix_generic_page_snapshot_page" in plan, (
            f"the {alias!r} capture-time lookup no longer uses the covering index: {plan}")


def test_a_record_whose_evidence_did_not_travel_is_still_written(conn):
    """UNKNOWN IS ALLOWED, AND THE CASE IS NOT HYPOTHETICAL.

    `generic_record.source_snapshot_id` is NOT NULL with a foreign key, so in one warehouse
    the lookup always finds a page. But #665 records that `merge-warehouse` does not carry
    every table between his two machines, and a record that arrives without its source page
    has a freshness nobody can read. Refusing it would freeze that record for ever -- no
    page could ever be proved newer than a page that is not there.

    SIMULATED EXACTLY THAT WAY: the record's source page is made to point at nothing, with
    the foreign key off for the one statement that does it, as a merge would leave it.
    """
    base = listing_candidate(LISTING)
    newer = _captured(conn, "2026-09-12T05:32:37Z")
    older = _captured(conn, "2026-09-05T10:19:21Z")
    _approve(conn, newer, _saying(base, "NEWER"))

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("UPDATE generic_record SET source_snapshot_id = 999999999")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")

    result = _approve(conn, older, _saying(base, "OLDER"))

    assert all(value.startswith("OLDER") for value in _values(conn)), (
        f"a record whose source page is missing refused a write it cannot judge, so it can "
        f"never be written again: {_values(conn)[:3]}")
    assert result["kept_newer"] == 0


# ---- the pass says what it kept ----------------------------------------------

class _Card:
    """The least a listing candidate can be and still reach `approve_candidate`."""

    approvable = True
    warnings: list = []
    locator = "div.info-box"

    def __init__(self) -> None:
        from types import SimpleNamespace
        self.rows = [{"contractor_id": "1"}]
        self.fields = [SimpleNamespace(field_key="contractor_id", source_name="Id")]


def _approve_saying(monkeypatch, tmp_path, kept: int) -> str:
    """Drive the REAL `contractors.approve` over one listing page whose write reported
    `kept` rows kept at newer evidence, and return what the pass said."""
    import io
    from contextlib import redirect_stdout
    from types import SimpleNamespace

    from scrapex import contractors
    from scrapex import db as dbmod

    warehouse = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(warehouse)
    directory = SimpleNamespace(
        key="muqawil_org", display_name="Saudi Contractors Authority",
        base_url="https://muqawil.org/", dataset_key="contractors",
        identity_field="contractor_id", candidate=lambda *a, **k: _Card(), profiles=None)
    monkeypatch.setattr(
        contractors, "_pairs",
        lambda conn, directory, run_ref, *, ids=(): {
            "https://muqawil.org/contractors?page=1": {"en": (1, "<html/>"),
                                                       "ar": (2, "<html/>")}})
    monkeypatch.setattr(contractors.service, "approve_candidate",
                        lambda conn, sid, approval, candidate=None: {"kept_newer": kept})
    monkeypatch.setattr(contractors, "write_groups", lambda *a, **k: (0, 0))
    said = io.StringIO()
    try:
        with redirect_stdout(said):
            contractors.approve(warehouse, directory, "run-now")
    finally:
        warehouse.close()
    return said.getvalue()


def test_a_pass_that_kept_newer_evidence_says_how_many_rows(monkeypatch, tmp_path):
    """NO SILENT REFUSALS. A pass that read a thousand pages and wrote nothing from two
    hundred of them must not read as a pass that wrote everything it was given -- and on
    the owner's warehouse the first walk would have been exactly that pass."""
    said = _approve_saying(monkeypatch, tmp_path, kept=3)

    assert "3 row(s) kept their newer evidence" in said, (
        f"the pass refused stale rows and did not say so: {said}")
    assert "an older page never overwrites a newer one" in said, (
        f"the count is there but not the reason, so it reads as a failure: {said}")


def test_a_pass_that_kept_nothing_says_nothing_about_it(monkeypatch, tmp_path):
    """SAID ONLY WHEN IT HAPPENED. Every crawl read in capture order keeps nothing, and a
    line reporting zero on every pass is a line he learns to skip."""
    said = _approve_saying(monkeypatch, tmp_path, kept=0)

    assert "kept their newer evidence" not in said, said

