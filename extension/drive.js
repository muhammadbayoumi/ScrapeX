// The owner's backups, in the owner's Drive — driven from the panel.
//
// THE OWNER'S RULING, 2026-08-11: the engine fetches and saves locally, and the
// extension owns every Google operation. So this file is where Drive lives now.
// The engine builds a bundle on its own disk and hands the bytes over the
// loopback; the token never leaves this extension and is never written down.
//
// IT REPLACES scrapex/drive.py, WHICH NEVER RAN. That module had zero importers
// — 300 lines that nothing in the repository could reach. It did have nineteen
// careful tests, and they are the reason this file exists rather than a port:
// the fake Drive they run against reads the boundary out of whatever
// Content-Type the client declares, so it accepts multipart/form-data exactly
// as readily as the multipart/related the real service requires. Nineteen tests
// could not catch the one defect that would have broken the feature on its
// first real use, because the fake was written to accept what the code sends.
//
// Porting it faithfully would have carried two defects across:
//
//   1. It sent multipart/form-data, because that is what httpx's `files=`
//      produces. Drive's multipart upload requires multipart/RELATED (RFC 2387,
//      metadata part first). The upload could never have succeeded.
//   2. Multipart upload is documented for files of 5 MB or less. The module's
//      own comment reasoned about 33 MB, which is the size at which that route
//      stops being allowed at all.
//
// So the upload here is RESUMABLE instead. It is the correct route at this size,
// and it pays for itself twice: a chunked upload is the only kind a browser can
// report progress for, because fetch() exposes no upload progress event. The
// owner asked for a loading bar; this is where it comes from.
//
// WHY THE MANIFEST NEEDS THE HOST PERMISSIONS, beyond simply being allowed to
// call: an extension request covered by host_permissions is not subject to CORS,
// so every response header is readable. The resumable handshake returns its
// session URI in the `Location` header, and a CORS-restricted response would
// hide it. The permission is not a formality here — without it this file cannot
// work at all.

const FILES = "https://www.googleapis.com/drive/v3/files";
const UPLOAD = "https://www.googleapis.com/upload/drive/v3/files";

/** One folder, made once and found thereafter. */
export const FOLDER_NAME = "ScrapeX backups";
const FOLDER_MIME = "application/vnd.google-apps.folder";

/** The pointer that says which upload is the current one. */
export const LATEST = "latest.json";

/**
 * The one file in a backup a browser can read on its own.
 *
 * A FIXED NAME, REPLACED EACH TIME, exactly like the pointer beside it — not a
 * stamped file per backup. Two reasons, and the second is the load-bearing one:
 *
 *   * it always describes the CURRENT data, which is the only thing a panel
 *     with no engine is asking for; nobody browses last week's backup.
 *   * `prunable` only ever proposes `.zip` files, so a stamped pack would be
 *     skipped by retention forever and accumulate one 4 MB file per backup
 *     until the owner noticed. Making it a replaced singleton removes that
 *     failure rather than adding a second rule to remember.
 */
export const PANEL_PACK = "panel.jsonl.gz";

/** How many bundles survive a prune. Three is a fortnight of daily backups
 * without asking the owner to think about it, and Drive quota is the owner's. */
export const KEEP = 3;

//: The bundle layout this panel knows how to read. Its twin is BUNDLE_FORMAT in
//: scrapex/bundle.py, and the pair is what lets an older device refuse a newer
//: backup by name rather than by failing to open it. Two constants that must
//: agree, in two languages that cannot import each other — the same arrangement
//: PROTOCOL_VERSION has, and held together the same way, by a test that reads
//: this line from Python.
export const BUNDLE_FORMAT = 1;

// A multiple of 256 KB, which Drive requires of every chunk but the last. Large
// enough that a 40 MB bundle is ten requests rather than a hundred, small enough
// that the progress bar moves often enough to be believed.
const CHUNK_BYTES = 4 * 1024 * 1024;

/** Something Drive refused, in words the owner can act on. */
export class DriveError extends Error {
  constructor(message, status = null, kind = "drive") {
    super(message);
    this.name = "DriveError";
    this.status = status;
    this.kind = kind;
  }
}

