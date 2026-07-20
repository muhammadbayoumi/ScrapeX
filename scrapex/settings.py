"""Owner-editable settings, stored in the warehouse (spec sections 21-25).

Integration settings used to live in environment variables only, which means a
destination could be configured exactly once — from a terminal, before launch —
and never from the interface the owner actually uses. This module gives them a
home that the UI can write to.

Precedence is deliberate and reported back to the caller:

    an explicitly saved value  >  an environment variable  >  the built-in default

The environment still wins over nothing, so a CI runner or a headless machine
keeps working untouched; but the moment the owner saves a value in the UI, that
choice is authoritative — a saved setting silently losing to a stale environment
variable would be the worst of both worlds.

Secrets (tokens) are stored like any other value but never returned by
`public_settings()`: it reports whether a secret is set and shows its last four
characters, which is enough to tell two tokens apart and not enough to use one.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

PREFIX = "setting:"

FROM_SAVED = "saved"
FROM_ENV = "environment"
FROM_DEFAULT = "default"


@dataclass(frozen=True)
class Setting:
    key: str
    default: str
    env: str = ""
    secret: bool = False
    label: str = ""


# Every setting the interface may write. An unknown key is rejected rather than
# silently stored, so a typo in the UI can never create a setting that nothing
# ever reads.
SETTINGS: dict[str, Setting] = {s.key: s for s in [
    # --- Excel (spec 21) ---
    Setting("excel_folder", "", label="Folder for exported workbooks"),
    Setting("excel_workbook", "ScrapeX Data", label="Workbook name"),
    Setting("excel_schema", "original", label="Columns to export"),
    # --- Apps Script funnel (spec 22) ---
    Setting("funnel_url", "", env="SCRAPEX_FUNNEL_URL", label="Deployment URL"),
    Setting("funnel_token", "", env="SCRAPEX_FUNNEL_TOKEN", secret=True, label="Shared token"),
    # --- Google Drive and Sheets (spec 23) ---
    Setting("google_folder", "ScrapeX", label="Drive folder"),
    Setting("google_workbook", "ScrapeX Data", label="Spreadsheet name"),
    # --- Crawling (spec 33) ---
    # Real knobs on the shared HttpFetcher, not decoration: politeness and
    # timeout were fixed constants until the owner could see and change them.
    Setting("crawl_min_interval_s", "1.0", label="Minimum seconds between requests"),
    Setting("crawl_timeout_s", "30", label="Request timeout in seconds"),
    Setting("crawl_user_agent", "", label="User agent"),
    # --- Storage (spec 17) ---
    Setting("backup_folder", "", label="Folder for backups"),
    # --- Logs and diagnostics (spec 33) ---
    Setting("log_retention_days", "30", label="Keep job logs for"),
]}

# Status records written after a run. They are not owner-editable, so they are
# kept out of SETTINGS and read/written through get_state/set_state.
STATE_KEYS = ("excel_last", "apps_script_last", "google_last",
              "storage_last", "retention_last", "storage_migration")


@dataclass
class RunResult:
    """What one owner-initiated operation actually did.

    Every long or destructive action in the product reports through this shape,
    so a screen never has to invent its own vocabulary for "it worked" and a
    failure always carries the sentence explaining why.
    """

    ok: bool
    rows: int = 0
    location: str = ""
    detail: str = ""
    at: str = ""

    def as_state(self) -> dict:
        return {"ok": self.ok, "rows": self.rows, "location": self.location,
                "detail": self.detail, "at": self.at or utc_now()}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_stamp() -> str:
    """The timestamp every lineage filename uses: harvest.sealed-<stamp>.db.

    One function because three call sites each rolled their own and two produced
    a form storage.base_stem could not match — so after a seal or a restore the
    owner's backups silently vanished from the Storage page.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class UnknownSettingError(KeyError):
    """A key that is not in SETTINGS. Rejected loudly rather than stored."""


def _read(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                       (PREFIX + key,)).fetchone()
    return row[0] if row is not None else None


def _write(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (PREFIX + key, value))


def resolve(conn: sqlite3.Connection, key: str) -> tuple[str, str]:
    """Return (effective value, where it came from) for one setting."""
    spec = SETTINGS.get(key)
    if spec is None:
        raise UnknownSettingError(key)
    saved = _read(conn, key)
    if saved:
        return saved, FROM_SAVED
    if spec.env:
        from_env = os.environ.get(spec.env, "")
        if from_env:
            return from_env, FROM_ENV
    return spec.default, FROM_DEFAULT


def get(conn: sqlite3.Connection, key: str) -> str:
    return resolve(conn, key)[0]


def save(conn: sqlite3.Connection, values: dict[str, str]) -> list[str]:
    """Persist owner-supplied settings. Returns the keys actually changed.

    An empty string CLEARS the saved value — which is how the UI removes a
    token or lets a setting fall back to the environment again. Clearing is
    therefore a normal, reversible edit, not a deletion of anything else.
    """
    changed = []
    for key, raw in (values or {}).items():
        if key not in SETTINGS:
            raise UnknownSettingError(key)
        value = "" if raw is None else str(raw).strip()
        if value == (_read(conn, key) or ""):
            continue
        if value:
            _write(conn, key, value)
        else:
            conn.execute("DELETE FROM scrapex_meta WHERE key = ?", (PREFIX + key,))
        changed.append(key)
    return changed


def hint(value: str) -> str:
    """A recognisable, unusable fragment of a secret."""
    return f"...{value[-4:]}" if len(value) >= 4 else ("set" if value else "")


def public_settings(conn: sqlite3.Connection) -> dict[str, dict]:
    """Every setting shaped for display. Secrets report presence, never value."""
    out: dict[str, dict] = {}
    for key, spec in SETTINGS.items():
        value, source = resolve(conn, key)
        entry = {"key": key, "label": spec.label, "source": source, "secret": spec.secret,
                 "env": spec.env}
        if spec.secret:
            entry.update({"value": "", "is_set": bool(value), "hint": hint(value)})
        else:
            entry.update({"value": value, "is_set": bool(value), "hint": ""})
        out[key] = entry
    return out


# ---- run status (written by the integrations, read by the UI) ----------------

def set_state(conn: sqlite3.Connection, key: str, state: dict) -> None:
    if key not in STATE_KEYS:
        raise UnknownSettingError(key)
    _write(conn, key, json.dumps(state))


def get_state(conn: sqlite3.Connection, key: str) -> dict | None:
    if key not in STATE_KEYS:
        raise UnknownSettingError(key)
    raw = _read(conn, key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # A corrupted status line must not take down the page that displays it.
        return None
