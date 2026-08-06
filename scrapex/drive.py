"""The warehouse travels through Drive, and only a bundle that verified may be latest.

DECISION 3: one device at a time, with restore, and Drive is enough — no server.
DECISION 12: the upload frequency is a setting, because a daily full upload that
changes nothing is not free.

WHOSE TOKEN THIS IS. The extension owns it and lends it (the owner's ruling of
2026-08-05), so every call here takes a bearer token as an argument. This module
never stores one, never refreshes one, and cannot obtain one — which is the
whole point: a token the engine kept would be a second copy of the owner's
Google access sitting on disk, and revoking the extension's would not revoke it.

WHICH FILES IT CAN SEE. `drive.file` and nothing else. Google grants that scope
per-file, to files the app itself created, so ScrapeX is structurally incapable
of reading the rest of the owner's Drive. That is not a promise this code keeps;
it is one Google keeps for it, and it is exactly what the Profile page says.

WHY `latest.json` IS WRITTEN LAST, AND ONLY AFTER A VERIFY. The pointer is the
one thing a restoring machine trusts. Written before the upload finishes, it
names a half-uploaded file; written without verifying, it names a bundle that
may be empty. A backup nobody checked is a backup discovered to be broken on the
day it is needed, and that day is by definition the worst one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import bundle

#: Drive's own endpoints. Upload and metadata are different hosts' paths and
#: mixing them up is a 404 that reads like a permissions problem.
FILES = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

#: The folder ScrapeX makes for itself. A name and not a path: Drive has no
#: paths, only parents, and two folders may share a name — so the id is looked
#: up once and the NAME is never used to identify anything afterwards.
FOLDER_NAME = "ScrapeX backups"
FOLDER_MIME = "application/vnd.google-apps.folder"

#: The pointer every restoring machine reads first.
LATEST = "latest.json"

#: How many bundles to keep. Three, for the same reason storage.backups_kept
#: gives three: the newest may be the one carrying the defect, and a backup
#: taken minutes before a bad crawl is the one worth having.
KEEP = 3

#: Uploads are big — 33 MB measured — and a network stall must not hang a crawl
#: for ever. Long enough for a slow line, short enough to fail and retry.
TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=600.0, pool=10.0)


class DriveError(RuntimeError):
    """Something Drive said no to, in words a panel can show.

    Carries the status so a caller can tell a token that expired (401) from a
    quota that is gone (403) from a network that is not there — three different
    remedies, and one "backup failed" for all of them is how an owner stops
    reading the message.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _headers(token: str) -> dict:
    if not token:
        raise DriveError("no Google token — sign in from the panel first")
    return {"Authorization": f"Bearer {token}"}


def _check(response: httpx.Response, doing: str) -> httpx.Response:
    if response.status_code < 400:
        return response
    detail = ""
    try:
        detail = (response.json().get("error") or {}).get("message", "")
    except (ValueError, AttributeError):
        detail = response.text[:200]
    if response.status_code == 401:
        raise DriveError(
            f"Google refused the token while {doing}. Sign in again from the panel.",
            401)
    if response.status_code == 403:
        raise DriveError(
            f"Google refused the request while {doing}: {detail}. This is a "
            "permission or quota answer, not a network one.", 403)
    raise DriveError(f"Drive answered {response.status_code} while {doing}: {detail}",
                     response.status_code)


def folder_id(token: str, client: httpx.Client | None = None) -> str:
    """The id of ScrapeX's own folder, made once and found thereafter.

    Searched by name AND by `'me' in owners` and not trashed: a folder the owner
    deleted must not be written into, or the backups go somewhere he cannot see
    and cannot restore from.
    """
    owned = client or httpx.Client(timeout=TIMEOUT)
    try:
        query = (f"name = '{FOLDER_NAME}' and mimeType = '{FOLDER_MIME}' "
                 "and trashed = false and 'me' in owners")
        found = _check(owned.get(FILES, headers=_headers(token),
                                 params={"q": query, "fields": "files(id,name)"}),
                       "looking for the backup folder").json()
        files = found.get("files") or []
        if files:
            return files[0]["id"]

        made = _check(owned.post(FILES, headers=_headers(token),
                                 json={"name": FOLDER_NAME, "mimeType": FOLDER_MIME},
                                 params={"fields": "id"}),
                      "creating the backup folder").json()
        return made["id"]
    finally:
        if client is None:
            owned.close()


def upload(token: str, path: Path | str, *, parent: str,
           name: str | None = None, mime: str = "application/zip",
           client: httpx.Client | None = None) -> dict:
    """Send one file and return what Drive says it stored.

    Multipart in one request rather than resumable: at 33 MB a failed upload is
    cheap to repeat, and a resumable session is a second piece of state to keep
    correct for a saving that does not exist at this size. If the bundle grows
    past a few hundred megabytes this is the thing to revisit, and the number
    that decides it is in tests/test_a_bundle_a_bare_extension_can_read.py.
    """
    path = Path(path)
    owned = client or httpx.Client(timeout=TIMEOUT)
    try:
        metadata = {"name": name or path.name, "parents": [parent]}
        with open(path, "rb") as handle:
            response = owned.post(
                UPLOAD, headers=_headers(token),
                params={"uploadType": "multipart", "fields": "id,name,size,md5Checksum"},
                files={
                    "metadata": (None, json.dumps(metadata), "application/json"),
                    "file": (metadata["name"], handle, mime),
                })
        return _check(response, f"uploading {metadata['name']}").json()
    finally:
        if client is None:
            owned.close()


