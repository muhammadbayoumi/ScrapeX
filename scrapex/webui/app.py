"""ScrapeX local web app: HTML browse UI + a JSON API for the Chrome extension.

Read routes go through reports.py (zero SQL in the web layer, DRY). The one
WRITE route (/api/capture) runs a connector + ingest under the DB write lock
(A10) — the extension triggers it but never parses anything itself; extraction
stays in the Python connectors.

Bound to 127.0.0.1 by the CLI — a local, single-machine surface.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import db as dbmod
from ..capture import capture_source
from ..changes import change_summary, recent_changes
from ..config import MANIFEST_FILE, SourceEntry, load_manifest
from ..connectors.factory import _BUILDERS
from ..databases import DatabaseRegistry, GeneralDatabase, MarketLensDatabase
from ..jobs import JobRunner, create_job, get_job, job_logs, list_jobs, set_control
from ..fields import (
    delete_view, ensure_fields, list_fields, list_views, reorder, reset_view, save_view,
    set_display_name, set_visibility,
)
from ..features import manifest as feature_manifest
from ..extract.api import create_extraction_router
from ..manifest_io import DuplicateSourceError, add_source
from ..matching import (
    ConflictError, Decision, decide, pending_reviews, suggest_for_source, undo_decision,
)
from ..outputs import (
    NotConfiguredError, all_destinations, apps_script_script_text, apps_script_send,
    apps_script_status, apps_script_test, excel_export, excel_status, google_connect,
    google_disconnect, google_push, google_status, rotate_funnel_token,
)
from ..settings import UnknownSettingError, get_state, public_settings
from ..settings import get as settings_get
from ..settings import save as save_settings
from .. import compaction, pricehistory, retention
from ..storage import (
    StorageRefused, backup_folder, backup_now, check_move, export_database,
    migrate_location, open_folder, repair, resolve_db_path, restore, storage_status,
)
from ..storage import compact as storage_compact
from ..probe import probe as probe_url
from ..reports import (
    SORTABLE, browse_observations, crawl_history, export_source_table, list_sources,
    price_extremes, source_summary,
)
from ..scheduler import list_schedules, upsert_schedule
from ..vocab import (
    Authority, Cadence, ConnectorFamily, ExtractKind, ExtractScope, Fetcher,
    JobControl, MissedRunPolicy, OverlapPolicy, RunMode, ScheduleFrequency, VatMode,
)
from .catalog_api import create_catalog_router
from .database_api import create_database_router, create_domain_health_router

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
STATIC_DIR = Path(__file__).parent / "static"
PAGE_SIZE = 50
AVAILABILITY_OPTIONS = ("in_stock", "out_of_stock", "unknown")


def create_app(
    db_path: Path | str | None = None,
    manifest_path: Path | str = MANIFEST_FILE,
    start_worker: bool = False,
    *,
    databases: DatabaseRegistry | None = None,
    general_db_path: Path | str | None = None,
) -> FastAPI:
    if databases is None and db_path is None:
        databases = DatabaseRegistry.defaults()
        databases.verify()
    if databases is not None:
        databases.verify()
        price_path = databases.marketlens.path
        general_database = databases.general
    else:
        price_path = Path(db_path)  # explicit legacy-compatible test/session path
        general_database = GeneralDatabase(general_db_path) if general_db_path else None
        if general_database is not None:
            general_database.initialize()
    app = FastAPI(title="ScrapeX", docs_url=None, redoc_url=None)
    app.state.db_path = str(price_path)
    app.state.databases = databases
    app.state.general_database = general_database
    app.state.manifest_path = str(manifest_path)
    app.state.manifest = load_manifest(manifest_path)
    # The job worker owns ALL long-running crawls (spec 4). Tests drive the
    # synchronous seam instead, so the thread is opt-in.
    # The worker follows the warehouse: a move or a compaction changes
    # app.state.db_path, and a worker still holding the old file would crawl
    # into a database nothing else reads.
    app.state.runner = JobRunner(
        str(price_path), lambda: app.state.manifest,
        path_provider=lambda: app.state.db_path) if start_worker else None
    if app.state.runner is not None:
        app.state.runner.start()

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # The extension calls from a chrome-extension:// origin. Local-only server,
    # no credentials — permissive CORS is acceptable here (A9: still 127.0.0.1).
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    if databases is not None:
        app.include_router(create_database_router(lambda: app.state.databases))
        app.include_router(create_domain_health_router(lambda: app.state.databases))

    def read_conn():
        if app.state.databases is not None:
            return app.state.databases.marketlens.connect()
        return dbmod.connect(app.state.db_path)

    def general_read_conn():
        if app.state.general_database is None:
            return read_conn()
        return app.state.general_database.connect()

    # ---- HTML browse UI ----------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        conn = read_conn()
        try:
            sources = list_sources(conn)
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(request=request, name="overview.html",
                                          context={"sources": sources, "tab": "overview",
                                                   "source_key": None})

    @app.get("/source/{source_key}", response_class=HTMLResponse)
    def source(request: Request, source_key: str, q: str = "", availability: str = "",
               page: int = 1, sort: str = "", direction: str = "asc"):
        page = max(1, page)
        conn = read_conn()
        try:
            summary = source_summary(conn, source_key)
            page_data, fields, views = None, [], []
            if summary is not None:
                page_data = browse_observations(
                    conn, source_key, search=q or None, availability=availability or None,
                    sort=sort or None, direction=direction,
                    offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE)
                # Register the columns on first view so "manage columns" has
                # something to manage, then read back the owner's arrangement.
                header, _ = export_source_table(conn, source_key, limit=1)
                ensure_fields(conn, source_key, header)
                conn.commit()
                fields, views = list_fields(conn, source_key), list_views(conn, source_key)
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(
            request=request, name="source.html",
            context={"summary": summary, "page_data": page_data, "source_key": source_key,
                     "q": q, "availability": availability, "page": page, "tab": "data",
                     "sort": sort or "name", "direction": direction,
                     "sortable": list(SORTABLE), "fields": fields, "views": views,
                     "availability_options": AVAILABILITY_OPTIONS},
            status_code=200 if summary is not None else 404)

    # ---- Workspace tabs (spec 21) ------------------------------------------
    # Each tab is a thin render over logic that already exists and is tested;
    # `source_key` rides along so switching tabs keeps the dataset in view.

    def _page(request: Request, name: str, tab: str, source_key: str | None, **ctx):
        return TEMPLATES.TemplateResponse(request=request, name=name,
                                          context={"tab": tab, "source_key": source_key, **ctx})

    @app.get("/changes", response_class=HTMLResponse)
    def page_changes(request: Request, source_key: str | None = None, limit: int = 100):
        conn = read_conn()
        try:
            return _page(request, "changes.html", "changes", source_key,
                         summary=change_summary(conn, source_key) if source_key else {},
                         changes=recent_changes(conn, source_key, limit=limit),
                         extremes=price_extremes(conn, source_key) if source_key else [],
                         offers=_offers_with_history(conn, source_key) if source_key else [],
                         sources=[s.source_key for s in list_sources(conn)])
        finally:
            conn.close()

    @app.get("/history", response_class=HTMLResponse)
    def page_history(request: Request, source_key: str | None = None):
        conn = read_conn()
        try:
            return _page(request, "history.html", "history", source_key,
                         runs=crawl_history(conn, source_key),
                         sources=[s.source_key for s in list_sources(conn)])
        finally:
            conn.close()

    @app.get("/review", response_class=HTMLResponse)
    def page_review(request: Request, source_key: str | None = None):
        conn = read_conn()
        try:
            return _page(request, "review.html", "review", source_key,
                         pending=pending_reviews(conn, source_key, limit=100),
                         sources=[s.source_key for s in list_sources(conn)])
        finally:
            conn.close()

    @app.get("/jobs", response_class=HTMLResponse)
    def page_jobs(request: Request):
        conn = read_conn()
        try:
            return _page(request, "jobs.html", "jobs", None,
                         jobs=[_job_view(j) for j in list_jobs(conn, limit=50)])
        finally:
            conn.close()

    @app.get("/schedules", response_class=HTMLResponse)
    def page_schedules(request: Request):
        conn = read_conn()
        try:
            return _page(request, "schedules.html", "schedules", None,
                         schedules=list_schedules(conn))
        finally:
            conn.close()

    @app.get("/logs", response_class=HTMLResponse)
    def page_logs(request: Request, job_ref: str | None = None):
        conn = read_conn()
        try:
            jobs = list_jobs(conn, limit=50)
            job_ref = job_ref or (jobs[0]["job_ref"] if jobs else None)
            return _page(request, "logs.html", "logs", None,
                         jobs=[_job_view(j) for j in jobs], job_ref=job_ref,
                         entries=job_logs(conn, job_ref) if job_ref else [])
        finally:
            conn.close()

    @app.get("/exports", response_class=HTMLResponse)
    def page_exports(request: Request, source_key: str = ""):
        conn = read_conn()
        try:
            return _page(request, "excel.html", "exports", source_key or None,
                         status=excel_status(conn), settings=public_settings(conn),
                         sources=list_sources(conn))
        finally:
            conn.close()

    @app.get("/settings", response_class=HTMLResponse)
    def page_settings(request: Request):
        """Spec 33: thirteen sections, every one closed until it is asked for."""
        conn = read_conn()
        try:
            return _page(request, "settings.html", "settings", None,
                         settings=public_settings(conn),
                         storage=storage_status(conn, app.state.db_path),
                         retention=_retention_view(conn),
                         excel=excel_status(conn), funnel=apps_script_status(conn),
                         google=google_status(conn),
                         engines=_engine_rows(),
                         schedule_count=len(list_schedules(conn)),
                         about=_about(conn))
        finally:
            conn.close()

    @app.get("/sync", response_class=HTMLResponse)
    def page_sync(request: Request, source_key: str = ""):
        conn = read_conn()
        try:
            return _page(request, "sync.html", "sync", source_key or None,
                         funnel=apps_script_status(conn), google=google_status(conn),
                         settings=public_settings(conn), sources=list_sources(conn))
        finally:
            conn.close()

    # ---- JSON API (the Chrome extension) -----------------------------------

    @app.get("/api/health")
    def api_health():
        from .. import __version__
        conn = read_conn()
        try:
            n = len(list_sources(conn))
        finally:
            conn.close()
        return {"ok": True, "app": "scrapex", "version": __version__, "sources_with_data": n}

    @app.get("/api/features")
    def api_features():
        """What is genuinely usable, separate from what the roadmap names."""
        return feature_manifest()

    @app.get("/api/sources")
    def api_sources():
        conn = read_conn()
        try:
            summaries = {s.source_key: s for s in list_sources(conn)}
        finally:
            conn.close()
        out = []
        for entry in app.state.manifest.sources:
            s = summaries.get(entry.source_key)
            out.append({
                "source_key": entry.source_key, "source_name": entry.source_name,
                "base_url": entry.base_url, "family": entry.family.value,
                "active": entry.active, "implemented": _is_implemented(entry),
                "observations": s.observations if s else 0,
                "products": s.products if s else 0,
            })
        return {"sources": out}

    @app.get("/api/resolve")
    def api_resolve(url: str):
        entry = app.state.manifest.resolve_by_url(url)
        if entry is None:
            return {"matched": False}
        return {"matched": True, "source_key": entry.source_key,
                "source_name": entry.source_name, "implemented": _is_implemented(entry)}

    @app.get("/manage", response_class=HTMLResponse)
    def manage(request: Request):
        conn = read_conn()
        try:
            summaries = {s.source_key: s for s in list_sources(conn)}
        finally:
            conn.close()
        rows = []
        for entry in app.state.manifest.sources:
            s = summaries.get(entry.source_key)
            rows.append({"entry": entry, "implemented": entry.family in _BUILDERS,
                         "observations": s.observations if s else 0})
        return TEMPLATES.TemplateResponse(request=request, name="manage.html", context={
            "rows": rows, "tab": "overview", "source_key": None,
            "families": [f.value for f in ConnectorFamily],
            "cadences": [c.value for c in Cadence],
            "authorities": [a.value for a in Authority],
            "vat_modes": [v.value for v in VatMode],
            "kinds": [k.value for k in ExtractKind],
            "scopes": [s.value for s in ExtractScope],
        })

    @app.post("/api/probe")
    def api_probe(body: dict):
        url = (body or {}).get("url", "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        return probe_url(url).to_json()

    @app.post("/api/sources")
    def api_add_source(body: dict):
        try:
            entry = _entry_from_form(body or {})
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid source: {exc}")
        try:
            add_source(entry, app.state.manifest_path)
        except DuplicateSourceError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        app.state.manifest = load_manifest(app.state.manifest_path)  # reflect the new source
        return {"ok": True, "source_key": entry.source_key,
                "implemented": entry.family in _BUILDERS}

    # ---- schedules (spec 26: the LOCAL RUNTIME schedules, not the browser) --

    @app.get("/api/schedules")
    def api_schedules():
        conn = read_conn()
        try:
            return {
                "schedules": list_schedules(conn),
                # Stated plainly in the API itself so no UI can imply otherwise.
                "note": ("Schedules run only while the ScrapeX engine is running. "
                         "Nothing can wake a sleeping or powered-off machine; a slot "
                         "missed while it was off follows the missed-run policy."),
            }
        finally:
            conn.close()

    @app.post("/api/schedules/{source_key}")
    def api_set_schedule(source_key: str, body: dict):
        body = body or {}
        try:
            app.state.manifest.get(source_key)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown source_key {source_key!r}")
        frequency = body.get("frequency", ScheduleFrequency.MANUAL.value)
        if frequency not in {f.value for f in ScheduleFrequency}:
            raise HTTPException(status_code=400, detail="frequency must be "
                                f"{[f.value for f in ScheduleFrequency]}")
        try:
            saved = _write(lambda c: upsert_schedule(
                c, source_key, frequency=frequency,
                run_at=body.get("run_at", "09:00"), tz_name=body.get("timezone", "UTC"),
                weekday=body.get("weekday"), run_mode=body.get("run_mode", RunMode.UPDATE.value),
                missed_run_policy=body.get("missed_run_policy",
                                           MissedRunPolicy.RUN_WHEN_AVAILABLE.value),
                overlap_policy=body.get("overlap_policy", OverlapPolicy.QUEUE.value),
                enabled=bool(body.get("enabled", True))))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return saved

    # ---- columns + saved views (spec 22: hiding is never deleting) ----------

    def _write(fn):
        """Run a short write under the process lock, then commit.

        A crawl in progress holds that lock, which is normal contention rather
        than a server fault — so it becomes a retryable 409, never an opaque 500.
        """
        try:
            with dbmod.write_lock(app.state.db_path):
                conn = read_conn()
                try:
                    result = fn(conn)
                    conn.commit()
                    return result
                finally:
                    conn.close()
        except dbmod.DbLockedError:
            raise HTTPException(
                status_code=409,
                detail="a crawl is currently writing to the database — try again shortly")

    def _general_write(fn):
        if app.state.general_database is None:
            return _write(fn)
        try:
            return app.state.general_database.write(fn)
        except dbmod.DbLockedError:
            raise HTTPException(
                status_code=409,
                detail="the General database is busy — try again shortly",
            )

    # The namespaced route is authoritative. The old catalogue path stays as a
    # compatibility alias during G2's rebase and writes to the same General DB.
    app.include_router(create_catalog_router(
        general_read_conn, _general_write, prefix="/api/general/catalog"
    ))
    app.include_router(create_catalog_router(
        general_read_conn, _general_write, prefix="/api/catalog"
    ))
    app.include_router(create_extraction_router(general_read_conn, _general_write))

    @app.get("/api/fields/{source_key}")
    def api_fields(source_key: str):
        conn = read_conn()
        try:
            header, _ = export_source_table(conn, source_key, limit=1)
            ensure_fields(conn, source_key, header)
            conn.commit()
            return {"source_key": source_key, "fields": list_fields(conn, source_key),
                    "views": list_views(conn, source_key)}
        finally:
            conn.close()

    @app.post("/api/fields/{source_key}")
    def api_update_fields(source_key: str, body: dict):
        """Rename / hide / reorder / reset — all reversible, none destructive."""
        body = body or {}
        def apply(conn):
            if "reset" in body:
                reset_view(conn, source_key)
            if "display_name" in body:
                if not set_display_name(conn, source_key, body.get("field_key", ""),
                                        body["display_name"]):
                    raise KeyError(body.get("field_key"))
            if "hidden" in body:
                if not set_visibility(conn, source_key, body.get("field_key", ""),
                                      bool(body["hidden"])):
                    raise KeyError(body.get("field_key"))
            if "order" in body:
                reorder(conn, source_key, list(body["order"]))
            return list_fields(conn, source_key)
        try:
            return {"source_key": source_key, "fields": _write(apply)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown field {exc.args[0]!r}")

    @app.post("/api/views/{source_key}")
    def api_save_view(source_key: str, body: dict):
        name = (body or {}).get("view_name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="view_name is required")
        view_id = _write(lambda c: save_view(c, source_key, name, (body or {}).get("config", {})))
        return {"saved_view_id": view_id, "view_name": name}

    @app.delete("/api/views/{saved_view_id}")
    def api_delete_view(saved_view_id: int):
        if not _write(lambda c: delete_view(c, saved_view_id)):
            raise HTTPException(status_code=404, detail=f"unknown view {saved_view_id}")
        return {"saved_view_id": saved_view_id, "deleted": True}

    # ---- review queue (spec 14: the human gate — nothing auto-approves) -----

    @app.get("/api/review")
    def api_review(source_key: str | None = None, limit: int = 50):
        conn = read_conn()
        try:
            return {"pending": pending_reviews(conn, source_key, limit=limit)}
        finally:
            conn.close()

    @app.post("/api/review/suggest")
    def api_review_suggest(body: dict):
        source_key = (body or {}).get("source_key")
        if not source_key:
            raise HTTPException(status_code=400, detail="source_key is required")
        with dbmod.write_lock(app.state.db_path):
            conn = read_conn()
            try:
                written = suggest_for_source(conn, source_key)
                conn.commit()
            finally:
                conn.close()
        return {"source_key": source_key, "suggested": written}

    @app.post("/api/review/{match_id}")
    def api_review_decide(match_id: int, body: dict):
        decision = (body or {}).get("decision", "")
        if decision not in (Decision.APPROVE, Decision.NEW, Decision.SEPARATE, Decision.LATER):
            raise HTTPException(status_code=400, detail="decision must be "
                                f"{[Decision.APPROVE, Decision.NEW, Decision.SEPARATE, Decision.LATER]}")
        with dbmod.write_lock(app.state.db_path):
            conn = read_conn()
            try:
                result = decide(conn, match_id, decision, (body or {}).get("material_id"))
                conn.commit()
            except KeyError:
                raise HTTPException(status_code=404, detail=f"unknown match {match_id}")
            except ConflictError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            finally:
                conn.close()
        return result

    @app.post("/api/review/{match_id}/undo")
    def api_review_undo(match_id: int):
        with dbmod.write_lock(app.state.db_path):
            conn = read_conn()
            try:
                undone = undo_decision(conn, match_id)
                conn.commit()
            finally:
                conn.close()
        if not undone:
            raise HTTPException(status_code=409, detail=f"match {match_id} has no active link to undo")
        return {"match_id": match_id, "undone": True}

    # ---- output destinations (spec 9/21/22/23) ------------------------------
    # Every route below reports the destination's REAL state, and every action
    # returns what actually happened rather than an optimistic acknowledgement.

    @app.get("/api/outputs")
    def api_outputs():
        """Real status of every output destination.

        Each entry reports whether it is usable RIGHT NOW and, when it is not,
        exactly what is missing — so the panel can say "needs setup" with a
        reason instead of offering a destination that will fail at write time.
        """
        conn = read_conn()
        try:
            destinations = all_destinations(conn)
        finally:
            conn.close()
        # `detail` stays populated for older panel builds that render it.
        return {"outputs": [{**d, "detail": d.get("detail") or d.get("blocker", "")}
                            for d in destinations]}

    def _write_conn():
        """A connection for routes that persist settings or run status."""
        return read_conn()

    def _integration(fn, *args, state_after=None, **kwargs):
        """Run one integration action under the write lock, mapping the
        destination's own refusal sentence onto a 400 instead of a traceback."""
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                result = fn(conn, *args, **kwargs)
                conn.commit()
                extra = state_after(conn) if state_after else {}
            except NotConfiguredError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            finally:
                conn.close()
        body = result.as_state() if hasattr(result, "as_state") else result
        return {**body, **extra} if isinstance(body, dict) else body

    @app.get("/api/settings")
    def api_settings():
        conn = read_conn()
        try:
            return {"settings": public_settings(conn)}
        finally:
            conn.close()

    @app.post("/api/settings")
    def api_save_settings(body: dict):
        try:
            with dbmod.write_lock(app.state.db_path):
                conn = _write_conn()
                try:
                    changed = save_settings(conn, body or {})
                    conn.commit()
                    current = public_settings(conn)
                finally:
                    conn.close()
        except UnknownSettingError as exc:
            raise HTTPException(status_code=400, detail=f"unknown setting {exc}")
        return {"changed": changed, "settings": current}

    @app.get("/api/outputs/excel")
    def api_excel_status():
        conn = read_conn()
        try:
            return excel_status(conn)
        finally:
            conn.close()

    @app.post("/api/outputs/excel/export")
    def api_excel_export(body: dict):
        keys = _source_keys(body)
        return _integration(excel_export, keys, state_after=excel_status)

    @app.get("/api/outputs/apps-script")
    def api_apps_script_status():
        conn = read_conn()
        try:
            return apps_script_status(conn)
        finally:
            conn.close()

    @app.get("/api/outputs/apps-script/script")
    def api_apps_script_source():
        """The script to paste into the sheet (spec 22: Copy Script)."""
        text = apps_script_script_text()
        if not text:
            raise HTTPException(status_code=404, detail="the Apps Script source is not bundled")
        return {"script": text}

    @app.post("/api/outputs/apps-script/test")
    def api_apps_script_test():
        return _integration(apps_script_test, state_after=apps_script_status)

    @app.post("/api/outputs/apps-script/send")
    def api_apps_script_send(body: dict):
        keys = _source_keys(body)
        return _integration(apps_script_send, keys[0], state_after=apps_script_status)

    @app.post("/api/outputs/apps-script/token")
    def api_apps_script_token():
        """Mint a new shared token and show it ONCE, for pasting into the script."""
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                token = rotate_funnel_token(conn)
                conn.commit()
            finally:
                conn.close()
        return {"token": token, "shown_once": True,
                "next_step": "Paste this into the Apps Script property SCRAPEX_TOKEN, "
                             "then redeploy. The old token stops working immediately."}

    @app.get("/api/outputs/google")
    def api_google_status():
        conn = read_conn()
        try:
            return google_status(conn)
        finally:
            conn.close()

    @app.post("/api/outputs/google/connect")
    def api_google_connect():
        """Start the one-time browser sign-in.

        It runs on a worker thread because the OAuth flow blocks on a local
        callback server: holding the request open would make the page look hung
        for as long as the owner spends in Google's consent screen.
        """
        import threading

        state = app.state.google_connect = {"status": "connecting", "error": ""}

        def run():
            try:
                google_connect()
                state.update(status="connected")
            except Exception as exc:                       # surfaced verbatim below
                state.update(status="error", error=str(exc))

        threading.Thread(target=run, daemon=True).start()
        return {"status": "connecting",
                "note": "A browser window is opening for Google sign-in. "
                        "This page reflects the result once you finish there."}

    @app.get("/api/outputs/google/connect")
    def api_google_connect_state():
        return getattr(app.state, "google_connect", {"status": "idle", "error": ""})

    @app.post("/api/outputs/google/push")
    def api_google_push(body: dict):
        keys = _source_keys(body)
        return _integration(google_push, keys, state_after=google_status)

    @app.post("/api/outputs/google/disconnect")
    def api_google_disconnect():
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                existed = google_disconnect(conn)
                conn.commit()
            finally:
                conn.close()
        app.state.google_connect = {"status": "idle", "error": ""}
        return {"disconnected": existed,
                "detail": "Signed out. Nothing in Drive was changed or removed."}

    # ---- storage and retention (spec 17/18/25) -----------------------------
    # Everything that can rewrite the warehouse lives here and nowhere else, so
    # a destructive control is never one stray click away inside a data screen.

    def _storage_action(run):
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                result = run(conn)
                conn.commit()
            except StorageRefused as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            finally:
                conn.close()
        return result.as_state()

    def _log_cutoff(conn) -> str:
        """The date before which job logs and change events may be removed.

        Driven by the Logs and diagnostics setting, because that is what the
        owner set it for — and because a diagnostic window has nothing to do
        with how long price history is kept.
        """
        from datetime import date, timedelta

        try:
            days = max(1, int(settings_get(conn, "log_retention_days")))
        except (TypeError, ValueError):
            days = 30
        return (date.fromisoformat(_today()) - timedelta(days=days)).isoformat()

    def _offers_with_history(conn, source_key: str) -> list[dict]:
        """Offers whose timeline has more than one period — the ones with a story.

        Bounded like every other read. An offer whose price has never moved has
        nothing to show on a CHANGES page, and listing it would bury the ones
        that do.
        """
        return [dict(r) for r in conn.execute(
            "SELECT so.offer_id, sp.source_name, so.region, "
            "       COUNT(pp.price_period_id) AS periods, "
            "       MAX(pp.last_confirmed_at) AS last_confirmed "
            "FROM price_period pp "
            "JOIN source_offer so ON so.offer_id = pp.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? GROUP BY so.offer_id "
            "HAVING COUNT(pp.price_period_id) > 1 "
            "ORDER BY periods DESC, sp.source_name LIMIT 50", (source_key,))]

    def _engine_rows() -> list[dict]:
        """Every connector family, with whether it is actually built.

        Read from the registry rather than a list in a template, so a family that
        lands tomorrow appears here without anyone remembering to add it.
        """
        used: dict[str, int] = {}
        for entry in app.state.manifest.sources:
            used[entry.family.value] = used.get(entry.family.value, 0) + 1
        return [{"name": family.value, "implemented": family in _BUILDERS,
                 "sources": used.get(family.value, 0)}
                for family in ConnectorFamily]

    def _about(conn) -> dict:
        from .. import __version__
        from ..connectors.base import DEFAULT_USER_AGENT
        from ..contract import CONTRACT_VERSION
        from ..jobs import worker_is_alive

        return {
            "version": __version__,
            "contract_version": CONTRACT_VERSION,
            "schema_version": dbmod.schema_version(conn),
            "worker_alive": worker_is_alive(conn),
            "default_user_agent": DEFAULT_USER_AGENT,
            "db_path": str(app.state.db_path),
            "log_entries": conn.execute(
                "SELECT COUNT(*) FROM job_log_entry").fetchone()[0],
        }

    def _policy_digest() -> str:
        conn = read_conn()
        try:
            return retention.policy_digest(retention.get_policies(conn))
        finally:
            conn.close()

    def _retention_view(conn) -> dict:
        policies = retention.get_policies(conn)
        # Diagnostics have their OWN window. Inheriting the price-history one
        # meant the default (ten years) offered to prune logs older than 2016 —
        # arithmetically right, and read by anyone as a bug.
        prune_before = _log_cutoff(conn)
        return {
            "policies": [
                {"source_key": p.source_key, "detail_days": p.detail_days,
                 "older_than_action": p.older_than_action, "excluded": p.excluded,
                 "action_label": retention.ACTIONS[p.older_than_action]}
                for p in sorted(policies.values(), key=lambda p: p.source_key)],
            "actions": retention.ACTIONS,
            "sources": retention.sources_with_data(conn),
            "protected": retention.protected_reasons(conn),
            "prunable": retention.prunable_counts(conn, prune_before),
            "prune_before": prune_before,
            "pins": retention.list_pins(conn, limit=50),
            "digest": retention.policy_digest(policies),
            "last": get_state(conn, "retention_last"),
            # Stated in the API itself, so no screen can imply otherwise.
            "promise": ("ScrapeX never deletes price history. A retention run copies "
                        "what you are keeping into a new database and seals the current "
                        "one beside it. Space is only freed once you delete that sealed "
                        "file yourself."),
            "prune_caveat": ("Change events are safe to remove while the observations "
                             "behind them are still here, because they can be "
                             "recomputed from them. After a summarising compaction they "
                             "cannot — so prune before you compact, not after."),
        }

    @app.get("/api/storage")
    def api_storage():
        conn = read_conn()
        try:
            return storage_status(conn, app.state.db_path)
        finally:
            conn.close()

    @app.post("/api/storage/backup")
    def api_storage_backup():
        return _storage_action(lambda conn: backup_now(conn, app.state.db_path))

    @app.post("/api/storage/restore")
    def api_storage_restore(body: dict):
        """Put a backup in place.

        Deliberately NOT run through _storage_action: that holds a connection to
        the very file restore has to move aside. On Windows an open handle makes
        the rename fail outright — so every restore returned a 500 — and it also
        risks letting the old WAL describe the new file. The writer lock is held,
        but no database connection is opened during the switch.
        """
        backup_path = (body or {}).get("backup_path", "")
        if not backup_path:
            raise HTTPException(status_code=400, detail="backup_path is required")
        # The worker holds its own connection for its whole life, and Windows
        # will not rename a file anyone has open. Giving up only THIS route's
        # connection was not enough.
        if app.state.runner is not None:
            app.state.runner.release_database()
        with dbmod.write_lock(app.state.db_path):
            try:
                result = restore(app.state.db_path, backup_path)
            except StorageRefused as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        return result.as_state()

    @app.post("/api/storage/open-folder")
    def api_storage_open_folder(body: dict):
        """Show a folder in the file manager. `which` picks WHICH folder, so a
        caller can never hand this an arbitrary path from the page."""
        which = (body or {}).get("which", "database")
        conn = read_conn()
        try:
            folders = {
                "database": Path(app.state.db_path).parent,
                "backups": backup_folder(conn, app.state.db_path),
                "exports": excel_status(conn)["folder"],
            }
        finally:
            conn.close()
        if which not in folders:
            raise HTTPException(status_code=400,
                                detail=f"which must be one of {sorted(folders)}")
        try:
            return open_folder(folders[which]).as_state()
        except StorageRefused as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/storage/repair")
    def api_storage_repair():
        return _storage_action(lambda conn: repair(app.state.db_path))

    @app.post("/api/storage/compact")
    def api_storage_compact():
        return _storage_action(lambda conn: storage_compact(conn, app.state.db_path))

    @app.post("/api/storage/export")
    def api_storage_export(body: dict):
        folder = (body or {}).get("folder", "")
        if not folder:
            raise HTTPException(status_code=400, detail="folder is required")
        return _storage_action(
            lambda conn: export_database(conn, app.state.db_path, folder))

    @app.post("/api/storage/check-move")
    def api_storage_check_move(body: dict):
        """Every refusal and warning, decided before anything is written."""
        folder = (body or {}).get("folder", "")
        if not folder:
            raise HTTPException(status_code=400, detail="folder is required")
        check = check_move(app.state.db_path, folder)
        return {"ok": check.ok, "reason": check.reason, "warning": check.warning}

    @app.post("/api/storage/move")
    def api_storage_move(body: dict):
        folder = (body or {}).get("folder", "")
        if not folder:
            raise HTTPException(status_code=400, detail="folder is required")
        result = _storage_action(lambda conn: migrate_location(app.state.db_path, folder))
        # The pointer moved, so this process follows it. Otherwise the server
        # keeps writing to a file the owner has been told is no longer live.
        app.state.db_path = str(resolve_db_path())
        if app.state.databases is not None:
            app.state.databases = DatabaseRegistry(
                app.state.databases.general,
                MarketLensDatabase(app.state.db_path),
                app.state.databases.legacy_path,
                app.state.databases.pointer_file,
            )
            app.state.databases.write()
        return result

    @app.get("/api/retention")
    def api_retention():
        conn = read_conn()
        try:
            return _retention_view(conn)
        finally:
            conn.close()

    @app.post("/api/retention/policy")
    def api_retention_policy(body: dict):
        body = body or {}
        source_key = body.get("source_key") or retention.DEFAULT_KEY
        try:
            with dbmod.write_lock(app.state.db_path):
                conn = _write_conn()
                try:
                    retention.save_policy(
                        conn, source_key,
                        detail_days=int(body.get("detail_days", 3650)),
                        older_than_action=body.get("older_than_action", retention.KEEP_ALL),
                        excluded=bool(body.get("excluded", False)))
                    conn.commit()
                    return _retention_view(conn)
                finally:
                    conn.close()
        except (retention.PolicyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/retention/preview")
    def api_retention_preview():
        """Measure a real rebuild. Slow on a big warehouse, and true."""
        conn = read_conn()
        try:
            result = compaction.preview(conn, app.state.db_path, today=_today())
        except compaction.CompactionAborted as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            conn.close()
        return {**result.as_state(),
                "observations_before": result.observations_before,
                "observations_after": result.observations_after,
                "observations_left_behind": result.observations_left_behind,
                "protected_count": result.protected_count,
                "bytes_before": result.bytes_before, "bytes_after": result.bytes_after,
                "problems": result.problems, "digest": _policy_digest()}

    @app.post("/api/retention/compact")
    def api_retention_compact(body: dict):
        digest = (body or {}).get("digest", "")
        if not digest:
            raise HTTPException(
                status_code=400,
                detail="Run a preview first: a compaction is only authorised by the "
                       "numbers you were actually shown.")
        # The lock spans build, verify and switch. An observation committed in
        # between would land in the file about to be sealed, and be unreachable
        # from the database that is live a moment later.
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                result = compaction.compact_warehouse(
                    conn, app.state.db_path, today=_today(), expected_digest=digest)
            except compaction.CompactionAborted as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            finally:
                conn.close()
        app.state.db_path = str(resolve_db_path())
        if app.state.databases is not None:
            app.state.databases = DatabaseRegistry(
                app.state.databases.general,
                MarketLensDatabase(app.state.db_path),
                app.state.databases.legacy_path,
                app.state.databases.pointer_file,
            )
            app.state.databases.write()
        return {**result.as_state(), "sealed_path": result.sealed_path,
                "observations_after": result.observations_after}

    @app.post("/api/retention/prune")
    def api_retention_prune(body: dict):
        """Remove old derived rows in place. Never touches an observation."""
        before_date = (body or {}).get("before_date", "")
        if not before_date:
            raise HTTPException(status_code=400, detail="before_date is required")
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                removed = retention.prune_derived(conn, before_date)
                conn.commit()
            finally:
                conn.close()
        return {"removed": removed, "ok": True,
                "detail": "Removed " + ", ".join(f"{n:,} {t}" for t, n in removed.items())
                          + ". No price observation was touched."}

    # ---- price history (spec: price-history storage semantics) --------------

    @app.get("/api/prices/timeline")
    def api_price_timeline(offer_id: int, limit: int = 200):
        """The first price and each real change. Unchanged confirmations are not
        history rows and do not appear here."""
        conn = read_conn()
        try:
            return {"offer_id": offer_id,
                    "periods": pricehistory.timeline(conn, offer_id, limit=limit)}
        finally:
            conn.close()

    @app.get("/api/prices/on")
    def api_price_on(offer_id: int, date: str):
        """What an offer cost on a date — and, when nothing confirms that date,
        what is actually known instead."""
        conn = read_conn()
        try:
            return pricehistory.price_on(conn, offer_id, date)
        finally:
            conn.close()

    @app.post("/api/prices/rebuild")
    def api_price_rebuild(body: dict):
        """Rebuild the derived timeline. Safe by construction: it reads the
        append-only evidence and cannot alter it."""
        source_key = (body or {}).get("source_key") or None
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                result = pricehistory.rebuild_all(conn, source_key)
                conn.commit()
            finally:
                conn.close()
        return {**result, "detail":
                f"Rebuilt {result['periods']} price periods across "
                f"{result['offers']} offers from the stored observations."}

    @app.get("/api/records")
    def api_records(source_key: str, q: str = "", availability: str = "",
                    cursor: int = 0, limit: int = 25):
        """Compact, paginated records for the panel's Browse Data screen.

        Bounded like every other read (A8): the panel shows cards, never a table,
        so it asks for a page at a time and stops when next_cursor is null.
        """
        conn = read_conn()
        try:
            page = browse_observations(conn, source_key, search=q or None,
                                       availability=availability or None,
                                       offset=max(0, cursor), limit=max(1, min(limit, 100)))
        finally:
            conn.close()
        nxt = max(0, cursor) + len(page.rows)
        return {"source_key": source_key, "records": page.rows, "total": page.total,
                "next_cursor": nxt if nxt < page.total else None}

    @app.get("/api/changes")
    def api_changes(source_key: str | None = None, limit: int = 50):
        """What changed since last time (spec 15/20) — summary + a bounded feed."""
        conn = read_conn()
        try:
            summary = change_summary(conn, source_key) if source_key else {}
            feed = recent_changes(conn, source_key, limit=limit)
        finally:
            conn.close()
        return {"source_key": source_key, "summary": summary, "changes": feed}

    # ---- jobs (spec 4/23/24: the panel enqueues and polls, never executes) ---

    @app.post("/api/jobs")
    def api_create_job(body: dict):
        body = body or {}
        source_keys = body.get("source_keys") or []
        if isinstance(source_keys, str):
            source_keys = [source_keys]
        if not source_keys:
            raise HTTPException(status_code=400, detail="source_keys is required")
        for key in source_keys:  # fail before queueing, not mid-crawl
            try:
                app.state.manifest.get(key)
            except KeyError:
                raise HTTPException(status_code=404, detail=f"unknown source_key {key!r}")
        try:
            run_mode = RunMode(body.get("run_mode", RunMode.UPDATE.value))
        except ValueError:
            raise HTTPException(status_code=400, detail="run_mode must be "
                                f"{[m.value for m in RunMode]}")
        conn = read_conn()
        try:
            dbmod.migrate(conn)
            job_ref = create_job(conn, source_keys, run_mode)
        finally:
            conn.close()
        return {"job_ref": job_ref, "status": "queued", "source_keys": source_keys,
                "run_mode": run_mode.value}

    @app.get("/api/jobs")
    def api_list_jobs(limit: int = 20, active_only: bool = False):
        conn = read_conn()
        try:
            jobs = list_jobs(conn, limit=limit, active_only=active_only)
        finally:
            conn.close()
        return {"jobs": [_job_view(j) for j in jobs]}

    @app.get("/api/jobs/{job_ref}")
    def api_get_job(job_ref: str):
        conn = read_conn()
        try:
            job = get_job(conn, job_ref)
        finally:
            conn.close()
        if job is None:
            raise HTTPException(status_code=404, detail=f"unknown job {job_ref!r}")
        return _job_view(job)

    @app.post("/api/jobs/{job_ref}/control")
    def api_control_job(job_ref: str, body: dict):
        try:
            control = JobControl((body or {}).get("control", ""))
        except ValueError:
            raise HTTPException(status_code=400, detail="control must be "
                                f"{[c.value for c in JobControl]}")
        conn = read_conn()
        try:
            if get_job(conn, job_ref) is None:
                raise HTTPException(status_code=404, detail=f"unknown job {job_ref!r}")
            applied = set_control(conn, job_ref, control)
            job = get_job(conn, job_ref)
        finally:
            conn.close()
        if not applied:  # already finished — a control request is meaningless
            raise HTTPException(status_code=409,
                                detail=f"job {job_ref!r} is {job['status']}")
        return _job_view(job)

    @app.get("/api/jobs/{job_ref}/logs")
    def api_job_logs(job_ref: str, limit: int = 200):
        conn = read_conn()
        try:
            if get_job(conn, job_ref) is None:
                raise HTTPException(status_code=404, detail=f"unknown job {job_ref!r}")
            entries = job_logs(conn, job_ref, limit=min(max(limit, 1), 200))
        finally:
            conn.close()
        return {"job_ref": job_ref, "entries": entries}

    @app.post("/api/capture")
    def api_capture(body: dict):
        source_key = (body or {}).get("source_key")
        if not source_key:
            raise HTTPException(status_code=400, detail="source_key is required")
        try:
            entry = app.state.manifest.get(source_key)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown source_key {source_key!r}")
        try:
            with dbmod.write_lock(app.state.db_path):
                conn = dbmod.connect(app.state.db_path)
                try:
                    dbmod.migrate(conn)
                    result = capture_source(conn, entry)
                    conn.commit()
                finally:
                    conn.close()
        except dbmod.DbLockedError:
            raise HTTPException(status_code=409,
                                detail="a crawl is already running — try again shortly")
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc))
        r = result.ingest
        return {
            "source_key": r.source_key, "run_id": r.run_id, "status": r.status.value,
            "observations": r.observations, "duplicates": r.duplicates,
            "products": r.products, "variants": r.variants,
            "requests": result.requests_count, "errors": len(r.errors),
        }

    return app


