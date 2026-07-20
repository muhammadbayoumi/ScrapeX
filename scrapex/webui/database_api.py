"""Read-only health API for the isolated operational databases."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from ..databases import DatabaseRegistry


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

    return router


def create_domain_health_router(
    databases: DatabaseRegistry | Callable[[], DatabaseRegistry]
) -> APIRouter:
    router = APIRouter(tags=["databases"])

    def current() -> DatabaseRegistry:
        return databases() if callable(databases) else databases

    @router.get("/api/general/health")
    def general_health() -> dict:
        return current().general.health().public()

    @router.get("/api/marketlens/health")
    def marketlens_health() -> dict:
        return current().marketlens.health().public()

    return router
