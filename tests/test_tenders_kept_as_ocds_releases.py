"""Tenders kept as OCDS releases, with the responses they came from (migration 0025).

On the real schema and the real migration stream, never a fixture schema (`CLAUDE.md`):

  * the ten tables follow Supabase's style as #1616 ruled it (ES-4), and the migration
    upgrades a warehouse at the version before it without touching what it holds;
  * the history is append-only and the evidence immutable, by trigger;
  * `tenderstore` stores a release once, keeps persons out of it, and compiles the
    current state by OCDS's merge rule (ES-3), from real World Bank notices;
  * the award tables stand empty until part 4 brings their writer, and already refuse
    what OCDS's codelists and their own pairs of columns refuse.
"""
from __future__ import annotations

import copy
import json
import re
import sqlite3
from pathlib import Path

import pytest

from scrapex import tenderstore
from scrapex.databases.domain import EngineDatabase
from scrapex.sites import worldbank as wb

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "0025_tenders_kept_as_ocds_releases.sql"
FIXTURE = Path(__file__).parent / "fixtures" / "worldbank" / "notices.json"
NOTICES = {n["id"]: n for n in json.loads(FIXTURE.read_text(encoding="utf-8"))["notices"]}
OPEN_REOI, IFB, ITS_AWARD = "OP00473710", "OP00158446", "OP00184991"

#: Every table 0025 creates, and the singular a foreign key to it is named after (ES-4).
TABLES = ("fetched_responses", "tender_processes", "tender_releases", "tenders",
          "tender_parties", "tender_party_roles", "tender_contact_points", "tender_items",
          "tender_classifications", "tender_locations", "tender_awards",
          "tender_award_suppliers", "tender_contracts", "tender_bids",
          "tender_beneficial_owners")
#: Created here on his ruling of 2026-10-17 (#1658), and written by nothing until part 4.
AWARD_TABLES = ("tender_awards", "tender_award_suppliers", "tender_contracts",
                "tender_bids", "tender_beneficial_owners")
SINGULAR = {"fetched_responses": "fetched_response", "tender_processes": "tender_process",
            "tender_releases": "tender_release", "tender_parties": "tender_party",
            "tender_awards": "tender_award", "crawl_job": "crawl_job",
            "source_site": "source_site"}


@pytest.fixture()
def conn(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    connection.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                       ("worldbank", "World Bank"))
    connection.commit()
    yield connection
    connection.close()


def _site(conn) -> int:
    return conn.execute("SELECT source_id FROM source_site WHERE source_key = 'worldbank'"
                        ).fetchone()[0]


def _store(conn, notice_id: str, notice: dict | None = None) -> tenderstore.Stored:
    raw = notice or NOTICES[notice_id]
    response = tenderstore.store_response(
        conn, target_uri=f"https://search.worldbank.org/api/v2/procnotices?id={notice_id}",
        status_code=200, content_type="application/json",
        headers={"content-type": "application/json"},
        body=json.dumps({"procnotices": [raw]}).encode("utf-8"))
    stored = tenderstore.store_release(conn, source_site_id=_site(conn),
                                       release=wb.release_from_notice(raw),
                                       fetched_response_id=response)
    conn.commit()
    return stored


# ---- the tables: Supabase's style, as #1616 ruled it (ES-4) -------------------------------

def test_every_new_table_is_strict_with_an_id_key():
    db_conn = sqlite3.connect(":memory:")
    db_conn.executescript("CREATE TABLE crawl_job (job_id INTEGER PRIMARY KEY);"
                          "CREATE TABLE source_site (source_id INTEGER PRIMARY KEY);")
    db_conn.executescript((ROOT / "db" / "engine" / "migrations" / MIGRATION)
                          .read_text(encoding="utf-8"))
    strict = dict(db_conn.execute("SELECT name, strict FROM pragma_table_list "
                                  "WHERE schema = 'main'"))
    for table in TABLES:
        assert strict[table] == 1, f"{table} is not STRICT"
        columns = list(db_conn.execute(f"PRAGMA table_info({table})"))
        assert (columns[0][1], columns[0][2], columns[0][5]) == ("id", "INTEGER", 1), table