function headers(token, extra = {}) {
  if (!token) {
    throw new DriveError(
      "No Google account is connected. Sign in from the panel first.",
      null, "no-token");
  }
  return {Authorization: `Bearer ${token}`, ...extra};
}

/**
 * Turn a refused response into a sentence naming what was being attempted.
 *
 * The status is kept on the error because the caller's decision differs by it:
 * 401 means sign in again, 403 may mean quota, and a 5xx means try later. A
 * single opaque failure sends the owner to fix the wrong thing — the lesson
 * transport.js already learned and wrote down.
 */
async function refuse(response, doing) {
  let detail = "";
  try {
    const body = await response.json();
    detail = (body && body.error && body.error.message) || "";
  } catch (_) {
    try { detail = (await response.text()).slice(0, 200); } catch (_) { /* nothing */ }
  }
  const tail = detail ? ` — ${detail}` : "";

  // A DISABLED API IS A 403, AND IT IS NOT A PERMISSION PROBLEM.
  //
  // Found by the owner on 2026-08-12, creating his first spreadsheet: Google
  // answered 403 with "Google Drive API has not been used in project ... before
  // or it is disabled", and this function told him ScrapeX could only open
  // files it created — the drive.file explanation, which is true in general and
  // had nothing to do with what had just happened. He was sent to think about
  // permissions while the fix was one click in a console.
  //
  // Blaming a component that is working sends the owner to fix the wrong thing;
  // transport.js learned that and wrote it down, and this is the same lesson
  // arriving through a different door. The console URL is Google's own and
  // carries the project number, so it is repeated rather than summarised.
  if (/has not been used in project|SERVICE_DISABLED|accessNotConfigured/i.test(detail)) {
    return new DriveError(
      "This Google project has not switched on the API ScrapeX needs. Open the " +
      "link Google gives below, press Enable, wait a minute, and try again — " +
      "nothing is wrong with your account or your files." + tail,
      403, "api-disabled");
  }

  if (response.status === 401) {
    return new DriveError(
      `Google refused the token while ${doing}. Sign in again from the panel.${tail}`,
      401, "unauthorized");
  }
  if (response.status === 403) {
    return new DriveError(
      `Google refused permission while ${doing}. This is usually a full Drive ` +
      `or a rate limit rather than a wrong account.${tail}`, 403, "forbidden");
  }
  return new DriveError(`Google returned ${response.status} while ${doing}.${tail}`,
                        response.status, "drive");
}

async function ask(fetchImpl, url, init, doing) {
  let response;
  try {
    response = await fetchImpl(url, init);
  } catch (error) {
    // A network failure and a refusal are different problems with different
    // fixes, and collapsing them is how "you are offline" gets shown to someone
    // whose token simply expired.
    throw new DriveError(`Could not reach Google while ${doing}.`, null, "network");
  }
  if (!response.ok) throw await refuse(response, doing);
  return response;
}

/**
 * The id of ScrapeX's own folder, made once and found thereafter.
 *
 * Searched by name AND by `'me' in owners` and not trashed — a folder the owner
 * deleted must not be written into, or the backups go somewhere they can neither
 * see nor restore from. Carried over from the Python module, which had this part
 * right.
 */
export async function folderId(token, {fetchImpl = fetch} = {}) {
  const query = `name = '${FOLDER_NAME}' and mimeType = '${FOLDER_MIME}' ` +
                "and trashed = false and 'me' in owners";
  const found = await (await ask(
    fetchImpl,
    `${FILES}?${new URLSearchParams({q: query, fields: "files(id,name)"})}`,
    {headers: headers(token)},
    "looking for the backup folder")).json();

  const files = found.files || [];
  if (files.length) return files[0].id;

  const made = await (await ask(
    fetchImpl, `${FILES}?${new URLSearchParams({fields: "id"})}`,
    {
      method: "POST",
      headers: headers(token, {"Content-Type": "application/json"}),
      body: JSON.stringify({name: FOLDER_NAME, mimeType: FOLDER_MIME}),
    },
    "creating the backup folder")).json();
  return made.id;
}

