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
    # Schedules is an EDITOR now: an empty database still shows a row per
    # implemented source — creating a schedule is what the page is FOR — and
    # each unscheduled row says so.
    schedules_page = fresh.get("/schedules").text
    assert 'data-sched="' in schedules_page
    assert "no schedule yet" in schedules_page


# ---- sorting (spec 16) -------------------------------------------------------

def test_every_sortable_column_is_declared_to_the_grid(client):
    """Sorting moved into the grid's own header menu, so the assertion moves to
    the contract the grid is built from rather than a server-rendered link."""
    payload = client.get(f"/api/table/{SOURCE}").json()
    keys = {c["key"] for c in payload["columns"]}
    assert "product_name" in keys and "effective_price" in keys


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


def test_the_table_payload_is_bounded_and_says_when_it_truncates(client):
    """The grid filters in the browser, which the owner chose. That is only
    honest while the page states what it did NOT load — a prefix presented as
    the whole is the failure the bound exists to prevent."""
    from scrapex.reports import TABLE_ROW_CAP

    payload = client.get(f"/api/table/{SOURCE}").json()

    assert payload["returned"] <= TABLE_ROW_CAP
    assert payload["truncated"] is (payload["total"] > payload["returned"])


def test_the_column_controls_live_on_the_columns(client):
    """They used to sit in a collapsed <details> holding a second table of
    checkboxes. They are now a three-dot menu on each header, built by the grid,
    so the assertion is that the grid is wired — not that a <th> exists."""
    body = client.get(f"/source/{SOURCE}").text
    assert "/static/grid.js" in body
    assert 'id="grid"' in body and f'data-source="{SOURCE}"' in body


def test_workspace_tools_panel_is_removed_in_favour_of_the_grid_chooser(client):
    body = client.get(f"/source/{SOURCE}").text
    grid_script = client.get("/static/grid.js").text
    assert "Workspace tools" not in body
    assert 'class="data-controls"' not in body
    assert "Choose Columns" in grid_script


def test_a_hidden_column_can_be_restored_from_the_grid_column_chooser(client):
    client.get(f"/source/{SOURCE}")
    client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})

    fields = client.get(f"/api/fields/{SOURCE}").json()["fields"]
    hidden = next(field for field in fields if field["field_key"] == "sku")
    grid_script = client.get("/static/grid.js").text

    assert hidden["is_hidden"] is True
    assert "Show all columns" in grid_script
    assert '"/api/fields/"' in grid_script


def test_hiding_a_column_through_the_api_is_reflected_in_the_grid_payload(client):
    client.get(f"/source/{SOURCE}")                     # registers the fields
    r = client.post(f"/api/fields/{SOURCE}", json={"field_key": "sku", "hidden": True})
    assert r.status_code == 200
    payload = client.get(f"/api/table/{SOURCE}").json()
    assert "sku" not in {column["key"] for column in payload["columns"]}
    fields = client.get(f"/api/fields/{SOURCE}").json()["fields"]
    assert any(field["field_key"] == "sku" and field["is_hidden"] for field in fields)


def test_the_schedules_page_is_the_full_editor(client):
    """The owner's ruling, verbatim: editable, with everything. The page was a
    read-only table that said "set one from the side panel" — the opposite of
    the central control it is meant to be."""
    body = client.get("/schedules").text
    for role in ("freq", "weekday", "time", "tz", "mode", "missed",
                 "overlap", "enabled", "save"):
        assert f'data-role="{role}"' in body, f"the {role} control is missing"
    assert "/api/schedules/" in body, "no save path — still read-only"
    assert "Monday" in body                       # 0=Monday, server convention
    # The capability gate reaches this face too.
    assert "not published by this site" in body


def test_the_schedules_editor_uses_one_source_list_and_one_visible_panel(client):
    """A source is selected from one compact list while its complete editor is
    shown in a single detail panel; advanced policies remain folded initially."""
    body = client.get("/schedules").text

    assert 'id="schedule-search"' in body
    for state in ("all", "scheduled", "manual", "paused"):
        assert f'data-filter="{state}"' in body
    assert 'class="schedule-source-list"' in body
    assert 'data-source-choice=' in body and 'role="tab"' in body
    assert 'class="schedule-editor"' in body and 'role="tabpanel"' in body
    assert body.count('data-source-choice=') == body.count('role="tabpanel"')
    assert 'aria-selected="true"' in body and 'tabindex="-1"' in body
    assert "showSource" in body and '"ArrowDown"' in body
    assert 'class="schedule-advanced"' in body and "Run behavior" in body
    assert "Schedule summary" in body and "Showing ${shown}" in body
    assert "Frequency" in body and "Timezone" in body


def test_saved_views_are_reachable_from_the_page_again(client):
    """The merge that removed the old workspace-tools panel orphaned
    POST /api/views — a feature no user could reach. The Views popover is its
    restored caller: save from the page, see it listed, open it."""
    page = client.get(f"/source/{SOURCE}").text
    assert "Saved views" in page
    assert "/api/views/" in page, "the save form lost its endpoint"

    saved = client.post(f"/api/views/{SOURCE}",
                        json={"view_name": "غالي فقط",
                              "config": {"filters": {"effective_price": "gte:120"},
                                         "q": "", "sort": "", "direction": "",
                                         "per_page": ""}})
    assert saved.status_code == 200

    page = client.get(f"/source/{SOURCE}").text
    assert "غالي فقط" in page, "a saved view must be listed where it was saved"


def test_a_view_naming_a_vanished_filter_says_so_on_the_page(client):
    """A view whose filter key no longer exists must SAY it was widened —
    the review found the old warning deleted and its test too weak to notice."""
    saved = client.post(f"/api/views/{SOURCE}",
                        json={"view_name": "قديم",
                              "config": {"filters": {"ghost_column": "has:x"},
                                         "q": "", "sort": "", "direction": "",
                                         "per_page": ""}}).json()
    view_id = saved["saved_view_id"] if "saved_view_id" in saved else \
        next(v["saved_view_id"] for v in saved.get("views", []) if v["view_name"] == "قديم")

    page = client.get(f"/source/{SOURCE}?view_id={view_id}").text
    assert "were ignored" in page, "the view widened silently"
    assert "ghost_column" in page, "the dropped filter must be NAMED"


def test_api_ui_serves_the_same_contract_the_sidebar_renders(client):
    """One module, two consumers: the endpoint's navigation must be exactly
    what the sidebar shows, source-scoped links included, and an unknown
    source must 404 instead of minting links to nowhere."""
    manifest = client.get(f"/api/ui?source_key={SOURCE}").json()
    keys = [d["key"] for d in manifest["navigation"]]
    assert keys[0] == "overview" and "settings" in keys
    data = next(d for d in manifest["navigation"] if d["key"] == "data")
    assert data["path"] == f"/source/{SOURCE}"
    assert {m["key"] for m in manifest["run_modes"]} == \
        {"update", "initial_crawl", "full_rebuild", "history_backfill"}

    page = client.get(f"/source/{SOURCE}").text
    for destination in manifest["navigation"]:
        assert destination["label"] in page, \
            f"sidebar lost {destination['label']} that /api/ui still promises"

    assert client.get("/api/ui?source_key=NOPE").status_code == 404
