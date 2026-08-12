# The Drive bridge — what the three connections need

> **A dated snapshot, not documentation.** Every line number below was true on 2026-08-11 and starts going stale the next time anyone edits these files. Read it for the reasoning and the shape; verify any `file:line` before acting on it.

Five readers, 2026-08-11, run before any of the Drive work was written. It is what established that `bundleview.js` had no caller, that no engine route accepted a Google token, and that `scrapex/gdrive.py` was a second, separate Google identity carrying the sensitive `spreadsheets` scope.

Produced by 5 parallel readers (`wf_85240fef-51a`).

---

## scrapex/drive.py (bearer-token Drive backup/restore) and scrapex/gdrive.py (OAuth + Drive/Sheets export) — public API, back_up/restore step order, token provenance, error types

- drive.py and gdrive.py are two entirely separate, non-communicating Drive integrations. drive.py imports only json, dataclasses, pathlib, httpx, and `from . import bundle` — it never imports gdrive. gdrive.py never imports drive.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:26-32`
- drive.py talks to Drive over raw HTTP with httpx against two distinct hosts/paths: FILES = 'https://www.googleapis.com/drive/v3/files' for metadata and UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files' for uploads.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:36-37`
- Module constants: FOLDER_NAME = 'ScrapeX backups', FOLDER_MIME = 'application/vnd.google-apps.folder', LATEST = 'latest.json', KEEP = 3.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:42-51`
- TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=600.0, pool=10.0) is the timeout applied to every client drive.py creates itself.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:55`
- Every public function in drive.py takes `token: str` as its first positional parameter. There is no module-level token cache, no refresh logic, and no code path anywhere in drive.py that reads a token from disk, env, or network. The docstring states this explicitly: the extension owns the token and lends it.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:7-11`
- The token is used only to build a header: _headers(token) returns {'Authorization': f'Bearer {token}'}. An empty/falsy token raises DriveError('no Google token — sign in from the panel first') with status defaulting to None.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:72-75`
- back_up() and restore() pass the same token they received down to folder_id/upload/download/listing/delete — they never re-derive or substitute one.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:238-239`
- Every drive.py function accepts `client: httpx.Client | None = None`; when None it constructs its own client and closes it in a `finally`, when supplied it reuses the caller's and does NOT close it. back_up/restore create one client and thread it through every nested call.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:236-238`
- back_up() step 1: bundle.pack(bundle_dir, archive_path) — this VERIFIES the bundle and raises ValueError (not DriveError) if verification fails, before any network call happens.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:232`
- back_up() step 2: reads manifest.json from the bundle_dir directly off disk with json.loads((Path(bundle_dir)/'manifest.json').read_text(encoding='utf-8')) — an unguarded read that raises FileNotFoundError/JSONDecodeError if absent or malformed.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:233-234`
- back_up() step 3: resolves the folder via folder_id(token, client=owned), then uploads the packed archive with upload(token, described['path'], parent=parent, client=owned) — NO `name=` argument, so the uploaded filename is the archive path's own basename (whatever the caller passed as archive_path), and the MIME defaults to application/zip.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:238-239`
- back_up() builds a Backup dataclass with name=stored.get('name', Path(described['path']).name), file_id=stored['id'], bytes=described['bytes'], sha256=described['sha256'], created_at=manifest.get('created_at',''), engine_version=manifest.get('engine_version','').
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:241-248`
- back_up() writes latest.json LOCALLY first, at Path(archive_path).with_name(LATEST) — i.e. a sibling of the archive, not in bundle_dir. Content is json.dumps(..., indent=2) + '\n', keys exactly: file_id, name, bytes, sha256, created_at, engine_version, bundle_format (bundle_format = bundle.BUNDLE_FORMAT, currently 1).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:250-257`
- back_up() replaces (never appends) the remote pointer: it lists the folder, deletes every file whose name == 'latest.json', then uploads the local pointer with name=LATEST and mime='application/json'. The delete-then-upload order means there is a window with no latest.json in the folder.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:260-264`
- back_up() prunes LAST, after the pointer is in place: `for old in prunable(listing(token, parent, client=owned)): delete(token, old['id'], client=owned)`, then returns the Backup.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:266-268`
- prunable() filters to names ending in '.zip' and returns files[keep:] — it relies on listing()'s createdTime-desc ordering for 'newest kept' and does no sorting of its own. latest.json is excluded purely because it does not end in .zip.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:219-220`
- listing() orders by 'createdTime desc' and requests fields 'files(id,name,size,createdTime)'; it filters to `'{parent}' in parents and trashed = false` and returns found.get('files') or [].
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:179-185`
- restore() needs to be told only the token and a destination directory `into`. Everything else — which file, its name, its checksum, its format — comes from the remote latest.json. There is no parameter to pick an older backup.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:274-275`
- restore() step order: folder_id -> listing keyed by name -> raise DriveError('no backup has been uploaded from any device yet') if LATEST absent -> download pointer to into/'latest.json' -> parse it.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:285-292`
- restore() gate 1: if pointer.get('bundle_format') != bundle.BUNDLE_FORMAT it raises DriveError naming both values and telling the owner to update the engine. Status is None (not passed).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:294-298`
- restore() downloads the archive to `into / pointer['name']` — a raw, unsanitised join of the destination with a name taken from the remote pointer — then computes bundle.sha256_of(archive) and compares against pointer.get('sha256'), raising DriveError on mismatch with 'Nothing was restored.'
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:300-307`
- restore() final step: report = bundle.unpack(archive, into / 'bundle'); if not report.ok it raises DriveError joining the first three faults as 'path: problem'. On success it returns the bundle.BundleReport.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:309-314`
- The only error type drive.py defines or raises deliberately is DriveError(RuntimeError), carrying `.status` (int | None). _check maps 401 -> 'Google refused the token ... Sign in again from the panel.' (status 401), 403 -> permission/quota wording (status 403), anything else >=400 -> generic message with response.status_code as status.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:58-95`
- _check extracts the Drive error message via response.json()['error']['message'], falling back to response.text[:200] on ValueError/AttributeError.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:81-85`
- download() streams with owned.stream('GET', f'{FILES}/{file_id}', params={'alt':'media'}), calls response.read() before _check on a >=400 status so the error body is available, writes with handle.writelines(response.iter_bytes()), and mkdir(parents=True, exist_ok=True) on path.parent first.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:158-169`
- upload() posts multipart (uploadType=multipart) with fields='id,name,size,md5Checksum' and a two-part body: 'metadata' as application/json ({'name':..., 'parents':[parent]}) and 'file' as the open handle with the given mime. Returns the parsed JSON dict from Drive.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:140-149`
- folder_id() searches by q = "name = 'ScrapeX backups' and mimeType = '<folder mime>' and trashed = false and 'me' in owners", returns files[0]['id'] if any, else creates the folder and returns made['id']. The folder name is interpolated into the query with no escaping (it is a constant here, so no injection in practice).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/drive.py:107-120`
- NOTHING in drive.py or gdrive.py mentions panel.jsonl.gz. That constant lives only in bundle.py as PANEL_PACK = 'panel.jsonl.gz'; drive.py handles the whole bundle as one opaque .zip and never names any file inside it.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:204`
- gdrive.py is the OTHER integration and it DOES fetch and persist a token itself: get_credentials() reads/writes token.json, runs InstalledAppFlow.run_local_server(port=0) to open a browser, refreshes expired creds, and writes creds.to_json() to TOKEN_PATH.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/gdrive.py:38-68`
- gdrive.py's token/secret locations: CRED_DIR = env SCRAPEX_GOOGLE_DIR or ~/.scrapex/google; CLIENT_SECRET_PATH = env SCRAPEX_GOOGLE_CLIENT_SECRET or CRED_DIR/client_secret.json; TOKEN_PATH = CRED_DIR/token.json (TOKEN_PATH has no env override).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/gdrive.py:22-26`
- gdrive.py SCOPES are drive.file + spreadsheets; drive.py's docstring claims drive.file only. Both are least-privilege but they are not the same scope set.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/gdrive.py:17-20`
- gdrive.py error types: GoogleNotConfiguredError(RuntimeError) when client_secret.json is missing; plain RuntimeError('Google support needs: pip install -e .[google]') on ImportError of the google libs; ValueError from DriveManager.write_tab when len(rows) > MAX_EXPORT_ROWS (40_000).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/gdrive.py:34-49`
- gdrive.py has no back_up/restore/prunable/latest.json concept at all. Its public surface is get_credentials, build_services, and DriveManager (ensure_folder, ensure_spreadsheet, write_tab, spreadsheet_url, folder_url) — spreadsheet export, not backup.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/gdrive.py:84-145`
- gdrive.py escapes query values via _q_escape (backslash then single-quote), which drive.py does not do.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/gdrive.py:80-81`
- No production code calls drive.py. Grep across the repo shows drive.back_up/restore/folder_id/listing/prunable called only from tests/test_the_warehouse_travels_through_drive.py; cli.py and outputs.py import from .gdrive instead.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/cli.py:589`

### Signatures a caller must satisfy

```
scrapex/drive.py:98  def folder_id(token: str, client: httpx.Client | None = None) -> str
scrapex/drive.py:126  def upload(token: str, path: Path | str, *, parent: str, name: str | None = None, mime: str = "application/zip", client: httpx.Client | None = None) -> dict
scrapex/drive.py:155  def download(token: str, file_id: str, path: Path | str, client: httpx.Client | None = None) -> Path
scrapex/drive.py:175  def listing(token: str, parent: str, client: httpx.Client | None = None) -> list[dict]
scrapex/drive.py:191  def delete(token: str, file_id: str, client: httpx.Client | None = None) -> None
scrapex/drive.py:212  def prunable(files: list[dict], keep: int = KEEP) -> list[dict]   # KEEP = 3; NOTE: no token, no client — pure function
scrapex/drive.py:223  def back_up(token: str, bundle_dir: Path | str, archive_path: Path | str, *, client: httpx.Client | None = None) -> Backup
scrapex/drive.py:274  def restore(token: str, into: Path | str, *, client: httpx.Client | None = None) -> bundle.BundleReport
scrapex/drive.py:67   DriveError.__init__(self, message: str, status: int | None = None)   # subclasses RuntimeError; sets self.status
scrapex/drive.py:201-209  @dataclass class Backup: name: str; file_id: str; bytes: int; sha256: str; created_at: str; engine_version: str
scrapex/drive.py:72   def _headers(token: str) -> dict   # private
scrapex/drive.py:78   def _check(response: httpx.Response, doing: str) -> httpx.Response   # private
scrapex/gdrive.py:38  def get_credentials(client_secret: Path = CLIENT_SECRET_PATH, token: Path = TOKEN_PATH)   # no return annotation; returns google.oauth2.credentials.Credentials
scrapex/gdrive.py:71  def build_services(creds)   # returns (drive_v3, sheets_v4) tuple, unannotated
scrapex/gdrive.py:88  DriveManager.__init__(self, drive, sheets)
scrapex/gdrive.py:94  DriveManager.ensure_folder(self, name: str, parent_id: str | None = None) -> str
scrapex/gdrive.py:103 DriveManager.ensure_spreadsheet(self, name: str, folder_id: str) -> str
scrapex/gdrive.py:120 DriveManager.write_tab(self, spreadsheet_id: str, tab: str, header: list[str], rows: list[list]) -> None
scrapex/gdrive.py:139 @staticmethod DriveManager.spreadsheet_url(spreadsheet_id: str) -> str
scrapex/gdrive.py:143 @staticmethod DriveManager.folder_url(folder_id: str) -> str
scrapex/bundle.py:355 def pack(bundle_dir: Path | str, archive_path: Path | str) -> dict   # returns {"path": str, "bytes": int, "sha256": str, "files": int, "uncompressed_bytes": int}
scrapex/bundle.py:379 def unpack(archive_path: Path | str, out_dir: Path | str) -> BundleReport
scrapex/bundle.py:62  def sha256_of(path: Path) -> str
scrapex/bundle.py:55  BUNDLE_FORMAT = 1
```

