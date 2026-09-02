"""Layers 2 and 3 of `OP-64`, which shipped without a witness and are guarded here.

An adversarial review found the gap and named it exactly: layer 1 has tests and
mutations, layers 2 and 3 had a live run and nothing repeatable — and layer 3 is the
only one that WRITES.

WORSE, AND THIS IS THE PART WORTH KEEPING. Every listing-served snapshot on disk is
caught by layer 1, so on today's corpus layer 2 is unreachable: the candidate raises
before the cross-check is consulted. That does not make layer 2 pointless — it is the
guard for a page of the RIGHT shape carrying the WRONG contractor, which layer 1 only
catches when the caller passes an id — but it does mean the only way to see it work is a
test that constructs the case.

AND THE FIRST VERSION OF THIS FILE CLAIMED TO BE THAT TEST AND WAS NOT. Round two of the
review measured it exactly: every test here called `_listing_membership_numbers` or
`disown_impostors`, **none called `approve`**, and deleting the cross-check plus its
counter left the suite green. Layer 3 was covered; layer 2 was covered by a sentence.
`test_the_cross_check_refuses_inside_approve` below is the witness that was missing.

WHAT LAYER 2 IS FOR. The listing's `card_membership_number` is unique across all 17,304
rows with none blank; the profile page's `membership_number` is not. So a profile that
disagrees with its own listing card is not reporting a different fact about the same
contractor — it is reporting a different contractor.

WHY IT REFUSES RATHER THAN CORRECTS. Writing the listing's number over the profile's
leaves a row that passes every check and is still half somebody else's: measured, five
declared columns on the poisoned rows belong to the stranger, not one.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from scrapex import contractors


def _warehouse() -> sqlite3.Connection:
    """The two tables the cross-check reads, and nothing else.

    A real registry is not needed: both functions under test take a connection and
    read `generic_record` through `dataset_definition`, so the schema they actually
    depend on is small enough to state — which also makes what they depend on
    visible rather than implied.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE dataset_definition (
            dataset_definition_id INTEGER PRIMARY KEY,
            dataset_key TEXT, valid_to TEXT);
        CREATE TABLE generic_record (
            generic_record_id INTEGER PRIMARY KEY,
            dataset_definition_id INTEGER, status TEXT, data_json TEXT,
            -- `record_key` is the upsert key the coverage read joins on. Named
            -- here rather than left out, because a stub that omits a column the
            -- production query needs is a stub that cannot see a real failure.
            record_key TEXT);
        -- `approve` ends with a coverage line, reading the sighting ledger.
        -- Empty here on purpose: the run under test discovered nothing new, and an
        -- empty ledger is a real state rather than a convenience.
        CREATE TABLE dataset_sighting (
            dataset_sighting_id INTEGER PRIMARY KEY, dataset_key TEXT,
            external_id TEXT, first_seen_at TEXT, last_seen_at TEXT,
            seen_count INTEGER, first_run_ref TEXT,
            last_absent_at TEXT, last_absent_run_ref TEXT);
        INSERT INTO dataset_definition VALUES (1, 'contractors', NULL),
                                              (2, 'contractor_profiles', NULL);
    """)
    return conn


def _listing(conn, contractor_id, number, status="active"):
    conn.execute("INSERT INTO generic_record (dataset_definition_id, status, data_json) "
                 "VALUES (1, ?, ?)",
                 (status, json.dumps({"contractor_id": contractor_id,
                                      "card_membership_number": number})))


def _profile(conn, contractor_id, number, status="active"):
    conn.execute("INSERT INTO generic_record (dataset_definition_id, status, data_json) "
                 "VALUES (2, ?, ?)",
                 (status, json.dumps({"contractor_id": contractor_id,
                                      "membership_number": number})))


# ---- layer 2's reader -------------------------------------------------------

def test_the_listing_numbers_are_read_in_one_pass():
    """It returns a MAP, and that is the fix an adversarial review demanded.

    The first version asked per page: `json_extract` in a WHERE cannot use an index,
    so each lookup scanned every `generic_record` row — measured at 78 ms against
    104 ms to parse the page pair it was checking, which is 22 minutes added to a
    30-minute run."""
    conn = _warehouse()
    _listing(conn, "1001", "111")
    _listing(conn, "1002", "222")
    assert contractors._listing_membership_numbers(conn) == {"1001": "111", "1002": "222"}


def test_a_listing_row_the_site_stopped_publishing_is_still_a_witness():
    """`status` IS NOT FILTERED, and that is deliberate.

    `sightings.mark_unavailable` moves a listing row out of `active` for a contractor
    the site stopped publishing — the SAME population whose profile ids die. Filtering
    to active would switch the cross-check off for exactly the contractors it exists to
    protect."""
    conn = _warehouse()
    _listing(conn, "1001", "111", status="unavailable")
    numbers = contractors._listing_membership_numbers(conn)
    assert numbers == {"1001": "111"}, (
        "an unavailable listing row stopped being a witness, so a dead contractor's "
        "profile is now unchecked — which is the case the guard is for")


def test_a_blank_number_is_not_a_witness():
    """An absent value cannot disagree with anything, and must not be read as ''."""
    conn = _warehouse()
    _listing(conn, "1001", "")
    assert contractors._listing_membership_numbers(conn) == {}


# ---- layer 3, the only layer that writes ------------------------------------

class _Profiles:
    dataset_key = "contractor_profiles"


class _Directory:
    profiles = _Profiles()


def test_a_profile_that_disagrees_is_found_and_a_dry_run_writes_nothing():
    conn = _warehouse()
    _listing(conn, "1001", "111")
    _profile(conn, "1001", "999")          # disagrees — the impostor
    _listing(conn, "1002", "222")
    _profile(conn, "1002", "222")          # agrees — must be left alone

    found = contractors.disown_impostors(conn, _Directory(), dry_run=True)
    assert found == 1
    statuses = [r[0] for r in conn.execute(
        "SELECT status FROM generic_record WHERE dataset_definition_id = 2")]
    assert statuses == ["active", "active"], "a dry run retired a row"


def test_repair_retires_only_the_one_that_disagrees():
    """THE LIVE RUN'S RESULT, made repeatable. Twelve rows carried one stranger's
    number and the thirteenth holder was its rightful owner; twelve were retired and
    the owner was left alone, because the guard tests AGREEMENT and not the value."""
    conn = _warehouse()
    _listing(conn, "1001", "111")
    _profile(conn, "1001", "999")
    _listing(conn, "1002", "222")
    _profile(conn, "1002", "222")

    assert contractors.disown_impostors(conn, _Directory(), dry_run=False) == 1
    rows = dict(conn.execute(
        "SELECT json_extract(data_json, '$.contractor_id'), status "
        "FROM generic_record WHERE dataset_definition_id = 2"))
    assert rows == {"1001": "retired", "1002": "active"}


def test_a_profile_with_no_listing_row_is_left_alone():
    """148 contractors were reached by the profile crawl and never by an approved
    listing card. The cross-check has nothing to compare for them, and must not
    invent a verdict — they are covered by layer 1 alone, which the PR says out loud
    rather than implying."""
    conn = _warehouse()
    _profile(conn, "1001", "999")
    assert contractors.disown_impostors(conn, _Directory(), dry_run=False) == 0
    assert [r[0] for r in conn.execute(
        "SELECT status FROM generic_record WHERE dataset_definition_id = 2")] == ["active"]


def test_an_already_retired_row_is_not_retired_twice():
    """`--impostors` is expected to be run more than once. It reports 0 today because
    the 14 are already retired, and that must stay true rather than churning."""
    conn = _warehouse()
    _listing(conn, "1001", "111")
    _profile(conn, "1001", "999", status="retired")
    assert contractors.disown_impostors(conn, _Directory(), dry_run=False) == 0


def test_a_clean_warehouse_writes_nothing_and_says_so(capsys):
    """The first version ran `executemany` over an empty list, committed, and printed
    `retired 0 row(s)` — which reads as an action taken.

    ASSERTING THE RETURN VALUE WAS NOT ENOUGH, and a mutation proved it: removing the
    early return changed nothing observable through the return, because the write is
    empty either way. What the guard actually protects is the REPORT, so the report is
    what this asserts."""
    conn = _warehouse()
    _listing(conn, "1001", "111")
    _profile(conn, "1001", "111")
    assert contractors.disown_impostors(conn, _Directory(), dry_run=False) == 0
    said = capsys.readouterr().out
    assert "retired" not in said, (
        f"a clean warehouse reported a repair it did not perform: {said!r}")


def test_a_directory_with_no_profile_reader_is_a_no_op():
    """Every other directory — Balady, the UAE — has no profile dataset yet."""
    class _NoProfiles:
        profiles = None
    assert contractors.disown_impostors(_warehouse(), _NoProfiles(), dry_run=False) == 0


# ---- layer 2, driven through `approve` itself -------------------------------

def test_the_cross_check_refuses_inside_approve(monkeypatch, capsys):
    """THE WITNESS THIS FILE CLAIMED TO BE AND WAS NOT.

    Round two proved the gap by deletion: removing the cross-check and its counter
    from `approve` left the whole suite green. Everything else here exercises the
    two helpers; nothing drove the function that uses them.

    `approve` is stubbed down to its seams rather than given a real warehouse: the
    pages come from `_pairs`, the candidate from the directory, and the write from
    `service.approve_candidate`. What is under test is the decision BETWEEN them —
    that a profile disagreeing with its listing card is refused, counted, and said."""
    from types import SimpleNamespace

    conn = _warehouse()
    _listing(conn, "1001", "111")          # the listing says 111
    _listing(conn, "1002", "222")

    class _Candidate:
        approvable = True
        warnings: list[str] = []
        def __init__(self, number):
            self.rows = [{"membership_number": number}]
            # ONE FIELD, BECAUSE `CandidateApproval` REQUIRES ONE. A stub that
            # skips it fails validation instead of the thing under test, and the
            # error reads as a defect in `approve` rather than in the fixture.
            self.fields = [SimpleNamespace(field_key="contractor_id",
                                           source_name="Contractor id")]
            self.locator = "div.info-box"

    numbers = {"1001": "999", "1002": "222"}   # 1001 disagrees, 1002 agrees
    directory = SimpleNamespace(
        key="muqawil_org", display_name="x", base_url="https://example.test/",
        dataset_key="contractors", identity_field="contractor_id",
        candidate=lambda *a, **k: _Candidate("x"),
        profiles=SimpleNamespace(
            dataset_key="contractor_profiles",
            candidate=lambda en, ar, *, contractor_id: _Candidate(numbers[contractor_id]),
            groups=(), locate=lambda *a, **k: None, dataset_name="Contractor profiles"),
    )
    # RECORDS THE `ids` IT WAS HANDED rather than swallowing it. This stub used to
    # take `(conn, run_ref)` only, so `approve` gaining an `ids` keyword raised
    # TypeError here -- and the widening that silences that (`**_`) would assert
    # nothing about the argument. `forwarded` is what the assertion at the end reads.
    forwarded: list[tuple[str, ...]] = []

    def _stub_pairs(conn, run_ref, *, ids: tuple[str, ...] = ()):
        forwarded.append(tuple(ids))
        return {
            "https://example.test/contractors/1001/143": {"en": (1, "<html></html>")},
            "https://example.test/contractors/1002/143": {"en": (2, "<html></html>")},
        }

    monkeypatch.setattr(contractors, "_pairs", _stub_pairs)
    monkeypatch.setattr(contractors, "_contractor_of",
                        lambda key: key.rsplit("/", 2)[-2])
    written: list[str] = []
    monkeypatch.setattr(contractors.service, "approve_candidate",
                        lambda conn, sid, approval, candidate=None: written.append(sid) or {})
    monkeypatch.setattr(contractors, "write_groups", lambda *a, **k: (0, 0))

    contractors.approve(conn, directory, "run-x")
    # READ BEFORE ASSERTING. `capsys` drains on read, so a failure that asserts
    # first prints nothing about why — which cost a debugging round here.
    said = capsys.readouterr().out

    assert written == [2], (
        "the disagreeing page was written, or the agreeing one was not: "
        + str(written) + " -- the run said: " + said)

    assert "membership number 999 on the profile page but 111 on the listing" in said, (
        "the refusal did not name both numbers, so nobody can check it")
    assert "1 page(s) refused because the profile and the listing disagree" in said, (
        "the mismatch was folded into the ordinary refusals and lost its own count")

    # AND THE `ids` KEYWORD IS FORWARDED, NOT DROPPED. `approve` gained it so a
    # re-approval can be narrowed to profiles a person named; a version that accepted
    # the argument and passed nothing on would reapprove all 17,417 rows and read as a
    # success. The empty tuple above proves the default; the call below proves the pass.
    assert forwarded == [()], (
        "the unnarrowed call did not reach the page reader with an empty id set: "
        + str(forwarded))

    contractors.approve(conn, directory, "run-x", ids=("1001",))
    capsys.readouterr()
    assert forwarded[-1] == ("1001",), (
        "the named id never reached `_pairs`, so narrowing was accepted and ignored: "
        + str(forwarded))