def test_every_foreign_key_is_named_after_its_table_and_indexed(conn):
    for table in TABLES:
        # The LEADING column of an index: one whose first column is another cannot serve
        # a lookup by this key (#1658's merge gate).
        leading = {row[2] for index in conn.execute(f"PRAGMA index_list({table})")
                   for row in conn.execute(f"PRAGMA index_info({index[1]})") if row[0] == 0}
        for fk in conn.execute(f"PRAGMA foreign_key_list({table})"):
            target, column = fk[2], fk[3]
            assert target in SINGULAR, f"{table}.{column} points at {target}: name its singular"
            # `<singular>_id`, or a role before it when it says which of two keys it is.
            assert column == f"{SINGULAR[target]}_id" or column.endswith(
                f"_{SINGULAR[target]}_id"), f"{table}.{column} -> {target}"
            assert column in leading, f"{table}.{column} leads no index"


def test_every_table_definition_carries_a_comment():
    """SQLite has no COMMENT ON, so a definition's comment is the line above it."""
    lines = (ROOT / "db" / "engine" / "migrations" / MIGRATION).read_text(
        encoding="utf-8").splitlines()
    created = [number for number, line in enumerate(lines) if line.startswith("CREATE TABLE")]
    assert {re.match(r"CREATE TABLE (\w+)", lines[n]).group(1) for n in created} == set(TABLES)
    for number in created:
        assert lines[number - 1].startswith("--"), f"no comment above: {lines[number]}"


def test_an_existing_warehouse_gains_the_tables_and_keeps_its_sources(tmp_path, monkeypatch):
    db = EngineDatabase(tmp_path / "upgraded.db")
    whole = db._migrations
    at = [one.name for one in whole].index(MIGRATION)
    monkeypatch.setattr(db, "_migrations", whole[:at])
    db.initialize()
    with db.connect() as before:
        before.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                       ("muqawil_org", "Saudi Contractors Authority"))
        before.commit()
    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    assert db.initialize() == [whole[at].number]
    with db.connect() as after:
        names = {r[0] for r in after.execute("SELECT name FROM sqlite_master")}
        assert set(TABLES) <= names
        assert after.execute("SELECT source_name FROM source_site WHERE source_key = ?",
                             ("muqawil_org",)).fetchone()[0] == "Saudi Contractors Authority"
        assert after.execute("SELECT 1 FROM database_migration WHERE migration_name = ?",
                             (MIGRATION,)).fetchone()


# ---- the history and the evidence never change ------------------------------------------

def test_the_history_is_append_only(conn):
    stored = _store(conn, OPEN_REOI)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE tender_releases SET language = 'ar' WHERE id = ?",
                     (stored.tender_release_id,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM tender_releases WHERE id = ?", (stored.tender_release_id,))


def test_the_evidence_never_changes_and_reads_back_exactly(conn):
    body = json.dumps({"procnotices": [NOTICES[OPEN_REOI]]}).encode("utf-8")
    response = tenderstore.store_response(
        conn, target_uri="https://search.worldbank.org/api/v2/procnotices", status_code=200,
        content_type="application/json; charset=utf-8", headers={"etag": 'W/"x"'}, body=body)
    assert tenderstore.response_body(conn, response) == body
    stored_size = conn.execute("SELECT length(body) FROM fetched_responses WHERE id = ?",
                               (response,)).fetchone()[0]
    assert stored_size < len(body), "the body is stored compressed"
    with pytest.raises(sqlite3.IntegrityError, match="evidence and never changes"):
        conn.execute("UPDATE fetched_responses SET status_code = 404 WHERE id = ?", (response,))
    with pytest.raises(sqlite3.IntegrityError, match="evidence and never changes"):
        conn.execute("DELETE FROM fetched_responses WHERE id = ?", (response,))


def test_a_body_that_fails_its_digest_is_refused(conn):
    """A codec or storage fault must not hand back a different document as evidence."""
    conn.execute("DROP TRIGGER fetched_responses_immutable_update")
    response = tenderstore.store_response(
        conn, target_uri="https://x.worldbank.org/", status_code=200,
        content_type="application/json", headers={}, body=b'{"a": 1}')
    conn.execute("UPDATE fetched_responses SET body_sha256 = ? WHERE id = ?",
                 ("0" * 64, response))
    with pytest.raises(ValueError, match="fails its own digest"):
        tenderstore.response_body(conn, response)


# ---- storing a release ---------------------------------------------------------------------

def test_the_same_notice_read_twice_is_stored_once(conn):
    first, second = _store(conn, OPEN_REOI), _store(conn, OPEN_REOI)
    assert first.new and not second.new
    assert first.tender_release_id == second.tender_release_id
    assert conn.execute("SELECT count(*) FROM tender_releases").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM tender_contact_points").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM fetched_responses").fetchone()[0] == 2