def _is_implemented(entry) -> bool:
    return entry.family in _BUILDERS


def _job_view(job: dict) -> dict:
    """The shape the side panel polls: aggregated progress only (spec 25) — never
    raw records, and everything needed to redraw the mini-player from scratch
    after the panel was closed."""
    total = job.get("progress_total") or 0
    done = job.get("progress_done") or 0
    return {
        "job_ref": job["job_ref"],
        "status": job["status"],
        "run_mode": job["run_mode"],
        "source_keys": job["source_keys"],
        "current_source_key": job["current_source_key"],
        "stage": job["stage"],
        "progress": {"done": done, "total": total,
                     "percent": round(done / total * 100) if total else 0},
        "counters": job["counters"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "last_heartbeat_at": job["last_heartbeat_at"],
        "error_summary": job["error_summary"],
    }


def _today() -> str:
    """Today's date, as the retention cutoffs measure from.

    A single function so a test can freeze it, rather than each caller reaching
    for the clock and drifting apart across a midnight boundary.
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()


def _source_keys(body: dict) -> list[str]:
    """Read source_keys/source_key off a request body, refusing an empty pick.

    Refusing here means a destination action can never be dispatched with an
    empty selection and then report a cheerful "0 rows written".
    """
    body = body or {}
    keys = body.get("source_keys") or body.get("source_key") or []
    keys = _csv(keys) if not isinstance(keys, list) else [str(k) for k in keys if str(k).strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="source_keys is required")
    return keys


def _csv(value) -> list[str]:
    """Accept a comma/space list or an actual list from the form."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").replace(",", " ").split() if part.strip()]


