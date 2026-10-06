"""Shared UI contract for every ScrapeX surface.

The Chrome side panel is intentionally compact while the local web workspace
owns the deep screens. Both surfaces read THIS module — the workspace sidebar
renders from it and /api/ui serves the same facts to the panel — so navigation
and run-mode copy cannot drift as features are added.

Ported from saved/unified-ui-design-system, whose other two ideas (token sync,
the unified navigation design itself) reached main independently. On the way
in, the destinations were corrected to main's REAL routes and the run modes
completed with history_backfill, which the branch predated — a contract that
disagrees with the product would be worse than no contract.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class WorkspaceDestination:
    key: str
    label: str
    path: str
    description: str
    group: str
    # LEGACY, FROZEN (#1056). The sprite id that panels released before the glyph
    # map draw for this destination, sent in /api/ui for them alone. Nothing here
    # reads it: the sidebar and the panel draw glyph_map() below. It never follows
    # the map, because an older panel resolves it against its OWN sprite, and a
    # <use> at an id that sprite lacks draws nothing. Remove it only after a panel
    # capability entry in scrapex/version.py whose `since` is the release in which
    # the panel stopped reading it, so that MINIMUM_EXTENSION_VERSION reaches that
    # release; the removal is a VERSION decision. tests/test_ui_manifest.py pins it.
    icon: str
    carries_source: bool = False   # append ?source_key=… when one is in view
    source_path: str | None = None  # a per-source page replaces the path outright

    def href(self, source_key: str | None = None) -> str:
        if source_key and self.source_path is not None:
            return self.source_path.format(source_key=quote(source_key, safe=""))
        if source_key and self.carries_source:
            return f"{self.path}?source_key={quote(source_key, safe='')}"
        return self.path

    def public(self, source_key: str | None = None) -> dict:
        return {"key": self.key, "label": self.label,
                "path": self.href(source_key), "description": self.description,
                "group": self.group, "icon": self.icon}


@dataclass(frozen=True)
class RunModeOption:
    key: str
    label: str
    detail: str
    warning: str | None = None

    def public(self) -> dict:
        return {"key": self.key, "label": self.label,
                "detail": self.detail, "warning": self.warning}


# THE ONE GLYPH MAP (design/glyph-map.json, #1056): which glyph each destination
# draws. This is the copy tools/sync_design_assets.py puts beside the engine's
# sprite; the panel carries its own in extension/app.html. A destination the map
# does not name draws the map's declared fallback, which is null: no glyph at all,
# so base.html writes no <use> for it and the link keeps its label.
GLYPH_MAP_PATH = Path(__file__).parent / "webui" / "static" / "material-icons" / "glyph-map.json"


# READ ON EVERY CALL: NOT AT IMPORT, AND NOT CACHED. A bundle built without
# scrapex/webui/static must still die where 0.3.0 died, in create_app's StaticFiles
# and in Starlette's words (tests/test_the_frozen_engine_carries_its_own_files.py);
# a read at import would raise first, from a different line, for the same missing
# tree. A cached map would outlive a sync: the sprite beside it and the templates
# are read from disk live, while "Restart needed" (scrapex/provenance.py) sees only
# loaded modules, so a renamed glyph would draw nothing with no badge to say why.
# A read and parse measured 15 to 18 microseconds a render.
def glyph_map() -> dict:
    glyphs = json.loads(GLYPH_MAP_PATH.read_text(encoding="utf-8"))
    # The fallback is DECLARED, null included: a map with no fallback key is not
    # a map that chose no glyph, it is a map that lost a line.
    if not (isinstance(glyphs.get("destinations"), dict) and "fallback" in glyphs
            and (glyphs["fallback"] is None or isinstance(glyphs["fallback"], str))):
        raise ValueError(f"{GLYPH_MAP_PATH} has no destinations table or no fallback "
                         "glyph; run tools/sync_design_assets.py")
    return glyphs


# The sidebar, as data. Order and grouping ARE the design (owner's layout);
# base.html renders exactly this and nothing else.
WORKSPACE_DESTINATIONS = (
    WorkspaceDestination("overview", "Overview", "/",
                         "Sources and warehouse totals.", "Browse", "dashboard"),
    WorkspaceDestination("data", "Data", "/data",
                         "Browse, search, and arrange saved records.",
                         "Browse", "storage", source_path="/source/{source_key}"),
    WorkspaceDestination("changes", "Changes", "/changes",
                         "Recent price and availability changes.",
                         "Browse", "trending-up", carries_source=True),
    WorkspaceDestination("history", "Crawl history", "/history",
                         "Past runs and their outcomes.",
                         "Browse", "history", carries_source=True),
    WorkspaceDestination("review", "Review queue", "/review",
                         "Resolve proposed record matches.",
                         "Browse", "check", carries_source=True),
    WorkspaceDestination("jobs", "Jobs", "/jobs",
                         "Start and monitor collection jobs.",
                         "Automation", "play-circle"),
    WorkspaceDestination("schedules", "Schedules", "/schedules",
                         "Review automatic collection times.",
                         "Automation", "schedule"),
    WorkspaceDestination("sync", "Google Sheets Synchronization", "/sync",
                         "Synchronize saved data with Google Sheets and Drive.",
                         "Outputs", "sync"),
    WorkspaceDestination("exports", "Exports", "/exports",
                         "Create and configure Excel exports.",
                         "Outputs", "file-download"),
    WorkspaceDestination("logs", "Logs", "/logs",
                         "Inspect detailed job activity.", "System", "description"),
    WorkspaceDestination("data-model", "Data Model", "/data-model",
                         "Tables, relationships, and how data moves.",
                         "System", "account-tree"),
    WorkspaceDestination("schema", "Schema", "/schema",
                         "What every column means and who fills it.",
                         "System", "view-column"),
    WorkspaceDestination("settings", "Settings", "/settings",
                         "Runtime, storage, and policy.", "System", "settings"),
)


# The run-mode copy, word for word what the panel shipped — the panel was the
# single source in practice, so its wording is the contract's starting truth.
RUN_MODE_OPTIONS = (
    RunModeOption("update", "Update existing data",
                  "Collect current data and record what changed."),
    RunModeOption("initial_crawl", "Initial crawl",
                  "Collect and save these sites for the first time."),
    RunModeOption("full_rebuild", "Full rebuild",
                  "Archive the current dataset, then crawl again.",
                  "Full rebuild archives the current catalogue and takes a "
                  "database backup first. Nothing is deleted, and the backup "
                  "is your rollback."),
    RunModeOption("history_backfill", "History backfill",
                  "Collect the history this source itself publishes (e.g. ten "
                  "years of weekly prices), recorded as the source's own dated "
                  "claims. Safe to repeat — known points are skipped."),
)


def workspace_navigation_groups(source_key: str | None = None
                                ) -> list[tuple[str, list[tuple[str, str, str, str | None]]]]:
    """The sidebar's grouped (href, label, key, glyph) rows, in design order.

    Shaped exactly like the tuple list base.html used to inline, so the
    template's loop body did not have to change to adopt the contract. The glyph
    is the map's, never the legacy `icon` field (#1056), and None for a key the
    map does not name: base.html then draws no glyph."""
    glyphs = glyph_map()
    groups: list[tuple[str, list[tuple[str, str, str, str | None]]]] = []
    for destination in WORKSPACE_DESTINATIONS:
        if not groups or groups[-1][0] != destination.group:
            groups.append((destination.group, []))
        glyph = glyphs["destinations"].get(destination.key, glyphs["fallback"])
        groups[-1][1].append((destination.href(source_key), destination.label,
                              destination.key, glyph))
    return groups


def ui_manifest(source_key: str | None = None) -> dict:
    """Public deterministic UI metadata consumed by both interfaces."""
    return {
        "navigation": [d.public(source_key) for d in WORKSPACE_DESTINATIONS],
        "run_modes": [mode.public() for mode in RUN_MODE_OPTIONS],
    }
