"""The shared UI contract: one module feeds the sidebar and /api/ui.

Ported from saved/unified-ui-design-system; these pins are what make it a
CONTRACT — a destination that names a route the app does not serve fails here
instead of shipping as a dead link. The glyph each destination draws is no longer
this module's: tests/test_each_destination_draws_one_declared_glyph.py guards it.
"""
from __future__ import annotations

import re
from pathlib import Path

from scrapex.ui_manifest import (
    RUN_MODE_OPTIONS, WORKSPACE_DESTINATIONS, ui_manifest,
    workspace_navigation_groups,
)
import pytest

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension


def test_every_destination_names_a_route_the_app_actually_serves():
    app_source = Path("scrapex/webui/app.py").read_text(encoding="utf-8")
    served = set(re.findall(r'@app\.get\("(/[^"{]*)', app_source))
    for destination in WORKSPACE_DESTINATIONS:
        path = destination.path.rstrip("/") or "/"
        assert path in served or destination.path in served, \
            f"{destination.key} points at {destination.path!r}, which nothing serves"
        if destination.source_path:
            base = destination.source_path.split("{", 1)[0]
            assert any(r.startswith(base.rstrip("/")) for r in served), \
                f"{destination.key} source_path {destination.source_path!r} unserved"


#: What every panel released before the glyph map (#1056) draws for each
#: destination, read off the `icon` field /api/ui sends. Each is a symbol in the
#: sprite those panels ship (design/material-icons.svg at main 03f1edab).
LEGACY_ICONS = {
    "overview": "dashboard", "data": "storage", "changes": "trending-up",
    "history": "history", "review": "check", "jobs": "play-circle",
    "schedules": "schedule", "sync": "sync", "exports": "file-download",
    "logs": "description", "data-model": "account-tree", "schema": "view-column",
    "settings": "settings",
}


def test_the_legacy_icon_field_is_frozen_for_panels_older_than_the_map():
    """The engine keeps sending `icon` unchanged, for panels that still read it.

    FROZEN, NOT FOLLOWING THE MAP. An older panel resolves this id against its OWN
    sprite, so renaming a glyph in design/glyph-map.json (Lucide, phase 3) must not
    rename it here: the new id would be one the older sprite lacks, and a <use> at
    a missing id draws nothing. Nothing in this repository draws the field any
    more; tests/test_each_destination_draws_one_declared_glyph.py guards what does.
    A destination added later adds its row to LEGACY_ICONS, naming a glyph the
    sprites of those older panels carry. The field goes only with a panel
    capability entry, as its comment in scrapex/ui_manifest.py says."""
    sent = {d["key"]: d["icon"] for d in ui_manifest()["navigation"]}
    assert sent == LEGACY_ICONS


def test_the_grouped_shape_matches_what_the_sidebar_renders():
    groups = workspace_navigation_groups()
    assert [g for g, _ in groups] == ["Browse", "Automation", "Outputs", "System"]
    flat = {key: href for _, items in groups for href, label, key, icon in items}
    assert flat["data"] == "/data"
    assert flat["overview"] == "/"

    scoped = {key: href for _, items in workspace_navigation_groups("GPP_ENERGY")
              for href, label, key, icon in items}
    assert scoped["data"] == "/source/GPP_ENERGY"      # per-source page replaces
    assert scoped["changes"] == "/changes?source_key=GPP_ENERGY"
    assert scoped["jobs"] == "/jobs"                    # never carries a source


def test_run_modes_cover_the_vocabulary_the_panel_offers():
    modes = {m.key: m for m in RUN_MODE_OPTIONS}
    assert set(modes) == {"update", "initial_crawl", "full_rebuild", "history_backfill"}
    assert modes["full_rebuild"].warning, "the destructive-adjacent mode must warn"
    assert "Safe to repeat" in modes["history_backfill"].detail


def test_the_public_manifest_is_json_shaped():
    manifest = ui_manifest("GPP_ENERGY")
    assert {"navigation", "run_modes"} <= set(manifest)
    assert all({"key", "label", "path", "description", "group", "icon"}
               <= set(d) for d in manifest["navigation"])
    assert all({"key", "label", "detail", "warning"} <= set(m)
               for m in manifest["run_modes"])


def test_the_panel_is_wired_to_adopt_the_contract():
    """A contract only one surface reads is not a contract. The panel fetches
    /api/ui and overlays its run-mode copy; the workspace sidebar renders from
    the module via the template global."""
    panel = Path("extension/app.js").read_text(encoding="utf-8")
    assert '"/api/ui"' in panel and "adoptUiContract" in panel
    assert "manifest.navigation" in panel and "renderWorkspaceNavigation" in panel
    for destination in WORKSPACE_DESTINATIONS:
        assert f'key: "{destination.key}"' in panel
        assert f'path: "{destination.path}"' in panel
    base = Path("scrapex/webui/templates/base.html").read_text(encoding="utf-8")
    assert "workspace_navigation_groups" in base
