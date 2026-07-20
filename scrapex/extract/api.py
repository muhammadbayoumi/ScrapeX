"""Router for the first owner-approved generic extraction workflow."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path as ApiPath, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..catalog_models import CatalogConflict, CatalogNotFound
from . import service
from .models import (
    DEFAULT_RECORD_PAGE_SIZE,
    MAX_RECORD_PAGE_SIZE,
    CandidateApproval,
    CandidateNotApprovable,
    ExtractionConflict,
    ExtractionNotFound,
    SnapshotCreate,
)

ReadConnection = Callable[[], sqlite3.Connection]
WriteAction = Callable[[Callable[[sqlite3.Connection], Any]], Any]
PositiveId = Annotated[int, ApiPath(gt=0)]
PageAfter = Annotated[int, Query(ge=0)]
PageLimit = Annotated[int, Query(ge=1, le=MAX_RECORD_PAGE_SIZE)]

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "webui" / "templates")
)


def create_extraction_router(
    read_connection: ReadConnection, write_action: WriteAction
) -> APIRouter:
    """Create one isolated router so app.py only owns the mount point."""
    router = APIRouter(tags=["generic-extraction"])

    def read(run: Callable[[sqlite3.Connection], Any]) -> Any:
        conn = read_connection()
        try:
            return run(conn)
        except (ExtractionNotFound, CatalogNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()

    def write(run: Callable[[sqlite3.Connection], Any]) -> Any:
        try:
            return write_action(run)
        except (ExtractionNotFound, CatalogNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CandidateNotApprovable as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (ExtractionConflict, CatalogConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "The generic dataset could not be saved safely. Review the "
                    f"candidate and try again. ({exc})"
                ),
            ) from exc
        except sqlite3.OperationalError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"The database is busy. Wait a moment and try again. ({exc})",
            ) from exc

    @router.get("/datasets", response_class=HTMLResponse)
    def datasets_workspace(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request,
            name="datasets.html",
            context={"tab": "datasets", "source_key": None},
        )

    @router.post(
        "/api/extract/snapshots", status_code=status.HTTP_201_CREATED
    )
    def create_snapshot(request: SnapshotCreate):
        return write(lambda conn: service.save_snapshot(conn, request))

    @router.get("/api/extract/snapshots/{snapshot_id}/candidates")
    def snapshot_candidates(snapshot_id: PositiveId):
        return read(lambda conn: service.discover_snapshot(conn, snapshot_id))

    @router.post(
        "/api/extract/snapshots/{snapshot_id}/approve",
        status_code=status.HTTP_201_CREATED,
    )
    def approve_snapshot_candidate(
        snapshot_id: PositiveId, request: CandidateApproval
    ):
        return write(
            lambda conn: service.approve_candidate(conn, snapshot_id, request)
        )

    @router.get("/api/extract/datasets")
    def approved_datasets(
        after_id: PageAfter = 0,
        limit: PageLimit = DEFAULT_RECORD_PAGE_SIZE,
    ):
        return read(
            lambda conn: service.list_datasets(
                conn, after_id=after_id, limit=limit
            )
        )

    @router.get("/api/extract/datasets/{dataset_id}/records")
    def dataset_records(
        dataset_id: PositiveId,
        after_id: PageAfter = 0,
        limit: PageLimit = DEFAULT_RECORD_PAGE_SIZE,
    ):
        return read(
            lambda conn: service.browse_records(
                conn, dataset_id, after_id=after_id, limit=limit
            )
        )

    return router
