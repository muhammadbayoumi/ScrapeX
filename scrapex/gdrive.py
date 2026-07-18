"""Google Drive + Sheets integration — Sign in with Google (ENGINEERING.md A4, A9).

OAuth "installed app" flow (owner's machine only). The Google client libraries
are imported LAZILY so this module (and DriveManager's pure logic) imports and
tests without them installed; only get_credentials/build_services need them.

Scope is deliberately least-privilege: drive.file lets ScrapeX manage only the
folder + spreadsheets it creates — never the owner's other Drive files — which
also keeps the app out of Google's sensitive-scope verification.
"""
from __future__ import annotations

import os
from pathlib import Path

# drive.file = manage only app-created files; spreadsheets = read/write their contents.
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

CRED_DIR = Path(os.environ.get("SCRAPEX_GOOGLE_DIR", str(Path.home() / ".scrapex" / "google")))
CLIENT_SECRET_PATH = Path(
    os.environ.get("SCRAPEX_GOOGLE_CLIENT_SECRET", str(CRED_DIR / "client_secret.json"))
)
TOKEN_PATH = CRED_DIR / "token.json"

FOLDER_MIME = "application/vnd.google-apps.folder"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
# Hard cap so a runaway export can never try to push millions of cells (A8).
MAX_EXPORT_ROWS = 40_000


class GoogleNotConfiguredError(RuntimeError):
    """client_secret.json is missing — the owner hasn't done the one-time setup."""


def get_credentials(client_secret: Path = CLIENT_SECRET_PATH, token: Path = TOKEN_PATH):
    """Return valid OAuth credentials, running the browser sign-in if needed.

    First run opens the browser ("Sign in with Google" + consent); the refresh
    token is cached at `token` so later runs are silent until it is revoked.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Google support needs: pip install -e .[google]") from exc

    creds = None
    if Path(token).exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not Path(client_secret).exists():
            raise GoogleNotConfiguredError(
                f"missing {client_secret}. Create a Google Cloud OAuth client "
                "(Desktop app) and save its JSON there — see ScrapeX/README.md."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        creds = flow.run_local_server(port=0)  # opens the browser for sign-in
    Path(token).parent.mkdir(parents=True, exist_ok=True)
    Path(token).write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_services(creds):
    """Build (drive_v3, sheets_v4) service clients from credentials."""
    from googleapiclient.discovery import build

    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return drive, sheets


def _q_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class DriveManager:
    """Idempotent Drive/Sheets operations. Takes injected service clients so the
    logic is unit-tested with mocks — no network, no credentials."""

    def __init__(self, drive, sheets):
        self._drive = drive
        self._sheets = sheets

    # ---- Drive: folders + spreadsheets (idempotent ensure) -----------------

    def ensure_folder(self, name: str, parent_id: str | None = None) -> str:
        found = self._find(name, FOLDER_MIME, parent_id)
        if found:
            return found
        meta = {"name": name, "mimeType": FOLDER_MIME}
        if parent_id:
            meta["parents"] = [parent_id]
        return self._drive.files().create(body=meta, fields="id").execute()["id"]

    def ensure_spreadsheet(self, name: str, folder_id: str) -> str:
        found = self._find(name, SHEET_MIME, folder_id)
        if found:
            return found
        meta = {"name": name, "mimeType": SHEET_MIME, "parents": [folder_id]}
        return self._drive.files().create(body=meta, fields="id").execute()["id"]

    def _find(self, name: str, mime: str, parent_id: str | None) -> str | None:
        q = f"name = '{_q_escape(name)}' and mimeType = '{mime}' and trashed = false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        res = self._drive.files().list(q=q, spaces="drive", fields="files(id,name)").execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None

    # ---- Sheets: write a whole tab (replace) -------------------------------

    def write_tab(self, spreadsheet_id: str, tab: str, header: list[str], rows: list[list]) -> None:
        if len(rows) > MAX_EXPORT_ROWS:
            raise ValueError(f"{len(rows)} rows exceeds MAX_EXPORT_ROWS={MAX_EXPORT_ROWS}")
        self._ensure_tab(spreadsheet_id, tab)
        self._sheets.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=f"'{tab}'", body={}).execute()
        self._sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1",
            valueInputOption="RAW", body={"values": [header, *rows]}).execute()

    def _ensure_tab(self, spreadsheet_id: str, tab: str) -> None:
        meta = self._sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="sheets(properties(title))").execute()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if tab not in titles:
            self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab}}}]}).execute()

    @staticmethod
    def spreadsheet_url(spreadsheet_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    @staticmethod
    def folder_url(folder_id: str) -> str:
        return f"https://drive.google.com/drive/folders/{folder_id}"
