"""The Oman candidate: the declared schema, R-12's shape, and what is deliberately absent.

No network. The fixtures are the same real 2026-09-18 captures the reader's tests use, so
the row that has no CR number is present in the English fixture and absent from the Arabic
one — which is why the candidate is built from the pairable rows and the reader's own
refusal is tested next door.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scrapex.extract.oman_tenderboard import (
    DATASET_KEY,
    FIELDS,
    IDENTITY_FIELD,
    NO_ARABIC_TWIN,
    bilingual_listing_candidate,
)
from scrapex.sites.oman_tenderboard import RegisterShapeError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
EN = (FIXTURES / "oman_register_en.html").read_text(encoding="utf-8")
AR = (FIXTURES / "oman_register_ar.html").read_text(encoding="utf-8")


def _pairable_en() -> str:
    """The English fixture without the firm that has no CR number.

    That firm cannot be paired by construction and the reader raises on it; this file is
    about the candidate, so it is removed here rather than the refusal being weakened.
    """
    return re.sub(r"<tr[^>]*>(?:(?!</tr>).)*ZYPHARSPH(?:(?!</tr>).)*</tr>",
                  "", EN, flags=re.S)


def _candidate():
    return bilingual_listing_candidate(_pairable_en(), AR)


# --- the declared schema -------------------------------------------------------------

def test_the_field_list_is_declared_and_in_its_declared_order():
    """Derived from the page, the schema becomes a property of which firms that page
    showed — which refused 823 of 897 muqawil pages."""
    fields = [f.field_key for f in _candidate().fields]
    assert fields[:len(FIELDS)] == list(FIELDS)


def test_every_field_is_nullable_and_text_whatever_this_page_happens_to_hold():
    """Measured per page, `nullable` flips and the schema hash with it."""
    for field in _candidate().fields:
        assert field.nullable is True, field.field_key
        assert field.data_type == "text", field.field_key


def test_the_identity_is_the_short_name_and_only_it():
    candidate = _candidate()
    identities = [f.field_key for f in candidate.fields if f.identity_candidate]
    assert identities == [IDENTITY_FIELD] == ["short_name"]


def test_the_same_schema_comes_back_for_a_page_with_different_firms():
    """The order and the set must not depend on the rows; that is the whole lesson.

    THE FIRM IS DROPPED FROM BOTH VIEWS, not just the English one. A page whose two
    views carry different firms is now a refusal in its own right -- in both directions
    -- so removing a row from one side tests the refusal rather than the schema.
    """
    one = [f.field_key for f in _candidate().fields]
    drop = r"<tr[^>]*>(?:(?!</tr>).)*00169963(?:(?!</tr>).)*</tr>"
    single_en = re.sub(drop, "", _pairable_en(), flags=re.S)
    single_ar = re.sub(drop, "", AR, flags=re.S)
    two = [f.field_key for f in
           bilingual_listing_candidate(single_en, single_ar).fields]
    assert one == two


def test_every_row_carries_every_field_even_when_absent():
    """`_validated_rows` walks the field list; a row simply lacking a key raises."""
    candidate = _candidate()
    names = {f.field_key for f in candidate.fields}
    for row in candidate.rows:
        assert set(row) == names


def test_the_dataset_is_named_once_and_not_guessed_per_call():
    assert DATASET_KEY == "oman_registered_vendors"
    assert _candidate().name == "Oman registered vendors"


# --- R-12's bilingual shape ----------------------------------------------------------

def test_the_english_view_fills_the_base_column_and_the_arabic_fills_its_twin():
    row = next(r for r in _candidate().rows if r["short_name"] == "0000")
    assert row["firm_name"] == "AL REEF LINE UNITED TRADE CO LLC"
    assert re.search(r"[؀-ۿ]", row["firm_name_ar"])
    assert row["registered_category"] == "Services"
    assert row["registered_category_ar"] == "الخدمات"


def test_the_address_base_column_stays_null_because_the_english_view_is_arabic():
    """A rule here, not an exception — measured on every row of page 1."""
    for row in _candidate().rows:
        assert row["address"] is None
    located = [r for r in _candidate().rows if r["address_ar"]]
    assert located and re.search(r"[؀-ۿ]", located[0]["address_ar"])


def test_an_identifier_gets_no_arabic_twin():
    declared = set(FIELDS)
    for name in NO_ARABIC_TWIN:
        assert name in declared
        assert f"{name}_ar" not in declared


def test_exactly_four_fields_carry_an_arabic_twin():
    """The four the site translates. `address`'s base column is NULL by measurement
    rather than absent, so the pair still exists."""
    twins = {f[:-3] for f in FIELDS if f.endswith("_ar")}
    assert twins == {"firm_name", "address", "registered_category", "company_type"}
    for name in twins:
        assert name in FIELDS, f"a twin with no base column: {name}"


# --- the category cell ---------------------------------------------------------------

def test_the_raw_category_cell_is_stored_whole():
    row = next(r for r in _candidate().rows if r["short_name"] == "00169963")
    assert row["registered_category"].startswith("Information Technology Services")
    assert len(row["registered_category"]) > 60, "several names, no separator"


def test_the_decomposed_list_is_deliberately_not_stored():
    """A delimited column is what `docs/GULF-EGYPT-SOURCES.md:353` refuses and what R-19
    measured the penalty for. The raw cell plus the vocabulary reproduces it."""
    names = {f.field_key for f in _candidate().fields}
    assert "registered_category_codes" not in names
    assert "registered_categories" not in names


def test_the_count_of_decomposed_categories_is_stored_flat():
    rows = {r["short_name"]: r for r in _candidate().rows}
    assert rows["0000"]["registered_category_count"] == "1"
    assert int(rows["00169963"]["registered_category_count"]) > 1


def test_what_the_vocabulary_could_not_explain_is_empty_on_every_measured_row():
    """The health signal: 102 of 102 decomposed with nothing left over."""
    assert all(r["registered_category_undecoded"] is None for r in _candidate().rows)


def test_a_cell_the_vocabulary_cannot_explain_lands_in_the_warehouse_visibly():
    broken = _pairable_en().replace(
        "<td>Services</td>", "<td>Services Something Unpublished</td>", 1)
    rows = bilingual_listing_candidate(broken, AR).rows
    leftover = [r["registered_category_undecoded"] for r in rows
                if r["registered_category_undecoded"]]
    assert leftover == ["Something Unpublished"]


# --- the rest of the row -------------------------------------------------------------

def test_a_blank_cell_reads_as_absent_and_not_as_empty_text():
    row = next(r for r in _candidate().rows if r["short_name"] == "00004174")
    assert row["reg_expiry"] is None
    assert row["address_ar"] is None or row["address_ar"]


def test_the_expiry_is_kept_as_the_site_printed_it():
    row = next(r for r in _candidate().rows if r["short_name"] == "0000")
    assert row["reg_expiry"] == "07-05-2026", "dd-MM-yyyy, not reformatted"


def test_the_short_name_keeps_its_leading_zeros():
    assert "0000" in {r["short_name"] for r in _candidate().rows}


def test_the_candidate_is_approvable_only_when_it_has_rows():
    """EMPTIED ON BOTH SIDES, and that correction is the point.

    This used to strip every English row and hand the reader three Arabic firms with no
    counterpart, then require a clean, warning-free candidate back. It was pinning the
    very absorption `join_languages` says it refuses -- "a firm present in one and not
    the other is news, not a row to skip" -- so the guard against dropping them could
    not have been added without this test going red.
    """
    assert _candidate().approvable is True
    strip = r"<tr[^>]*>(?:(?!</tr>).)*getProcActivities(?:(?!</tr>).)*</tr>"
    empty_en = re.sub(strip, "", _pairable_en(), flags=re.S)
    empty_ar = re.sub(strip, "", AR, flags=re.S)
    assert bilingual_listing_candidate(empty_en, empty_ar).approvable is False


def test_an_arabic_firm_with_no_english_twin_is_news_too():
    """The direction that was never checked: `join_languages` walked the English rows
    only, so a firm present in the Arabic view alone was dropped without a word."""
    drop_one = re.sub(r"<tr[^>]*>(?:(?!</tr>).)*00169963(?:(?!</tr>).)*</tr>", "",
                      _pairable_en(), flags=re.S)
    with pytest.raises(RegisterShapeError, match="no counterpart"):
        bilingual_listing_candidate(drop_one, AR)


def test_an_unpairable_firm_reaches_the_candidate_as_a_refusal_not_a_gap():
    """The full English fixture still holds the firm with no CR number."""
    with pytest.raises(RegisterShapeError, match="no counterpart"):
        bilingual_listing_candidate(EN, AR)


# --- a row whose two keys disagree (#1333) -------------------------------------------

def _disagreeing(html: str, key: str = "00169963") -> str:
    """The page with one firm's activities argument changed so its two keys disagree:
    the shape of `ALWASIT` against `nabil` on page 369 of job 191."""
    marked = html.replace(f"getProcActivities('{key}')", "getProcActivities('nabil')")
    assert marked != html, f"the fixture no longer carries {key}'s activities call"
    return marked


def test_the_warning_column_is_declared_last_and_has_no_arabic_twin():
    """LAST, so every column the Sheet already carries keeps its place; an identifier-
    class field, so `R-12` gives it no `_ar` twin."""
    assert FIELDS[-1] == "key_warning"
    assert [f.field_key for f in _candidate().fields][-1] == "key_warning"
    assert "key_warning" in NO_ARABIC_TWIN


@pytest.mark.parametrize("english, arabic", [
    pytest.param(True, False, id="english-only"),
    pytest.param(False, True, id="arabic-only"),
    pytest.param(True, True, id="both-views"),
])
def test_a_disagreeing_row_is_a_firm_whose_warning_column_says_why(english, arabic):
    """His ruling on #1333: record every disagreeing row, never skip it. In whichever
    view the keys disagree, the firm stays on the page under its commented key and its
    `key_warning` names both keys; every other row's is empty."""
    whole = _candidate()
    candidate = bilingual_listing_candidate(
        _disagreeing(_pairable_en()) if english else _pairable_en(),
        _disagreeing(AR) if arabic else AR)

    rows = {row["short_name"]: row for row in candidate.rows}
    assert candidate.approvable
    assert len(rows) == len(whole.rows), "no firm is left out"
    warning = rows["00169963"]["key_warning"]
    assert warning and "'00169963'" in warning and "'nabil'" in warning, warning
    assert warning.count("disagree beyond case") == 1, (
        f"the same sentence from both views is said once: {warning}")
    assert [key for key, row in rows.items() if row["key_warning"]] == ["00169963"]
    assert candidate.warnings == (f"row 00169963: {warning}",), candidate.warnings