/** What is in the folder, newest first. */
export async function listing(token, parent, {fetchImpl = fetch} = {}) {
  const found = await (await ask(
    fetchImpl,
    `${FILES}?${new URLSearchParams({
      q: `'${parent}' in parents and trashed = false`,
      orderBy: "createdTime desc",
      fields: "files(id,name,size,createdTime)",
    })}`,
    {headers: headers(token)},
    "listing the backup folder")).json();
  return found.files || [];
}

export async function remove(token, fileId, {fetchImpl = fetch} = {}) {
  await ask(fetchImpl, `${FILES}/${encodeURIComponent(fileId)}`,
            {method: "DELETE", headers: headers(token)}, `deleting ${fileId}`);
}

/**
 * Which bundles to delete, newest kept.
 *
 * Returned rather than deleted, so the caller — and the test — can see the
 * decision before anything is destroyed. `latest.json` is never a candidate: it
 * is the pointer, not a backup.
 *
 * It sorts by createdTime here rather than trusting the caller's order. The
 * Python version relied on the listing arriving newest-first and said so in a
 * comment; a function whose correctness depends on an argument's order, with
 * nothing checking that order, is one refactor away from deleting the newest
 * three and keeping the oldest.
 */
export function prunable(files, keep = KEEP) {
  const bundles = (files || []).filter((f) => (f.name || "").endsWith(".zip"));
  const newestFirst = [...bundles].sort(
    (a, b) => String(b.createdTime || "").localeCompare(String(a.createdTime || "")));
  return newestFirst.slice(keep);
}

/**
 * Send one file, in chunks, reporting progress as it goes.
 *
 * `onProgress` receives {sent, total} after every chunk. It is called with
 * {sent: 0} before the first byte so a bar can appear at once rather than after
 * the first four megabytes.
 */
/**
 * A blob, expressed as the thing `upload` actually needs.
 *
 * `upload` never wanted a Blob — it wanted a size and a way to get bytes
 * `[a, b)`. Saying so lets the same loop upload something that is never held
 * whole, and keeps every existing caller and test working unchanged.
 */
export function blobSource(blob) {
  return {size: blob.size, chunk: (start, end) => blob.slice(start, end)};
}

export async function upload(token, {
  blob, source = null, name, parent, mime = "application/zip", onProgress = null,
  fetchImpl = fetch,
} = {}) {
  // A SOURCE OR A BLOB, and a blob is just the simplest source. The archive is
  // uploaded from a source that fetches each chunk as it is sent, because holding
  // 541 MB in a side panel is what broke on 2026-09-03; the 4 MB panel-pack is
  // still a blob, because for that size the extra requests buy nothing.
  const from = source || (blob ? blobSource(blob) : null);
  if (!from) throw new DriveError("Nothing was given to upload.", null, "empty");
  const total = from.size;

  // STEP 1 — the handshake. Drive answers with a one-use session URI in the
  // Location header, and everything after this goes there rather than to the
  // upload endpoint.
  const start = await ask(
    fetchImpl,
    `${UPLOAD}?${new URLSearchParams({uploadType: "resumable"})}`,
    {
      method: "POST",
      headers: headers(token, {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": mime,
        "X-Upload-Content-Length": String(total),
      }),
      body: JSON.stringify({name, parents: parent ? [parent] : undefined}),
    },
    `starting the upload of ${name}`);

  const session = start.headers.get("location");
  if (!session) {
    // Reached when the response is CORS-restricted, which is what happens if
    // the host permission for this endpoint is ever dropped from the manifest.
    // Saying that here is cheaper than debugging an upload that stops on its
    // first line with no error at all.
    throw new DriveError(
      "Google accepted the upload request but its session address could not be " +
      "read. This is what a missing host permission for googleapis.com looks " +
      "like from inside the panel.", null, "no-session");
  }

  if (onProgress) onProgress({sent: 0, total});

  // STEP 2 — the bytes. A zero-length blob still needs one request, or Drive
  // never learns the upload is finished.
  let sent = 0;
  for (;;) {
    const end = Math.min(sent + CHUNK_BYTES, total);
    // `await`, because a chunk may be fetched rather than sliced. A source that
    // reads from the engine raises on a short read rather than uploading fewer
    // bytes than it promised.
    const chunk = await from.chunk(sent, end);
    const range = total === 0
      ? "bytes */0"
      : `bytes ${sent}-${end - 1}/${total}`;

    let response;
    try {
      response = await fetchImpl(session, {
        method: "PUT",
        headers: {"Content-Range": range},
        body: chunk,
      });
    } catch (error) {
      throw new DriveError(
        `The connection dropped after ${sent} of ${total} bytes of ${name}.`,
        null, "network");
    }

    // 308 is Drive saying "resume incomplete" — not an error and not a
    // redirect to follow. fetch() reports it with ok === false, so a plain
    // `if (!response.ok)` would abort every multi-chunk upload on its first
    // chunk. It carries a Range header of what it actually holds, and that,
    // not our own arithmetic, is where the next chunk starts.
    if (response.status === 308) {
      const held = response.headers.get("range");
      const match = held && /bytes=0-(\d+)/.exec(held);
      sent = match ? Number(match[1]) + 1 : end;
      if (onProgress) onProgress({sent, total});
      continue;
    }
    if (!response.ok) throw await refuse(response, `uploading ${name}`);

    if (onProgress) onProgress({sent: total, total});
    return await response.json();
  }
}

