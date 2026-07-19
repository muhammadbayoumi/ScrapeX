"""Output destinations as one service layer (spec sections 21, 22, 23).

Every destination answers the same three questions in the same shape, because
the interface asks them in the same way:

    status(...)  -> can I use this right now, and if not, what exactly is missing?
    run(...)     -> do it, and tell me where the result landed
    last run     -> what happened the previous time, in the owner's words

Nothing here re-implements publishing: Excel and Google both go through
`publish.publish_source`, so the two sinks keep emitting identical columns in
identical order. This module only adds configuration, readiness and reporting.

Network and Google clients arrive through injectable seams (`sink`, `client`,
`connector`), so every path below is tested without credentials or a network.
"""
from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import settings
from .fields import ORIGINAL_SCHEMA
from .ingest import _canon_amount
from .payload import PAYLOAD_VERSION, FunnelPayload, utc_now_iso
from .publish import publish_source
from .reports import export_source_table
from .vocab import ExtractKind, PayloadClient

EXCEL = "excel"
APPS_SCRIPT = "apps_script"
GOOGLE = "google_drive"

# Spec 22: the funnel accepts a batch at a time. The Apps Script side has a
# 6-minute execution budget, so a batch that is too large fails as a timeout
# rather than as an error anyone can read.
FUNNEL_MAX_ROWS = 20_000


class NotConfiguredError(RuntimeError):
    """The destination is missing something the owner must supply first.

    Carries the same sentence the UI shows, so the reason never has to be
    guessed at or reworded in two places.
    """


@dataclass
class RunResult:
    ok: bool
    rows: int = 0
    location: str = ""
    detail: str = ""
    at: str = ""

    def as_state(self) -> dict:
        return {"ok": self.ok, "rows": self.rows, "location": self.location,
                "detail": self.detail, "at": self.at or utc_now_iso()}


def _record(conn: sqlite3.Connection, state_key: str, result: RunResult) -> RunResult:
    settings.set_state(conn, state_key, result.as_state())
    return result


