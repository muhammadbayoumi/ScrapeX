"""The side panel and web workspace share one UI contract."""
from __future__ import annotations

from scrapex.ui_manifest import RUN_MODE_OPTIONS, ui_manifest, workspace_navigation
from scrapex.vocab import RunMode


def test_navigation_keys_are_unique_and_stable():
    items = workspace_navigation()
    assert [item["key"] for item in items] == [
        "overview", "data", "changes", "history", "review", "jobs",
        "schedules", "sync", "exports", "logs", "settings",
    ]
    assert len({item["key"] for item in items}) == len(items)


def test_source_context_is_carried_only_where_it_is_useful():
    items = {item["key"]: item for item in workspace_navigation("SHOP & MORE")}
    assert items["data"]["path"] == "/source/SHOP%20%26%20MORE"
    assert items["changes"]["path"] == "/changes?source_key=SHOP+%26+MORE"
    assert items["jobs"]["path"] == "/jobs"


def test_every_engine_run_mode_has_shared_interface_copy():
    assert {mode.key for mode in RUN_MODE_OPTIONS} == {mode.value for mode in RunMode}
    assert all(mode.label and mode.detail for mode in RUN_MODE_OPTIONS)


def test_public_manifest_contains_both_shared_concepts():
    payload = ui_manifest()
    assert payload["navigation"] == workspace_navigation()
    assert [mode["key"] for mode in payload["run_modes"]] == [
        "update", "initial_crawl", "full_rebuild",
    ]