def download(token: str, file_id: str, path: Path | str,
             client: httpx.Client | None = None) -> Path:
    """Fetch one file by id, streamed so a 33 MB bundle is never held in memory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    owned = client or httpx.Client(timeout=TIMEOUT)
    try:
        with owned.stream("GET", f"{FILES}/{file_id}", headers=_headers(token),
                          params={"alt": "media"}) as response:
            if response.status_code >= 400:
                response.read()
                _check(response, f"downloading {file_id}")
            with open(path, "wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return path
    finally:
        if client is None:
            owned.close()


def listing(token: str, parent: str, client: httpx.Client | None = None) -> list[dict]:
    """What is in the folder, newest first."""
    owned = client or httpx.Client(timeout=TIMEOUT)
    try:
        found = _check(owned.get(
            FILES, headers=_headers(token),
            params={"q": f"'{parent}' in parents and trashed = false",
                    "orderBy": "createdTime desc",
                    "fields": "files(id,name,size,createdTime)"}),
            "listing the backup folder").json()
        return found.get("files") or []
    finally:
        if client is None:
            owned.close()


def delete(token: str, file_id: str, client: httpx.Client | None = None) -> None:
    owned = client or httpx.Client(timeout=TIMEOUT)
    try:
        _check(owned.delete(f"{FILES}/{file_id}", headers=_headers(token)),
               f"deleting {file_id}")
    finally:
        if client is None:
            owned.close()


@dataclass
class Backup:
    """What one completed backup is, from a restoring machine's point of view."""
    name: str
    file_id: str
    bytes: int
    sha256: str
    created_at: str
    engine_version: str


def prunable(files: list[dict], keep: int = KEEP) -> list[dict]:
    """Which bundles to delete, newest kept.

    Returned rather than deleted so the caller — and the test — can see the
    decision before anything is destroyed. `latest.json` is never a candidate:
    it is the pointer, not a backup.
    """
    bundles = [f for f in files if f.get("name", "").endswith(".zip")]
    return bundles[keep:]


def back_up(token: str, bundle_dir: Path | str, archive_path: Path | str, *,
            client: httpx.Client | None = None) -> Backup:
    """Pack, verify, upload, and only then say this is the latest.

    THE ORDER IS THE WHOLE DESIGN. `pack` refuses a bundle that does not verify;
    the archive goes up before anything points at it; and `latest.json` is
    written last, so a machine restoring midway through an upload reads the
    PREVIOUS backup rather than half of this one.
    """
    described = bundle.pack(bundle_dir, archive_path)
    manifest = json.loads(
        (Path(bundle_dir) / "manifest.json").read_text(encoding="utf-8"))

    owned = client or httpx.Client(timeout=TIMEOUT)
    try:
        parent = folder_id(token, client=owned)
        stored = upload(token, described["path"], parent=parent, client=owned)

        backup = Backup(
            name=stored.get("name", Path(described["path"]).name),
            file_id=stored["id"],
            bytes=described["bytes"],
            sha256=described["sha256"],
            created_at=manifest.get("created_at", ""),
            engine_version=manifest.get("engine_version", ""),
        )

        pointer = Path(archive_path).with_name(LATEST)
        pointer.write_text(json.dumps({
            "file_id": backup.file_id, "name": backup.name,
            "bytes": backup.bytes, "sha256": backup.sha256,
            "created_at": backup.created_at,
            "engine_version": backup.engine_version,
            "bundle_format": bundle.BUNDLE_FORMAT,
        }, indent=2) + "\n", encoding="utf-8")
        # Replaced rather than appended: there is one latest, and a folder with
        # two of them is a folder with none.
        for existing in listing(token, parent, client=owned):
            if existing.get("name") == LATEST:
                delete(token, existing["id"], client=owned)
        upload(token, pointer, parent=parent, name=LATEST,
               mime="application/json", client=owned)

        for old in prunable(listing(token, parent, client=owned)):
            delete(token, old["id"], client=owned)
        return backup
    finally:
        if client is None:
            owned.close()


def restore(token: str, into: Path | str, *,
            client: httpx.Client | None = None) -> bundle.BundleReport:
    """Read `latest.json`, fetch what it names, and verify before believing it.

    The checksum is checked against what the POINTER said, not only against the
    bundle's own manifest: a bundle whose manifest was rewritten to match its
    own damage would verify internally and still be the wrong file.
    """
    into = Path(into)
    owned = client or httpx.Client(timeout=TIMEOUT)
    try:
        parent = folder_id(token, client=owned)
        files = {f.get("name"): f for f in listing(token, parent, client=owned)}
        if LATEST not in files:
            raise DriveError("no backup has been uploaded from any device yet")

        pointer_path = into / LATEST
        download(token, files[LATEST]["id"], pointer_path, client=owned)
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))

        if pointer.get("bundle_format") != bundle.BUNDLE_FORMAT:
            raise DriveError(
                f"the newest backup is bundle format {pointer.get('bundle_format')!r} "
                f"and this engine reads {bundle.BUNDLE_FORMAT}. Update the engine "
                "before restoring.")

        archive = into / pointer["name"]
        download(token, pointer["file_id"], archive, client=owned)
        actual = bundle.sha256_of(archive)
        if actual != pointer.get("sha256"):
            raise DriveError(
                "the downloaded backup does not match the checksum its pointer "
                "names — it was truncated in transit or replaced. Nothing was "
                "restored.")

        report = bundle.unpack(archive, into / "bundle")
        if not report.ok:
            raise DriveError(
                "the backup arrived intact and does not verify: "
                + "; ".join(f"{f.path}: {f.problem}" for f in report.faults[:3]))
        return report
    finally:
        if client is None:
            owned.close()