def _module_available(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


# =============================================================================
# Excel (spec 21)
# =============================================================================

def excel_folder(conn: sqlite3.Connection) -> Path:
    """Where workbooks are written. Empty setting means the packaged default."""
    from .localsheets import DEFAULT_EXPORT_DIR

    saved = settings.get(conn, "excel_folder")
    return Path(saved).expanduser() if saved else DEFAULT_EXPORT_DIR


def excel_status(conn: sqlite3.Connection) -> dict:
    folder = excel_folder(conn)
    workbook = settings.get(conn, "excel_workbook")
    path = folder / f"{workbook}.xlsx"
    installed = _module_available("openpyxl")
    return {
        "key": EXCEL,
        "label": "Excel workbook",
        "ready": installed,
        "blocker": "" if installed else
                   'Excel export needs the local extra: pip install -e ".[local]"',
        "folder": str(folder),
        "workbook": workbook,
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "schema": settings.get(conn, "excel_schema"),
        # Spec 21 asks the interface to state the workbook's structure and its
        # update behaviour, because both are surprising if you assume otherwise.
        "structure": "One workbook, one tab per source, named after the source key.",
        "update_behaviour": ("Re-exporting a source REPLACES that source's tab and "
                             "leaves every other tab untouched. The workbook is "
                             "never deleted and no other file is written."),
        "last": settings.get_state(conn, "excel_last"),
    }


def excel_export(conn: sqlite3.Connection, source_keys: list[str], *,
                 sink=None, schema: str | None = None) -> RunResult:
    """Write one tab per source into the configured workbook."""
    from .localsheets import LocalSink

    if not source_keys:
        raise NotConfiguredError("Pick at least one source to export.")
    status = excel_status(conn)
    if not status["ready"]:
        raise NotConfiguredError(status["blocker"])

    sink = sink if sink is not None else LocalSink()
    schema = schema or settings.get(conn, "excel_schema") or ORIGINAL_SCHEMA
    folder, workbook = status["folder"], status["workbook"]
    total, location, failures = 0, "", []
    for key in source_keys:
        try:
            rows, location = publish_source(conn, key, sink, folder, workbook, schema=schema)
            total += rows
        except ValueError as exc:          # nothing to publish for that source
            failures.append(f"{key}: {exc}")
    conn.commit()                          # apply_schema registers new columns

    ok = total > 0
    detail = (f"Wrote {total} rows into {len(source_keys) - len(failures)} tab(s)."
              if ok else "Nothing was written.")
    if failures:
        detail += " Skipped — " + "; ".join(failures)
    return _record(conn, "excel_last",
                   RunResult(ok=ok, rows=total, location=location, detail=detail))


# =============================================================================
# Apps Script funnel (spec 22)
# =============================================================================

def apps_script_status(conn: sqlite3.Connection) -> dict:
    from .funnel import DEFAULT_OUTBOX_DIR, OUTBOX_ALARM_THRESHOLD

    url, url_source = settings.resolve(conn, "funnel_url")
    token, token_source = settings.resolve(conn, "funnel_token")
    outbox = DEFAULT_OUTBOX_DIR
    pending = len(list(outbox.glob("*.json"))) if outbox.is_dir() else 0
    missing = [name for name, value in (("Deployment URL", url), ("token", token)) if not value]
    return {
        "key": APPS_SCRIPT,
        "label": "Google Sheets via Apps Script",
        "ready": not missing,
        "blocker": "" if not missing else
                   f"Missing: {' and '.join(missing)}. Deploy the script, then save both here.",
        "url": url,
        "url_source": url_source,
        "token_is_set": bool(token),
        "token_hint": settings.hint(token),
        "token_source": token_source,
        "outbox_dir": str(outbox),
        "outbox_pending": pending,
        "outbox_threshold": OUTBOX_ALARM_THRESHOLD,
        "max_rows": FUNNEL_MAX_ROWS,
        # Stated here so no screen can imply a guarantee the transport does not give.
        "limits": ("Batches are signed with a shared token over HTTPS. Request "
                   "signing (HMAC) and adaptive batch sizing described in the "
                   "product spec are NOT implemented — a batch that exceeds the "
                   "Apps Script time budget is refused up front instead."),
        "last": settings.get_state(conn, "apps_script_last"),
    }


def apps_script_script_text() -> str:
    """The Apps Script source the owner pastes into their sheet (Copy Script)."""
    path = Path(__file__).resolve().parent.parent / "apps_script" / "StagingAppScript.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def rotate_funnel_token(conn: sqlite3.Connection) -> str:
    """Mint a new shared token and return it ONCE, so it can be pasted into the
    script. It is never readable again — only its last four characters are."""
    token = secrets.token_urlsafe(32)
    settings.save(conn, {"funnel_token": token})
    return token


def _funnel_client(conn: sqlite3.Connection):
    from .funnel import FunnelClient

    status = apps_script_status(conn)
    if not status["ready"]:
        raise NotConfiguredError(status["blocker"])
    return FunnelClient(endpoint=status["url"], token=settings.get(conn, "funnel_token"))


def apps_script_test(conn: sqlite3.Connection, *, client=None) -> RunResult:
    """Send one self-test row and report exactly what came back (spec 22 Test)."""
    from .funnel import FunnelDeliveryError, OutboxAlarm

    client = client if client is not None else _funnel_client(conn)
    payload = FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="FUNNEL_SELFTEST",
        kind=ExtractKind.PRODUCT_PRICES, client=PayloadClient.CLI,
        scraped_at=utc_now_iso(), source_url="scrapex://funnel-test",
        header=["check"], rows=[["ok"]])
    try:
        chunks = client.send(payload)
    except (FunnelDeliveryError, OutboxAlarm) as exc:
        return _record(conn, "apps_script_last",
                       RunResult(ok=False, detail=f"The funnel refused the test: {exc}"))
    return _record(conn, "apps_script_last", RunResult(
        ok=True, rows=1, detail=f"The funnel accepted the self-test ({chunks} chunk(s)). "
                                "Look for a FUNNEL_SELFTEST row in the _INBOX tab."))


def _canonical_cell(value) -> str:
    """Rows cross an engine boundary here, so every cell leaves as a canonical
    STRING. Sending a Python float would hand the Apps Script side a value whose
    text form differs from ours (15.0 vs 15) and quietly fork the record hash."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, Decimal)):
        try:
            return _canon_amount(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return str(value)
    return str(value)


def apps_script_send(conn: sqlite3.Connection, source_key: str, *, client=None) -> RunResult:
    """Deliver one source's current prices through the funnel."""
    from .funnel import FunnelDeliveryError, OutboxAlarm

    header, rows = export_source_table(conn, source_key)
    if not rows:
        raise NotConfiguredError(
            f"Nothing to send for {source_key} — crawl and ingest it first.")
    if len(rows) > FUNNEL_MAX_ROWS:
        raise NotConfiguredError(
            f"{len(rows)} rows exceeds the {FUNNEL_MAX_ROWS}-row batch limit. Export "
            "to Excel instead, or narrow the source.")

    client = client if client is not None else _funnel_client(conn)
    payload = FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key=source_key,
        kind=ExtractKind.PRODUCT_PRICES, client=PayloadClient.CLI,
        scraped_at=utc_now_iso(), source_url=f"scrapex://export/{source_key}",
        header=list(header), rows=[[_canonical_cell(c) for c in row] for row in rows])
    try:
        chunks = client.send(payload)
    except (FunnelDeliveryError, OutboxAlarm) as exc:
        return _record(conn, "apps_script_last", RunResult(
            ok=False, rows=len(rows),
            detail=f"Delivery failed and the batch is kept in the outbox: {exc}"))
    return _record(conn, "apps_script_last", RunResult(
        ok=True, rows=len(rows),
        detail=f"Delivered {len(rows)} rows in {chunks} chunk(s)."))