### Gotchas

- The uploaded bundle's filename is NOT chosen by back_up(). back_up calls upload() without `name=`, so the remote name is Path(archive_path).name — whatever basename the caller passed. prunable() then filters on names ending in '.zip'. A caller who passes an archive_path not ending in .zip silently makes every backup unprunable (they accumulate for ever) while latest.json still points at them correctly.
- latest.json is written to Path(archive_path).with_name('latest.json') — a sibling of the ARCHIVE, not inside bundle_dir. Two concurrent back_up() calls sharing an archive directory clobber each other's local pointer file.
- back_up() DELETES the remote latest.json before uploading the new one (drive.py:260-264). Between those two calls the folder has no pointer, and a restore() racing that window gets DriveError('no backup has been uploaded from any device yet') even though a valid bundle is sitting there.
- back_up() reads manifest.json with a bare read_text/json.loads and no try (drive.py:233-234). A missing or malformed manifest raises FileNotFoundError or json.JSONDecodeError, NOT DriveError — a caller that only catches DriveError will crash. Note bundle.pack runs first and would normally have caught a broken bundle, but pack verifies the bundle contents, it does not guarantee manifest.json parses here.
- bundle.pack() raises ValueError (bundle.py:365) when the bundle does not verify, and back_up calls it on line 1 of its body. So back_up's failure modes are ValueError | DriveError | OSError, not DriveError alone.
- prunable() does not sort. It trusts that listing() returned createdTime-desc order. Called on any list that is not already newest-first (or a hand-built list in a test), it deletes the wrong files. It also takes no token and no client — it is a pure function that only decides; the caller must actually delete.
- restore() writes the downloaded archive to `into / pointer['name']` with no path sanitisation (drive.py:300). The name comes from the remote pointer JSON. bundle.unpack defends against zip-entry traversal (bundle.py:395-399) but this join is not similarly guarded.
- restore() has no way to select an older backup — it is hardwired to latest.json. Retention keeps 3 bundles but only the newest is reachable through this API; recovering an older one requires listing() + download() by hand.
- The checksum comparison in restore() is `actual != pointer.get('sha256')`. If the pointer lacks a sha256 key, .get returns None, the comparison is true, and it raises — it fails closed, which is correct but means a pointer written by anything other than back_up() will be rejected.
- DriveError.status is only populated by _check. The DriveErrors raised inside back_up/restore/_headers (no token, no backup yet, format mismatch, checksum mismatch, verify failure) all have status=None. Any caller switching on .status to render a panel message must handle None.
- When `client` is passed in, drive.py never closes it — but when it is None the function closes the client it made, INCLUDING inside back_up/restore's finally. Passing a client into back_up means the caller owns closing it.
- drive.py has NO retry, NO backoff, and NO resumable upload. A 33 MB multipart POST that fails mid-write (write timeout is 600s) is a total loss and must be repeated from pack onward. The docstring says to revisit this above a few hundred MB.
- gdrive.py is a completely different code path with its own persisted token at ~/.scrapex/google/token.json and its own browser OAuth flow. It contradicts drive.py's stated 'the engine never stores a token' principle — and it is the one production code (cli.py, outputs.py) actually uses. drive.py is currently exercised only by tests.
- Neither file knows anything about panel.jsonl.gz. drive.py treats the bundle as an opaque zip; PANEL_PACK = 'panel.jsonl.gz' lives at bundle.py:204. Any change to what the panel reads is a bundle.py concern, not a drive.py one.
- folder_id() interpolates FOLDER_NAME into the Drive q= string unescaped (drive.py:107). Safe today because FOLDER_NAME is a module constant, but it is not a parameterised query — gdrive.py's _q_escape (gdrive.py:80) exists precisely for this and drive.py has no equivalent.

### Not answerable from the code

- Who supplies the bearer token to drive.py in production. Grep found no non-test caller of drive.back_up/restore — cli.py and outputs.py use gdrive.py instead. Whether an HTTP endpoint or IPC layer bridges the extension's token into drive.py is not visible from these files.
- Whether drive.py is intended to replace gdrive.py's persisted-token flow, or whether the two are meant to coexist. The drive.py docstring cites an 'owner's ruling of 2026-08-05' that the engine must never hold a token, which gdrive.py:66-67 violates by writing token.json — the resolution is not recorded in either file.
- What caller decides archive_path, and therefore whether the uploaded name always ends in .zip (which prunable() requires). The tests pass names like 'b.zip', but no production caller exists to confirm.
- Whether manifest.json is guaranteed by bundle.build() to contain 'created_at' and 'engine_version'. back_up uses .get(..., '') for both, so an absent key silently yields empty strings in latest.json rather than an error — I did not read bundle.build() to confirm they are always written.
- Whether Drive's createdTime ordering is stable enough for prunable() when several bundles are uploaded within the same second (the test at test_the_warehouse_travels_through_drive.py:273 loops uploads back-to-back against a fake).
- What the extension/panel does with the returned Backup dataclass or BundleReport — no consumer of those return values exists outside tests.

---

## scrapex/bundle.py (backup bundle writer/verifier/packer) and extension/bundleview.js (the engine-less panel reader)