def test_a_changed_notice_is_a_new_release_with_the_same_ref(conn):
    _store(conn, OPEN_REOI)
    changed = copy.deepcopy(NOTICES[OPEN_REOI])
    changed["bid_description"] = changed["bid_description"] + " (revised)"
    changed["api_modified_date"] = "2026-10-11T08:00:00Z"
    second = _store(conn, OPEN_REOI, changed)
    assert second.new
    refs = [r[0] for r in conn.execute("SELECT release_ref FROM tender_releases")]
    assert refs == [OPEN_REOI, OPEN_REOI]
    title = conn.execute("SELECT title FROM tenders").fetchone()[0]
    assert title.endswith("(revised)"), "the newer release decides the current state"


def test_persons_live_in_their_own_table_and_can_be_removed(conn):
    stored = _store(conn, OPEN_REOI)
    # The history is JSONB since 0026 (ES-6); `json()` reads it back as its text.
    payload = conn.execute("SELECT json(payload) FROM tender_releases WHERE id = ?",
                           (stored.tender_release_id,)).fetchone()[0]
    assert NOTICES[OPEN_REOI]["contact_email"] not in payload
    row = conn.execute("SELECT name, email, job_title FROM tender_contact_points").fetchone()
    assert tuple(row) == (NOTICES[OPEN_REOI]["contact_name"],
                          NOTICES[OPEN_REOI]["contact_email"],
                          NOTICES[OPEN_REOI]["contact_job_title"])
    conn.execute("DELETE FROM tender_contact_points")  # his ruling: removable
    assert conn.execute("SELECT count(*) FROM tender_releases").fetchone()[0] == 1


#: Every place OCDS puts a person: a contact point on any organisation, and a party's
#: beneficial owners. The history cannot be edited, so each is refused (#1658's gate).
PERSONS_IN_A_PAYLOAD = {
    "a party's contact point": lambda p: p["parties"][-1].update(
        contactPoint={"name": "A Person"}),
    "a party's beneficial owners": lambda p: p["parties"][-1].update(
        beneficialOwners=[{"id": "1", "name": "A Person"}]),
    "the procuring entity's contact point": lambda p: p["tender"].update(
        procuringEntity={"id": "x", "contactPoint": {"name": "A Person"}}),
    "the buyer's contact point": lambda p: p.update(
        buyer={"id": "x", "contactPoint": {"email": "a.person@example.org"}}),
    "a supplier's contact point": lambda p: p.update(
        awards=[{"id": "1", "suppliers": [{"id": "s", "contactPoint": {"name": "A Person"}}]}]),
    "a tenderer's contact point": lambda p: p["tender"].update(
        tenderers=[{"id": "t", "contactPoint": {"name": "A Person"}}]),
}


@pytest.mark.parametrize("where", sorted(PERSONS_IN_A_PAYLOAD))
def test_a_person_anywhere_in_the_payload_is_refused(conn, where):
    release = wb.release_from_notice(NOTICES[OPEN_REOI])
    PERSONS_IN_A_PAYLOAD[where](release.payload)
    with pytest.raises(ValueError, match="persons are kept beside it"):
        tenderstore.store_release(conn, source_site_id=_site(conn), release=release,
                                  fetched_response_id=None)
    assert conn.execute("SELECT count(*) FROM tender_releases").fetchone()[0] == 0


def test_a_release_whose_ocid_is_not_its_process_is_refused(conn):
    release = wb.release_from_notice(NOTICES[OPEN_REOI])
    release.payload["ocid"] = "scrapex-worldbank:another"
    with pytest.raises(ValueError, match="names ocid"):
        tenderstore.store_release(conn, source_site_id=_site(conn), release=release,
                                  fetched_response_id=None)


# ---- compiling the current state (ES-3) -------------------------------------------------------