def _entry_from_form(form: dict) -> SourceEntry:
    """Build (and validate) a SourceEntry from the add-source form fields."""
    extract = {
        "kind": form.get("kind", ExtractKind.PRODUCT_PRICES.value),
        "scope": form.get("scope", ExtractScope.CENSUS.value),
    }
    materials, regions = _csv(form.get("materials")), _csv(form.get("regions"))
    if materials:
        extract["materials"] = materials
    if regions:
        extract["regions"] = regions
    data = {
        "source_key": (form.get("source_key") or "").strip().upper(),
        "source_name": (form.get("source_name") or "").strip(),
        "base_url": (form.get("base_url") or "").strip(),
        "family": form.get("family"),
        "cadence": form.get("cadence", Cadence.DAILY.value),
        "authority": form.get("authority", Authority.SHOP.value),
        "fetcher": form.get("fetcher", Fetcher.HTTP.value),
        "default_region": (form.get("default_region") or "*").strip() or "*",
        "vat_mode": form.get("vat_mode", VatMode.INCLUSIVE.value),
        "active": bool(form.get("active", False)),
        "extract": [extract],
    }
    currency = (form.get("currency") or "").strip()
    if currency:
        data["currency"] = currency
    # Advanced blocks (spec 11): persisted rather than silently dropped, so the
    # form never collects something it then throws away.
    fallbacks = _csv(form.get("fallback_families"))
    if fallbacks:
        data["fallback_families"] = fallbacks
    if form.get("auth_required"):
        data["auth_required"] = True
    identity = {k: v for k, v in (form.get("identity") or {}).items() if v not in (None, "")}
    if identity:
        data["identity"] = identity
    return SourceEntry.model_validate(data)
