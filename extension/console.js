// The Console — reads the add-in's configuration workbook, and says what is
// wrong with it before offering to change anything.
//
// THE ENGINE IS NOT INVOLVED. No fetch to 127.0.0.1, no import from anything
// that talks to it. The owner's ruling, restated 2026-08-12: «الكونسول يخص
// extension بنسبة 100%، المحرك غير مسؤول عنه اطلاقا».

import { getToken } from "./identity.js";
import { chooseSpreadsheet } from "./picker.js";
import { TAB_NAMES, parseWorkbook, inspect, vocabularies } from "./workbook.js";
import { KNOWN_VOCABULARIES, SHEET_GIDS } from "./addin-contract.js";

const $ = (id) => document.getElementById(id);
const SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets";

//: Where the chosen workbook is remembered. storage.local, not session: this is
//: a decision about which file the add-in reads, not a passing choice, and
//: making the owner find it again every morning would be its own defect.
const REMEMBERED = "scrapexConfigWorkbook";

const state = {token: "", fileId: "", name: ""};

function say(id, text, tone = "") {
  const node = $(id);
  if (!node) return;
  node.textContent = text;
  node.className = tone ? `hint ${tone}` : "hint";
}

// ---- Google -----------------------------------------------------------------

async function ask(path, token) {
  const answer = await fetch(`${SHEETS_API}/${path}`, {
    headers: {Authorization: `Bearer ${token}`},
  });
  if (!answer.ok) {
    let detail = `${answer.status}`;
    try {
      const body = await answer.json();
      detail = body?.error?.message || detail;
    } catch { /* a body that is not JSON tells us nothing extra */ }
    throw new Error(detail);
  }
  return answer.json();
}

/**
 * The tab ids of a spreadsheet, by tab name.
 *
 * `spreadsheets.get` with a fields mask, because the whole document would be
 * megabytes of cell data to answer a question about six names.
 */
async function tabsOf(fileId, token) {
  const book = await ask(
    `${encodeURIComponent(fileId)}?fields=properties.title,sheets.properties`,
    token);
  const tabs = {};
  for (const sheet of book.sheets || []) {
    const properties = sheet.properties || {};
    tabs[properties.title] = String(properties.sheetId);
  }
  return {title: book.properties?.title || "", tabs};
}

/** All six tabs in one call. */
async function readWorkbook(fileId, token) {
  const ranges = TAB_NAMES
    .map((tab) => `ranges=${encodeURIComponent(`'${tab}'!A1:CA2000`)}`)
    .join("&");
  const answer = await ask(
    `${encodeURIComponent(fileId)}/values:batchGet?${ranges}`, token);
  return parseWorkbook(answer.valueRanges || []);
}

// ---- is this even the right file --------------------------------------------

/**
 * THE CHECK THAT COMES BEFORE EVERY OTHER CHECK.
 *
 * The add-in does not find its configuration by name. `EndpointCatalog` carries
 * six tab ids compiled into the build, and fetches each one directly. So a
 * workbook can have all six tab NAMES, look perfect, and be a copy the add-in
 * has never read — and a Console that checked it would report that everything
 * is fine about a file nobody opens. That is a worse outcome than refusing.
 */
function identify(tabs) {
  const wrong = [];
  const absent = [];
  for (const [tab, gid] of Object.entries(SHEET_GIDS)) {
    if (!(tab in tabs)) absent.push(tab);
    else if (tabs[tab] !== gid) wrong.push({tab, found: tabs[tab], wanted: gid});
  }
  return {ok: !wrong.length && !absent.length, wrong, absent};
}

// ---- what it says -----------------------------------------------------------

function renderFindings(found) {
  const list = $("findings-list");
  list.textContent = "";

  const broken = found.filter((f) => f.severity === "broken");
  const unused = found.filter((f) => f.severity === "unused");

  if (!found.length) {
    say("findings-summary",
        "Nothing to report. Every reference resolves and every source has an "
        + "address the add-in can read.", "ok");
    return;
  }

  say("findings-summary",
      `${broken.length} ${broken.length === 1 ? "problem" : "problems"} that `
      + `would change what the add-in loads, and ${unused.length} that would `
      + "not.");

  for (const finding of found) {
    const row = document.createElement("div");
    row.className = `finding finding-${finding.severity}`;

    const where = document.createElement("span");
    where.className = "finding-where";
    where.textContent = finding.row
      ? `${finding.tab} · row ${finding.row}`
      : finding.tab;

    const kind = document.createElement("span");
    kind.className = "finding-kind";
    kind.textContent = finding.kind;

    const detail = document.createElement("p");
    detail.className = "finding-detail";
    detail.textContent = finding.detail;

    row.append(where, kind, detail);
    list.append(row);
  }
}