def test_an_open_notice_compiles_to_its_tender_with_the_deadline_it_states(conn):
    _store(conn, OPEN_REOI)
    row = dict(conn.execute(
        "SELECT tender_ref, status, status_details, procurement_method, "
        "main_procurement_category, value_amount, value_currency, tender_period_end, "
        "tender_period_end_local_time, tender_period_end_zone FROM tenders").fetchone())
    assert row == {"tender_ref": "EG-EEAA-559382-CS-QCBS", "status": "active",
                   "status_details": "Published", "procurement_method": "open",
                   "main_procurement_category": "services", "value_amount": 70000.0,
                   "value_currency": "USD", "tender_period_end": "2026-11-05",
                   "tender_period_end_local_time": "14:00", "tender_period_end_zone": None}
    assert conn.execute("SELECT project_ref FROM tender_processes").fetchone()[0] == "P172548"
    assert [tuple(r) for r in conn.execute(
        "SELECT country_code, source_country_code FROM tender_locations")] == [("EG", "EG")]
    roles = {tuple(r) for r in conn.execute(
        "SELECT p.party_ref, r.role FROM tender_parties p "
        "JOIN tender_party_roles r ON r.tender_party_id = p.id")}
    assert ("worldbank", "funder") in roles
    assert any(role == "procuringEntity" for _, role in roles)
    assert conn.execute("SELECT classification_scheme FROM tender_items").fetchone()[0] == "UNSPSC"


@pytest.mark.parametrize("order", [(IFB, ITS_AWARD), (ITS_AWARD, IFB)],
                         ids=["invitation first", "award first"])
def test_an_award_closes_its_tender_and_keeps_the_deadline_the_invitation_stated(conn, order):
    """OCDS's record rule: what the award states replaces, what it leaves out stays. In
    either order of arrival: a collector reading the newest first stores the award before
    its invitation, and the compile follows the dates, not the arrival (#1658's gate)."""
    for notice_id in order:
        _store(conn, notice_id)
    assert conn.execute("SELECT count(*) FROM tender_processes").fetchone()[0] == 1
    row = conn.execute("SELECT status, tender_period_end, tender_period_end_local_time, "
                       "compiled_from_tender_release_id FROM tenders").fetchone()
    award_release = conn.execute("SELECT id FROM tender_releases WHERE release_ref = ?",
                                 (ITS_AWARD,)).fetchone()[0]
    assert tuple(row) == ("complete", "2022-02-06", "10:00", award_release)


def test_a_compile_is_a_rebuild_from_the_history(conn):
    stored = _store(conn, OPEN_REOI)

    def snapshot():
        return {t: [tuple(r)[1:] for r in conn.execute(f"SELECT * FROM {t} ORDER BY id")]
                for t in ("tenders", "tender_items", "tender_classifications",
                          "tender_locations")}

    before = snapshot()
    conn.execute("DELETE FROM tender_items")
    conn.execute("DELETE FROM tenders")
    tenderstore.compile_process(conn, stored.tender_process_id)
    assert snapshot() == before


# ---- the award tables: here now, written from part 4 on (his ruling, #1658) ---------------

def test_an_award_notice_leaves_the_award_tables_empty_until_their_writer(conn):
    """The award notice's payload carries its award and contract (`release_from_notice`),
    and still nothing is compiled from them: their writer is part 4's."""
    _store(conn, IFB)
    stored = _store(conn, ITS_AWARD)
    payload = json.loads(conn.execute("SELECT json(payload) FROM tender_releases WHERE id = ?",
                                      (stored.tender_release_id,)).fetchone()[0])
    assert payload["awards"][0]["id"] == NOTICES[ITS_AWARD]["contract_id"]
    assert payload["contracts"][0]["awardID"] == NOTICES[ITS_AWARD]["contract_id"]
    for table in AWARD_TABLES:
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0, table


