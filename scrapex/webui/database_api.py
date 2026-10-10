"""Read-only health API for the isolated operational databases."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from ..databases import DatabaseRegistry
from ..dbupgrade import upgrade_what_is_only_behind


def create_database_router(
    databases: DatabaseRegistry | Callable[[], DatabaseRegistry]
) -> APIRouter:
    router = APIRouter(prefix="/api/databases", tags=["databases"])

    def current() -> DatabaseRegistry:
        return databases() if callable(databases) else databases

    @router.get("/health")
    def health() -> dict:
        states = current().health()
        return {
            "status": "Healthy" if all(item["ok"] for item in states.values()) else "Failed",
            "databases": states,
            "action": (
                "No action is required."
                if all(item["ok"] for item in states.values())
                else "Follow the action shown for each failed database, then retry."
            ),
        }

    @router.post("/upgrade")
    def upgrade() -> dict:
        """Bring both databases up to this build, from a button.

        The database-attention page used to end with "run
        `python -m scrapex.cli init-db`, then reload" — an instruction the owner
        cannot follow, because he does not use a terminal. Anything a page tells
        him to type is a button that was never built.

        This is exactly what that command does and nothing more: the same
        registry, the same migrations, the same locks. It is safe to press when
        nothing is pending — the answer is then "applied none", which is a
        truthful no-op rather than an error.

        It cannot fix the OPPOSITE fault: a database written by a NEWER build
        than the one running. Migrations only go forward, so that state needs a
        newer engine, which is what Restart engine is for.

        THROUGH THE GUARDED PATH, the one `native.upgrade_database` and the CLI take
        (#1635). This called `initialize()` bare -- no backup, no refusal over damage,
        nothing said -- and it is the door the panel tries FIRST
        (`upgradeDatabaseFromPanel`), so whenever the engine answered, the button
        migrated his warehouse with no copy beside it. A refusal is a 409 carrying the
        reason in words, which the panel shows as it shows any refusal.
        """
        registry = current()
        report, outcome = upgrade_what_is_only_behind(registry, registry.ensure_ready())
        if outcome.refused:
            raise HTTPException(status_code=409, detail=outcome.refused)
        return {
            "ok": True,
            "applied": outcome.applied,
            "databases": report.get("databases") or {},
            "backups": [{"kind": kind, "path": where} for kind, where in outcome.backups],
            "message": outcome.message(),
        }

    return router


def create_domain_health_router(
    databases: DatabaseRegistry | Callable[[], DatabaseRegistry]
) -> APIRouter:
    router = APIRouter(tags=["databases"])

    def current() -> DatabaseRegistry:
        return databases() if callable(databases) else databases

    # ONE DATABASE, ONE ROUTE. There were two, one per database, because
    # there were two files that could be healthy or broken independently.
    # The retired route is deliberately not spelled out: a guard reads the
    # callers of engine routes, and prose naming a dead one reads as a call.
    # M5 removed that possibility, and a
    # second route answering about the same file would only invite the panel to
    # show one of them.
    @router.get("/api/engine/health")
    def engine_health() -> dict:
        return current().engine.health().public()

    return router
