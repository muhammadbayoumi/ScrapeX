"""Spec 21: the Workspace tabs. Each renders real data and keeps the dataset in view."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.jobs import create_job, run_job_once  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402

SOURCE = "ELSEWEDYSHOP"
TABS = ["/changes", "/history", "/review", "/jobs", "/schedules", "/logs",
        "/exports", "/sync"]


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "harvest.db"
    conn = dbmod.connect(p)
    dbmod.migrate(conn)
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="100.00")])])
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="130.00")],
                                               scraped_at="2026-07-20T10:00:00Z")])
    conn.commit()
    conn.close()
    return p


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


# ---- every tab renders -------------------------------------------------------

@pytest.mark.parametrize("path", TABS)
def test_every_tab_renders(client, path):
    r = client.get(path)
    assert r.status_code == 200 and 'class="wstabs"' in r.text


@pytest.mark.parametrize("path", TABS + ["/", f"/source/{SOURCE}", "/manage"])
def test_no_arabic_leaks_into_the_interface(client, path):
    """Spec 1: the interface is English only.

    Arabic is legitimate as DATA — most sources in the manifest genuinely have
    Arabic display names — so those exact values are stripped before checking.
    Anything Arabic left over is interface text, which is a violation.
    """
    import re

    from scrapex.config import load_manifest

    body = client.get(path).text
    # Longest first: "السويد" is a PREFIX of "السويدي شوب", so replacing the short
    # one first would leave a fragment behind and fail for the wrong reason.
    names = sorted((e.source_name for e in load_manifest(MANIFEST_FILE).sources),
                   key=len, reverse=True)
    for name in names:
        body = body.replace(name, "")
    leaked = re.findall(r"[؀-ۿ]+", body)
    assert not leaked, f"Arabic interface text leaked into {path}: {leaked[:3]}"


def test_active_tab_is_marked_for_assistive_tech(client):
    assert 'aria-current="page"' in client.get("/jobs").text


def test_dataset_context_survives_tab_switches(client):
    """Spec 21: opening a tab from a dataset must not lose which dataset it was."""
    body = client.get(f"/source/{SOURCE}").text
    assert f"/changes?source_key={SOURCE}" in body
    assert f"/history?source_key={SOURCE}" in body


# ---- content, not just status codes -----------------------------------------

def test_changes_tab_shows_the_movement_and_its_percentage(client):
    body = client.get("/changes", params={"source_key": SOURCE}).text
    assert "price increase" in body                 # the change type
    assert "100.0" in body and "130.0" in body      # previous and new value
    assert "+30.00" in body and "+30.0%" in body    # absolute AND percentage


def test_changes_tab_shows_first_current_min_max(client):
    body = client.get("/changes", params={"source_key": SOURCE}).text
    assert "Price history per offer" in body
    assert "First" in body and "Min" in body and "Max" in body


def test_history_tab_lists_runs_with_counts(client):
    body = client.get("/history").text
    assert "Rows seen" in body and "#1" in body     # two ingests -> at least run #1


def test_jobs_and_logs_tabs_show_a_real_job(client, db_path):
    from tests.test_jobs import _FakeManifest, _capture_ok

    conn = dbmod.connect(db_path)
    try:
        ref = create_job(conn, [SOURCE])
        run_job_once(conn, ref, _FakeManifest([SOURCE]), capture=_capture_ok([]))
    finally:
        conn.close()

    jobs = client.get("/jobs").text
    assert ref in jobs and "completed" in jobs
    logs = client.get("/logs", params={"job_ref": ref}).text
    assert "job started" in logs


def test_schedules_tab_states_the_limitation_plainly(client):
    body = client.get("/schedules").text
    assert "sleeping or powered-off" in body


def test_review_tab_says_nothing_auto_approves(client):
    body = client.get("/review").text
    assert "No confidence level ever approves" in body


def test_export_and_sync_tabs_are_real_controls_now(client):
    """Spec 21-23: both tabs run their destination instead of documenting a command."""
    assert "Export to Excel" in client.get("/exports").text
    sync = client.get("/sync").text
    assert "Send a test row" in sync and "Push to Drive" in sync


def test_the_sync_tab_still_admits_what_the_transport_does_not_do(client):
    """Having built the screen does not license implying more than it does:
    request signing and adaptive batching remain unbuilt and are named as such."""
    assert "NOT implemented" in client.get("/sync").text


def test_empty_states_are_designed_not_blank(client, tmp_path):
    """A fresh warehouse must explain itself rather than render an empty table."""
    empty = tmp_path / "empty.db"
    conn = dbmod.connect(empty)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    manifest = tmp_path / "m.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    fresh = TestClient(create_app(empty, manifest_path=manifest))
    assert "No crawls recorded yet" in fresh.get("/history").text
    assert "Nothing awaiting review" in fresh.get("/review").text
    assert "No jobs yet" in fresh.get("/jobs").text
    assert "No schedules yet" in fresh.get("/schedules").text


# ---- sorting (spec 16) -------------------------------------------------------

def test_sort_links_are_offered_for_the_sortable_columns(client):
    body = client.get(f"/source/{SOURCE}").text
    for key in ("name", "region", "effective_price", "business_date"):
        assert f"sort={key}" in body


def test_sorting_changes_the_order_and_is_reversible(client, db_path):
    from scrapex.reports import browse_observations

    conn = dbmod.connect(db_path)
    try:
        entry = make_entry()
        for i, price in enumerate(["5.00", "90.00", "40.00"]):
            ingest_payloads(conn, entry, [make_payload(
                [one_row(external_product_id=f"p{i}", external_variant_id=f"v{i}",
                         product_name=f"Item {i}", effective_price=price)])])
        asc = [r["effective_price"] for r in browse_observations(
            conn, SOURCE, sort="effective_price", direction="asc").rows]
        desc = [r["effective_price"] for r in browse_observations(
            conn, SOURCE, sort="effective_price", direction="desc").rows]
    finally:
        conn.close()
    assert asc == sorted(asc) and desc == sorted(desc, reverse=True)


def test_an_unknown_sort_key_falls_back_instead_of_reaching_sql(client, db_path):
    """The sort key is an ALLOW-LIST lookup, so a crafted value can never become
    SQL — it silently falls back to the default ordering."""
    from scrapex.reports import browse_observations

    conn = dbmod.connect(db_path)
    try:
        crafted = browse_observations(conn, SOURCE, sort="po.effective_price; DROP TABLE x--")
        default = browse_observations(conn, SOURCE)
    finally:
        conn.close()
    assert [r["name"] for r in crafted.rows] == [r["name"] for r in default.rows]
    assert crafted.total == default.total


def test_the_active_sort_is_announced_to_assistive_tech(client):
    """The arrow alone is not enough: the sorted column carries aria-sort so the
    state is not conveyed by a glyph only."""
    body = client.get(f"/source/{SOURCE}",
                      params={"sort": "effective_price", "direction": "desc"}).text
    assert 'aria-sort="descending"' in body
    # ...and clicking the same header again flips back to ascending.
    assert "sort=effective_price&direction=asc" in body


# ---- manage columns + saved views (spec 22) ---------------------------------

def test_manage_columns_panel_lists_every_field(client):
    body = client.get(f"/source/{SOURCE}").text
    assert "Manage columns and views" in body
    assert "effective_price" in body and "Original" in body


def test_panel_states_that_hiding_is_not_deleting(client):
    body = client.get(f"/source/{SOURCE}").text
    assert "keeps receiving every future update" in body
    assert "Nothing here deletes anything" in body


def test_both_export_schemas_are_offered(client):
    body = client.get(f"/source/{SOURCE}").text
    assert "--schema original" in body and "--schema current" in body


def test_hiding_a_column_through_the_api_is_reflected_on_the_page(client):
    client.get(f"/source/{SOURCE}")                     # registers the fields
    r = client.post(f"/api/fields/{SOURCE}", json={"field_key": "currency", "hidden": True})
    assert r.status_code == 200
    body = client.get(f"/source/{SOURCE}").text
    assert "Hidden" in body                              # the word, not a colour
    # ...and the field is still listed, because hiding is a view operation.
    assert "currency" in body