/**
 * Fetch one file by id.
 *
 * Returns a Blob rather than writing anywhere: the panel has no filesystem, and
 * every caller either hands the bytes to bundleview.js or offers them as a
 * download. Progress is reported when Drive sends a length; a response without
 * one still succeeds, with `total` null, because refusing to download a file
 * whose size is unknown would be a worse failure than a bar that cannot fill.
 */
export async function download(token, fileId, {
  onProgress = null, fetchImpl = fetch,
} = {}) {
  const response = await ask(
    fetchImpl,
    `${FILES}/${encodeURIComponent(fileId)}?${new URLSearchParams({alt: "media"})}`,
    {headers: headers(token)},
    `downloading ${fileId}`);

  const declared = Number(response.headers.get("content-length"));
  const total = Number.isFinite(declared) && declared > 0 ? declared : null;

  if (!onProgress || !response.body) return await response.blob();

  const reader = response.body.getReader();
  const parts = [];
  let received = 0;
  onProgress({received: 0, total});
  for (;;) {
    const {value, done} = await reader.read();
    if (done) break;
    parts.push(value);
    received += value.length;
    onProgress({received, total});
  }
  return new Blob(parts);
}

/**
 * Read the pointer that says which upload is current.
 *
 * Returns null when there is none, which is not a fault: it is what a Drive
 * looks like before the first backup, and every caller has to tell that apart
 * from a failure.
 */
export async function readLatest(token, parent, {fetchImpl = fetch} = {}) {
  const files = await listing(token, parent, {fetchImpl});
  const pointer = files.find((f) => f.name === LATEST);
  if (!pointer) return null;
  const blob = await download(token, pointer.id, {fetchImpl});
  try {
    return JSON.parse(await blob.text());
  } catch (_) {
    throw new DriveError(
      "The backup pointer in Drive could not be read. Nothing has been changed; " +
      "the next backup will replace it.", null, "malformed-pointer");
  }
}

/**
 * Upload an archive and only then say it is the latest.
 *
 * THE ORDER IS THE WHOLE POINT, and it is the one thing worth keeping from the
 * module this replaces. The archive goes up FIRST. The pointer is replaced
 * SECOND. Pruning happens LAST, after the pointer already names a file that is
 * certainly there. A pointer written first would, on a failed upload, name a
 * backup that does not exist — and a restoring machine would follow it.
 *
 * `manifest` is the bundle's own manifest, read by the engine and passed
 * through: this file never opens a bundle, because that is the engine's job and
 * doing it twice is how two readers of one format drift.
 */
/** Refuse a part whose length is not the length the engine described.
 *
 * `typeof`, NEVER truthiness. `if (described && ...)` is the shape that let the
 * 2026-08-30 backup through: a size of zero is falsy, so the comparison was
 * skipped, and THE CHECK SWITCHED ITSELF OFF AT EXACTLY THE VALUE THAT MEANS
 * THE THING IT CHECKS FOR HAS HAPPENED. A missing size is still forgiven — a
 * caller may legitimately have no manifest — but a size of zero is not missing.
 *
 * Exported for its own test. The truthiness bug is invisible in a test that
 * only ever passes plausible numbers, so it is asserted at zero directly.
 */