def _award_chain(conn) -> dict[str, int]:
    """One row in each award table, as part 4 will write them, on a stored process."""
    stored = _store(conn, ITS_AWARD)
    process = stored.tender_process_id
    party = conn.execute("SELECT id, party_ref FROM tender_parties WHERE tender_process_id = ? "
                         "AND party_ref != 'worldbank'", (process,)).fetchone()
    award = conn.execute(
        "INSERT INTO tender_awards (tender_process_id, award_ref, title, status, awarded_at, "
        "value_amount, value_currency, value_amount_usd, contract_period_duration) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (process, "1703070", "Supply of transformers", "active", "2022-03-01",
         292182.0, "EGP", 18690.5, "P30M")).lastrowid
    conn.execute("INSERT INTO tender_award_suppliers (tender_award_id, tender_party_id, "
                 "value_amount_usd, value_is_split) VALUES (?,?,?,?)",
                 (award, party[0], 9345.25, 1))
    conn.execute("INSERT INTO tender_contracts (tender_award_id, contract_ref, signed_at, "
                 "no_objection_at) VALUES (?,?,?,?)", (award, "1703070", "2022-03-30",
                                                       "2022-03-20"))
    bid = conn.execute(
        "INSERT INTO tender_bids (tender_process_id, bid_ref, tender_party_id, status, "
        "value_amount, value_currency, evaluated_value_amount, evaluated_value_currency, "
        "technical_score, financial_score, combined_score, rank) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (process, "1", party[0], "valid", 319200.0, "EGP", 292182.0, "EGP",
         84.5, 100.0, 87.6, 1)).lastrowid
    owner = conn.execute(
        "INSERT INTO tender_beneficial_owners (tender_release_id, party_ref, owner_ref, name, "
        "nationality, residence, control) VALUES (?,?,?,?,?,?,?)",
        (stored.tender_release_id, party[1], "1", "A Person", "Egypt", "Egypt",
         "holds 25% or more of the shares")).lastrowid
    return {"process": process, "party": party[0], "award": award, "bid": bid,
            "owner": owner, "release": stored.tender_release_id}


def test_the_award_tables_hold_what_part_4_will_write(conn):
    rows = _award_chain(conn)
    assert tuple(conn.execute(
        "SELECT a.value_amount, a.value_currency, a.value_amount_usd, s.value_is_split, "
        "c.signed_at, b.rank FROM tender_awards a "
        "JOIN tender_award_suppliers s ON s.tender_award_id = a.id "
        "JOIN tender_contracts c ON c.tender_award_id = a.id "
        "JOIN tender_bids b ON b.tender_party_id = s.tender_party_id").fetchone()) == (
        292182.0, "EGP", 18690.5, 1, "2022-03-30", 1)
    assert conn.execute("SELECT tender_release_id FROM tender_beneficial_owners"
                        ).fetchone()[0] == rows["release"]


@pytest.mark.parametrize(("table", "column", "value"), [
    ("tender_awards", "status", "awarded"),                     # not in awardStatus
    ("tender_awards", "value_currency", "egp"),                 # ISO 4217 is upper case
    ("tender_awards", "value_currency", None),                  # an amount with no currency
    ("tender_awards", "contract_period_duration", "30 Month(s)"),  # as written, not ISO 8601
    ("tender_award_suppliers", "value_amount_usd", None),       # split, but no share
    ("tender_bids", "status", "rejected"),                      # bidStatus says disqualified
    ("tender_bids", "rank", 0),                                 # 1 is first
    ("tender_bids", "evaluated_value_currency", None),          # an amount with no currency
    ("tender_beneficial_owners", "name", None),                 # an owner is a named person
])
def test_the_award_tables_refuse_what_their_definitions_refuse(conn, table, column, value):
    rows = _award_chain(conn)
    key = {"tender_awards": rows["award"], "tender_bids": rows["bid"],
           "tender_beneficial_owners": rows["owner"]}.get(table)
    where = ("tender_award_id = ?", rows["award"]) if key is None else ("id = ?", key)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"UPDATE {table} SET {column} = ? WHERE {where[0]}", (value, where[1]))


def test_a_bid_or_a_supplier_must_name_a_party_of_the_warehouse(conn):
    rows = _award_chain(conn)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("UPDATE tender_bids SET tender_party_id = ? WHERE id = ?",
                     (rows["party"] + 1000, rows["bid"]))
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        conn.execute("UPDATE tender_award_suppliers SET tender_party_id = ?",
                     (rows["party"] + 1000,))


def test_a_beneficial_owner_can_be_removed_and_the_history_stays(conn):
    """His ruling on #1647: persons live outside the append-only history, so they can go."""
    rows = _award_chain(conn)
    conn.execute("DELETE FROM tender_beneficial_owners WHERE id = ?", (rows["owner"],))
    assert conn.execute("SELECT count(*) FROM tender_beneficial_owners").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM tender_releases WHERE id = ?",
                        (rows["release"],)).fetchone()[0] == 1


# ---- what the compile keeps, and what it lets go (#1658's merge gate) ---------------------

def test_a_draft_after_its_invitation_leaves_the_tender_with_no_status(conn):
    """OCDS's merge removes a field a later release sets to null. A draft states no status
    the Bank has published (`worldbank.py`), so the invitation's `active` must not stay."""
    _store(conn, IFB)
    draft = copy.deepcopy(NOTICES[ITS_AWARD])
    draft["notice_status"] = "Draft"
    _store(conn, ITS_AWARD, draft)
    assert tuple(conn.execute("SELECT status, status_details FROM tenders").fetchone()) == (
        None, "Draft")


