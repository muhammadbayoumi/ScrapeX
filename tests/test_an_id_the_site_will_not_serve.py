"""An id whose profile the site declines to serve is recorded, not re-asked for ever.

WHAT WAS ACTUALLY WRONG, MEASURED ON HIS WAREHOUSE 2026-09-07. An interpretation of 938
fetched profile pages turned 432 of 469 page pairs into rows and refused 37, every one
with `ProfileIdDidNotResolve`: the site answered `/contractors/<id>/143` with the
contractors listing, at HTTP 200. The row gap fell 469 -> 37 and stopped there.

    the card said 37 contractors had work waiting on them, for ever
    every later pass refused the same 37 and wrote nothing
    coverage could never reach its population

AND THE OBVIOUS WORD FOR IT IS THE WRONG ONE. All 20 of those ids recoverable from the
log carry an ACTIVE listing row last seen 2026-08-29, `last_absent_at = NULL`, and the
ledger holds ZERO proven absences out of 17,848 sightings. **The contractor is published;
its profile page is not served.** Two facts, and only the second has evidence -- so the
column is `profile_unresolved_at` and not `gone_at`, and `mark_unavailable` is left alone.

THE SEAMS ARE STUBBED AND THE SCHEMA IS REAL, which is the split this repository's rule
asks for: `db/engine/schema.sql` plus every migration builds the ledger under test, while
`_pairs`, `_contractor_of` and `approve_candidate` are stubs so the DECISION between them
is what each test measures. A hand-written `dataset_sighting` is what migration 0020
broke in `test_the_two_pages_must_agree.py`, and that failure is the argument.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from typing import ClassVar

import pytest

from scrapex import contractors, sightings
from scrapex import db as dbmod
from scrapex.extract.muqawil import PageIsNotAProfile, ProfileIdDidNotResolve

DATASET = "contractors"
PROFILES = "contractor_profiles"


@pytest.fixture()
def warehouse(tmp_path):
    """A real engine warehouse, migrated to the head of the stream."""
    conn = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(conn)
    try:
        yield conn
    finally:
        conn.close()


def _sight(conn: sqlite3.Connection, ids) -> None:
    for one in ids:
        conn.execute(
            "INSERT INTO dataset_sighting (dataset_key, external_id, seen_count) "
            "VALUES (?, ?, 1)", (DATASET, str(one)))
    conn.commit()


def _mark(conn: sqlite3.Connection, external_id: str) -> None:
    """Through the production writer, never raw SQL."""
    marked = sightings.mark_profile_unresolved(
        conn, DATASET, external_ids=(external_id,), run_ref="run-earlier")
    assert marked == (external_id,), f"the fixture could not mark {external_id}"


def _ledger(conn: sqlite3.Connection, external_id: str) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT profile_unresolved_at, profile_unresolved_run_ref FROM dataset_sighting "
        " WHERE dataset_key = ? AND external_id = ?", (DATASET, external_id)).fetchone()
    assert row is not None, f"{external_id} is not in the ledger at all"
    return row[0], row[1]


class _Candidate:
    """The least a candidate can be and still reach `approve_candidate`."""

    approvable = True
    warnings: ClassVar[list[str]] = []
    locator = "div.info-box"

    def __init__(self) -> None:
        self.rows = [{"membership_number": ""}]
        self.fields = [SimpleNamespace(field_key="contractor_id",
                                       source_name="Contractor id")]


def _directory(builder) -> SimpleNamespace:
    """A directory whose PROFILE candidate builder is the thing each test varies."""
    return SimpleNamespace(
        key="muqawil_org", display_name="Saudi Contractors Authority",
        base_url="https://muqawil.org/", dataset_key=DATASET,
        identity_field="contractor_id",
        candidate=lambda *a, **k: _Candidate(),
        profiles=SimpleNamespace(
            dataset_key=PROFILES, candidate=builder, groups=(),
            locate=lambda *a, **k: None, dataset_name="Contractor profiles"),
    )


def _run(conn, monkeypatch, builder, ids, run_ref="run-now") -> str:
    """Drive the real `approve` over one profile page per id. Returns what it said."""
    def _stub_pairs(conn, run_ref, *, ids: tuple[str, ...] = ()):
        return {f"https://muqawil.org/en/contractors/{one}/143": {"en": (1, "<html/>")}
                for one in ids_for_pages}

    ids_for_pages = tuple(ids)
    monkeypatch.setattr(contractors, "_pairs", _stub_pairs)
    monkeypatch.setattr(contractors, "_contractor_of",
                        lambda key: key.rsplit("/", 2)[-2])
    monkeypatch.setattr(contractors.service, "approve_candidate",
                        lambda conn, sid, approval, candidate=None: {})
    monkeypatch.setattr(contractors, "write_groups", lambda *a, **k: (0, 0))
    import io
    from contextlib import redirect_stdout
    said = io.StringIO()
    with redirect_stdout(said):
        contractors.approve(conn, _directory(builder), run_ref)
    return said.getvalue()


# ---- the refusal that IS evidence about the id ------------------------------

def test_the_site_refusing_an_id_is_recorded_in_the_ledger(warehouse, monkeypatch):
    """THE WHOLE POINT: the verdict outlives the job log.

    `log_retention_days` is 30 on his warehouse, so a refusal that lives only in the
    log expires -- and the 37 would return to the frontier a month later with nothing
    having changed about them.
    """
    _sight(warehouse, ["9001", "9002"])

    def _refuse_9001(english, arabic, *, contractor_id):
        if contractor_id == "9001":
            raise ProfileIdDidNotResolve(
                "this page links to 20 contractor(s) other than 9001")
        return _Candidate()

    said = _run(warehouse, monkeypatch, _refuse_9001, ["9001", "9002"])

    when, run_ref = _ledger(warehouse, "9001")
    assert when, f"the refusal was printed and not recorded: {said!r}"
    assert run_ref == "run-now", (
        f"the mark does not say which run judged it, so a pass later found to have "
        f"been wrong cannot be undone as a set: {run_ref!r}")
    assert _ledger(warehouse, "9002") == (None, None), (
        "a contractor whose profile read was marked as well")
    assert "1 contractor(s) marked as not served" in said, (
        f"the run did not say it had changed the ledger: {said!r}")


def test_a_refusal_that_is_not_about_the_id_records_nothing(warehouse, monkeypatch):
    """`R-27` FROM THE OTHER SIDE, and this is the guard the subclass exists for.

    `read_profile` raises the general refusal for a page that links to NO contractor,
    and says in its own words that it "may not be a profile page at all" -- a login
    wall, an interstitial, a truncated body. Marking that would take a live contractor
    out of the frontier because the site had a bad minute. `merge_locales` refusing a
    locale pair with different box counts (8 of 712 real profiles) is the same story.
    """
    _sight(warehouse, ["9101"])

    def _refuse_generally(english, arabic, *, contractor_id):
        raise PageIsNotAProfile(
            "this page links to no contractor at all, and every real profile links "
            "to itself")

    said = _run(warehouse, monkeypatch, _refuse_generally, ["9101"])

    assert "refused" in said, f"the page was not even refused: {said!r}"
    assert _ledger(warehouse, "9101") == (None, None), (
        "a page that told us nothing about the contractor took it out of the "
        "frontier: an interstitial is now indistinguishable from a dead id")
    assert "marked as not served" not in said


def test_a_second_interpretation_keeps_the_first_date(warehouse, monkeypatch):
    """WHEN IT WAS FIRST FOUND UNSERVED IS THE USEFUL FACT, and he re-interprets often
    -- four passes over the same 469 pairs on 2026-09-07 alone. A mark that moved its
    own date every pass would report "since today" for ever."""
    _sight(warehouse, ["9201"])

    def _refuse(english, arabic, *, contractor_id):
        raise ProfileIdDidNotResolve("other than 9201")

    _run(warehouse, monkeypatch, _refuse, ["9201"], run_ref="run-first")
    first, first_ref = _ledger(warehouse, "9201")
    said = _run(warehouse, monkeypatch, _refuse, ["9201"], run_ref="run-second")
    again, again_ref = _ledger(warehouse, "9201")

    assert (again, again_ref) == (first, first_ref), (
        f"the second pass moved the mark: {first}/{first_ref} -> {again}/{again_ref}")
    assert "marked as not served" not in said, (
        f"a pass that changed nothing reported a change: {said!r}")


def test_a_profile_that_reads_again_lifts_the_mark(warehouse, monkeypatch):
    """NOT OPTIONAL, for the reason `mark_unavailable`'s restore gives about itself: a
    mark that cannot be lifted is not half a feature, it is a contractor permanently
    outside the frontier. muqawil reissues membership numbers."""
    _sight(warehouse, ["9301"])
    _mark(warehouse, "9301")

    said = _run(warehouse, monkeypatch,
                lambda english, arabic, *, contractor_id: _Candidate(), ["9301"])

    assert _ledger(warehouse, "9301") == (None, None), (
        "the site served the profile and the mark stayed, so this contractor can "
        "never come back into the count")
    assert "served a profile page again" in said, (
        f"the run lifted a mark and did not say so: {said!r}")


def test_a_run_that_reads_unmarked_profiles_writes_nothing_to_the_ledger(
        warehouse, monkeypatch):
    """THE ORDINARY CASE IS 17,811 PROFILES. A clear-per-id that wrote unconditionally
    would touch every one of them on every pass, and report a change every time."""
    _sight(warehouse, ["9401", "9402"])

    said = _run(warehouse, monkeypatch,
                lambda english, arabic, *, contractor_id: _Candidate(),
                ["9401", "9402"])

    assert "served a profile page again" not in said, (
        f"a pass over unmarked contractors reported lifting a mark: {said!r}")
    assert "marked as not served" not in said