export function expectSize(what, blob, described) {
  if (typeof described !== "number") return;
  const size = blob ? blob.size : 0;
  if (size === described) return;
  throw new DriveError(
    `The engine built a ${what} of ${described} bytes and this panel read ` +
    `${size}. Nothing was uploaded, and the backup already in Drive is ` +
    "untouched. Restart the engine from the Engine page, then try again.",
    null, "mismatched");
}

export async function backUp(token, {
  archive, name, panelPack = null, manifest = {}, bundleFormat = 1,
  onProgress = null, fetchImpl = fetch,
} = {}) {
  // NOTHING COMPARED THE BYTES TO THE DESCRIPTION UNTIL 2026-08-30, and the
  // manifest was already being passed in when it happened. The engine's POST
  // reply says how long the archive is; the archive arrives from a SECOND
  // request that serves the newest file on disk. Two concurrent builds made
  // those two different things, and a 0-byte archive went to Drive under a
  // pointer carrying the complete build's digest -- a backup that reported
  // success and could restore nothing.
  //
  // Refused here, before a single byte leaves the machine, and refused twice:
  // the size must match what the engine described, AND an empty archive is
  // never a backup whatever anyone described. The second is not redundant --
  // it holds for a caller that passes no manifest at all.
  expectSize("archive", archive, manifest.bytes);
  expectSize("panel pack", panelPack, manifest.panel_pack?.bytes);
  if (!archive || archive.size === 0) {
    throw new DriveError(
      "The archive was empty, so nothing was uploaded. The backup already in " +
      "Drive is untouched.", null, "empty");
  }
  if (panelPack && panelPack.size === 0) {
    throw new DriveError(
      "The panel pack was empty, so nothing was uploaded. The backup already " +
      "in Drive is untouched.", null, "empty");
  }
  const parent = await folderId(token, {fetchImpl});

  // A SOURCE OR A BLOB, whichever the caller had. The panel hands a source that
  // fetches each chunk as it is sent; the tests hand a blob. `upload` treats a
  // blob as the simplest kind of source, so both take the same path through the
  // resumable session and neither is a second implementation.
  const stored = await upload(token, {
    ...(typeof archive?.chunk === "function" ? {source: archive} : {blob: archive}),
    name, parent, onProgress, fetchImpl,
  });

  // THE PANEL PACK, BEFORE THE POINTER AND AFTER THE ARCHIVE. Its place in the
  // order follows the same rule as everything else here: the pointer is written
  // last, so it can only ever name files that have already arrived. A pointer
  // promising a pack that failed to upload would send a bare panel to fetch
  // something that is not there — with no engine on that machine to explain it.
  let packed = null;
  if (panelPack) {
    const existing = await listing(token, parent, {fetchImpl});
    for (const file of existing.filter((f) => f.name === PANEL_PACK)) {
      await remove(token, file.id, {fetchImpl});
    }
    packed = await upload(token, {
      blob: panelPack, name: PANEL_PACK, parent,
      mime: "application/gzip", fetchImpl,
    });
  }

  const pointer = {
    file_id: stored.id,
    name: stored.name || name,
    bytes: archive.size,
    sha256: manifest.sha256 || "",
    created_at: manifest.created_at || "",
    engine_version: manifest.engine_version || "",
    bundle_format: bundleFormat,
    panel_pack: packed
      ? {file_id: packed.id, name: PANEL_PACK, bytes: panelPack.size}
      : null,
  };

  // Replace, never append. The old pointer is deleted before the new one is
  // written, so there is a moment with none — which a restore reports as "no
  // backup yet" rather than reading a stale one. Between naming the wrong
  // backup and naming none, none is the recoverable failure.
  const existing = await listing(token, parent, {fetchImpl});
  for (const file of existing.filter((f) => f.name === LATEST)) {
    await remove(token, file.id, {fetchImpl});
  }
  await upload(token, {
    blob: new Blob([JSON.stringify(pointer, null, 2) + "\n"],
                   {type: "application/json"}),
    name: LATEST, parent, mime: "application/json", fetchImpl,
  });

  const pruned = [];
  for (const old of prunable(await listing(token, parent, {fetchImpl}))) {
    await remove(token, old.id, {fetchImpl});
    pruned.push(old.name);
  }

  return {...pointer, parent, pruned};
}

