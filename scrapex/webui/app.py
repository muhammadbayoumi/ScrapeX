"""ScrapeX local web app: HTML browse UI + a JSON API for the Chrome extension.

Read routes go through reports.py (zero SQL in the web layer, DRY). The one
WRITE route (/api/capture) runs a connector + ingest under the DB write lock
(A10) — the extension triggers it but never parses anything itself; extraction
stays in the Python connectors.

Bound to 127.0.0.1 by the CLI — a local, single-machine surface.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import db as dbmod
from ..capture import capture_source
from ..config import MANIFEST_FILE, SourceEntry, load_manifest
from ..connectors.factory import _BUILDERS
from ..manifest_io import DuplicateSourceError, add_source
from ..probe import probe as probe_url
from ..reports import browse_observations, list_sources, source_summary
from ..vocab import Authority, Cadence, ConnectorFamily, ExtractKind, ExtractScope, Fetcher, VatMode

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
PAGE_SIZE = 50
AVAILABILITY_OPTIONS = ("in_stock", "out_of_stock", "unknown")


def create_app(db_path: Path | str, manifest_path: Path | str = MANIFEST_FILE) -> FastAPI:
    app = FastAPI(title="ScrapeX", docs_url=None, redoc_url=None)
    app.state.db_path = str(db_path)
    app.state.manifest_path = str(manifest_path)
    app.state.manifest = load_manifest(manifest_path)

    # The extension calls from a chrome-extension:// origin. Local-only server,
    # no credentials — permissive CORS is acceptable here (A9: still 127.0.0.1).
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    def read_conn():
        return dbmod.connect(app.state.db_path)

    # ---- HTML browse UI ----------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        conn = read_conn()
        try:
            sources = list_sources(conn)
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(request=request, name="overview.html",
                                          context={"sources": sources})

    @app.get("/source/{source_key}", response_class=HTMLResponse)
    def source(request: Request, source_key: str, q: str = "", availability: str = "", page: int = 1):
        page = max(1, page)
        conn = read_conn()
        try:
            summary = source_summary(conn, source_key)
            page_data = None
            if summary is not None:
                page_data = browse_observations(
                    conn, source_key, search=q or None, availability=availability or None,
                    offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE)
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(
            request=request, name="source.html",
            context={"summary": summary, "page_data": page_data, "source_key": source_key,
                     "q": q, "availability": availability, "page": page,
                     "availability_options": AVAILABILITY_OPTIONS},
            status_code=200 if summary is not None else 404)

    # ---- JSON API (the Chrome extension) -----------------------------------

    @app.get("/api/health")
    def api_health():
        conn = read_conn()
        try:
            n = len(list_sources(conn))
        finally:
            conn.close()
        return {"ok": True, "app": "scrapex", "sources_with_data": n}

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
            "rows": rows,
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
    return SourceEntry.model_validate(data)