def test_a_page_whose_keys_all_agree_has_an_empty_warning_column():
    candidate = _candidate()
    assert all(row["key_warning"] is None for row in candidate.rows)
    assert candidate.warnings == ()


def _approve_log(tmp_path, monkeypatch, english: str, arabic: str, *, after=None
                 ) -> tuple[str, dict[str, dict]]:
    """What the real `contractors.approve` says over one stored Oman page pair, on the
    real Oman directory and the real schema -- and the rows it stored, by key. `after`
    is handed the connection once the approval is done, and its output is in the log."""
    import io
    import json
    from contextlib import redirect_stdout

    from scrapex import contractors, directories
    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.snapshotbody import encode

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        def stored(url: str, html: str) -> int:
            body, codec, dict_id = encode(conn, html, label=None)
            cursor = conn.execute(
                "INSERT INTO generic_page_snapshot (source_url, html_content, "
                " content_hash, crawl_run_ref, html_codec, html_dict_id, captured_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (url, body, url, "run-1", codec, dict_id, "2026-10-03T10:00:00Z"))
            conn.commit()
            return int(cursor.lastrowid)

        en_url = "https://esnad.example/page?CTRL_STRDIRECTION=LTR&pageNo=369"
        ar_url = "https://esnad.example/page?CTRL_STRDIRECTION=RTL&pageNo=369"
        pair = {"en": (stored(en_url, english), english),
                "ar": (stored(ar_url, arabic), arabic)}
        monkeypatch.setattr(contractors, "_pairs",
                            lambda c, d, run_ref, *, ids=(): {"page-369": pair})
        monkeypatch.setattr(contractors, "coverage", lambda c, key: "")
        # `say` also writes a log file; it goes to this test's directory, not a home.
        monkeypatch.setattr(contractors, "LOG", tmp_path / "listing.log")

        said = io.StringIO()
        with redirect_stdout(said):
            contractors.approve(conn, directories.get("oman_tenderboard"), "run-1")
            if after is not None:
                after(conn)
        rows = {}
        for (blob,) in conn.execute(
                "SELECT r.data_json FROM generic_record AS r "
                "  JOIN dataset_definition AS d "
                "    ON d.dataset_definition_id = r.dataset_definition_id "
                " WHERE d.dataset_key = ?", (DATASET_KEY,)):
            row = json.loads(blob)
            rows[row["short_name"]] = row
        return said.getvalue(), rows
    finally:
        conn.close()


def _only(html: str, key: str) -> str:
    """The page with every firm row removed except `key`'s."""
    def keep(match):
        return match.group(0) if key in match.group(0) else ""
    return re.sub(r"<tr[^>]*>(?:(?!</tr>).)*getProcActivities(?:(?!</tr>).)*</tr>",
                  keep, html, flags=re.DOTALL)


def test_the_real_approval_writes_the_disagreeing_row_with_its_warning(
        tmp_path, monkeypatch):
    """Through `contractors.approve` onto the real schema: the firm is a stored row whose
    `key_warning` is filled, its neighbours' is empty, and the log he reads names it."""
    log, rows = _approve_log(tmp_path, monkeypatch, _disagreeing(_pairable_en()), AR)

    assert "approved 1 page(s)" in log, log
    assert "approved page-369 with a warning: row 00169963: " in log, log
    assert "refused page-369" not in log, log
    assert set(rows) == {row["short_name"] for row in _candidate().rows}
    assert "'nabil'" in rows["00169963"]["key_warning"], rows["00169963"]
    assert all(row["key_warning"] is None
               for key, row in rows.items() if key != "00169963"), rows


def test_a_page_whose_only_firm_disagrees_is_approved_not_refused(tmp_path, monkeypatch):
    """Under #1537 this page was refused -- nothing left once its one row was. Now the
    row is the firm, so the page is approved and the firm is stored."""
    log, rows = _approve_log(tmp_path, monkeypatch,
                             _only(_disagreeing(_pairable_en()), "nabil"),
                             _only(AR, "00169963"))

    assert "approved 1 page(s)" in log, log
    assert "refused page-369" not in log, log
    assert list(rows) == ["00169963"] and rows["00169963"]["key_warning"], rows


def test_a_page_whose_write_failed_is_not_called_approved_with_a_warning(
        tmp_path, monkeypatch):
    """The write rolled back, so nothing was approved; its row's warning must not be
    reported beside an approval that never happened."""
    from scrapex.extract import service

    def fail(*args, **kwargs):
        raise RuntimeError("disk full")
    monkeypatch.setattr(service, "approve_candidate", fail)
    log, rows = _approve_log(tmp_path, monkeypatch, _disagreeing(_pairable_en()), AR)

    assert "refused page-369: RuntimeError: disk full" in log, log
    assert "with a warning" not in log, log
    assert rows == {}


def test_a_firm_the_register_rekeyed_is_found_by_its_cr_number_end_to_end(
        tmp_path, monkeypatch):
    """THE REAL CHAIN, so the field names cannot drift apart: rows stored by the real
    approval, evidence read by the real `OmanPartition`, and the real Oman directory's
    `registration_field` joining the two. `00169963` comes back as `NEWKEY` with its CR
    number unchanged -- it changed key, it did not leave."""
    from scrapex import directories
    from scrapex.contractors import mark_departures
    from scrapex.partitioncrawl import (
        WHOLE,
        Attempt,
        CellOutcome,
        CellSize,
        PartitionOutcome,
    )
    from scrapex.sightings import record_sightings
    from scrapex.sites.oman_tenderboard import OmanPartition, read_ids

    directory = directories.get("oman_tenderboard")
    assert directory.registration_field == "cr_number"
    assert directory.registration_field in FIELDS
    rekeyed = _pairable_en().replace("<!-- <td>00169963</td> -->",
                                     "<!-- <td>NEWKEY</td> -->").replace(
        "getProcActivities('00169963')", "getProcActivities('newkey')")
    ids = read_ids(rekeyed)
    assert "NEWKEY" in ids and "00169963" not in ids, "the fixture must rekey the firm"

    def crawl(conn):
        stored = [row["short_name"] for row in _candidate().rows]
        record_sightings(conn, DATASET_KEY, stored)
        conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-08-20T09:00:00Z'")
        conn.commit()
        size = CellSize(cell=WHOLE, last_page=1, cards_per_page=len(ids),
                        tail_cards=len(ids), requests=1)
        outcome = PartitionOutcome(whole=size, cells=(CellOutcome(size=size, attempts=(
            Attempt(ids=ids, pages_read=1, witnessed=True, note="", run_ref="r2",
                    identity_evidence=OmanPartition().identity_evidence(rekeyed)),)),))
        assert outcome.provably_complete
        mark_departures(conn, directory, outcome, "r2")
        absent = conn.execute(
            "SELECT external_id FROM dataset_sighting "
            " WHERE dataset_key = ? AND last_absent_at IS NOT NULL",
            (DATASET_KEY,)).fetchall()
        assert absent == [], absent

    log, rows = _approve_log(tmp_path, monkeypatch, _pairable_en(), AR, after=crawl)

    assert rows["00169963"]["cr_number"], "the stored firm must carry its CR number"
    assert "changed key: 00169963 → NEWKEY (by cr_number)" in log, log


def test_rows_stored_before_the_column_move_to_its_version_when_a_new_run_is_approved(
        tmp_path, monkeypatch):
    """THE UPGRADE HE WILL RUN. His warehouse holds Oman rows approved under the schema
    without `key_warning` (v1). The first approval after this ships grows the schema:
    v1 retires, v2 opens, every stored row moves to v2 with a revision of its own, and
    the warning lands on the disagreeing row only. A regression in the retire-or-refuse
    path would reach every Oman row; this is the guard on it."""
    import dataclasses
    import io
    import json
    from contextlib import redirect_stdout

    from scrapex import contractors, directories
    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.extract import oman_tenderboard as extract
    from scrapex.snapshotbody import encode

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    monkeypatch.setattr(contractors, "coverage", lambda c, key: "")
    monkeypatch.setattr(contractors, "LOG", tmp_path / "listing.log")
    try:
        def page_pair(run_ref: str, page: int, english: str, arabic: str) -> dict:
            pair = {}
            for locale, direction, html in (("en", "LTR", english), ("ar", "RTL", arabic)):
                url = (f"https://esnad.example/page?CTRL_STRDIRECTION={direction}"
                       f"&pageNo={page}")
                body, codec, dict_id = encode(conn, html, label=None)
                snapshot = conn.execute(
                    "INSERT INTO generic_page_snapshot (source_url, html_content, "
                    " content_hash, crawl_run_ref, html_codec, html_dict_id, "
                    " captured_at) VALUES (?,?,?,?,?,?,?) RETURNING page_snapshot_id",
                    (url, body, f"{run_ref}{url}", run_ref, codec, dict_id,
                     f"2026-10-0{page}T10:00:00Z")).fetchone()[0]
                pair[locale] = (snapshot, html)
            conn.commit()
            return {f"page-{page}": pair}

        def approve(run_ref: str, pairs: dict, directory) -> str:
            monkeypatch.setattr(contractors, "_pairs",
                                lambda c, d, ref, *, ids=(): pairs)
            said = io.StringIO()
            with redirect_stdout(said):
                contractors.approve(conn, directory, run_ref)
            return said.getvalue()

        # v1: the schema as it shipped before this change -- the same candidate with
        # `key_warning` taken out of its fields and its rows, so its hash is v1's.
        def without_the_column(english, arabic, **kwargs):
            whole = extract.bilingual_listing_candidate(english, arabic, **kwargs)
            return dataclasses.replace(
                whole,
                fields=tuple(f for f in whole.fields if f.field_key != "key_warning"),
                rows=tuple({k: v for k, v in r.items() if k != "key_warning"}
                           for r in whole.rows))
        oman = directories.get("oman_tenderboard")
        first = approve("run-old", page_pair("run-old", 1, _pairable_en(), AR),
                        dataclasses.replace(oman, candidate=without_the_column))
        assert "approved 1 page(s)" in first, first

        second = approve("run-new", page_pair(
            "run-new", 2, _disagreeing(_pairable_en()), AR), oman)
        assert "approved 1 page(s)" in second, second

        versions = conn.execute(
            "SELECT v.version_number, v.status, v.schema_version_id "
            "  FROM dataset_schema_version AS v JOIN dataset_definition AS d "
            "    ON d.dataset_definition_id = v.dataset_definition_id "
            " WHERE d.dataset_key = ? ORDER BY v.version_number",
            (DATASET_KEY,)).fetchall()
        assert [(n, s) for n, s, _ in versions] == [(1, "retired"), (2, "approved")]
        current = versions[-1][2]
        stored = conn.execute(
            "SELECT r.schema_version_id, r.data_json, "
            "       (SELECT COUNT(*) FROM generic_record_revision AS v "
            "         WHERE v.generic_record_id = r.generic_record_id) "
            "  FROM generic_record AS r JOIN dataset_definition AS d "
            "    ON d.dataset_definition_id = r.dataset_definition_id "
            " WHERE d.dataset_key = ?", (DATASET_KEY,)).fetchall()
    finally:
        conn.close()

    assert len(stored) == len(_candidate().rows), "no firm may be lost or doubled"
    assert {version for version, _, _ in stored} == {current}, "a row stayed on v1"
    assert all(revisions == 2 for _, _, revisions in stored), stored
    warnings = {json.loads(blob)["short_name"]: json.loads(blob).get("key_warning")
                for _, blob, _ in stored}
    assert warnings.pop("00169963"), "the disagreeing row lost its warning"
    assert not any(warnings.values()), warnings