/**
 * Fetch the current backup's bytes, checked against what the pointer promised.
 *
 * The size check is not the checksum the engine does — a browser cannot cheaply
 * hash 40 MB without blocking — but a truncated download is the failure that
 * actually happens, and it is the one this catches. Whoever unpacks the archive
 * verifies the rest.
 */
/**
 * What Drive says it is holding, without moving any of it.
 *
 * `size` and `md5Checksum` are metadata: one small request answers "is the backup
 * there, and is it whole" for a file of any size. The panel used to answer that by
 * DOWNLOADING the archive and looking at `archive.size`, which on a 541,531,989-byte
 * bundle asks a Chrome side panel to hold half a gigabyte — the same thing that
 * failed on the upload side on 2026-09-03.
 *
 * AND IT IS A STRONGER CHECK, not merely a cheaper one. Comparing a downloaded
 * size to the pointer catches a truncated DOWNLOAD. Drive's own stored size
 * catches a truncated UPLOAD — which is the failure that actually happened: a
 * 0-byte archive reached Drive on 2026-08-30 and the pointer described it as
 * whole. The question the owner is asking this button is about the copy in
 * Drive, and now that is the copy being examined.
 */
export async function metadata(token, fileId, {fetchImpl = fetch} = {}) {
  const response = await ask(
    fetchImpl,
    `${FILES}/${fileId}?${new URLSearchParams({
      fields: "id,name,size,md5Checksum,createdTime",
    })}`,
    {headers: headers(token)},
    `reading what Drive holds for ${fileId}`);
  const file = await response.json();
  // Drive returns `size` as a STRING. Compared with `!==` against a number from
  // the pointer it is never equal, and the check would report every healthy
  // backup as wrong — a guard that fails on correct input is one people learn to
  // route around.
  return {...file, size: file.size === undefined ? undefined : Number(file.size)};
}

/**
 * Prove the latest backup is there and complete. Downloads nothing.
 *
 * This is what the panel's check button needs and all it needs. `fetchLatest`
 * below still exists and still downloads, because a RESTORE has to have the
 * bytes — but a restore is a destructive act behind its own confirmation, and it
 * is not what this answers.
 */
/**
 * The latest pointer, or a DriveError saying why there is nothing usable.
 *
 * ONE GATE, NOT TWO. `verifyLatest` and `fetchLatest` must answer the same two
 * questions before they can do anything -- is there a backup, and is it one
 * this panel can read -- and each answered them with its own copy of the same
 * condition, the same "wrong-format" kind and the same sentence. A format
 * number is ONE piece of knowledge about ONE format: two copies mean a
 * BUNDLE_FORMAT bump has to be made twice, and missing one leaves a path that
 * silently accepts what the other refuses. `tail` was the only difference, and
 * it is context rather than knowledge -- a restore says "Nothing was restored",
 * a check that moved nothing has nothing to reassure anyone about.
 *
 * The format number exists so that a machine running last month's engine says
 * "update me" instead of opening an archive it does not understand and
 * reporting whatever it manages to read as the warehouse.
 */
async function readableLatest(token, {reads, tail = "", fetchImpl}) {
  const parent = await folderId(token, {fetchImpl});
  const pointer = await readLatest(token, parent, {fetchImpl});
  if (!pointer) {
    throw new DriveError(
      "No backup has been uploaded from any device yet.", null, "no-backup");
  }
  const format = pointer.bundle_format;
  if (format !== undefined && format !== null && format !== reads) {
    throw new DriveError(
      `That backup was written in bundle format ${format} and this device ` +
      `reads ${reads}. Update the ScrapeX engine on this machine, then try ` +
      `again.${tail}`, null, "wrong-format");
  }
  return pointer;
}

