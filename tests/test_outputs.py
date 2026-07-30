"""Spec 21-23: Excel, the Apps Script funnel, and Google Drive as real surfaces.

Every destination is exercised through injected sinks/clients, so these tests
need no network, no credentials and no Google libraries — the same seams the
interface uses.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex import outputs, settings
from scrapex.config import MANIFEST_FILE
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row

SOURCE = "ELSEWEDYSHOP"

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex.webui.app import create_app  # noqa: E402


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(c)
    ingest_payloads(c, make_entry(), [make_payload([one_row()])])
    c.commit()
    try:
        yield c
    finally:
        c.close()


@pytest.fixture()
def db_path(tmp_path):
    p = tmp_path / "api.db"
    c = dbmod.connect(p)
    dbmod.migrate(c)
    ingest_payloads(c, make_entry(), [make_payload([one_row()])])
    c.commit()
    c.close()
    return p


@pytest.fixture()
def client(db_path, tmp_path):
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


class FakeSink:
    """A SheetSink that records what it was asked to write."""

    def __init__(self):
        self.tabs = {}
        self.handles = []

    def ensure_workbook(self, folder, workbook):
        handle = f"{folder}/{workbook}"
        self.handles.append(handle)
        return handle

    def write_tab(self, handle, tab, header, rows):
        self.tabs[tab] = (header, rows)

    def location(self, handle):
        return str(handle)


class FakeFunnel:
    """A FunnelClient stand-in: captures the payload, never sends anything."""

    def __init__(self, fail: Exception | None = None):
        self.sent = []
        self.fail = fail

    def send(self, payload):
        if self.fail:
            raise self.fail
        self.sent.append(payload)
        return 1


# ---- settings ----------------------------------------------------------------

def test_a_saved_setting_beats_the_environment(conn, monkeypatch):
    """The environment keeps a headless machine working, but the moment the owner
    saves a value in the interface it must be the one that is used."""
    monkeypatch.setenv("SCRAPEX_FUNNEL_URL", "https://from-env.example/exec")
    assert settings.resolve(conn, "funnel_url") == ("https://from-env.example/exec",
                                                    settings.FROM_ENV)
    settings.save(conn, {"funnel_url": "https://saved.example/exec"})
    assert settings.resolve(conn, "funnel_url") == ("https://saved.example/exec",
                                                    settings.FROM_SAVED)


def test_clearing_a_setting_falls_back_instead_of_leaving_a_hole(conn, monkeypatch):
    monkeypatch.setenv("SCRAPEX_FUNNEL_URL", "https://from-env.example/exec")
    settings.save(conn, {"funnel_url": "https://saved.example/exec"})
    settings.save(conn, {"funnel_url": ""})
    assert settings.resolve(conn, "funnel_url")[1] == settings.FROM_ENV


def test_a_secret_is_never_returned_for_display(conn):
    settings.save(conn, {"funnel_token": "supersecrettoken1234"})
    public = settings.public_settings(conn)["funnel_token"]
    assert public["value"] == "" and public["is_set"] is True
    assert public["hint"] == "...1234"
    assert "supersecrettoken" not in str(public)


def test_an_unknown_setting_is_refused_not_stored(conn):
    with pytest.raises(settings.UnknownSettingError):
        settings.save(conn, {"rm_rf": "yes"})


def test_settings_survive_a_reconnect(conn, tmp_path):
    settings.save(conn, {"excel_workbook": "Prices 2026"})
    conn.commit()
    again = dbmod.connect(tmp_path / "harvest.db")
    try:
        assert settings.get(again, "excel_workbook") == "Prices 2026"
    finally:
        again.close()


# ---- Excel (spec 21) ---------------------------------------------------------

def test_excel_status_states_structure_and_update_behaviour(conn):
    status = outputs.excel_status(conn)
    assert "one tab per source" in status["structure"].lower()
    assert "REPLACES" in status["update_behaviour"]
    assert status["path"].endswith(".xlsx")


def test_excel_export_writes_one_tab_per_source(conn):
    sink = FakeSink()
    result = outputs.excel_export(conn, [SOURCE], sink=sink)
    assert result.ok and result.rows == 1
    # The prices tab, plus the history and about tabs publish_source now writes
    # beside it (details is skipped — this fixture has no attributes). The
    # about tab is never skipped: a workbook is read long after the screen it
    # came from is closed, and a price with no source, date, currency policy or
    # tax statement is a number rather than a fact.
    assert list(sink.tabs) == [SOURCE, f"{SOURCE} — history", f"{SOURCE} — about"]
    header, rows = sink.tabs[SOURCE]
    assert "country" in header and len(rows) == 1


def test_excel_export_records_what_happened_for_next_time(conn):
    outputs.excel_export(conn, [SOURCE], sink=FakeSink())
    last = outputs.excel_status(conn)["last"]
    assert last["ok"] is True and last["rows"] == 1 and last["at"]


def test_a_source_with_no_data_is_reported_not_silently_skipped(conn):
    result = outputs.excel_export(conn, [SOURCE, "NOTHING_HERE"], sink=FakeSink())
    assert "Skipped" in result.detail and "NOTHING_HERE" in result.detail
    assert result.rows == 1                      # the good source still went out


def test_exporting_nothing_is_refused_rather_than_reported_as_success(conn):
    with pytest.raises(outputs.NotConfiguredError):
        outputs.excel_export(conn, [], sink=FakeSink())


def test_the_saved_folder_is_used_over_the_default(conn, tmp_path):
    settings.save(conn, {"excel_folder": str(tmp_path / "books")})
    assert outputs.excel_status(conn)["folder"] == str(tmp_path / "books")


# ---- Apps Script funnel (spec 22) -------------------------------------------

def test_funnel_is_not_ready_until_both_url_and_token_exist(conn, monkeypatch):
    monkeypatch.delenv("SCRAPEX_FUNNEL_URL", raising=False)
    monkeypatch.delenv("SCRAPEX_FUNNEL_TOKEN", raising=False)
    assert outputs.apps_script_status(conn)["ready"] is False
    settings.save(conn, {"funnel_url": "https://x.example/exec"})
    status = outputs.apps_script_status(conn)
    assert status["ready"] is False and "token" in status["blocker"]
    settings.save(conn, {"funnel_token": "t0ken"})
    assert outputs.apps_script_status(conn)["ready"] is True


def test_the_funnel_page_states_what_the_transport_actually_does(conn):
    """This test used to assert the words "NOT implemented", because signing and
    adaptive batching were in the product spec and missing from the transport.
    A9 built both, so keeping that assertion would make the suite defend a claim
    that is no longer true — the screen owes the owner the same honesty in the
    other direction. What it must still never do is overstate: the softness that
    keeps an un-repasted script working has to be on the page too.
    """
    limits = outputs.apps_script_status(conn)["limits"]
    assert "HMAC-SHA256" in limits
    assert "FUNNEL_REQUIRE_SIGNATURE" in limits, \
        "the page must say that an UNSIGNED request is still accepted until the owner says otherwise"
    assert "NOT replay protection" in limits, \
        "a signature is integrity only; the page must not let it read as more than that"
    assert "halves" in limits and "one row per chunk" in limits


def test_rotating_the_token_returns_it_once_and_then_only_a_hint(conn):
    token = outputs.rotate_funnel_token(conn)
    assert len(token) > 20
    status = outputs.apps_script_status(conn)
    assert status["token_is_set"] and status["token_hint"] == f"...{token[-4:]}"
    assert token not in str(status)


def test_a_funnel_send_leaves_only_canonical_strings_on_the_wire(conn):
    """The cross-engine contract: a cell crosses the boundary as a canonical
    string. A Python float would render as 15.0 where the other engine writes 15
    and quietly fork the record hash."""
    client = FakeFunnel()
    outputs.apps_script_send(conn, SOURCE, client=client)
    rows = client.sent[0].rows
    assert all(isinstance(cell, str) for row in rows for cell in row)
    assert "1200" in rows[0] and "1200.0" not in rows[0]


def test_a_refused_delivery_is_reported_and_the_batch_is_not_lost(conn):
    from scrapex.funnel import FunnelDeliveryError

    result = outputs.apps_script_send(
        conn, SOURCE, client=FakeFunnel(fail=FunnelDeliveryError("bad token")))
    assert result.ok is False
    assert "outbox" in result.detail and "bad token" in result.detail


def test_an_oversized_batch_is_delivered_with_the_sheet_cap_named(conn, monkeypatch):
    """This test used to assert that an oversized batch was REFUSED before
    sending. That refusal existed because the transport could not survive a
    batch Apps Script choked on; now it halves the chunk and retries (A9), so
    refusing up front would be turning down work that would have gone through.
    The one limit that is still real past this size belongs to the sheet, not to
    the transport, and the run result has to say which is which."""
    monkeypatch.setattr(outputs, "FUNNEL_MAX_ROWS", 0)
    client = FakeFunnel()
    result = outputs.apps_script_send(conn, SOURCE, client=client)
    # More than one payload now: prices, then whichever of details, history and
    # provenance this source actually has. This asserted exactly one because the
    # funnel used to send the price table alone; what it was really testing —
    # that an oversized batch is SENT rather than refused up front — is proven
    # by the first payload existing at all.
    assert client.sent, "the batch was refused instead of sent"
    assert client.sent[0].source_url.endswith(SOURCE), "the prices go first"
    assert "SYNC_MAX_ROWS" in result.detail and "_INBOX" in result.detail


def test_sending_a_source_with_no_data_is_refused_with_the_next_step(conn):
    with pytest.raises(outputs.NotConfiguredError, match="crawl and ingest"):
        outputs.apps_script_send(conn, "NOTHING_HERE", client=FakeFunnel())


def test_the_script_to_paste_is_available_to_copy():
    assert "function" in outputs.apps_script_script_text()


def test_the_script_to_paste_verifies_signatures_without_locking_anyone_out():
    """The half of A9 that lives on the sheet. Both halves are load-bearing:
    the verifier (or signing is decoration), and the fact that it only demands a
    signature once FUNNEL_REQUIRE_SIGNATURE is set (or an owner who pastes this
    script while running any older producer gets an unexplained 'unauthorized'
    and no way to see why)."""
    script = outputs.apps_script_script_text()
    assert "computeHmacSha256Signature" in script and "canonicalJson_" in script
    assert "FUNNEL_REQUIRE_SIGNATURE" in script
    assert "constantTimeEquals_" in script


# ---- Google (spec 23) --------------------------------------------------------

def test_google_status_explains_each_missing_step_in_order(conn, monkeypatch, tmp_path):
    # Without the extra, google_status stops at "needs the extra" and never
    # reaches the steps under test. Skipping says that; failing blamed the code.
    # The [google] client libraries are too heavy to pull into [dev] for one test.
    pytest.importorskip("google_auth_oauthlib")
    monkeypatch.setattr("scrapex.gdrive.CLIENT_SECRET_PATH", tmp_path / "client_secret.json")
    monkeypatch.setattr("scrapex.gdrive.TOKEN_PATH", tmp_path / "token.json")
    assert "Missing" in outputs.google_status(conn)["blocker"]

    (tmp_path / "client_secret.json").write_text("{}", encoding="utf-8")
    assert "Continue with Google" in outputs.google_status(conn)["blocker"]

    (tmp_path / "token.json").write_text("{}", encoding="utf-8")
    status = outputs.google_status(conn)
    assert status["connected"] is True
    # Ready only if the client libraries are installed too — the optional extra
    # is a separate blocker from being signed in, and both must clear.
    import importlib.util
    assert status["ready"] is (importlib.util.find_spec("googleapiclient") is not None)


def test_the_account_line_is_honest_about_least_privilege(conn):
    """Spec 23 asks for the signed-in account; the scopes deliberately exclude
    identity, so the interface says why instead of inventing a value."""
    status = outputs.google_status(conn)
    assert status["account"] == ""
    assert "not requested" in status["account_note"]


def test_disconnect_removes_only_the_local_sign_in(conn, monkeypatch, tmp_path):
    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("scrapex.gdrive.TOKEN_PATH", token)
    assert outputs.google_disconnect(conn) is True
    assert not token.exists()
    assert "left exactly as they are" in settings.get_state(conn, "google_last")["detail"]


def test_google_push_writes_the_same_table_as_excel(conn):
    """One publish path, two sinks: the arrangement must not drift apart."""
    excel_sink, drive_sink = FakeSink(), FakeSink()
    outputs.excel_export(conn, [SOURCE], sink=excel_sink)
    outputs.google_push(conn, [SOURCE], sink=drive_sink)
    assert excel_sink.tabs[SOURCE] == drive_sink.tabs[SOURCE]


# ---- the HTTP surface --------------------------------------------------------

def test_every_destination_reports_readiness_with_a_reason(client):
    outs = client.get("/api/outputs").json()["outputs"]
    keys = [o["key"] for o in outs]
    assert keys[0] == "local_db" and outs[0]["required"] is True
    for out in outs[1:]:
        assert out["ready"] or out["blocker"], f"{out['key']} is not ready and says nothing"


def test_the_local_database_is_never_offered_as_optional(client):
    local = client.get("/api/outputs").json()["outputs"][0]
    assert local["required"] is True and "cannot be disabled" in local["detail"]


def test_settings_round_trip_through_the_api(client):
    r = client.post("/api/settings", json={"excel_workbook": "Prices"})
    assert r.status_code == 200 and "excel_workbook" in r.json()["changed"]
    assert client.get("/api/settings").json()["settings"]["excel_workbook"]["value"] == "Prices"


def test_the_api_refuses_an_unknown_setting(client):
    assert client.post("/api/settings", json={"nope": "1"}).status_code == 400


def test_the_api_never_returns_a_stored_token(client):
    client.post("/api/settings", json={"funnel_token": "abcd1234efgh"})
    body = client.get("/api/settings").text
    assert "abcd1234efgh" not in body
    assert "...efgh" in body


def test_an_export_with_no_selection_is_a_400_not_an_empty_success(client):
    assert client.post("/api/outputs/excel/export", json={}).status_code == 400


def test_an_unconfigured_funnel_refuses_with_the_missing_piece(client, monkeypatch):
    monkeypatch.delenv("SCRAPEX_FUNNEL_URL", raising=False)
    monkeypatch.delenv("SCRAPEX_FUNNEL_TOKEN", raising=False)
    r = client.post("/api/outputs/apps-script/test")
    assert r.status_code == 400 and "Missing" in r.json()["detail"]


def test_the_pages_render_the_real_state(client):
    excel = client.get("/exports").text
    assert "Export to Excel" in excel and "one tab per source" in excel.lower()
    sync = client.get("/sync").text
    assert "Copy script" in sync and "Continue with Google" in sync


def test_the_sync_page_states_the_disconnect_consequence(client, monkeypatch, tmp_path):
    """Disconnect must never read as if it could delete the owner's Drive files.

    TOKEN_PATH is redirected first: without it this test would delete the real
    sign-in of whoever runs the suite — a test that damages the machine it runs
    on is a worse defect than the one it checks for.
    """
    monkeypatch.setattr("scrapex.gdrive.TOKEN_PATH", tmp_path / "token.json")
    assert "Nothing in Drive was changed" in \
        client.post("/api/outputs/google/disconnect").json()["detail"]


# ---- spec 19: the two workbook choices, which were absent entirely ----------

def test_the_default_arrangement_is_one_workbook_with_a_tab_per_source(conn):
    status = outputs.excel_status(conn)
    assert status["structure_key"] == "combined" and status["update_key"] == "replace"
    assert "one tab per source" in status["structure"].lower()
    assert "REPLACES" in status["update_behaviour"]


def test_per_site_writes_one_workbook_per_source(conn):
    settings.save(conn, {"excel_structure": "per_site"})
    sink = FakeSink()
    outputs.excel_export(conn, [SOURCE], sink=sink)
    assert SOURCE in sink.handles[0], \
        "a per-site workbook is named after the source, not the shared name"


def test_the_snapshot_behaviour_keeps_the_previous_export_instead_of_replacing_it(conn):
    """Spec 19's second update behaviour. With `replace`, exporting twice writes
    one tab twice; with `snapshot`, each export keeps its own dated tab."""
    settings.save(conn, {"excel_update": "snapshot"})
    sink = FakeSink()
    outputs.excel_export(conn, [SOURCE], sink=sink)
    tabs = list(sink.tabs)
    # The dated prices tab, and the history and about tabs that now ride beside
    # it — a snapshot keeps the WHOLE picture of that run, not a third of it.
    prices = [t for t in tabs
              if not any(k in t for k in ("history", "details", "about"))]
    assert len(prices) == 1 and prices[0].startswith(SOURCE) and prices[0] != SOURCE, \
        "a snapshot tab carries its date"
    assert all(t.startswith(SOURCE) for t in tabs)


def test_the_status_describes_the_arrangement_actually_configured(conn):
    settings.save(conn, {"excel_structure": "per_site", "excel_update": "snapshot"})
    status = outputs.excel_status(conn)
    assert "one workbook per source" in status["structure"].lower()
    assert "NEW dated tab" in status["update_behaviour"]
    assert "grows with every run" in status["update_behaviour"], \
        "the cost of keeping every snapshot must be stated, not discovered"


def test_the_sheets_own_answer_reaches_the_sync_ui(conn):
    """Delivery is half the story: the sheet-side assembler's answer now rides
    back into the run result, so 'delivered' can no longer mask a stale tab."""
    class _Confirming(FakeFunnel):
        def call_action(self, action, **fields):
            assert action == "staging_sync"
            return {"ok": True, "report": {"written": [{"source": SOURCE, "rows": 1}],
                                           "skipped": []}}

    result = outputs.apps_script_send(conn, SOURCE, client=_Confirming())
    assert result.ok is True
    assert "wrote 1 row(s)" in result.detail


def test_a_column_that_appeared_in_the_sheet_is_named_in_the_run_result(conn):
    """A new column now reaches the sheet without anyone pasting a new script —
    that is the whole point of the two version numbers. Which is exactly why its
    arrival has to be SAID somewhere the owner already looks: a column that
    turns up unannounced is one read six months later as though it had been
    checked. The sheet records it in _RUNS; this is the same news in the UI."""
    class _Widening(FakeFunnel):
        def call_action(self, action, **fields):
            return {"ok": True, "report": {"written": [
                {"source": SOURCE, "rows": 1,
                 "columns_added": ["quantity_is_decimal"], "columns_removed": []}],
                "skipped": []}}

    result = outputs.apps_script_send(conn, SOURCE, client=_Widening())
    assert result.ok is True, "a new column is not a failure — it is news"
    assert "Columns changed" in result.detail
    assert "new quantity_is_decimal" in result.detail


def test_a_column_that_vanished_from_the_sheet_is_named_too(conn):
    """The rename's second line of defence. If one ever slips through without
    the generation moving, the sheet keeps the old column beside the new one and
    nothing errors — so the disappearance itself has to be reported."""
    class _Narrowing(FakeFunnel):
        def call_action(self, action, **fields):
            return {"ok": True, "report": {"written": [
                {"source": SOURCE, "rows": 1,
                 "columns_added": ["brand"], "columns_removed": ["brand_raw"]}],
                "skipped": []}}

    result = outputs.apps_script_send(conn, SOURCE, client=_Narrowing())
    assert "new brand" in result.detail and "gone brand_raw" in result.detail


def test_an_older_script_that_reports_no_columns_says_nothing_about_them(conn):
    """A sheet running the previous script answers without the two new keys.
    That is not "no columns changed" and must not be narrated as anything."""
    class _Quiet(FakeFunnel):
        def call_action(self, action, **fields):
            return {"ok": True, "report": {"written": [{"source": SOURCE, "rows": 1}],
                                           "skipped": []}}

    result = outputs.apps_script_send(conn, SOURCE, client=_Quiet())
    assert result.ok is True
    assert "Columns changed" not in result.detail


def test_a_sheet_refusal_is_a_failure_with_the_reason_verbatim(conn):
    class _Refusing(FakeFunnel):
        def call_action(self, action, **fields):
            return {"ok": True, "report": {"written": [], "skipped": [
                {"source": SOURCE, "reason": "row 7 has 22 cells, header has 23"}]}}

    result = outputs.apps_script_send(conn, SOURCE, client=_Refusing())
    assert result.ok is False
    assert "REFUSED" in result.detail and "row 7 has 22 cells" in result.detail


def test_an_older_script_degrades_to_an_honest_not_confirmed(conn):
    result = outputs.apps_script_send(conn, SOURCE, client=FakeFunnel())
    assert result.ok is True
    assert "did not confirm" in result.detail and "Copy Script" in result.detail


def test_a_refused_details_tab_is_named_and_fails_the_run(conn):
    """The sheet files the details under 'ELSEWEDYSHOP — details'
    (tableSuffix_ in the pasted script), never under the bare source_key. The
    old matching compared the bare key alone, so this exact reply — prices
    written, details refused — recorded ok=True and mentioned the refusal
    nowhere: a silent failure, the class of defect the owner has twice lost
    hours to."""
    class _RefusingDetails(FakeFunnel):
        def call_action(self, action, **fields):
            return {"ok": True, "report": {
                "written": [{"source": SOURCE, "rows": 1}],
                "skipped": [{"source": f"{SOURCE} — details",
                             "reason": "row 3 has 4 cells, header has 5"}]}}

    result = outputs.apps_script_send(conn, SOURCE, client=_RefusingDetails())
    assert result.ok is False, "one refused tab must fail the whole run"
    assert f"{SOURCE} — details" in result.detail, \
        "the detail must name WHICH tab the sheet refused"
    assert "row 3 has 4 cells" in result.detail, "the sheet's reason travels verbatim"
    last = outputs.apps_script_status(conn)["last"]
    assert last["ok"] is False, "the recorded state must carry the failure too"


def test_a_report_covering_all_four_tabs_reports_all_four(conn):
    """When the sheet confirms the whole family, the run result says so tab by
    tab — the owner reads ONE line and knows the spreadsheet is whole."""
    class _AllFour(FakeFunnel):
        def call_action(self, action, **fields):
            return {"ok": True, "report": {"written": [
                {"source": SOURCE, "rows": 1},
                {"source": f"{SOURCE} — details", "rows": 2},
                {"source": f"{SOURCE} — history", "rows": 3},
                {"source": f"{SOURCE} — about", "rows": 9},
            ], "skipped": []}}

    result = outputs.apps_script_send(conn, SOURCE, client=_AllFour())
    assert result.ok is True
    for tab in (SOURCE, f"{SOURCE} — details",
                f"{SOURCE} — history", f"{SOURCE} — about"):
        assert tab in result.detail, f"{tab} must be accounted for by name"
    assert "1 row(s)" in result.detail and "3 row(s)" in result.detail, \
        "each tab reports its own row count, not one shared number"


def test_a_companion_refusal_can_no_longer_vanish_from_the_report(conn):
    """Regression pin for the old behaviour itself: a skipped entry for any
    suffixed family tab matched neither `written` nor `refused`, so the run
    fell through to the ok=True 'did not confirm' fallback. Whatever the
    wording becomes, the invariant is that every refused family tab is NAMED
    with its reason and the run is a failure — never the fallback."""
    refusals = [{"source": f"{SOURCE} — history", "reason": "no complete batch"},
                {"source": f"{SOURCE} — about", "reason": "batch carries no header"}]

    class _RefusingTwo(FakeFunnel):
        def call_action(self, action, **fields):
            return {"ok": True, "report": {"written": [{"source": SOURCE, "rows": 1}],
                                           "skipped": list(refusals)}}

    result = outputs.apps_script_send(conn, SOURCE, client=_RefusingTwo())
    assert result.ok is False
    for entry in refusals:
        assert entry["source"] in result.detail
        assert entry["reason"] in result.detail
    assert "did not confirm" not in result.detail, \
        "a refusal must never be presented as the benign not-confirmed case"


def test_the_engine_and_the_sheet_agree_on_the_tab_suffixes():
    """FUNNEL_TABLE_SUFFIXES is how outputs.py knows which tab names the
    sheet's sync report can answer in; SYNC_TABLE_SUFFIXES is how the sheet
    builds them. Let them drift and a refusal of the missing suffix turns
    invisible again — the exact defect this family of tests exists to keep
    dead."""
    script = (Path(__file__).resolve().parent.parent / "apps_script" /
              "StagingAppScript.txt").read_text(encoding="utf-8")
    expected = "[" + ", ".join(f'"{s}"' for s in outputs.FUNNEL_TABLE_SUFFIXES) + "]"
    assert f"SYNC_TABLE_SUFFIXES = {expected}" in script


def test_the_funnel_sends_every_table_the_workbook_has(conn):
    """The owner's ruling: Apps Script sends every piece of information
    collected.

    It sent the price table alone while the local workbook and the Google push
    both carried the details and the history — the same data, three
    destinations, two answers. All four tables now go, each announcing WHICH
    table it is in its own source_url, which the frozen payload already carries
    and which means exactly "where this came from"."""
    client = FakeFunnel()
    outputs.apps_script_send(conn, SOURCE, client=client)

    urls = [payload.source_url for payload in client.sent]
    assert urls[0] == f"scrapex://export/{SOURCE}", "prices lead, with no suffix"
    assert any(url.endswith("/history") for url in urls), "the price history never left"
    assert any(url.endswith("/about") for url in urls), "nothing said where the numbers came from"
    # Every batch carries the same source_key: these are four views of ONE
    # source, not four sources, and the sheet must file them together.
    assert {payload.source_key for payload in client.sent} == {SOURCE}


def test_the_sheet_names_a_tab_from_the_table_it_was_sent(conn):
    """The sheet script reads that suffix and writes SOURCE — details beside
    SOURCE. Pinned here because the two engines have to agree on it and only
    one of them is Python."""
    script = (Path(__file__).resolve().parent.parent / "apps_script" /
              "StagingAppScript.txt").read_text(encoding="utf-8")

    assert "function tableSuffix_" in script
    assert 'SYNC_TABLE_SUFFIXES = ["details", "history", "about"]' in script
    assert "tableSuffix_(payload.source_url)" in script


def test_the_sheet_and_the_engine_speak_the_same_payload_version():
    """The script declares BOTH numbers, so both live in two languages and only
    one of them is Python.

    Let the GENERATION drift and nothing looks wrong: handleChunk has no version
    gate, so every chunk is accepted and acked ok, the throw fires later inside
    reassemble_, rebuildTables_ files the batch under "skipped", and the
    published tab keeps republishing the last complete batch. The sheet stays
    alive, opens fine, and is frozen.

    Letting the CONTENT number drift is now harmless by design — the script
    reports it and refuses nothing on it — but it is still what a human reads to
    know which build a sheet was pasted from, so it is still pinned. The
    generation, the ledger and the gate's shape are pinned in
    tests/test_payload_compat.py."""
    from scrapex.payload import PAYLOAD_COMPAT_VERSION, PAYLOAD_VERSION

    script = (Path(__file__).resolve().parent.parent / "apps_script" /
              "StagingAppScript.txt").read_text(encoding="utf-8")

    assert f"const SYNC_PAYLOAD_VERSION = {PAYLOAD_VERSION};" in script, (
        f"the engine speaks payload version {PAYLOAD_VERSION}; "
        "apps_script/StagingAppScript.txt must declare the same number"
    )
    assert f"const SYNC_PAYLOAD_COMPAT_VERSION = {PAYLOAD_COMPAT_VERSION};" in script, (
        f"the engine speaks meaning generation {PAYLOAD_COMPAT_VERSION}; a sheet "
        "declaring a different one refuses every batch this engine sends"
    )
