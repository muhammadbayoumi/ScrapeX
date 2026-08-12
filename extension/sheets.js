// Spreadsheets in the owner's Drive — made, found, filled, and linked.
//
// THE OWNER'S RULING, 2026-08-11: the engine fetches and saves locally, and the
// extension owns every Google operation. This is the second half of that (the
// first is drive.js), and it is what replaces scrapex/gdrive.py.
//
// THE SCOPE DID NOT HAVE TO GROW, AND THAT IS THE POINT. gdrive.py asked for
//
//     https://www.googleapis.com/auth/drive.file        non-sensitive
//     https://www.googleapis.com/auth/spreadsheets      SENSITIVE
//
// while its own docstring, two lines above the list, claimed the choice "keeps
// the app out of Google's sensitive-scope verification". Google's Sheets API
// documentation lists drive.file among the scopes it accepts, and names it the
// recommended one; `spreadsheets` is the sensitive alternative and `drive` /
// `drive.readonly` are restricted. Everything gdrive.py touched was a file it
// had created itself — `files().create`, and a workbook identified by NAME
// rather than by a pasted id — so drive.file covered all of it and the
// sensitive scope bought nothing.
//
// It is gone with that module, and the panel's three scopes are unchanged.
//
// WHAT drive.file REACHES, exactly: files this app created, and files the owner
// hands it through the Google Picker. Not the rest of their Drive. That is a
// limit Google enforces rather than a promise this code keeps, which is why the
// privacy policy states it in those words.

const FILES = "https://www.googleapis.com/drive/v3/files";
const SHEETS = "https://sheets.googleapis.com/v4/spreadsheets";

const FOLDER_MIME = "application/vnd.google-apps.folder";
export const SHEET_MIME = "application/vnd.google-apps.spreadsheet";

// The cap gdrive.py carried, kept for the reason it carried it: a runaway export
// must never try to push millions of cells at a service that charges the owner
// in quota for the attempt.
export const MAX_EXPORT_ROWS = 40_000;

export class SheetsError extends Error {
  constructor(message, status = null, kind = "sheets") {
    super(message);
    this.name = "SheetsError";
    this.status = status;
    this.kind = kind;
  }
}

function headers(token, extra = {}) {
  if (!token) {
    throw new SheetsError(
      "No Google account is connected. Sign in from the panel first.",
      null, "no-token");
  }
  return {Authorization: `Bearer ${token}`, ...extra};
}

async function refuse(response, doing) {
  let detail = "";
  try {
    const body = await response.json();
    detail = (body && body.error && body.error.message) || "";
  } catch (_) {
    try { detail = (await response.text()).slice(0, 200); } catch (_) { /* nothing */ }
  }
  const tail = detail ? ` — ${detail}` : "";
  if (response.status === 401) {
    return new SheetsError(
      `Google refused the token while ${doing}. Sign in again from the panel.${tail}`,
      401, "unauthorized");
  }
  if (response.status === 403) {
    // The one worth naming apart. drive.file cannot open a spreadsheet this app
    // did not create and the owner did not hand over, and 403 is how Google
    // says so. "Permission denied" would send the owner to check their account,
    // which is not where the problem is.
    return new SheetsError(
      `Google refused access while ${doing}. ScrapeX can only open ` +
      "spreadsheets it created itself, or ones you choose for it — not the " +
      `rest of your Drive.${tail}`, 403, "not-ours");
  }
  return new SheetsError(`Google returned ${response.status} while ${doing}.${tail}`,
                         response.status, "sheets");
}

async function ask(fetchImpl, url, init, doing) {
  let response;
  try {
    response = await fetchImpl(url, init);
  } catch (_) {
    throw new SheetsError(`Could not reach Google while ${doing}.`, null, "network");
  }
  if (!response.ok) throw await refuse(response, doing);
  return response;
}

/**
 * Escape a name for a Drive query string.
 *
 * Backslash first, then the quote — the other order double-escapes every
 * backslash it just wrote. Carried across from gdrive.py's `_q_escape`, which
 * had it right; a workbook called `O'Brien's` is not a rare name and an
 * unescaped one turns a search into a syntax error the owner cannot read.
 */