export async function verifyLatest(token, {reads = BUNDLE_FORMAT, fetchImpl = fetch} = {}) {
  const pointer = await readableLatest(token, {reads, fetchImpl});
  const held = await metadata(token, pointer.file_id, {fetchImpl});
  if (held.size === 0) {
    throw new DriveError(
      "The backup in Drive is empty, so there is nothing to restore from. Take " +
      "a new backup from this panel.", null, "empty");
  }
  // `typeof`, not truthiness, for the reason recorded on `fetchLatest`: a pointer
  // saying `bytes: 0` is the loudest failure here and truthiness reads it as
  // "nothing recorded, nothing to compare".
  if (typeof pointer.bytes === "number" && held.size !== pointer.bytes) {
    throw new DriveError(
      `Drive is holding ${held.size} bytes and the backup was recorded as ` +
      `${pointer.bytes}. The upload did not finish, so this copy is not whole.`,
      null, "truncated");
  }
  return {pointer, held};
}

export async function fetchLatest(token, {
  reads = BUNDLE_FORMAT, onProgress = null, fetchImpl = fetch,
} = {}) {
  const pointer = await readableLatest(
    token, {reads, tail: " Nothing was restored.", fetchImpl});
  const archive = await download(token, pointer.file_id, {onProgress, fetchImpl});
  // `typeof`, NOT `pointer.bytes &&`. The truthiness version read a pointer
  // saying `bytes: 0` as "no size recorded, nothing to compare" and returned an
  // empty archive as a good one -- THE GUARD WAS DISABLED BY EXACTLY THE VALUE
  // THAT MEANS THE THING IT GUARDS AGAINST HAS HAPPENED. A pointer with no
  // `bytes` at all is a genuinely older pointer and is still forgiven; a
  // pointer that says zero is now the loudest failure here.
  if (typeof pointer.bytes === "number" && archive.size !== pointer.bytes) {
    throw new DriveError(
      `The download stopped at ${archive.size} of ${pointer.bytes} bytes. ` +
      "Nothing was restored.", null, "truncated");
  }
  // Reached when a pointer carries no size at all, so the comparison above had
  // nothing to compare. An empty archive is unusable whatever the pointer says.
  if (archive.size === 0) {
    throw new DriveError(
      "The backup in Drive is empty, so there is nothing to restore. Take a " +
      "new backup from this panel.", null, "empty");
  }
  return {archive, pointer};
}

/**
 * The 4 MB a bare panel actually needs — no engine, no zip reader, no archive.
 *
 * THIS IS THE FUNCTION THE WHOLE ARRANGEMENT EXISTS FOR. The archive above is
 * 36 MB of zip that only an engine can open; this is one gzip file the browser
 * decompresses natively, and it carries every row the Data page shows.
 *
 * It reads the pointer FIRST rather than fetching `panel.jsonl.gz` by name.
 * Fetching by name would work and would also happily return a pack left behind
 * by a backup that never finished — the pointer is what says a pack belongs to
 * a complete one, which is the same reason nothing else here trusts a filename.
 */
export async function fetchPanelPack(token, {
  onProgress = null, fetchImpl = fetch,
} = {}) {
  const parent = await folderId(token, {fetchImpl});
  const pointer = await readLatest(token, parent, {fetchImpl});
  if (!pointer) {
    throw new DriveError(
      "No backup has been uploaded from any device yet.", null, "no-backup");
  }
  if (!pointer.panel_pack || !pointer.panel_pack.file_id) {
    // An OLD backup, made before the pack was carried separately. Saying that
    // is better than "no data": the owner's warehouse is safe, it is this one
    // screen that cannot open it, and the fix is one more backup.
    throw new DriveError(
      "That backup was made before ScrapeX could show data without the " +
      "engine. Back up once more from a machine that has the engine, and this " +
      "screen will work everywhere.", null, "no-panel-pack");
  }

  const pack = await download(token, pointer.panel_pack.file_id,
                              {onProgress, fetchImpl});
  const promised = pointer.panel_pack.bytes;
  if (promised && pack.size !== promised) {
    throw new DriveError(
      `The download stopped at ${pack.size} of ${promised} bytes, so the rows ` +
      "would be incomplete. Nothing is shown.", null, "truncated");
  }
  return {pack, pointer};
}