def test_a_later_deadline_that_states_no_time_keeps_no_time(conn):
    """A second notice of the same process moves the deadline and names no hour: the
    invitation's 10:00 belonged to another day, so it must not be paired with this one."""
    _store(conn, IFB)
    later = copy.deepcopy(NOTICES[IFB])
    later.update(id="OP00158447", notice_status="Revised",
                 submission_date="2022-01-20T00:00:00Z", api_modified_date="2026-03-22T09:00:00Z",
                 submission_deadline_date="2022-03-01T00:00:00Z")
    del later["submission_deadline_time"]
    _store(conn, "OP00158447", later)
    assert conn.execute("SELECT count(*) FROM tender_processes").fetchone()[0] == 1
    assert tuple(conn.execute("SELECT tender_period_end, tender_period_end_local_time "
                              "FROM tenders").fetchone()) == ("2022-03-01", None)


def test_a_revision_that_stops_stating_a_field_lets_it_go(conn):
    """His ruling on #1658: a revised notice is a new version of the same release, and
    only its newest version is compiled, so the version it replaced leaves nothing."""
    _store(conn, OPEN_REOI)
    revised = copy.deepcopy(NOTICES[OPEN_REOI])
    revised.update(notice_status="Revised", api_modified_date="2026-10-11T08:00:00Z")
    for field in ("bid_estimate_amount", "submission_deadline_date", "submission_deadline_time",
                  "market_approach_code"):
        del revised[field]
    second = _store(conn, OPEN_REOI, revised)
    assert tuple(conn.execute(
        "SELECT status_details, value_amount, value_currency, procurement_method, "
        "tender_period_end, tender_period_end_local_time, compiled_from_tender_release_id "
        "FROM tenders").fetchone()) == ("Revised", None, None, None, None, None,
                                        second.tender_release_id)
    assert conn.execute("SELECT count(*) FROM tender_releases").fetchone()[0] == 2


