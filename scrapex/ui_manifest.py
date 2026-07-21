"""Shared UI contract for every ScrapeX surface.

The Chrome side panel is intentionally compact while the local web workspace
owns the deep screens.  Both surfaces consume this manifest so navigation and
run-mode copy cannot drift as features are added.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import quote, urlencode


@dataclass(frozen=True)
class WorkspaceDestination:
    key: str
    label: str
    path: str
    description: str
    carries_source: bool = False
    source_path: str | None = None

    def public(self, source_key: str | None = None) -> dict:
        path = self.path
        if source_key and self.carries_source:
            if self.source_path is not None:
                path = self.source_path.format(source_key=quote(source_key, safe=""))
            else:
                path = f"{path}?{urlencode({'source_key': source_key})}"
        return {
            "key": self.key,
            "label": self.label,
            "path": path,
            "description": self.description,
        }


@dataclass(frozen=True)
class RunModeOption:
    key: str
    label: str
    detail: str
    warning: str | None = None

    def public(self) -> dict:
        return asdict(self)


WORKSPACE_DESTINATIONS = (
    WorkspaceDestination("overview", "Overview", "/", "Sources and warehouse totals."),
    WorkspaceDestination(
        "data", "Data", "/", "Browse, search, and arrange saved records.", True,
        "/source/{source_key}",
    ),
    WorkspaceDestination(
        "changes", "Changes", "/changes", "Recent price and availability changes.", True,
    ),
    WorkspaceDestination(
        "history", "Crawl history", "/history", "Past runs and their outcomes.", True,
    ),
    WorkspaceDestination(
        "review", "Review queue", "/review", "Resolve proposed record matches.", True,
    ),
    WorkspaceDestination("jobs", "Jobs", "/jobs", "Start and monitor collection jobs."),
    WorkspaceDestination(
        "schedules", "Schedules", "/schedules", "Review automatic collection times."
    ),
    WorkspaceDestination(
        "sync", "Sync", "/sync", "Send saved data to Sheets and Drive.", True,
    ),
    WorkspaceDestination(
        "exports", "Exports", "/exports", "Create and configure Excel exports.", True,
    ),
    WorkspaceDestination("logs", "Logs", "/logs", "Inspect detailed job activity."),
    WorkspaceDestination("settings", "Settings", "/settings", "Runtime, storage, and policy."),
)


RUN_MODE_OPTIONS = (
    RunModeOption(
        "update",
        "Update existing data",
        "Collect current data and record what changed.",
    ),
    RunModeOption(
        "initial_crawl",
        "Initial crawl",
        "Collect and save these sites for the first time.",
    ),
    RunModeOption(
        "full_rebuild",
        "Full rebuild",
        "Archive the current dataset, then crawl again.",
        "Full rebuild archives the current catalogue and takes a database backup "
        "first. Nothing is deleted, and the backup is your rollback.",
    ),
)


def workspace_navigation(source_key: str | None = None) -> list[dict]:
    """Return the same ordered navigation for the workspace and side panel."""
    return [item.public(source_key) for item in WORKSPACE_DESTINATIONS]


def ui_manifest(source_key: str | None = None) -> dict:
    """Public deterministic UI metadata consumed by both interfaces."""
    return {
        "navigation": workspace_navigation(source_key),
        "run_modes": [mode.public() for mode in RUN_MODE_OPTIONS],
    }
