"""The shared UI contract: one module feeds the sidebar and /api/ui.

Ported from saved/unified-ui-design-system; these pins are what make it a
CONTRACT — a destination that names a route the app does not serve, or an
icon the sprite lacks, fails here instead of shipping as a dead link.
"""
from __future__ import annotations

import re
from pathlib import Path

from scrapex.ui_manifest import (
    RUN_MODE_OPTIONS, WORKSPACE_DESTINATIONS, ui_manifest,
    workspace_navigation_groups,
)


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


def test_every_icon_exists_in_the_sprite():
    sprite = Path("scrapex/webui/static/material-icons/material-icons.svg").read_text(encoding="utf-8")
    for destination in WORKSPACE_DESTINATIONS:
        assert f'id="{destination.icon}"' in sprite, \
            f"{destination.key} uses icon {destination.icon!r} the sprite lacks"


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
    base = Path("scrapex/webui/templates/base.html").read_text(encoding="utf-8")
    assert "workspace_navigation_groups" in base
