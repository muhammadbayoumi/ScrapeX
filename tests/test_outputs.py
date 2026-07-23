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
    # The prices tab, plus the history tab publish_source now writes
    # beside it (details is skipped — this fixture has no attributes).
    assert list(sink.tabs) == [SOURCE, f"{SOURCE} — history"]
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


def test_the_funnel_page_admits_what_the_transport_does_not_do(conn):
    """Signing and adaptive batching are in the product spec and not built. The
    status says so, so no screen can imply a guarantee that does not exist."""
    assert "NOT implemented" in outputs.apps_script_status(conn)["limits"]


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


def test_an_oversized_batch_is_refused_before_sending(conn, monkeypatch):
    monkeypatch.setattr(outputs, "FUNNEL_MAX_ROWS", 0)
    with pytest.raises(outputs.NotConfiguredError, match="row batch limit"):
        outputs.apps_script_send(conn, SOURCE, client=FakeFunnel())


def test_sending_a_source_with_no_data_is_refused_with_the_next_step(conn):
    with pytest.raises(outputs.NotConfiguredError, match="crawl and ingest"):
        outputs.apps_script_send(conn, "NOTHING_HERE", client=FakeFunnel())


def test_the_script_to_paste_is_available_to_copy():
    assert "function" in outputs.apps_script_script_text()


# ---- Google (spec 23) --------------------------------------------------------

def test_google_status_explains_each_missing_step_in_order(conn, monkeypatch, tmp_path):
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
    # The dated prices tab, and the history tab that now rides beside it —
    # a snapshot keeps the WHOLE picture of that run, not a third of it.
    prices = [t for t in tabs if "history" not in t and "details" not in t]
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