# =============================================================================
# Google Drive and Sheets (spec 23)
# =============================================================================

def google_status(conn: sqlite3.Connection) -> dict:
    from .gdrive import CLIENT_SECRET_PATH, TOKEN_PATH

    libs = _module_available("googleapiclient")
    connected = Path(TOKEN_PATH).exists()
    has_secret = Path(CLIENT_SECRET_PATH).exists()
    if not libs:
        blocker = 'Google support needs the extra: pip install -e ".[google]"'
    elif not has_secret:
        blocker = (f"Missing {CLIENT_SECRET_PATH}. Create a Google Cloud OAuth "
                   "client (Desktop app) and save its JSON there.")
    elif not connected:
        blocker = "Not signed in yet — use Continue with Google."
    else:
        blocker = ""
    return {
        "key": GOOGLE,
        "label": "Google Drive and Sheets",
        "ready": connected and libs,
        "blocker": blocker,
        "connected": connected,
        "client_secret_present": has_secret,
        "token_path": str(TOKEN_PATH),
        "folder": settings.get(conn, "google_folder"),
        "workbook": settings.get(conn, "google_workbook"),
        # Spec 23 asks for the connected account. Least-privilege scopes
        # (drive.file + spreadsheets) do NOT include an identity scope, so the
        # email is genuinely not available — saying so beats inventing a
        # placeholder or widening the scope just to fill a line of UI.
        "account": "",
        "account_note": ("The signed-in email is not requested: ScrapeX asks only for "
                         "access to the files it creates, not your identity."),
        "scopes": ["drive.file (only files ScrapeX creates)", "spreadsheets (their contents)"],
        "last": settings.get_state(conn, "google_last"),
    }


def google_connect(*, connector=None) -> None:
    """Run the one-time browser sign-in. Blocking: the caller decides threading."""
    if connector is not None:
        connector()
        return
    from .gdrive import get_credentials
    get_credentials()


def google_disconnect(conn: sqlite3.Connection) -> bool:
    """Forget the cached sign-in.

    This removes ScrapeX's own OAuth token file and nothing else: no Drive file,
    folder or spreadsheet is touched, and signing in again restores access.
    """
    from .gdrive import TOKEN_PATH

    path = Path(TOKEN_PATH)
    existed = path.exists()
    path.unlink(missing_ok=True)
    settings.set_state(conn, "google_last", RunResult(
        ok=True, detail="Signed out. Drive files were left exactly as they are.").as_state())
    return existed


def google_push(conn: sqlite3.Connection, source_keys: list[str], *, sink=None) -> RunResult:
    """Publish sources into the Drive spreadsheet (one tab per source)."""
    if not source_keys:
        raise NotConfiguredError("Pick at least one source to push.")
    status = google_status(conn)
    if sink is None:
        if not status["ready"]:
            raise NotConfiguredError(status["blocker"])
        from .gdrive import DriveManager, build_services, get_credentials
        from .publish import GoogleSink
        sink = GoogleSink(DriveManager(*build_services(get_credentials())))

    folder, workbook = status["folder"], status["workbook"]
    total, location, failures = 0, "", []
    for key in source_keys:
        try:
            rows, location = publish_source(conn, key, sink, folder, workbook)
            total += rows
        except ValueError as exc:
            failures.append(f"{key}: {exc}")
    conn.commit()

    detail = f"Pushed {total} rows into {len(source_keys) - len(failures)} tab(s)."
    if failures:
        detail += " Skipped — " + "; ".join(failures)
    return _record(conn, "google_last",
                   RunResult(ok=total > 0, rows=total, location=location, detail=detail))


# =============================================================================
# One list for the panel's "where does data go" screen (spec 9)
# =============================================================================

def all_destinations(conn: sqlite3.Connection) -> list[dict]:
    """Every destination with its real, current state — local DB included.

    The local database is listed first and marked required: it is the source of
    truth, so the interface must never present it as something to switch off.
    """
    return [
        {"key": "local_db", "label": "Local database", "ready": True, "required": True,
         "blocker": "", "detail": "Always on — the source of truth. It cannot be disabled.",
         "settings_url": ""},
        {**excel_status(conn), "required": False, "settings_url": "/exports"},
        {**apps_script_status(conn), "required": False, "settings_url": "/sync"},
        {**google_status(conn), "required": False, "settings_url": "/sync"},
    ]
