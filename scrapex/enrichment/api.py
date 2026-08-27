"""HTTP boundary for the organization enrichment workspace."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from . import service
from .models import (
    DefinitionCreate,
    DefinitionStatusUpdate,
    OrganizationMergeCreate,
    OrganizationMergeReverseCreate,
    ReviewDecisionCreate,
)

ReadConnection = Callable[[], sqlite3.Connection]
WriteAction = Callable[[Callable[[sqlite3.Connection], Any]], Any]
PositiveId = Annotated[int, Path(gt=0)]


def create_enrichment_router(
    read_connection: ReadConnection, write_action: WriteAction
) -> APIRouter:
    """Keep enrichment persistence behind the same General DB boundary."""
    router = APIRouter(prefix="/api/enrichment", tags=["organization-enrichment"])

    def read(run: Callable[[sqlite3.Connection], Any]) -> Any:
        conn = read_connection()
        try:
            return run(conn)
        except service.EnrichmentError as exc:
            code = 404 if str(exc).startswith(("unknown ", "organization ")) else 400
            raise HTTPException(status_code=code, detail=str(exc)) from exc
        finally:
            conn.close()

    def write(run: Callable[[sqlite3.Connection], Any]) -> Any:
        try:
            return write_action(run)
        except service.EnrichmentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"The enrichment definition could not be saved safely. ({exc})",
            ) from exc
        except sqlite3.OperationalError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"The database is busy. Wait a moment and try again. ({exc})",
            ) from exc

    @router.get("/sources/{source_dataset_key}")
    def source_proposal(
        source_dataset_key: str,
        site_key: Annotated[str | None, Query()] = None,
    ):
        return read(
            lambda conn: service.propose_definition(
                conn, source_dataset_key, site_key=site_key
            )
        )

    @router.post("/definitions", status_code=status.HTTP_201_CREATED)
    def create_definition(request: DefinitionCreate):
        return write(lambda conn: service.create_definition(conn, request))

    @router.get("/definitions/{definition_id}")
    def get_definition(definition_id: PositiveId):
        return read(lambda conn: service.get_definition(conn, definition_id))

    @router.put("/definitions/{definition_id}")
    def update_definition(definition_id: PositiveId, request: DefinitionCreate):
        return write(lambda conn: service.update_definition(conn, definition_id, request))

    @router.patch("/definitions/{definition_id}/status")
    def update_definition_status(
        definition_id: PositiveId, request: DefinitionStatusUpdate
    ):
        return write(lambda conn: service.set_definition_status(
            conn, definition_id, request.status.value
        ))

    @router.get("/definitions/{definition_id}/estimate")
    def estimate_run(definition_id: PositiveId):
        return read(lambda conn: service.estimate_definition_run(conn, definition_id))

    @router.get("/definitions/{definition_id}/diagnostics")
    def diagnostics(definition_id: PositiveId):
        return read(lambda conn: service.definition_diagnostics(conn, definition_id))

    @router.post(
        "/definitions/{definition_id}/runs", status_code=status.HTTP_202_ACCEPTED
    )
    def start_run(definition_id: PositiveId):
        return write(lambda conn: service.create_enrichment_job(conn, definition_id))

    @router.get("/definitions/{definition_id}/review")
    def review_queue(
        definition_id: PositiveId,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        after_id: Annotated[int, Query(ge=0)] = 0,
    ):
        return read(lambda conn: service.review_queue(
            conn, definition_id, limit=limit, after_id=after_id
        ))

    @router.post("/definitions/{definition_id}/review/{fact_id}/decision")
    def decide_review(
        definition_id: PositiveId,
        fact_id: PositiveId,
        request: ReviewDecisionCreate,
    ):
        return write(lambda conn: service.decide_review(
            conn, definition_id, fact_id, request
        ))

    @router.get("/definitions/{definition_id}/identity-candidates")
    def identity_candidates(
        definition_id: PositiveId,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        after_id: Annotated[int, Query(ge=0)] = 0,
    ):
        return read(lambda conn: service.identity_candidates(
            conn, definition_id, limit=limit, after_id=after_id
        ))

    @router.post("/definitions/{definition_id}/organizations/{organization_id}/merge")
    def merge_organization(
        definition_id: PositiveId,
        organization_id: str,
        request: OrganizationMergeCreate,
    ):
        return write(lambda conn: service.merge_organization(
            conn, definition_id, organization_id, request
        ))

    @router.get("/definitions/{definition_id}/merges")
    def merge_history(
        definition_id: PositiveId,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        after_id: Annotated[int, Query(ge=0)] = 0,
    ):
        return read(lambda conn: service.merge_history(
            conn, definition_id, limit=limit, after_id=after_id
        ))

    @router.post("/definitions/{definition_id}/merges/{merge_id}/reverse")
    def reverse_merge(
        definition_id: PositiveId,
        merge_id: PositiveId,
        request: OrganizationMergeReverseCreate,
    ):
        return write(lambda conn: service.reverse_organization_merge(
            conn, definition_id, merge_id, request
        ))

    return router
