"""Typed, cursor-paginated HTTP boundary for the generic catalogue."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from .. import catalog, catalog_relations
from .. import catalog_models as models
from ..catalog_models import DatasetCreate, FieldCreate, RelationshipCreate, SiteCreate

ReadConnection = Callable[[], sqlite3.Connection]
WriteAction = Callable[[Callable[[sqlite3.Connection], Any]], Any]
SiteKeyPath = Annotated[str, Path(pattern=models.KEY_PATTERN)]
PageAfter = Annotated[int, Query(ge=0)]
PageLimit = Annotated[int, Query(ge=1, le=models.MAX_PAGE_SIZE)]


def create_catalog_router(
    read_connection: ReadConnection, write_action: WriteAction,
    *, prefix: str = "/api/catalog",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["generic-catalog"])

    def read(run: Callable[[sqlite3.Connection], Any]) -> Any:
        conn = read_connection()
        try:
            return run(conn)
        except models.CatalogNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        finally:
            conn.close()

    def write(run: Callable[[sqlite3.Connection], Any]) -> Any:
        try:
            return write_action(run)
        except models.CatalogNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except models.CatalogConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except sqlite3.OperationalError as exc:
            # Matches every other write route in app.py: a busy database is a
            # retryable conflict, not an internal error.
            raise HTTPException(
                status_code=409,
                detail=f"the database is busy — try again shortly ({exc})")

    @router.post(
        "/sites", status_code=status.HTTP_201_CREATED,
        response_model=models.SiteView,
    )
    def create_site(request: SiteCreate):
        return write(lambda conn: catalog.register_site(conn, request))

    @router.get("/sites", response_model=models.SitePage)
    def sites(after_id: PageAfter = 0, limit: PageLimit = models.DEFAULT_PAGE_SIZE):
        return read(lambda conn: catalog.list_sites(
            conn, after_id=after_id, limit=limit
        ))

    @router.post(
        "/sites/{site_key}/datasets", status_code=status.HTTP_201_CREATED,
        response_model=models.DatasetView,
    )
    def create_dataset(site_key: SiteKeyPath, request: DatasetCreate):
        return write(lambda conn: catalog.register_dataset(conn, site_key, request))

    @router.get("/sites/{site_key}/datasets", response_model=models.DatasetPage)
    def datasets(
        site_key: SiteKeyPath, after_id: PageAfter = 0,
        limit: PageLimit = models.DEFAULT_PAGE_SIZE,
    ):
        return read(lambda conn: catalog.list_datasets(
            conn, site_key, after_id=after_id, limit=limit
        ))

    @router.post(
        "/datasets/{dataset_id}/fields", status_code=status.HTTP_201_CREATED,
        response_model=models.FieldView,
    )
    def create_field(
        dataset_id: Annotated[int, Path(gt=0)], request: FieldCreate
    ):
        return write(lambda conn: catalog.register_field(conn, dataset_id, request))

    @router.get("/datasets/{dataset_id}/fields", response_model=models.FieldPage)
    def fields(
        dataset_id: Annotated[int, Path(gt=0)], after_id: PageAfter = 0,
        limit: PageLimit = models.DEFAULT_PAGE_SIZE,
    ):
        return read(lambda conn: catalog.list_fields(
            conn, dataset_id, after_id=after_id, limit=limit
        ))

    @router.post(
        "/sites/{site_key}/relationships", status_code=status.HTTP_201_CREATED,
        response_model=models.RelationshipView,
    )
    def create_relationship(site_key: SiteKeyPath, request: RelationshipCreate):
        return write(lambda conn: catalog_relations.propose_relationship(
            conn, site_key, request
        ))

    @router.get(
        "/sites/{site_key}/relationships", response_model=models.RelationshipPage
    )
    def relationships(
        site_key: SiteKeyPath, after_id: PageAfter = 0,
        limit: PageLimit = models.DEFAULT_PAGE_SIZE,
    ):
        return read(lambda conn: catalog_relations.list_relationships(
            conn, site_key, after_id=after_id, limit=limit
        ))

    return router