function escapeQuery(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

async function findByName(token, {name, mime, parent = null, fetchImpl}) {
  let query = `name = '${escapeQuery(name)}' and mimeType = '${mime}' ` +
              "and trashed = false";
  if (parent) query += ` and '${parent}' in parents`;

  const found = await (await ask(
    fetchImpl, `${FILES}?${new URLSearchParams({
      q: query, spaces: "drive", fields: "files(id,name)",
    })}`,
    {headers: headers(token)}, `looking for ${name}`)).json();

  const files = found.files || [];
  return files.length ? files[0].id : null;
}

/** The folder, made once and found thereafter. */
export async function ensureFolder(token, name, {
  parent = null, fetchImpl = fetch,
} = {}) {
  const found = await findByName(token, {name, mime: FOLDER_MIME, parent, fetchImpl});
  if (found) return found;

  const body = {name, mimeType: FOLDER_MIME};
  if (parent) body.parents = [parent];
  const made = await (await ask(
    fetchImpl, `${FILES}?${new URLSearchParams({fields: "id"})}`,
    {
      method: "POST",
      headers: headers(token, {"Content-Type": "application/json"}),
      body: JSON.stringify(body),
    },
    `creating the folder ${name}`)).json();
  return made.id;
}

/**
 * The spreadsheet, made once and found thereafter — and its link.
 *
 * `webViewLink` is asked for from Drive rather than assembled from the id. The
 * Python module built the URL by hand from a template, which is correct today
 * and is a guess about a URL shape ScrapeX does not own. Asking costs nothing:
 * it is a field on a response already being read.
 */
export async function ensureSpreadsheet(token, name, {
  folder = null, fetchImpl = fetch,
} = {}) {
  const existing = await findByName(
    token, {name, mime: SHEET_MIME, parent: folder, fetchImpl});

  if (existing) {
    const known = await (await ask(
      fetchImpl,
      `${FILES}/${encodeURIComponent(existing)}?${new URLSearchParams({
        fields: "id,name,webViewLink",
      })}`,
      {headers: headers(token)}, `reading the link for ${name}`)).json();
    return {id: known.id, name: known.name, url: known.webViewLink, created: false};
  }

  const body = {name, mimeType: SHEET_MIME};
  if (folder) body.parents = [folder];
  const made = await (await ask(
    fetchImpl,
    `${FILES}?${new URLSearchParams({fields: "id,name,webViewLink"})}`,
    {
      method: "POST",
      headers: headers(token, {"Content-Type": "application/json"}),
      body: JSON.stringify(body),
    },
    `creating the spreadsheet ${name}`)).json();
  return {id: made.id, name: made.name, url: made.webViewLink, created: true};
}

/** The tabs a spreadsheet already has. */
export async function tabsOf(token, spreadsheetId, {fetchImpl = fetch} = {}) {
  const meta = await (await ask(
    fetchImpl,
    `${SHEETS}/${encodeURIComponent(spreadsheetId)}?${new URLSearchParams({
      fields: "sheets(properties(title))",
    })}`,
    {headers: headers(token)}, "reading the spreadsheet's tabs")).json();
  return (meta.sheets || []).map((s) => s.properties.title);
}

async function ensureTab(token, spreadsheetId, tab, {fetchImpl}) {
  if ((await tabsOf(token, spreadsheetId, {fetchImpl})).includes(tab)) return;
  await ask(
    fetchImpl, `${SHEETS}/${encodeURIComponent(spreadsheetId)}:batchUpdate`,
    {
      method: "POST",
      headers: headers(token, {"Content-Type": "application/json"}),
      body: JSON.stringify({
        requests: [{addSheet: {properties: {title: tab}}}],
      }),
    },
    `adding the tab ${tab}`);
}

/**
 * Replace one tab's contents with a header and rows.
 *
 * CLEARED FIRST, THEN WRITTEN, and the order is not cosmetic: an update alone
 * overwrites only the cells it covers, so a run that produces fewer rows than
 * the last one leaves the tail of the previous export in place. The owner would
 * be reading a table whose bottom half is last week's prices with nothing
 * saying so.
 *
 * RAW, not USER_ENTERED. A price of "1-2" or a code beginning with "=" must
 * arrive as the text it is; letting Sheets interpret it turns a product code
 * into a formula error and a date-shaped string into a date.
 */
export async function writeTab(token, spreadsheetId, {
  tab, header, rows, fetchImpl = fetch,
} = {}) {
  if (rows.length > MAX_EXPORT_ROWS) {
    throw new SheetsError(
      `${rows.length} rows is more than the ${MAX_EXPORT_ROWS} this export ` +
      "allows. Narrow the selection and try again; nothing was written.",
      null, "too-many-rows");
  }

  await ensureTab(token, spreadsheetId, tab, {fetchImpl});

  await ask(
    fetchImpl,
    `${SHEETS}/${encodeURIComponent(spreadsheetId)}/values/` +
    `${encodeURIComponent(`'${tab}'`)}:clear`,
    {
      method: "POST",
      headers: headers(token, {"Content-Type": "application/json"}),
      body: "{}",
    },
    `clearing the tab ${tab}`);

  await ask(
    fetchImpl,
    `${SHEETS}/${encodeURIComponent(spreadsheetId)}/values/` +
    `${encodeURIComponent(`'${tab}'!A1`)}?${new URLSearchParams({
      valueInputOption: "RAW",
    })}`,
    {
      method: "PUT",
      headers: headers(token, {"Content-Type": "application/json"}),
      body: JSON.stringify({values: [header, ...rows]}),
    },
    `writing the tab ${tab}`);

  return {tab, rows: rows.length};
}

/**
 * A spreadsheet the owner chose rather than one ScrapeX made.
 *
 * WHY THIS TAKES AN ID AND DOES NOT PICK. Google Picker is the only thing that
 * can widen drive.file to a file the owner already had, and it cannot run in
 * this panel: it needs `https://apis.google.com/js/api.js`, and Manifest V3
 * forbids an extension executing code fetched from a server. The Picker
 * therefore has to run on an ordinary web origin and hand the chosen id back.
 *
 * So this function is the half that CAN live here: given an id the owner's
 * choice has already unlocked, it confirms the file is reachable and is
 * actually a spreadsheet, and returns its name and link. If the id was never
 * picked, Google answers 403 and `refuse` above says why in the owner's terms
 * rather than as a permission error they cannot act on.
 */
export async function openChosen(token, spreadsheetId, {fetchImpl = fetch} = {}) {
  const known = await (await ask(
    fetchImpl,
    `${FILES}/${encodeURIComponent(spreadsheetId)}?${new URLSearchParams({
      fields: "id,name,mimeType,webViewLink",
    })}`,
    {headers: headers(token)}, "opening the spreadsheet you chose")).json();

  if (known.mimeType !== SHEET_MIME) {
    throw new SheetsError(
      `"${known.name}" is not a spreadsheet, so ScrapeX cannot write rows into ` +
      "it. Choose a Google Sheets file.", null, "not-a-spreadsheet");
  }
  return {id: known.id, name: known.name, url: known.webViewLink, created: false};
}