- build() is the only bundle writer. It creates out_dir, takes a consistent SQLite copy via archive.backup_database(db_path, tag="bundle") and shutil.move()s it to <root>/warehouse.db, then opens THAT COPY read-only (file:...?mode=ro, uri=True) to do all exports — never the live db.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:131-138`
- Dataset selection: source_keys=None means every key from reports.list_sources(conn); otherwise the given list is INTERSECTED with available keys, so an unknown key is silently dropped rather than raising.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:140-142`
- Per dataset, 'current' is ALWAYS written (even with zero rows, deliberately, to distinguish 'nothing yet' from 'missing'); 'details' and 'history' are written ONLY if their row list is non-empty.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:145-159`
- _write_table writes each table TWICE: <name>.jsonl (utf-8, newline="\n", one json.dumps(dict(zip(header,row,strict=True))) per line, ensure_ascii=False) and <name>.csv (encoding utf-8-sig i.e. BOM, newline="", csv.writer, header row first then data rows).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:103-116`
- _write_table returns the per-table manifest fragment: {"rows": len(rows), "columns": len(header), "files": ["<name>.jsonl", "<name>.csv"]} — bare filenames, not paths.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:118-119`
- panel.jsonl.gz sits at the BUNDLE ROOT (out_dir / PANEL_PACK), a sibling of warehouse.db and manifest.json — NOT inside datasets/.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:204,208`
- The panel pack is written by gzip.open(..., "wt", encoding="utf-8", newline="\n", compresslevel=6) and is built by RE-READING the already-written datasets/<key>/<table>.jsonl files — it never re-queries SQL.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:207-222`
- Each panel.jsonl.gz line is exactly one JSON object with exactly THREE keys: "dataset" (the source_key string), "table" ("current" | "details" | "history"), and "row" (the parsed object from the source .jsonl line, whose own keys are that table's export header column names). ensure_ascii=False, one "\n" after each.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:219-222`
- Pack-file ordering is sorted(datasets) then sorted(tables) — so datasets are alphabetical by source_key and, within one dataset, tables come out current, details, history (alphabetical). Blank source lines are skipped.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:210-218`
- manifest.json is written last, JSON with indent=2, ensure_ascii=False, plus a trailing newline, utf-8. Its top-level keys are exactly: bundle_format, engine_version, created_at, source, datasets, files.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:165-184`
- manifest["files"] maps each bundle-relative POSIX path -> {"bytes": st_size, "sha256": hex}. It is built from out_dir.rglob("*") and EXCLUDES manifest.json itself (a file cannot contain its own hash), so warehouse.db, every datasets/*.jsonl, every datasets/*.csv and panel.jsonl.gz are all listed.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:172-181`
- manifest["source"] is str(db_path) — the caller's original database path verbatim, i.e. an absolute local filesystem path is embedded in a bundle that is uploaded to Drive.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:169`
- manifest["datasets"] is {source_key: {table_name: {"rows", "columns", "files"}}} — the same dict build() accumulated and handed to _write_panel_pack.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:144-170`
- build() does not return its own report — it returns verify(out_dir), so the returned BundleReport can carry faults.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:185`
- verify() checks four things and collects ALL faults rather than stopping at the first: manifest present+readable; bundle_format == BUNDLE_FORMAT (else it returns immediately, refusing the bundle whole); every named file exists with matching byte size then matching sha256; every file on disk is named in the manifest (an unnamed file is a fault: 'present and not in the manifest').
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:242-300`
- verify() additionally RE-COUNTS non-blank lines in each datasets/<key>/<table>.jsonl and faults if the count differs from manifest datasets[key][table]["rows"] — explicitly because a truncated export has a valid checksum for its truncated self. It does NOT re-count panel.jsonl.gz lines.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:303-317`
- BundleReport.files / BundleReport.bytes are incremented ONLY for files that passed both size and checksum checks, i.e. they count manifest-named files and therefore never include manifest.json.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:290-291`
- pack() calls verify(root) first and raises ValueError (message listing at most the first 3 faults) if the bundle does not verify — packing cannot skip validation.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:362-367`
- pack() produces a ZIP: zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6), writing every file under root sorted, with arcname = path.relative_to(root).as_posix(). The zip DOES include manifest.json (the rglob here has no manifest exclusion).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:369-373`
- pack() does NOT choose a filename — the archive path is entirely the caller's archive_path argument; pack only mkdirs archive.parent. There is no naming convention or extension enforcement in this module.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:362,369`
- pack() returns a plain dict with exactly five keys: {"path": str(archive), "bytes": archive.stat().st_size, "sha256": sha256_of(archive), "files": report.files, "uncompressed_bytes": report.bytes}.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:374-376`
- read_dataset() reads datasets/<source_key>/<table>.jsonl directly and returns [] (not an error) when the file is absent; table defaults to "current". It performs no checksum or manifest check.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:322-334`
- read_panel_pack() is the Python mirror of the JS reader: it gzip-opens the pack in text mode, skips blank lines, filters on entry.get("table") == table (default "current") and optionally entry.get("dataset") == dataset, and returns a flat list of entry["row"] objects.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:225-239`
- Hashing reads in 1 MiB blocks (_BLOCK = 1024*1024) so the 112+ MB warehouse is never held whole in memory.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:57-67`
- The only ROW limit is inherited, not declared here: build() calls export_source_table / export_details_table / export_history_table without a limit argument, and all three default to limit: int = 40_000, applied as a SQL LIMIT. So each table of each dataset is capped at 40,000 rows.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/reports.py:1215,1465,1493`
- There is NO byte-size limit anywhere in bundle.py — no max bundle size, no max archive size, no streaming cap. The only size facts are measured comments: warehouse.db 116 MB, exports 93 MB (64 jsonl + 29 csv), bundle 209 MB, zipped 33 MB (6.3x, ~1 second); and the pack measured at 64.1 MB of rows -> 4.1 MB gzipped.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:338-352,200-203`
- BUNDLE_FORMAT = 1 is the layout version, deliberately separate from engine VERSION and the DB schema version; verify() refuses any other value outright.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:55,262-270`
- unpack() extracts entry-by-entry (never extractall), resolving each target against the destination and raising ValueError on anything not is_relative_to(destination) — zip-slip guarded — then returns verify(root).
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:379-404`
- JS SIDE — bundleview.js consumes EXACTLY ONE bundle file: panel.jsonl.gz. readPanelPack pipes the blob through DecompressionStream("gzip"), then TextDecoderStream, and splits on "\n" incrementally, adding the final carry as a last line.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:28-47`
- JS SIDE — CONFIRMED it reads the RAW gzip file, not the ZIP from pack(). DecompressionStream("gzip") only handles gzip/deflate; the header states the browser has 'no zip reader at all' and unpacking the archive would need a bundled library the repo refuses to ship. There is no zipfile/ZIP handling anywhere in bundleview.js.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:12-16,29`
- JS SIDE — the three per-line keys it actually reads are entry.dataset (must be typeof string or the line is dropped), entry.table (falls back to "current" when falsy/absent), and entry.row (pushed verbatim, never validated). Result shape is Map<dataset, Map<table, row[]>>.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:49-67`
- JS SIDE — a line that fails JSON.parse is silently skipped, deliberately, so a download truncated mid-line loses one row instead of the whole backup.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:53-59`
- JS SIDE — datasetSummaries returns {source_key, rows (count of the 'current' table), tables (sorted table names), has_history} sorted by descending current-row count; rowsOf(datasets, key, table="current") returns [] for a missing dataset or table.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:70-85`
- JS SIDE — toCsv builds the header as the union of every row's keys in FIRST-SEEN order (not the first row's keys, so a row carrying an extra promoted axis keeps its column), quotes cells containing " , CR or LF by doubling quotes, joins with CRLF and prepends a UTF-8 BOM to match the engine's utf-8-sig csv writer.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:94-114`
- JS SIDE — bundleview.js NEVER touches manifest.json, warehouse.db, datasets/*.jsonl or datasets/*.csv. It performs no sha256 verification of anything: all of verify()'s integrity guarantees are Python-side only.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:1-115`
- JS SIDE — readPanelPack takes an already-obtained Blob; the module contains no fetch/XHR/downloads API call, so nothing in this file decides where panel.jsonl.gz comes from.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:28-29`
- bundleview.js currently has NO production importer in the extension — the only importers repo-wide are extension/tests/bundleview.test.mjs and the Python round-trip test that runs the module under node. app.js, background.js and the rest of extension/ never mention bundle, panel.jsonl or DecompressionStream.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/tests/bundleview.test.mjs:14-15`
- The Python/JS contract is enforced by a real round-trip test: it builds a bundle with build(), takes out / bundle.PANEL_PACK (the raw .gz, not an archive), wraps it in a Blob and runs the extension's own readPanelPack/datasetSummaries/rowsOf/toCsv over it under node.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/tests/test_the_panel_reads_what_the_engine_wrote.py:63-88`

### Signatures a caller must satisfy

```
def build(db_path: Path | str, out_dir: Path | str, *, source_keys: list[str] | None = None) -> BundleReport   # bundle.py:122-123
def verify(bundle_dir: Path | str) -> BundleReport   # bundle.py:242
def pack(bundle_dir: Path | str, archive_path: Path | str) -> dict   # bundle.py:355
def read_dataset(bundle_dir: Path | str, source_key: str, table: str = "current") -> list[dict]   # bundle.py:322-323
def read_panel_pack(path: Path | str, *, dataset: str | None = None, table: str = "current") -> list[dict]   # bundle.py:225-226
def _write_panel_pack(out_dir: Path, datasets: dict) -> None   # bundle.py:207
def unpack(archive_path: Path | str, out_dir: Path | str) -> BundleReport   # bundle.py:379
def _write_table(directory: Path, name: str, header: list[str], rows: list[list]) -> dict   # bundle.py:94-95
def sha256_of(path: Path) -> str   # bundle.py:62
BUNDLE_FORMAT = 1   # bundle.py:55
PANEL_PACK = "panel.jsonl.gz"   # bundle.py:204
_BLOCK = 1024 * 1024   # bundle.py:59
@dataclass class Fault: path: str; problem: str   # bundle.py:70-78
@dataclass class BundleReport: root: Path; files: int = 0; bytes: int = 0; datasets: dict = field(default_factory=dict); faults: list[Fault] = field(default_factory=list); @property ok -> bool (= not self.faults)   # bundle.py:81-91
pack() return dict: {"path": str, "bytes": int, "sha256": str, "files": int, "uncompressed_bytes": int}   # bundle.py:374-376
_write_table() return dict: {"rows": int, "columns": int, "files": ["<name>.jsonl", "<name>.csv"]}   # bundle.py:118-119
panel.jsonl.gz line object: {"dataset": str, "table": str, "row": object}   # bundle.py:220-221
manifest.json object: {"bundle_format": int, "engine_version": str, "created_at": str, "source": str, "datasets": {key: {table: {"rows", "columns", "files"}}}, "files": {relpath: {"bytes": int, "sha256": str}}}   # bundle.py:165-181
def backup_database(db_path: Path | str, tag: str = "rebuild") -> Path   # archive.py:17
def export_source_table(conn: sqlite3.Connection, source_key: str, limit: int = 40_000) -> tuple[list[str], list[list]]   # reports.py:1214-1215
def export_details_table(conn: sqlite3.Connection, source_key: str, limit: int = 40_000) -> tuple[list[str], list[list]]   # reports.py:1464-1465
def export_history_table(conn: sqlite3.Connection, source_key: str, limit: int = 40_000) -> tuple[list[str], list[list]]   # reports.py:1492-1493
export async function readPanelPack(blob)  ->  Promise<Map<datasetKey, Map<tableName, row[]>>>   # bundleview.js:28
export function datasetSummaries(datasets) -> {source_key, rows, tables, has_history}[]   # bundleview.js:70
export function rowsOf(datasets, key, table = "current") -> object[]   # bundleview.js:82
export function toCsv(rows) -> string   # bundleview.js:94
```

### Gotchas

- ON-DISK LAYOUT, exactly: <root>/warehouse.db  |  <root>/datasets/<SOURCE_KEY>/current.jsonl + current.csv (always)  |  <root>/datasets/<SOURCE_KEY>/details.jsonl + details.csv (only when non-empty)  |  <root>/datasets/<SOURCE_KEY>/history.jsonl + history.csv (only when non-empty)  |  <root>/panel.jsonl.gz  |  <root>/manifest.json. Nothing else. (bundle.py:135, 147-158, 163, 183)
- panel.jsonl.gz is at the bundle ROOT, not under datasets/. Anything that globs datasets/** will miss the one file the browser actually reads.
- The JS reads the RAW panel.jsonl.gz, NOT the pack() zip. Whatever ships the bundle to a bare extension must expose that .gz as its own downloadable object — handing the panel the .zip gives it a format it provably cannot open (no zip reader in a browser, no npm dependency allowed).
- pack()'s returned "files" and "uncompressed_bytes" come from BundleReport.files/.bytes, which only count manifest-named files — manifest.json is inside the zip but is excluded from both numbers. The counts do not describe the archive's contents.
- verify() faults on any file present on disk but absent from the manifest. Writing pack()'s archive (or any scratch file, or a stale previous bundle's leftovers) inside the bundle root makes the bundle fail verification, and build() would hash the leftovers into the new manifest because it never cleans out_dir first.
- 40,000 rows per table per dataset is a SILENT truncation: build() calls the three export functions without a limit, taking their default, and nothing records that a cap was hit. verify()'s row re-count compares files against the manifest, so a truncated export verifies clean.
- 'details' and 'history' are omitted entirely when empty, so their keys are absent from manifest["datasets"][key] and from panel.jsonl.gz. Readers must treat a missing table as 'no rows', not as an error — which is exactly what read_dataset() (returns []) and rowsOf() (returns []) do.
- The panel pack is derived from the already-written .jsonl files, so a fault in an export silently propagates into the pack, and verify() never re-counts the pack's own lines against the dataset row counts.
- manifest.json is deliberately NOT in manifest["files"] (it cannot hash itself). Any consumer iterating manifest["files"] to reconstruct the bundle will reconstruct one without its manifest.
- manifest["source"] embeds the absolute local path of the source database into an artefact designed to be uploaded off-machine.
- _write_table uses zip(header, row, strict=True) — any header/row length mismatch raises rather than silently padding, so a change to an export function's column count fails loudly at build time.
- CSV and JSONL disagree by design: CSV is utf-8-sig (BOM) with a header row for Excel; JSONL is plain utf-8 with keys per row and preserves null-vs-empty-string and numeric types. Only the JSONL feeds the panel; the CSV is dead weight in the pack path but still hashed, verified and zipped.
- The JS's toCsv rebuilds a header from the rows themselves (first-seen key union) rather than carrying the engine's header, so a panel-exported CSV's column ORDER can differ from the engine's datasets/*.csv, and a column that is absent from every row simply disappears.
- addLine drops any line whose "dataset" is not a string, but never checks "row" — an entry with dataset+table and no row pushes undefined into the rows array.

### Not answerable from the code

- Nothing in the shipped extension imports bundleview.js — only the two test harnesses do. Which panel screen is supposed to call readPanelPack, and where it obtains the Blob (Drive download? chrome.downloads? file picker?), is not in either file.
- pack()'s archive filename is entirely caller-supplied; bundle.py defines no naming convention. What the callers actually name it (and whether latest.json points at the .zip or at panel.jsonl.gz for the bare-panel path) lives outside this module — I did not read the Drive/latest.json code.
- Whether anything ever calls build() with source_keys set, and where the 12-dataset figure in the comment comes from, is not determinable from bundle.py.
- The exact column names inside a 'row' object are whatever reports.EXPORT_COLUMNS plus the dynamically appended axis/promoted-attribute columns produce (_with_axis_columns); they are data-dependent per source and are not fixed by bundle.py.
- No code here enforces a maximum bundle or archive size; whether an upload path imposes one (Drive quota, chunking) is outside this file.

---

## extension/app.js — the view system, the Data page, and where an offline bundle source would plug in

- Views are a flat string array `VIEWS`, and each id maps by convention to a DOM section with id `view-<id>`. The eleven ids are: profile, engines, source, run, data, sources, source-edit, appearance, finance, console, settings.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:151-158`
- There is no registry object and no route table. Switching is `showView(name, animate = true)`, which toggles the `hidden` class on every `view-<id>` section: `for (const v of VIEWS) $(`view-${v}`).classList.toggle("hidden", v !== name);`
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:296-301`
- showView also drives the rail: it finds `nav.side-rail button[data-view="<name>"]`, sets aria-selected / tabIndex / aria-current on every rail button, and moves the rail indicator. `source-edit` deliberately maps onto the `sources` rail button via `navigationName`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:298, 302-311`
- Per-view data loading is a tail of if-statements at the bottom of showView. The Data page's loader is called there unconditionally: `if (name === "data") loadDatasets();`
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:325-338`
- The current view is read back by scanning for the one section without `hidden`: `currentViewName()`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:341-343`
- Rail buttons are wired once at startup — every `nav.side-rail button[data-view]` gets a click handler calling `showView(b.dataset.view)`, plus ArrowUp/ArrowDown/Home/End roving-tabindex keyboard navigation that also calls showView.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:4331-4332, 4346-4357`
- The panel opens on `profile`, entered through showView rather than by relying on markup visibility.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:4375`
- The Data page markup is `<section id="view-data" class="hidden" role="tabpanel" aria-labelledby="tab-data">`, containing an `Open workbook` button (`#open-workbook`) in the header and one card `Browse Data` whose body is `<div id="datasets" class="dataset-list">` pre-seeded with two `.skeleton` divs.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.html:513-540`
- The Data rail button is `<button class="rail-item" id="tab-data" role="tab" data-view="data" aria-controls="view-data">`, sitting inside `<div id="engine-tablist">` alongside Source, Run and Google Finance.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.html:1713, 1731-1738`
- The Data page gets its rows from `loadDatasets()`, which makes exactly ONE call — `await api("/api/sources")` — and never queries records/rows directly.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:3244-3247`
- Rows shown are sources filtered by a counter carried on the source record, not by reading data: `const withData = sources.filter((s) => s.observations > 0);`. Each card prints `s.observations` as the metric, `fmtCount(s.products)` products, and `freshnessLine(s)`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:3248, 3253-3262`
- loadDatasets renders into `$("datasets")` by wholesale `innerHTML` assignment, then re-attaches click and Enter/Space keydown handlers to every `[data-open]` card.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:3245, 3253, 3263-3270`
- The empty state is engine-answered-but-nothing-stored: `box.innerHTML = `<div class="card"><span class="muted">No data yet. Run a crawl from the Run tab.</span></div>`;`
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:3249-3252`
- The engine-absent branch on the Data page is the bare catch of loadDatasets — one message for every failure mode: `catch (_) { box.innerHTML = `<div class="card"><span class="err">Couldn't reach the engine.</span></div>`; }`. That is the whole of what the Data page shows with no engine: header, Open workbook button, Browse Data card, and one red line. No dataset list, no fallback source, no action.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:3271-3273`
- Nothing else in the panel branches on engine presence for the Data page. `render()` — the whole-panel refresh — when `!engine.running` only unhides `#setup`, clears the poll timer, blanks the miniplayer and rewrites `#sites` (the Run page list). It never touches `#datasets`, and it never disables or hides `#tab-data` or `#engine-tablist`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:4090-4109`
- `#engine-tablist` (Source / Run / Data / Finance) is referenced nowhere in JavaScript — a repo-wide grep hits only app.html:1713 and the diagnostic copy. So with no engine the Data tab stays fully enabled and clickable, and clicking it runs loadDatasets into its catch every time.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.html:1713`
- Both Data-page navigations point at the engine's HTTP origin, so they are dead links when the engine is absent: `openDataset(key)` calls `openTab("/source/" + key)`, and Open workbook calls `openTab("/data")`. `openTab` is `chrome.tabs.create({ url: (await backendBase()) + path })`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:122, 3294-3296, 4526`
- The state object literal declares, relevant to engine presence: `engineUp: false, engineState: "checking"`, `installedVersion: "", engineVersion: "", versionReport: null, versionStatus: "pending"`, `engineProtocol: null, protocolMismatch: false`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:128-147`
- Account fields in state: `token: "", account: null, accountStatus: null`. `token` is the copy the panel lends onward and is never written to storage; `account` holds `{name, email, picture}` from `accountFor`; `accountStatus` holds a non-ok lookup result with `{detail, retryable}`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:139-140, 2277-2306, 2415-2427`
- Data-relevant state fields: `sources: []` (filled only by `loadSources()`), `selected: new Set()`, `filter`, `sourceFilter`, `editingSourceKey`, `job`, `jobRef`, `logs`, `logSignature`, `logAtBottom`, `financeRates`, `financeSavedSettings`, `financeStatus`. There is NO state field for datasets — loadDatasets keeps nothing, it refetches and repaints on every entry into the view.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:129-132, 1944-1947, 3244-3274`
- `state.engineReachable` is written by setStatus but is NOT declared in the state literal, so it is `undefined` until the first health answer lands. engineStatusFromState reads it.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:497, 2500`
- engineState is a four-value enum computed once, in setStatus: `engine.running ? "ready" : engine.timedOut ? "timeout" : engine.reachable ? "stopped" : "unavailable"`, plus the transient "checking" set by setEngineChecking.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:462, 496-501`
- `checkEngine` defines what absence means: `running` is `h.worker_alive !== false` from /api/health; `reachable: false` plus `timedOut`/`cancelled` is returned from the catch. Engine absence and engine-stopped are distinguishable at this layer.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/engine.js:21-57`
- The offline bundle READER already exists as a standalone ES module, `extension/bundleview.js`, exporting readPanelPack / datasetSummaries / rowsOf / toCsv, with `datasetSummaries` documented as "What the Data page lists when there is no engine to ask" and returning `{source_key, rows, tables, has_history}`.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/bundleview.js:28-85`
- bundleview.js is imported NOWHERE in the extension. A repo-wide grep finds it only in its own unit test and a Python round-trip test. app.js's import block (lines 10-19) does not mention it.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:10-19`
- The producer side is real: the engine writes `panel.jsonl.gz` into every bundle (`PANEL_PACK = "panel.jsonl.gz"`, written by `_write_panel_pack`, listed in manifest.json with size and sha256). So the file the Data page would read is already being produced — only the panel-side wiring is missing.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/scrapex/bundle.py:163, 204, 207-222`
- There is no backup/restore/Drive UI anywhere in app.js — no file picker, no download of a pack, no import control. Grepping app.js for backup/restore/Drive returns only source-wipe confirmation copy, the storage card's `backup_count` readout, and the workspace-nav description string.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:3530`
- All local /api/ traffic goes through one funnel: `api(path, options)` resolves `backendBase()`, applies `deadlineForLocalRequest`, and throws on non-2xx with `{status, kind: "http"}`. window.fetch itself is monkey-patched at module load to impose the same deadline policy on the shared appearance/timezone modules.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/app.js:79-112`

### Signatures a caller must satisfy

```
function showView(name, animate = true)  // app.js:296
function currentViewName()  // app.js:341
const VIEWS = ["profile", "engines", "source", "run", "data", "sources", "source-edit", "appearance", "finance", "console", "settings"]  // app.js:151-158
async function loadDatasets()  // app.js:3244 — no parameters, no return value, renders into $("datasets")
function freshnessLine(s)  // app.js:3279 — returns MARKUP; the call site must not esc() it
function openDataset(key)  // app.js:3294 — body is openTab("/source/" + key)
async function openTab(path)  // app.js:122 — chrome.tabs.create({url: (await backendBase()) + path})
async function api(path, options = {})  // app.js:92 — throws Object.assign(new Error(detail), {status, kind: "http"})
function sourceIdentity(source, compact = false, metricValue = null, metricLabel = "Row")  // app.js:1368 — returns markup
function fmtCount(n)  // app.js:2930
function sourceDomain(url)  // app.js:1363
async function loadSources()  // app.js:1944 — the only writer of state.sources
async function updateEngineState()  // app.js:715 — returns the engine object, or {cancelled: true}
function setStatus(engine)  // app.js:495 — sole writer of state.engineUp/engineState/engineReachable/engineVersion/engineProtocol/protocolMismatch
async function render()  // app.js:4090 — whole-panel refresh; the !engine.running branch is lines 4100-4104
function engineStatusFromState()  // app.js:2465 — returns {text, tone, detail}
export async function checkEngine({backend = null, signal = null, timeoutMs = STARTUP_DEADLINES.engineHealth} = {})  // engine.js:21
export async function readPanelPack(blob)  // bundleview.js:28 — returns Map<datasetKey, Map<tableName, row[]>>
export function datasetSummaries(datasets)  // bundleview.js:70 — returns [{source_key, rows, tables, has_history}] sorted by rows desc
export function rowsOf(datasets, key, table = "current")  // bundleview.js:82
export function toCsv(rows)  // bundleview.js:94 — UTF-8 BOM, CRLF
```

### Gotchas

- loadDatasets' `catch (_)` at app.js:3271 swallows the error object entirely, so a timeout, an HTTP 500 from a running engine, a protocol mismatch, and an abort fired by closePanelWork on panel close all render the identical string "Couldn't reach the engine." Any offline-bundle branch that keys off "the engine is absent" must not be placed inside this catch — by the time control reaches it, the reason has already been discarded.
- The Data page's empty state ("No data yet. Run a crawl from the Run tab.") is reachable ONLY when the engine answers. With no engine you never see it; you see the error line instead. The two states are not on the same code path.
- showView calls loadDatasets() unconditionally (app.js:325) with no `state.engineUp` guard — unlike loadRunDestination (app.js:4068) which returns null when `!state.engineUp`. So the Data page already re-fires a doomed request on every visit, and an offline branch has a natural home here, but adding a guard at line 325 would also suppress the loader on the recover-from-stopped case.
- loadDatasets derives row counts from `s.observations` on the /api/sources record, while bundleview.datasetSummaries derives them from the actual rows in the pack (`(tables.get("current") || []).length`). The two numbers come from different places and will not agree — the pack counts current-table rows, `observations` counts observations.
- The card shape assumes engine-only fields that a bundle summary does not carry: `s.base_url` and `s.source_name` (fed to sourceIdentity/sourceDomain), `s.products`, and `s.last_success.{started_at,rows_seen,requests_count}` (fed to freshnessLine, which returns markup and is exempt from esc()). datasetSummaries returns only {source_key, rows, tables, has_history}.
- Both exits from the Data page — openDataset (app.js:3294) and #open-workbook (app.js:4526) — build URLs on backendBase(), i.e. http://127.0.0.1:8000. With no engine they open a tab to a refused connection. A bundle-backed list whose cards still call openDataset would render data and then dead-end on click.
- Nothing disables the Data tab when the engine is absent: `#engine-tablist` has zero JavaScript references repo-wide. The comment at app.html:1683-1687 claims every page in that group "is dead until an engine is installed", which is a statement of intent, not enforced code.
- `state.engineReachable` is assigned in setStatus (app.js:497) but is absent from the state literal (app.js:128-147), so it reads `undefined` before the first health answer. A new branch that tests it during startup would take the falsy path.
- state has no field for datasets at all. loadDatasets refetches and repaints from scratch on every entry into the view, so a decompressed pack (64 MB of text per the bundleview header comment) has nowhere to live and would be re-parsed per visit unless a field is added.
- window.fetch is replaced at module load (app.js:79-87) to attach panelController/backendController abort signals to any /api/ URL. Reading a local Blob or a chrome.storage-held pack bypasses that funnel entirely, so an offline path gets none of the deadline or cancellation behaviour the rest of the panel relies on.
- `DESTINATION_DATA_PATH` (app.js:89-90) matches /api/sources and fires the one-shot `first-destination-data-request` startup mark. Whichever call ends up first in an offline-first ordering changes what that trace measures.
- showView dereferences `$(`view-${v}`)` for every id in VIEWS (app.js:297, 301). Adding an id to VIEWS without a matching section in app.html throws on the next navigation — including for a hypothetical separate offline view.

### Not answerable from the code

- How a bare panel would OBTAIN panel.jsonl.gz. The engine writes it (scrapex/bundle.py:204) and bundleview.readPanelPack consumes a Blob, but app.js contains no file picker, no download, and no Drive/backup UI — so the acquisition step has no existing call site to point at.
- Whether the pack should be cached between panel opens, and where. chrome.storage.local is used only for the `backend` address (engine.js:10-17); nothing in the extension persists bulk data, and no quota decision is recorded in the code I read.
- Whether the offline Data page is meant to replace the engine-backed list or to be a distinct destination. VIEWS has no reserved id for it, and PANEL_DESTINATIONS (app.js:159) only names data and settings as panel-owned workspace keys.
- What openDataset should do offline. The bundle carries current/details/history tables per dataset (bundle.py:153-158) but the panel has no row-level view of its own — every dataset click currently leaves for the engine's web UI.

---

## HTTP surface of scrapex/webui/app.py relevant to backup, restore, bundles, Drive, export and tokens — plus the middleware protecting it and the /api/ paths the Chrome extension actually calls

- NO route anywhere in the HTTP surface accepts a Google OAuth access token from the caller. The only place any request header is read at all is the origin check in RefuseForeignOrigins.dispatch; there is no Authorization header read, no Bearer parsing, no access_token body field, in app.py, catalog_api.py, database_api.py or extract/api.py.
  <br>↳ `scrapex/webui/app.py:391 (`origin = request.headers.get("origin")` — the sole request.headers access in the file)`
- NO route mentions bundle or Drive-upload. scrapex/bundle.py, scrapex/drive.py, scrapex/gdrive.py, scrapex/backupschedule.py and scrapex/lease.py exist as modules but none of them is imported by the web layer, so none of them is reachable over HTTP. The only occurrence of the word 'bundle' in app.py is the noun 'bundled' in an error message.
  <br>↳ `scrapex/webui/app.py:31-140 (import block: no drive, gdrive, bundle, backupschedule or lease); scrapex/webui/app.py:2199`
- POST /api/storage/backup — no request body. Calls backup_now(conn, app.state.db_path) under the write lock via _storage_action; returns RunResult.as_state() = {"ok": bool, "rows": int, "location": str, "detail": str, "at": iso8601}. StorageRefused maps to 400.
  <br>↳ `scrapex/webui/app.py:2425-2427; _storage_action at scrapex/webui/app.py:2287-2297; RunResult.as_state at scrapex/settings.py:158-160`
- POST /api/storage/restore — body {"backup_path": "<absolute path>"}; empty/missing backup_path is a 400 ("backup_path is required"). It deliberately bypasses _storage_action (no DB connection may be open during the file switch on Windows) and calls app.state.runner.release_database() first. Response is RunResult.as_state(); StorageRefused (missing file, failed health check, insufficient space, backup already live) maps to 400.
  <br>↳ `scrapex/webui/app.py:2429-2452; restore() at scrapex/storage.py:839-870`
- GET /api/storage — no body. Returns storage_status(conn, db_path): {key, label, ready, blocker, path, folder, pointer, drive_kind, sizes:{db_bytes,wal_bytes,shm_bytes,backup_bytes,backup_count,free_bytes,total_bytes}, health:{ok,status,detail}, backups:[{path,name,bytes,modified_at,tag}], backup_folder, space_warning, last, migration}. This is the only storage route the extension calls.
  <br>↳ `scrapex/webui/app.py:2417-2423; scrapex/storage.py:1332-1354; list_backups at scrapex/storage.py:684-697; measure at scrapex/storage.py:343-352`
- POST /api/storage/export — body {"folder": "<path>"}; missing folder is a 400. Calls export_database(conn, db_path, folder) under the write lock; returns RunResult.as_state(). This is a local filesystem export of the database, not an upload.
  <br>↳ `scrapex/webui/app.py:2518-2524`
- POST /api/storage/start-fresh — body {"confirm": "start fresh"} exactly, else 400; 409 if any job is active. Releases the worker DB handle, seals the warehouse aside, initialises an empty one. Returns RunResult.as_state().
  <br>↳ `scrapex/webui/app.py:2454-2486`
- POST /api/storage/open-folder — body {"which": "database"|"backups"|"exports"} (defaults to "database"); anything else is 400. The caller can never pass an arbitrary path — `which` selects from a server-built dict. Returns RunResult.as_state().
  <br>↳ `scrapex/webui/app.py:2488-2508`
- POST /api/storage/repair (no body), POST /api/storage/compact (no body) — both run through _storage_action and return RunResult.as_state().
  <br>↳ `scrapex/webui/app.py:2510-2516`
- POST /api/storage/check-move — body {"folder": "<path>"}, 400 if empty. Returns {"ok": bool, "reason": str, "warning": str} and writes nothing.
  <br>↳ `scrapex/webui/app.py:2526-2533`
- POST /api/storage/move — body {"folder": "<path>"}, 400 if empty. Returns RunResult.as_state(); afterwards the process re-points app.state.db_path and rebuilds the DatabaseRegistry.
  <br>↳ `scrapex/webui/app.py:2535-2545`
- GET /export/{source_key}.xlsx — no body. Returns a binary xlsx (Content-Disposition attachment, filename `<source_key>-<YYYY-MM-DD>.xlsx`), built server-side from publish.workbook_tables. 404 if nothing ingested for that source, 501 if openpyxl is absent. Not an /api/ path, so it is outside the extension's own endpoint policy regex.
  <br>↳ `scrapex/webui/app.py:978-1008`
- POST /api/outputs/excel/export — body {"source_keys": [...]} or {"source_key": "a,b"} (comma/space string accepted); an empty pick is a 400 "source_keys is required". Response is the RunResult state merged with excel_status(conn). NotConfiguredError maps to 400.
  <br>↳ `scrapex/webui/app.py:2181-2184; _source_keys at scrapex/webui/app.py:3066-3077; _integration at scrapex/webui/app.py:2024-2038`
- GET /api/outputs/google — no body. Returns google_status(conn): {key, label, ready, blocker, connected, client_secret_present, token_path, folder, workbook, account:"", account_note, scopes:[...], last}. `connected` is simply whether the server-side token file at gdrive.TOKEN_PATH exists — the token lives on the engine's disk, never in a request.
  <br>↳ `scrapex/webui/app.py:2229-2235; scrapex/outputs.py:429-463`
- POST /api/outputs/google/connect — no body. Spawns a daemon thread running google_connect(), which does the desktop OAuth flow with a local callback server on the engine host. Returns {"status": "connecting", "note": "A browser window is opening for Google sign-in..."}. GET /api/outputs/google/connect polls that state: {"status": "idle"|"connecting"|"connected"|"error", "error": str}.
  <br>↳ `scrapex/webui/app.py:2237-2263`
- POST /api/outputs/google/push — body {"source_keys": [...]} (same _source_keys shape); returns the push RunResult state merged with google_status(conn). POST /api/outputs/google/disconnect — no body; returns {"disconnected": bool, "detail": "Signed out. Nothing in Drive was changed or removed."}.
  <br>↳ `scrapex/webui/app.py:2265-2281`
- POST /api/outputs/apps-script/token — no body. MINTS a token server-side (rotate_funnel_token) and returns it: {"token": "<secret>", "shown_once": true, "next_step": "...FUNNEL_TOKEN..."}. This is the one 'token' route and it emits a secret rather than accepting one; it is named in the code's own threat comment as the reason the old allow_origins=["*"] was dangerous.
  <br>↳ `scrapex/webui/app.py:2211-2227; threat note at scrapex/webui/app.py:461-466`
- Other apps-script routes: GET /api/outputs/apps-script (status), GET /api/outputs/apps-script/script -> {"script": "<text>"} or 404, POST /api/outputs/apps-script/test (no body), POST /api/outputs/apps-script/send (body {"source_keys":[...]}, only keys[0] is used).
  <br>↳ `scrapex/webui/app.py:2186-2209`
- GET /api/outputs — no body. Returns {"outputs": [ {key,label,ready,blocker,detail,required,settings_url,...} ]} for local_db, excel, apps_script and google. settings_url values are HTML page paths ("/exports", "/sync"), which is how the panel hands Drive setup off to the engine's own web page rather than hosting the form.
  <br>↳ `scrapex/webui/app.py:2003-2018; scrapex/outputs.py:533-536`
- GET /exports and GET /sync are HTML pages (Excel exports page, Google Sheets/Drive sync page). They are the surface where Drive is actually configured today.
  <br>↳ `scrapex/webui/app.py:1153 and scrapex/webui/app.py:1181`
- CORS: CORSMiddleware is mounted with allow_origin_regex=_ANY_EXTENSION (any chrome-extension:// id), allow_methods=["*"], allow_headers=["*"]. chrome-extension:// origins ARE allowed; no allow_credentials is set. Exact config: `app.add_middleware(CORSMiddleware, allow_origin_regex=_ANY_EXTENSION, allow_methods=["*"], allow_headers=["*"],)` with `_ANY_EXTENSION = r"^chrome-extension://[a-p]{32}$"`.
  <br>↳ `scrapex/webui/app.py:476-479; scrapex/webui/app.py:334`
- RefuseForeignOrigins (a BaseHTTPMiddleware, added last so it runs first) rejects any request whose Origin header is present, is not the engine's own scheme://netloc, and does not fullmatch the extension pattern — with 403 and detail "This engine answers its own pages and the ScrapeX extension only...". A request with NO Origin header is left alone entirely (engine pages, curl, local tools). The pattern is `^chrome-extension://(<id>|<id>)$` built from the native-messaging manifest's allowlist, falling back to _ANY_EXTENSION when no manifest exists yet.
  <br>↳ `scrapex/webui/app.py:367-406; pattern built at scrapex/webui/app.py:352-364; mounted at scrapex/webui/app.py:481`
- One route is exempt from the allowlist and reachable by ANY extension id: RELINK_PATH = "/api/native-host/register". POST body {"extension_id": "<24-40 alnum chars>"} (400 if malformed); it ADDS the id to the native-messaging manifest (additive, capped, printed to stdout) and returns {"ok": true, "manifest": "<path>", "extension_id": ..., "allowed_extension_ids": [...], "message": ...}.
  <br>↳ `scrapex/webui/app.py:383 and scrapex/webui/app.py:926-959`
- TrustedHostMiddleware is mounted with allowed_hosts=LOOPBACK_HOSTS, where `LOOPBACK_HOSTS = ["127.0.0.1", "localhost", "::1", "testserver"]` — the DNS-rebinding guard. Exact line: `app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOOPBACK_HOSTS)`.
  <br>↳ `scrapex/webui/app.py:338 and scrapex/webui/app.py:484`
- There is NO auth/token middleware and no per-route authentication dependency of any kind. Origin + Host are the entire protection model; anything that passes them may call every one of the 96 routes, including start-fresh, restore and the token-minting route.
  <br>↳ `scrapex/webui/app.py:476-484 (the complete middleware stack: CORSMiddleware, RefuseForeignOrigins, TrustedHostMiddleware)`
- extension/engine.js requests exactly ONE path: GET <backend>/api/health. Nothing else.
  <br>↳ `extension/engine.js:26`
- extension/app.js installs its own client-side endpoint policy — a fetch wrapper plus DESTINATION_DATA_PATH = /^\/api\/(?:sources|outputs|jobs|resolve|records|changes|schedules|storage|settings|fields|rates)(?:[/?]|$)/ — but that regex is only used to mark the first destination-data request for startup timing, not to block anything.
  <br>↳ `extension/app.js:89-90 and extension/app.js:97-100`
- The extension calls GET /api/storage (read-only status) and NEVER calls /api/storage/backup, /api/storage/restore, /api/storage/export, /api/storage/move, /api/storage/start-fresh, /api/outputs/google/*, /api/outputs/apps-script/*, /api/outputs/excel/export or /export/{key}.xlsx. For output setup it opens the engine's HTML page in a new tab instead (openTab(o.settings_url) -> /exports or /sync).
  <br>↳ `extension/app.js:3522 (the only storage call) and extension/app.js:3485-3486, 3515-3516`
- The panel DOES hold a Google OAuth access token (chrome.identity, scopes userinfo.email, userinfo.profile and drive.file) in state.token, and the comment at app.js:2198 says "The extension owns the token and lends it to the engine (the owner's ruling of 2026-08-05)" — but no code lends it: the token is only ever passed to accountFor()/revokeToken(), which call Google's own https://www.googleapis.com/oauth2/v3/userinfo and https://oauth2.googleapis.com/revoke. state.token never reaches api()/post()/del() or any backend URL.
  <br>↳ `extension/app.js:2197-2199, 2274, 2330-2337, 4308; extension/identity.js:43-50, 174, 259-262`

### Signatures a caller must satisfy

```
POST /api/storage/backup  ->  def api_storage_backup()  # no body; returns {ok, rows, location, detail, at}  [app.py:2425]
POST /api/storage/restore  ->  def api_storage_restore(body: dict)  # body {"backup_path": str} required; returns {ok, rows, location, detail, at}  [app.py:2429]
GET  /api/storage  ->  def api_storage()  # returns storage_status(conn, db_path)  [app.py:2417]
POST /api/storage/export  ->  def api_storage_export(body: dict)  # body {"folder": str} required  [app.py:2518]
POST /api/storage/start-fresh  ->  def api_storage_start_fresh(body: dict)  # body {"confirm": "start fresh"}  [app.py:2454]
POST /api/storage/open-folder  ->  def api_storage_open_folder(body: dict)  # body {"which": "database"|"backups"|"exports"}  [app.py:2488]
POST /api/storage/repair  ->  def api_storage_repair()  # no body  [app.py:2510]
POST /api/storage/compact  ->  def api_storage_compact()  # no body  [app.py:2514]
POST /api/storage/check-move  ->  def api_storage_check_move(body: dict)  # body {"folder": str}; returns {ok, reason, warning}  [app.py:2526]
POST /api/storage/move  ->  def api_storage_move(body: dict)  # body {"folder": str}  [app.py:2535]
GET  /export/{source_key}.xlsx  ->  def export_workbook(source_key: str)  # returns binary xlsx attachment  [app.py:978]
GET  /api/outputs  ->  def api_outputs()  # returns {"outputs": [...]}  [app.py:2003]
POST /api/outputs/excel/export  ->  def api_excel_export(body: dict)  # body {"source_keys": [str]} | {"source_key": "a,b"}  [app.py:2181]
GET  /api/outputs/excel  ->  def api_excel_status()  [app.py:2173]
GET  /api/outputs/google  ->  def api_google_status()  # returns google_status(conn)  [app.py:2229]
POST /api/outputs/google/connect  ->  def api_google_connect()  # no body; returns {status:"connecting", note}  [app.py:2237]
GET  /api/outputs/google/connect  ->  def api_google_connect_state()  # returns {status, error}  [app.py:2261]
POST /api/outputs/google/push  ->  def api_google_push(body: dict)  # body {"source_keys": [str]}  [app.py:2265]
POST /api/outputs/google/disconnect  ->  def api_google_disconnect()  # no body; returns {disconnected: bool, detail}  [app.py:2270]
GET  /api/outputs/apps-script  ->  def api_apps_script_status()  [app.py:2186]
GET  /api/outputs/apps-script/script  ->  def api_apps_script_source()  # returns {"script": str} or 404  [app.py:2194]
POST /api/outputs/apps-script/test  ->  def api_apps_script_test()  # no body  [app.py:2202]
POST /api/outputs/apps-script/send  ->  def api_apps_script_send(body: dict)  # body {"source_keys": [str]}, uses keys[0]  [app.py:2206]
POST /api/outputs/apps-script/token  ->  def api_apps_script_token()  # no body; RETURNS {"token": str, "shown_once": true, "next_step": str}  [app.py:2211]
POST /api/native-host/register  ->  def register_native_host(payload: dict)  # body {"extension_id": str}; the ONE origin-allowlist exemption  [app.py:926]
def storage_status(conn: sqlite3.Connection, db_path: Path | str) -> dict  [storage.py:1332]
def backup_now(conn: sqlite3.Connection, db_path: Path | str, tag: str = "manual") -> RunResult  [storage.py:804]
def restore(db_path: Path | str, backup_path: Path | str) -> RunResult  [storage.py:839]
def export_database(conn: sqlite3.Connection, db_path: Path | str, ...) -> RunResult  [storage.py:1053]
RunResult.as_state() -> {"ok": bool, "rows": int, "location": str, "detail": str, "at": str}  [settings.py:158]
_source_keys(body) -> list[str]  # reads body["source_keys"] or body["source_key"], 400 on empty  [app.py:3066]
```

### Gotchas

- A request with NO Origin header bypasses RefuseForeignOrigins entirely (app.py:400 — `if origin and not is_engine_page and ...`). Any local process, curl, or non-browser client on the machine can call every route including /api/storage/restore and /api/outputs/apps-script/token. The middleware defends only against browser-originated cross-site requests.
- POST /api/native-host/register is reachable from ANY chrome-extension:// origin regardless of the manifest allowlist (app.py:383, 392-393) — this is deliberate (it is the repair path for a reloaded extension) but it means an id-agnostic write into the native-messaging manifest is part of the public surface.
- CORSMiddleware uses _ANY_EXTENSION (any 32-char extension id) while RefuseForeignOrigins uses the narrower manifest-derived pattern. So a non-allowlisted extension gets CORS headers back but a 403 body from every route except the relink path — the CORS layer is intentionally looser than the authorization layer.
- With no native-messaging manifest installed, extension_origin_regex() falls back to _ANY_EXTENSION (app.py:361-364), so before the one-time installer has run, ANY Chrome extension may drive the whole engine.
- /api/storage/restore does NOT go through _storage_action and does not open a DB connection during the switch — it calls app.state.runner.release_database() first. Any new code that opens a connection inside that window reintroduces the Windows rename failure that made every restore a 500 (documented at app.py:2431-2438).
- /api/storage/restore takes an arbitrary absolute filesystem path from the request body. It is validated only by existence, a health() check and free-space — not by being inside the backup folder.
- /api/storage/export and /api/storage/move likewise take an arbitrary destination folder path from the body.
- google_status().connected is derived purely from the existence of gdrive.TOKEN_PATH on the engine's disk — Drive auth today is a server-side desktop OAuth flow with a local callback server (app.py:2241-2243), completely independent of the token the extension holds via chrome.identity.
- The word 'token' in this codebase means two unrelated things: the funnel/Apps Script shared secret minted by POST /api/outputs/apps-script/token, and the Google OAuth token held by the extension. Neither ever travels from extension to engine.
- The panel's DESTINATION_DATA_PATH regex (app.js:89-90) looks like an allowlist but is only a startup-timing marker; the actual fetch wrapper (app.js:79-87) just attaches deadlines and abort signals.
- scrapex/bundle.py, drive.py, backupschedule.py and lease.py are implemented but unrouted — the 'M2a backup bundle', 'M2b lease' and 'M2c Drive' work exists in the library layer with no HTTP entry point at all.

### Not answerable from the code

- Whether scrapex/bundle.py, drive.py, backupschedule.py and lease.py are reachable through the CLI (scrapex/cli.py references bundle) — I only established that they are not reachable over HTTP.
- What gdrive.CLIENT_SECRET_PATH / TOKEN_PATH resolve to on disk, and whether the desktop OAuth client used by google_connect() is the same Google Cloud client as the extension's chrome.identity client.
- Whether any test or tool (outside extension/ and webui/) posts to /api/storage/restore or /api/outputs/* — I scoped the client-side search to extension/engine.js and extension/app.js as asked.
- Whether extension/background.js, transport.js or any other extension file (not in scope here) calls /api/ paths beyond those in engine.js and app.js.
- The exact shapes of excel_status() and apps_script_status(), which are merged into several responses — I read google_status() in full but only the call sites of the other two.

---

## extension/identity.js and its use in app.js; the Drive/bundle test surface and the constraints that govern it

- identity.js exports eight symbols: SCOPES, missingScopes, readTokenResult, getToken, revokeToken, ensureScope, accountFor, forgetToken. app.js imports only four of them.
  <br>↳ `C:/Users/User01/source/repos/ScrapeX/extension/identity.js:42,74,84,124,191,232,259,317 and C:/Users/User01/source/repos/ScrapeX/extension/app.js:15`
- getToken never rejects — it always resolves a discriminated object. Nine distinct shapes exist: {state:'ok',token}; {state:'partial',token,missing[],detail}; {state:'declined',detail}; {state:'authorization-required',detail}; {state:'misconfigured',detail}; {state:'failed',detail}; {state:'cancelled',retryable:true,detail}; {state:'timeout',retryable:true,detail}; {state:'failed',retryable:true,detail}.
  <br>↳ `identity.js:101, 88-99, 104-107, 108-111, 112-118, 119-120, 140-143, 150-155, 165-166`
- getToken's timeout defaults are asymmetric and come from STARTUP_DEADLINES: interactiveToken when interactive is true, silentToken when false. The signal option is wired to both an already-aborted check and an abort listener.
  <br>↳ `identity.js:126-128, 145-149`
- accountFor returns {state:'ok', account:{name,email,picture}} on success, with all three fields coerced to strings and defaulted to empty string when Google omits them. Nine failure shapes carry an explicit retryable boolean: timeout, network (retryable true); unauthorized(401), forbidden(403), client, malformed (retryable false); rate-limited(429), server(>=500) (retryable true).
  <br>↳ `identity.js:303-313, 266-273, 275-301`
- accountFor calls https://www.googleapis.com/oauth2/v3/userinfo with a Bearer header through fetchWithDeadline, bounded by STARTUP_DEADLINES.accountDetails.
  <br>↳ `identity.js:50, 262-264`
- forgetToken resolves undefined — it has no return value at all. It resolves immediately when token is falsy, otherwise wraps chrome.identity.removeCachedAuthToken. It only clears Chrome's cache; the grant at Google survives.
  <br>↳ `identity.js:317-322, 171-173`
- revokeToken POSTs the token to https://oauth2.googleapis.com/revoke as form-encoded, treats both 200 and 400 as successfully revoked, and ALWAYS calls forgetToken afterwards regardless of the revoke outcome. Three return shapes: {state:'ok',revoked:false} for no token, {state:'ok',revoked:true}, {state:'local-only',revoked:false,detail}.
  <br>↳ `identity.js:174, 191-217 (205 for the 400 rule, 214 for the unconditional forgetToken)`
- app.js call site 1 — loadAccount() calls getToken({interactive, signal: panelController.signal}). Any state other than 'ok' clears state.token/account/accountStatus and renders a problem ONLY when the call was interactive or the state was timeout/failed; a silent check that found nobody shows nothing.
  <br>↳ `app.js:2255-2270`
- app.js call site 2 — loadAccount() then calls accountFor(result.token, window.fetch, {signal}). On 'ok' it stores both token and account. On 'unauthorized' it calls forgetToken(result.token), clears state, and renders an authorization-required notice. On EVERY other failure it KEEPS the token, sets state.accountStatus to the failure object, and renders.
  <br>↳ `app.js:2273-2306 (forgetToken at 2286)`
- app.js call site 3 — loadAccountDetails() calls accountFor(token, window.fetch, {signal}) as the retry path behind the Retry button, and calls forgetToken(token) on 'unauthorized' before moving focus back to the sign-in button.
  <br>↳ `app.js:2329-2365 (accountFor at 2337, forgetToken at 2346, Retry wired at 2419)`
- app.js call site 4 — the Sign out click handler calls revokeToken(state.token). It bumps accountGeneration BEFORE the await so an in-flight account check cannot repaint the account just signed out of. A 'local-only' result is surfaced to the user as a tokenProblem saying this browser forgot the account but Google still lists ScrapeX.
  <br>↳ `app.js:4296-4324 (accountGeneration at 4303, revokeToken at 4308, local-only branch at 4312-4319)`
- getToken's 'partial' state is never handled distinctly in app.js. loadAccount treats anything not 'ok' as signed out, so a token that carries email+profile but NOT drive.file is discarded and the panel shows the signed-out card — the partial detail text only reaches the user as a one-off notice on an interactive press.
  <br>↳ `app.js:2263-2270 vs identity.js:88-99`
- ensureScope — the function written specifically to obtain drive.file at the moment a feature needs it — has zero callers in app.js or anywhere else in extension/. It is exercised only by its own test file.
  <br>↳ `identity.js:232; grep over extension/ finds it only at extension/tests/granted-scopes.test.mjs:15,84,96,107,120`
- The token is stored ONLY in the in-memory state object as state.token, initialised to empty string, with an inline comment saying it is never written to storage.
  <br>↳ `app.js:128-147 (comment at 138-139, `token: ""` at 140)`
- The token is never persisted anywhere. localStorage is used only by timezone.js and appearance.js; chrome.storage.session only by startup-trace.js/background.js for startup marks; chrome.storage.local only by engine.js for the `backend` URL. background.js contains no reference to token, identity, or getAuthToken.
  <br>↳ `extension/timezone.js:333,343; extension/appearance.js:167-179; extension/startup-trace.js:42; extension/background.js:170; extension/engine.js:11,16; grep for token|identity|getAuthToken in background.js returns no matches`
- The token is never sent to the engine. transport.js contains no Authorization or Bearer header and no reference to a token. state.token is read in only 15 places, all of them panel display or sign-out logic.
  <br>↳ `grep for Authorization|Bearer|token in extension/transport.js returns no matches; state.token appears only at app.js:2213,2226,2265,2278,2288,2302,2309,2330,2348,2368,4288,4308,4309,4627`
- The Profile panel has exactly three states in markup: welcome-checking, welcome-signed-out, welcome-signed-in. The signed-in card shows a photo, a name, an email, a status notice, a Retry button, and Sign out — and nothing else.
  <br>↳ `extension/app.html:1091-1153 (checking 1100, signed-out 1109, signed-in 1136; photo 1139, name 1140, email 1141, status 1142-1143, retry 1144, signout 1148)`
- renderAccount falls back to the literal word 'Signed in' for the name when the profile is unreadable, hides the email when empty, hides the photo on load error, and mirrors the picture into the rail avatar via setProfileAvatar.
  <br>↳ `app.js:2367-2431 (name fallback 2399, email hide 2402, photo onerror 2406, setProfileAvatar 2413); setProfileAvatar defined at app.js:278-294`
- Accessibility labels are the only other place the account surfaces: the summary gets aria-label 'Signed in as {name}', and the rail tab gets 'Profile, signed in' / 'signed out' / 'checking account'.
  <br>↳ `app.js:2429 and app.js:2220-2232`
- The panel shows NOTHING about scopes, Drive access, last backup, or lease holder. A comment in wireStartupShell states this as the design: before sign-in there is 'no account, no backup, no lease'.
  <br>↳ `app.js:4372-4375`
- tests/test_the_warehouse_travels_through_drive.py imports both bundle and drive and is the Drive path's guard — 16 tests, no network, all through an httpx.MockTransport FakeDrive. It guards folder creation/reuse, trashed-folder refusal, upload-before-pointer ordering, refusal of an unverifying bundle, single latest.json, keep-3 retention, the pointer never being prunable, byte-exact restore, corruption refusal, newer-engine refusal, and three distinguished failures (401/403/no-token).
  <br>↳ `tests/test_the_warehouse_travels_through_drive.py:31, 39, 175, 186, 202, 225, 238, 250, 261, 270, 281, 291, 307, 313, 331, 341, 352`
- test_this_module_never_stores_a_token is a source-text guard: it reads scrapex/drive.py and asserts none of 'write_text(token', 'json.dump(token', 'keyring', 'refresh_token', 'client_secret' appear. It cites the owner's ruling of 2026-08-05 as the reason.
  <br>↳ `tests/test_the_warehouse_travels_through_drive.py:360-371`
- tests/test_a_bundle_a_bare_extension_can_read.py imports scrapex.bundle — 16 tests guarding bundle contents and verification: db+export+manifest present, an uncrawled source recorded not dropped, rows readable with no db/engine, Arabic-safe CSV, post-seal modification caught, same-size byte change caught, missing file caught by name, unnamed extra file caught, truncated export caught by row count, a later bundle_format refused whole, every fault reported not just the first, pack refusing an unverifying bundle, pack/unpack round-trip, zip-slip refused, and the bundled .db being a real openable warehouse.
  <br>↳ `tests/test_a_bundle_a_bare_extension_can_read.py:37, 80, 98, 111, 134, 148, 161, 183, 195, 208, 229, 243, 258, 269, 286, 303`
- tests/test_the_panel_reads_what_the_engine_wrote.py imports scrapex.bundle and drives the JavaScript reader against the Python writer through a subprocess — 6 tests: rows survive, Arabic survives two languages and a compressor, a Python number is a JavaScript number, the columns are the engine's own EXPORT_HEADER, the panel's CSV matches the engine's, and the pack is inside the bundle and checksummed.
  <br>↳ `tests/test_the_panel_reads_what_the_engine_wrote.py:25, 99, 111, 121, 131, 144, 162`
- tests/test_gdrive.py guards a DIFFERENT, older path — scrapex.gdrive with DriveManager, Sheets MIME types and MagicMock, not the bundle path. 8 tests: ensure_folder create/reuse, ensure_spreadsheet in folder, apostrophe escaping in the find query, write_tab add-then-write, write_tab skip-addSheet, oversize rejection, urls, export shape.
  <br>↳ `tests/test_gdrive.py:15, 28, 36, 43, 52, 59, 74, 82, 88, 95`
- tests/test_outputs.py does not import the module but monkeypatches scrapex.gdrive.CLIENT_SECRET_PATH and TOKEN_PATH — the legacy engine-side Google sign-in that writes a token.json to disk. It asserts the account line is empty with a 'not requested' note, and that disconnect removes only the local sign-in. This is a second, contradictory token mechanism to the extension's.
  <br>↳ `tests/test_outputs.py:285-286, 301-306, 309-315, 383`
- Two adjacent suites guard the same milestone without importing drive or bundle: tests/test_one_device_writes_at_a_time.py imports scrapex.lease (15 tests — refusal with who and how long, renewal, expiry recovery, clean handover, unreadable lease treated as gone, atomic write, stable device identity), and tests/test_you_decide_when_the_backup_happens.py imports scrapex.backupschedule (14 tests — default changed-only, every refusal naming its setting, 'off' outranked by nothing, a press outranking every schedule but off, intervals, ceilings, clock moved only by a successful upload).
  <br>↳ `tests/test_one_device_writes_at_a_time.py:25,42-210 and tests/test_you_decide_when_the_backup_happens.py:24,49-211`
- extension/tests/bundleview.test.mjs covers extension/bundleview.js under node --test with no browser and no engine — 12 tests over readPanelPack, datasetSummaries, rowsOf and toCsv. Reading: two datasets from a gzipped JSONL pack with Arabic intact and history separated; numbers staying numbers so a column sorts correctly; dataset summaries carrying rows and has_history; a truncated download losing only its last row; a line with no dataset skipped rather than fatal; a final line with no trailing newline still yielded; a 200,000-character row reassembled across stream chunks. Exporting: CSV header as the union of all rows' keys in first-seen order (not the first row's), commas/quotes/newlines escaped, a UTF-8 BOM so Excel reads Arabic, and absent values written empty rather than the word undefined.
  <br>↳ `extension/tests/bundleview.test.mjs:10-15, 33, 42, 51, 62, 73, 83, 93, 105, 113, 119, 127; exports at extension/bundleview.js:28,70,82,94`
- docs/BACKLOG.md contains NO M2a, M2b, M2c or M3 entries, and no lease, Drive-backup or 'one device at a time' constraint. Its section headings run SR-1..SR-23, OP-1..OP-18, DEC-1..DEC-7, BV-1..BV-5, DEBT-*, Q-*, plus §6a in-flight, §6c separation audit, §7 done, and three appendices. DEC-1 through DEC-7 are about topology, shopify resume, custom_json rescue, the vocabulary sweep, unfinished sources, authenticated capture and branch cleanup — none touch Drive, the bundle or the lease.
  <br>↳ `docs/BACKLOG.md heading list at lines 1, 30, 63, 67-306, 308-374, 410-452, 462, 467, 534, 554, 626-720, 772, 784, 802`
- The 'one device at a time' constraint lives in docs/PLATFORM-PLAN.md as Decision 3, verbatim: '| 3 | **One device at a time, with restore.** | Drive is enough. No server, no shared SQLite file. A lease stops two devices at once. |'
  <br>↳ `docs/PLATFORM-PLAN.md:22`
- Decision 3 also settles a direct contradiction inside the plan, quoted verbatim: 'Decision 3 settles it: **Drive is backup and restore; the local database is the writer.**' — and the architecture section restates it as '1. **The local database is the writer.** Drive holds versioned backups and one lease, which names the device and expires, with a recovery path for a stale one.'
  <br>↳ `docs/PLATFORM-PLAN.md:68 and :123`
- M2 in PLATFORM-PLAN.md names four deliverables and one acceptance test, verbatim: 'A lease with device id and expiry, and a stale-lease recovery path.' / '**Done when:** a second machine restores the warehouse and refuses to run while the first holds the lease.' M3 is 'The panel reads the plain export from the bundle and shows datasets, rows and history with no engine installed, and exports to XLSX/CSV.'
  <br>↳ `docs/PLATFORM-PLAN.md:345-353 and :355-358`
- The token-ownership ruling that constrains any Drive work is recorded at the top of identity.js as the owner's ruling of 2026-08-05: the EXTENSION owns the token and lends it to the engine; Chrome holds, refreshes and scopes it; nothing is written to disk; the engine never sees a refresh token.
  <br>↳ `extension/identity.js:5-8`
- Decision 20's scope promise is enforced in code: spreadsheets was REMOVED before the first listing because nothing called the Sheets API, leaving userinfo.email, userinfo.profile and drive.file — and the file argues drive.file plus the Google Picker covers Decision 28's both-buttons case without a sensitive scope.
  <br>↳ `extension/identity.js:26-46`
- BACKLOG.md constraints that DO bear on this work even though not milestone-labelled: SR-10 — every setting lives in the extension, the web page display-only but must still show every value it stopped editing, enforced by tests/test_settings_live_in_the_extension.py; SR-5 — retention never deletes a price observation and the UI may never say 'recovered space' (a test fails on the phrase); SR-23 — CI green on every push including the extension node:test suite.
  <br>↳ `docs/BACKLOG.md:46, :41, :59`
- BACKLOG.md §6a records the engine-signing decision as closed and explicitly not to be re-proposed: the engine stays unsigned by decision on 2026-08-11, sole user, the only consequence being one Defender scan per download which the splash covers.
  <br>↳ `docs/BACKLOG.md:547-552`
- scrapex/drive.py, scrapex/lease.py, scrapex/bundle.py and scrapex/backupschedule.py have NO production caller anywhere. A precise import/call scan across scrapex/, webui/ and tools/ finds exactly two lines: drive.py importing bundle, and drive.py calling bundle.pack and bundle.unpack. No CLI command, no HTTP route, no job hook reaches any of them — the entire Drive/backup/lease path is built and fully tested but unreachable at runtime.
  <br>↳ `scrapex/drive.py:32, :232, :309 — and no other match for an import or a module-qualified call across scrapex/, webui/, tools/`

### Signatures a caller must satisfy

```
export function getToken({ interactive = true, identity = chrome.identity, runtime = chrome.runtime, timeoutMs = interactive ? STARTUP_DEADLINES.interactiveToken : STARTUP_DEADLINES.silentToken, signal = null } = {})  // identity.js:124 — returns Promise, never rejects
export async function accountFor(token, fetchImpl = fetch, {signal = null} = {})  // identity.js:259
export function forgetToken(token, { identity = chrome.identity } = {})  // identity.js:317 — resolves undefined
export async function revokeToken(token, { identity = chrome.identity, fetchImpl = fetch } = {})  // identity.js:191
export async function ensureScope(scope, { identity = chrome.identity, runtime = chrome.runtime } = {})  // identity.js:232 — currently uncalled outside tests
export function missingScopes(granted, wanted = SCOPES)  // identity.js:74 — returns null when granted is not an array
export function readTokenResult(token, lastError, grantedScopes)  // identity.js:84
export const SCOPES = [userinfo.email, userinfo.profile, drive.file]  // identity.js:42
def back_up(token: str, bundle_dir: Path | str, archive_path: Path | str, *, client: httpx.Client | None = None) -> Backup  # scrapex/drive.py:223
def restore(token: str, into: Path | str, *, client: httpx.Client | None = None) -> bundle.BundleReport  # scrapex/drive.py:274
def folder_id(token: str, client: httpx.Client | None = None) -> str  # scrapex/drive.py:98
def upload(token: str, path: Path | str, *, parent: str, ...) -> dict  # scrapex/drive.py:126
def download(token: str, file_id: str, path: Path | str, ...)  # scrapex/drive.py:155
def listing(token: str, parent: str, client: httpx.Client | None = None) -> list[dict]  # scrapex/drive.py:175
def delete(token: str, file_id: str, client: httpx.Client | None = None) -> None  # scrapex/drive.py:191
def prunable(files: list[dict], keep: int = KEEP) -> list[dict]  # scrapex/drive.py:212, KEEP = 3 at :51
def build(db_path: Path | str, out_dir: Path | str, *, ...)  # scrapex/bundle.py:122
def verify(bundle_dir: Path | str) -> BundleReport  # scrapex/bundle.py:242
def pack(bundle_dir: Path | str, archive_path: Path | str) -> dict  # scrapex/bundle.py:355
def unpack(archive_path: Path | str, out_dir: Path | str) -> BundleReport  # scrapex/bundle.py:379
export async function readPanelPack(blob)  // extension/bundleview.js:28
export function datasetSummaries(datasets)  // extension/bundleview.js:70
export function rowsOf(datasets, key, table = "current")  // extension/bundleview.js:82
export function toCsv(rows)  // extension/bundleview.js:94
```

### Gotchas

- getToken NEVER rejects — it resolves a state object in all nine cases including thrown exceptions from chrome.identity. Any caller written with try/catch expecting a rejection will silently treat a failure as a success.
- app.js has no handler for state 'partial'. loadAccount's `result.state !== 'ok'` branch discards a valid token that is merely missing drive.file, so today a Drive-less grant renders as signed OUT. Anything that needs drive.file cannot rely on state.token being present for a partially-granted account.
- forgetToken resolves with NO value. `const r = await forgetToken(t)` gives undefined, not a result object — unlike every other function in the file.
- revokeToken treats HTTP 400 from Google as SUCCESS (identity.js:205), because an already-invalid token has the same end state. A caller that checks only response.ok would report a spurious failure.
- revokeToken always drops Chrome's cached copy even when the network revoke failed, and reports that split state as 'local-only'. Silently collapsing 'local-only' into 'ok' would hide that the grant still stands in the owner's Google account — the panel deliberately says so out loud (app.js:4312-4319).
- ensureScope MUST drop the cached token before re-asking (identity.js:243) or Chrome returns the same partial token with no consent screen. That is documented in the function's header as the whole non-obvious step.
- accountFor distinguishes retryable from non-retryable via an explicit `retryable` boolean, and app.js branches on it to decide whether to show a Retry button (app.js:2415). A new state added without `retryable` renders as a dead-end message with no retry.
- The sign-out handler bumps accountGeneration BEFORE awaiting revokeToken (app.js:4303). Moving that bump after the await reintroduces the bug where an in-flight account check repaints the name and photo of the account just signed out of.
- There are TWO unrelated Google token mechanisms in this repo. The extension's chrome.identity token lives only in memory; scrapex/gdrive.py has a legacy TOKEN_PATH/CLIENT_SECRET_PATH that writes token.json to disk (tests/test_outputs.py:285-286,312,383). The extension-owns-the-token ruling (identity.js:5-8) is enforced only against scrapex/drive.py, not against scrapex/gdrive.py.
- tests/test_the_warehouse_travels_through_drive.py:360 is a source-TEXT assertion over scrapex/drive.py. Adding any of the strings 'write_text(token', 'json.dump(token', 'keyring', 'refresh_token', 'client_secret' to that file fails the suite, even in a comment.
- docs/BACKLOG.md is NOT where the milestone constraints live — it has no M2a/M2b/M2c/M3 entries at all. Reading only BACKLOG.md would miss Decision 3 entirely; the constraints are in docs/PLATFORM-PLAN.md:22, :68, :123, :345-358.
- The whole Drive/bundle/lease path has no production caller — scrapex/drive.py, lease.py, bundle.py and backupschedule.py are reached only by their own tests. The green suite proves the modules work, not that the feature exists.
- The panel currently exposes nothing about Drive scope, backup state or lease holder, and the profile card's markup has exactly three states (app.html:1100/1109/1136). There is no existing surface for a partial-scope or lease-conflict message.

### Not answerable from the code

- How the token is intended to travel from the panel to the engine — no mechanism exists today. transport.js sends no Authorization header, background.js never touches chrome.identity, and no native-messaging or HTTP shape for handing a token across was found.
- Whether scrapex/webui/app.py exposes any route that would call drive.back_up / drive.restore / lease.may_write. I confirmed no Python module imports them, but did not enumerate the 95 routes to see whether a route is stubbed under a different name.
- Whether scrapex/lease.py is consulted anywhere at crawl start. The lease module is fully tested but I found no caller; whether jobs.py is supposed to gate on it is unstated in the code I read.
- Whether the legacy scrapex/gdrive.py disk-token path is still reachable in the shipped release build, and whether the owner considers it superseded by the extension-owns-the-token ruling or a deliberate second path for M7.
- What UI Decision 24 anticipates for the signed-in profile page beyond name/email/photo — PLATFORM-PLAN.md:42 says explicitly that what the page shows after sign-in 'is decided when sign-in exists (M1)', and I found no follow-up entry recording that decision.
- Where docs/PLAN.md sits relative to PLATFORM-PLAN.md on these milestones — I did not read it, and it is newer (Aug 10) than PLATFORM-PLAN.md (Aug 9).

---
