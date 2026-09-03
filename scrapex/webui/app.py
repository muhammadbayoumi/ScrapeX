"""ScrapeX local web app: HTML browse UI + a JSON API for the Chrome extension.

Read routes go through reports.py (zero SQL in the web layer, DRY). The one
WRITE route (/api/capture) runs a connector + ingest under the DB write lock
(A10) — the extension triggers it but never parses anything itself; extraction
stays in the Python connectors.

Bound to 127.0.0.1 by the CLI — a local, single-machine surface.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import (
    bundle,
    compaction,
    directories,
    directoryjob,
    localinbox,
    nativehost,
    pricehistory,
    provenance,
    rates,
    retention,
)
from .. import db as dbmod
from .. import version as engine_version
from ..capture import capture_source, crawl_settings
from ..changes import change_summary, changes_for_offer, recent_changes
from ..config import SourceEntry, load_manifest, resolve_manifest_path
from ..connectors.base import CrawlBlocked, HttpFetcher
from ..connectors.factory import _BUILDERS, supports_history
from ..databases import (
    DatabaseKindError,
    DatabaseMigrationError,
    DatabaseRegistry,
    DatabaseUnavailableError,
    EngineDatabase,
)
from ..extract import service as extract_service
from ..extract.api import create_extraction_router
from ..features import FeatureKey, is_enabled
from ..features import manifest as feature_manifest
from ..fields import (
    arranged,
    delete_view,
    ensure_fields,
    list_fields,
    list_views,
    promotable_attributes,
    reorder,
    reset_view,
    save_view,
    set_display_name,
    set_promotion,
    set_visibility,
    visible_columns,
)
from ..jobs import (
    JobRunner,
    create_job,
    get_job,
    job_log_count,
    job_logs,
    list_jobs,
    set_control,
    worker_health,
)
from ..localsheets import workbook_bytes
from ..manifest_io import DuplicateSourceError, add_source, remove_source, set_active, update_source
from ..matching import (
    ConflictError,
    Decision,
    decide,
    pending_reviews,
    suggest_for_source,
    undo_decision,
)
from ..outputs import (
    NotConfiguredError,
    all_destinations,
    apps_script_script_text,
    apps_script_send,
    apps_script_status,
    apps_script_test,
    excel_export,
    excel_status,
    rotate_funnel_token,
)
from ..payload import utc_now_iso
from ..probe import probe as probe_url
from ..publish import workbook_tables
from ..reports import (
    BROWSE_COLUMNS,
    FILTERABLE,
    SORTABLE,
    SourceSummary,
    browse_columns,
    browse_google_finance_rates,
    browse_observations,
    column_presence,
    crawl_history,
    data_model_report,
    export_source_table,
    facet_options,
    google_finance_status,
    history_counts,
    list_sources,
    offer_identity,
    offer_observations,
    parse_filters,
    price_extremes,
    product_attributes,
    schema_report,
    table_payload,
    watch,
)
from ..scheduler import list_schedules, upsert_schedule, zone_exists
from ..settings import UnknownSettingError, get_state, public_settings
from ..settings import get as settings_get
from ..settings import save as save_settings
from ..sourceresolver import SourceResolver
from ..sources_admin import SourceKeyInUse, rename_source, source_footprint
from ..storage import (
    StorageRefused,
    backup_folder,
    backup_now,
    check_move,
    export_database,
    migrate_location,
    open_folder,
    reconcile_active,
    repair,
    resolve_db_path,
    restore,
    start_fresh,
    storage_status,
    wipe_source,
)
from ..storage import compact as storage_compact
from ..storage import list_backups as storage_list_backups
from ..ui_manifest import ui_manifest, workspace_navigation_groups
from ..vocab import (
    TERMINAL_JOB_STATUSES,
    Authority,
    Cadence,
    ConnectorFamily,
    ExtractKind,
    ExtractScope,
    Fetcher,
    JobControl,
    JobStatus,
    MissedRunPolicy,
    OverlapPolicy,
    RunMode,
    ScheduleFrequency,
    VatMode,
)
from .catalog_api import create_catalog_router
from .database_api import create_database_router, create_domain_health_router
from .update_api import create_update_router

#: The appearance registry, server side, and it MUST agree with the Map in
#: `design/appearance.js`. Two surfaces cannot import from each other at
#: runtime, so agreement is asserted by a test rather than achieved by sharing:
#: `tests/test_the_appearance_registry_agrees_across_both_surfaces.py` parses the
#: JavaScript and compares it with these two names, because the failure mode of a
#: divergence is silent in a way that is worth spelling out.
#:
#: WHAT USED TO HAPPEN WHEN THESE DISAGREED, measured on this code: the panel
#: POSTs the new palette, this function raises 400, and `pushRemote` in
#: appearance.js returns `response.ok` from inside a try block whose value both
#: call sites discard -- so nothing is reported. Meanwhile `pullRemote` keeps
#: succeeding, because GET answers 200 with `{"appearance": null}`, which resets
#: `consecutiveFailures` on every tick and means the QUIET_AFTER_FAILURES backoff
#: never engages. The result is a 2-second write loop that runs for as long as the
#: panel is open, tells the user nothing, and never persists their choice.
#:
#: R-59 decision 3: `whatsapp` and `github` are legacy compatibility ALIASES for
#: `brand` and `blue`. Before R-73 this function enforced only the aliases while
#: the registry they alias did not exist -- OP-82, now closed. Both spellings are
#: accepted here because every appearance stored before 2026-08-28 uses the old
#: one, and the value is canonicalised on the way in so the warehouse ends up
#: holding one name per palette rather than two.
APPEARANCE_PALETTES = ("brand", "blue", "supabase")
APPEARANCE_PALETTE_ALIASES = {"whatsapp": "brand", "github": "blue"}


def _appearance_value(body: dict | None) -> dict:
    """Validate the small cross-surface appearance contract.

    Keeping this allowlist at the boundary prevents an old or modified extension
    from persisting arbitrary CSS values for the Workspace to consume.
    """
    candidate = body if isinstance(body, dict) else {}
    mode = candidate.get("mode")
    scheme = candidate.get("scheme")
    palette = candidate.get("palette")
    device_colors = candidate.get("deviceColors")
    updated_at = candidate.get("updatedAt")
    if mode not in {"manual", "device"}:
        raise HTTPException(status_code=400, detail="mode must be manual or device")
    if scheme not in {"light", "dark"}:
        raise HTTPException(status_code=400, detail="scheme must be light or dark")
    palette = APPEARANCE_PALETTE_ALIASES.get(palette, palette)
    if palette not in APPEARANCE_PALETTES:
        raise HTTPException(
            status_code=400,
            detail="palette must be one of " + ", ".join(APPEARANCE_PALETTES))
    if not isinstance(device_colors, bool):
        raise HTTPException(status_code=400, detail="deviceColors must be true or false")
    if isinstance(updated_at, bool) or not isinstance(updated_at, (int, float)) or updated_at < 0:
        raise HTTPException(status_code=400, detail="updatedAt must be a positive timestamp")
    return {
        "mode": mode,
        "scheme": scheme,
        "palette": palette,
        "deviceColors": device_colors,
        "updatedAt": int(updated_at),
    }


def _google_finance_setting_values(body: dict) -> dict:
    """Validate and canonicalise the two public rate-control settings."""
    values = dict(body or {})
    if "google_finance_auto_refresh" in values:
        raw = values["google_finance_auto_refresh"]
        accepted = isinstance(raw, (bool, int, str)) and raw in {
            True, False, "0", "1", "true", "false",
        }
        if not accepted:
            raise HTTPException(
                status_code=400,
                detail="google_finance_auto_refresh must be true or false",
            )
        values["google_finance_auto_refresh"] = (
            "1" if raw in {True, "1", "true"} else "0"
        )
    if "google_finance_refresh_hours" in values:
        try:
            hours = float(values["google_finance_refresh_hours"])
        except (TypeError, ValueError):
            hours = math.nan
        if (not math.isfinite(hours)
                or not rates.MIN_REFRESH_HOURS <= hours <= rates.MAX_REFRESH_HOURS):
            raise HTTPException(
                status_code=400,
                detail=("google_finance_refresh_hours must be between "
                        f"{rates.MIN_REFRESH_HOURS:g} and "
                        f"{rates.MAX_REFRESH_HOURS:g}"),
            )
        values["google_finance_refresh_hours"] = f"{hours:g}"
    return values
def _time_zone_value(body: dict | None) -> dict:
    """Validate the shared display time zone (spec 33 §6.4).

    An unknown identifier is REFUSED rather than stored: a zone that cannot
    resolve here would show every timestamp in the fallback zone forever while
    the saved preference claimed otherwise, which is the one failure the owner
    could not diagnose from the screen. `zone_exists` is the scheduler's own
    check — the same tz database, so a zone that can be scheduled can be
    displayed and the two can never disagree.

    An empty string is valid and means "follow the zone each browser detects".
    """
    candidate = body if isinstance(body, dict) else {}
    zone = candidate.get("zone")
    updated_at = candidate.get("updatedAt")
    if zone is None:
        zone = ""
    if not isinstance(zone, str):
        raise HTTPException(status_code=400, detail="zone must be an IANA identifier")
    zone = zone.strip()
    if zone and not zone_exists(zone):
        raise HTTPException(
            status_code=400,
            detail=f"{zone!r} is not a known IANA time zone identifier")
    if isinstance(updated_at, bool) or not isinstance(updated_at, (int, float)) \
            or updated_at < 0:
        raise HTTPException(status_code=400, detail="updatedAt must be a positive timestamp")
    return {"zone": zone, "updatedAt": int(updated_at)}


def database_state(request: Request) -> dict:
    """Runtime status for every page, derived from the request's own app.

    A context processor rather than a template global: the state is read from
    `request.app.state`, so two apps in one test process cannot report each
    other's databases.

    Every page carries it because the database is what every page is made of. A
    status the owner has to go looking for is a status they find out about from
    a failure instead.
    """
    runner = getattr(request.app.state, "runner", None)
    try:
        engine_connected = bool(runner and runner.is_alive)
    except Exception:
        engine_connected = False
    runtime = {"engine_state": {"connected": engine_connected}}

    registry = getattr(request.app.state, "databases", None)
    if registry is None:
        return {**runtime, "db_state": None}
    try:
        states = registry.health()
    except Exception:
        return {**runtime, "db_state": None}
    failed = {kind: item for kind, item in states.items() if not item["ok"]}
    return {
        **runtime,
        "db_state": {"ok": not failed, "all": states, "failed": failed},
    }


TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"),
                            context_processors=[database_state])


def _source_domain(value: str | None) -> str:
    """Presentation-only host label: no scheme, path, credentials, port, or www."""
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").strip(".")
    return host[4:] if host.lower().startswith("www.") else host


def _dataset_freshness(conn, dataset_id: int) -> dict | None:
    """A dataset's freshness in the shape both source surfaces already read.

    THE FIELD NAMES ARE `ingest.last_successful_run`'s, ON PURPOSE, and one of
    them earns a word. `started_at` is what `freshnessLine` (extension/app.js)
    and `_source_list.html` print after *"Last crawled"*, so it holds the NEWEST
    capture. For a price run that instant is when the run began, because the run
    and its ingest are one transaction; the generic pipeline separates fetching
    from interpreting by design (docs/GENERIC-FETCH-SEAM.md), so there is no run
    interval to report and the honest instant is the last moment a page arrived.
    Its oldest page would understate the freshness by the length of the crawl —
    on his `contractors` dataset, by a day and twelve hours.

    AND IT CARRIES NO MEASURE BESIDE THE DATE, WHICH IS A DECISION. Both
    surfaces print `rows_seen` after the date, then fall back to
    `requests_count`; a dataset has an honest number for neither.

    * **Not `rows_seen`.** The obvious candidate is the dataset's own row count —
      and *seen* already means something else in this warehouse. `dataset_sighting`
      is *what the site showed us*, and on his `contractors` the two differ:
      **17,417 sighted against 17,304 stored**. Printing the stored count under
      the word `seen` would put a wrong answer to a question this schema can
      answer exactly. The card states the count on its own line anyway.
    * **Not `requests_count`.** The stored pages behind a dataset are not the
      requests its crawl spent: retries, 304s and the Arabic half of every
      muqawil page are all requests that leave no second row.

    So both stay 0, which `last_successful_run` already documents as an absence
    rather than a measurement of zero, and the line reads *"Last crawled …"* and
    stops.

    None when nothing has ever been ingested. The card then says "no successful
    crawl yet", which at that point is true.
    """
    captured_at = extract_service.last_evidence_captured_at(conn, dataset_id)
    if not captured_at:
        return None
    return {"started_at": captured_at, "finished_at": captured_at,
            "rows_seen": 0, "requests_count": 0,
            "products_discovered": 0, "errors_count": 0}


TEMPLATES.env.filters["source_domain"] = _source_domain
# The sidebar renders from the shared UI contract (scrapex/ui_manifest.py) —
# the same module /api/ui serves to the panel, so the surfaces cannot drift.
TEMPLATES.env.globals["workspace_navigation_groups"] = workspace_navigation_groups
# The job-status vocabulary reaches the templates from vocab.py rather than being
# re-typed in each of them. Four hand-copied sets had accumulated - two JS Sets
# used as polling stop-conditions and two Jinja tuples - and a status added to
# JobStatus but forgotten in one copy makes that page poll a finished job every
# eight seconds forever while painting the wrong badge. Exactly that happened
# once already, when completed_with_errors was introduced (migration 0020).
TEMPLATES.env.globals["TERMINAL_JOB_STATUSES"] = sorted(
    status.value for status in TERMINAL_JOB_STATUSES)
TEMPLATES.env.globals["UNCLEAN_JOB_STATUSES"] = sorted(
    status.value for status in TERMINAL_JOB_STATUSES if status is not JobStatus.COMPLETED)
STATIC_DIR = Path(__file__).parent / "static"
PAGE_SIZE = 50
AVAILABILITY_OPTIONS = ("in_stock", "out_of_stock", "unknown")
# The page sizes offered. The largest is the cap browse_observations already
# enforces (reports.py) — offering a number the server would silently clamp
# would be a lie told by a dropdown.
PER_PAGE_OPTIONS = (25, 50, 100, 200)

# ---- who may talk to this engine ---------------------------------------------
# Binding to 127.0.0.1 keeps the port off the network. It does NOT keep the port
# away from the internet: every page the owner opens runs inside the browser that
# can reach it, so any site could fetch() this API. That is why the origin is
# checked here rather than trusted.

# Chrome extension ids are 32 characters drawn from a-p.
_ANY_EXTENSION = r"^chrome-extension://[a-p]{32}$"
# Hosts a loopback URL can carry. A DNS-rebinding page resolves its OWN name to
# 127.0.0.1 and so arrives with `Host: attacker.example`, which is refused.
# "testserver" is Starlette's TestClient default and resolves nowhere.
LOOPBACK_HOSTS = ["127.0.0.1", "localhost", "::1", "testserver"]


def allowed_extension_ids() -> list[str]:
    """The extension ids the native-messaging manifest already trusts.

    Reusing that file means there is ONE allowlist deciding which extension may
    drive this machine, instead of a second one here to keep in step with it —
    and the READER of it lives beside the file too, for the same reason: this
    module used to carry its own copy of the parsing.
    """
    return nativehost.allowed_extension_ids()


def extension_origin_regex() -> str:
    """One pattern, used both to answer CORS and to refuse everything else.

    With no manifest the owner has not run the one-time installer yet — a state
    transport.js deliberately supports — so any extension origin is accepted and
    every web origin is still refused. That leaves the attack that mattered
    closed (a page on the internet reaching this port) without stranding a panel
    whose engine is reachable only over HTTP.
    """
    ids = allowed_extension_ids()
    if not ids:
        return _ANY_EXTENSION
    return r"^chrome-extension://(%s)$" % "|".join(re.escape(i) for i in sorted(set(ids)))


class RefuseForeignOrigins(BaseHTTPMiddleware):
    """Refuse a browser origin that is not the extension, BEFORE any handler.

    CORS alone is not enough: the browser blocks the attacker from READING the
    reply, but the request has already run by then — and the routes that matter
    here are writes (start-fresh, restore, settings, native-host/register), where
    doing the work IS the damage. A request with no Origin header at all is the
    engine's own pages and local tools, and is left alone.
    """

    # The one exception, and why it has to exist: when the helper's allowlist no
    # longer names this extension — a reload from another folder gives it a new
    # id — the panel repairs that by posting its own id to the re-link route. Held
    # to the same stale allowlist, the repair would be locked out by the exact
    # fault it repairs, and the owner would be left with a dead panel and no
    # route back. Any EXTENSION may reach it. No web page can.
    RELINK_PATH = "/api/native-host/register"

    def __init__(self, app, pattern: str) -> None:
        super().__init__(app)
        self._pattern = re.compile(pattern)
        self._any_extension = re.compile(_ANY_EXTENSION)

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        pattern = (self._any_extension if request.url.path == self.RELINK_PATH
                   else self._pattern)
        # Browsers include Origin on same-origin writes as well as cross-origin
        # requests. The engine's own page is safe only when its scheme, host and
        # port match this request exactly; TrustedHostMiddleware independently
        # guarantees that this Host is loopback before the request reaches us.
        engine_origin = f"{request.url.scheme}://{request.url.netloc}"
        is_engine_page = origin == engine_origin
        if origin and not is_engine_page and not pattern.fullmatch(origin):
            return JSONResponse(
                status_code=403,
                content={"detail": "This engine answers its own pages and the ScrapeX "
                                   "extension only. A page from another site may not "
                                   "drive the warehouse on this machine."})
        return await call_next(request)


def create_app(
    db_path: Path | str | None = None,
    # None, not MANIFEST_FILE: a default evaluated at import time cannot see
    # `SCRAPEX_SOURCES`, so the running engine read the repository's own twelve
    # shops whatever the environment said, and no test could drive it against a
    # shop it controls. `load_manifest(None)` resolves the variable, then the
    # repository file. An explicit path still wins over both.
    manifest_path: Path | str | None = None,
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
        price_path = databases.engine.path
        general_database = databases.engine
    else:
        price_path = Path(db_path)  # explicit legacy-compatible test/session path
        # One database now, so the generic half is the same file as the price
        # half. `general_db_path` survives only as a legacy test/session knob
        # and names an engine database like any other.
        general_database = EngineDatabase(general_db_path) if general_db_path else None
        if general_database is not None:
            general_database.initialize()
    app = FastAPI(title="ScrapeX", docs_url=None, redoc_url=None)
    app.state.db_path = str(price_path)
    app.state.databases = databases
    app.state.general_database = general_database
    # RESOLVED TO A CONCRETE PATH, and not left as None: `set_active`,
    # `add_source`, `update_source` and `remove_source` are all handed this value
    # and all four default to MANIFEST_FILE, so a None reaching them becomes
    # `Path(None)` — every source edit in the panel would raise. Resolving once,
    # here, also means every later reload reads the same file this one did.
    app.state.manifest_path = str(resolve_manifest_path(manifest_path))
    app.state.manifest = load_manifest(app.state.manifest_path)

    def _follow_the_manifest() -> list[str]:
        """Write the manifest's `active` into the warehouse. Returns what moved.

        THE MANIFEST IS THE DEFINITION; THE WAREHOUSE IS THE CONSEQUENCE. An
        inactive source is never crawled, so its stored flag is never touched by
        a crawl either — which is exactly how the database came to claim all
        twelve sources were live while sources.yaml had five switched off.

        CALLED FROM EVERY PATH THAT RELOADS THE MANIFEST, and that is the fix
        rather than the reconciliation itself, which already existed. It had one
        caller: the panel's active toggle. So the warehouse followed the manifest
        only when the owner used that one control, and drifted silently whenever
        sources.yaml changed any other way — an edit by hand, an add, a rename, a
        remove, or a `git checkout`.

        That last one is not hypothetical. BACKLOG OP-2 records a manifest edit
        that existed on one machine, was reverted by a checkout, and went
        unnoticed for eleven days.

        Nothing reads the stored flag to decide a crawl — the scheduler reads the
        manifest — so this repairs no behaviour. It repairs what the owner's own
        database SAYS, which is what he queries, exports, and will read from the
        Console.
        """
        conn = read_conn()
        try:
            return sorted(reconcile_active(conn))
        except Exception:
            # A warehouse that cannot be reconciled is a warehouse health
            # already reports on. Refusing to start over it would be worse.
            return []
        finally:
            conn.close()

    # The job worker owns ALL long-running crawls (spec 4). Tests drive the
    # synchronous seam instead, so the thread is opt-in.
    # The worker follows the warehouse: a move or a compaction changes
    # app.state.db_path, and a worker still holding the old file would crawl
    # into a database nothing else reads.
    # `R-78`: THE SCHEDULER RESOLVES A SOURCE THROUGH THE REGISTRY, NOT A FILE.
    # This is the whole wire. `SourceResolver` answers `.get(key)` for the manifest
    # first and `source_site` second, and it is duck-compatible with `Manifest` on
    # purpose -- `jobs.py` takes the manifest as a bare object and calls `.get`, so
    # passing a resolver here needs NO change to the scheduler and a contractor source
    # inherits host lanes, cross-job admission, pause/resume and per-source failure
    # isolation, none of which the CLI path has.
    app.state.runner = JobRunner(
        str(price_path),
        lambda: SourceResolver(app.state.manifest, lambda: dbmod.connect(app.state.db_path)),
        path_provider=lambda: app.state.db_path) if start_worker else None
    # Start the worker only after every route has been registered. The final
    # boundary below keeps app construction out of the orphan-resume race.

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # "Local-only" was never a boundary. Every page the owner browses runs in the
    # same browser that can reach 127.0.0.1, so allow_origins=["*"] handed every
    # site on the internet this engine's whole command surface: one fetch() to
    # POST /api/storage/start-fresh wipes the warehouse, /api/native-host/register
    # re-points the helper's allowlist, /api/outputs/apps-script/token mints the
    # funnel token AND — with the wildcard — lets the calling page read it back.
    #
    # A web origin is now refused before any handler runs. The extension is not:
    # its own id is read from the native-messaging manifest, the file that
    # already decides which extension may drive this machine, so there is one
    # allowlist rather than a second one to keep in step.
    origin_pattern = extension_origin_regex()
    # CORS answers any extension origin so the re-link route's reply is readable
    # by the panel that needs it; which origins may actually DO anything is
    # decided below, before a handler runs.
    app.add_middleware(
        CORSMiddleware, allow_origin_regex=_ANY_EXTENSION,
        allow_methods=["*"], allow_headers=["*"],
    )
    # Added last, so it runs first: a refused origin never reaches a handler.
    app.add_middleware(RefuseForeignOrigins, pattern=origin_pattern)
    # And the Host header, against DNS rebinding — Starlette's own, not a
    # hand-rolled check (X8: the dependency already ships one).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOOPBACK_HOSTS)

    if databases is not None:
        app.include_router(create_database_router(lambda: app.state.databases))
        app.include_router(create_domain_health_router(lambda: app.state.databases))

    # UNCONDITIONAL, unlike the two above. Update is the one surface that has to
    # answer when everything else is broken: a database this build cannot open is
    # a reason to want a newer engine, not a reason to hide the way to get one.
    # It touches no database at all -- see scrapex/webui/update_api.py.
    app.include_router(create_update_router())

    # A database can become unusable while the engine is running: a drive is
    # unplugged, a file is replaced, a schema stops being the one this build
    # reads. Every page then opened a connection and threw, so the owner met a
    # stack trace instead of the status — the exact opposite of a notification.
    # Serving the status is not "hiding an error": nothing is written and no
    # request succeeds; the page just says which database, what state, what to do.
    def _database_unavailable(request: Request, exc: Exception):
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                {"ok": False, "error": "database_unavailable", "detail": str(exc)},
                status_code=503,
            )
        return TEMPLATES.TemplateResponse(
            request=request, name="database_unavailable.html",
            context={"tab": None, "source_key": None, "detail": str(exc)},
            status_code=503,
        )

    for failure in (DatabaseUnavailableError, DatabaseMigrationError, DatabaseKindError):
        app.add_exception_handler(failure, _database_unavailable)

    def read_conn():
        if app.state.databases is not None:
            return app.state.databases.engine.connect()
        return dbmod.connect(app.state.db_path)

    # AT STARTUP, and here rather than beside the manifest load thirty lines
    # above: `_follow_the_manifest` closes over `read_conn`, which is defined on
    # the line above this one. Calling it earlier raised
    # "cannot access free variable 'read_conn'" — a closure reads its enclosing
    # scope when it RUNS, and at that point the name was still unbound.
    #
    # This is the only path that notices a manifest changed outside the panel:
    # an edit by hand, a restore, or a `git checkout` that reverts one.
    _follow_the_manifest()

    def ensure_schema(conn) -> None:
        """Migrate ONLY a legacy single-file warehouse.

        A registry database has its own numbered migration stream and was
        already migrated when it was created. Running the unified stream over it
        re-applies migration 1 and dies on "table offer_state already exists" —
        which is what happened the moment the owner pressed Run, because two
        request paths called dbmod.migrate() unconditionally.

        One helper rather than a check at each call site: the next route that
        needs a writable connection should not have to remember this.
        """
        if app.state.databases is None:
            dbmod.migrate(conn)

    def general_read_conn():
        if app.state.general_database is None:
            return read_conn()
        return app.state.general_database.connect()

    # ---- HTML browse UI ----------------------------------------------------

    def _display_sources(conn):
        """Warehouse counts with the manifest's current display identity."""
        sources = list_sources(conn)
        entries = {entry.source_key: entry for entry in app.state.manifest.sources}
        for source in sources:
            entry = entries.get(source.source_key)
            if entry is None:
                continue
            source.source_name = entry.source_name or source.source_name
            source.source_name_ar = entry.source_name_ar or source.source_name_ar
            source.base_url = entry.base_url or source.base_url
        return sources

    def _dataset_rows():
        """Every approved dataset, in the shape a source listing already speaks.

        ONE QUERY, TWO READERS, and the reason is a bug that shipped. `/api/sources`
        learned about datasets in #212 and the PAGE did not — so
        `/source/contractors` answered 404 while `/api/table/contractors` served
        11,059 rows to nobody at all. Copying the query into the page would have
        left the next widening to drift the same way.

        `kind` MARKS THEM, and the panel needs it: the row menu offers Update,
        Wipe and Rename, and every one of those is a price-path action that would
        answer 400 or worse for a dataset. A button that cannot work is worse
        than no button, so the panel hides them on this marker.

        AND THIS IS THE CALLER `is_enabled` WAS WRITTEN FOR. That function describes
        itself as *"the gate that NAVIGATION and UI must call before advertising a
        capability"* and it had **zero callers anywhere** — so `GENERIC_DATASET_CATALOG`
        being lit was a CLAIM about a capability rather than a switch over it, and
        turning it off would have changed nothing at all.

        THIS FUNCTION IS THE ADVERTISEMENT. It is what puts a dataset in the source
        listing the panel draws, which is precisely *telling a user the capability
        exists* — the claim `is_enabled`'s docstring says spec section 40 forbids
        inflating. The ROUTES stay mounted whatever the flag says, deliberately and as
        that docstring requires: `/api/table/contractors` and `/source/contractors`
        exist so the slice can be exercised and tested on a server bound to 127.0.0.1.
        Gating the routes would make the flag a kill switch for development; gating the
        listing makes it a switch over what is announced.
        """
        if not is_enabled(FeatureKey.GENERIC_DATASET_CATALOG):
            return []
        general = general_read_conn()
        try:
            # READ WHOLE, THEN SHAPED. The freshness is a second query per
            # dataset, and running it inside the walk of this one would nest a
            # read in the middle of a GROUP BY scan for no gain — there are as
            # many datasets as a site has tables, and the aggregate above is
            # already the expensive half.
            catalogue = general.execute(
                "SELECT d.dataset_definition_id, d.dataset_key, d.display_name, "
                "s.source_key AS site_key, "
                "d.original_name, s.base_url, count(r.generic_record_id) AS rows "
                "FROM dataset_definition AS d "
                "JOIN source_site AS s "
                "ON s.source_id = d.source_id "
                "LEFT JOIN generic_record AS r "
                "ON r.dataset_definition_id = d.dataset_definition_id "
                "AND r.status = 'active' "
                "WHERE d.valid_to IS NULL GROUP BY d.dataset_definition_id"
            ).fetchall()
            return [{
                "kind": "dataset",
                "site_key": row["site_key"],
                "source_key": row["dataset_key"],
                "source_name": row["display_name"] or row["original_name"],
                "source_name_ar": "", "base_url": row["base_url"],
                "family": "generic", "active": True, "implemented": True,
                "supports_history": False,
                # `observations` is what the Data screen filters on, and for a
                # directory the honest number is its rows. `products` has no
                # meaning for a company, so it carries the same count rather
                # than a zero that would read as an empty dataset.
                #
                # THE PANEL NO LONGER READS THIS KEY FOR A DATASET, and the note
                # above now describes exactly one surviving reader: the engine's
                # own `/source/{key}` page, which fills `SourceSummary.products`
                # from it at line ~960 and prints it as a "Products" tile
                # (`templates/_source_overview.html`). So a contractor directory
                # still reads "Products 17,304" THERE — the same defect this
                # branch fixed on the panel, on the surface this branch did not
                # touch. Recorded as `OP-63` rather than fixed here, because
                # that page shows four tiles and two of them are meaningless for
                # a directory, which is a design question and not a noun.
                "observations": row["rows"], "products": row["rows"],
                # WHEN THE DATA ON SCREEN WAS GATHERED, and it is DERIVED rather
                # than recorded. The card printed "no successful crawl yet"
                # under 17,304 rows, because this key was the literal `None` and
                # `freshnessLine` says so in words when it is. A price source
                # gets it from `crawl_run`; a dataset can have no row there at
                # all — `crawl_run.source_id` is NOT NULL into `source_site` and
                # muqawil is in `source_site`, which is the split `REQ-25`
                # holds — so this reads the evidence the crawl already stored.
                # Same SHAPE as `ingest.last_successful_run`, deliberately: the
                # panel and `_source_list.html` both draw `last_success`, and a
                # second shape would be a second code path in each of them.
                "last_success": _dataset_freshness(
                    general, int(row["dataset_definition_id"])),
                "kept_pages": 0, "kept_at": None,
            } for row in catalogue]
        finally:
            general.close()

    def _dataset_listing():
        """The same datasets, as ONE CARD PER SITE. `R-47`, and `REQ-37` before it.

        HIS COMPLAINT, twice, with a screenshot each time: «المفروض مصدر مقاول يظهر
        مرة واحدة فقط واختيارات الزحف الخاصة به تكون متعغددة». The Data screen drew
        `muqawil.org` twice, once per `dataset_definition` row, and neither card knew
        the other existed.

        **ONLY THE PRESENTATION COLLAPSES, and that is the whole of `R-47`.** The two
        `dataset_definition` rows stay two — `contractors._approval` refuses to put a
        27-field profile and a 28-field listing under one approved schema, because a
        subset is what a broken parser looks like (`R-31`). So this folds the LISTING
        and `_dataset_rows` is left alone, which is not a stylistic split: it has a
        second caller. `/source/{key}` resolves ONE dataset out of it by key, so
        folding in place would have made `/source/contractor_profiles` answer 404
        again — the exact regression #212 was built to close.

        THE GROUPING KEY IS NOT THE SITE ALONE, and measuring it is what settled
        that. `REQ-37` names `source_id`, and both muqawil datasets do share
        one (id 2, `muqawil_org`) — but `R-47`'s own justification is narrower than
        the site: *"the join is the thing that makes the single card honest rather
        than a label over two unrelated tables."* Two datasets that happen to sit on
        one site and are NOT related are two populations, and one card over them
        would state a number nobody could act on. So the key is the site **plus a
        confirmed one-to-one relationship**, which is the thing he had already asked
        for by name — «اربطهم فى dataset_relationship» — and which is `confirmed` in
        his warehouse today.

        MEASURED READ-ONLY ON HIS WAREHOUSE, 2026-08-23:

            dataset_definition   1 contractors         source_id 2
                                 2 contractor_profiles source_id 2
            dataset_relationship parent 1, child 2, one_to_one, confirmed
            active rows          17,304 and 704

        AND `base_url` WOULD HAVE BEEN THE WRONG KEY, which only the measurement
        shows: `source_site` holds TWO muqawil rows — id 1 `https://muqawil.org/ar/
        contractors` and id 2 `https://muqawil.org/` — so the host is shared and the
        base URL is not. Grouping on the URL works today only because id 1 carries no
        datasets.

        WHAT IS NOT BUILT HERE, deliberately: the two crawl OPTIONS on the card,
        which is `R-47`'s third point. `POST /api/jobs` answers 404
        `unknown source_key 'contractors'` — measured, `OP-52` — so there is no panel
        path to a dataset crawl, and offering two menu entries that cannot run is the
        "button that cannot work is worse than no button" rule #258 built a guard
        for. The profile crawl reaches the card as COVERAGE instead, which is
        `R-47`'s second point and the number he actually wants.
        """
        rows = _dataset_rows()
        if len(rows) < 2:
            return rows
        general = general_read_conn()
        try:
            # CONFIRMED AND ONE-TO-ONE, both load-bearing. `review_status` is the
            # human gate — a proposed relationship is a guess, and collapsing two
            # cards on a guess would hide a population behind a percentage. And
            # `one_to_one` is what makes "704 of 17,304" a sentence: under
            # `one_to_many` a parent row can carry several children, so the child
            # count is not a fraction of the parent count at all.
            links = general.execute(
                "SELECT p.dataset_key AS parent, c.dataset_key AS child "
                "FROM dataset_relationship AS r "
                "JOIN dataset_definition AS p "
                "ON p.dataset_definition_id = r.parent_dataset_id "
                "JOIN dataset_definition AS c "
                "ON c.dataset_definition_id = r.child_dataset_id "
                "WHERE r.valid_to IS NULL AND r.review_status = 'confirmed' "
                "AND r.cardinality = 'one_to_one'"
            ).fetchall()
        finally:
            general.close()
        entries = {row["source_key"]: row for row in rows}
        parents = {link["parent"] for link in links}
        # A CHILD THAT IS ITSELF A PARENT KEEPS ITS OWN CARD. Folding it away would
        # take its own children off the listing with it, and a dataset that reaches
        # no card is worse than one that reaches a redundant card. One level, and the
        # limit is stated rather than discovered: nothing in the warehouse is two
        # deep today, and the day something is, its middle row stays visible.
        folded_into = {link["child"]: link["parent"] for link in links
                       if link["parent"] in entries and link["child"] in entries
                       and link["child"] not in parents}
        listing = []
        for row in rows:
            key = row["source_key"]
            if key in folded_into:
                continue
            children = [entries[child] for child, parent in folded_into.items()
                        if parent == key]
            if not children:
                listing.append(row)
                continue
            # THE SECOND NUMBER STOPS BEING A POPULATION. Today the cards read
            # 17,304 and 704 as if they were two populations; they are one —
            # 17,304 contractors, of whom 704 have an approved profile. A LIST
            # because a site may grow a second detail crawl, and one line each is
            # the shape that does not have to be rewritten when it does.
            listing.append(dict(row, coverage=[{
                "dataset_key": child["source_key"],
                # The child's own stored `display_name`, never a word of ours:
                # `R-45` — «ما يقوله الموقع هو مصدر الحقيقة الوحيد» — and this is
                # the label the approval recorded from the site.
                "label": child["source_name"],
                "stored": child["observations"],
                "population": row["observations"],
            } for child in children]))
        return listing

    def _source_catalog(conn):
        """Every configured source, split by whether it has warehouse data."""
        sources = _display_sources(conn)
        source_sites = {entry.source_key: entry.base_url
                        for entry in app.state.manifest.sources}
        known = {source.source_key for source in sources}
        pending = [
            # A source with no warehouse row yet has only the manifest to be
            # named from, so its English name comes from there too — otherwise
            # the "never run" half of the list would read Arabic-only while the
            # half above it reads both.
            {"source_key": key, "source_name": entry.source_name,
             "source_name_ar": entry.source_name_ar,
             "base_url": entry.base_url,
             "family": entry.family.value, "active": entry.active}
            for entry in sorted(app.state.manifest.sources, key=lambda item: item.source_key)
            for key in [entry.source_key]
            if key not in known
        ]
        return sources, pending, source_sites

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        conn = read_conn()
        try:
            sources, pending, _ = _source_catalog(conn)
            review_items = pending_reviews(conn, None, limit=200)
            schedules = list_schedules(conn)
            recent_jobs = [_job_view(job) for job in list_jobs(conn, limit=6)]
            active_jobs = [_job_view(job) for job in list_jobs(
                conn, limit=20, active_only=True)]
            changes = recent_changes(conn, None, limit=6)
        finally:
            conn.close()
        scheduled = [
            item for item in schedules
            if item.get("enabled")
            and (item.get("frequency") or "manual") != "manual"
        ]
        attention_sources = [
            source for source in sources
            if not source.last_run or source.last_status != "success"
        ]
        totals = {
            "configured": len(sources) + len(pending),
            "ready": len(sources),
            "products": sum(source.products for source in sources),
            "variants": sum(source.variants for source in sources),
            "observations": sum(source.observations for source in sources),
            "matched": sum(source.matched_variants for source in sources),
            "reviews": len(review_items),
            "reviews_capped": len(review_items) == 200,
            "scheduled": len(scheduled),
            "active_jobs": len(active_jobs),
            "attention": len(attention_sources) + len(pending),
        }
        shown_sources = sources[:6]
        shown_pending = pending[:max(0, 6 - len(shown_sources))]
        return TEMPLATES.TemplateResponse(request=request, name="overview.html",
                                          context={"sources": sources, "pending": pending,
                                                   "totals": totals,
                                                   "shown_sources": shown_sources,
                                                   "shown_pending": shown_pending,
                                                   "remaining_datasets": (
                                                       totals["configured"]
                                                       - len(shown_sources)
                                                       - len(shown_pending)),
                                                   "recent_changes": changes,
                                                   "recent_jobs": recent_jobs,
                                                   "tab": "overview",
                                                   "source_key": None})

    @app.get("/data", response_class=HTMLResponse)
    def data_landing(request: Request):
        """Dataset selection remains a first-class workspace below Overview."""
        conn = read_conn()
        try:
            sources, pending, _ = _source_catalog(conn)
            rate_dataset = google_finance_status(conn)
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(request=request, name="data.html",
                                          context={"sources": sources, "pending": pending,
                                                   "rate_dataset": rate_dataset,
                                                   "tab": "data", "source_key": None,
                                                   "wide_page": True})

    @app.get("/data/google-finance", response_class=HTMLResponse)
    def google_finance_dataset(request: Request, page: int = 1, per_page: int = 50):
        """The provider's stored rate history as a first-class dataset."""
        page = max(1, page)
        per_page = per_page if per_page in {25, 50, 100, 200} else 50
        conn = read_conn()
        try:
            sources, pending, _ = _source_catalog(conn)
            rate_dataset = google_finance_status(conn)
            page_data = browse_google_finance_rates(
                conn, offset=(page - 1) * per_page, limit=per_page,
            )
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(
            request=request, name="google_finance_dataset.html",
            context={"sources": sources, "pending": pending,
                     "rate_dataset": rate_dataset, "page_data": page_data,
                     "page": page, "per_page": per_page,
                     "tab": "data", "source_key": None,
                     "rate_dataset_active": True,
                     "wide_page": True},
        )

    def _view_defaults(source_key: str, view_id: int) -> dict:
        """A saved view as query parameters. Unknown keys never reach SQL.

        A view can name a column this source no longer publishes, or a filter
        key that has since been removed. Both are dropped HERE, before anything
        is queried, and the page says which — a filter silently disappearing
        makes the answer bigger than the question with no way to tell.
        """
        conn = read_conn()
        try:
            saved = next((v for v in list_views(conn, source_key)
                          if v["saved_view_id"] == view_id), None)
        finally:
            conn.close()
        if saved is None:
            return {}
        config = saved.get("config") or {}
        out: dict = {}
        dropped: list[str] = []
        for key in ("q", "direction", "per_page"):
            if config.get(key):
                out[key] = str(config[key])
        # E3: the SORT is validated too, and its loss is announced.
        #
        # It was copied straight through while filters were checked, so a view
        # saved on a column that was later renamed or hidden silently fell back
        # to the default order. _order_by does the same fallback, so nothing
        # broke — it just answered a different question than the one the owner
        # saved, with nothing on screen to say so. The moment to fix it is now:
        # zero saved views exist, so no owner arrangement is disturbed.
        sort = str(config.get("sort") or "")
        if sort and sort in SORTABLE:
            out["sort"] = sort
        elif sort:
            dropped.append(f"sort by {sort}")
        for key, spec in (config.get("filters") or {}).items():
            if key in FILTERABLE and FILTERABLE[key][1] != "derived":
                out[f"f.{key}"] = str(spec)
            else:
                dropped.append(f"filter {key}")
        out["__dropped__"] = dropped
        return out

    def build_query(current: dict, **overrides) -> str:
        """One query-string builder for sort links, the pager, chips and Reset.

        Everything that builds a URL on the data page routes through here. The
        hand-concatenated links it replaces listed q/availability/sort/direction
        and already dropped `page` — with per-column filters added, every sort
        click would have silently discarded the filters the reader had set, and
        the page would have looked like it simply found different rows.

        A changed filter or sort always returns to page 1: staying on page 7 of
        a result set that no longer has seven pages shows an empty table and
        blames the data.
        """
        merged = dict(current)
        merged.update(overrides)
        if any(k != "page" for k in overrides):
            merged.pop("page", None)
        pairs = [(k, v) for k, v in merged.items() if v not in (None, "", [])]
        return "?" + urlencode(pairs, doseq=True) if pairs else ""

    @app.get("/source/{source_key}", response_class=HTMLResponse)
    def source(request: Request, source_key: str, q: str = "", availability: str = "",
               page: int = 1, sort: str = "", direction: str = "asc",
               per_page: int = PAGE_SIZE, edit: str = "", said: str = "",
               focus: str = "", view_id: int = 0):
        page = max(1, page)
        # Clamped against the same cap browse_observations enforces, so a
        # hand-typed ?per_page=40000 cannot ask the warehouse for everything.
        per_page = per_page if per_page in PER_PAGE_OPTIONS else PAGE_SIZE
        # f.* cannot be expressed as typed FastAPI arguments — the number of
        # filters is not known in advance — so they are read from the raw query
        # string and validated against the allow-list before anything else.
        raw = dict(request.query_params)
        # A saved view supplies DEFAULTS. Anything explicitly in the URL wins,
        # so opening a view and then changing a filter does what it looks like
        # rather than snapping back to the saved state.
        dropped_from_view: list[str] = []
        if view_id:
            with_view = _view_defaults(source_key, view_id)
            dropped_from_view = with_view.pop("__dropped__", [])
            for key, value in with_view.items():
                raw.setdefault(key, value)
            q = q or raw.get("q", "")
            sort = sort or raw.get("sort", "")
            direction = raw.get("direction", direction) if "direction" not in request.query_params else direction
        column_filters, ignored_filters = parse_filters(raw)
        # The state every URL on this page is built from.
        state = {k: v for k, v in raw.items()
                 if k.startswith("f.") and k[2:] in column_filters}
        state.update({"q": q, "availability": availability, "sort": sort,
                      "direction": direction, "per_page": per_page})
        if edit:
            state["edit"] = edit
        if view_id:
            state["view_id"] = view_id
        conn = read_conn()
        try:
            sources, pending, source_sites = _source_catalog(conn)
            rate_dataset = google_finance_status(conn)
            summary = next((source for source in sources
                            if source.source_key == source_key), None)
            # A DATASET IS NOT IN THE MANIFEST, and this page asked the manifest
            # alone: `/source/contractors` answered 404 for a table that
            # `/api/table/contractors` was already serving in full. The price
            # machinery below stays behind `is_dataset` because none of it means
            # anything for a company — there is no availability, no offer and no
            # price history to count. The GRID does not need any of it:
            # `grid.js` fetches `/api/table/{key}` itself and builds the language
            # switch from `payload.bilingual`, which is generic and not
            # product-specific.
            is_dataset = summary is None
            if is_dataset:
                dataset = next((row for row in _dataset_rows()
                                if row["source_key"] == source_key), None)
                if dataset is not None:
                    summary = SourceSummary(
                        source_key=dataset["source_key"],
                        source_name=dataset["source_name"],
                        source_name_ar=dataset["source_name_ar"],
                        base_url=dataset["base_url"],
                        products=dataset["products"],
                        observations=dataset["observations"])
            page_data, fields, views, columns = None, [], [], []
            changes_by_offer, facets, watch_counts = {}, {}, {}
            absent_columns = []
            if summary is not None and not is_dataset:
                page_data = browse_observations(
                    conn, source_key, search=q or None, availability=availability or None,
                    sort=sort or None, direction=direction,
                    column_filters=column_filters,
                    offset=(page - 1) * per_page, limit=per_page)
                # Register THIS SOURCE's columns — not a constant header shared by
                # every site — so "manage columns" manages what the table shows,
                # and a source with no variants is never given a Variant column.
                present = column_presence(conn, source_key)
                seed = [key for key, _ in BROWSE_COLUMNS if key in present]
                ensure_fields(conn, source_key, seed)
                conn.commit()
                fields, views = list_fields(conn, source_key), list_views(conn, source_key)
                # The owner's arrangement wins; the per-source seed is the
                # fallback for a source whose fields have never been registered.
                shown = visible_columns(conn, source_key, fallback=seed)
                # A column registered once and no longer published is NOT the
                # same as one the owner hid; conflating them sends them hunting
                # for a control that was never there.
                absent_columns = [f["field_key"] for f in list_fields(conn, source_key)
                                  if f["field_key"] not in present
                                  and f["field_key"] in dict(BROWSE_COLUMNS)]
                labels = dict(BROWSE_COLUMNS)
                renamed = {f["field_key"]: f["display_name"] for f in fields
                           if f.get("display_name")}
                columns = [{"key": key, "label": renamed.get(key) or labels.get(key, key)}
                           for key in shown if key in labels]
                # One bounded query for the whole page, never one per row.
                changes_by_offer = history_counts(
                    conn, [r["offer_id"] for r in page_data.rows if r.get("offer_id")])
                # A <select> only where the schema bounds the domain. Free-text
                # columns get a text box, because listing every distinct product
                # name is the unbounded read A8 forbids.
                watch_counts = watch(conn, source_key)
                facets = {key: facet_options(conn, source_key, key)
                          for key in shown
                          if FILTERABLE.get(key, ("", ""))[1] == "exact"}
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(
            request=request, name="source.html",
            context={"summary": summary, "page_data": page_data, "source_key": source_key,
                     "sources": sources, "pending": pending,
                     "rate_dataset": rate_dataset,
                     "source_sites": source_sites,
                     "source_site": source_sites.get(source_key, ""),
                     "wide_page": True,
                     "q": q, "availability": availability, "page": page, "tab": "data",
                     "sort": sort or "name", "direction": direction,
                     "sortable": list(SORTABLE), "fields": fields, "views": views,
                     "columns": columns, "changes_by_offer": changes_by_offer,
                     # When the Unit column is hidden the unit rides on the price
                     # instead: a price may lose its column, never its unit.
                     "shows_unit": any(c["key"] == "unit" for c in columns),
                     "availability_options": AVAILABILITY_OPTIONS,
                     "per_page_options": PER_PAGE_OPTIONS,
                     "watch": watch_counts, "edit": bool(edit), "view_id": view_id,
                     "dropped_from_view": dropped_from_view,
                     "said": said, "focus": focus, "absent_columns": absent_columns,
                     "filters": column_filters, "ignored_filters": ignored_filters,
                     "facets": facets, "filter_kinds": {k: v[1] for k, v in FILTERABLE.items()},
                     "query": lambda **kw: build_query(state, **kw)},
            status_code=200 if summary is not None else 404)

    @app.get("/api/table/{source_key}")
    def api_table(
        source_key: str,
        fold: bool | None = None,
        site_key: str | None = None,
    ):
        """The whole table for one source, for a grid that filters it in place.

        Bounded at reports.TABLE_ROW_CAP — a large number, but a number. A source
        past it reports truncated=true, because a prefix presented as the whole
        is exactly the failure the bound exists to prevent.
        """
        # Whether this source's same-priced variations fold into one row has a
        # per-source DEFAULT in the manifest and a live switch above the table.
        # `fold` absent means "whatever this source is set to"; ?fold=1 or 0 is
        # the reader saying otherwise for this view, which is why it wins.
        if fold is None:
            try:
                fold = bool(app.state.manifest.get(source_key).fold_variants)
            except KeyError:
                fold = False

        # A GENERIC DATASET IS A TABLE LIKE ANY OTHER TABLE. The key is looked
        # up in the catalogue FIRST, and the price path answers everything the
        # catalogue does not know — so a contractor directory renders on the
        # page the owner already has, with its filters, its column menus, its
        # export and its AR|EN toggle, and `grid.js` never learns it exists.
        #
        # The catalogue goes first rather than second because a dataset key is
        # lower-case with underscores and a source key is upper-case
        # (`^[A-Z][A-Z0-9_]{2,63}$`), so the two sets cannot collide — and
        # asking the cheaper, smaller table first costs nothing when it misses.
        general = general_read_conn()
        try:
            dataset = extract_service.dataset_table_payload(
                general, source_key, site_key=site_key
            )
        finally:
            general.close()
        if dataset is not None:
            return dataset

        conn = read_conn()
        try:
            return table_payload(conn, source_key, fold_variants=fold)
        finally:
            conn.close()

    @app.get("/data-model", response_class=HTMLResponse)
    def data_model_page(request: Request):
        """Every live relational model, drawn from its own SQLite schema.

        ONE FILE IS REPORTED ONCE, and until 2026-08-30 it was reported twice.
        `create_app` sets `general_database = databases.engine` whenever a
        registry is present, so both handles opened the SAME database — and
        `data_model_report` selects every non-`sqlite_` table from
        `sqlite_master` with no `database_key` predicate, so both reports listed
        every table. Measured: 67 tables each, identical lists, and the page
        summing them to **134**. One of the two was labelled *MarketLens*, after
        a database `R-72` retired.

        THE UNCONDITIONAL DELETION WOULD HAVE BEEN WRONG, which is why this is a
        path comparison rather than one report. `general_db_path` is still a
        parameter, and this module's own comment calls it "a legacy
        test/session knob" that "names an engine database like any other" — with
        it set the two handles are two different files and both belong here. The
        page reports what is actually distinct, which is right in both cases
        instead of right in today's.
        """
        reports = []
        price_conn = read_conn()
        try:
            reports.append(data_model_report(
                price_conn, database_key="engine", database_label="Engine"))
        finally:
            price_conn.close()

        second = app.state.general_database
        if second is not None and Path(second.path) != Path(app.state.db_path):
            general_conn = general_read_conn()
            try:
                reports.append(data_model_report(
                    general_conn, database_key="general", database_label="General"))
            finally:
                general_conn.close()

        model = {
            "databases": reports,
            "table_count": sum(len(report["tables"]) for report in reports),
            "relationship_count": sum(
                len(report["relationships"]) for report in reports),
            "row_count": sum(report["row_count"] for report in reports),
        }
        return TEMPLATES.TemplateResponse(
            request=request, name="data_model.html",
            context={"model": model, "tab": "data-model", "source_key": None,
                     "wide_page": True})

    @app.post("/api/engine/restart")
    def restart_engine(request: Request) -> dict:
        """Replace this engine with one running the current code.

        The fault only this can repair: a database written by a NEWER build than
        the process reading it. Migrations go forward only, so Upgrade database
        cannot help, and the guard is right to refuse rather than guess — which
        left exactly one route out, and it was a terminal command. The owner
        does not use a terminal, so it is a button.

        A process cannot free its own port and then bind it, so the work goes to
        a detached helper that outlives this one (scrapex/relaunch.py). This
        answers FIRST and exits a moment later, so the browser gets a reply
        instead of a dropped connection.
        """
        from .. import relaunch as relaunch_module

        port = int(request.url.port or 8000)
        try:
            helper = relaunch_module.spawn_helper(port)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(f"could not start the helper that brings the engine back ({exc}). "
                        "The engine is still running; start a new one from the Startup "
                        "folder if you need the newer code.")) from exc

        def bow_out() -> None:
            # Long enough for the response to reach the browser, short enough
            # that the helper is not left waiting on a port nobody released.
            time.sleep(1.5)
            os._exit(0)

        threading.Thread(target=bow_out, daemon=True).start()
        return {"ok": True, "helper_pid": helper, "port": port,
                "message": ("Restarting. This page will not answer for a few seconds — "
                            "reload it once the engine is back.")}

    @app.post("/api/native-host/register")
    def register_native_host(payload: dict) -> dict:
        """Re-link the Chrome helper to THIS extension id.

        Reloading an unpacked extension from a different folder gives it a new
        id, and the installed host allows only the id it was installed for — so
        the panel's Start engine starts failing with nothing visibly broken.
        The panel knows its own id; this writes it into the host, so the repair
        needs no command and no reinstall.

        It ADDS the id — see nativehost.install. Any extension may reach this
        route (that exception is what keeps the repair reachable), so replacing
        the list here let one extension evict another, and the two could take
        the helper from each other indefinitely with nothing said anywhere. The
        write is now additive, capped, and printed: stdout is the engine log,
        which is where the owner is already sent when the helper misbehaves.
        """
        extension_id = str(payload.get("extension_id") or "").strip()
        if not extension_id.isalnum() or not (24 <= len(extension_id) <= 40):
            raise HTTPException(status_code=400,
                                detail="that does not look like a Chrome extension id")
        from ..nativehost import install

        before = allowed_extension_ids()
        try:
            written = install([extension_id])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        after = allowed_extension_ids()
        print(f"[native-host] {extension_id} asked to be recognised; "
              f"allowlist {before or '[]'} -> {after}", flush=True)
        return {"ok": True, "manifest": str(written), "extension_id": extension_id,
                "allowed_extension_ids": after,
                "message": "The helper now recognises this extension. Try Start engine again."}

    @app.get("/schema", response_class=HTMLResponse)
    def schema_page(request: Request):
        """What every column is, derived from the code and the warehouse.

        The owner asked for a page he could read and review with me. Written by
        hand it would be wrong within a week, so nothing here is written by
        hand: the names come from the same lists the table and the export are
        built from, and the counts from the warehouse as it is right now.
        """
        conn = read_conn()
        try:
            return TEMPLATES.TemplateResponse(
                request=request, name="schema.html",
                context={"schema": schema_report(conn)})
        finally:
            conn.close()

    @app.get("/export/{source_key}.xlsx")
    def export_workbook(source_key: str):
        """One download carrying the WHOLE record for a source.

        The owner exported to Excel and got the price table alone. Two separate
        reasons, both fixed here: the details, the history and the provenance
        were published to Google and reachable from nowhere else, and the Data
        page's Excel button called Tabulator's browser-side xlsx writer, which
        needs a SheetJS library this project has never vendored — so it logged
        a console error and produced no file at all.

        Built on the server, where those tabs actually live, from the same
        publish.workbook_tables the CLI and the Google push use, so one export
        cannot answer differently from another.
        """
        conn = read_conn()
        general = general_read_conn()
        try:
            tabs = workbook_tables(conn, source_key, general=general)
        except ValueError as exc:      # nothing ingested for this source yet
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            general.close()
            conn.close()
        try:
            body = workbook_bytes(tabs)
        except RuntimeError as exc:    # openpyxl absent: name the install
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        name = f"{source_key}-{utc_now_iso()[:10]}.xlsx"
        return Response(
            content=body,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/source/{source_key}/offer/{offer_id}", response_class=HTMLResponse)
    def offer_history(request: Request, source_key: str, offer_id: int):
        """One offer's price story: every change, and what was recorded.

        A real page at a real URL, not a dialog, so it can be linked, bookmarked
        and read with scripting off. pricehistory.timeline() has been callable
        since migration 0016 and no screen could reach it — the row on the data
        page carried no offer_id to ask about.
        """
        conn = read_conn()
        try:
            offer = offer_identity(conn, source_key, offer_id)
            if offer is None:
                # Either the offer does not exist or it belongs to another
                # source. Both are "not here" from this URL, and saying which
                # would confirm the existence of an id the caller may not own.
                raise HTTPException(status_code=404,
                                    detail=f"no offer {offer_id} in {source_key}")
            periods = pricehistory.timeline(conn, offer_id)
            observations = offer_observations(conn, offer_id)
        finally:
            conn.close()
        return TEMPLATES.TemplateResponse(
            request=request, name="offer.html",
            context={"tab": "data", "source_key": source_key, "offer": offer,
                     "periods": periods, "observations": observations})

    @app.get("/api/offer/{source_key}/{offer_id}")
    def api_offer(source_key: str, offer_id: int):
        """One offer's story as JSON, for the panel the Data page opens INLINE.

        The same ownership rule as the HTML page: an offer that is not this
        source's answers 404 without confirming whether the id exists at all.
        """
        conn = read_conn()
        try:
            offer = offer_identity(conn, source_key, offer_id)
            if offer is None:
                raise HTTPException(status_code=404,
                                    detail=f"no offer {offer_id} in {source_key}")
            return {
                "offer": offer,
                "periods": pricehistory.timeline(conn, offer_id),
                "observations": offer_observations(conn, offer_id),
                "changes": changes_for_offer(conn, offer_id),
                "details": product_attributes(conn, offer_id),
            }
        finally:
            conn.close()

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
                         extremes=price_extremes(conn, source_key, limit=2000) if source_key else [],
                         offers=_offers_with_history(conn, source_key) if source_key else [],
                          sources=_display_sources(conn))
        finally:
            conn.close()

    @app.get("/history", response_class=HTMLResponse)
    def page_history(request: Request, source_key: str | None = None):
        conn = read_conn()
        try:
            return _page(request, "history.html", "history", source_key,
                         runs=crawl_history(conn, source_key),
                          sources=_display_sources(conn))
        finally:
            conn.close()

    @app.get("/review", response_class=HTMLResponse)
    def page_review(request: Request, source_key: str | None = None):
        conn = read_conn()
        try:
            return _page(request, "review.html", "review", source_key,
                         pending=pending_reviews(conn, source_key, limit=100),
                          sources=_display_sources(conn))
        finally:
            conn.close()

    @app.get("/jobs", response_class=HTMLResponse)
    def page_jobs(request: Request):
        conn = read_conn()
        try:
            return _page(request, "jobs.html", "jobs", None,
                         jobs=[_job_view(j) for j in list_jobs(conn, limit=50)],
                         sources=_display_sources(conn))
        finally:
            conn.close()

    @app.get("/schedules", response_class=HTMLResponse)
    def page_schedules(request: Request):
        """THE central editor for automation (owner's ruling) — one editable
        row per implemented source, its saved schedule merged in. The page was
        a read-only table that said "set one from the side panel", which is
        the opposite of central."""
        conn = read_conn()
        try:
            saved = {s["source_key"]: s for s in list_schedules(conn)}
        finally:
            conn.close()
        rows = []
        for entry in app.state.manifest.sources:
            if not _is_implemented(entry):
                continue
            rows.append({
                "source_key": entry.source_key,
                "source_name": entry.source_name,
                "source_name_ar": entry.source_name_ar,
                "base_url": entry.base_url,
                "active": entry.active,
                "supports_history": supports_history(entry.family),
                "sched": saved.get(entry.source_key) or {},
            })
        return _page(request, "schedules.html", "schedules", None, rows=rows)

    @app.get("/logs", response_class=HTMLResponse)
    def page_logs(request: Request, job_ref: str | None = None):
        conn = read_conn()
        try:
            jobs = list_jobs(conn, limit=50)
            job_ref = job_ref or (jobs[0]["job_ref"] if jobs else None)
            # Every entry, same as the panel and the API: this page's whole job
            # is reading why a run went wrong, and the line that says so is
            # exactly the one a tail drops.
            return _page(request, "logs.html", "logs", None,
                         jobs=[_job_view(j) for j in jobs], job_ref=job_ref,
                         entries=job_logs(conn, job_ref) if job_ref else [],
                         entry_total=job_log_count(conn, job_ref) if job_ref else 0)
        finally:
            conn.close()

    @app.get("/exports", response_class=HTMLResponse)
    def page_exports(request: Request, source_key: str = ""):
        conn = read_conn()
        try:
            return _page(request, "excel.html", "exports", source_key or None,
                         status=excel_status(conn), settings=public_settings(conn),
                          sources=_display_sources(conn))
        finally:
            conn.close()

    @app.get("/settings", response_class=HTMLResponse)
    def page_settings(request: Request):
        """Settings remain collapsed and display the engine's current truth."""
        conn = read_conn()
        try:
            return _page(request, "settings.html", "settings", None,
                         settings=public_settings(conn),
                         storage=storage_status(conn, app.state.db_path),
                         retention=_retention_view(conn),
                         excel=excel_status(conn), funnel=apps_script_status(conn),
                         google_finance=google_finance_status(conn),
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
                         funnel=apps_script_status(conn),
                          settings=public_settings(conn), sources=_display_sources(conn))
        finally:
            conn.close()

    # ---- JSON API (the Chrome extension) -----------------------------------

    @app.get("/api/ui")
    def api_ui(source_key: str | None = None):
        """Shared presentation metadata for the workspace and the Chrome panel.

        One contract (scrapex/ui_manifest.py) feeds the sidebar AND this
        endpoint; the panel overlays its run-mode copy from here and falls
        back to its built-ins when the engine is unreachable."""
        if source_key:
            try:
                app.state.manifest.get(source_key)
            except KeyError:
                raise HTTPException(status_code=404,
                                    detail=f"unknown source_key {source_key!r}")
        return ui_manifest(source_key)

    @app.get("/api/health")
    def api_health():
        from .. import __version__
        # Health must survive the thing it reports on. Counting sources needs a
        # readable database, and when that failed this endpoint failed with it —
        # so the panel's only timed poll went silent exactly when it had
        # something to say.
        try:
            conn = read_conn()
            try:
                n = len(list_sources(conn))
            finally:
                conn.close()
        except (DatabaseUnavailableError, DatabaseMigrationError,
                DatabaseKindError, sqlite3.DatabaseError):
            n = 0
        # IS THE DATABASE BEHIND THE CODE? The panel polls this and nothing else
        # on a timer, so the answer rides along.
        #
        # CI was green and the Data page was broken at the same moment, and both
        # were right: CI builds a database from every migration, so a query
        # reading a new column passes there by construction, while the owner's
        # machine had the code and not the migration and answered
        # "no such column: so.weight". Nothing said the database was one
        # migration behind — the product just broke, and raw SQLite text was the
        # only clue. A lag the engine can measure must not be something the
        # owner discovers from a stack trace.
        schema_lag = None
        try:
            conn = read_conn()
            try:
                waiting = dbmod.pending_migrations(conn)
            finally:
                conn.close()
            if waiting:
                schema_lag = {
                    "pending": [name for _n, name in waiting],
                    # Named so the message can be acted on without a manual:
                    # the fix is one command, and it is the ONLY sanctioned one.
                    "fix": "python -m scrapex.cli init-db",
                    "message": (
                        f"{len(waiting)} migration(s) on disk are not applied to "
                        f"this database — {waiting[0][1]} onward. Pages that read "
                        "the newer columns will fail until they are applied."),
                }
        except (DatabaseUnavailableError, DatabaseMigrationError,
                DatabaseKindError, sqlite3.DatabaseError):
            schema_lag = None      # unreadable is a different fault, reported above
        # The panel polls this and nothing else on a timer, so database status
        # rides along: a reachable engine sitting on an unusable database looked
        # exactly like a healthy one from the panel.
        databases = None
        if app.state.databases is not None:
            try:
                # NO CORRUPTION SCAN ON A TIMED POLL. `quick_check(1)` and
                # `foreign_key_check` are O(file size) — measured at 0.879 s and
                # 0.398 s on a 1,067 MB warehouse — and the panel polls this
                # endpoint on a timer with a 2.5 s deadline
                # (`extension/startup.js`, `engineHealth`). At 796 MB the whole
                # endpoint fitted inside it; after a merge took the file to
                # 1,067 MB it answered in 3.8 s, the deadline expired, and the
                # panel reported the engine as "Not detected" — while it was
                # healthy and serving 0.3.0.
                #
                # The poll asks IDENTITY: readable, right version, right kind.
                # Corruption is the Storage page's question, it does not develop
                # between two polls seconds apart, and the result carries
                # `integrity_checked=False` so the narrower claim is visible
                # rather than implied.
                states = app.state.databases.health(integrity=False)
                databases = {
                    "ok": all(item["ok"] for item in states.values()),
                    "detail": ", ".join(
                        f"{item['kind']} {item['status'].lower()}"
                        for item in states.values() if not item["ok"]
                    ),
                }
            except Exception:
                databases = {"ok": False, "detail": "status unavailable"}
        runner = getattr(app.state, "runner", None)
        try:
            thread_alive = bool(runner and runner.is_alive)
        except Exception:
            thread_alive = False
        # The THREAD being alive is not the same question as the worker
        # doing its work, and neither is the port answering. The heartbeat
        # is written by the loop itself, so it is the only one of the three
        # that can prove a crawl could start — and when it cannot, the
        # reason the loop recorded travels with it instead of dying on a
        # stderr that pythonw discards.
        try:
            conn = read_conn()
            try:
                worker = worker_health(conn)
            finally:
                conn.close()
        except Exception as exc:
            # NOT `pass` onto a fallback seeded with thread_alive. That published
            # the thread flag AS the worker's liveness - the one conflation the
            # comment above forbids - and it did it on exactly the failure the
            # loop had already recorded: a worker spinning on a dead handle read
            # as "running" because its thread object was still alive. Unknown is
            # now said as unknown, and the reason for not knowing travels with it.
            worker = {"alive": None, "failure": None,
                      "detail": "the worker's state could not be read: "
                                f"{type(exc).__name__}: {exc}"}
        worker["thread_alive"] = thread_alive
        from ..native import PROTOCOL_VERSION
        from ..version import MINIMUM_EXTENSION_VERSION, VERSION
        return {"ok": True, "app": "scrapex", "version": __version__,
                # The panel polls THIS and nothing else on a timer, so the two
                # numbers a stale extension needs to notice itself ride along.
                # The full ledger does not: it is fetched once from /api/version
                # and would otherwise be re-sent every few seconds to answer a
                # question whose answer only changes when the engine restarts.
                #
                # `version` above is the engine's. These two say whose they are
                # in their own names, which is the whole complaint behind issue
                # 32: a number displayed without its owner is the bug.
                "latest_extension_version": VERSION,
                "minimum_extension_version": MINIMUM_EXTENSION_VERSION,
                # The version handshake belongs on the transport that carries
                # the traffic. It lived only on native messaging, which carries
                # four control commands, while THIS path carries every record
                # the panel shows — so an extension newer than its engine met a
                # 404 and read it as a broken feature rather than a stale engine.
                "protocol_version": PROTOCOL_VERSION,
                "sources_with_data": n,
                # Kept for the panel that already reads it. Unknown answers false:
                # this endpoint may never claim a health it could not read.
                "worker_alive": worker.get("alive") is True,
                "worker": worker,
                "databases": databases,
                # None when the database is level with the code, which is the
                # normal case — so the panel shows nothing rather than a badge
                # that is always there and therefore never read.
                "schema_lag": schema_lag,
                # IS THE CODE BEHIND THE DISK? `schema_lag` above asks whether the
                # DATABASE is behind the code, and it was written because a lag the
                # engine can measure must not be something the owner discovers from
                # a stack trace. This is the same sentence about the other pair, and
                # it had no answer at all until 2026-08-23: `version` above says
                # "0.3.0" for ten different trees, so it can say what this engine
                # ADVERTISES and never what it IS. The compact form rides the timed
                # poll; the module list is on /api/version with the ledger, for the
                # reason stated there.
                "build": provenance.summary()}

    @app.get("/api/version")
    def api_version(extension_version: str | None = None):
        """Which version this engine is, and what it deploys (issue 32 §1.3–§1.6).

        ONE implementation of "is this extension outdated", and it is here
        rather than in the panel: the panel states its own version, the engine
        applies the rule, and the same answer is available to the web page. Two
        surfaces computing one verdict from one ledger is what §2.5 asks for,
        and it is also the only way the web page can display a state it has no
        other way of knowing.

        A malformed version is refused rather than treated as "very old": an
        unreadable number is a bug in the caller, and answering it with
        "everything is missing" would send the owner to reload an extension
        that is perfectly current.
        """
        from ..version import version_report

        try:
            # An absent or empty parameter is "the caller did not say", which is
            # a different answer from "the caller said something unreadable".
            report = version_report(extension_version or None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        # WHAT THIS ENGINE IS, beside what it advertises. Every number above is a
        # declaration read out of `scrapex/version.py`; this is the only field on
        # either endpoint that is MEASURED from the running process. It carries the
        # changed-module list that `/api/health` deliberately leaves out, because
        # this endpoint is fetched once rather than polled — the same split the
        # capability ledger already makes.
        report["provenance"] = provenance.report()
        return report

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
            # Widened rather than given a route of its own: the panel already
            # redraws every source row from THIS answer, and a second request
            # per source would arrive after the rows were painted — the kept
            # pages would appear a beat late, next to a Start button that was
            # already live. One answer, one paint.
            kept = localinbox.journal_state(localinbox.JOURNAL_DIR, entry.source_key)
            out.append({
                "source_key": entry.source_key, "source_name": entry.source_name,
                "source_name_ar": entry.source_name_ar,
                "base_url": entry.base_url, "family": entry.family.value,
                "active": entry.active, "implemented": _is_implemented(entry),
                # A per-source CAPABILITY, not a universal mode: the panel
                # offers History backfill only where this is true.
                "supports_history": supports_history(entry.family),
                # The editable facts, carried because the panel's source editor
                # renders FROM this list. Without them it painted an empty
                # currency over a real one and offered to save it back — an
                # edit of the name would have erased the currency, the cadence
                # and the tax position.
                "currency": entry.currency or "",
                "cadence": entry.cadence.value,
                "vat_mode": entry.vat_mode.value,
                "fold_variants": entry.fold_variants,
                "observations": s.observations if s else 0,
                "products": s.products if s else 0,
                # When the data on screen was last actually gathered, and by what
                # measure — the freshness fact the cards were missing. None where
                # a source has never had a successful crawl, which the card says
                # in words rather than showing a blank or a zero.
                "last_success": s.last_success if s else None,
                # An interrupted crawl's pages, still on disk. A resume skips
                # exactly these; a fresh run deletes them (capture.py).
                "kept_pages": kept["pages"],
                "kept_at": kept["stopped_at"],
            })

        # A GENERIC DATASET IS A SOURCE THE OWNER CAN OPEN, and until now it was
        # invisible here: this route walked the manifest alone, so a
        # `source_site` row could never reach the panel however much data it
        # held. The Data screen lists what this answers and opens it through
        # /api/table/{key}, which already serves a dataset — so listing them is
        # the whole of what was missing.
        #
        # `kind` MARKS THEM, and the panel needs it: the row menu offers Update,
        # Wipe and Rename, and every one of those is a price-path action that
        # would answer 400 or worse for a dataset. A button that cannot work is
        # worse than no button, so the panel hides them on this marker.
        #
        # `_dataset_listing` AND NOT `_dataset_rows`, which is `R-47`: this is the
        # LISTING, where one site is one card, and `/source/{key}` is the resolver,
        # where the two stored datasets stay two. The same function serving both is
        # what drew `muqawil.org` twice on his Data screen (`REQ-37`).
        out.extend(_dataset_listing())
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
            "rows": rows, "tab": "data", "source_key": None,
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

    @app.post("/api/sources/{source_key}/active")
    def api_set_active(source_key: str, body: dict):
        """Flip one source's automation switch, from the panel.

        Writes the manifest surgically (comments survive) and reloads it, so
        the runner's next scheduler tick sees the new truth. Manual runs are
        never gated by this — active means "may run WITHOUT me".
        """
        wanted = bool((body or {}).get("active"))
        try:
            set_active(source_key, wanted, app.state.manifest_path)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown source {source_key!r}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # pydantic refusals (e.g. a TBD-probe placeholder)
            raise HTTPException(status_code=400, detail=str(exc))
        app.state.manifest = load_manifest(app.state.manifest_path)
        reconciled = _follow_the_manifest()
        return {"source_key": source_key, "active": wanted,
                "warehouse_updated": sorted(reconciled)}

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
        _follow_the_manifest()
        return {"ok": True, "source_key": entry.source_key,
                "implemented": entry.family in _BUILDERS}

    @app.get("/api/sources/{source_key}")
    def api_source_detail(source_key: str):
        """One source's manifest entry PLUS what it actually holds.

        The footprint is not decoration. The owner asked for "stop this source"
        and "erase its data" to be two separate buttons, and a button that says
        how many products and observations it is about to erase is the
        difference between a choice and a guess.
        """
        try:
            entry = app.state.manifest.get(source_key)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown source {source_key!r}")
        conn = read_conn()
        try:
            holds = source_footprint(conn, source_key)
        finally:
            conn.close()
        return {"source": json.loads(entry.model_dump_json()), "holds": holds,
                "implemented": entry.family in _BUILDERS}

    @app.get("/api/sources/{source_key}/robots")
    def api_source_robots(source_key: str):
        """LOOK BEFORE CHOOSING: what this site's robots.txt actually says.

        Its own route, and a GET, because it is the one step of the three that
        changes nothing. A choice offered before the facts is a guess with a
        dropdown around it — the owner cannot sensibly pick "obey" for a site
        until he knows whether obeying means a five-second delay or an empty
        crawl, and the only honest way to tell him is to read the file.

        `would_block_everything` is the field that decides the answer: when it
        is true, choosing obey does not make this source polite, it makes it
        collect nothing while reporting success.
        """
        import httpx

        from ..connectors.base import DEFAULT_USER_AGENT
        from ..robots import RobotsChoice, RobotsCustom, decide, inspect

        try:
            entry = app.state.manifest.get(source_key)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown source {source_key!r}")

        conn = read_conn()
        try:
            crawl = crawl_settings(conn)
            agent = entry.user_agent or crawl.get("user_agent") or DEFAULT_USER_AGENT
            obeys_by_default = bool(crawl.get("obey_disallow"))
        finally:
            conn.close()

        text, unreadable = None, ""
        try:
            base = urlsplit(entry.base_url)
            with httpx.Client(timeout=15.0, follow_redirects=True,
                              headers={"User-Agent": agent}) as client:
                answer = client.get(f"{base.scheme}://{base.netloc}/robots.txt")
            if answer.status_code == 200:
                text = answer.text
            elif answer.status_code not in (404, 410):
                # 404 means there is no file, which is an ANSWER. Anything else
                # means we did not get to read one, and the two must not look
                # alike on the screen.
                unreadable = f"HTTP {answer.status_code}"
        except Exception as exc:
            # Any failure to READ robots.txt is reported as a failure to read
            # it, never as an empty file: "the site asks nothing" and "we could
            # not find out" lead the owner to opposite choices.
            unreadable = f"{type(exc).__name__}: {exc}"

        report = inspect(entry.base_url, text, user_agent=agent, unreadable=unreadable)
        choice = RobotsChoice(entry.robots or "default")
        custom = None
        if choice is RobotsChoice.CUSTOM and entry.robots_custom:
            custom = RobotsCustom(
                enforce_disallow=bool(entry.robots_custom.get("enforce_disallow")),
                crawl_delay_s=entry.robots_custom.get("crawl_delay_s"))
        # Shown as "what would happen on a disallowed path", because that is the
        # only case where the three choices differ at all.
        try:
            verdict = decide(report, choice, custom=custom,
                             tool_default_obeys=obeys_by_default, url_disallowed=True)
            outcome = {"may_fetch": verdict.may_fetch, "delay_s": verdict.delay_s,
                       "reason": verdict.reason}
        except ValueError as exc:
            outcome = {"may_fetch": None, "delay_s": None, "error": str(exc)}

        return {
            "source_key": source_key,
            "host": report.host,
            "found": report.found,
            "unreadable": report.unreadable,
            "names_us": report.names_us,
            "user_agent": agent,
            "crawl_delay_s": report.crawl_delay_s,
            "would_block_everything": report.obeying_would_block_everything,
            "summary": report.summary(),
            "rules": [{"kind": r.kind, "value": r.value, "agent": r.agent}
                      for r in report.rules],
            "choice": str(choice),
            "custom": entry.robots_custom,
            "tool_default_obeys": obeys_by_default,
            "on_a_disallowed_path": outcome,
        }

    @app.post("/api/sources/{source_key}/edit")
    def api_edit_source(source_key: str, body: dict):
        """Replace one source's manifest block.

        Every field may change EXCEPT source_key, refused here with the reason:
        the warehouse joins on it, so changing it in the manifest alone orphans
        the data rather than renaming it. /rename does both together.

        A cost the owner should be told rather than discover: comments written
        INSIDE this source's block do not survive an edit. An edit can add or
        remove any field, so there is no single line to rewrite the way the
        active flip has — the block is replaced whole. Comments elsewhere in the
        manifest are untouched.
        """
        if source_key not in {s.source_key for s in app.state.manifest.sources}:
            raise HTTPException(status_code=404, detail=f"unknown source {source_key!r}")
        current = json.loads(app.state.manifest.get(source_key).model_dump_json())
        # MERGE, never rebuild: an edit that named two fields would otherwise
        # drop every field it did not mention, which is a wipe wearing the word
        # "edit". Only what the form actually sends changes.
        form = {**current, **{k: v for k, v in (body or {}).items() if v is not None}}
        form.setdefault("source_key", source_key)
        # ENFORCED HERE, not trusted from the form. The merge above drops nulls
        # on purpose -- a partial edit must not wipe fields it did not mention --
        # so a client switching a source AWAY from `custom` cannot clear its
        # custom rule by sending null. Left behind, the rule sits under a choice
        # that ignores it and reads as "this site is customised" on every later
        # open, until someone switches back and is silently governed by a rule
        # they last saw weeks ago.
        if form.get("robots") != "custom":
            form["robots_custom"] = None
        if str(form.get("source_key")) != source_key:
            raise HTTPException(
                status_code=400,
                detail="use /rename to change a source_key: the warehouse joins "
                       "on it, so editing it here would orphan the rows")
        try:
            entry = _entry_from_form(form)
            update_source(source_key, entry, app.state.manifest_path)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # pydantic refusals reach the panel as a message
            raise HTTPException(status_code=400, detail=str(exc))
        app.state.manifest = load_manifest(app.state.manifest_path)
        _follow_the_manifest()
        return {"ok": True, "source_key": source_key}

    @app.post("/api/sources/{source_key}/rename")
    def api_rename_source(source_key: str, body: dict):
        """Rename a source AND move every row that joins on it, together.

        source_key appears in nine tables. Renaming the manifest alone would
        leave it describing a shop the warehouse has never heard of while the
        products sat under a name nothing points at — so the rows move first, in
        one transaction, all of them or none.
        """
        new_key = str((body or {}).get("source_key") or "").strip()
        if not new_key:
            raise HTTPException(status_code=400, detail="a new source_key is required")
        known = {s.source_key for s in app.state.manifest.sources}
        if source_key not in known:
            raise HTTPException(status_code=404, detail=f"unknown source {source_key!r}")
        if new_key in known:
            raise HTTPException(status_code=409,
                                detail=f"{new_key!r} already names another source")

        entry = app.state.manifest.get(source_key)
        renamed = entry.model_copy(update={"source_key": new_key})
        # The write lock, like every other route that changes the warehouse: a
        # rename racing an ingest would leave rows arriving under the old name
        # while the transaction moved the rest.
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                moved = rename_source(conn, source_key, new_key)
            except SourceKeyInUse as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            except KeyError:
                moved = {}      # never crawled: nothing to move, the name is free
            finally:
                conn.close()
        # The manifest moves only AFTER the rows did. A manifest renamed while
        # the data failed to move is precisely the orphaning this prevents.
        try:
            remove_source(source_key, app.state.manifest_path)
            add_source(renamed, app.state.manifest_path)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"the rows moved to {new_key!r} but the manifest did not: "
                       f"{exc}. The warehouse is consistent; fix the manifest.")
        app.state.manifest = load_manifest(app.state.manifest_path)
        _follow_the_manifest()
        return {"ok": True, "source_key": new_key, "moved": moved}

    @app.delete("/api/sources/{source_key}")
    def api_remove_source(source_key: str):
        """Take a source off the crawl list. Its DATA is untouched.

        The owner's ruling: stopping a source and erasing its data are two
        separate actions with two clear outcomes, so neither can be mistaken for
        the other. This is the first. The rows, the price history and the crawl
        audit trail all survive — they are evidence of what a shop published,
        and removing the entry is not a claim that none of it happened.
        """
        if not remove_source(source_key, app.state.manifest_path):
            raise HTTPException(status_code=404, detail=f"unknown source {source_key!r}")
        app.state.manifest = load_manifest(app.state.manifest_path)
        _follow_the_manifest()
        return {"ok": True, "source_key": source_key, "data_kept": True}

    @app.post("/api/sources/{source_key}/wipe")
    def api_wipe_source(source_key: str, body: dict | None = None):
        """Erase every row this source ever ingested. The ENTRY survives.

        The second of the owner's two actions. A backup is taken first,
        unconditionally — the CLI has done that since wipe-source existed, and a
        button is not a reason to be braver than a command line.

        Registration and crawl audit history are kept, matching wipe-source
        exactly: a button must not quietly mean something different from the
        command that does the same job.
        """
        if source_key not in {s.source_key for s in app.state.manifest.sources}:
            raise HTTPException(status_code=404, detail=f"unknown source {source_key!r}")
        if not bool((body or {}).get("confirm")):
            raise HTTPException(
                status_code=400,
                detail="this erases every row this source ever ingested; send "
                       "confirm=true to proceed (a backup is taken first)")
        # NO separate backup call: wipe_source takes one itself, unconditionally,
        # and says why in its own docstring ("a wipe that cannot be undone is not
        # a dev tool, it is a trap"). Taking a second would make the guarantee
        # look like the caller's to remember.
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                result = wipe_source(conn, app.state.db_path, source_key)
                conn.commit()
            finally:
                conn.close()
        return {"ok": True, "source_key": source_key,
                "detail": getattr(result, "detail", "") or str(result),
                "entry_kept": True}

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
        tz_name = body.get("timezone", "UTC")
        if not zone_exists(tz_name):
            # Saving would silently mean UTC and 09:00 would fire at a
            # different hour, unexplained forever. Refuse with the name.
            raise HTTPException(status_code=400,
                                detail=f"unknown timezone {tz_name!r} — use an "
                                       "IANA name like Africa/Cairo")
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
    from ..enrichment.api import create_enrichment_router

    app.include_router(create_enrichment_router(general_read_conn, _general_write))

    def _dataset_fields(source_key: str, schema_fields):
        """Choose-Columns for a DATASET: its own fields, and only its own.

        Two rules, and each answers a defect measured on 2026-08-22.

        SEEDED FROM THE SCHEMA, never from `browse_columns()`. The dataset's
        `field_definition` rows are what it actually publishes, so the panel can
        only offer columns the directory has.

        AND LISTED BY INTERSECTION, because `ensure_fields` is additive and the
        eleven price-path rows already written against `contractors` cannot be
        un-written by seeding correctly — they would simply be joined by the 28
        real ones. Filtering here makes them inert without deleting anything:
        `COMPATIBILITY.md` puts a destructive migration behind a review gate that
        is HIS, and old data is never rewritten just to make the model look
        clean. The rows stay on disk; the panel stops believing them.
        """
        keys = [row["field_key"] for row in schema_fields]
        conn = read_conn()
        try:
            ensure_fields(conn, source_key, keys)
            conn.commit()
            wanted = set(keys)
            return {"source_key": source_key,
                    "fields": [field for field in list_fields(conn, source_key)
                               if field["field_key"] in wanted],
                    "views": list_views(conn, source_key),
                    "order_source": ("yours" if arranged(conn, source_key)
                                     else "agreed")}
        finally:
            conn.close()

    @app.get("/api/fields/{source_key}")
    def api_fields(source_key: str):
        # A GENERIC DATASET IS A TABLE LIKE ANY OTHER TABLE, and the catalogue is
        # asked FIRST for exactly the reason `/api/table` asks it first: a
        # dataset key is lower-case with underscores and a source key is
        # upper-case, so the two sets cannot collide, and the cheaper table costs
        # nothing when it misses.
        #
        # WITHOUT THIS BRANCH THIS ENDPOINT LIED, and it wrote its lie down.
        # Falling through to the price path asked `column_presence` — "which
        # BROWSE columns does this source populate" — about a contractor
        # directory, and `ensure_fields` is additive by design, so merely
        # opening Choose-Columns on the muqawil table registered ELEVEN
        # price-path keys against `contractors`: display_method, price,
        # minimum_quantity, quantity_increment, stock_quantity, tax,
        # category_leaf, category_leaf_ar, price_changed_on, last_confirmed_on,
        # curation. Measured in the live warehouse 2026-08-22 — all eleven are
        # there, and not one of the directory's own 28 fields was.
        general = general_read_conn()
        try:
            resolved = extract_service.dataset_schema_fields(general, source_key)
        finally:
            general.close()
        if resolved is not None:
            return _dataset_fields(source_key, resolved[1])

        conn = read_conn()
        try:
            # Seeded from THIS SOURCE's present columns, the same way the page
            # does it. It used to seed from export_source_table's constant
            # header, so merely opening the panel registered columns the source
            # does not publish — and they then showed up in the manage list
            # forever, because ensure_fields is additive by design.
            present = column_presence(conn, source_key)
            # Seeded in the AGREED order, not the order the list happens to be
            # written in: ensure_fields assigns display_order by insertion, so
            # a source registered here would otherwise carry the unsorted order
            # the moment its owner arranges anything.
            ensure_fields(conn, source_key,
                          [key for key, _ in browse_columns() if key in present])
            conn.commit()
            return {"source_key": source_key, "fields": list_fields(conn, source_key),
                    "views": list_views(conn, source_key),
                    # Whose order this is. The panel says it out loud, because an
                    # owner who arranged his columns should never have to wonder
                    # whether an update replaced them.
                    "order_source": "yours" if arranged(conn, source_key) else "agreed"}
        finally:
            conn.close()

    @app.get("/api/promotable/{source_key}")
    def api_promotable(source_key: str):
        """Every detail this source publishes that COULD be a column.

        The owner asked whether the exported tables are not already assembled
        from the system's own tables. They are: madar's export is 56 declared
        columns plus 64 pivoted straight out of the details table. What he could
        not do was CHOOSE — an attribute rose only where the shop published it
        as a facet, so sika, whose shop publishes none, got none of its 18.
        """
        conn = read_conn()
        try:
            return {"source_key": source_key,
                    "attributes": promotable_attributes(conn, source_key)}
        finally:
            conn.close()

    @app.post("/api/promotable/{source_key}")
    def api_promote(source_key: str, body: dict):
        """Promote a detail to a column, or send it back. Reversible: the row
        IS the promotion, so demoting deletes it and nothing has to remember a
        previous shape."""
        body = body or {}
        code = str(body.get("attribute_code") or "").strip()
        if not code:
            raise HTTPException(status_code=422, detail="attribute_code is required")
        promote = bool(body.get("promote", True))

        def apply(conn):
            set_promotion(conn, source_key, code, promote)
            return {"attribute_code": code, "promoted": promote,
                    "attributes": promotable_attributes(conn, source_key)}
        return _write(apply)

    @app.post("/api/fields/{source_key}")
    def api_update_fields(source_key: str, body: dict):
        """Rename / hide / reorder / reset — all reversible, none destructive."""
        body = body or {}
        def apply(conn):
            # The grid can name a column the side panel has never registered —
            # the panel registers on open, the grid's menu does not need it open.
            # Without this, hiding a column UPDATEd zero rows and returned 404,
            # which the grid then reloaded straight past. Additive by design, so
            # calling it here cannot disturb an existing view.
            #
            # PRESENCE-GATED like the GET path, and for the same reason: seeding
            # every BROWSE_COLUMNS key registered columns the source does not
            # publish (Category L1-L4 on a flat-label shop), and they then sat
            # in the manage list forever. The one key the caller is actually
            # touching is included even when absent, so hiding a column that
            # just lost its data still works.
            present = column_presence(conn, source_key)
            wanted = [key for key, _ in BROWSE_COLUMNS
                      if key in present or key == body.get("field_key")]
            ensure_fields(conn, source_key, wanted)
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

    @app.get("/api/appearance")
    def api_appearance():
        conn = read_conn()
        try:
            raw = settings_get(conn, "ui_appearance")
        finally:
            conn.close()
        if not raw:
            return {"appearance": None}
        try:
            return {"appearance": _appearance_value(json.loads(raw))}
        except (json.JSONDecodeError, HTTPException):
            # A stale preference must never keep either interface from opening.
            return {"appearance": None}

    @app.post("/api/appearance")
    def api_save_appearance(body: dict):
        appearance = _appearance_value(body)
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                save_settings(conn, {
                    "ui_appearance": json.dumps(
                        appearance, separators=(",", ":"), sort_keys=True,
                    ),
                })
                conn.commit()
            finally:
                conn.close()
        return {"appearance": appearance}

    # The display time zone travels the same road as the appearance, for the
    # same reason (spec 33 §6.9): one preference, read and written by both the
    # side panel and this web page, so the two can never disagree about what
    # time it is. Nothing here converts or writes a timestamp — the value is a
    # zone name and the conversion happens in the browser, on the way to the
    # screen.
    @app.get("/api/timezone")
    def api_time_zone():
        conn = read_conn()
        try:
            raw = settings_get(conn, "ui_time_zone")
        finally:
            conn.close()
        if not raw:
            return {"timezone": None}
        try:
            return {"timezone": _time_zone_value(json.loads(raw))}
        except (json.JSONDecodeError, HTTPException):
            # A stale or since-removed zone must never keep either interface
            # from opening; the browser's own fallback chain takes over.
            return {"timezone": None}

    @app.post("/api/timezone")
    def api_save_time_zone(body: dict):
        timezone_value = _time_zone_value(body)
        with dbmod.write_lock(app.state.db_path):
            conn = _write_conn()
            try:
                save_settings(conn, {
                    "ui_time_zone": json.dumps(
                        timezone_value, separators=(",", ":"), sort_keys=True,
                    ),
                })
                conn.commit()
            finally:
                conn.close()
        return {"timezone": timezone_value}

    @app.post("/api/settings")
    def api_save_settings(body: dict):
        body = _google_finance_setting_values(body)
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

    @app.get("/api/rates/google-finance")
    def api_google_finance_status():
        conn = read_conn()
        try:
            return google_finance_status(conn)
        finally:
            conn.close()

    @app.post("/api/rates/google-finance/refresh")
    def api_refresh_google_finance():
        """Owner-requested refresh, independent of automatic cadence."""
        try:
            with dbmod.write_lock(app.state.db_path):
                conn = _write_conn()
                fetcher = None
                try:
                    wanted = rates.currencies_in_use(conn)
                    if not wanted:
                        status = google_finance_status(conn)
                        return {
                            "ok": True, "updated": 0, "warnings": [],
                            "detail": "No non-USD currencies are in use yet.",
                            **status,
                        }
                    fetcher = HttpFetcher(**crawl_settings(conn))
                    batch = rates.refresh_now(conn, fetcher)
                    status = google_finance_status(conn)
                finally:
                    if fetcher is not None:
                        fetcher.close()
                    conn.close()
        except CrawlBlocked as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        updated = len(batch.rates)
        detail = f"Updated {updated} of {len(wanted)} currencies."
        return {
            "ok": True, "updated": updated, "warnings": batch.warnings,
            "detail": detail, **status,
        }

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
                # The name must match the property StagingAppScript.txt reads:
                # naming it anything else makes every send fail "unauthorized".
                "next_step": "Paste this into the Apps Script property FUNNEL_TOKEN "
                             "(Project Settings -> Script Properties). It takes effect "
                             "at once — no redeploy needed. The old token stops working "
                             "immediately."}

    # The four /api/outputs/google/* routes were here until 2026-08-11, together
    # with app.state.google_connect and the background thread that ran a desktop
    # OAuth flow on this machine. They are gone because the owner ruled that the
    # engine fetches and saves locally while the extension owns every Google
    # operation: the panel already holds a token from chrome.identity, and a
    # second sign-in on the engine meant one owner signing in twice, a
    # client_secret.json they had to create, and the SENSITIVE `spreadsheets`
    # scope — which Google's own Sheets documentation says drive.file replaces.
    #
    # See extension/drive.js and extension/sheets.js.

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
            "SELECT so.offer_id, sp.product_name_ar AS source_name, so.country_code_alpha2, "
            "       COUNT(pp.price_period_id) AS periods, "
            "       MAX(pp.last_confirmed_at) AS last_confirmed "
            "FROM price_period pp "
            "JOIN source_offer so ON so.offer_id = pp.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? GROUP BY so.offer_id "
            "HAVING COUNT(pp.price_period_id) > 1 "
            "ORDER BY periods DESC, sp.product_name_ar LIMIT 50", (source_key,))]

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
        from ..version import LATEST_SOURCE, MINIMUM_EXTENSION_VERSION, UPDATE_INSTRUCTIONS, VERSION

        worker = worker_health(conn)
        return {
            "version": __version__,
            # DISPLAY, never a control (the owner's standing rule, and
            # tests/test_settings_live_in_the_extension.py enforces it). The web
            # page cannot know which extension is installed in a browser it does
            # not run in, so it shows what the engine ships with and what it
            # requires, each named for the side it belongs to, and leaves the
            # installed-versus-required verdict to the panel that can see both.
            "extension_version": VERSION,
            "extension_version_source": LATEST_SOURCE,
            "minimum_extension_version": MINIMUM_EXTENSION_VERSION,
            "update_instructions": UPDATE_INSTRUCTIONS,
            "contract_version": CONTRACT_VERSION,
            "schema_version": dbmod.schema_version(conn),
            # THE SAME VERDICT /api/health PUBLISHES, from the `worker` dict
            # already computed above. It used to call worker_is_alive(), which
            # reads ONLY the runtime heartbeat — the single-heartbeat answer
            # worker_health() was written to supersede. So the Settings page
            # this feeds declared "Not running", and advised the owner to check
            # whether the engine had started at all, WHILE it was crawling. The
            # panel read the corrected one and was right; the engine's own page
            # read the old one and was wrong, which is the worse way round.
            "worker_alive": worker.get("alive") is True,
            # Says WHY when the answer is no, instead of leaving the owner
            # to infer it from a port that answers regardless.
            "worker": worker,
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

    @app.get("/api/storage/backups")
    def api_storage_backups():
        """The snapshots on this machine, newest first.

        WHY A ROUTE FOR SOMETHING THAT ALREADY EXISTED. `storage.list_backups` has
        worked for weeks and had no caller outside the engine's own page, so the panel
        could not offer a RESTORE: `/api/storage/restore` needs a `backup_path`, and
        the only place that knew the paths was a page the owner does not open.
        Measured 2026-09-02: the panel calls **none** of the nine `/api/storage/*`
        controls, and `bundle.py` `unpack` has no caller at all — so he had a backup
        button in his only interface and **not one restore control anywhere in it**
        (`R-81`).

        READ-ONLY AND NOT THROUGH `_storage_action`. That helper opens a write
        connection for actions that change something; this changes nothing, and a
        listing that took the writer's connection would contend with a crawl for no
        reason. `list_backups` only stats files.

        EVERY FIELD IS ONE THE PANEL NEEDS TO ASK ITS QUESTION. A restore is
        destructive, so the confirmation has to name WHICH snapshot: `name` to show,
        `modified_at` to order and date it, `bytes` so a truncated one is obvious
        before it is made live, `tag` because `pre-upgrade` and `reset` are different
        events, and `path` because that is what the restore route takes. Nothing else
        is returned — a panel that could be handed an arbitrary path is the shape
        `open-folder` deliberately refuses.
        """
        conn = read_conn()
        try:
            folder = backup_folder(conn, app.state.db_path)
        finally:
            conn.close()
        return {"folder": str(folder),
                "backups": storage_list_backups(app.state.db_path, folder)}

    # ---- the bundle the panel puts in Drive --------------------------------
    #
    # THE OWNER'S RULING, 2026-08-11: the engine fetches and saves locally, and
    # the extension owns every Google operation. So these two routes are the
    # whole of the engine's part in a Drive backup — it builds the bundle on
    # its own disk and hands over the bytes. It never sees the Google token, and
    # there is deliberately no route here that would accept one.
    #
    # That is not merely tidier. A token lent to this process would be a
    # credential living in a second place, on disk or in memory, for a job the
    # panel can do itself; the ruling removes it rather than protecting it.

    #: Built bundles are named so the newest can be found without keeping any
    #: state between the two requests. A build followed by a restart must still
    #: be downloadable, and app.state would not survive one.
    #: The export ceiling, named once. reports.export_source_table defaults to
    #: the same number and extension/sheets.js mirrors it as MAX_EXPORT_ROWS —
    #: three places that must agree, held together by the test beside this.
    EXPORT_ROW_LIMIT = 40_000

    BUNDLE_PREFIX = "scrapex-bundle-"

    #: The panel pack lifted out of the bundle, named so the two files of one
    #: backup share a stamp and sort together.
    PANEL_SUFFIX = "-panel.jsonl.gz"

    #: How many built bundles stay on disk. NOTHING pruned these before
    #: 2026-08-29 and each one is now 372.6 MB, so they accumulated for as long
    #: as the feature has existed. Two, not one: `/api/bundle/archive` serves the
    #: newest, and the predecessor survives so that rebuilding while the previous
    #: upload is still running does not delete the file that upload was named for.
    BUNDLE_KEEP = 2

    #: A staging directory younger than this may belong to a build still running,
    #: so the sweep leaves it alone. `start_engine` (scrapex/native.py) refuses to
    #: spawn a second engine on a held port, so within one port there is never a
    #: second builder -- but an engine started by hand elsewhere would share this
    #: folder, and deleting a live foreign build is worse than the leak it fixes.
    STAGING_ORPHAN_AGE_S = 6 * 3600

    #: Serialises the build. The panel re-enables its button the moment a request
    #: fails, so the 10-second deadline that used to fire mid-build invited a
    #: second click while the first was still packing -- two copies of the
    #: warehouse, two staging trees, and `_newest` free to hand the panel an
    #: archive from one build while it holds the manifest of the other.
    #:
    #: IN-PROCESS ON PURPOSE, and per app rather than per module so tests do not
    #: share one. A build is a thread inside this process; it cannot outlive a
    #: crash, so there is never a survivor to lock against. An on-disk lock would
    #: only add a stale one to clear.
    _bundle_build_lock = threading.Lock()

    #: `%Y%m%d-%H%M%S`, the stamp both files of a backup share.
    _BUNDLE_STAMP = re.compile(rf"^{re.escape(BUNDLE_PREFIX)}(\d{{8}}-\d{{6}})")

    def _bundle_folder(conn) -> Path:
        return backup_folder(conn, app.state.db_path)

    def _newest(folder: Path, suffix: str) -> Path | None:
        """The newest COMPLETE artefact of its kind, never one being written.

        THE SECOND HALF OF THAT SENTENCE IS THE WHOLE FUNCTION'S JOB, and it did
        not used to be. On 2026-08-30 this returned a `.zip` that a concurrent
        build had created and not yet filled — newest by mtime, zero bytes long —
        and the panel uploaded it to Drive as the owner's backup.

        WHAT ENFORCES IT IS THE NAMING, not a filter here. `bundle.pack` writes
        to `<name>.zip.part` and renames, and `*.zip` does not match `*.zip.part`
        — measured, not assumed. A guard was written here as well and then taken
        out again: it could not fire, and a condition that can never be true
        reads as a hazard that is still live.

        Two properties this relies on, both measured 2026-08-30:
        `Path.replace` is atomic on one filesystem, so this glob sees the name
        either not at all or complete; and it carries the write-completion mtime
        across the rename, so a renamed archive still sorts by when its bytes
        finished rather than by when its name first appeared.
        """
        made = sorted(folder.glob(f"{BUNDLE_PREFIX}*{suffix}"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        return made[0] if made else None

    def _prune_old_bundles(folder: Path, keep: int = BUNDLE_KEEP) -> None:
        """Keep the newest `keep` backups; delete every file of the older ones.

        BY STAMP RATHER THAN BY MTIME, because the two files of one backup do not
        share an mtime: `shutil.copy2` gives the panel pack the timestamp of the
        staged file it was copied from, minutes before the archive beside it is
        closed. Pruning each suffix on its own could therefore keep an archive
        from one build and a panel pack from another, and the panel uploads the
        pair as though they described the same warehouse.
        """
        stamps: dict[str, list[Path]] = {}
        for path in folder.glob(f"{BUNDLE_PREFIX}*"):
            found = _BUNDLE_STAMP.match(path.name)
            if path.is_file() and found:
                stamps.setdefault(found.group(1), []).append(path)
        for stamp in sorted(stamps, reverse=True)[keep:]:
            for path in stamps[stamp]:
                try:
                    path.unlink()
                except OSError:
                    # Windows refuses to unlink a file another process holds
                    # open. Housekeeping must never fail a backup that worked.
                    pass

    def _sweep_orphan_staging(folder: Path) -> None:
        """Remove staging trees left by a build that never reached its `finally`.

        The rmtree below runs in a `finally`, so an engine killed mid-build skips
        it and leaves the bundle expanded on disk -- a second full copy of the
        warehouse, 1.5 GB on the owner's machine. That is what actually survives
        a crash here; the build itself cannot.
        """
        cutoff = time.time() - STAGING_ORPHAN_AGE_S
        for path in folder.glob(f"{BUNDLE_PREFIX}*"):
            if not path.is_dir() or not _BUNDLE_STAMP.match(path.name):
                continue
            try:
                if path.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            shutil.rmtree(path, ignore_errors=True)

    @app.post("/api/bundle")
    def api_bundle_build():
        """Build a bundle, verify it, pack it, and describe what was made.

        `pack` refuses an unverified bundle, so a reply from this route is a
        promise that what the panel is about to upload reads back correctly.
        The alternative — pack now, check later — is how `latest.json` ends up
        naming an archive nobody can open.

        ONE AT A TIME. This route answers only when the whole job is done -- it
        does not stream, so on the owner's warehouse the panel waits 104 seconds
        for a first byte. Anything that makes him press the button twice used to
        start a second build over the top of the first.
        """
        if not _bundle_build_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail=(
                "a backup is already being built — try again shortly"))
        try:
            return _build_one_bundle()
        finally:
            _bundle_build_lock.release()

    def _build_one_bundle() -> dict:
        conn = read_conn()
        try:
            folder = _bundle_folder(conn)
        finally:
            conn.close()

        # Under the lock, so the only staging trees old enough to match are the
        # ones no build in this process is using.
        _sweep_orphan_staging(folder)

        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        staging = folder / f"{BUNDLE_PREFIX}{stamp}"
        archive = folder / f"{BUNDLE_PREFIX}{stamp}.zip"
        try:
            report = bundle.build(app.state.db_path, staging)
            if not report.ok:
                raise HTTPException(status_code=400, detail=(
                    "the bundle did not verify, so nothing was packed: "
                    + "; ".join(f"{f.path}: {f.problem}" for f in report.faults[:3])))
            described = bundle.pack(staging, archive)
            # THE PANEL PACK IS LIFTED OUT OF THE BUNDLE BEFORE THE STAGING
            # DIRECTORY GOES, and this is the whole reason this block exists.
            #
            # A browser has DecompressionStream for gzip and no zip reader at
            # all, and this repository ships no npm dependency on purpose. So
            # `panel.jsonl.gz` inside the archive is unreachable to the very
            # reader it was written for: extension/bundleview.js.
            #
            # MEASURED on the owner's warehouse, 2026-08-12: the bundle is
            # 207.9 MB raw and 36.0 MB zipped — the zip earns its 1.8 seconds
            # many times over and is not going anywhere. But panel.jsonl.gz is
            # 4.0 MB and ALREADY gzipped, so copying it out beside the archive
            # costs 11% more upload and removes the need for a zip reader
            # entirely. Compressing it again would be the mistake; carrying it
            # separately is the fix.
            pack_source = staging / bundle.PANEL_PACK
            panel_pack = folder / f"{BUNDLE_PREFIX}{stamp}{PANEL_SUFFIX}"
            if pack_source.is_file():
                # COPIED ASIDE AND RENAMED, for the reason `bundle.pack` is now
                # written the same way: a destination being copied INTO is a
                # file that exists, is newest by mtime, and is the wrong length,
                # and `_newest` would hand it to the panel as this backup's pack.
                # Four megabytes copy fast, but "fast" is not "atomic".
                building = panel_pack.with_name(
                    panel_pack.name + bundle.PARTIAL_SUFFIX)
                try:
                    shutil.copy2(pack_source, building)
                    building.replace(panel_pack)
                except BaseException:
                    building.unlink(missing_ok=True)
                    raise
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            # The staging directory is the bundle expanded; once packed it is a
            # second full copy of the warehouse sitting on the owner's disk.
            shutil.rmtree(staging, ignore_errors=True)

        # AFTER the build succeeded, never before: a build that fails must not
        # take the last archive that worked with it.
        _prune_old_bundles(folder)

        return {
            "name": archive.name,
            "bytes": described["bytes"],
            "sha256": described["sha256"],
            "files": described["files"],
            "uncompressed_bytes": described["uncompressed_bytes"],
            "bundle_format": bundle.BUNDLE_FORMAT,
            "engine_version": engine_version.VERSION,
            "created_at": utc_now_iso(),
            "panel_pack": {
                "name": panel_pack.name,
                "bytes": panel_pack.stat().st_size,
                "sha256": bundle.sha256_of(panel_pack),
            } if panel_pack.is_file() else None,
        }

    @app.get("/api/bundle/archive")
    def api_bundle_archive():
        """Stream the newest built bundle so the panel can upload it.

        The path is derived here and never taken from the caller: this route
        reads from the backup folder and nowhere else, so no request can ask it
        for a file outside one directory.
        """
        conn = read_conn()
        try:
            folder = _bundle_folder(conn)
        finally:
            conn.close()

        archive = _newest(folder, ".zip")
        if archive is None:
            raise HTTPException(status_code=404, detail=(
                "no bundle has been built yet — POST /api/bundle first"))
        return FileResponse(
            archive, media_type="application/zip", filename=archive.name)

    @app.get("/api/export/{source_key}")
    def api_export_rows(source_key: str):
        """The rows the panel writes into a Google Sheet.

        THE LAST GAP IN THE OWNER'S RULING OF 2026-08-11. The extension owns
        every Google operation, and extension/sheets.js could already create a
        spreadsheet and fill a tab — but the rows had nowhere to come from. The
        panel's own /api/records is paginated at 100 and carries the COMPACT
        card shape; /export/{key}.xlsx is a binary workbook the panel will not
        ship a library to parse. So the menu entry sat disabled, saying so.

        This is the same `export_source_table` the .xlsx and the Apps Script
        funnel already use — one expression of what an export IS, rather than a
        third. A separate query here would drift from those two, which is the
        drift `fields.column_order` exists to prevent.

        BOUNDED (A8) at the same 40,000 rows the function's own default sets and
        the panel's MAX_EXPORT_ROWS mirrors. `truncated` is reported rather than
        left to be inferred from a row count nobody compares — a spreadsheet
        that quietly stops at forty thousand looks exactly like a business with
        forty thousand products.
        """
        conn = read_conn()
        try:
            # THE MANIFEST, which is what /api/sources answers from and
            # therefore what the panel's Data page offers. The first version of
            # this checked `list_sources`, which reads `source_site` in the
            # WAREHOUSE — a different set. On a database that has been
            # initialised but not yet crawled the manifest names twelve sources
            # and the warehouse none, so every export the panel offered was
            # refused with "no source called MADAR" while the card for MADAR sat
            # on the screen. Validating against a set the caller cannot see is
            # worse than not validating.
            known = {entry.source_key for entry in app.state.manifest.sources}
            if source_key not in known:
                raise HTTPException(status_code=404, detail=(
                    f"no source called {source_key!r} — the panel asked for "
                    "something the warehouse does not have"))
            header, rows = export_source_table(conn, source_key)
        finally:
            conn.close()
        return {
            "source_key": source_key,
            "header": header,
            "rows": rows,
            "truncated": len(rows) >= EXPORT_ROW_LIMIT,
            "limit": EXPORT_ROW_LIMIT,
        }

    @app.get("/api/bundle/panel-pack")
    def api_bundle_panel_pack():
        """Stream the newest panel pack — the one file a browser can read.

        Separate from the archive above rather than a parameter on it, for the
        same reason that route takes no arguments at all: two fixed routes
        cannot be pointed anywhere, and a `?which=` would be the first place a
        path would eventually arrive from the caller.
        """
        conn = read_conn()
        try:
            folder = _bundle_folder(conn)
        finally:
            conn.close()

        pack = _newest(folder, PANEL_SUFFIX)
        if pack is None:
            raise HTTPException(status_code=404, detail=(
                "no panel pack has been built yet — POST /api/bundle first"))
        # `application/gzip`, and the encoding is NOT declared as a Content-
        # Encoding: this is a gzip FILE being transferred, not a response the
        # browser should transparently inflate. Getting that wrong would hand
        # bundleview.js already-decompressed bytes it would then try to
        # decompress again.
        return FileResponse(
            pack, media_type="application/gzip", filename=pack.name)

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

    @app.post("/api/storage/start-fresh")
    def api_storage_start_fresh(body: dict):
        """Seal the warehouse aside and put an empty one in its place.

        The most destructive-LOOKING action here, so the guards are explicit:
        the exact phrase must be typed (a checkbox is one habitual click; typing
        is a decision), and a running crawl refuses it — resetting mid-ingest
        would tear the run. Like restore, no connection of ours may be open
        during the switch, or Windows fails the rename outright.
        """
        if (body or {}).get("confirm", "") != "start fresh":
            raise HTTPException(status_code=400,
                                detail='Type "start fresh" to confirm.')
        conn = read_conn()
        try:
            running = list_jobs(conn, active_only=True)
        finally:
            conn.close()
        if running:
            raise HTTPException(
                status_code=409,
                detail="A crawl is running. Let it finish or cancel it first — "
                       "resetting under a live run would tear it in half.")
        if app.state.runner is not None:
            app.state.runner.release_database()
        with dbmod.write_lock(app.state.db_path):
            try:
                result = start_fresh(
                    app.state.db_path,
                    lambda path: EngineDatabase(path).initialize())
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
        _follow_the_committed_location(app)
        return result

    def _follow_the_committed_location(app_) -> None:
        """This PROCESS catches up with a location that has already been committed.

        Both records on disk — the pointer and the registry — are written
        together by storage.commit_live_database, at the commit point. What is
        left for a route is only the in-memory half: the running engine keeps a
        DatabaseRegistry object and a db_path string, and a move or a compaction
        that did not refresh them would leave this server writing into a file the
        owner has been told is no longer live.

        This used to be eight lines duplicated between the move route and the
        compact route, and absent from every other caller of those operations —
        which is why undo_compaction, written and tested and merely unrouted,
        would have shipped broken the day a button reached it.
        """
        if app_.state.databases is None:
            return
        app_.state.databases = DatabaseRegistry(
            EngineDatabase(app_.state.db_path),
            app_.state.databases.pointer_file,
        )
        # Written here as well as at the commit point, and not instead of it:
        # storage only knows the registry named by the process-wide
        # REGISTRY_FILE, while THIS app may have been handed a different one
        # (a --registry session, a test). The one it was handed is the one that
        # must end up correct, so the object that owns it writes it.
        app_.state.databases.write()

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
        _follow_the_committed_location(app)
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

    # ---- the dry route: what a source WOULD do, for every source type ---------

    @app.get("/api/dry/{source_key}")
    def api_dry(source_key: str):
        """«اعمل مسار dry لكل المصادر مهما اختلفت نوعها» — one route, both registries.

        `POST /api/jobs` below validates against `app.state.manifest` alone, so
        muqawil answered `404 unknown source_key 'contractors'` while
        `/api/table/contractors` served 11,059 rows. This route asks both, and a key
        either register knows answers 200.

        BOTH CONNECTIONS ARE SEALED BEFORE ANY PAYLOAD WORK. `refuse_writes` denies
        every statement able to change the warehouse, which matters on exactly one
        call: `disown_impostors` deletes when `dry_run=False`.

        IMPORTED HERE AND NOT AT MODULE SCOPE, and the reason is measured rather than
        stylistic: one import line at the top of this 3,800-line module renumbers
        every line below it, and 26 citations across six of the nine documents
        `tests/test_the_documents_cite_what_they_claim.py` guards point into this
        file. Adding it there moved 36 documented lines, six of them RECORDS of past
        drift that must not be renumbered. This route sits below every cited line, so
        the import belongs where the route is.
        """
        # DO NOT MOVE THIS TO MODULE SCOPE. It is deliberate, it is measured, and the
        # primary session ruled on 2026-08-27 that the trade is not worth a style
        # point: see the paragraph above for the 36 documented lines it would shift.
        from ..dryrun import dry_payload, refuse_writes, unknown_key_detail

        general = general_read_conn()
        price = read_conn()
        try:
            refuse_writes(general)
            refuse_writes(price)
            payload = dry_payload(source_key, general=general, price=price,
                                  manifest=app.state.manifest)
        finally:
            general.close()
            price.close()
        if payload is None:
            raise HTTPException(status_code=404, detail=unknown_key_detail(
                source_key, manifest=app.state.manifest))
        return payload

    # ---- jobs (spec 4/23/24: the panel enqueues and polls, never executes) ---

    @app.post("/api/jobs")
    def api_create_job(body: dict):
        body = body or {}
        source_keys = body.get("source_keys") or []
        if isinstance(source_keys, str):
            source_keys = [source_keys]
        if not source_keys:
            raise HTTPException(status_code=400, detail="source_keys is required")
        # `R-78`: ASKED OF THE REGISTRY, NOT THE FILE. `muqawil_org` lives in
        # `source_site` since `0014` and answered 404 here -- `REQ-45`, and the reason
        # every muqawil crawl to date ran from a terminal. `UnknownSource` subclasses
        # `LookupError` alongside `KeyError`, so this still fails BEFORE queueing: a key
        # accepted here and refused inside the run is the delayed failure `R-71`
        # measured and `OP-92` records.
        sources = SourceResolver(app.state.manifest,
                                 lambda: dbmod.connect(app.state.db_path))
        for key in source_keys:  # fail before queueing, not mid-crawl
            try:
                sources.get(key)
            except LookupError:
                raise HTTPException(status_code=404, detail=f"unknown source_key {key!r}")
        # AND WHICH COLLECTOR READS IT, decided here for the same reason the key is
        # validated here. `REQ-45` made this route accept `muqawil_org`; the worker then
        # handed it to `capture_source`, the PRICE collector, whose result carries
        # observations, duplicates, products and variants -- none of which a contractor
        # listing crawl produces. So the key was accepted and the wrong thing ran.
        #
        # `directories.BUILDERS` IS THE REGISTRY AND NOT A NEW COLUMN. It is keyed by
        # `site_key`, it is what `--source` already names, and it already refuses a
        # mistyped key rather than defaulting. A `source_site.collector` column would be
        # a second place for a fact this one holds.
        directory_keys = [key for key in source_keys if key in directories.BUILDERS]
        if directory_keys and len(directory_keys) != len(source_keys):
            # ONE DENOMINATOR PER JOB. A price job counts sources, a directory job counts
            # cells, and a progress bar mixing them cannot say what is left of either.
            raise HTTPException(
                status_code=400,
                detail="a directory crawl and a price crawl are different jobs: "
                       f"{directory_keys} are directories and "
                       f"{[k for k in source_keys if k not in directory_keys]} are not. "
                       "Queue them separately.")
        job_kind = directoryjob.JOB_KIND if directory_keys else "crawl"
        if job_kind == directoryjob.JOB_KIND and len(source_keys) != 1:
            # The runner refuses this too. Refused here as well because the message a
            # person reads should come from the door they knocked on, not from a job
            # that started and stopped.
            raise HTTPException(
                status_code=400,
                detail="a directory crawl runs one directory at a time, and this names "
                       f"{len(source_keys)}: {source_keys}")
        try:
            run_mode = RunMode(body.get("run_mode", RunMode.UPDATE.value))
        except ValueError:
            raise HTTPException(status_code=400, detail="run_mode must be "
                                f"{[m.value for m in RunMode]}")
        # RESUME: continue an interrupted crawl from the pages it already kept,
        # instead of from the top. The worker reads `partial_source` out of the
        # checkpoint (jobs.run_job_once) and hands capture `resume=True`, which
        # is what turns the journal into a skip set instead of rubbish to clear.
        # Seeding it here — rather than reviving the paused job — is deliberate:
        # the job that filled the journal is usually gone (cancelled, or lost
        # with the runtime) while its pages are still on disk.
        resume = bool(body.get("resume"))
        checkpoint = None
        if resume:
            if len(source_keys) != 1:
                # One checkpoint holds one partial_source, so a two-source
                # resume could only be honoured for one of them. Refusing beats
                # silently starting the other from the top.
                raise HTTPException(status_code=400,
                                    detail="resume takes exactly one source_key")
            kept = localinbox.journal_state(localinbox.JOURNAL_DIR, source_keys[0])
            if not kept["pages"]:
                # Nothing to continue. Queueing a full crawl under the word
                # 'resume' would be the opposite of what was asked for.
                raise HTTPException(
                    status_code=409,
                    detail=f"{source_keys[0]} has no kept pages to resume — "
                           "start a run instead")
            checkpoint = {"completed_source_keys": [], "errors": [], "succeeded": 0,
                          "partial_source": source_keys[0]}
        conn = read_conn()
        try:
            ensure_schema(conn)
            job_ref = create_job(conn, source_keys, run_mode, checkpoint=checkpoint,
                                 job_kind=job_kind)
        finally:
            conn.close()
        return {"job_ref": job_ref, "status": "queued", "source_keys": source_keys,
                "run_mode": run_mode.value, "resume": resume}

    @app.get("/api/jobs")
    def api_list_jobs(limit: int = 20, active_only: bool = False):
        conn = read_conn()
        try:
            jobs = list_jobs(conn, limit=limit, active_only=active_only)
            # A queued job needs to say WHY it is queued, and that answer is not
            # in its own row: it is in the row of the job holding the worker.
            # Computed here, where the whole list is in hand.
            queue = _queue_state(conn)
        finally:
            conn.close()
        return {"jobs": [_job_view(j, queue) for j in jobs], "queue": queue}

    @app.get("/api/jobs/{job_ref}")
    def api_get_job(job_ref: str):
        conn = read_conn()
        try:
            job = get_job(conn, job_ref)
            queue = _queue_state(conn) if job is not None else None
        finally:
            conn.close()
        if job is None:
            raise HTTPException(status_code=404, detail=f"unknown job {job_ref!r}")
        return _job_view(job, queue)

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
    def api_job_logs(job_ref: str, limit: int | None = None):
        """Every entry by default.

        THE CAP WAS IN TWO PLACES and removing either alone changes nothing.
        The panel asked for `?limit=200` (app.js) and this route then clamped
        whatever it was given to 200 as well — so a run whose 400th log line
        explains the failure had that line silently discarded twice over, under
        a heading that read "Last 200 log entries" as though 200 were all there
        were.

        `total` travels with the entries so the panel can state what it is
        showing out of what exists, and an explicit `limit` still works for a
        caller that genuinely wants a tail.
        """
        conn = read_conn()
        try:
            if get_job(conn, job_ref) is None:
                raise HTTPException(status_code=404, detail=f"unknown job {job_ref!r}")
            entries = job_logs(conn, job_ref,
                               limit=None if limit is None else max(int(limit), 1))
            total = job_log_count(conn, job_ref)
        finally:
            conn.close()
        return {"job_ref": job_ref, "entries": entries, "total": total,
                "truncated": len(entries) < total}

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
                    ensure_schema(conn)
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
            "notices": list(r.notices),
        }

    # WHICH CODE IS THIS PROCESS RUNNING? Sealed HERE, on the last line before the
    # app is handed to the server, because this is the moment every module the
    # engine will serve with has been imported and none of them can have changed
    # yet. Sealing earlier misses `webui.app` itself — the module the incident of
    # 2026-08-23 was actually about; sealing later takes the baseline after the
    # edit it exists to notice. See `scrapex/provenance.py`.
    if app.state.runner is not None:
        app.state.runner.start()
    provenance.seal()
    return app


def _is_implemented(entry) -> bool:
    return entry.family in _BUILDERS


# Which basis wins when a job's denominator is assembled from several sources.
# A total that mixes a measurement with an estimate IS an estimate — the weakest
# contributor names the whole, because claiming otherwise is how an undated guess
# gets displayed as a fact.
_BASIS_RANK = {"measured": 0, "declared": 1, "estimate": 2}


def _fetch_progress(job: dict) -> dict:
    """Requests fetched, what that is a fraction OF, and where the total came from.

    THE ONE PLACE this is computed. The panel's bar, its counters and the web
    Jobs page all read this, so they cannot drift into disagreeing about how far
    along a crawl is — and there is exactly one definition of the numerator to
    get wrong.

    `progress_total` (the number of SOURCES) is not this and never was: a
    one-source job is 0/1 for its whole duration, which is the 0% the owner
    watched for 18 minutes while 1,030 requests succeeded behind it. Sites done
    remains reported, separately and honestly, as its own count.

    `expected` is None when nothing knows the total — a source's first ever
    crawl. Callers MUST render that as unknown; a bar drawn at 0% against it is
    the original defect.
    """
    counters = job.get("counters") or {}
    slots = counters.get("sources") or {}
    # Sources already merged at their boundary, plus whatever the ones still
    # fetching have counted so far. A finished source is in the merged total, so
    # its slot is deliberately not added again.
    merged = int(counters.get("requests") or 0)
    in_flight = sum(int((slot or {}).get("requests") or 0)
                    for slot in slots.values()
                    if (slot or {}).get("state") == "fetching")
    requests = merged + in_flight

    expectations = [slot for slot in slots.values()
                    if slot and slot.get("expected")]
    unknown = [key for key, slot in slots.items()
               if not (slot or {}).get("expected")]
    expected = sum(int(slot["expected"]) for slot in expectations) or None
    basis = None
    as_of = None
    if expected is not None:
        basis = max((slot.get("basis") or "estimate" for slot in expectations),
                    key=lambda name: _BASIS_RANK.get(name, 2))
        # The OLDEST date among the estimates, because an estimate is only as
        # fresh as its stalest part.
        dates = sorted(slot["as_of"] for slot in expectations if slot.get("as_of"))
        as_of = dates[0] if dates else None
    return {
        "requests": requests,
        "expected": expected,
        "basis": basis,               # measured | declared | estimate | None
        "as_of": as_of,               # the estimate's date, when it is one
        # Sources with no denominator at all. Named so the panel can say which
        # site it cannot predict rather than quietly leaving it out of the total.
        "unknown_sources": sorted(unknown),
        "sources": slots,
    }


def _queue_state(conn) -> dict:
    """Which jobs hold the worker, and which wait behind them, in firing order.

    The engine runs up to `capacity` jobs at once (jobs.job_capacity — the
    owner's "Sites crawled at the same time" setting). A second run waits only
    when that budget is full, and until now the panel said "queued" with no
    reason at all: the concurrency added in 63dc24b is WITHIN a job across its
    sources, so a crawl-behind-a-crawl looked like the parallel feature failing.

    Both facts are stated here, from the one place that knows them, so the panel
    can say "running alongside N others" or "waiting for a slot" and never
    disagree with what the worker will actually do.
    """
    from ..jobs import job_capacity

    capacity = job_capacity(conn)
    holders = conn.execute(
        "SELECT job_ref, source_keys FROM crawl_job "
        "WHERE status IN ('running','preparing','resuming','pausing','cancelling') "
        "ORDER BY job_id").fetchall()
    waiting = conn.execute(
        "SELECT job_ref, source_keys FROM crawl_job WHERE status = 'queued' "
        "ORDER BY job_id").fetchall()
    return {
        "capacity": capacity,
        "running": [{"job_ref": row[0], "source_keys": json.loads(row[1] or "[]")}
                    for row in holders],
        # Position 1 is the next job to start. A slot is free the moment fewer
        # than `capacity` jobs are running, and the worker fills it on its next
        # poll (half a second) — so a job whose position is within the free slots
        # is starting now, not waiting.
        "waiting": [{"job_ref": row[0], "source_keys": json.loads(row[1] or "[]"),
                     "position": index + 1}
                    for index, row in enumerate(waiting)],
    }


def _queued_behind(job: dict, queue: dict | None) -> dict | None:
    """What this queued job is waiting for, or None if it is not waiting.

    Everything here is a fact from the queue, never a reassurance: which jobs
    hold the budget, which sites they are crawling, this job's place in line, and
    whether a slot is already free for it (the worker starts it on the next
    poll). The panel turns it into a sentence; nothing invents a finish time for
    a job ahead, because that job's own denominator may be unknown and a
    made-up wait is worse than an honest "when a slot frees".
    """
    if queue is None or job["status"] != JobStatus.QUEUED.value:
        return None
    mine = next((item for item in queue["waiting"]
                 if item["job_ref"] == job["job_ref"]), None)
    if mine is None:
        return None
    free_slots = max(0, queue["capacity"] - len(queue["running"]))
    return {
        "position": mine["position"],
        "capacity": queue["capacity"],
        "running_count": len(queue["running"]),
        "running": queue["running"],
        # True when this job is within the free slots — it is not really waiting,
        # it starts on the next poll. The panel must not call that "queued".
        "starting_now": mine["position"] <= free_slots,
    }


def _job_view(job: dict, queue: dict | None = None) -> dict:
    """The shape the side panel polls: aggregated progress only (spec 25) — never
    raw records, and everything needed to redraw the mini-player from scratch
    after the panel was closed."""
    total = job.get("progress_total") or 0
    done = job.get("progress_done") or 0
    return {
        "job_ref": job["job_ref"],
        "job_kind": job.get("job_kind", "crawl"),
        "status": job["status"],
        "run_mode": job["run_mode"],
        "source_keys": job["source_keys"],
        "current_source_key": job["current_source_key"],
        "stage": job["stage"],
        # SITES done, which is all this ever measured. It keeps its name and
        # loses the percentage: 0/1 is a true statement about a one-source job
        # and "0%" was not.
        "progress": {
            "done": done,
            "total": total,
            **({"unit": "organizations"}
               if job.get("job_kind") == "organization_enrichment" else {}),
        },
        # PAGES fetched against a stated denominator — what the bar draws.
        "fetch": _fetch_progress(job),
        # Why this job is not moving, when it is not. None for the job that holds
        # the worker and for anything already finished.
        "queued_behind": _queued_behind(job, queue),
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
    from datetime import datetime

    return datetime.now(UTC).date().isoformat()


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
    # An EDIT arrives as the whole existing entry merged with the changed
    # fields, so it carries `extract` as the manifest stores it — a list — and
    # not the form's flat kind/scope. Rebuilding from the defaults here would
    # quietly rewrite a commodity source into product_prices/census and drop
    # its materials and regions, on an edit that only renamed the shop.
    existing = form.get("extract")
    if isinstance(existing, list) and existing and "kind" not in form and "scope" not in form:
        extract = existing
    data = {
        "source_key": (form.get("source_key") or "").strip().upper(),
        "source_name": (form.get("source_name") or "").strip(),
        # Both keys, or a site added through the form with an Arabic name
        # has nowhere to put it. The form collects English as the primary
        # name (required) and Arabic beside it when the site has one.
        "source_name_ar": (form.get("source_name_ar") or "").strip(),
        "base_url": (form.get("base_url") or "").strip(),
        "family": form.get("family"),
        "cadence": form.get("cadence", Cadence.DAILY.value),
        "authority": form.get("authority", Authority.SHOP.value),
        "fetcher": form.get("fetcher", Fetcher.HTTP.value),
        "default_region": (form.get("default_region") or "*").strip() or "*",
        "vat_mode": form.get("vat_mode", VatMode.INCLUSIVE.value),
        "active": bool(form.get("active", False)),
        "extract": extract if isinstance(extract, list) else [extract],
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
    if form.get("fold_variants"):
        data["fold_variants"] = True
    identity = {k: v for k, v in (form.get("identity") or {}).items() if v not in (None, "")}
    if identity:
        data["identity"] = identity

    # EVERYTHING ELSE THE MODEL HAS, carried rather than dropped. The block
    # above names seventeen fields and normalises them; SourceEntry has
    # twenty-nine, and an EDIT arrives as the whole stored entry merged with the
    # changed ones — so the twelve unnamed were rebuilt out of existence every
    # time the panel saved a rename. Measured, not guessed: api, brand,
    # default_language, max_drop_pct, min_expected_rows, notes, robots,
    # robots_custom, tax, taxonomy, unit_charter, user_agent.
    #
    # `user_agent` alone breaks a source outright — Zid 403s a non-browser
    # client, which is why that field exists — and `unit_charter` is days of
    # measured per-source rules. manifest_io.py already carries the same warning
    # about the WRITER, and was fixed there; the fields never reached it,
    # because they were gone before update_source was called.
    for field in SourceEntry.model_fields:
        if field not in data and field in form:
            data[field] = form[field]
    return SourceEntry.model_validate(data)