function renderSheets(workbook) {
  const list = $("sheets-list");
  list.textContent = "";
  const lists = vocabularies(workbook, KNOWN_VOCABULARIES);

  for (const tab of TAB_NAMES) {
    const sheet = workbook.sheets[tab];
    const row = document.createElement("div");
    row.className = "sheet-row";

    const name = document.createElement("span");
    name.className = "sheet-name";
    name.textContent = tab;

    const count = document.createElement("span");
    count.className = "sheet-count";
    count.textContent = sheet ? `${sheet.rows.length} rows` : "not found";

    row.append(name, count);
    list.append(row);
  }

  const note = document.createElement("p");
  note.className = "hint";
  note.textContent =
    `${lists.entityKeys.length} tables, ${lists.profileKeys.length} mapping `
    + `profiles, ${lists.sourceKeys.length} sources.`;
  list.append(note);
}

// ---- the flow ---------------------------------------------------------------

async function show(fileId) {
  say("workbook-state", "Reading the workbook…");
  $("findings-card").classList.add("hidden");
  $("sheets-card").classList.add("hidden");

  let identity;
  try {
    identity = await tabsOf(fileId, state.token);
  } catch (error) {
    say("workbook-state",
        `That workbook could not be opened: ${error.message}`, "err");
    return;
  }

  state.name = identity.title;
  const verdict = identify(identity.tabs);
  $("workbook-identity").textContent = identity.title;

  if (!verdict.ok) {
    // REFUSED, and told exactly why. "Something is wrong" would send the owner
    // looking at the data; the tab ids are the thing that is wrong.
    const parts = [];
    if (verdict.absent.length) {
      parts.push(`it has no ${verdict.absent.join(", ")}`);
    }
    for (const {tab, found, wanted} of verdict.wrong) {
      parts.push(`${tab} is tab ${found} here and the add-in reads tab ${wanted}`);
    }
    say("workbook-state",
        "This is not the workbook the add-in reads — " + parts.join("; ")
        + ". Nothing is shown, because checking the wrong file and reporting it "
        + "correct is worse than saying nothing.", "err");
    $("workbook-choose").hidden = false;
    return;
  }

  let workbook;
  try {
    workbook = await readWorkbook(fileId, state.token);
  } catch (error) {
    say("workbook-state", `The sheets could not be read: ${error.message}`, "err");
    return;
  }

  await chrome.storage.local.set({[REMEMBERED]: {fileId, name: identity.title}});
  say("workbook-state",
      "This is the workbook the add-in reads — all six tabs match.", "ok");
  $("workbook-choose").hidden = false;
  $("workbook-recheck").hidden = false;

  renderFindings(inspect(workbook));
  renderSheets(workbook);
  $("findings-card").classList.remove("hidden");
  $("sheets-card").classList.remove("hidden");
}

async function pick() {
  $("workbook-choose").disabled = true;
  say("workbook-state",
      "Choose the workbook in the tab that just opened, then come back here.");
  try {
    const picked = await chooseSpreadsheet({token: state.token, surface: "console"});
    if (!picked) {
      say("workbook-state", "Nothing was chosen.");
      return;
    }
    state.fileId = picked.fileId;
    await show(picked.fileId);
  } catch (error) {
    say("workbook-state", error.message || "The chooser could not be opened.", "err");
  } finally {
    $("workbook-choose").disabled = false;
  }
}

async function start() {
  const result = await getToken({interactive: false});
  if (result.state !== "ok" || !result.token) {
    say("workbook-state",
        "Sign in with Google from the ScrapeX panel first — this page reads a "
        + "spreadsheet with your account, and asks for nothing else.", "err");
    return;
  }
  state.token = result.token;

  const held = await chrome.storage.local.get(REMEMBERED);
  const remembered = held[REMEMBERED];
  $("workbook-choose").hidden = false;

  if (remembered?.fileId) {
    state.fileId = remembered.fileId;
    await show(remembered.fileId);
    return;
  }
  say("workbook-state",
      "Choose the workbook the Excel add-in reads. This page will refuse any "
      + "other file rather than check the wrong one.");
}

$("workbook-choose").addEventListener("click", () => pick());
$("workbook-recheck").addEventListener("click", () => {
  if (state.fileId) show(state.fileId);
});

start();
