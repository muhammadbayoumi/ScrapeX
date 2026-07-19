"""Spec 24/25: the Settings page, and the storage and retention controls in it.

These tests cover what the SCREEN promises, not what the modules underneath can
do — a correct backend behind a screen that overstates it is still a lie.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod, storage  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402

# Spec 33 names these thirteen, in this order.
SECTIONS = [
    "General", "Local runtime", "Storage", "Crawling", "Engines",
    "Jobs and scheduling", "Excel", "Apps Script", "Google account",
    "Data and history", "Privacy and security", "Logs and diagnostics", "About",
]


@pytest.fixture(autouse=True)
def isolated_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


def prose(client, path: str = "/settings") -> str:
    """The page with its whitespace collapsed.

    A sentence in a template wraps across source lines wherever it happens to
    fit, so asserting on raw markup makes a test fail on indentation rather than
    on meaning. This asserts on what the reader sees.
    """
    import re

    return re.sub(r"\s+", " ", client.get(path).text)


# ---- the thirteen sections (spec 24) ----------------------------------------

def test_every_named_section_is_present(client):
    body = client.get("/settings").text
    for name in SECTIONS:
        assert f">{name}</span>" in body, f"the {name} section is missing"


def test_the_sections_are_collapsed_not_one_long_screen(client):
    """Progressive disclosure is the requirement, and it is also the safety
    property: the controls that can rewrite the database take a deliberate act
    to reach rather than sitting under a scrolling thumb."""
    body = client.get("/settings").text
    assert body.count('<details class="sect"') == len(SECTIONS)
    assert "<details class=\"sect\" open" not in body


def test_settings_is_reachable_from_the_workspace_tabs(client):
    assert '/settings"' in client.get("/").text


def test_each_integration_section_points_at_its_one_page(client):
    """One place where a thing is configured, not two."""
    body = client.get("/settings").text
    assert 'href="/exports"' in body and 'href="/sync"' in body


# ---- storage (spec 25) -------------------------------------------------------

def test_storage_shows_location_size_and_health(client):
    body = prose(client)
    assert "Current location" in body and "harvest.db" in body
    assert "Health" in body and "Healthy" in body


def test_every_storage_control_the_spec_names_is_offered(client):
    body = client.get("/settings").text
    for label in ("Back up now", "Compact database", "Repair", "Export a copy",
                  "Move the database", "Restore from a backup"):
        assert label in body, f"the {label} control is missing"


def test_moving_is_disabled_until_a_folder_has_been_checked(client):
    """A move must never be the first thing a stray click does."""
    body = client.get("/settings").text
    assert 'id="do-move" data-storage="move" disabled' in body


def test_the_backup_folder_warning_is_on_the_screen_not_only_in_the_result(client):
    assert "does not survive that disk failing" in prose(client)


def test_restore_states_that_nothing_is_overwritten(client):
    assert "moved aside, not overwritten" in prose(client)


def test_a_removable_drive_is_called_out_where_the_path_is_shown(client, monkeypatch):
    monkeypatch.setattr(storage, "drive_kind", lambda p: "removable")
    body = prose(client)
    assert "removable drive" in body and "crawl in progress will fail" in body


# ---- retention (spec 25) -----------------------------------------------------

def test_the_promise_comes_before_any_control(client):
    """Every button below is read in the light of this sentence, so it must be
    above them, not in a footnote."""
    body = prose(client)
    promise = body.index("ScrapeX never deletes price history")
    assert promise < body.index("Preview this policy")


def test_the_protected_set_is_shown_in_the_owners_words(client):
    body = client.get("/settings").text
    for label in ("First recorded value", "Latest value", "Lowest price", "Highest price"):
        assert label in body


def test_every_retention_action_is_offered(client):
    body = client.get("/settings").text
    for label in ("Keep everything", "Keep one observation per day",
                  "Keep one observation per week", "Keep only the protected observations"):
        assert label in body


def test_the_space_figure_is_not_called_recovered_space(client):
    """A compaction recovers nothing by itself; naming it 'recovered' would be
    the single most misleading word available."""
    body = prose(client)
    assert "Space the archive would free" in body
    assert "Recovered space" not in body
    assert "only when you delete it yourself" in body


def test_the_prune_ordering_caveat_is_stated(client):
    assert "prune before you compact, not after" in prose(client)


# ---- the API behind the screen ----------------------------------------------

def test_a_compaction_cannot_be_requested_without_a_preview(client):
    r = client.post("/api/retention/compact", json={})
    assert r.status_code == 400 and "Run a preview first" in r.json()["detail"]


def test_a_preview_returns_measured_numbers_and_a_digest(client):
    body = client.post("/api/retention/preview").json()
    assert body["digest"] and body["bytes_after"] > 0
    assert body["observations_before"] >= body["observations_after"]


def test_saving_a_policy_invalidates_nothing_silently(client):
    """The digest must change, so a preview taken before the edit cannot
    authorise a run after it."""
    before = client.get("/api/retention").json()["digest"]
    r = client.post("/api/retention/policy",
                    json={"source_key": "*", "detail_days": 90,
                          "older_than_action": "daily_summary"})
    assert r.status_code == 200 and r.json()["digest"] != before


def test_an_impossible_policy_is_refused_with_the_reason(client):
    r = client.post("/api/retention/policy",
                    json={"source_key": "*", "detail_days": 1,
                          "older_than_action": "archive_only"})
    assert r.status_code == 400 and "shortest window" in r.json()["detail"]


def test_pruning_reports_what_it_removed_and_what_it_did_not(client):
    r = client.post("/api/retention/prune", json={"before_date": "2030-01-01"})
    assert r.status_code == 200
    assert "No price observation was touched" in r.json()["detail"]


def test_a_move_to_an_unusable_folder_is_refused_before_anything_moves(client, tmp_path, db_path):
    # A sibling of the database's folder, not a child: a folder INSIDE the
    # current one is refused for a different reason, which would make this
    # test pass without ever exercising the overwrite guard.
    occupied = tmp_path.parent / f"{tmp_path.name}-occupied"
    occupied.mkdir(exist_ok=True)
    (occupied / "harvest.db").write_bytes(b"someone else's data")
    r = client.post("/api/storage/check-move", json={"folder": str(occupied)})
    assert r.json()["ok"] is False and "will not overwrite" in r.json()["reason"]
    assert db_path.exists()


def test_the_engines_section_reads_the_registry_rather_than_a_hand_list(client):
    """A connector family that lands tomorrow must appear without anyone
    remembering to edit a template."""
    from scrapex.vocab import ConnectorFamily

    body = client.get("/settings").text
    for family in ConnectorFamily:
        assert family.value in body


def test_crawl_settings_are_real_knobs_not_decoration(client, db_path):
    """A settings field that nothing reads is worse than no field at all."""
    from scrapex.capture import crawl_settings

    assert client.post("/api/settings", json={"crawl_min_interval_s": "2.5"}).status_code == 200
    conn = dbmod.connect(db_path)
    try:
        assert crawl_settings(conn)["min_interval_s"] == 2.5
    finally:
        conn.close()


def test_a_nonsense_crawl_setting_degrades_to_the_default(client, db_path):
    from scrapex.capture import crawl_settings

    client.post("/api/settings", json={"crawl_timeout_s": "not a number"})
    conn = dbmod.connect(db_path)
    try:
        assert crawl_settings(conn)["timeout_s"] == 30.0
    finally:
        conn.close()
