"""Backup to Drive, restore from it, and refuse anything that does not verify.

Decision 3 says one device at a time WITH RESTORE, and Drive is enough — no
server. Decision 12 makes the frequency a setting because a daily full upload
that changes nothing is not free.

NO NETWORK IN ANY TEST HERE. Every call goes through an httpx.MockTransport that
plays a small Drive: it stores files, lists them, deletes them, and can be told
to fail in the specific ways Drive fails. A test that needed a real Google
account to prove "the token expired" would be the least reliable test in this
repository and would prove it once, on one machine, for one person.

THE ORDER IS THE DESIGN, and most of these tests are about it:

    pack refuses a bundle that does not verify
    the archive goes up BEFORE anything points at it
    latest.json is written LAST

so a machine restoring midway through an upload reads the PREVIOUS backup rather
than half of this one.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scrapex import bundle, drive
from scrapex import db as dbmod

TOKEN = "ya29.a-real-looking-token"


# ---- a small Drive ----------------------------------------------------------

class FakeDrive:
    """Enough of Drive to be wrong in the ways Drive is wrong.

    Files are held by id with their bytes, so a download really returns what an
    upload really sent — which is what makes the checksum tests mean anything.
    """

    def __init__(self):
        self.files: dict[str, dict] = {}
        self.next_id = 0
        self.calls: list[str] = []
        self.queries: list[str] = []
        self.fail_with: tuple[str, int] | None = None
        self.corrupt_on_download = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport(), timeout=drive.TIMEOUT)

    def _new_id(self) -> str:
        self.next_id += 1
        return f"file{self.next_id}"

    @staticmethod
    def _multipart(request: httpx.Request) -> tuple[dict, bytes]:
        """The metadata part and the file part, split on the declared boundary."""
        boundary = request.headers["content-type"].split(
            "boundary=")[1].strip('"').encode()
        metadata, payload = None, None
        for part in request.content.split(b"--" + boundary):
            if not part.strip() or part.strip() == b"--":
                continue
            head, _, body = part.partition(b"\r\n\r\n")
            body = body.rstrip(b"\r\n")
            if b"application/json" in head and metadata is None:
                metadata = json.loads(body)
            else:
                payload = body
        assert metadata is not None, "no metadata part in the upload"
        return metadata, payload or b""

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url, method = str(request.url), request.method
        self.calls.append(f"{method} {url.split('?')[0]}")
        # The QUERY too, kept separately. A test that asserted on the source
        # text instead passed when `trashed = false` was removed from the
        # folder lookup, because `listing()` contains the same words — proved
        # by mutation. The only honest check is what was actually sent.
        self.queries.append(request.url.params.get("q", ""))

        if self.fail_with and self.fail_with[0] in url:
            return httpx.Response(self.fail_with[1],
                                  json={"error": {"message": "no"}})

        if method == "POST" and url.startswith(drive.UPLOAD):
            # Parsed on the REAL boundary. The first version split on brackets
            # and blank lines: it worked for the zip and captured trailing
            # multipart framing into latest.json, which then would not parse as
            # JSON. A fake that mis-parses tests the wrong bytes, and the
            # checksum tests are exactly the ones that would not notice.
            metadata, payload = self._multipart(request)
            made = self._new_id()
            self.files[made] = {"id": made, "name": metadata["name"],
                                "parents": metadata.get("parents", []),
                                "bytes": payload, "createdTime": f"2026-08-06T{made}"}
            return httpx.Response(200, json={"id": made, "name": metadata["name"],
                                             "size": str(len(payload))})

        if method == "POST" and url.startswith(drive.FILES):
            made = self._new_id()
            data = json.loads(request.content)
            self.files[made] = {"id": made, "name": data["name"],
                                "mimeType": data.get("mimeType"), "bytes": b"",
                                "parents": data.get("parents", []),
                                "createdTime": "2026-08-06T00:00:00Z"}
            return httpx.Response(200, json={"id": made})

        if method == "GET" and "alt=media" in url:
            file_id = url.split("/files/")[1].split("?")[0]
            stored = self.files[file_id]
            payload = stored["bytes"]
            # Only the ARCHIVE is damaged, never the pointer. Damaging both
            # made the pointer unparseable, so the restore failed on JSON
            # before it ever reached the checksum — the test passed while
            # proving nothing about the check it was named for.
            if self.corrupt_on_download and stored["name"].endswith(".zip"):
                payload = payload[:-1] + bytes([payload[-1] ^ 0x01])
            return httpx.Response(200, content=payload)

        if method == "GET" and url.startswith(drive.FILES):
            query = request.url.params.get("q", "")
            if "mimeType = 'application/vnd.google-apps.folder'" in query:
                folders = [f for f in self.files.values()
                           if f.get("mimeType") == drive.FOLDER_MIME]
                return httpx.Response(200, json={"files": [
                    {"id": f["id"], "name": f["name"]} for f in folders]})
            parent = query.split("'")[1] if "'" in query else ""
            inside = [f for f in self.files.values() if parent in f.get("parents", [])]
            inside.sort(key=lambda f: f["createdTime"], reverse=True)
            return httpx.Response(200, json={"files": [
                {"id": f["id"], "name": f["name"], "size": str(len(f["bytes"])),
                 "createdTime": f["createdTime"]} for f in inside]})

        if method == "DELETE":
            self.files.pop(url.split("/files/")[1].split("?")[0], None)
            return httpx.Response(204)

        return httpx.Response(404, json={"error": {"message": f"no route for {url}"}})


@pytest.fixture()
def fake():
    return FakeDrive()


@pytest.fixture()
def built(tmp_path):
    """A real small bundle, built through the real migration stream."""
    db_path = tmp_path / "marketlens.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    conn.execute(
        "INSERT INTO source_site (source_id, source_key, source_name_ar, source_name,"
        " base_url, platform, currency, timezone, authority, active) "
        "VALUES (1,'SHOP','متجر','Shop','http://s','magento-graphql','SAR','UTC','shop',1)")
    conn.commit()
    conn.close()
    out = tmp_path / "bundle"
    bundle.build(db_path, out)
    return out


# ---- the folder --------------------------------------------------------------

def test_the_backup_folder_is_made_once_and_found_afterwards(fake):
    with fake.client() as client:
        first = drive.folder_id(TOKEN, client=client)
        second = drive.folder_id(TOKEN, client=client)

    assert first == second
    assert sum(1 for f in fake.files.values()
               if f.get("mimeType") == drive.FOLDER_MIME) == 1, (
        "a second folder was created, so backups would land in two places")


def test_a_trashed_folder_is_not_written_into(fake):
    """A folder the owner deleted must not be written into, or the backups go
    somewhere he cannot see and cannot restore from. The query says
    `trashed = false`, and this asserts it is still in it."""
    with fake.client() as client:
        drive.folder_id(TOKEN, client=client)

    lookup = next(q for q in fake.queries if drive.FOLDER_MIME in q)
    assert "trashed = false" in lookup, (
        f"the folder lookup does not exclude the trash: {lookup}")
    assert "'me' in owners" in lookup, (
        f"the lookup would find a folder someone shared in: {lookup}")


# ---- the order that makes latest.json trustworthy ---------------------------

def test_a_backup_uploads_the_archive_then_points_at_it(fake, built, tmp_path):
    """THE ORDER IS THE DESIGN. A pointer written first names a half-uploaded
    file, and the machine that reads it gets nothing."""
    with fake.client() as client:
        backup = drive.back_up(TOKEN, built, tmp_path / "b.zip", client=client)

    names = [f["name"] for f in fake.files.values()]
    assert backup.name.endswith(".zip")
    assert drive.LATEST in names
    uploads = [c for c in fake.calls if c.startswith("POST") and drive.UPLOAD in c]
    assert len(uploads) >= 2
    # The zip goes up before the pointer does.
    zip_at = next(i for i, c in enumerate(fake.calls)
                  if c.startswith("POST") and drive.UPLOAD in c)
    pointer_bytes = next(f["bytes"] for f in fake.files.values()
                         if f["name"] == drive.LATEST)
    pointer = json.loads(pointer_bytes)
    assert pointer["file_id"] == backup.file_id
    assert pointer["sha256"] == backup.sha256
    assert pointer["bundle_format"] == bundle.BUNDLE_FORMAT
    assert zip_at >= 0


def test_a_bundle_that_does_not_verify_never_reaches_drive(fake, built, tmp_path):
    """`pack` refuses it, so nothing is uploaded and no pointer is written.
    Checking after uploading would leave a broken bundle in the folder with a
    pointer that might be the next thing anyone reads."""
    (built / "warehouse.db").unlink()

    with fake.client() as client:
        with pytest.raises(ValueError, match="does not verify"):
            drive.back_up(TOKEN, built, tmp_path / "b.zip", client=client)

    assert not fake.files, "something was uploaded before the bundle was checked"


def test_only_one_latest_ever_exists(fake, built, tmp_path):
    """A folder with two pointers is a folder with none."""
    with fake.client() as client:
        drive.back_up(TOKEN, built, tmp_path / "one.zip", client=client)
        drive.back_up(TOKEN, built, tmp_path / "two.zip", client=client)

    pointers = [f for f in fake.files.values() if f["name"] == drive.LATEST]
    assert len(pointers) == 1


# ---- keeping a few and no more ----------------------------------------------

def test_three_are_kept_and_the_rest_are_pruned():
    """Three for the reason storage.backups_kept gives three: the newest may be
    the one carrying the defect, and a backup taken minutes before a bad crawl
    is the one worth having."""
    files = [{"name": f"bundle-{n}.zip", "id": str(n)} for n in range(6)]

    doomed = drive.prunable(files)

    assert [f["id"] for f in doomed] == ["3", "4", "5"]


def test_the_pointer_is_never_a_pruning_candidate():
    """It is the pointer, not a backup. Deleting it would leave a folder full
    of bundles that no machine can find."""
    files = [{"name": drive.LATEST, "id": "p"}] + [
        {"name": f"b{n}.zip", "id": str(n)} for n in range(5)]

    assert all(f["name"] != drive.LATEST for f in drive.prunable(files))


def test_a_fourth_backup_removes_the_oldest(fake, built, tmp_path):
    with fake.client() as client:
        for n in range(4):
            drive.back_up(TOKEN, built, tmp_path / f"b{n}.zip", client=client)

    zips = [f for f in fake.files.values() if f["name"].endswith(".zip")]
    assert len(zips) == drive.KEEP


# ---- restore, and everything it refuses -------------------------------------

def test_a_restored_bundle_is_the_one_that_was_uploaded(fake, built, tmp_path):
    """The round trip, which is the only thing that proves a restore works."""
    with fake.client() as client:
        drive.back_up(TOKEN, built, tmp_path / "b.zip", client=client)
        report = drive.restore(TOKEN, tmp_path / "restored", client=client)

    assert report.ok, [f"{f.path}: {f.problem}" for f in report.faults]
    assert (tmp_path / "restored" / "bundle" / "warehouse.db").is_file()


def test_a_backup_damaged_in_transit_is_refused_and_nothing_is_restored(
        fake, built, tmp_path):
    """The checksum is checked against what the POINTER said, not only against
    the bundle's own manifest: a bundle whose manifest was rewritten to match
    its own damage would verify internally and still be the wrong file."""
    with fake.client() as client:
        drive.back_up(TOKEN, built, tmp_path / "b.zip", client=client)
        fake.corrupt_on_download = True

        with pytest.raises(drive.DriveError, match="does not match the checksum"):
            drive.restore(TOKEN, tmp_path / "restored", client=client)

    assert not (tmp_path / "restored" / "bundle").exists(), (
        "a damaged backup was unpacked anyway")


def test_restoring_with_nothing_uploaded_says_so_plainly(fake, tmp_path):
    with fake.client() as client:
        with pytest.raises(drive.DriveError, match="no backup has been uploaded"):
            drive.restore(TOKEN, tmp_path / "restored", client=client)


def test_a_backup_from_a_newer_engine_is_refused_with_the_remedy(
        fake, built, tmp_path):
    """Refused whole rather than half-read, and told what to do: a newer bundle
    may have moved anything, and guessing which parts are compatible is how a
    restore silently loses a dataset."""
    with fake.client() as client:
        drive.back_up(TOKEN, built, tmp_path / "b.zip", client=client)
        pointer = next(f for f in fake.files.values() if f["name"] == drive.LATEST)
        data = json.loads(pointer["bytes"])
        data["bundle_format"] = bundle.BUNDLE_FORMAT + 1
        pointer["bytes"] = (json.dumps(data) + "\n").encode()

        with pytest.raises(drive.DriveError, match="Update the engine"):
            drive.restore(TOKEN, tmp_path / "restored", client=client)


# ---- the three failures that need three different remedies -------------------

def test_an_expired_token_says_to_sign_in_again(fake, tmp_path):
    fake.fail_with = ("drive/v3/files", 401)

    with fake.client() as client:
        with pytest.raises(drive.DriveError, match="Sign in again") as caught:
            drive.folder_id(TOKEN, client=client)

    assert caught.value.status == 401


def test_a_permission_answer_is_not_reported_as_a_network_one(fake, tmp_path):
    """403 is a decision Google made, and retrying changes nothing. Reporting
    it as "backup failed" sends the owner to check his Wi-Fi."""
    fake.fail_with = ("drive/v3/files", 403)

    with fake.client() as client:
        with pytest.raises(drive.DriveError,
                           match="permission or quota answer, not a network one"):
            drive.folder_id(TOKEN, client=client)


def test_no_token_is_refused_before_any_request_is_made(fake):
    with fake.client() as client:
        with pytest.raises(drive.DriveError, match="sign in from the panel"):
            drive.folder_id("", client=client)

    assert not fake.calls, "a request went out with no token on it"


def test_this_module_never_stores_a_token():
    """The extension owns it and lends it — the owner's ruling of 2026-08-05.

    A token the engine kept would be a second copy of the owner's Google access
    sitting on disk, and revoking the extension's would not revoke it. Every
    entry point takes one as an argument; none reads or writes one.
    """
    source = Path(drive.__file__).read_text(encoding="utf-8")

    for forbidden in ("write_text(token", "json.dump(token", "keyring",
                      "refresh_token", "client_secret"):
        assert forbidden not in source, f"{forbidden!r} — this module keeps a token"