def test_the_six_real_notices_compile_to_exactly_these_rows(conn):
    """Every compiled column the six real fixture notices fill, written out by hand."""
    for notice_id in sorted(NOTICES):
        _store(conn, notice_id)
    assert [tuple(r) for r in conn.execute(
        "SELECT p.source_record_id, t.tender_ref, t.title, t.status, t.status_details, "
        "t.procurement_method, t.main_procurement_category, t.value_amount, t.value_currency, "
        "t.tender_period_end, t.tender_period_end_local_time, t.tender_period_end_zone, "
        "t.published_at, r.release_ref FROM tenders t "
        "JOIN tender_processes p ON p.id = t.tender_process_id "
        "JOIN tender_releases r ON r.id = t.compiled_from_tender_release_id "
        "ORDER BY p.source_record_id")] == [
        ("P095392:ICB16:LOT2;ITEM1", "ICB 16: Lot 2; Item 1",
         "Copper Tubes, PE 80 Pipes and PE 80 Fittings", None, "Draft", None, None, None, None,
         None, None, None, "2021-03-29T03:51:56Z", "OP00012856"),
        ("P100047:ZAHRAAEL-MAADISUBSTATION-PACKAGEA", "Zahraa El-Maadi Substation - Package A",
         "turnkey bases", "active", "Revised", None, None, None, None, None, None, None,
         "2015-08-05T00:00:00Z", "OP00033824"),
        # The award decides the state and the date; the deadline is the invitation's.
        ("P146007:EGICB1-2022", "EG ICB 1-2022", "PE Pipes", "complete", "Published", "open",
         "goods", 1620430.71, "USD", "2022-02-06", "10:00", None, "2022-06-23T00:00:00Z",
         ITS_AWARD),
        ("P172548:EG-EEAA-559382-CS-QCBS", "EG-EEAA-559382-CS-QCBS",
         "developing guidelines for healthcare waste management in Egypt - rebidding process "
         "related to activity ref EG-EEAA-474647-CS-CQS", "active", "Published", "open",
         "services", 70000.0, "USD", "2026-11-05", "14:00", None, "2026-10-07T00:00:00Z",
         OPEN_REOI),
        ("notice:OP00208979", None, None, "planned", "Published", None, None, None, None, None,
         None, None, "2022-12-09T00:00:00Z", "OP00208979"),
    ]
    assert [tuple(r) for r in conn.execute(
        "SELECT p.source_record_id, x.party_ref, x.name, x.country_code, ro.role "
        "FROM tender_parties x JOIN tender_processes p ON p.id = x.tender_process_id "
        "JOIN tender_party_roles ro ON ro.tender_party_id = x.id "
        "WHERE x.party_ref != 'worldbank' ORDER BY p.source_record_id")] == [
        ("P100047:ZAHRAAEL-MAADISUBSTATION-PACKAGEA",
         "agency:Egyptian Electricity Transmission Company (EETC)",
         "Egyptian Electricity Transmission Company (EETC)", "EG", "procuringEntity"),
        ("P146007:EGICB1-2022", "agency:Egypt Gas", "Egypt Gas", "EG", "procuringEntity"),
        ("P172548:EG-EEAA-559382-CS-QCBS", "agency:Egyptian Environmental Affairs Agency",
         "Egyptian Environmental Affairs Agency", "EG", "procuringEntity"),
        ("notice:OP00208979", "agency:Egyptian Holding Company for Silos and Storage",
         "Egyptian Holding Company for Silos and Storage", "EG", "procuringEntity"),
    ]
    # One person per notice that names one (4 of 6), none for the award, which names none,
    # and each the contact of a party stored in its own process.
    assert [tuple(r) for r in conn.execute(
        "SELECT r.release_ref, c.party_ref, c.name, c.job_title, c.email, c.telephone, "
        "c.fax_number, c.url, EXISTS (SELECT 1 FROM tender_parties x "
        "  WHERE x.tender_process_id = r.tender_process_id AND x.party_ref = c.party_ref) "
        "FROM tender_contact_points c JOIN tender_releases r ON r.id = c.tender_release_id "
        "ORDER BY r.release_ref")] == [
        ("OP00033824", "agency:Egyptian Electricity Transmission Company (EETC)",
         "Contact Person", "Procurement Officer", "contact@example.org", "+20 000 0000",
         "+20 000 0001", None, 1),
        (IFB, "agency:Egypt Gas", "Contact Person", "Procurement Officer",
         "contact@example.org", "+20 000 0000", "+20 000 0001", "https://www.example.org", 1),
        ("OP00208979", "agency:Egyptian Holding Company for Silos and Storage",
         "Contact Person", "Procurement Officer", "contact@example.org", "+20 000 0000",
         "+20 000 0001", "https://www.example.org", 1),
        (OPEN_REOI, "agency:Egyptian Environmental Affairs Agency", "Contact Person",
         "Procurement Officer", "contact@example.org", "+20 000 0000", None,
         "https://www.example.org", 1),
    ]


def test_a_process_read_again_is_seen_again(conn):
    _store(conn, OPEN_REOI)
    conn.execute("UPDATE tender_processes SET first_seen_at = '2000-01-01T00:00:00Z', "
                 "last_seen_at = '2000-01-01T00:00:00Z'")
    before = conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ', 'now')").fetchone()[0]
    _store(conn, OPEN_REOI)
    first_seen, last_seen = conn.execute(
        "SELECT first_seen_at, last_seen_at FROM tender_processes").fetchone()
    assert first_seen == "2000-01-01T00:00:00Z"
    assert last_seen >= before


def test_a_release_nested_past_the_bound_is_refused_by_its_own_id():
    """`jsonb()` refuses a value past SQLite's own depth as `malformed JSON`, an `OperationalError`,
    which reads as the warehouse's fault. The bound is far above any real release, and below it."""
    assert tenderstore.MAX_PAYLOAD_DEPTH < 900

    def release(depth, wrap):
        title = "x"
        for _ in range(depth - 1):
            title = wrap(title)
        return tenderstore.Release(process_key="p", ocid="o", payload={
            "ocid": "o", "id": "r", "date": "2026-10-13T00:00:00Z", "tag": ["tender"],
            "tender": {"title": title}})

    for wrap in (lambda inner: [inner], lambda inner: {"k": inner}):
        tenderstore._assert_release_shape(release(tenderstore.MAX_PAYLOAD_DEPTH - 1, wrap))
        with pytest.raises(ValueError, match="'r' nests deeper than"):
            tenderstore._assert_release_shape(release(tenderstore.MAX_PAYLOAD_DEPTH, wrap))
