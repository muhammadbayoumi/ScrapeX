// ScrapeX control panel — the single always-available UI (Chrome side panel).
//
// The panel is a REMOTE CONTROL: it queues jobs and polls. The engine (local
// Python) owns execution, so closing this panel never stops a run and reopening
// reconnects to whatever is already in flight.
//
// Scraped and user-entered values are UNTRUSTED: everything interpolated into
// markup goes through esc(), and content spans use unicode-bidi:plaintext so
// Arabic renders right-to-left without disturbing the English chrome around it.
import { checkEngine, getBackend, setBackend } from "./engine.js";
import { autostartStatus, checkStartup, setAutostart, startEngine, upgradeDatabase } from "./transport.js";
import { capabilityProblem, deployedFrom, installedVersion, CAPABILITY_REPORTING_SINCE, isOlder } from "./version.js";
import { PROTOCOL_VERSION } from "./transport.js";
import { latestEngineRelease } from "./releases.js";
import { getToken, accountFor, authorize, forgetToken, revokeToken } from "./identity.js";
import {
  clearCurrentAccount, forgetAccount, readAccounts, rememberAccount,
} from "./accounts.js";
import {
  backUp, fetchLatest, fetchPanelPack,
  FOLDER_NAME, KEEP, folderId, listing, readLatest,
} from "./drive.js";
import { readPanelPack, datasetSummaries } from "./bundleview.js";
import {
  ensureFolder, ensureSpreadsheet, openChosen, writeTab,
  DEFAULT_WORKBOOK, SHEET_FOLDER,
} from "./sheets.js";
import {
  afterIdle, afterNextPaint, deadlineForLocalRequest, fetchWithDeadline,
  isTimeoutError, markStartup,
} from "./startup.js";

const $ = (id) => document.getElementById(id);
// Called by renderSchemaLag since c4ea06b and DEFINED NOWHERE until now, so the
// banner that tells the owner his database is behind the engine threw
// ReferenceError instead of rendering -- and only ever in the one situation it
// exists for. Nothing caught it: the early return above it means the normal
// case never reaches these lines, and no test supplied a pending migration.
const el = (tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
};
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ICON_SPRITE = "icons/material-icons.svg";
const icon = (name, className = "") =>
  `<svg class="sx-icon ${className}" aria-hidden="true">` +
  `<use href="${ICON_SPRITE}#${name}"></use></svg>`;

const nativeFetch = window.fetch.bind(window);
const panelController = new AbortController();
let backendController = new AbortController();
let activeBackend = "";
let backendGeneration = 0;
let accountGeneration = 0;
let engineGeneration = 0;
let firstDestinationDataMarked = false;

function activateBackend(url) {
  const clean = String(url || "").replace(/\/+$/, "");
  if (clean === activeBackend) return clean;
  backendController.abort();
  backendController = new AbortController();
  activeBackend = clean;
  backendGeneration += 1;
  engineGeneration += 1;
  return clean;
}

async function backendBase() {
  if (activeBackend) return activeBackend;
  return activateBackend(await getBackend());
}

function localApiPath(input) {
  try {
    const url = new URL(String(input), window.location.href);
    if (!url.pathname.startsWith("/api/")) return null;
    if (activeBackend && !String(input).startsWith(activeBackend)) return null;
    return url.pathname + url.search;
  } catch (_) {
    return null;
  }
}

// The shared appearance/timezone modules use fetch directly. Install the same
// endpoint policy beneath them without changing the byte-identical Web UI
// copies of those modules. Calls that already declare a signal keep it.
window.fetch = (input, options = {}) => {
  const path = localApiPath(input);
  if (!path || options.signal) return nativeFetch(input, options);
  const deadline = deadlineForLocalRequest(path, options.method || "GET");
  return fetchWithDeadline(
    nativeFetch, input, options, deadline,
    [panelController.signal, backendController.signal],
  );
};

const DESTINATION_DATA_PATH =
  /^\/api\/(?:sources|outputs|jobs|resolve|records|changes|schedules|storage|settings|fields|rates)(?:[/?]|$)/;

async function api(path, options = {}) {
  const backend = await backendBase();
  const method = options.method || "GET";
  const deadlineMs = options.deadlineMs || deadlineForLocalRequest(path, method);
  const requestOptions = {...options};
  delete requestOptions.deadlineMs;
  if (!firstDestinationDataMarked && DESTINATION_DATA_PATH.test(path)) {
    firstDestinationDataMarked = true;
    markStartup("first-destination-data-request", {path});
  }
  const res = await fetchWithDeadline(
    window.fetch, backend + path, requestOptions, deadlineMs,
    [panelController.signal, backendController.signal],
  );
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw Object.assign(new Error(detail), {status: res.status, kind: "http"});
  }
  return res.json();
}
const post = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body || {}),
});
const del = (path) => api(path, { method: "DELETE" });

function out(id, html, cls) {
  $(id).innerHTML = html ? `<span class="${cls || ""}">${html}</span>` : "";
}
async function openTab(path) { chrome.tabs.create({ url: (await backendBase()) + path }); }
async function probeEngine() {
  return checkEngine({backend: await backendBase(), signal: backendController.signal});
}

// ---- state ----------------------------------------------------------------
const state = {
  sources: [], selected: new Set(), filter: "", sourceFilter: "",
  editingSourceKey: null,
  job: null, jobRef: null, logs: [], logSignature: null, logAtBottom: true,
  financeRates: [], financeSavedSettings: null, financeStatus: null,
  engineUp: false, engineState: "checking",
  // The two versions and what the engine says it deploys. `versionReport` is
  // null for an engine too old to publish one, which is NOT the same as an
  // engine that has not been asked yet — every reader of it checks
  // state.engineVersion too, so silence is never read as a refusal.
  // Chrome holds the token; this is the copy the panel lends onward, and
  // it is never written to storage.
  token: "", account: null, accountStatus: null,
  // The DIRECTORY, not a keyring: who this browser has seen, read from
  // chrome.storage.local by accounts.js. It holds names and addresses the panel
  // already paints and never a credential — the owner's ruling of 2026-08-11.
  accounts: [], currentAccountId: "",
  // Card state. `openAccountMenu` holds an id rather than a boolean so "exactly
  // one menu open" is a property of the state instead of a rule the handlers
  // have to remember to keep.
  accountsExpanded: true, openAccountMenu: null, pendingRemove: null,
  installedVersion: "", engineVersion: "", versionReport: null,
  versionStatus: "pending",
  // null means the engine never said, which is a THIRD state and not a
  // mismatch: an engine built before the handshake moved here answers
  // nothing, and refusing it as incompatible would be a guess.
  engineProtocol: null, protocolMismatch: false,
};

// ---- views ----------------------------------------------------------------
// (one comment line, used to prove the CI split picks the extension gate)
const VIEWS = [
  // profile and engines lead: the agreed shape opens on "who am I" and "what is
  // installed" before anything can be run. console is the owner build's page and
  // is removed from the published one — see docs/PLATFORM-PLAN.md Decision 20.
  "profile", "engines",
  "source", "run", "data", "sources", "source-edit", "appearance", "finance",
  "console", "settings",
  // A sub-view of Profile, like source-edit is of Sources: no rail button, and
  // showView maps it back to the Profile rail entry below. A name here with no
  // matching #view-<name> section takes down every navigation, so the two move
  // together.
  "manage-account",
];
const PANEL_DESTINATIONS = new Set(["data", "settings"]);
// The local fallback keeps every web page reachable even while the engine is
// stopped. When /api/ui responds, its canonical navigation replaces this copy.
const WORKSPACE_NAVIGATION_FALLBACK = [
  {key: "overview", label: "Overview", path: "/", icon: "dashboard", group: "Browse",
    description: "Sources and warehouse totals."},
  {key: "data", label: "Data", path: "/data", icon: "storage", group: "Browse",
    description: "Browse, search, and arrange saved records."},
  {key: "changes", label: "Changes", path: "/changes", icon: "trending-up", group: "Browse",
    description: "Recent price and availability changes."},
  {key: "history", label: "Crawl history", path: "/history", icon: "history", group: "Browse",
    description: "Past runs and their outcomes."},
  {key: "review", label: "Review queue", path: "/review", icon: "check", group: "Browse",
    description: "Resolve proposed record matches."},
  {key: "jobs", label: "Jobs", path: "/jobs", icon: "play-circle", group: "Automation",
    description: "Start and monitor collection jobs."},
  {key: "schedules", label: "Schedules", path: "/schedules", icon: "schedule", group: "Automation",
    description: "Review automatic collection times."},
  {key: "sync", label: "Google Sheets Synchronization", path: "/sync", icon: "sync", group: "Outputs",
    description: "Synchronize saved data with Google Sheets and Drive."},
  {key: "exports", label: "Exports", path: "/exports", icon: "file-download", group: "Outputs",
    description: "Create and configure Excel exports."},
  {key: "logs", label: "Logs", path: "/logs", icon: "description", group: "System",
    description: "Inspect detailed job activity."},
  {key: "data-model", label: "Data Model", path: "/data-model", icon: "account-tree",
    group: "System", description: "Tables, relationships, and how data moves."},
  {key: "schema", label: "Schema", path: "/schema", icon: "view-column", group: "System",
    description: "What every column means and who fills it."},
  {key: "settings", label: "Settings", path: "/settings", icon: "settings", group: "System",
    description: "Runtime, storage, and policy."},
];

function renderWorkspaceNavigation(navigation) {
  const destinations = (navigation || WORKSPACE_NAVIGATION_FALLBACK)
    .filter((destination) => !PANEL_DESTINATIONS.has(destination.key));
  const box = $("workspace-links");
  const groups = new Map();
  destinations.forEach((destination) => {
    const group = destination.group || "Workspace";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(destination);
  });
  box.innerHTML = [...groups.entries()].map(([group, items]) =>
    `<section class="workspace-menu-group" aria-labelledby="workspace-group-${
      esc(group.toLowerCase())}">
      <h3 id="workspace-group-${esc(group.toLowerCase())}">${esc(group)}</h3>
      ${items.map((destination) =>
        `<button type="button" class="workspace-destination" data-workspace-key="${
          esc(destination.key)}" data-workspace-path="${esc(destination.path)}">
          ${icon(destination.icon)}
          <span class="workspace-destination-copy">
            <strong>${esc(destination.label)}</strong>
            <small>${esc(destination.description || "Open in Workspace")}</small>
          </span>
          ${icon("open-in-new", "sm")}
        </button>`).join("")}
    </section>`).join("");
  box.querySelectorAll("[data-workspace-path]").forEach((button) =>
    button.addEventListener("click", () => {
      openTab(button.dataset.workspacePath);
      closeWorkspaceMenu(true);
    }));
}

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let workspaceFocusFrame = null;

function positionRailIndicator(button, immediate = false) {
  if (!button) return;
  const rail = document.querySelector("nav.side-rail");
  const indicator = $("rail-indicator");
  rail.querySelectorAll(".rail-item").forEach((item) => {
    item.classList.toggle("is-rail-active", item === button);
  });
  if (immediate) indicator.style.transition = "none";
  rail.style.setProperty("--rail-indicator-y", `${button.offsetTop}px`);
  rail.classList.add("rail-ready");
  if (immediate) requestAnimationFrame(() => { indicator.style.transition = ""; });
}

function openWorkspaceMenu() {
  if (workspaceFocusFrame !== null) cancelAnimationFrame(workspaceFocusFrame);
  $("workspace-menu").classList.add("is-open");
  $("workspace-backdrop").classList.add("is-open");
  $("workspace-menu").setAttribute("aria-hidden", "false");
  $("workspace-toggle").setAttribute("aria-expanded", "true");
  positionRailIndicator($("workspace-toggle"));
  workspaceFocusFrame = requestAnimationFrame(() => {
    workspaceFocusFrame = null;
    if ($("workspace-toggle").getAttribute("aria-expanded") === "true") {
      $("workspace-links").querySelector("button")?.focus();
    }
  });
}

function closeWorkspaceMenu(returnFocus = false) {
  if (workspaceFocusFrame !== null) {
    cancelAnimationFrame(workspaceFocusFrame);
    workspaceFocusFrame = null;
  }
  const wasOpen = $("workspace-toggle").getAttribute("aria-expanded") === "true";
  $("workspace-menu").classList.remove("is-open");
  $("workspace-backdrop").classList.remove("is-open");
  $("workspace-menu").setAttribute("aria-hidden", "true");
  $("workspace-toggle").setAttribute("aria-expanded", "false");
  if (wasOpen) {
    positionRailIndicator(document.querySelector(
      'nav.side-rail button[data-view][aria-current="page"]'));
  }
  if (returnFocus && wasOpen) $("workspace-toggle").focus();
}

// The rail's Profile button wears whoever is signed in. M1 owns the sign-in and
// will call this with the account's `picture`; everything below it is already
// real, so M1 adds a caller and not a feature.
//
// A photo that fails to load must not leave a blank hole where a button was —
// Google's avatar URLs expire, and the panel is often opened offline — so the
// fallback comes back on `error` rather than being trusted to have worked.
function setProfileAvatar(url) {
  const photo = $("profile-avatar");
  const fallback = $("profile-avatar-fallback");
  if (!photo || !fallback) return;
  const wear = (showPhoto) => {
    photo.classList.toggle("hidden", !showPhoto);
    fallback.classList.toggle("hidden", showPhoto);
  };
  if (!url) {
    photo.removeAttribute("src");
    wear(false);
    return;
  }
  photo.onerror = () => { photo.removeAttribute("src"); wear(false); };
  photo.onload = () => wear(true);
  photo.src = url;
}

function showView(name, animate = true) {
  const current = VIEWS.find((view) => !$(`view-${view}`).classList.contains("hidden"));
  // Which RAIL entry stays lit. A sub-view has no button of its own, and
  // without an entry here every rail button loses aria-current and tabIndex,
  // leaving the rail with no keyboard entry point at all.
  const SUB_VIEW_RAIL = {"source-edit": "sources", "manage-account": "profile"};
  const navigationName = SUB_VIEW_RAIL[name] || name;
  runModeSelectUi?.close();
  closeWorkspaceMenu();
  // BUG FIXED HERE, introduced with the accounts card and merged in PR 168.
  // (Written without the number sign: the colour-literal guard reads a hash
  // followed by three hex digits as a colour, and 168 qualifies.)
  // state.openAccountMenu survived navigation, and while it was set the
  // capture-phase Escape handler swallowed Escape on EVERY other view. Nothing
  // was visibly open, so the only symptom was Escape quietly doing nothing
  // somewhere else entirely.
  closeAccountMenu();
  for (const v of VIEWS) $(`view-${v}`).classList.toggle("hidden", v !== name);
  const activeButton = document.querySelector(
    `nav.side-rail button[data-view="${navigationName}"]`);
  document.querySelectorAll("nav.side-rail button[data-view]").forEach((b) => {
    const selected = b.dataset.view === navigationName;
    b.setAttribute("aria-selected", String(selected));
    b.tabIndex = selected ? 0 : -1;
    if (selected) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  positionRailIndicator(activeButton, !animate);
  if (animate && current !== name && !reduceMotion.matches) {
    $(`view-${name}`).animate(
      [
        {opacity: 0, transform: "translateY(8px)"},
        {opacity: 1, transform: "translateY(0)"},
      ],
      {duration: 180, easing: "cubic-bezier(.2,.8,.2,1)"},
    );
  }
  const main = document.querySelector("main");
  if (main.scrollTop) {
    main.scrollTo({top: 0, behavior: reduceMotion.matches ? "auto" : "smooth"});
  }
  if (name === "data") loadDatasets();
  if (name === "sources") loadSources();
  if (name === "finance") loadGoogleFinance();
  if (name === "settings") {
    ensureTimeZoneControl();
    loadSchedules();
    loadStorage();
    // THE OUTPUTS LIST LIVES ON THIS SCREEN AND WAS LOADED FROM THE OTHER ONE.
    // `loadOutputs` had exactly one caller — loadRunDestination — which returns
    // early unless the current view is "run" AND the engine is up. So the
    // destinations panel here showed its loading skeleton forever to anyone who
    // opened Settings without first visiting Run, and there was nothing on the
    // screen to say why. Found on 2026-08-11 while reading the panel to wire
    // Drive into it; guarded by test_every_screen_loads_what_it_shows.
    loadOutputs();
  }
  if (name === "run") {
    loadRunDestination();
    maybeRenderAutostart();
  }
  if (name === "source") loadCurrentPage();
  if (name === "engines") renderEngines();
  if (name === "manage-account") loadManageAccount();
}

function currentViewName() {
  return VIEWS.find((view) => !$(`view-${view}`).classList.contains("hidden")) || "";
}

// ---- runtime status --------------------------------------------------------
const COMPONENTS = [
  ["Core service", "dns", (e) => (e.running ? "Running" : "Stopped")],
  ["Python runtime", "settings", (e) => (e.running ? "Ready" : "Unknown")],
  ["HTTP fetcher", "link", (e) => (e.running ? "Ready" : "Unknown")],
  // The engine creates and owns both databases; the panel only reports them. A
  // reachable engine sitting on an unusable database read as healthy from here.
  ["Databases", "storage", (e) => {
    if (!e.running) return "Unknown";
    if (!e.databases) return "Ready";
    return e.databases.ok ? "Healthy" : `Needs attention — ${e.databases.detail}`;
  }],
  ["Browser automation", "language", () => "Optional"],
];

function renderRuntime(engine) {
  $("components").innerHTML = COMPONENTS.map(([label, componentIcon, fn]) => {
    const value = fn(engine);
    const tone = /Stopped|Unknown|Needs attention/i.test(value)
      ? "warning"
      : /Optional/i.test(value) ? "neutral" : "ready";
    return `<article class="engine-component" data-tone="${tone}">` +
      `<span class="engine-component-icon">${icon(componentIcon, "sm")}</span>` +
      `<span class="engine-component-copy"><strong>${esc(label)}</strong>` +
      `<small>${esc(value)}</small></span></article>`;
  }).join("");
}

function renderRuntimeCheckAction(engine) {
  const button = $("runtime-check-action");
  if (!button) return;
  const diagnostics = Boolean(engine.running);
  const label = diagnostics ? "Run diagnostics" : "Recheck status";
  button.dataset.action = diagnostics ? "diagnostics" : "recheck";
  button.setAttribute("aria-label", label);
  button.title = label;
  $("runtime-check-label").textContent = label;
  $("runtime-check-icon").setAttribute(
    "href", `${ICON_SPRITE}#${diagnostics ? "tune" : "sync"}`);
}

function issueCopy(error) {
  const kind = error && error.kind;
  if (kind === "startup_blocked" || kind === "database_needs_upgrade") {
    return {
      title: "Engine cannot start yet",
      body: error.message || "The engine found a database that needs attention before it can start.",
      action: error.action === "upgrade_database" ? "upgrade" : "",
    };
  }
  if (kind === "database_upgrade_failed") {
    return {
      title: "Database upgrade failed",
      body: error.message || "The database could not be upgraded.",
      action: "",
    };
  }
  if (kind === "startup_check_failed") {
    return {
      title: "Startup check failed",
      body: error.message || "ScrapeX could not inspect its local databases.",
      action: "",
    };
  }
  if (kind === "timeout") {
    return {
      title: "Local helper did not answer",
      body: state.engineUp
        ? "The engine is online, but Chrome could not reach the native messaging helper."
        : (error.message || "The helper did not answer in time. It may still be starting."),
      action: "",
    };
  }
  return {
    title: "Engine action failed",
    body: error && error.message ? error.message : "The engine did not complete the requested action.",
    action: "",
  };
}

function renderIssueInto(box, error) {
  if (!box) return;
  if (!error) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  const copy = issueCopy(error);
  box.innerHTML = `<div><strong>${esc(copy.title)}</strong>` +
    `<p>${esc(copy.body)}</p>` +
    (copy.action === "upgrade"
      ? `<button type="button" class="ghost compact runtime-alert-action" data-runtime-upgrade>Upgrade database</button>`
      : "") + `</div>`;
  box.classList.remove("hidden");
  const action = box.querySelector("[data-runtime-upgrade]");
  if (action) action.addEventListener("click", upgradeDatabaseFromPanel);
}

function setRuntimeIssue(error) {
  const runtimeError = $("runtime-error");
  const engineError = $("engine-error");
  if (runtimeError || engineError) {
    renderIssueInto(runtimeError, error);
    renderIssueInto(engineError, error);
    return;
  }
  if (error) {
    const note = $("runtime-note");
    if (note) note.textContent = issueCopy(error).body;
  }
}

function clearRuntimeIssue() {
  setRuntimeIssue(null);
}

function setEngineChecking() {
  state.engineState = "checking";
  state.versionStatus = "pending";
  $("dot").className = "dot";
  $("estat-text").textContent = "Checking…";
  $("engine-note").textContent = "Checking the local engine independently…";
  // The Engine page's status row is rendered FROM `state`, never written to by
  // hand, so "checking" reaches it — and aria-busy with it — by the one road
  // every other answer takes.
  renderEngineStatusUI();
}

function renderSchemaLag(lag) {
  // Absent is the normal case, so the banner is absent too: a badge that is
  // always on screen is a badge nobody reads. When it IS there it must say the
  // three things the owner needs — what is wrong, what breaks, what fixes it —
  // because the alternative he met was a raw SQLite error on a broken page.
  const box = $("schema-lag");
  if (!lag || !lag.pending || !lag.pending.length) {
    box.classList.add("hidden");
    box.textContent = "";
    return;
  }
  box.textContent = "";
  const title = el("div", "setup-title", "Database is behind the engine");
  const what = el("div", "muted steps mb-2", lag.message || "");
  const how = el("div", "muted text-xs");
  how.textContent = "Fix: " + (lag.fix || "python -m scrapex.cli init-db")
    + " — back up first, and apply it before restarting the engine.";
  const which = el("div", "muted text-xs tech", lag.pending.join(", "));
  box.append(title, what, which, how);
  box.classList.remove("hidden");
}

function setStatus(engine) {
  state.engineUp = engine.running;
  state.engineReachable = engine.reachable;
  state.engineState = engine.running
    ? "ready"
    : engine.timedOut ? "timeout"
    : engine.reachable ? "stopped" : "unavailable";
  state.engineVersion = engine.version || "";
  // engine.js has computed `protocolMismatch` from /api/health since the
  // handshake moved onto the transport that carries the traffic. It reached
  // exactly one place: the Diagnostics output, which only appears when someone
  // presses it. So the one fact that can refuse an impossible pair was
  // available, correct, and shown to nobody — and a run started regardless.
  //
  // The VERDICT stays in engine.js so there is one rule; the numbers are kept
  // here because a refusal has to print them.
  state.engineProtocol = typeof engine.engineProtocol === "number"
    ? engine.engineProtocol : null;
  state.protocolMismatch = Boolean(engine.protocolMismatch);
  $("dot").className = "dot " + (engine.running ? "on" : "off");
  // The word carries the state; the dot only reinforces it. "v0.2.0" here is
  // the ENGINE's — said in full in About, where the extension's own version now
  // sits beside it, because one number under no label was the original defect.
  $("estat-text").textContent = engine.running
    ? `Ready${engine.version ? " · engine v" + engine.version : ""}`
    : engine.timedOut ? "Check timed out"
    : engine.reachable ? "Stopped" : "Unavailable";
  $("engine-note").textContent = engine.running
    ? "The local engine is ready."
    : engine.timedOut
      ? "The engine did not answer before its deadline. Check again when it is ready."
      : engine.reachable
        ? "The engine answered but is not running. Start it from here."
        : "The local engine is unavailable. Start it or check again.";
  renderRuntimeCheckAction(engine);
  $("about-version").textContent = engine.version || "—";
  renderSchemaLag(engine.schema_lag);
  renderRuntime(engine);
  // The Engine destination may have been opened while this independent check
  // was still pending. Repaint its status card when the answer arrives so it
  // cannot remain stuck on "Checking engine…" after Profile has already settled.
  //
  // The STATUS half only. `renderEngines` also fetches the release feed, and
  // pulling a network request into every health answer is exactly what the
  // Engine page was separated from. `renderEngineStatusUI` reads `state` and
  // writes DOM, so it is safe on a hidden view and costs nothing.
  //
  // aria-busy is deliberately NOT touched here: the check owns it, and the
  // version report it is still waiting for is part of that check.
  renderEngineStatusUI();
}

// ---- versions ---------------------------------------------------------------
// TWO versions, updated by TWO mechanisms that nothing keeps in step: the engine
// arrives with the repository, the extension only when someone presses Reload in
// chrome://extensions. They drift apart every working day, and until now the
// panel showed one of them and never its own — so a feature the installed
// extension could not reach looked exactly like a feature that was never built.
// That is issue 32 §1.2/§1.3, and it is what cost two sessions.

async function loadVersions(engine, stillCurrent = () => true) {
  const installed = installedVersion();
  state.installedVersion = installed;
  $("about-extension-version").textContent = installed || "unknown";
  if (!engine.reachable) {
    // Nothing to compare against. The setup card already says the engine is
    // down; inventing a version verdict on top of it would be noise.
    state.versionReport = null;
    state.versionStatus = "unavailable";
    renderVersionNotice(engine);
    return;
  }
  const query = installed ? `?extension_version=${encodeURIComponent(installed)}` : "";
  try {
    // Local version compatibility must not hang the whole Engine card if the
    // engine is slow or stuck. The health check already answered; this is a
    // secondary report, and `api` gives it its own 2500 ms deadline from
    // `deadlineForLocalRequest` — the same bound the hand-rolled
    // AbortController here used to apply, now stated once for every local
    // request instead of once per call site, and raised as a TimeoutError the
    // status below can actually name.
    const report = await api(`/api/version${query}`);
    if (!stillCurrent()) return;
    state.versionReport = report;
    state.versionStatus = "ready";
  } catch (error) {
    if (!stillCurrent()) return;
    // A 404 here is not a broken feature: it is an engine built before version
    // reporting existed. A timeout or any other failure is also a fact, not a
    // broken build. Recorded as null and SAID as such below, never silently
    // treated as "everything is fine".
    state.versionReport = null;
    state.versionStatus = error && error.status === 404
      ? "unsupported"
      : isTimeoutError(error) ? "timeout" : "unavailable";
  }
  renderVersionNotice(engine);
}

function renderVersionNotice(engine) {
  const report = state.versionReport;
  const installed = state.installedVersion;
  const notice = $("version-notice");
  $("about-latest-version").textContent = report ? report.latest_extension_version : "—";
  $("about-minimum-version").textContent = report ? report.minimum_extension_version : "—";
  $("about-latest-source").textContent = report
    ? `"Newest available" means ${report.latest_source}.` : "";
  // The feature-to-version ledger, in the panel (§1.5). It is the answer to the
  // question that started this: "has this shipped, and from which version?"
  $("about-capabilities").innerHTML = report
    ? `<div class="mt-2"><strong>What this engine deploys</strong></div>` +
      report.capabilities.map((c) =>
        `<div class="kv"><span>${esc(c.summary)}</span>` +
        `<span class="tech">${esc(c.since)}${c.commit ? " · " + esc(c.commit) : ""}</span></div>`
      ).join("")
    : "";

  if (!report && ["timeout", "unavailable"].includes(state.versionStatus)
      && engine.reachable) {
    notice.innerHTML = state.versionStatus === "timeout"
      ? `<div class="setup-title">The engine version check timed out</div>` +
        `<div class="muted text-sm">The engine health check succeeded, but its ` +
        `version endpoint did not answer before its own deadline. Recheck status to try again.</div>`
      : `<div class="setup-title">The engine version could not be checked</div>` +
        `<div class="muted text-sm">The engine is reachable, but its version endpoint ` +
        `is unavailable. Recheck status to try again.</div>`;
    notice.classList.remove("hidden");
    return;
  }

  if (report && report.outdated) {
    // The five facts §1.4 asks for, none of them optional: what is installed,
    // what is available, what is required, what is missing because of the gap,
    // and what to press to fix it.
    notice.innerHTML =
      `<div class="setup-title">This ScrapeX extension is older than the engine it is talking to</div>` +
      `<div class="kv"><span>Installed extension</span><span class="tech">${esc(installed || "unknown")}</span></div>` +
      `<div class="kv"><span>Latest available extension</span><span class="tech">${esc(report.latest_extension_version)}</span></div>` +
      `<div class="kv"><span>Minimum extension required</span><span class="tech">${esc(report.minimum_extension_version)}</span></div>` +
      `<div class="kv"><span>Engine</span><span class="tech">${esc(engine.version || "unknown")}</span></div>` +
      (report.missing.length
        ? `<div class="muted text-sm mt-2">Not available in this extension:</div><ul class="muted text-sm">` +
          report.missing.map((m) =>
            `<li>${esc(m.summary)} <span class="tech">(needs ${esc(m.since)})</span></li>`).join("") +
          `</ul>`
        : `<div class="muted text-sm mt-2">No capability is missing yet — the extension is simply behind.</div>`) +
      `<div class="muted text-sm mt-2">${esc(report.update_instructions)}</div>`;
    notice.classList.remove("hidden");
    return;
  }
  if (!report && engine.reachable && engine.version) {
    // The engine is silent about its features. That is ONE fact, and it has
    // three different causes, so it cannot have one sentence.
    //
    // The first version of this printed "the engine is older than this
    // extension" without ever comparing the two numbers, and prescribed
    // "update the engine to <the extension's own version>". With both sides at
    // 0.1.0 the owner got a card that contradicted itself twice: a claim of
    // "older" that the two numbers printed directly beneath it denied, and an
    // instruction to update to the version already installed. A remedy you
    // have already carried out is not a remedy.
    const engineIsOlder = installed && isOlder(engine.version, installed);
    const bothPredateReporting = isOlder(engine.version, CAPABILITY_REPORTING_SINCE);
    let title;
    let remedy;
    if (engineIsOlder) {
      title = "The ScrapeX engine is older than this extension";
      // Lead with the action, and name where it is. The engine runs on this
      // machine from the same checkout and reports the version of the code
      // RUNNING, not the code on disk — so after a pull it is behind until the
      // process restarts, which is the ordinary case. The reader cannot see
      // which version is on disk, so do not make the instruction depend on it:
      // restart first, because it is free and fixes the common case, and let
      // the number afterwards decide whether anything else is needed.
      remedy = `Press "Restart engine" on the ScrapeX Settings page. If it ` +
        `still reports ${esc(engine.version)} afterwards, its files really are ` +
        `older and need updating to ${esc(installed)}.`;
    } else if (bothPredateReporting) {
      // Same number, or a newer engine, and below the line where reporting
      // began. Nothing is "behind" anything; both sides are simply early.
      title = "This ScrapeX engine cannot say what it deploys";
      // Both sides are early, so both have to move — and each moves a different
      // way, so both ways are named.
      remedy = `Version reporting starts at ${esc(CAPABILITY_REPORTING_SINCE)}, ` +
        `and both sides are below it. Update the files, then press "Restart ` +
        `engine" on the ScrapeX Settings page and reload this extension from ` +
        `chrome://extensions.`;
    } else {
      // It claims a version that DOES report, and reported nothing: the files
      // on disk moved and the process did not. Restarting is the whole fix,
      // and sending the owner to download something would waste their time.
      title = "This ScrapeX engine is not reporting what it deploys";
      remedy = `Version ${esc(engine.version)} publishes a capability report and ` +
        `this one did not, so the running engine is older than its own files. ` +
        `Press "Restart engine" on the ScrapeX Settings page — there is nothing ` +
        `to download.`;
    }
    notice.innerHTML =
      `<div class="setup-title">${title}</div>` +
      `<div class="kv"><span>Installed extension</span><span class="tech">${esc(installed || "unknown")}</span></div>` +
      `<div class="kv"><span>Engine</span><span class="tech">${esc(engine.version)}</span></div>` +
      `<div class="muted text-sm mt-2">Nothing here can promise a feature will ` +
      `work until it does. ${remedy}</div>`;
    notice.classList.remove("hidden");
    return;
  }
  notice.innerHTML = "";
  notice.classList.add("hidden");
}

// Engine-only state refresh. Used by the Engine page recheck action so it does
// not pull in sources, outputs, jobs, or other destination data — and by
// render(), so the two can never run different checks or guard them differently.
//
// The generation guard is not decoration. The Engine check settles independently
// of the account and of whatever the owner does next: pressing Check again, or
// saving a new backend address, starts a second check while the first is still
// out, and without this the older answer overwrites the newer one whenever it
// happens to come back last. `{cancelled: true}` means SOMETHING ELSE IS NOW
// AUTHORITATIVE — every caller returns rather than painting.
async function updateEngineState() {
  const backend = await backendBase();
  const request = ++engineGeneration;
  const backendAtStart = backendGeneration;
  const current = () => request === engineGeneration
    && backendAtStart === backendGeneration
    && !panelController.signal.aborted;
  setEngineChecking();
  markStartup("engine-check-start", {backend});
  const engine = await checkEngine({backend, signal: backendController.signal});
  if (!current() || engine.cancelled) return {cancelled: true};
  setStatus(engine);
  await loadVersions(engine, current);
  if (!current()) return {cancelled: true};
  markStartup("engine-check-finish", {
    state: state.engineState, reachable: Boolean(engine.reachable),
  });
  return engine;
}

// The gate (§1.6). Called BEFORE a capability is used, never after the request
// has already come back wearing someone else's error message.
function capabilityRefusal(key) {
  if (!state.installedVersion) {
    // Chrome did not say what is loaded, and neither guess is safe: claiming
    // support we cannot prove is the silent failure this gate exists to remove,
    // and claiming a gap that may not exist sends the owner to reload for
    // nothing. Passing "unknown" down as if it were a version would throw
    // inside the comparison and lose the click entirely.
    return `«${key}» cannot be checked: this extension cannot read its own ` +
      `version from Chrome, so nothing here can promise the engine ` +
      `(${state.engineVersion || "unknown"}) supports it. Close and reopen ` +
      `the side panel, and reload ScrapeX in chrome://extensions if it persists.`;
  }
  return capabilityProblem(key, {
    extensionVersion: state.installedVersion,
    engineVersion: state.engineVersion || "unknown",
    deployed: deployedFrom(state.versionReport),
    updateInstructions: state.versionReport
      ? state.versionReport.update_instructions : "",
  });
}

// ---- crawl pace and engine control -----------------------------------------
// These settings were built, plumbed all the way to the fetcher, and rendered
// ONLY on the engine's own web page — which is display-only. So from the side
// panel, where the work actually happens, they did not exist: the owner asked
// for a feature that had been shipped weeks earlier. Settings belong here.

// FOUND BY THE LINTER: nothing reads this. loadCrawlSettings/saveCrawlSettings
// name their keys inline instead, so this list can drift from the real ones and
// nothing would say so. Left in place rather than deleted because "which keys
// are the crawl settings" is worth having in one place -- WIRING it is the fix,
// and that is a change to behaviour, not a lint tidy.
// eslint-disable-next-line no-unused-vars
const CRAWL_KEYS = ["crawl_honour_delay", "crawl_min_interval_s",
                    "crawl_parallel_sources", "crawl_timeout_s",
                    "crawl_user_agent"];

// The engine's own ceiling (jobs.py MAX_PARALLEL_SOURCES). Past a handful the
// wall-clock stops improving while the open handles and the contended write
// lock keep growing, so the field refuses what the engine would clamp anyway
// rather than accepting a number and silently ignoring it.
const MAX_PARALLEL_SOURCES = 8;

function crawlPaceEffect() {
  // What the choice MEANS, in the units the owner thinks in. A checkbox that
  // silently decides whether a crawl takes one hour or eleven should say so.
  const honour = $("crawl_honour_delay").checked;
  const every = parseFloat($("crawl_min_interval_s").value) || 0;
  $("crawl-pace-effect").textContent = honour
    ? "Each site's own delay wins when it asks for more than " + every + "s."
    : "Our pace only: " + every + "s between requests, whatever a site asks for.";
}

function crawlParallelEffect() {
  // What the number MEANS, in the terms the owner asked in. elburoj starved
  // nine other sources for days because one slow site held the whole run; the
  // field that fixes that should say so, and should say the part people get
  // wrong — this is sites at once, never two pages of one site at once.
  const at = parseInt($("crawl_parallel_sources").value, 10) || 1;
  $("crawl-parallel-effect").textContent = at <= 1
    ? "One site at a time: a slow site holds up every source behind it."
    : at + " different sites at once. Two sources on the SAME site still take "
      + "turns, so no site is asked for more than it was before.";
}

async function loadCrawlSettings() {
  let settings;
  try { settings = (await api("/api/settings")).settings || {}; }
  catch (err) { out("crawl-msg", "could not read settings: " + err.message, "err"); return; }
  const value = (key) => {
    const raw = settings[key];
    return raw && typeof raw === "object" ? raw.value : raw;
  };
  $("crawl_honour_delay").checked = !["0", "false", false].includes(value("crawl_honour_delay"));
  $("crawl_min_interval_s").value = value("crawl_min_interval_s") || "1.0";
  $("crawl_parallel_sources").value = value("crawl_parallel_sources") || "1";
  $("crawl_timeout_s").value = value("crawl_timeout_s") || "30";
  $("crawl_user_agent").value = value("crawl_user_agent") || "";
  $("log_retention_days").value = value("log_retention_days") || "30";
  crawlPaceEffect();
  crawlParallelEffect();
}

async function saveCrawlSettings() {
  const interval = parseFloat($("crawl_min_interval_s").value);
  if (!(interval > 0)) {
    // Refused HERE, not at the server: zero seconds between requests is not a
    // pace, it is a flood, and the site that gets it blocks us for good.
    out("crawl-msg", "seconds between requests must be greater than zero", "err");
    return;
  }
  // §1.6, on the one case that is already in the wild. An engine that does not
  // know `crawl_parallel_sources` answers this POST with 400 "unknown setting
  // 'crawl_parallel_sources'" — a sentence about a typo, for what is a version
  // gap — and the panel printed it as "not saved: unknown setting". Every other
  // field in the same request would have saved. Ask the version question first,
  // and answer it naming both versions.
  const refusal = capabilityRefusal("crawl_parallel_sources");
  if (refusal) { out("crawl-msg", esc(refusal), "err"); return; }
  out("crawl-msg", "saving…");
  try {
    await post("/api/settings", {
      crawl_honour_delay: $("crawl_honour_delay").checked ? "1" : "0",
      crawl_min_interval_s: String(interval),
      crawl_parallel_sources: String(Math.min(
        Math.max(parseInt($("crawl_parallel_sources").value, 10) || 1, 1),
        MAX_PARALLEL_SOURCES)),
      crawl_timeout_s: String(parseInt($("crawl_timeout_s").value, 10) || 30),
      crawl_user_agent: $("crawl_user_agent").value.trim(),
      log_retention_days: String(parseInt($("log_retention_days").value, 10) || 30),
    });
  } catch (err) { out("crawl-msg", "not saved: " + err.message, "err"); return; }
  out("crawl-msg", "saved — it applies to the next crawl, not one already running", "ok");
  crawlPaceEffect();
  crawlParallelEffect();
}

async function restartEngineFromPanel() {
  out("crawl-msg", "restarting the engine…");
  // A DROPPED request is the success case: the restart tears down the very
  // connection carrying its own reply. A DELIVERED refusal is the opposite, and
  // the previous version could not tell them apart because it only read
  // err.message from a thrown api() call. So a hard 500 — "could not start the
  // helper ([Errno 13] Permission denied ...)" — was printed INSIDE the words
  // "restart requested", and the owner was told to watch a status dot that
  // would never change. Raw fetch, so the status and the body are both readable.
  let refused = null;
  try {
    const asked = await fetch((await backendBase()) + "/api/engine/restart",
                              {method: "POST"});
    if (asked.status === 404) refused = ENGINE_TOO_OLD;
    else if (!asked.ok) {
      let detail = `The engine refused (HTTP ${asked.status}).`;
      try { detail = (await asked.json()).detail || detail; } catch (_) {}
      refused = detail;
    }
  } catch (_) { /* the socket died: it is going down, which is the point */ }
  if (refused) { out("crawl-msg", esc(refused), "err"); return; }
  out("crawl-msg", "restart requested — the status dot turns green when it is back", "ok");
}

// ---- Google Finance rate control -----------------------------------------
function financeCurrencyName(currency) {
  if (currency === "USD") return "United States Dollar";
  try {
    return new Intl.DisplayNames(["en"], {type: "currency"}).of(currency) || currency;
  } catch (_) {
    return currency;
  }
}

function financeNumber(value) {
  return new Intl.NumberFormat("en-US", {
    maximumSignificantDigits: 8,
  }).format(value);
}

function financeUsdNumber(value) {
  let digits = 3;
  while (value !== 0 && Number(value.toFixed(digits)) === 0 && digits < 9) {
    digits += 2;
  }
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function financeDateTime(value, empty) {
  if (!value) return empty;
  const time = window.ScrapeXTime;
  return time && time.isInstant(value) ? time.format(value, "datetime") : String(value);
}

function financeRelativeCheck(value) {
  const checkedAt = Date.parse(value || "");
  if (!Number.isFinite(checkedAt)) return "Not checked yet";
  const elapsedSeconds = Math.max(0, Math.round((Date.now() - checkedAt) / 1000));
  if (elapsedSeconds < 60) return "Checked just now";
  const elapsedMinutes = Math.round(elapsedSeconds / 60);
  if (elapsedMinutes < 60) {
    return `Checked ${elapsedMinutes.toLocaleString()} minute${elapsedMinutes === 1 ? "" : "s"} ago`;
  }
  const elapsedHours = Math.round(elapsedMinutes / 60);
  if (elapsedHours < 24) {
    return `Checked ${elapsedHours.toLocaleString()} hour${elapsedHours === 1 ? "" : "s"} ago`;
  }
  return `Checked ${financeDateTime(value, String(value))}`;
}

function setFinanceRateState(title, detail, tone = "neutral") {
  const surface = $("finance-rate-state");
  surface.dataset.tone = tone;
  surface.setAttribute("aria-busy", String(tone === "loading"));
  $("finance-rate-state-title").textContent = title;
  $("finance-last-check").textContent = detail;
}

function financeRefreshIsOverdue(status) {
  if (!status.automatic) return false;
  if (typeof status.due === "boolean") return status.due;
  const checkedAt = Date.parse(status.last_checked || "");
  const refreshHours = Number(status.refresh_hours);
  if (!Number.isFinite(checkedAt) || !Number.isFinite(refreshHours) || refreshHours <= 0) {
    return false;
  }
  return Date.now() - checkedAt >= refreshHours * 60 * 60 * 1000;
}

let financeCurrencySelectUi = null;
// FOUND BY THE LINTER: assigned at setup and never read again, while its twin
// `financeCurrencySelectUi` is re-synced every time the rates change. It may be
// harmless -- the target list is not repopulated the way the source list is --
// or it may be the sync nobody wrote. Answering that means knowing what the
// target select is meant to show, which is the owner's call, not a linter's.
// eslint-disable-next-line no-unused-vars
let financeTargetSelectUi = null;

function setupFinanceConverterSelect({selectId, triggerId, listId, labelPrefix}) {
  const select = $(selectId);
  const trigger = $(triggerId);
  const label = trigger.querySelector("[data-finance-select-label]");
  const list = $(listId);
  const row = trigger.closest(".finance-converter-row");
  let typed = "";
  let typeTimer = null;

  const buttons = () => [...list.querySelectorAll(".finance-converter-option")];

  function close({restoreFocus = false} = {}) {
    list.classList.add("hidden");
    list.classList.remove("opens-up");
    row.classList.remove("is-open");
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus({preventScroll: true});
  }

  function focusOption(direction = 1) {
    const choices = buttons();
    if (!choices.length) return;
    const current = choices.indexOf(document.activeElement);
    const selected = choices.findIndex(
      (button) => button.getAttribute("aria-selected") === "true");
    const start = current >= 0 ? current : Math.max(selected, 0);
    choices[(start + direction + choices.length) % choices.length]
      .focus({preventScroll: true});
  }

  function typeAhead(event) {
    if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return false;
    const key = event.key.toLocaleLowerCase();
    const nextTyped = typed + key;
    const repeatedKey = nextTyped.length > 1 && [...nextTyped].every(
      (character) => character === key);
    const query = repeatedKey ? key : nextTyped;
    typed = repeatedKey ? key : nextTyped;
    window.clearTimeout(typeTimer);
    typeTimer = window.setTimeout(() => { typed = ""; }, 700);
    const choices = buttons();
    const matches = choices.filter((button) =>
      button.textContent.trim().toLocaleLowerCase().startsWith(query));
    let match = matches[0];
    if (repeatedKey && matches.length > 1) {
      const current = choices.indexOf(document.activeElement);
      match = [...choices.slice(current + 1), ...choices.slice(0, current + 1)]
        .find((button) => matches.includes(button));
    }
    if (!match) return false;
    match.focus({preventScroll: true});
    match.scrollIntoView({block: "nearest"});
    return true;
  }

  function open() {
    if (select.disabled || !select.options.length) return;
    const bounds = row.getBoundingClientRect();
    const below = window.innerHeight - bounds.bottom;
    list.classList.toggle("opens-up", below < 250 && bounds.top > below);
    list.classList.remove("hidden");
    row.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    requestAnimationFrame(() => {
      (buttons().find((button) => button.getAttribute("aria-selected") === "true") ||
        buttons()[0])?.focus({preventScroll: true});
    });
  }

  function choose(value) {
    if (![...select.options].some((option) => option.value === value)) return;
    select.value = value;
    select.dispatchEvent(new Event("change", {bubbles: true}));
    close({restoreFocus: true});
  }

  function sync() {
    const selected = select.selectedOptions[0];
    label.textContent = selected?.textContent || "Select a currency";
    trigger.disabled = select.disabled;
    trigger.setAttribute("aria-label", `${labelPrefix}: ${label.textContent}`);
    list.replaceChildren(...[...select.options].map((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "finance-converter-option";
      button.dataset.currency = option.value;
      button.tabIndex = -1;
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(option.selected));
      button.innerHTML = `<span>${esc(option.textContent)}</span>${icon("check", "sm")}`;
      button.addEventListener("click", () => choose(option.value));
      return button;
    }));
  }

  trigger.addEventListener("click", () => {
    if (list.classList.contains("hidden")) open();
    else close();
  });
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (list.classList.contains("hidden")) open();
      else focusOption(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (list.classList.contains("hidden")) open();
      else close();
    } else if (event.key === "Escape" && !list.classList.contains("hidden")) {
      // ESCAPE HAS TO BE HEARD HERE TOO, and the only other listener is on the
      // LIST. open() moves focus into the list inside a requestAnimationFrame,
      // so between the click that opens it and the frame that lands, focus is
      // still on this trigger and Escape reached NOTHING — the list stayed open
      // with no keyboard way out of it. The same holds afterwards for anyone
      // who shift-tabs back to the trigger.
      //
      // It surfaced as an intermittently red CI job and I first recorded it as
      // a race in the test, "not a defect in the panel". It is a defect in the
      // panel: waiting for the list properly did not make the test pass, it
      // made it fail for thirty seconds with the list resolved visible 63 times.
      event.preventDefault();
      close({restoreFocus: true});
    }
  });
  list.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close({restoreFocus: true});
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      focusOption(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const choices = buttons();
      (event.key === "Home" ? choices[0] : choices[choices.length - 1])
        ?.focus({preventScroll: true});
    } else if (typeAhead(event)) {
      event.preventDefault();
    }
  });
  document.addEventListener("click", (event) => {
    if (!row.contains(event.target)) close();
  });
  select.addEventListener("change", sync);
  sync();
  return {close, sync};
}

function updateFinanceConverter() {
  const select = $("finance-converter-currency");
  const quote = state.financeRates.find((rate) => rate.currency === select.value);
  const amount = Number($("finance-converter-amount").value);
  if (!quote || !Number.isFinite(amount) || amount < 0) {
    $("finance-converter-equation").textContent = "No stored rate available";
    $("finance-converter-usd").textContent = "— United States Dollar";
    $("finance-converter-as-of").textContent = "Update rates to use the converter";
    $("finance-converter-output").textContent = "—";
    return;
  }
  const formattedAmount = financeNumber(amount);
  const formattedUsd = financeUsdNumber(amount / quote.per_usd);
  $("finance-converter-equation").textContent =
    `${formattedAmount} ${financeCurrencyName(quote.currency)} equals`;
  $("finance-converter-usd").textContent =
    `${formattedUsd} ${financeCurrencyName("USD")}`;
  $("finance-converter-as-of").textContent =
    `${financeDateTime(quote.as_of, "Unknown market time")} · Google Finance`;
  $("finance-converter-output").textContent = formattedUsd;
}

function renderFinanceConverter(status) {
  const select = $("finance-converter-currency");
  const previous = select.value;
  state.financeRates = (status.latest_rates || [])
    .map((rate) => ({
      currency: String(rate.currency || "").toUpperCase(),
      per_usd: Number(rate.per_usd),
      as_of: String(rate.as_of || ""),
    }))
    .filter((rate) => /^[A-Z]{3}$/.test(rate.currency) &&
      Number.isFinite(rate.per_usd) && rate.per_usd > 0);
  select.innerHTML = state.financeRates.length
    ? state.financeRates.map((rate) =>
      `<option value="${esc(rate.currency)}">${esc(financeCurrencyName(rate.currency))}</option>`).join("")
    : `<option value="">No stored currencies</option>`;
  select.disabled = !state.financeRates.length;
  if (state.financeRates.some((rate) => rate.currency === previous)) select.value = previous;
  financeCurrencySelectUi?.sync();
  updateFinanceConverter();
}

function renderGoogleFinanceStatus(status) {
  state.financeStatus = status;
  const tracked = status.tracked_currencies || [];
  const count = tracked.length;
  const rows = Number(status.rows || 0);
  $("finance-coverage-summary").textContent = count
    ? `The local engine currently has rates for ${count.toLocaleString()} currencies.`
    : "No non-USD currencies are using stored rates yet.";
  $("finance-currency-count").textContent =
    `${count.toLocaleString()} ${count === 1 ? "currency" : "currencies"}`;
  $("finance-currencies").textContent = tracked.length ? tracked.join(" · ") : "None yet";
  $("finance-latest-market").textContent =
    financeDateTime(status.latest_market_at, "No rates yet");
  $("finance-rows").textContent =
    `${rows.toLocaleString()} ${rows === 1 ? "rate" : "rates"}`;
  if (!status.automatic) {
    setFinanceRateState("Rates update manually", financeRelativeCheck(status.last_checked), "neutral");
  } else if (financeRefreshIsOverdue(status)) {
    setFinanceRateState("Rate update overdue", financeRelativeCheck(status.last_checked), "error");
  } else if (!rows) {
    setFinanceRateState("No stored rates yet", financeRelativeCheck(status.last_checked), "neutral");
  } else {
    setFinanceRateState("Rates are up to date", financeRelativeCheck(status.last_checked), "positive");
  }
  renderFinanceConverter(status);
}

function financeSettingsFromControls() {
  return {
    automatic: $("google_finance_auto_refresh").checked,
    refreshHours: Number($("google_finance_refresh_hours").value),
  };
}

function renderFinanceSaveState() {
  const saved = state.financeSavedSettings;
  const current = financeSettingsFromControls();
  const dirty = Boolean(saved) && (
    current.automatic !== saved.automatic ||
    current.refreshHours !== saved.refreshHours
  );
  const stateBox = $("finance-saved-state");
  const button = $("finance-save");
  const label = button.querySelector("span");
  const savedHours = saved
    ? saved.refreshHours.toLocaleString("en-US", {maximumFractionDigits: 2})
    : "";
  stateBox.dataset.dirty = String(dirty);
  $("finance-saved-summary").textContent = saved
    ? (saved.automatic
      ? `Rates refresh automatically every ${savedHours} hours.`
      : "Automatic refresh is off. Use Update now when needed.")
    : "Not loaded";
  button.disabled = !dirty;
  button.dataset.saveState = dirty ? "dirty" : "saved";
  // `ghost` off IS primary: the base button rule is the filled style. A
  // `primary` class was toggled here for years and no stylesheet ever
  // defined it.
  button.classList.toggle("ghost", !dirty);
  label.textContent = dirty ? "Apply changes" : "Saved";
}

async function loadGoogleFinance() {
  try {
    const status = await api("/api/rates/google-finance");
    $("google_finance_auto_refresh").checked = Boolean(status.automatic);
    $("google_finance_refresh_hours").value = String(status.refresh_hours ?? 6);
    state.financeSavedSettings = {
      automatic: Boolean(status.automatic),
      refreshHours: Number(status.refresh_hours ?? 6),
    };
    renderGoogleFinanceStatus(status);
    renderFinanceSaveState();
    out("finance-msg", "");
  } catch (err) {
    out("finance-msg", "could not read Google Finance status: " + esc(err.message), "err");
  }
}

async function saveGoogleFinance() {
  const hours = Number($("google_finance_refresh_hours").value);
  if (!Number.isFinite(hours) || hours < 0.25 || hours > 168) {
    out("finance-msg", "hours must be between 0.25 and 168", "err");
    return;
  }
  out("finance-msg", "saving...");
  const saveButton = $("finance-save");
  saveButton.disabled = true;
  saveButton.querySelector("span").textContent = "Applying...";
  try {
    await post("/api/settings", {
      google_finance_auto_refresh: $("google_finance_auto_refresh").checked,
      google_finance_refresh_hours: hours,
    });
    await loadGoogleFinance();
  } catch (err) {
    out("finance-msg", "not saved: " + esc(err.message), "err");
    renderFinanceSaveState();
    return;
  }
  out("finance-msg", "saved - the new cadence applies immediately", "ok");
}

async function refreshGoogleFinance() {
  const button = $("finance-refresh");
  const label = button.querySelector("span");
  button.disabled = true;
  setFinanceRateState("Checking for newer rates", "Please wait", "loading");
  const oldLabel = label.textContent;
  label.textContent = "Updating...";
  out("finance-msg", "requesting the latest rates...");
  try {
    const result = await post("/api/rates/google-finance/refresh", {});
    renderGoogleFinanceStatus(result);
    const warning = (result.warnings || []).length
      ? ` ${result.warnings.length} warning(s): ${esc(result.warnings.join("; "))}` : "";
    out("finance-msg", esc(result.detail || "Update complete.") + warning,
        warning ? "" : "ok");
  } catch (err) {
    setFinanceRateState("Rates could not be updated", err.message, "error");
    out("finance-msg", "update failed: " + esc(err.message), "err");
  } finally {
    button.disabled = false;
    label.textContent = oldLabel;
  }
}

// ---- display time zone (spec 33) -------------------------------------------
//
// The panel owns the CONTROL; timezone.js owns the preference, the sharing and
// the one formatter. Everything here is the sentence around the select: what
// the current choice looks like on a real time, and whether it reached the
// engine — because a preference that silently failed to save would come back
// on the next crawl and look like the panel had forgotten it.

let timeZoneControlReady = false;

function ensureTimeZoneControl() {
  if (timeZoneControlReady) return true;
  const time = window.ScrapeXTime;
  const select = $("ui_time_zone");
  if (!time || !select) return false;

  const {zones: all, complete} = time.zones();
  const detected = time.detected();
  const auto = document.createElement("option");
  auto.value = "";
  auto.textContent = detected ? `Detected (${detected})` : "Detected";
  select.replaceChildren(auto);
  all.forEach((id) => {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = id;
    select.append(option);
  });
  select.dataset.timeZoneComplete = String(complete);
  select.value = time.get().zone;
  // Added only after the expensive option list exists. From this point the
  // shared module may keep the value synchronized without having built it at
  // DOMContentLoaded.
  select.setAttribute("data-time-zone-select", "");
  select.addEventListener("change", () => {
    time.set(select.value);
    timeZoneEffect();
    out("timezone-msg", "saving…");
    confirmTimeZoneShared();
  });
  timeZoneControlReady = true;
  timeZoneEffect();
  return true;
}

function timeZoneEffect() {
  const time = window.ScrapeXTime;
  // A LIVE example in the issue's own shape, on the moment he is reading it.
  // "Asia/Riyadh" tells him nothing he can check; "30 July 2026, 2:05 PM"
  // beside a clock he can see tells him everything.
  //
  // The caveat rides here and NOT in #timezone-msg, which belongs to the save:
  // this function runs on every zone change, so writing the status region would
  // wipe the "Saved" line it had just been given.
  const {zones, complete} = time.zones();
  const caveat = complete ? "" :
    " This browser publishes no full zone list, so only " + zones.length +
    " zones can be offered.";
  $("timezone-example").textContent =
    "Right now this reads " + time.label(new Date().toISOString()) + "." + caveat;
  return time.resolution();
}

/** Report whether a chosen zone actually reached the engine.
 *
 * The module pushes on its own and swallows the result, which is right for a
 * colour and wrong for this: if the engine refuses the identifier or is down,
 * the workspace keeps showing the old zone and only this line can say so. */
async function confirmTimeZoneShared() {
  const chosen = window.ScrapeXTime.get().zone;
  try {
    const remote = await api("/api/timezone");
    const shared = remote && remote.timezone ? remote.timezone.zone : "";
    if (shared === chosen) {
      out("timezone-msg", chosen
        ? "Saved — the workspace pages show " + esc(chosen) + " too."
        : "Saved — every surface follows the zone each browser detects.", "ok");
    } else {
      out("timezone-msg", "saved on this device; the engine still has " +
        esc(shared || "no zone") + ". It will catch up when the engine is reachable.");
    }
  } catch (err) {
    out("timezone-msg", "saved on this device — the engine is not reachable, " +
      "so the workspace pages will catch up later (" + esc(err.message) + ")");
  }
}

// ---- sites -----------------------------------------------------------------
function hostOf(url) { try { return new URL(url).host; } catch (_) { return url || ""; } }

function sourceDomain(url) {
  const host = hostOf(url).replace(/\.$/, "");
  return host.toLowerCase().startsWith("www.") ? host.slice(4) : host;
}

function sourceIdentity(source, compact = false, metricValue = null, metricLabel = "Row") {
  const key = source.source_key || "";
  // The unmarked name is English and is required; _ar is the site's own
  // Arabic name and may be absent. English leads, as it always did.
  const name = source.source_name || key.replaceAll("_", " ");
  const domain = sourceDomain(source.base_url);
  const arabic = source.source_name_ar && source.source_name_ar !== name
    ? `<span class="source-identity-name" dir="auto">${esc(source.source_name_ar)}</span>` : "";
  return `<span class="source-identity${compact ? " source-identity-compact" : ""}">
    <strong class="source-identity-domain" dir="${domain ? "ltr" : "auto"}">${esc(domain || name)}</strong>
    ${domain || arabic ? `<span class="source-identity-names"><span class="source-identity-name-en" dir="ltr">${esc(name)}</span>${
      arabic ? '<span class="source-identity-separator" aria-hidden="true">·</span>' : ""
    }${arabic}</span>` : ""}
    <span class="source-identity-footer">
      <code class="source-identity-key">${esc(key)}</code>
      ${metricValue == null ? "" : sourceMetric(metricValue, metricLabel)}
    </span>
  </span>`;
}

function sourceMetric(value, label) {
  return `<span class="source-identity-meta">
    <span class="source-identity-meta-bracket" aria-hidden="true">[</span>
    <small>${esc(label)}</small><span class="source-identity-meta-value">${esc(value)}</span>
    <span class="source-identity-meta-bracket" aria-hidden="true">]</span>
  </span>`;
}

function visibleSources() {
  const term = state.filter.trim().toLowerCase();
  return state.sources.filter((s) =>
    !term || (s.source_name || "").toLowerCase().includes(term) ||
    (s.source_name_ar || "").toLowerCase().includes(term) ||
    (s.source_key || "").toLowerCase().includes(term) ||
    (s.base_url || "").toLowerCase().includes(term));
}

// ---- kept pages: an interrupted crawl the owner can continue ---------------
//
// The engine has journaled every fetched page and resumed from it for a while,
// but nothing here ever SAID so — a source holding 871 pages looked exactly
// like one holding none, and the only button on offer was the one that throws
// them away. That is how elburoj reached nine runs and zero completions.

const keptPages = (source) => Number(source?.kept_pages || 0);

/** The interrupted run's own stopping point, in the display time zone.
 *
 * A date and not "3 hours ago": a journal can sit for days, and the question
 * this answers is WHICH run stopped here, not how long ago it was.
 *
 * It used to call toLocaleString() itself, which meant this line and the rest
 * of the product could disagree about what zone they were in. There is one
 * formatter now (timezone.js) and this returns its markup, so the value also
 * carries its raw UTC in a title and re-renders on a zone change for free. */
const fmtStopped = (iso) => window.ScrapeXTime.markup(iso, "short");

const pageCount = (n) => `${n.toLocaleString()} page${n === 1 ? "" : "s"}`;

/** Start a run that CONTINUES the journal instead of clearing it. */
async function resumeSource(key, button) {
  const source = state.sources.find((s) => s.source_key === key);
  if (!source) return;
  button.disabled = true;
  try {
    // The mode is chosen the same way the run-mode select chooses it for a
    // fresh run. The engine treats update and initial_crawl identically, but
    // the job history should still say which of the two this was.
    const r = await post("/api/jobs", {
      source_keys: [key], resume: true,
      run_mode: source.observations > 0 ? "update" : "initial_crawl",
    });
    state.jobRef = r.job_ref;
    await pollJob();
  } catch (e) {
    button.disabled = false;
    $("run-blocked").textContent = "Couldn't resume: " + e.message;
  }
}

function renderSites() {
  const box = $("sites");
  const shown = visibleSources();

  if (!state.sources.length) {
    box.innerHTML = `<div class="srow"><span class="muted">No sites yet. Open Source to register your first one.</span></div>`;
  } else if (!shown.length) {
    box.innerHTML = `<div class="srow"><span class="muted">No site matches “${esc(state.filter)}”.</span></div>`;
  } else {
    box.innerHTML = shown.map((s) => {
      const ready = s.implemented;
      const checked = state.selected.has(s.source_key) ? "checked" : "";
      const reason = ready ? "" :
        `<span class="chip off" title="No connector has shipped for this platform yet">Not supported yet</span>`;
      // The automation switch. Words carry the state, never colour alone; the
      // title says exactly what the switch gates — schedules, not your hand.
      const auto = ready ? `<button type="button" class="chip ${s.active ? "accent" : ""}"
            data-auto="${esc(s.source_key)}" aria-pressed="${s.active ? "true" : "false"}"
            title="Scheduled runs fire only while this is on. Running manually from this panel always works.">Auto: ${
              s.active ? "on" : "off"}</button>` : "";
      // What an interrupted crawl left behind, with its count and the moment
      // it stopped: "partly crawled" carrying no number is not something the
      // owner can decide anything from.
      //
      // It takes a full-width line UNDER the site rather than joining the chip
      // column beside it — "Resume 871 pages" is wide and never wraps, and in
      // a 360px panel it squeezed the domain down to "elburoj....", hiding
      // which site the offer was even about. Control first and the sentence
      // that explains it second, the same shape as the run button and its
      // hint: the list is a short scrollport, and the half of this block that
      // has to survive being scrolled past is the half he came here to press.
      const kept = keptPages(s);
      const stopped = kept ? fmtStopped(s.kept_at) : "";
      const keptBlock = kept ? `<span class="source-row-kept">
          <button type="button" class="chip accent" data-resume="${esc(s.source_key)}"
            title="Continue this crawl from the ${esc(pageCount(kept))} already kept. None of them is fetched again.">Resume ${
              esc(pageCount(kept))}</button>
          <span><strong>${esc(pageCount(kept))} kept</strong> from a run that
          stopped${stopped ? " " + stopped : ""}. Resume continues from
          there and re-fetches none of them; starting a run discards them.</span>
        </span>` : "";
      return `<div class="srow ${ready ? "" : "off"}">
        <label>
          <input type="checkbox" data-key="${esc(s.source_key)}" ${checked} ${ready ? "" : "disabled"}>
          ${sourceIdentity(s, true, Number(s.observations || 0).toLocaleString())}
        </label>
        <span class="source-row-actions">
          ${auto}${reason}
        </span>
        ${keptBlock}
      </div>`;
    }).join("");
    box.querySelectorAll("input[data-key]").forEach((cb) =>
      cb.addEventListener("change", () => {
        cb.checked ? state.selected.add(cb.dataset.key) : state.selected.delete(cb.dataset.key);
        renderSelected();
        refreshRunButton();
      }));
    box.querySelectorAll("button[data-resume]").forEach((button) =>
      button.addEventListener("click", () =>
        resumeSource(button.dataset.resume, button)));
    box.querySelectorAll("button[data-auto]").forEach((button) =>
      button.addEventListener("click", async () => {
        const key = button.dataset.auto;
        const source = state.sources.find((s) => s.source_key === key);
        if (!source) return;
        button.disabled = true;
        try {
          await post("/api/sources/" + encodeURIComponent(key) + "/active",
                     { active: !source.active });
          await loadSources();               // re-render from the server's truth
        } catch (e) {
          button.disabled = false;
          button.textContent = "Auto: failed";
          button.title = e.message;          // e.g. a placeholder that refuses activation
        }
      }));
  }
  renderSelected();
  refreshRunButton();
}

function renderSourceManager() {
  const box = $("source-manager-list");
  const term = state.sourceFilter.trim().toLowerCase();
  const shown = state.sources.filter((source) =>
    !term || (source.source_name || "").toLowerCase().includes(term) ||
    (source.source_name_ar || "").toLowerCase().includes(term) ||
    (source.source_key || "").toLowerCase().includes(term) ||
    sourceDomain(source.base_url).includes(term));

  $("source-manager-count").textContent = state.sources.length
    ? `${shown.length} of ${state.sources.length}`
    : "";

  if (!state.sources.length) {
    box.innerHTML = `<div class="source-manager-empty">
      No sources yet. Add your first source to start collecting data.
    </div>`;
    return;
  }
  if (!shown.length) {
    box.innerHTML = `<div class="source-manager-empty">
      No source matches “${esc(state.sourceFilter)}”.
    </div>`;
    return;
  }

  box.innerHTML = shown.map((source) => {
    const status = source.implemented ? "Ready" : "Connector unavailable";
    return `<article class="source-manager-card">
      <div class="source-manager-card-copy">
        ${sourceIdentity(
          source, false, Number(source.observations || 0).toLocaleString())}
        <span class="source-manager-card-meta muted text-xs">
          <span class="dot ${source.implemented ? "on" : "off"}" aria-hidden="true"></span>
          <span>${status}</span>
          <span aria-hidden="true">·</span>
          <span>Automation ${source.active ? "on" : "off"}</span>
        </span>
      </div>
      <button type="button" class="ghost source-manager-edit"
              data-edit-source="${esc(source.source_key)}"
              aria-label="Edit ${esc(sourceDomain(source.base_url) ||
                source.source_name || source.source_key)}">
        Edit
        ${icon("open-in-new", "sm")}
      </button>
    </article>`;
  }).join("");

  box.querySelectorAll("[data-edit-source]").forEach((button) =>
    button.addEventListener("click", () => openSourceEditor(button.dataset.editSource)));
}

// ---- which columns a source shows, from the panel ---------------------------
//
// Owner ruling, 2026-08-01: «انا عاوز extension غرفة التحكم فى كل شى — يعنى
// مينفعش يكون فى ميزة على الويب لا توجد فى extension».
//
// The same endpoint the web page's chooser uses — /api/fields/{source} — because
// two writers of one order is how the grid and the chooser came to disagree in
// the first place. The panel is the control room; it does not get its own path
// to the same fact.

async function loadSourceColumns(sourceKey) {
  const list = $("source-columns-list");
  const origin = $("source-columns-origin");
  if (!list) return;
  list.innerHTML = "";
  out("source-columns-result", "");
  try {
    const answer = await api("/api/fields/" + encodeURIComponent(sourceKey));
    const fields = answer.fields || [];
    // Whose order this is. The owner should never have to wonder whether an
    // update replaced an arrangement he made.
    origin.textContent = answer.order_source === "yours"
      ? "This is the order you arranged."
      : "This is the agreed order — identity, then the offer, then the filing.";
    if (!fields.length) {
      list.innerHTML = `<li class="muted text-xs">This source has no columns yet — it has not been crawled.</li>`;
      return;
    }
    fields.forEach((field, index) => {
      const item = document.createElement("li");
      item.className = "row source-column-row";
      const shown = !field.is_hidden;
      item.innerHTML =
        `<label class="row gap-1"><input type="checkbox" data-column-visible="${esc(field.field_key)}"` +
        `${shown ? " checked" : ""}> <span>${esc(field.display_name || field.original_name || field.field_key)}</span></label>` +
        `<span class="spacer"></span>` +
        `<button type="button" class="ghost compact" data-column-up="${esc(field.field_key)}"` +
        `${index === 0 ? " disabled" : ""} aria-label="Move up">↑</button>` +
        `<button type="button" class="ghost compact" data-column-down="${esc(field.field_key)}"` +
        `${index === fields.length - 1 ? " disabled" : ""} aria-label="Move down">↓</button>`;
      list.append(item);
    });
    state.sourceColumns = fields.map((field) => field.field_key);
  } catch (err) {
    list.innerHTML = "";
    out("source-columns-result", "could not read the columns: " + esc(err.message), "err");
  }
}

async function saveSourceColumns(sourceKey, body) {
  out("source-columns-result", "saving…");
  try {
    await post("/api/fields/" + encodeURIComponent(sourceKey), body);
  } catch (err) {
    out("source-columns-result", "not saved: " + esc(err.message), "err");
    return;
  }
  await loadSourceColumns(sourceKey);
  out("source-columns-result", "saved — the table and the export both follow this", "ok");
}

function wireSourceColumns() {
  const list = $("source-columns-list");
  if (!list) return;
  list.addEventListener("change", (event) => {
    const key = event.target.dataset && event.target.dataset.columnVisible;
    if (!key) return;
    saveSourceColumns(state.editingSourceKey,
                      {field_key: key, hidden: !event.target.checked});
  });
  list.addEventListener("click", (event) => {
    const button = event.target.closest("[data-column-up],[data-column-down]");
    if (!button) return;
    const key = button.dataset.columnUp || button.dataset.columnDown;
    const order = (state.sourceColumns || []).slice();
    const at = order.indexOf(key);
    const to = button.dataset.columnUp ? at - 1 : at + 1;
    if (at < 0 || to < 0 || to >= order.length) return;
    order[at] = order[to];
    order[to] = key;
    saveSourceColumns(state.editingSourceKey, {order});
  });
  const reset = $("source-columns-reset");
  if (reset) {
    reset.addEventListener("click", () =>
      saveSourceColumns(state.editingSourceKey, {reset: true}));
  }
}

function renderSourceEditor(source) {
  state.editingSourceKey = source.source_key;
  $("source-edit-identity").innerHTML = sourceIdentity(
    source, false, Number(source.observations || 0).toLocaleString());

  renderRobotsChoice(source);

  const ready = Boolean(source.implemented);
  $("source-edit-readiness").innerHTML =
    `<span class="dot ${ready ? "on" : "off"}" aria-hidden="true"></span>
     <span>${ready ? "Ready" : "Connector unavailable"}</span>`;
  $("source-edit-domain").textContent = sourceDomain(source.base_url) || "—";
  $("source-edit-family").textContent = source.family || "—";
  // Editable now, not read-only text: the owner asked to change a registered
  // source rather than delete and re-add it.
  $("source-edit-name").value = source.source_name || "";
  $("source-edit-name-ar").value = source.source_name_ar || "";
  $("source-edit-url").value = source.base_url || "";
  $("source-edit-key").value = source.source_key || "";
  $("source-edit-currency").value = source.currency || "";
  if ($("source-edit-cadence")) $("source-edit-cadence").value = source.cadence || "manual";
  if ($("source-edit-vat")) $("source-edit-vat").value = source.vat_mode || "incl";
  out("source-edit-rename-result", "");
  out("source-edit-danger-result", "");
  $("source-edit-holds").textContent = "…";
  loadSourceColumns(source.source_key);
  $("source-edit-wipe-scope").textContent = "";
  // What it HOLDS, fetched rather than guessed: a destructive button that says
  // how much it is about to erase is the difference between a choice and a
  // guess. Failure here must not block the editor, so it degrades to a dash.
  api("/api/sources/" + encodeURIComponent(source.source_key)).then((detail) => {
    if (state.editingSourceKey !== source.source_key) return;   // moved on
    const holds = detail.holds || {};
    const parts = [];
    if (holds.products) parts.push(`${holds.products.toLocaleString()} products`);
    if (holds.observations) parts.push(`${holds.observations.toLocaleString()} prices`);
    if (holds.details) parts.push(`${holds.details.toLocaleString()} details`);
    $("source-edit-holds").textContent = parts.length ? parts.join(" · ") : "nothing yet";
    $("source-edit-wipe-scope").textContent = parts.length
      ? `This would erase ${parts.join(", ")}.` : "";
  }).catch(() => { $("source-edit-holds").textContent = "—"; });

  $("source-edit-fold").checked = Boolean(source.fold_variants);
  const active = $("source-edit-active");
  active.checked = Boolean(source.active);
  active.disabled = !ready;
  $("source-edit-save").disabled = !ready;
  $("source-edit-active-help").textContent = ready
    ? "Manual runs remain available when automation is off."
    : "Automation cannot be enabled until this connector is available.";
  out("source-edit-result", "");
}

// robots.txt, per site. Kept together so the three steps read in the order the
// owner takes them: what the site says, what he chose, what that will do.
function renderRobotsChoice(source) {
  const choice = source.robots || "default";
  $("source-edit-robots").value = choice;
  const custom = source.robots_custom || {};
  $("source-edit-robots-enforce").checked = Boolean(custom.enforce_disallow);
  $("source-edit-robots-delay").value =
    custom.crawl_delay_s === null || custom.crawl_delay_s === undefined
      ? "" : String(custom.crawl_delay_s);
  $("source-edit-robots-custom").classList.toggle("hidden", choice !== "custom");
  // The consequence, in the same breath as the choice. A dropdown that does not
  // say what it will do is asking the owner to guess.
  const says = {
    default: "Whatever the Settings page says. Today that is: disallowed paths "
           + "are crawled and the run says so.",
    obey: "Disallowed paths are NOT fetched, and the site's own delay is used. "
        + "On a site that disallows this source's pages, that means it collects "
        + "nothing — check the site first.",
    custom: "This site only. Nothing else changes.",
  };
  $("source-edit-robots-consequence").textContent = says[choice] || "";
}

async function lookAtRobots() {
  const key = state.editingSourceKey;
  if (!key) return;
  const box = $("source-edit-robots-report");
  const button = $("source-edit-robots-look");
  button.disabled = true;
  box.textContent = "Reading " + key + "'s robots.txt…";
  try {
    const report = await api("/api/sources/" + encodeURIComponent(key) + "/robots");
    const lines = [report.summary];
    if (report.names_us) {
      lines.push("This site names " + report.names_us + " specifically.");
    }
    if (report.would_block_everything) {
      // THE ONE THAT CHANGES THE ANSWER, said plainly and not as a footnote.
      lines.push("Obeying would leave this source with nothing to collect.");
    }
    if (report.on_a_disallowed_path && report.on_a_disallowed_path.reason) {
      lines.push("On a disallowed path today: " + report.on_a_disallowed_path.reason);
    }
    box.textContent = lines.join(" ");
    box.classList.toggle("warn", Boolean(report.would_block_everything));
  } catch (error) {
    box.textContent = "Could not read it: " + (error && error.message ? error.message : error);
  } finally {
    button.disabled = false;
  }
}

function openSourceEditor(sourceKey) {
  const source = state.sources.find((item) => item.source_key === sourceKey);
  if (!source) return;
  renderSourceEditor(source);
  showView("source-edit");
  requestAnimationFrame(() => $("source-edit-back").focus({preventScroll: true}));
}

async function saveSourceEditor() {
  const source = state.sources.find(
    (item) => item.source_key === state.editingSourceKey);
  if (!source) {
    out("source-edit-result", "This source is no longer available.", "err");
    return;
  }

  const button = $("source-edit-save");
  const wanted = $("source-edit-active").checked;
  button.disabled = true;
  out("source-edit-result", "Saving…", "muted");
  try {
    // The manifest fields first, then the active flag. Order matters: the
    // active flip reloads the manifest, so saving fields afterwards would
    // write onto a copy the engine had already replaced.
    const edits = {
      source_name: $("source-edit-name").value.trim(),
      source_name_ar: $("source-edit-name-ar").value.trim(),
      base_url: $("source-edit-url").value.trim(),
      currency: $("source-edit-currency").value.trim(),
      cadence: $("source-edit-cadence").value,
      vat_mode: $("source-edit-vat").value,
      fold_variants: $("source-edit-fold").checked,
      robots: $("source-edit-robots").value,
    };
    // The custom rule rides along only when it is the chosen one. Sending it
    // otherwise would leave a rule stored behind a choice that ignores it,
    // which reads as "this site is customised" on every later open.
    if (edits.robots === "custom") {
      const delay = $("source-edit-robots-delay").value.trim();
      edits.robots_custom = {
        enforce_disallow: $("source-edit-robots-enforce").checked,
        crawl_delay_s: delay === "" ? null : Number(delay),
      };
    } else {
      edits.robots_custom = null;
    }
    const changed = Object.entries(edits).some(([field, value]) =>
      // robots_custom is an OBJECT. `String({}) !== String(null)` is true for
      // every pair of objects, so comparing it the same way as the text fields
      // would report a change on every save and POST for nothing.
      (value !== null && typeof value === "object") || field === "robots_custom"
        ? JSON.stringify(source[field] ?? null) !== JSON.stringify(value ?? null)
        : String(source[field] ?? "") !== String(value));
    if (changed) {
      await post("/api/sources/" + encodeURIComponent(source.source_key) + "/edit", edits);
      Object.assign(source, edits);
    }
    if (wanted !== Boolean(source.active)) {
      await post("/api/sources/" + encodeURIComponent(source.source_key) + "/active",
                 {active: wanted});
      source.active = wanted;
    }
    if (changed || wanted !== Boolean(source.active)) {
      renderSites();
      renderSourceManager();
    }
    renderSourceEditor(source);
    out("source-edit-result", `${icon("check", "sm")} Changes saved.`, "ok icon-label");
  } catch (error) {
    button.disabled = false;
    out("source-edit-result", `${icon("close", "sm")} ${esc(error.message)}`,
        "err icon-label");
  }
}

async function renameSourceKey() {
  const source = state.sources.find((i) => i.source_key === state.editingSourceKey);
  if (!source) return;
  const wanted = $("source-edit-key").value.trim();
  if (!wanted || wanted === source.source_key) {
    out("source-edit-rename-result", "That is already its key.", "muted");
    return;
  }
  // Confirmed by TYPING, not a click: this moves every stored row, and a
  // habitual OK is not a decision.
  const typed = window.prompt(
    `Rename ${source.source_key} to ${wanted}?

` +
    "Every product, price, saved layout, schedule and log entry moves with " +
    "the name, in one step.\n\nType the NEW key to confirm:");
  if (typed !== wanted) {
    out("source-edit-rename-result", "Not renamed.", "muted");
    return;
  }
  out("source-edit-rename-result", "Moving the data…", "muted");
  try {
    const result = await post(
      "/api/sources/" + encodeURIComponent(source.source_key) + "/rename",
      {source_key: wanted});
    const moved = Object.entries(result.moved || {})
      .map(([table, n]) => `${n} in ${table}`).join(", ");
    state.editingSourceKey = wanted;
    await loadSources();
    const renamed = state.sources.find((i) => i.source_key === wanted);
    if (renamed) renderSourceEditor(renamed);
    out("source-edit-rename-result",
        `${icon("check", "sm")} Renamed. ${moved ? "Moved " + moved + "." : "No stored rows to move."}`,
        "ok icon-label");
  } catch (error) {
    out("source-edit-rename-result", `${icon("close", "sm")} ${esc(error.message)}`,
        "err icon-label");
  }
}

async function stopTrackingSource() {
  const source = state.sources.find((i) => i.source_key === state.editingSourceKey);
  if (!source) return;
  if (!window.confirm(
      `Stop tracking ${source.source_key}?

` +
      "It comes off the crawl list. Everything it has already collected stays " +
      "— you can still read its prices and history.")) return;
  out("source-edit-danger-result", "Removing…", "muted");
  try {
    await del("/api/sources/" + encodeURIComponent(source.source_key));
    await loadSources();
    showView("sources");
  } catch (error) {
    out("source-edit-danger-result", `${icon("close", "sm")} ${esc(error.message)}`,
        "err icon-label");
  }
}

async function wipeSourceData() {
  const source = state.sources.find((i) => i.source_key === state.editingSourceKey);
  if (!source) return;
  // Typed, like the rename and for the same reason: this one cannot be
  // undone except from the backup it takes on the way.
  const typed = window.prompt(
    `Erase every row ${source.source_key} has collected?

` +
    "The source itself stays, so the next run starts clean. A backup is taken " +
    "first.\n\nType ERASE to confirm:");
  if (typed !== "ERASE") {
    out("source-edit-danger-result", "Nothing was erased.", "muted");
    return;
  }
  out("source-edit-danger-result", "Erasing (taking a backup first)…", "muted");
  try {
    const result = await post(
      "/api/sources/" + encodeURIComponent(source.source_key) + "/wipe", {confirm: true});
    await loadSources();
    const same = state.sources.find((i) => i.source_key === source.source_key);
    if (same) renderSourceEditor(same);
    out("source-edit-danger-result",
        `${icon("check", "sm")} ${esc(result.detail || "Erased.")} The source is still registered.`,
        "ok icon-label");
  } catch (error) {
    out("source-edit-danger-result", `${icon("close", "sm")} ${esc(error.message)}`,
        "err icon-label");
  }
}

async function loadSources() {
  try {
    const { sources } = await api("/api/sources");
    state.sources = sources;
    // Drop selections for sites that vanished from the manifest.
    for (const key of [...state.selected]) {
      if (!sources.some((s) => s.source_key === key)) state.selected.delete(key);
    }
    renderSites();
    renderSourceManager();
    loadChangeSummaries();
  } catch (_) {
    $("sites").innerHTML =
      `<div class="srow"><span class="err">Couldn&#39;t reach the engine.</span></div>`;
    $("source-manager-count").textContent = "";
    $("source-manager-list").innerHTML =
      `<div class="source-manager-empty err">Couldn&#39;t reach the engine.</div>`;
  }
}

const CHANGE_LABELS = {
  new: "new", price_increase: "price up", price_decrease: "price down",
  field_updated: "updated", unavailable: "unavailable", returned: "back", removed: "removed",
};

async function loadChangeSummaries() {
  // One request per source is what the engine offers, but they were awaited one
  // after another AND each answer re-rendered the entire source list — so ten
  // sources meant ten serial round-trips and ten full rebuilds of the DOM the
  // owner was already reading, with the rows shifting under the pointer as each
  // landed. The requests go out together and the list is drawn ONCE, when they
  // have all answered.
  const wanted = state.sources.filter((s) => s.observations);
  const summaries = await Promise.all(wanted.map(async (s) => {
    try {
      const { summary } = await api("/api/changes?limit=1&source_key=" +
        encodeURIComponent(s.source_key));
      return [s, Object.entries(summary || {}).filter(([, n]) => n > 0)
        .map(([k, n]) => `${n} ${CHANGE_LABELS[k] || k}`).join(" · ")];
    } catch (_) {
      return [s, ""];   // a missing summary is not worth surfacing
    }
  }));
  let changed = false;
  for (const [source, line] of summaries) {
    if (line && source.changes !== line) { source.changes = line; changed = true; }
  }
  if (changed) renderSites();
}

// ---- run -------------------------------------------------------------------
const MODES = {
  update: ["Update existing data", "Collect current data and record what changed.", null],
  initial_crawl: ["Initial crawl", "Collect and save these sites for the first time.", null],
  full_rebuild: ["Full rebuild", "Archive the current dataset, then crawl again.",
    "Full rebuild archives the current catalogue and takes a database backup first. Nothing is deleted, and the backup is your rollback."],
  history_backfill: ["History backfill",
    "Collect the history this source itself publishes (e.g. ten years of weekly prices), recorded as the source's own dated claims. Safe to repeat — known points are skipped.",
    null],
};

let runModeSelectUi = null;

function setupRunModeSelect() {
  const shell = document.querySelector('[data-select-control="run-mode"]');
  const select = $("run-mode");
  const trigger = $("run-mode-trigger");
  const list = $("run-mode-list");
  const label = trigger.querySelector("[data-select-label]");

  function buttons() {
    return [...list.querySelectorAll("[data-select-value]")];
  }

  function close({restoreFocus = false} = {}) {
    if (list.classList.contains("hidden")) return;
    list.classList.add("hidden");
    trigger.setAttribute("aria-expanded", "false");
    shell.classList.remove("is-open");
    if (restoreFocus) trigger.focus({preventScroll: true});
  }

  function focusOption(direction = 1) {
    const enabled = buttons().filter((button) => !button.disabled);
    if (!enabled.length) return;
    const current = enabled.indexOf(document.activeElement);
    const selected = enabled.findIndex((button) => button.getAttribute("aria-selected") === "true");
    const start = current >= 0 ? current : Math.max(selected, 0);
    enabled[(start + direction + enabled.length) % enabled.length]
      .focus({preventScroll: true});
  }

  function open() {
    list.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
    shell.classList.add("is-open");
    requestAnimationFrame(() => {
      const selected = list.querySelector('[aria-selected="true"]:not(:disabled)');
      (selected || buttons().find((button) => !button.disabled))
        ?.focus({preventScroll: true});
    });
  }

  function choose(value) {
    const option = [...select.options].find((candidate) => candidate.value === value);
    if (!option || option.disabled) return;
    select.value = value;
    select.dispatchEvent(new Event("change", {bubbles: true}));
    close({restoreFocus: true});
  }

  function sync() {
    const selected = select.selectedOptions[0];
    label.textContent = selected?.textContent || "";
    trigger.setAttribute("aria-label", `Run mode: ${label.textContent}`);
    list.replaceChildren(...[...select.options].map((option) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "sx-select-option";
      item.dataset.selectValue = option.value;
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(option.selected));
      item.disabled = option.disabled;
      item.innerHTML = `<span>${esc(option.textContent)}</span>
        <svg class="sx-icon sm" aria-hidden="true">
          <use href="icons/material-icons.svg#check"></use>
        </svg>`;
      item.addEventListener("click", () => choose(option.value));
      return item;
    }));
  }

  trigger.addEventListener("click", () => {
    if (list.classList.contains("hidden")) open();
    else close();
  });
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (list.classList.contains("hidden")) open();
      else focusOption(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Escape" && !list.classList.contains("hidden")) {
      // ESCAPE HAS TO BE HEARD HERE TOO, and the only other listener is on the
      // LIST. open() moves focus into the list inside a requestAnimationFrame,
      // so between the click that opens it and the frame that lands, focus is
      // still on this trigger and Escape reached NOTHING — the list stayed open
      // with no keyboard way out of it. The same holds afterwards for anyone
      // who shift-tabs back to the trigger.
      //
      // It surfaced as an intermittently red CI job and I first recorded it as
      // a race in the test, "not a defect in the panel". It is a defect in the
      // panel: waiting for the list properly did not make the test pass, it
      // made it fail for thirty seconds with the list resolved visible 63 times.
      event.preventDefault();
      close({restoreFocus: true});
    }
  });
  list.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close({restoreFocus: true});
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      focusOption(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const enabled = buttons().filter((button) => !button.disabled);
      const target = event.key === "Home" ? enabled[0] : enabled[enabled.length - 1];
      target?.focus({preventScroll: true});
    }
  });
  document.addEventListener("click", (event) => {
    if (!shell.contains(event.target)) close();
  });
  select.addEventListener("change", sync);
  sync();
  return {close, sync};
}

// The copy above ships BUILT-IN so the panel works with the engine down; when
// the engine answers, the shared UI contract (/api/ui — the same module the
// workspace sidebar renders from) overlays it, so the two surfaces can never
// hold two drifting wordings of the same mode.
async function adoptUiContract() {
  try {
    const manifest = await api("/api/ui");
    for (const mode of manifest.run_modes || []) {
      if (MODES[mode.key]) MODES[mode.key] = [mode.label, mode.detail, mode.warning || null];
    }
    renderWorkspaceNavigation(manifest.navigation);
    refreshMode();
  } catch (_) { /* engine down or older — the built-ins stand */ }
}

function renderModeTexts(availabilityNote) {
  const [label, help, warn] = MODES[$("run-mode").value];
  $("mode-help").textContent = help + (availabilityNote ? " " + availabilityNote : "");
  $("mode-warn").className = warn ? "card warn" : "hidden";
  $("mode-warn").innerHTML = warn ? `<span class="muted">${esc(warn)}</span>` : "";
  $("run").textContent = `Start ${label.toLowerCase()}`;
}

function refreshMode() {
  renderModeTexts("");
  refreshRunButton();
}

// Which modes the SELECTED sites' data can honestly support. "Update existing
// data" over a site with no data is not an update of anything, and a rebuild
// has nothing to archive; equally, "Initial crawl" over sites that all have
// data already happened. The option list states this instead of letting a
// meaningless choice be made and quietly reinterpreted.
function syncModeChoices() {
  const chosen = state.sources.filter((s) => state.selected.has(s.source_key));
  const withData = chosen.filter((s) => Number(s.observations) > 0).length;
  const without = chosen.length - withData;
  // Nothing selected: leave every mode open — the Run button is blocked anyway,
  // and greying the whole list would read as a fault rather than a state.
  // History backfill is a CAPABILITY, not a data state: only sources whose
  // connector knows where their site publishes history can run it, and a mixed
  // selection may not — running "history" on a shop that has none would be a
  // normal crawl wearing the wrong name.
  const allHistory = chosen.length > 0 && chosen.every((s) => s.supports_history);
  const allow = chosen.length === 0
    ? { update: true, initial_crawl: true, full_rebuild: true, history_backfill: true }
    : { update: withData > 0, initial_crawl: without > 0, full_rebuild: withData > 0,
        history_backfill: allHistory };
  const select = $("run-mode");
  for (const option of select.options) option.disabled = !allow[option.value];
  let note = "";
  if (chosen.length > 0 && withData === 0) {
    note = "The selected sites have no data yet, so this run is their first crawl.";
  } else if (chosen.length > 0 && without === 0) {
    note = "Every selected site already has data, so a first crawl is not on offer.";
  }
  if (chosen.length > 0 && !allHistory) {
    const capable = state.sources.filter((s) => s.supports_history)
      .map((s) => s.source_name);
    if (capable.length) {
      note += (note ? " " : "") + "History backfill is available only for: " +
        capable.join(", ") + ".";
    }
  }
  if (!allow[select.value]) {
    // The mode the owner had chosen stopped being meaningful for this
    // selection. Switching silently would run something they did not pick, so
    // the note above says what happened and why.
    select.value = withData > 0 ? "update" : "initial_crawl";
  }
  runModeSelectUi?.sync();
  renderModeTexts(note);
}

// ---- who is signed in -----------------------------------------------------
// The extension owns the token and lends it to the engine (the owner's ruling
// of 2026-08-05). Chrome holds it; nothing is stored here.
//
// The panel asks NON-INTERACTIVELY on open, so a returning owner is simply
// signed in and never sees the button again. Only the button itself is allowed
// to open a consent window — a panel that popped one on every open would be
// indistinguishable from a broken extension.

function setChecking(checking) {
  $("profile-stage").setAttribute("aria-busy", String(checking));
  $("welcome-checking").classList.toggle("hidden", !checking);
  if (checking) {
    $("welcome-signed-out").classList.add("hidden");
    $("welcome-signed-in").classList.add("hidden");
  } else {
    const signedIn = Boolean(state.token);
    $("welcome-signed-out").classList.toggle("hidden", signedIn);
    $("welcome-signed-in").classList.toggle("hidden", !signedIn);
  }
  updateRailLabel();
}

function updateRailLabel() {
  const tab = $("tab-profile");
  if (!tab) return;
  let suffix = "signed out";
  if (!$("welcome-checking").classList.contains("hidden")) {
    suffix = "checking account";
  } else if (state.token) {
    suffix = "signed in";
  }
  const label = `Profile, ${suffix}`;
  tab.setAttribute("aria-label", label);
  tab.title = label;
}

function focusAccountSummary() {
  const summary = $("welcome-summary");
  if (summary) summary.focus({ preventScroll: true });
}

function focusSignin() {
  const btn = $("signin");
  if (btn) btn.focus({ preventScroll: true });
}

function setGoogleButtonScheme() {
  const scheme = window.ScrapeXAppearance?.get?.().effectiveScheme || "light";
  // [data-scheme], not .profile-signin-img: the class is for styling, and a
  // JavaScript hook on a class means a CSS tidy can silently unwire the button.
  // The attribute is already what this function reads, so it is also what it
  // should select on.
  $("welcome-signed-out").querySelectorAll("img[data-scheme]").forEach((img) => {
    img.classList.toggle("hidden", img.dataset.scheme !== scheme);
  });
}

// ---- the remembered directory ---------------------------------------------
// Every call here is wrapped, and every failure is swallowed. The directory is
// what makes SWITCHING possible; signing in and using the panel does not depend
// on it. A storage fault must not turn a working account into a broken panel —
// so this layer is allowed to be absent, and nothing above it may assume it.

async function loadAccountDirectory() {
  try {
    const held = await readAccounts();
    state.accounts = held.accounts;
    state.currentAccountId = held.currentId;
  } catch (_) {
    state.accounts = [];
    state.currentAccountId = "";
  }
}

/** Keep the directory in step with whoever just proved who they are.
 *
 * Called on EVERY successful lookup, not only the first: a name or a photo that
 * changed at Google is the truth, and the row should be carrying it. An account
 * with no `sub` is not remembered — accounts.js refuses it, and a row nothing
 * can switch to is worse than no row.
 */
async function rememberSignedInAccount(account) {
  if (!account || !account.id) return;
  try {
    const held = await rememberAccount(account);
    state.accounts = held.accounts;
    state.currentAccountId = held.currentId;
  } catch (_) { /* the panel works without the directory */ }
}

/** Sign out: stop acting as the account, and KEEP it listed.
 *
 * The row becomes the design's signed-out row — the way back in without having
 * to type the address again. Removing it is a different button entirely, and
 * the only one that erases anything.
 */
async function endCurrentAccountSession() {
  try {
    const held = await clearCurrentAccount();
    state.accounts = held.accounts;
    state.currentAccountId = held.currentId;
  } catch (_) { /* the panel works without the directory */ }
}

async function loadAccount({ interactive = false } = {}) {
  const generation = ++accountGeneration;
  const current = () => generation === accountGeneration && !panelController.signal.aborted;
  markStartup("account-check-start", {interactive});
  setChecking(true);
  // Read before asking Chrome: the directory is what the switcher paints, and
  // it is known from storage alone — it must not wait on a network round trip.
  await loadAccountDirectory();
  try {
    const result = await getToken({interactive, signal: panelController.signal});
    if (!current()) return {state: "stale"};
    if (result.state !== "ok") {
      state.account = null;
      state.token = "";
      state.accountStatus = null;
      const visibleProblem = interactive || ["timeout", "failed"].includes(result.state)
        ? result : null;
      renderAccount({tokenProblem: visibleProblem});
      return result;
    }

    const accountResult = await accountFor(
      result.token, window.fetch, {signal: panelController.signal},
    );
    if (!current()) return {state: "stale"};
    if (accountResult.state === "ok") {
      state.token = result.token;
      state.account = accountResult.account;
      state.accountStatus = null;
      // THE DIRECTORY IS UPDATED BEFORE THE CARD IS DRAWN, and the order is the
      // whole fix. It used to render first and remember afterwards, so the card
      // read `state.currentAccountId` while it still held the empty string left
      // by the last sign-out — and the row for the account that had just signed
      // in failed the `id !== currentAccountId` filter, appearing in the list
      // BELOW the header, labelled "Signed out".
      //
      // Reported by the owner from the running panel on 2026-08-12: one
      // account, signed in at the top and signed out two inches under it.
      // Nothing re-rendered afterwards, so the contradiction simply stayed on
      // screen. The state was never wrong; it was read one step too early.
      await rememberSignedInAccount(accountResult.account);
      renderAccount({});
      return { ...result, account: accountResult.account };
    }

    if (accountResult.state === "unauthorized") {
      await forgetToken(result.token);
      if (!current()) return {state: "stale"};
      state.token = "";
      state.account = null;
      state.accountStatus = null;
      renderAccount({
        tokenProblem: {
          state: "authorization-required",
          detail: "Google access isn’t currently granted. Sign in with Google to try again.",
        },
      });
      return { state: "authorization-required" };
    }

    // Token is still valid, but the account lookup failed in a way we can
    // explain and possibly retry.
    state.token = result.token;
    state.account = null;
    state.accountStatus = accountResult;
    renderAccount({});
    return { ...result, accountStatus: accountResult };
  } catch (error) {
    if (!current()) return {state: "stale"};
    state.token = "";
    state.account = null;
    state.accountStatus = null;
    renderAccount({
      tokenProblem: {
        state: "failed",
        detail: "Something went wrong while checking the account.",
      },
    });
    return { state: "failed", detail: String(error && error.message) };
  } finally {
    if (current()) {
      setChecking(false);
      markStartup("account-check-finish", {
        signedIn: Boolean(state.token), interactive,
      });
    }
  }
}

async function loadAccountDetails() {
  const token = state.token;
  if (!token) return;
  const generation = ++accountGeneration;
  const current = () => generation === accountGeneration && !panelController.signal.aborted;
  const retry = $("retry-account");
  if (retry) retry.disabled = true;
  try {
    const result = await accountFor(token, window.fetch, {signal: panelController.signal});
    if (!current()) return;
    if (result.state === "ok") {
      state.account = result.account;
      state.accountStatus = null;
      renderAccount({});
      await rememberSignedInAccount(result.account);
      return;
    }
    if (result.state === "unauthorized") {
      await forgetToken(token);
      if (!current()) return;
      state.token = "";
      state.account = null;
      state.accountStatus = null;
      renderAccount({
        tokenProblem: {
          state: "authorization-required",
          detail: "Google access isn’t currently granted. Sign in with Google to try again.",
        },
      });
      focusSignin();
      return;
    }
    state.accountStatus = result;
    renderAccount({});
  } finally {
    if (retry && current()) retry.disabled = false;
  }
}

function renderAccount({ tokenProblem = null } = {}) {
  const signedIn = Boolean(state.token);
  $("welcome-signed-out").classList.toggle("hidden", signedIn);
  $("welcome-signed-in").classList.toggle("hidden", !signedIn);

  // A silent check that found nobody is not a problem to report: it is the
  // ordinary state of a machine nobody has signed in on yet.
  // The box appears only when it has something to say. An empty notice frame
  // reads as "something is wrong and we are not telling you".
  const note = $("signin-problem");
  note.textContent = tokenProblem ? tokenProblem.detail : "";
  note.classList.toggle("hidden", !tokenProblem);

  const status = $("account-detail-status");
  const retry = $("retry-account");
  const summary = $("welcome-summary");

  if (!signedIn) {
    setProfileAvatar(null);
    if (status) status.classList.add("hidden");
    if (retry) retry.classList.add("hidden");
    if (summary) summary.setAttribute("aria-label", "Signed in");
    // Nothing is open on a card nobody can see, and a menu left open would
    // reappear over whichever account signs in next.
    state.openAccountMenu = null;
    state.pendingRemove = null;
    renderAccountsCard();
    setAccountsStatus("");
    updateRailLabel();
    return;
  }

  const account = state.account;
  const accountStatus = state.accountStatus;

  // Signed in with no network: the token is real and the profile is not
  // readable. Saying "Signed in" is true; inventing a name would not be.
  const name = (account && account.name) || "";
  $("welcome-name").textContent = name || "Signed in";
  // "Hi," is only true once there is someone to greet. Without this the line
  // reads "Hi, Signed in" in the two states that have a token but no profile:
  // the moment before Google answers, and every case where the lookup failed.
  $("welcome-greeting").classList.toggle("hidden", !name);
  const email = (account && account.email) || "";
  $("welcome-email").textContent = email;
  $("welcome-email").classList.toggle("hidden", !email);

  const photo = $("welcome-photo");
  if (account && account.picture) {
    photo.onerror = () => photo.classList.add("hidden");
    photo.onload = () => photo.classList.remove("hidden");
    photo.src = account.picture;
  } else {
    photo.removeAttribute("src");
    photo.classList.add("hidden");
  }
  setProfileAvatar(account ? account.picture : "");

  if (accountStatus && accountStatus.retryable) {
    status.textContent = `${accountStatus.detail} Try again in a moment.`;
    status.classList.remove("hidden");
    retry.classList.remove("hidden");
    retry.onclick = () => { loadAccountDetails(); };
  } else if (accountStatus) {
    status.textContent = accountStatus.detail;
    status.classList.remove("hidden");
    retry.classList.add("hidden");
  } else {
    status.classList.add("hidden");
    retry.classList.add("hidden");
  }

  summary.setAttribute("aria-label", name ? `Signed in as ${name}` : "Signed in");
  renderAccountsCard();
  updateRailLabel();
}

// ---- the accounts card -----------------------------------------------------
//
// Every row here is DATA, so none of it lives in app.html: the card is rendered
// from the remembered directory. Names and addresses come from Google and are
// therefore untrusted, so every one of them is written with `textContent` and
// nothing on this path builds markup by string concatenation. The only innerHTML
// below carries `icon()`, whose argument is a literal in this file.
//
// WHAT "SIGNED OUT" MEANS ON A ROW. The directory deliberately stores no session
// state — a cached "signed in" is a fact that goes stale on disk and then lies.
// The only account this panel KNOWS it holds a token for is the current one;
// every other row is offered as signed out until a silent authorisation proves
// otherwise. That check needs the Web OAuth client, which this build does not
// have yet, so today every other row renders as signed out. That is the truth
// about this build rather than a placeholder.

function accountInitial(account) {
  const source = String(account.name || account.email || "").trim();
  return source ? source[0].toUpperCase() : "?";
}

function accountInitialFace(account, className) {
  const face = el("span", className, accountInitial(account));
  face.setAttribute("aria-hidden", "true");
  return face;
}

/** The face for a row: the photo when there is one, the initial when there is
 *  not — and the initial again the moment the photo fails, because Google's
 *  photo URLs expire and a broken image is worse than a letter. */
function accountFace(account, className) {
  if (!account.picture) return accountInitialFace(account, className);
  const img = document.createElement("img");
  img.className = className;
  img.alt = "";
  img.setAttribute("aria-hidden", "true");
  img.addEventListener("error", () => {
    img.replaceWith(accountInitialFace(account, className));
  }, { once: true });
  img.src = account.picture;
  return img;
}

function accountLabel(account) {
  return account.name || account.email || "Account";
}

/** One row. `signedIn` decides whether it can be switched to or must be
 *  re-authorised first. */
function accountRow(account, { signedIn }) {
  const row = el("div", `account-row${signedIn ? "" : " is-signed-out"}`);
  row.dataset.accountId = account.id;
  row.append(accountFace(account, "account-face"));

  const identity = el("div", "account-identity");
  const nameLine = el("div", "account-name-line");
  nameLine.append(el("span", "account-name", accountLabel(account)));
  if (!signedIn) nameLine.append(el("span", "account-badge", "Signed out"));
  identity.append(nameLine);
  const email = el("span", "account-email", account.email);
  email.setAttribute("dir", "ltr");
  identity.append(email);

  if (signedIn) {
    // The whole text column is the switch target, not a separate control: the
    // design has no "switch" button, and giving the row a click handler while
    // it looks like a button to nobody is how a control becomes undiscoverable.
    const target = el("button", "account-switch");
    target.type = "button";
    target.setAttribute("aria-label", `Use ${accountLabel(account)}`);
    target.append(identity);
    target.addEventListener("click", () => switchToAccount(account.id));
    row.append(target);
  } else {
    row.append(identity);
  }

  const menuButton = el("button", "icon-button compact account-menu-button");
  menuButton.type = "button";
  menuButton.setAttribute("aria-label", `Actions for ${accountLabel(account)}`);
  menuButton.setAttribute("aria-haspopup", "menu");
  menuButton.setAttribute("aria-expanded", String(state.openAccountMenu === account.id));
  menuButton.innerHTML = icon("more-vert");
  menuButton.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleAccountMenu(account.id);
  });
  row.append(menuButton);

  if (!signedIn) {
    const actions = el("div", "account-actions");
    const signIn = el("button", "compact account-action", "Sign in");
    signIn.type = "button";
    signIn.addEventListener("click", () => signInToAccount(account.id));
    const remove = el("button", "ghost compact account-action", "Remove");
    remove.type = "button";
    // No confirm: this row holds no session and erases nothing. A confirm step
    // in front of a harmless action teaches people to click through the ones
    // that are not.
    remove.addEventListener("click", () => removeAccount(account.id));
    actions.append(signIn, remove);
    row.append(actions);
  }

  // The menu is NOT appended here. It belongs to the card, because this row
  // lives inside a clipping scroller — see renderAccountsCard.
  return row;
}

/** The per-row menu, and the confirm step that lives inside it.
 *
 * NOT A DIALOG, and not by preference: tests/test_panel_dom.py forbids
 * `[role="dialog"]` anywhere inside #view-profile. The confirm therefore
 * replaces the menu's own contents, which also keeps the question next to the
 * row it is about instead of floating over the whole panel.
 */
function accountMenu(account, { signedIn }) {
  const menu = el("div", "account-menu");
  menu.setAttribute("role", "menu");
  menu.dataset.accountId = account.id;

  if (state.pendingRemove === account.id) {
    // Says what it does AND what it does not. In a local-first tool "remove
    // account" reads as deleting the Google account, and it does not: nothing
    // leaves Google and no collected data is touched.
    menu.append(el("p", "account-menu-question",
      `Remove ${accountLabel(account)} from ScrapeX? The Google account is not `
      + "touched and no collected data is erased — this browser just stops "
      + "listing it."));
    const confirm = el("button", "account-menu-item is-destructive", "Remove");
    confirm.type = "button";
    confirm.setAttribute("role", "menuitem");
    confirm.addEventListener("click", () => removeAccount(account.id));
    const cancel = el("button", "account-menu-item", "Keep it");
    cancel.type = "button";
    cancel.setAttribute("role", "menuitem");
    cancel.addEventListener("click", () => {
      state.pendingRemove = null;
      renderAccountsCard();
      focusAccountMenuButton(account.id);
    });
    menu.append(confirm, cancel);
    return menu;
  }

  if (signedIn) {
    const signOut = el("button", "account-menu-item", "Sign out");
    signOut.type = "button";
    signOut.setAttribute("role", "menuitem");
    signOut.addEventListener("click", () => signOutOfAccount(account.id));
    menu.append(signOut);
  }
  const remove = el("button", "account-menu-item is-destructive", "Remove from ScrapeX");
  remove.type = "button";
  remove.setAttribute("role", "menuitem");
  remove.addEventListener("click", () => {
    state.pendingRemove = account.id;
    renderAccountsCard();
    // Focus the confirm, so a keyboard user is standing on the answer to the
    // question that just appeared rather than back at the top of the menu.
    const confirm = $("accounts-card").querySelector(".account-menu .is-destructive");
    if (confirm) confirm.focus({ preventScroll: true });
  });
  menu.append(remove);
  return menu;
}

function accountsAction(label, symbol, { quiet = false, onClick }) {
  const button = el("button", "accounts-action");
  button.type = "button";
  button.innerHTML = icon(symbol, `lg accounts-action-icon${quiet ? " is-quiet" : ""}`);
  button.append(el("span", "", label));
  button.addEventListener("click", onClick);
  return button;
}

function accountsCollapsedPill(others) {
  const pill = el("button", "accounts-pill");
  pill.type = "button";
  pill.setAttribute("aria-expanded", "false");
  pill.setAttribute("aria-controls", "accounts-list");
  pill.append(el("span", "", "Show more accounts"));

  const faces = el("span", "accounts-pill-faces");
  faces.setAttribute("aria-hidden", "true");
  for (const account of others.slice(0, 3)) {
    faces.append(accountFace(account, "account-face-mini"));
  }
  pill.append(faces);

  const chevron = el("span", "accounts-pill-chevron icon-button xs");
  chevron.setAttribute("aria-hidden", "true");
  chevron.innerHTML = icon("expand-more");
  pill.append(chevron);
  pill.addEventListener("click", () => toggleAccountsList());
  return pill;
}

function renderAccountsCard() {
  const card = $("accounts-card");
  if (!card) return;

  // WHERE THE LIST WAS. Every state change rebuilds this card from scratch,
  // which throws the scroller back to the top — and the row whose menu was just
  // opened goes with it. Measured: the menu ended 205px below the visible list,
  // clipped and unreachable, for a row the person had scrolled to.
  const previous = card.querySelector(".accounts-list");
  const scrollTop = previous ? previous.scrollTop : 0;

  const signedIn = Boolean(state.token);
  card.textContent = "";
  card.classList.toggle("hidden", !signedIn);
  card.classList.remove("is-bare");
  if (!signedIn) return;

  const others = state.accounts.filter((account) => account.id !== state.currentAccountId);

  // Nobody else is listed yet, so there is nothing to disclose and nothing to
  // sign out of "as well". One row, and it is the one that changes that.
  if (!others.length) {
    card.append(accountsAction("Add another account", "add", { onClick: addAnotherAccount }));
    return;
  }

  if (!state.accountsExpanded) {
    card.classList.add("is-bare");
    card.append(accountsCollapsedPill(others));
    return;
  }

  const disclosure = el("button", "accounts-disclosure");
  disclosure.type = "button";
  disclosure.setAttribute("aria-expanded", "true");
  disclosure.setAttribute("aria-controls", "accounts-list");
  disclosure.append(el("span", "", "Hide more accounts"));
  disclosure.insertAdjacentHTML("beforeend", icon("expand-more", "accounts-chevron"));
  disclosure.addEventListener("click", () => toggleAccountsList());
  card.append(disclosure);

  const list = el("div", "accounts-list");
  list.id = "accounts-list";
  for (const account of others) {
    // See the note at the top of this section: without the Web OAuth client
    // nothing can be authorised silently, so no other row can be shown as
    // signed in without saying something this build cannot know.
    list.append(accountRow(account, { signedIn: false }));
  }
  card.append(list);

  card.append(accountsAction("Add another account", "add", { onClick: addAnotherAccount }));
  card.append(accountsAction("Sign out of all accounts", "logout",
                             { quiet: true, onClick: signOutOfAllAccounts }));

  // Put the scroller back before deciding where the menu goes: where it can fit
  // depends on where its row currently sits, and that is not settled until now.
  list.scrollTop = scrollTop;

  const open = others.find((account) => account.id === state.openAccountMenu);
  if (open) {
    card.append(accountMenu(open, { signedIn: false }));
    placeOpenAccountMenu();
  }

  // The menu FOLLOWS its row; it is never closed from here.
  //
  // Closing on scroll was tried and is wrong, because scroll events are
  // ASYNCHRONOUS: restoring the scroll position two lines above queues an event
  // that arrives after this function returns, so the menu closed itself the
  // instant it was opened on any row the person had scrolled to. Repositioning
  // has no such race — and placeOpenAccountMenu clamps inside the card, so a
  // row scrolled out of view leaves the menu parked at the edge rather than
  // adrift.
  list.addEventListener("scroll", () => {
    if (state.openAccountMenu) placeOpenAccountMenu();
  }, { passive: true });
}

/** Put the open menu where it fits, measured against the card it hangs in.
 *
 * Preferred position is just under the ⋮ that opened it. When there is not room
 * below, it opens upward from just above it instead; when neither fits — a very
 * short panel with a tall menu — it is clamped inside the card, because a menu
 * half outside its surface is worse than one that does not quite line up.
 *
 * Everything here is read after layout, because it depends on where the row
 * currently is, and scrolling moves that.
 */
/** The ⋮ the open menu belongs to, or null when there is no menu open. */
function triggerForOpenMenu() {
  const card = $("accounts-card");
  if (!card || !state.openAccountMenu) return null;
  const row = card.querySelector(
    `.account-row[data-account-id="${CSS.escape(state.openAccountMenu)}"]`);
  return row ? row.querySelector(".account-menu-button") : null;
}

function placeOpenAccountMenu() {
  const card = $("accounts-card");
  const menu = card && card.querySelector(".account-menu");
  if (!menu) return;
  const trigger = triggerForOpenMenu();
  if (!trigger) return;

  const cardBox = card.getBoundingClientRect();
  const triggerBox = trigger.getBoundingClientRect();
  const gap = 4;
  const below = triggerBox.bottom - cardBox.top + gap;
  const above = triggerBox.top - cardBox.top - menu.offsetHeight - gap;
  const highest = gap;
  const lowest = card.clientHeight - menu.offsetHeight - gap;

  let top = below;
  if (below > lowest) top = above;
  menu.style.top = `${Math.round(Math.max(highest, Math.min(top, lowest)))}px`;
}

function focusAccountMenuButton(id) {
  const card = $("accounts-card");
  if (!card) return;
  const row = card.querySelector(`.account-row[data-account-id="${CSS.escape(id)}"]`);
  const button = row && row.querySelector(".account-menu-button");
  if (button) button.focus({ preventScroll: true });
}

function toggleAccountsList() {
  state.accountsExpanded = !state.accountsExpanded;
  // Collapsing hides the rows a menu is anchored to, and a menu left open would
  // be re-opened by the next expand for a row nobody is looking at any more.
  state.openAccountMenu = null;
  state.pendingRemove = null;
  renderAccountsCard();
}

function toggleAccountMenu(id) {
  const opening = state.openAccountMenu !== id;
  state.openAccountMenu = opening ? id : null;
  // A confirm belongs to the menu that raised it. Opening another one, or
  // closing this one, ends the question rather than carrying it around.
  state.pendingRemove = null;
  renderAccountsCard();
  if (!opening) focusAccountMenuButton(id);
}

function closeAccountMenu({ restoreFocus = false } = {}) {
  if (!state.openAccountMenu) return;
  const id = state.openAccountMenu;
  state.openAccountMenu = null;
  state.pendingRemove = null;
  renderAccountsCard();
  if (restoreFocus) focusAccountMenuButton(id);
}

function setAccountsStatus(detail) {
  const status = $("accounts-status");
  if (!status) return;
  status.textContent = detail || "";
  status.classList.toggle("hidden", !detail);
}

async function removeAccount(id) {
  state.pendingRemove = null;
  state.openAccountMenu = null;
  try {
    const held = await forgetAccount(id);
    state.accounts = held.accounts;
    state.currentAccountId = held.currentId;
  } catch (_) { /* the panel works without the directory */ }
  setAccountsStatus("");
  renderAccountsCard();
}

// The four actions that need a token for an account this panel is not currently
// holding one for. Each is a single call into identity.js, and each reports what
// came back rather than pretending it worked — today that is the same sentence
// for all of them, because the build has no Web OAuth client yet and
// `authorize` refuses before opening anything.

async function switchToAccount(id) {
  const account = state.accounts.find((held) => held.id === id);
  if (!account) return;
  closeAccountMenu();
  const result = await authorize({ email: account.email, interactive: false });
  if (result.state !== "ok" && result.state !== "partial") {
    setAccountsStatus(result.detail);
    return;
  }
  await adoptAuthorizedAccount(result.token);
}

async function signInToAccount(id) {
  const account = state.accounts.find((held) => held.id === id);
  if (!account) return;
  closeAccountMenu();
  const result = await authorize({ email: account.email, interactive: true });
  if (result.state !== "ok" && result.state !== "partial") {
    setAccountsStatus(result.detail);
    return;
  }
  await adoptAuthorizedAccount(result.token);
}

async function addAnotherAccount() {
  closeAccountMenu();
  const result = await authorize({ interactive: true });
  if (result.state !== "ok" && result.state !== "partial") {
    setAccountsStatus(result.detail);
    return;
  }
  await adoptAuthorizedAccount(result.token);
}

/** Take a freshly authorised token as the panel's current identity. */
async function adoptAuthorizedAccount(token) {
  setAccountsStatus("");
  const lookup = await accountFor(token, window.fetch, {signal: panelController.signal});
  if (lookup.state !== "ok") {
    setAccountsStatus(lookup.detail);
    return;
  }
  state.token = token;
  state.account = lookup.account;
  state.accountStatus = null;
  await rememberSignedInAccount(lookup.account);
  renderAccount({});
  renderAccountsCard();
}

async function signOutOfAccount(id) {
  closeAccountMenu();
  if (id === state.currentAccountId) {
    const button = $("signout");
    if (button) button.click();
    return;
  }
  // No token is held for any other account — there is nothing to end here, and
  // saying so is better than a button that appears to work and does nothing.
  setAccountsStatus("That account has no session on this device to end.");
}

async function signOutOfAllAccounts() {
  closeAccountMenu();
  const button = $("signout");
  // The current account is the only one holding a session, so ending it ends
  // them all. The row for every account stays; signing out is not removing.
  if (button) button.click();
}

// ---- Profile › Manage account ----------------------------------------------
//
// Everything on this screen is about the Drive side of the signed-in account.
// Every number is READ LIVE — the folder id, the listing and the pointer — and
// nothing is cached between visits: a count that is stale is a count that lies,
// and this screen exists to be believed.
//
// It is a sibling section of #view-profile rather than a child, because its
// confirmation is a real modal and tests/test_panel_dom.py forbids
// [role="dialog"] anywhere inside #view-profile.

const GOOGLE_PERMISSIONS_URL = "https://myaccount.google.com/permissions";
let manageAccountGeneration = 0;

function driveFolderUrl(id) {
  return `https://drive.google.com/drive/folders/${encodeURIComponent(id)}`;
}

/** One row of a Manage-account card. `onClick` makes it a button instead. */
function manageRow(title, {
  sub = "", figure = "", lead = "", symbol = "", onClick = null,
} = {}) {
  const row = el(onClick ? "button" : "div",
                 "manage-account-row"
                 + (onClick ? " manage-account-row-button" : "")
                 + (lead ? " has-lead" : ""));
  if (onClick) {
    row.type = "button";
    row.addEventListener("click", onClick);
  }
  // The leading icon is a column of its own. Appending it after the figure put
  // a third child in a two-column grid, which wrapped it onto its own line.
  if (lead) row.insertAdjacentHTML("beforeend", icon(lead, "lg manage-account-row-icon"));
  const text = el("span", "manage-account-row-text");
  text.append(el("span", "manage-account-row-title", title));
  if (sub) text.append(el("span", "manage-account-row-sub", sub));
  row.append(text);
  if (figure) row.append(el("span", "manage-account-figure", figure));
  if (symbol) row.insertAdjacentHTML("beforeend", icon(symbol, "lg manage-account-row-icon"));
  return row;
}

// The one sentence that says what a backup contains. Sourced from
// scrapex/bundle.py, not from the design draft, so a change to what is packed
// has one place to be corrected.
const BUNDLE_CONTENTS =
  "The database, a plain export of every dataset (JSON Lines and CSV), and a "
  + "manifest with row counts and checksums.";

function renderDriveFacts(
  { state: phase, pointer = null, count = 0, folder = "", detail = "" } = {}) {
  const card = $("drive-backups");
  if (!card) return;
  card.textContent = "";

  if (phase === "loading") {
    card.append(manageRow("Reading your Drive…"));
    return;
  }
  if (phase === "signed-out") {
    card.append(manageRow("Sign in to see what is in your Drive"));
    return;
  }
  if (phase === "error") {
    card.append(manageRow("Could not read your Drive", { sub: detail }));
    return;
  }

  if (pointer) {
    // financeDateTime despite the name: it is the panel's ONE instant formatter
    // and routes through ScrapeXTime, so this screen cannot invent a second date
    // format. fmtMegabytes is the same argument for sizes.
    card.append(manageRow("Latest backup", {
      sub: financeDateTime(pointer.created_at, "Time not recorded"),
      figure: fmtMegabytes(pointer.bytes),
      lead: "history",
    }));
    // The REAL count, not the policy. Pruning happens on the next backup, so a
    // folder can briefly hold more than KEEP; `Math.min(count, KEEP)` was tried
    // and it silently reported 3 while 4 were sitting there. The policy belongs
    // in the sentence beside it, where it is a promise rather than a miscount.
    card.append(manageRow("Backups kept", {
      sub: `In the folder ScrapeX created, ${FOLDER_NAME}. The newest ${KEEP} are kept.`,
      figure: String(count),
      lead: "storage",
    }));
  } else {
    // The card STAYS. Hiding it would leave the person with no way to learn
    // what a backup will contain before making one.
    card.append(manageRow("No backups in your Drive yet."));
  }

  card.append(manageRow("Each backup holds", { sub: BUNDLE_CONTENTS }));

  if (folder) {
    card.append(manageRow("Open the folder in Drive", {
      symbol: "open-in-new",
      onClick: () => window.open(driveFolderUrl(folder), "_blank", "noopener,noreferrer"),
    }));
  }
}

/** Say what went wrong in the words the person's next step depends on. */
function driveFailureDetail(error) {
  if (!error) return "Google did not say why.";
  if (error.kind === "unauthorized") {
    return "Google refused the token. Sign in again from the Profile page.";
  }
  if (error.kind === "forbidden") {
    return "Google refused the request — usually a full Drive or a rate limit.";
  }
  if (error.kind === "network") return "Could not reach Google.";
  if (error.kind === "malformed-pointer") {
    return "The backup pointer in your Drive could not be read.";
  }
  return error.message || "Google did not say why.";
}

function renderManageAccountIdentity() {
  const account = state.account;
  $("manage-account-name").textContent = (account && account.name) || "Signed in";
  const email = (account && account.email) || "";
  $("manage-account-email").textContent = email;
  $("manage-account-email").classList.toggle("hidden", !email);

  const photo = $("manage-account-photo");
  if (account && account.picture) {
    photo.onerror = () => photo.classList.add("hidden");
    photo.onload = () => photo.classList.remove("hidden");
    photo.src = account.picture;
  } else {
    photo.removeAttribute("src");
    photo.classList.add("hidden");
  }
}

async function loadManageAccount() {
  renderManageAccountIdentity();
  setDisconnectStatus("");
  if (!state.token) {
    renderDriveFacts({ state: "signed-out" });
    return;
  }

  // Generation guard, the same one loadAccount uses: leaving and returning
  // starts a second read, and the slower answer must not paint over the newer.
  const generation = ++manageAccountGeneration;
  const current = () => generation === manageAccountGeneration
    && !panelController.signal.aborted;
  renderDriveFacts({ state: "loading" });
  try {
    const folder = await folderId(state.token);
    if (!current()) return;
    const files = await listing(state.token, folder);
    if (!current()) return;
    const pointer = await readLatest(state.token, folder);
    if (!current()) return;
    // The pointer file is not a backup. Counting it would say 4 of 3.
    const bundles = files.filter((file) => file.name && file.name.endsWith(".zip"));
    renderDriveFacts({ state: "ok", pointer, count: bundles.length, folder });
  } catch (error) {
    if (!current()) return;
    renderDriveFacts({ state: "error", detail: driveFailureDetail(error) });
  }
}

function setDisconnectStatus(detail) {
  const status = $("disconnect-status");
  if (!status) return;
  status.textContent = detail || "";
  status.classList.toggle("hidden", !detail);
}

// ---- the confirmation ------------------------------------------------------
// A plain element, not <dialog>: the document keydown handler in this file
// calls preventDefault() on every Escape, which would stop the browser's own
// close and leave a dialog that only the mouse can dismiss.

let disconnectReturnFocus = null;

function disconnectDialogCopy() {
  const email = (state.account && state.account.email) || "your account";
  const veil = document.createDocumentFragment();
  const first = el("p", "", `Backups stop, and ScrapeX loses access to the folder it `
    + `created for ${email}. The backups already in your Drive stay where they are.`);
  const second = el("p", "");
  second.append(el("strong", "", "Nothing is deleted."),
                document.createTextNode(" Not in your Drive, not on this machine. "
                  + "Because the same Google grant carries your name and address, "
                  + "this also signs you out of ScrapeX."));
  veil.append(first, second);
  return veil;
}

function openDisconnectDialog() {
  const veil = $("disconnect-veil");
  if (!veil) return;
  disconnectReturnFocus = document.activeElement;
  const copy = $("disconnect-dialog-copy");
  copy.textContent = "";
  copy.append(disconnectDialogCopy());
  veil.classList.remove("hidden");
  $("disconnect-dialog").focus({ preventScroll: true });
}

function closeDisconnectDialog({ restoreFocus = true } = {}) {
  const veil = $("disconnect-veil");
  if (!veil || veil.classList.contains("hidden")) return;
  veil.classList.add("hidden");
  if (restoreFocus && disconnectReturnFocus && disconnectReturnFocus.isConnected) {
    disconnectReturnFocus.focus({ preventScroll: true });
  }
  disconnectReturnFocus = null;
}

function disconnectDialogIsOpen() {
  const veil = $("disconnect-veil");
  return Boolean(veil) && !veil.classList.contains("hidden");
}

/** Keep Tab inside the dialog while it is open. */
function trapDisconnectFocus(event) {
  if (event.key !== "Tab" || !disconnectDialogIsOpen()) return;
  const dialog = $("disconnect-dialog");
  const focusable = dialog.querySelectorAll("button:not(:disabled)");
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;
  if (event.shiftKey && (active === first || active === dialog)) {
    event.preventDefault();
    last.focus({ preventScroll: true });
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus({ preventScroll: true });
  }
}

/** Disconnect Drive — which is the same act as signing out.
 *
 * `revokeToken` ends the WHOLE grant at Google, identity scopes included; there
 * is no Drive-only revoke. The button says so, and this reuses the sign-out path
 * rather than writing a second one: it is the tested one, and its ordering
 * (revoke while the token is still valid, then drop Chrome's copy) is
 * load-bearing.
 */
async function disconnectDrive() {
  const primary = $("drive-disconnect").querySelector(".split-button-primary");
  const confirm = $("disconnect-confirm");
  primary.disabled = true;
  confirm.disabled = true;
  setDisconnectStatus("Ending the grant at Google…");
  try {
    const signout = $("signout");
    if (signout) signout.click();
    setDisconnectStatus("");
    closeDisconnectDialog({ restoreFocus: false });
    showView("profile");
  } finally {
    primary.disabled = false;
    confirm.disabled = false;
  }
}

// ---- what is installed, and what is available -----------------------------
// The Engines page is the one page that has to work with NO ENGINE INSTALLED —
// that is its whole purpose, and it is the state every machine is in for its
// first minute. So the feed is read by the extension, and the page is filled
// whether or not anything is running.
//
// Asked once per panel open and remembered. Engine status and release status
// are checked independently: the local engine state is known immediately from
// `state`, while the remote release feed is fetched only when missing and
// never blocks the engine status from being shown.
let latestRelease = null;

function setEngineBusy(busy) {
  const region = $("engine-status-region");
  if (region) region.setAttribute("aria-busy", String(busy));
}

// True for the whole of the Engine page's own Check again — the health answer,
// the version report AND the release feed — because that is what the owner
// pressed, and the button is disabled for exactly as long.
let engineRecheckRunning = false;

// aria-busy is DERIVED, never hand-set beside a status write. It was hand-set in
// four places once the Engine check began settling independently of the rest of
// startup, and they disagreed: entering this page mid-check announced a settled
// region over the words "Checking engine…", and clearing it when the health
// answer landed announced a finished recheck while Check again was still
// disabled and the release feed still out.
function refreshEngineBusy() {
  setEngineBusy(engineRecheckRunning || state.engineState === "checking");
}

function engineStatusFromState() {
  // THE CHECK IS STILL RUNNING is a state, not a verdict. The Engine check now
  // settles independently of the rest of startup, so this card can be read
  // while the answer is still in flight — and showing the previous open's
  // verdict in that window is how a panel comes to claim "Not detected" about
  // an engine nobody has asked about yet. Said first, because every branch
  // below it is a conclusion and this one is the absence of a conclusion.
  if (state.engineState === "checking") {
    return { text: "Checking engine…", tone: "neutral", detail: "" };
  }
  if (state.protocolMismatch) {
    return {
      text: "Incompatible",
      tone: "danger",
      detail: `Engine protocol ${state.engineProtocol} · Extension protocol ${PROTOCOL_VERSION}`,
    };
  }
  if (state.engineUp) {
    return { text: "Running", tone: "ok", detail: "" };
  }
  // A DEADLINE THAT EXPIRED IS NOT AN ABSENT ENGINE. Without this the health
  // check's own timeout fell through to "Not detected" below and told the owner
  // his engine is not installed, which is a different problem with a different
  // and useless answer. The Check again action beside this row is what repairs
  // it, so the text does not have to say "retry available" — the button does.
  if (state.engineState === "timeout") {
    return {
      text: "Check timed out",
      tone: "warn",
      detail: "The engine did not answer before its deadline. Check again when it is ready.",
    };
  }
  if (state.engineVersion) {
    return { text: "Installed, not running", tone: "warn", detail: "" };
  }
  if (state.engineReachable) {
    // The endpoint answered but the worker is not alive. We cannot prove the
    // executable is absent, only that it is not running right now.
    return { text: "Not running", tone: "warn", detail: "" };
  }
  return {
    text: "Not detected",
    tone: "neutral",
    detail: "The panel could not reach the Engine.",
  };
}

function updateEngineStatus() {
  const summary = engineStatusFromState();
  const badge = $("engine-status-badge");
  const dot = $("engine-status-dot");
  badge.className = "badge";
  dot.className = "dot";
  if (summary.tone === "ok") {
    badge.classList.add("ok");
    dot.classList.add("on");
  } else if (summary.tone === "warn") {
    badge.classList.add("off");
    dot.classList.add("warn");
  } else if (summary.tone === "danger") {
    badge.classList.add("danger");
    dot.classList.add("off");
  }
  $("engine-status").textContent = summary.text;
  const detail = $("engine-status-detail");
  detail.textContent = summary.detail;
  detail.classList.toggle("hidden", !summary.detail);
}

function engineProtocolText() {
  const installed = state.engineVersion;
  if (!installed) return "Not available";
  if (state.engineProtocol === null) return `Not reported · Extension expects ${PROTOCOL_VERSION}`;
  if (state.protocolMismatch) return `Engine ${state.engineProtocol} · Extension ${PROTOCOL_VERSION}`;
  return String(state.engineProtocol);
}

function updateEngineWarning() {
  const warning = $("engine-compatibility-warning");
  if (state.protocolMismatch) {
    warning.textContent =
      `The installed engine uses protocol ${state.engineProtocol}; this extension uses ${PROTOCOL_VERSION}. They cannot communicate.`;
    warning.classList.remove("hidden");
  } else {
    warning.classList.add("hidden");
    warning.textContent = "";
  }
}

function renderEngineStatusUI() {
  const installed = state.engineVersion || "";
  $("engine-installed-version").textContent = installed || "Not detected";
  $("engine-protocol-row").textContent = engineProtocolText();
  updateEngineWarning();
  updateEngineStatus();
  refreshEngineBusy();
}

function engineReleaseVerdict(installed, latest) {
  if (latest.state === "offline" || latest.state === "unreadable") return "Update status unavailable";
  if (latest.state === "none") return "";
  if (latest.state !== "ok") return "";
  const hasInstaller = !!latest.installer;
  if (!installed) return hasInstaller ? "Available to install" : "";
  try {
    if (isOlder(installed, latest.version)) return "Update available";
    return "Up to date";
  } catch {
    return "";
  }
}

function updateEngineReleaseUI(latest) {
  const installed = state.engineVersion || "";

  $("engine-latest-version").textContent =
    latest.state === "ok" ? latest.version
    : latest.state === "none" ? "No release yet"
    : "Unavailable";

  $("engine-latest-detail").textContent = latest.state === "ok"
    ? (latest.installer
        ? ""
        : "This release has no installer attached, so there is nothing to install yet.")
    : (latest.detail || "");

  $("engine-release-verdict").textContent = engineReleaseVerdict(installed, latest);

  const download = $("engine-download");
  const steps = $("engine-install-steps");
  const installer = latest.state === "ok" ? latest.installer : null;

  download.disabled = !installer;
  steps.classList.toggle("hidden", !installer);

  if (installer) {
    $("engine-download-checksum").textContent = installer.sha256 ? installer.sha256 : "";
    download.onclick = () => {
      window.open(installer.url, "_blank");
      steps.open = true;
    };
  } else {
    download.onclick = null;
  }
}

async function renderEngines() {
  // The local engine status is known from state immediately and must not be
  // hidden while waiting for the remote release feed.
  renderEngineStatusUI();
  $("engine-recheck").onclick = refreshEngines;

  if (!latestRelease) {
    latestRelease = await latestEngineRelease();
  }
  updateEngineReleaseUI(latestRelease);
}

async function refreshEngines() {
  const recheck = $("engine-recheck");
  recheck.disabled = true;
  engineRecheckRunning = true;
  refreshEngineBusy();
  try {
    // Only refresh Engine health and version compatibility. Do not pull in
    // sources, outputs, jobs, or other destination data.
    //
    // The card is put into its checking state by updateEngineState, through the
    // same renderer every other answer takes. This used to hand-write the badge,
    // the dot and the words here — a second description of "checking" that the
    // status renderer knew nothing about and could contradict.
    await updateEngineState();
    renderEngineStatusUI();

    latestRelease = null;
    const latest = await latestEngineRelease();
    updateEngineReleaseUI(latest);
  } finally {
    // Both in the same synchronous step, deliberately: a reader who sees the
    // region stop being busy must find the button that ends it enabled, not
    // enabled a network round trip later.
    engineRecheckRunning = false;
    refreshEngineBusy();
    recheck.disabled = false;
  }
}

// ---- Engine overflow menu ----------------------------------------------
function openEngineSetupGuide() {
  chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html") });
}

async function copyEngineDetails() {
  const backend = await backendBase();
  const lines = [
    `Status: ${$("engine-status").textContent}`,
    `Installed version: ${$("engine-installed-version").textContent}`,
    `Latest version: ${$("engine-latest-version").textContent}`,
    `Protocol: ${$("engine-protocol-row").textContent}`,
    `Backend: ${backend}`,
  ];
  if (state.versionReport && state.versionReport.outdated) {
    lines.push(`Extension outdated: installed ${state.installedVersion}, requires ${state.versionReport.minimum_extension_version}`);
  }
  const text = lines.join("\n");
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    // Fallback for contexts where clipboard permission is not granted.
  }
}

async function runEngineDiagnostics() {
  const out = $("engine-diagnostics-output");
  out.classList.remove("hidden");
  out.textContent = "Running diagnostics…";
  // probeEngine, not checkEngine: the same deadline and the same cancellation
  // signal every other local request now carries. A diagnostics button that can
  // hang for ever is the one button in the panel that must not.
  const engine = await probeEngine();
  setStatus(engine);
  renderEngineStatusUI();
  out.textContent = engine.protocolMismatch
    ? `The panel and the ScrapeX engine speak different protocol versions ` +
      `(panel ${engine.clientProtocol}, engine ${engine.engineProtocol}). ` +
      `Update whichever is older.`
    : engine.running
    ? `Engine reachable at ${await backendBase()} · version ${engine.version || "unknown"}`
    : `No engine at ${await backendBase()}. Start the engine, then check again.`;
}

function bindEngineOverflowMenu() {
  const button = $("engine-overflow");
  const menu = $("engine-overflow-menu");
  if (!button || !menu) return;
  const items = () => Array.from(menu.querySelectorAll('[role="menuitem"]'));

  function openMenu() {
    menu.classList.remove("hidden");
    button.setAttribute("aria-expanded", "true");
    const first = items()[0];
    if (first) first.focus({ preventScroll: true });
    document.addEventListener("click", outsideClick, true);
  }

  function closeMenu(returnFocus = true) {
    menu.classList.add("hidden");
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", outsideClick, true);
    if (returnFocus) button.focus({ preventScroll: true });
  }

  function outsideClick(e) {
    if (!menu.contains(e.target) && e.target !== button) closeMenu(true);
  }

  button.addEventListener("click", () => {
    if (menu.classList.contains("hidden")) openMenu(); else closeMenu(false);
  });

  button.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openMenu();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      openMenu();
    }
  });

  menu.addEventListener("keydown", (e) => {
    const list = items();
    const idx = list.indexOf(document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      closeMenu(true);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = list[(idx + 1) % list.length];
      next.focus({ preventScroll: true });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = list[(idx - 1 + list.length) % list.length];
      prev.focus({ preventScroll: true });
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      document.activeElement.click();
    } else if (e.key === "Tab") {
      closeMenu(true);
    }
  });

  $("engine-diagnostics").addEventListener("click", () => {
    runEngineDiagnostics();
    closeMenu(true);
  });
  $("engine-setup-guide").addEventListener("click", () => {
    openEngineSetupGuide();
    closeMenu(false);
  });
  $("engine-copy-details").addEventListener("click", () => {
    copyEngineDetails();
    closeMenu(true);
  });
}

// ---- the refusal --------------------------------------------------------
// M1's whole "done when": an incompatible engine is REFUSED WITH A NAMED
// ACTION, instead of a dead panel.
//
// Until now nothing checked. `startRun` posted the job and let whatever
// happened happen — and the failure that cost the owner his engine was exactly
// this shape: migration 0061 merged, never applied, the engine refused to start
// and said so correctly on a stderr nobody reads. What he saw was a dead panel.
//
// Every branch returns the SAME five facts, because a refusal that names four
// of them sends someone to check the fifth by hand. Returning null is the only
// way to run.
function engineRefusal() {
  const facts = () => ({
    "Extension": state.installedVersion || "unknown",
    "Engine": state.engineVersion || "unknown",
    "Minimum extension the engine will talk to":
      state.versionReport ? state.versionReport.minimum_extension_version : "unknown",
    "Protocol - extension": String(PROTOCOL_VERSION),
    "Protocol - engine":
      state.engineProtocol === null ? "not stated" : String(state.engineProtocol),
  });

  if (!state.engineUp) {
    return { title: "The engine is not running", facts: facts(),
             action: "Start it from Settings, then try again." };
  }

  // THE PROTOCOL FIRST, because it is the only one of these that makes every
  // other answer meaningless: two products that cannot agree how to speak
  // cannot be compared on features at all.
  if (state.protocolMismatch) {
    const engineIsOlder = state.engineProtocol < PROTOCOL_VERSION;
    return {
      title: "The extension and the engine speak different protocol versions",
      facts: facts(),
      action: engineIsOlder
        ? "Install the newer engine from its GitHub release, then reopen this panel."
        : "This extension is behind the engine. Chrome updates it from the Web " +
          "Store on its own schedule; reopen the panel once it has.",
    };
  }

  // An engine that answers /api/health and says nothing about its features is
  // ONE fact with three causes, and none of them is "everything is fine".
  if (!state.versionReport) {
    return {
      title: "The engine did not say what it supports",
      facts: facts(),
      action: "It is older than feature reporting, or the request failed. " +
        "Restart the engine from Settings; if it persists, install the " +
        "current engine from its GitHub release.",
    };
  }

  if (!state.installedVersion) {
    // Refusing here rather than guessing: claiming support that cannot be
    // proved is the silent failure this gate removes, and the comparison
    // below would throw on "unknown" and lose the click entirely.
    return {
      title: "This extension cannot read its own version",
      facts: facts(),
      action: "Close and reopen the side panel. If it persists, reload ScrapeX " +
        "and open it again.",
    };
  }

  if (isOlder(state.installedVersion, state.versionReport.minimum_extension_version)) {
    const missing = (state.versionReport.missing || [])
      .map((m) => m.summary + " (needs " + m.since + ")");
    return {
      title: "This extension is older than the engine will talk to",
      facts: facts(),
      missing,
      action: state.versionReport.update_instructions ||
        "Update the extension, then reopen this panel.",
    };
  }

  return null;
}

function renderRefusal(where, refusal) {
  const box = $(where);
  if (!box) return;
  if (!refusal) { box.innerHTML = ""; box.classList.add("hidden"); return; }
  box.innerHTML =
    '<div class="setup-title">' + esc(refusal.title) + '</div>' +
    Object.entries(refusal.facts).map(([k, v]) =>
      '<div class="kv"><span>' + esc(k) + '</span>' +
      '<span class="tech">' + esc(v) + '</span></div>'
    ).join("") +
    ((refusal.missing || []).length
      ? '<div class="muted text-sm">Not available in this extension:</div>' +
        '<ul class="muted text-sm">' +
        refusal.missing.map((m) => '<li>' + esc(m) + '</li>').join("") + '</ul>'
      : "") +
    '<div class="muted text-sm">' + esc(refusal.action) + '</div>';
  box.classList.remove("hidden");
}

function refreshRunButton() {
  syncModeChoices();
  const n = state.selected.size;
  $("sel-count").textContent = `${n} selected`;
  const refusal = engineRefusal();
  let blocked = "";
  if (!refusal) {
    if (!n) blocked = "Select at least one site above.";
    else if (state.job) blocked = "A job is already running. It will queue behind it.";
  }
  // The refusal disables the button as well as explaining it. A pressable
  // button that always fails is the dead panel with an extra click in it.
  $("run").disabled = Boolean(refusal) || !n;
  $("run-blocked").textContent = blocked;
  renderRefusal("run-refusal", refusal);
}

async function startRun() {
  // Checked again here and not only in refreshRunButton: the engine can stop,
  // or be replaced by an older one, between the render and the click.
  const refusal = engineRefusal();
  if (refusal) { renderRefusal("run-refusal", refusal); return; }
  const keys = [...state.selected];
  if (!keys.length) return;
  const mode = $("run-mode").value;
  if (mode === "full_rebuild" &&
      !confirm(`Full rebuild will archive the current catalogue for ${keys.length} site(s) ` +
               `and take a backup first. Continue?`)) return;
  // A run starts from the top, and capture clears the journal of every source
  // it touches before it fetches anything. So the pages an interrupted crawl
  // kept are gone the moment this is queued — silently, and for elburoj that
  // is 871 pages and most of a day. Say it before it happens.
  const discarding = state.sources.filter(
    (s) => state.selected.has(s.source_key) && keptPages(s) > 0);
  if (discarding.length && !confirm(
      "Starting a run throws away pages that an interrupted crawl kept:\n\n" +
      discarding.map((s) => `  ${s.source_key} — ${pageCount(keptPages(s))}`).join("\n") +
      "\n\nResume, on the site's own row, continues from them instead and " +
      "re-fetches none of them.\n\nDiscard them and start from the top?")) return;
  $("run").disabled = true;
  try {
    const r = await post("/api/jobs", { source_keys: keys, run_mode: mode });
    state.jobRef = r.job_ref;
    await pollJob();
  } catch (e) {
    $("run-blocked").textContent = "Couldn't start: " + e.message;
  } finally { refreshRunButton(); }
}

// ---- activity + mini-player ------------------------------------------------
const POLL_MS = 1500;   // throttled: aggregated progress, never per-record events
let pollTimer = null;
let pollPromise = null;

// ---- ONE formatter each (the DRY the owner asked for) ----------------------
// A count with thousands separators. Every number the panel shows goes through
// here, so 1030 reads as "1,030" everywhere and never as a bare 1030 in one
// place and grouped in another.
function fmtCount(n) {
  return Number(n || 0).toLocaleString();
}

// Bytes as megabytes, for the same reason fmtCount exists: the Storage panel
// had this as a local `mb` helper and the Drive controls needed the identical
// thing, and two copies of one rounding rule is how "12.3 MB" and "12 MB" end
// up on one screen describing the same file.
function fmtMegabytes(n) {
  return `${(Number(n || 0) / 1048576).toFixed(1)} MB`;
}

// A duration in seconds as human time. Shared by elapsed AND the finish
// estimate, so the two can never format the same span two different ways.
function fmtDuration(secs) {
  secs = Math.max(0, Math.round(secs));
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m ${secs % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function fmtElapsed(startedAt) {
  if (!startedAt) return "";
  return fmtDuration((Date.now() - Date.parse(startedAt)) / 1000);
}

// The date an estimate carries, "29 Jul" from "2026-07-29" — the same rule that
// makes a converted price carry its rate's date. Bare YYYY-MM-DD if it cannot
// be parsed, which is still a stated date.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function fmtAsOf(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}` : String(iso || "");
}

// The bar and the sentence beneath it, from job.fetch — requests against a
// stated denominator. THREE honest shapes, never a bare percentage and never a
// bar stuck at 0%:
//   known total   -> a real fraction, the sentence says what OF and (for an
//                    estimate) its date
//   unknown total -> an indeterminate bar and "total not known yet", because a
//                    first-ever crawl genuinely cannot say
function renderProgress(job) {
  const f = job.fetch || {};
  const bar = $("act-bar");
  const label = $("act-progress-label");
  if (f.expected) {
    const pct = Math.min(100, Math.round((f.requests / f.expected) * 100));
    bar.classList.remove("indeterminate");
    bar.style.width = pct + "%";
    // "1,030 of ~2,461 expected (est. 29 Jul)" — a declared total drops the "~"
    // and the date because it is a count, not a guess.
    const tilde = f.basis === "estimate" ? "~" : "";
    const basis = f.basis === "estimate"
      ? ` · estimate from the last crawl${f.as_of ? " (" + fmtAsOf(f.as_of) + ")" : ""}`
      : f.basis === "declared" ? " · the site's own page count"
      : "";
    label.textContent =
      `${fmtCount(f.requests)} of ${tilde}${fmtCount(f.expected)} requests (${pct}%)${basis}`;
  } else {
    // No denominator anywhere: the count climbs and the bar says so, rather
    // than drawing 0% of a number nobody has.
    bar.classList.add("indeterminate");
    bar.style.width = "100%";
    const unknown = (f.unknown_sources || []).length;
    label.textContent = f.requests
      ? `${fmtCount(f.requests)} requests so far · total not known yet` +
        (unknown ? ` (${unknown} source${unknown > 1 ? "s" : ""} with no past crawl to estimate from)` : "")
      : "starting…";
  }
}

// An honest finish estimate, ONLY when the denominator that could ground it
// exists. Derived from the same numbers the bar draws, so it can never claim a
// precision the bar does not have.
function finishEstimate(job) {
  const f = job.fetch || {};
  if (!f.expected || !job.started_at || f.requests < 2) return "";
  const elapsed = (Date.now() - Date.parse(job.started_at)) / 1000;
  const rate = f.requests / elapsed;               // requests per second so far
  if (rate <= 0) return "";
  const remaining = Math.max(0, f.expected - f.requests) / rate;
  const about = f.basis === "estimate" ? "about " : "";
  return `~${about}${fmtDuration(remaining)} left`;
}

function renderActivity(job) {
  const box = $("activity");
  if (!job) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const elapsed = fmtElapsed(job.started_at);
  const left = finishEstimate(job);
  $("act-elapsed").textContent = [elapsed && `elapsed ${elapsed}`, left]
    .filter(Boolean).join(" · ");
  $("act-state").innerHTML =
    `<span>${esc(job.status.replace(/_/g, " "))}${job.stage ? " · " + esc(job.stage) : ""}</span>` +
    `<span class="content">${esc(job.current_source_key || "—")}</span>`;
  renderProgress(job);
  renderQueue(job);
  $("act-counters").innerHTML = activityCounters(job).map(([k, v, title]) =>
    `<div class="kv"${title ? ` title="${esc(title)}"` : ""}>` +
    `<span>${esc(k)}</span><span class="tech">${esc(v)}</span></div>`).join("");
}

// Every row states what it measures. The politeness rows (304s, pace) are the
// owner's own asks: they are the clearest sign a recurring crawl is being cheap
// and welcome, and they only appear when the crawl actually reported them.
function activityCounters(job) {
  const c = job.counters || {};
  const f = job.fetch || {};
  const source = firstFetchingSource(job) || {};
  const rows = [
    ["Sites done", `${job.progress.done} / ${job.progress.total}`],
    ["Requests", fmtCount(f.requests)],
    ["New data rows", fmtCount(c.observations)],
    ["Unchanged", fmtCount(c.duplicates)],
    ["New products", fmtCount(c.products)],
    ["Errors", fmtCount(c.errors)],
  ];
  // 304 Not-Modified against the requests made: the single best sign a recurring
  // crawl is being polite and cheap. Shown only once the source reports it.
  if (source.not_modified) {
    rows.push(["Unchanged pages (304)",
               `${fmtCount(source.not_modified)} of ${fmtCount(source.requests)}`,
               "Pages the site said had not changed since our last visit — fetched cheaply, nothing re-downloaded."]);
  }
  if (source.retries) {
    rows.push(["Retries", fmtCount(source.retries),
               "Requests we had to attempt more than once (a dropped connection, a rate-limit)."]);
  }
  // The pace ACTUALLY in force, and whether the site's Crawl-delay is honoured —
  // a fast crawl and a polite one must not look the same while they happen.
  if (source.pace_s != null && source.pace_s > 0) {
    rows.push(["Pace", `${source.pace_s}s between requests`,
               source.honouring_delay
                 ? "Honouring the site's requested crawl delay."
                 : "Crawl delay overridden for this run at your request."]);
    const perMin = source.pace_s > 0 ? Math.round(60 / source.pace_s) : 0;
    if (perMin) rows.push(["Rate", `~${perMin} requests/min at this pace`]);
  }
  return rows;
}

// The slot of whichever source is fetching right now — the source-level facts
// (304s, pace) belong to a source, not the whole job.
function firstFetchingSource(job) {
  const slots = (job.fetch && job.fetch.sources) || {};
  const current = job.current_source_key;
  if (current && slots[current]) return slots[current];
  return Object.values(slots).find((s) => s && s.state === "fetching") || null;
}

// Why a queued job is not moving — a fact, not a placeholder. Nothing invents a
// finish time for the job in front; "when a slot frees" is the honest wait.
function renderQueue(job) {
  const box = $("act-queue");
  const behind = job.queued_behind;
  if (!behind || behind.starting_now) { box.classList.add("hidden"); box.textContent = ""; return; }
  box.classList.remove("hidden");
  const running = (behind.running || [])
    .map((r) => r.source_keys.join(", ")).filter(Boolean);
  const runningText = running.length
    ? `${running.length === 1 ? "" : running.length + " jobs: "}${running.join("; ")}`
    : "another job";
  const ahead = behind.position - 1;
  box.innerHTML =
    `<strong>Queued.</strong> The engine crawls ${behind.capacity} ` +
    `site${behind.capacity > 1 ? "s" : ""} at a time and is busy with ${esc(runningText)}. ` +
    (ahead > 0 ? `${ahead} job${ahead > 1 ? "s" : ""} ahead of this one; it` : "This") +
    ` starts when a slot frees. ` +
    `<span class="muted">Raise “Sites crawled at the same time” in Settings to run more together.</span>`;
}

// The identity of a log AS DISPLAYED: level and message, in order. The
// separators are control characters no log line can contain, so two different
// logs cannot collide into one signature — which would be the one way this
// optimisation could hide a real change from the owner.
function logSignatureOf(entries) {
  return entries.map((e) => `${e.level}\u0000${e.message}`).join("\u0001");
}

function renderLogs(entries, meta) {
  const box = $("logbox");
  // Rewriting innerHTML destroys the selection inside it, and this runs on a
  // 1.5s poll — so an owner trying to copy an error message out of the log had
  // the highlight taken away from them every 1.5 seconds, whether or not a
  // single line had changed. A crawl is mostly quiet: the entries are usually
  // identical to the ones already on screen, and the cheapest correct fix is to
  // notice that and leave the DOM alone.
  const signature = logSignatureOf(entries);
  // childElementCount guards the other direction: a view switch can empty this
  // box, and a signature that still matched would then leave it empty forever.
  if (signature === state.logSignature && box.childElementCount) return;
  // Follow the tail only when the owner is ALREADY at the bottom. Auto-scroll is
  // no longer a button he has to manage (he asked for that gone): the log simply
  // keeps up if he is watching the newest line, and stays put the moment he
  // scrolls up to read something, so a repaint never yanks him away mid-read.
  const wasAtBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
  state.logSignature = signature;
  state.logs = entries;
  box.innerHTML = entries.map((e) =>
    `<div class="logline"><span class="lvl muted">${esc(e.level)}</span>` +
    `<span class="content">${esc(e.message)}</span></div>`).join("") ||
    `<span class="muted">No log entries yet.</span>`;
  if (wasAtBottom) box.scrollTop = box.scrollHeight;
  // Say what is shown out of what exists — the caption that used to read
  // "Last 200 log entries" is now the truth, whatever the count.
  const total = meta && meta.total != null ? meta.total : entries.length;
  $("log-caption").textContent = total
    ? `Live log · ${fmtCount(total)} entr${total === 1 ? "y" : "ies"}, all shown`
    : "Live log";
}

// The mini-player's own progress figure, drawn from the SAME fetch progress the
// Activity bar uses — never the old sites-percentage that read 0% all run.
function miniProgress(job) {
  const f = job.fetch || {};
  if (f.expected) {
    const pct = Math.min(100, Math.round((f.requests / f.expected) * 100));
    return { pct, text: `${pct}% · ${fmtCount(f.requests)}/${fmtCount(f.expected)}`,
             indeterminate: false };
  }
  return { pct: 100, text: f.requests ? `${fmtCount(f.requests)} requests` : "starting…",
           indeterminate: true };
}

function renderMiniplayer(job, queued) {
  const box = $("miniplayer");
  if (!job) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const scope = job.source_keys.length > 1 ? `${job.source_keys.length} sites` : job.source_keys[0];
  $("mini-title").textContent = `${scope} — ${job.status.replace(/_/g, " ")}`;
  const prog = miniProgress(job);
  $("mini-pct").textContent = prog.text;
  $("mini-bar").style.width = prog.pct + "%";
  $("mini-bar").classList.toggle("indeterminate", prog.indeterminate);
  const c = job.counters || {};
  const bits = [];
  if (job.current_source_key) bits.push(`now: ${job.current_source_key}`);
  if (c.observations != null) bits.push(`${fmtCount(c.observations)} new data rows`);
  if (queued > 0) bits.push(`${queued} queued`);
  $("mini-sub").textContent = bits.join(" · ") || "starting…";
  const paused = job.status === "paused";
  $("mini-pause").textContent = paused ? "Resume" : "Pause";
  $("mini-pause").dataset.control = paused ? "resume" : "pause";
}

async function pollJobOnce() {
  clearTimeout(pollTimer);
  pollTimer = null;
  if (document.visibilityState === "hidden") return;
  let jobs = [];
  try { jobs = (await api("/api/jobs?active_only=true&limit=5")).jobs; }
  catch (_) { renderMiniplayer(null); renderActivity(null); return; }

  const job = jobs[0] || null;
  state.job = job;
  if (job) {
    state.jobRef = job.job_ref;
    renderMiniplayer(job, Math.max(0, jobs.length - 1));
    renderActivity(job);
    // No ?limit: the log shows EVERY entry now (the 200 cap was the client's,
    // and it dropped exactly the line that explained a long run's failure). The
    // answer carries `total` so the caption can state what is shown out of what.
    try {
      const log = await api(`/api/jobs/${job.job_ref}/logs`);
      renderLogs(log.entries, log);
    } catch (_) {}
    refreshRunButton();
    if (document.visibilityState === "visible") {
      pollTimer = setTimeout(() => { pollJob(); }, POLL_MS);
    }
    return;
  }
  // Nothing active. Report how the last one ended, then refresh the counts.
  renderMiniplayer(null);
  if (state.jobRef) {
    try {
      const done = await api(`/api/jobs/${state.jobRef}`);
      renderActivity(done);
      const log = await api(`/api/jobs/${state.jobRef}/logs`);
      renderLogs(log.entries, log);
    } catch (_) {}
    state.jobRef = null;
    await loadSources();
  }
  refreshRunButton();
}

async function pollJob() {
  clearTimeout(pollTimer);
  pollTimer = null;
  if (document.visibilityState === "hidden") return null;
  if (pollPromise) return pollPromise;
  pollPromise = pollJobOnce().finally(() => { pollPromise = null; });
  return pollPromise;
}

function handlePanelVisibility() {
  if (document.visibilityState === "hidden") {
    clearTimeout(pollTimer);
    pollTimer = null;
    return;
  }
  // The shared appearance/timezone modules perform their own immediate refresh
  // on this event. Only the job poll is owned here, and the in-flight guard
  // in pollJob prevents a second timer or request from being created.
  //
  // NO `state.job || state.jobRef` CONDITION. It used to require one, which
  // meant the poll only resumed for a run this DOCUMENT already knew about —
  // and a panel that was closed and reopened is a new document that knows about
  // nothing. See reattachToRunningJob for the rest of that story.
  if (state.engineUp) pollJob();
}

/**
 * Find a crawl that was already running when this panel opened.
 *
 * ISSUE 161, and the half of it that was fragile. (Written without a
 * leading hash: a hash and three hex digits is a colour literal to
 * test_ui_colour_literals_live_only_in_the_canonical_colour_system, and a
 * false positive there is still the guard doing its job.) app.js has promised since it
 * was written that "closing this panel never stops a run and reopening
 * reconnects to whatever is already in flight". The first half is the engine's
 * doing and holds. The second was nobody's.
 *
 * `pollJob` had exactly one startup caller — loadRunDestination — which returns
 * early unless the current view is "run". The panel opens on "profile" (line
 * "The panel opens on Welcome"), so a reopened panel polled NOTHING until the
 * owner happened to click Run. A crawl could be an hour into muqawil's 34 hours
 * and the panel would show an idle screen.
 *
 * The failure is worse than a blank: the natural response to a run that has
 * vanished is to start it again, and now two crawls of one source are writing
 * at once.
 *
 * `pollJobOnce` already asks the engine for `active_only=true` and adopts
 * whatever comes back, so reconnecting needs no new endpoint and no state
 * carried across the close — only for the question to be asked.
 */
async function reattachToRunningJob() {
  if (!state.engineUp) return null;
  return pollJob();
}

async function controlJob(control) {
  if (!state.jobRef) return;
  if (control === "cancel" && !confirm("Cancel this job? Work already saved is kept.")) return;
  try { await post(`/api/jobs/${state.jobRef}/control`, { control }); }
  catch (e) { $("run-blocked").textContent = e.message; }
  await pollJob();
}

// ---- browse data -----------------------------------------------------------
async function loadDatasets() {
  const box = $("datasets");
  try {
    const { sources } = await api("/api/sources");
    const withData = sources.filter((s) => s.observations > 0);
    if (!withData.length) {
      box.innerHTML = `<div class="card"><span class="muted">No data yet. Run a crawl from the Run tab.</span></div>`;
      return;
    }
    box.innerHTML = withData.map((s) => `
      <article class="card dataset-card" data-open="${esc(s.source_key)}"
               role="link" tabindex="0"
               aria-label="Open ${esc(sourceDomain(s.base_url) || s.source_name || s.source_key)} dataset in workbook">
        ${sourceMenu(s)}
        <div><div class="dataset-identity-line">${sourceIdentity(
          s, false, fmtCount(s.observations))}</div>
          <div class="n">${fmtCount(s.products)} products</div>
          <div class="n muted">${freshnessLine(s)}</div></div>
      </article>`).join("");
    box.querySelectorAll(".dataset-card .split-button").forEach((root) => {
      const key = root.closest("[data-open]").dataset.open;
      window.ScrapeXSplitButton.wire(root, (action) => runSourceAction(action, key));
    });
    box.querySelectorAll("[data-open]").forEach((card) => {
      // THE MENU IS INSIDE THE CARD, AND THE CARD IS ITSELF A LINK. Without
      // this guard, opening the menu ALSO opens the dataset in a new tab — the
      // owner clicks three dots and lands on a different page, having chosen
      // nothing. `closest` rather than a target check, because the click can
      // land on the icon, the summary or the option inside it.
      card.addEventListener("click", (event) => {
        if (event.target.closest(".split-button")) return;
        openDataset(card.dataset.open);
      });
      card.addEventListener("keydown", (event) => {
        if (!["Enter", " "].includes(event.key)) return;
        if (event.target.closest(".split-button")) return;
        event.preventDefault();
        openDataset(card.dataset.open);
      });
    });
  } catch (_) {
    // NOT A DEAD END ANY MORE. This is the machine with no engine on it — the
    // case the whole bundle format was designed for — and until now the panel
    // said "couldn't reach the engine" and stopped, while a complete copy of
    // the owner's data sat in their Drive.
    box.innerHTML = `<div class="card">
      <span class="err">Couldn't reach the engine.</span>
      <p class="hint">Your data is still in your Drive backup. It can be read
        here without the engine — it will be a snapshot from the last backup,
        not live.</p>
      <button id="browse-offline" class="button" type="button">
        Read my Drive backup</button>
      <p id="offline-msg" class="hint" role="status" aria-live="polite"></p>
    </div>`;
    const button = $("browse-offline");
    if (button) button.addEventListener("click", () => browseFromDrive(box));
  }
}

/**
 * The Data page, read from Drive, on a machine with no engine.
 *
 * 4 MB of gzip against a 36 MB archive only an engine can open, decompressed by
 * the browser itself. bundleview.js has been able to do this since the day it
 * was written and nothing ever called it; this is the call.
 */
async function browseFromDrive(box) {
  if (!state.token) {
    out("offline-msg", "Sign in with Google first — the Account button at the " +
                       "top of the panel.", "err");
    return;
  }
  const button = $("browse-offline");
  if (button) button.disabled = true;
  out("offline-msg", "Fetching the latest backup…", "");
  try {
    const {pack, pointer} = await fetchPanelPack(state.token, {
      onProgress: ({received, total}) => {
        if (total) {
          out("offline-msg",
              `Fetching… ${fmtMegabytes(received)} of ${fmtMegabytes(total)}`, "");
        }
      },
    });
    const datasets = await readPanelPack(pack);
    const summaries = datasetSummaries(datasets);
    if (!summaries.length) {
      out("offline-msg", "That backup carries no datasets.", "err");
      return;
    }
    // A SNAPSHOT, AND IT SAYS SO. Rows read here are as old as the last backup,
    // and a screen that looked identical to the live one would be lying by
    // omission on the day it matters.
    box.innerHTML = `<div class="card">
      <span class="muted">From your Drive backup${
        pointer.created_at ? ` of ${esc(pointer.created_at)}` : ""
      } — not live.</span></div>` +
      summaries.map((d) => `
      <article class="card dataset-card">
        <div><div class="dataset-identity-line">${esc(d.source_key)}</div>
          <div class="n">${fmtCount(d.rows)} rows</div>
          <div class="n muted">${d.has_history
            ? "with change history" : "current prices only"}</div></div>
      </article>`).join("");
  } catch (error) {
    out("offline-msg", esc((error && error.message) || "Something went wrong."), "err");
  } finally {
    if ($("browse-offline")) $("browse-offline").disabled = false;
  }
}

// The freshness of a dataset — the first thing anyone asks, and the fact the
// card was missing where it used to read "no recorded changes yet". A read-out
// from the last SUCCESSFUL crawl; "never" is a real answer, not a blank.
function freshnessLine(s) {
  const last = s.last_success;
  if (!last || !last.started_at) return "no successful crawl yet";
  // Returns MARKUP, so the call site must not esc() it — the same shape
  // fmtStopped uses. It named UTC in fixed text, which made this line the one
  // place in the panel the owner had to convert in his head; and the workspace
  // shows the very same fact from _source_list.html, so the two surfaces
  // disagreed about a date the owner reads to decide whether to re-crawl.
  const when = window.ScrapeXTime.markup(last.started_at, "datetime", {zone: true});
  const measure = last.rows_seen
    ? `${fmtCount(last.rows_seen)} rows seen`
    : last.requests_count ? `${fmtCount(last.requests_count)} requests` : "";
  return `Last crawled ${when}${measure ? " · " + esc(measure) : ""}`;
}

// ---- what can be done to one source, from its own card ----------------------
//
// The card used to carry a chevron and one action: open. Everything else about a
// source lived on another screen or on the engine's web page, and the owner had
// to know where. The chevron is now a menu of the things that are actually about
// THIS source, built on the split-button already shared with the Activity log
// rather than a second menu implementation.
//
// AN ACTION THAT IS NOT BUILT IS SHOWN, DISABLED, WITH THE REASON. The owner
// asked to see the work in progress rather than a tidy screen that hides it, and
// this repository already had the convention ("Not built yet." on the file
// source). A menu that quietly omits what is coming teaches the owner it will
// never exist.
const SOURCE_ACTIONS = [
  {action: "update", label: "Update now",
   why: "Crawl this source once, immediately."},
  {action: "changes", label: "Recent changes",
   why: "What moved since the last crawl."},
  {action: "settings", label: "Source settings",
   why: "Address, name and how this source is read."},
  {action: "pause", label: "Pause collecting",
   why: "Stop scheduled crawls without deleting anything."},
  // BUILT ON 2026-08-12, and it shipped disabled for exactly one day with the
  // reason written on it: sheets.js could create a spreadsheet and fill a tab,
  // and the rows had nowhere to come from. GET /api/export/{key} closed that,
  // reusing the same export_source_table the .xlsx and the Apps Script funnel
  // already use rather than inventing a third idea of what an export is.
  {action: "sheet", label: "Export to Google Sheets",
   why: "One tab per source, in a spreadsheet ScrapeX made in your Drive."},
];

function sourceMenu(source) {
  const options = SOURCE_ACTIONS.map((item) => `
    <button class="split-button-option" role="menuitem" type="button"
            data-split-action="${item.action}"${item.ready === false ? " disabled" : ""}
            title="${esc(item.why)}">${esc(item.label)}${
      item.ready === false ? ' <span class="muted">· not built yet</span>' : ""
    }</button>`).join("");
  return `<div class="split-button" role="group"
               aria-label="Actions for ${esc(source.source_key)}">
      <details class="split-button-menu">
        <summary class="split-button-trigger" aria-haspopup="menu"
                 aria-expanded="false" title="Actions for this source">
          ${icon("more-vert", "sm")}</summary>
        <div class="split-button-options" role="menu">${options}</div>
      </details>
    </div>`;
}

/** Everything a source menu can do, in one place so the card stays a template. */
async function runSourceAction(action, key) {
  if (action === "changes") return openTab(`/source/${key}#changes`);
  if (action === "settings") return openTab(`/sources/${key}`);
  if (action === "update") {
    try {
      await post("/api/jobs", {source_keys: [key], run_mode: "current"});
      showView("run");
    } catch (error) {
      out("datasets-msg", esc((error && error.message) || "Couldn't start it."), "err");
    }
    return;
  }
  if (action === "pause") {
    try {
      await post(`/api/sources/${encodeURIComponent(key)}/active`, {active: false});
      out("datasets-msg", `${esc(key)} paused. Nothing was deleted.`, "ok");
      loadDatasets();
    } catch (error) {
      out("datasets-msg", esc((error && error.message) || "Couldn't pause it."), "err");
    }
    return;
  }
  if (action === "sheet") return exportSourceToSheet(key);
  out("datasets-msg", `Unknown action ${esc(action)}.`, "err");
}

/**
 * One source, into a tab of the owner's own spreadsheet.
 *
 * THE DIVISION HOLDS ALL THE WAY THROUGH. The engine produces rows and knows
 * nothing about Google; the panel talks to Google and never opens a database.
 * The token is read at the moment of use, as everywhere else here, because
 * sign-out clears it from five places and a captured copy would outlive it.
 *
 * ONE TAB PER SOURCE, named for the source. The alternative — everything in one
 * sheet — is the arrangement gdrive.py had, and it means an export of one
 * source silently rewrites the rows of another.
 */
async function exportSourceToSheet(key) {
  if (!state.token) {
    out("datasets-msg", "Sign in with Google first — the Account button at the "
                        + "top of the panel.", "err");
    return;
  }
  out("datasets-msg", `Reading ${esc(key)}…`, "");
  try {
    const table = await api(`/api/export/${encodeURIComponent(key)}`);
    if (!table.rows.length) {
      out("datasets-msg",
          `${esc(key)} has no rows to export yet — crawl it first.`, "err");
      return;
    }

    out("datasets-msg", `Writing ${fmtCount(table.rows.length)} rows to Google…`, "");
    const folder = await ensureFolder(state.token, SHEET_FOLDER);
    const sheet = await ensureSpreadsheet(state.token, DEFAULT_WORKBOOK, {folder});
    await writeTab(state.token, sheet.id, {
      tab: key, header: table.header, rows: table.rows,
    });

    // TRUNCATION IS SAID, NOT LEFT TO BE NOTICED. A spreadsheet that stops at
    // forty thousand rows looks exactly like a business with forty thousand
    // products, and the difference matters on the day someone counts.
    const capped = table.truncated
      ? ` Only the first ${fmtCount(table.limit)} rows fit — the tab is not the whole source.`
      : "";
    out("datasets-msg",
        `${esc(key)}: ${fmtCount(table.rows.length)} rows written to `
        + `<a class="link" href="${esc(sheet.url)}" target="_blank" `
        + `rel="noreferrer noopener">${esc(sheet.name)}</a>.${capped}`,
        table.truncated ? "" : "ok");
  } catch (error) {
    out("datasets-msg", esc((error && error.message) || "Something went wrong."), "err");
  }
}


function openDataset(key) {
  openTab("/source/" + key);
}

// ---- settings --------------------------------------------------------------
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                  "Saturday", "Sunday"];   // 0=Monday, the server's convention

async function loadSchedules() {
  // An EDITOR, not a list. The API could create schedules since spec 26 and
  // the panel could only read them — so the section said "No schedules yet"
  // forever, with no way to change that. One row per implemented site, its
  // saved schedule merged in, defaults from the source's declared cadence.
  try {
    const [d, src] = await Promise.all([api("/api/schedules"), api("/api/sources")]);
    $("sched-note").textContent = d.note;
    const saved = new Map(d.schedules.map((s) => [s.source_key, s]));
    const sites = src.sources.filter((s) => s.implemented);
    if (!sites.length) {
      $("schedules").innerHTML = `<span class="muted">No sites yet.</span>`;
      return;
    }
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    $("schedules").innerHTML = sites.map((s) => {
      const sched = saved.get(s.source_key) || {};
      const freq = sched.frequency || "manual";
      const runAt = sched.run_at || "09:00";
      const weekday = sched.weekday == null ? 0 : Number(sched.weekday);
      const paused = sched.schedule_id != null && !sched.enabled;
      const summary = freq === "manual" ? "manual"
        : freq + (freq === "weekly" ? " · " + WEEKDAYS[weekday] : "") + " · " + esc(runAt);
      // The next fire, in the display zone and NAMING it (§6.8) — a schedule
      // read four hours out is a run the owner waits for and does not get.
      // This is display only: the scheduler still computes and stores the
      // instant in UTC, and the row's own Timezone field below is a different
      // thing entirely (it decides WHEN the job fires, not how it is read).
      const next = paused ? "paused"
        : sched.next_run_at
          ? "next " + window.ScrapeXTime.markup(sched.next_run_at, "datetime", {zone: true})
          : "";
      // The scheduler fires only ACTIVE sources (the Auto switch). A schedule
      // saved on an inactive one is a real record that will not fire — the
      // row says so instead of letting the owner wait for nothing.
      const gate = s.active ? "" :
        `<span class="muted"> — Auto is off for this site, so this will not fire</span>`;
      // Every knob the schedule model has, one disclosure per site so the
      // 320px panel is not wallpapered with forms. This section is THE
      // central control for automation (owner's ruling): nothing about a
      // schedule is decided anywhere else.
      return `<details class="sched-row" data-sched="${esc(s.source_key)}">
        <summary class="row sched-summary">
          ${sourceIdentity(s, true)}
          <span class="muted" data-role="next">${esc(summary)}${next ? " · " + next : ""}</span>
        </summary>
        <div class="stack sched-body">
          <div class="row sched-fields">
            <select data-role="freq" aria-label="Frequency for ${esc(s.source_name)}">
              ${["manual", "daily", "weekly"].map((f) =>
                `<option value="${f}" ${f === freq ? "selected" : ""}>${f}</option>`).join("")}
            </select>
            <select data-role="weekday" class="${freq === "weekly" ? "" : "hidden"}"
                    aria-label="Weekday">
              ${WEEKDAYS.map((w, i) =>
                `<option value="${i}" ${i === weekday ? "selected" : ""}>${w}</option>`).join("")}
            </select>
            <input type="time" data-role="time" value="${esc(runAt)}"
                   aria-label="Run time" ${freq === "manual" ? "disabled" : ""}>
          </div>
          <div class="fieldset">
            <label>Timezone <span class="muted">(IANA name — 09:00 means 09:00 there)</span></label>
            <input data-role="tz" dir="ltr" spellcheck="false"
                   value="${esc(sched.timezone || zone)}" aria-label="Timezone">
          </div>
          <div class="fieldset">
            <label>What the run does</label>
            <select data-role="mode" aria-label="Run mode">
              <option value="update" ${(sched.run_mode || "update") === "update" ? "selected" : ""}>Update existing data</option>
              <option value="full_rebuild" ${sched.run_mode === "full_rebuild" ? "selected" : ""}>Full rebuild (archives first)</option>
              <option value="history_backfill" ${sched.run_mode === "history_backfill" ? "selected" : ""}
                ${s.supports_history ? "" : "disabled"}>History backfill${s.supports_history ? "" : " — not published by this site"}</option>
            </select>
          </div>
          <div class="two">
            <div class="fieldset">
              <label>If the machine was off</label>
              <select data-role="missed" aria-label="Missed run policy">
                <option value="run_when_available" ${(sched.missed_run_policy || "run_when_available") === "run_when_available" ? "selected" : ""}>Run when back</option>
                <option value="skip" ${sched.missed_run_policy === "skip" ? "selected" : ""}>Skip that slot</option>
              </select>
            </div>
            <div class="fieldset">
              <label>If the previous run is still going</label>
              <select data-role="overlap" aria-label="Overlap policy">
                <option value="queue" ${(sched.overlap_policy || "queue") === "queue" ? "selected" : ""}>Queue behind it</option>
                <option value="skip" ${sched.overlap_policy === "skip" ? "selected" : ""}>Skip this one</option>
              </select>
            </div>
          </div>
          <label class="check"><input type="checkbox" data-role="enabled"
                 ${paused ? "" : "checked"}>
            <span>Enabled <span class="muted">— untick to pause without losing these settings</span></span></label>
          <div class="row">
            <button class="ghost" data-role="save">Save</button>
            <span class="hint" data-role="status" role="status" aria-live="polite">${gate}</span>
          </div>
        </div>
      </details>`;
    }).join("");

    $("schedules").querySelectorAll(".sched-row").forEach((row) => {
      const freq = row.querySelector('[data-role="freq"]');
      const weekday = row.querySelector('[data-role="weekday"]');
      const time = row.querySelector('[data-role="time"]');
      const status = row.querySelector('[data-role="status"]');
      freq.addEventListener("change", () => {
        weekday.classList.toggle("hidden", freq.value !== "weekly");
        time.disabled = freq.value === "manual";
      });
      row.querySelector('[data-role="save"]').addEventListener("click", async (event) => {
        const button = event.target;
        button.disabled = true;
        status.textContent = "Saving…";
        try {
          const body = {
            frequency: freq.value,
            run_at: time.value || "09:00",
            timezone: row.querySelector('[data-role="tz"]').value.trim() || "UTC",
            run_mode: row.querySelector('[data-role="mode"]').value,
            missed_run_policy: row.querySelector('[data-role="missed"]').value,
            overlap_policy: row.querySelector('[data-role="overlap"]').value,
            enabled: row.querySelector('[data-role="enabled"]').checked,
          };
          if (freq.value === "weekly") body.weekday = Number(weekday.value);
          const result = await post(
            "/api/schedules/" + encodeURIComponent(row.dataset.sched), body);
          // A textContent sink, so label() — the same formatter, returning the
          // plain sentence instead of markup.
          status.textContent = !body.enabled ? "Saved — paused."
            : result && result.next_run_at
              ? "Saved — next " + window.ScrapeXTime.label(result.next_run_at)
              : "Saved.";
        } catch (e) {
          status.textContent = "Couldn't save: " + e.message;
        } finally {
          button.disabled = false;
        }
      });
    });
  } catch (_) { $("schedules").innerHTML = `<span class="err">Couldn't load schedules.</span>`; }
}

// ---- selected site cards (spec 12) -----------------------------------------
function renderSelected() {
  const box = $("selected");
  const chosen = state.sources.filter((s) => state.selected.has(s.source_key));
  box.classList.toggle("hidden", chosen.length === 0);
  if (!chosen.length) return;
  // Many sites selected -> compact rows, so the run button stays reachable.
  const compact = chosen.length > 3;
  box.innerHTML = `<h2 class="flush">Selected (${chosen.length})</h2>` + chosen.map((s) => {
    const detail = compact ? "" : `
      <div class="kv"><span class="muted">Engine</span><span class="tech">${esc(s.family)}</span></div>
      <div class="kv"><span class="muted">Dataset</span><span>${
        Number(s.observations || 0).toLocaleString()} records</span></div>
      <div class="kv"><span class="muted">Status</span><span>${
        s.implemented ? "Ready" : "Not supported yet"}</span></div>`;
    return `<div class="card">
      <div class="row">
        <span>${sourceIdentity(s)}</span>
        <button class="ghost" data-drop="${esc(s.source_key)}"
                title="Remove from this run — the saved site is kept">Remove</button>
      </div>${detail}
    </div>`;
  }).join("");
  box.querySelectorAll("button[data-drop]").forEach((b) =>
    b.addEventListener("click", () => {
      state.selected.delete(b.dataset.drop);
      renderSites();                    // also re-renders these cards
    }));
}

// ---- output destinations (spec 16) ------------------------------------------
async function loadOutputs() {
  try {
    const { outputs } = await api("/api/outputs");
    const renderRows = (items) => items.map((o) => {
      // State is a WORD, never a colour: "Enabled" / "Needs setup".
      const state_ = o.ready ? (o.required ? "Always on" : "Enabled") : "Needs setup";
      // A destination that needs setup must offer the way to do it. The panel
      // deliberately does not host the setup form: the workspace page owns it,
      // so there is one place where a destination is configured, not two.
      const setup = o.settings_url
        ? `<button class="link" data-setup="${esc(o.settings_url)}">${
             o.ready ? "Settings" : "Set it up"}</button>`
        : "";
      return `<div class="out">
        <span>${esc(o.label)}${o.ready ? "" :
          `<span class="hint muted text-block">${esc(o.blocker || o.detail)}</span>`}
          ${setup}</span>
        <span class="chip ${o.ready ? "" : "off"}">${esc(state_)}</span>
      </div>`;
    }).join("");
    const local = outputs.filter((o) => o.key === "local_db" || o.key === "excel");
    const sync = outputs.filter((o) => o.key !== "local_db" && o.key !== "excel");
    $("outputs").innerHTML = `
      <section class="output-group" aria-labelledby="local-output-heading">
        <div class="output-group-head">
          <h3 id="local-output-heading">Local storage</h3>
          <p>Database and Excel output kept on this computer.</p>
        </div>
        <div>${renderRows(local)}</div>
      </section>
      <section class="output-group" aria-labelledby="sync-output-heading">
        <div class="output-group-head">
          <h3 id="sync-output-heading">Synchronization services</h3>
          <p>Optional destinations that send data outside the local workspace.</p>
        </div>
        <div>${renderRows(sync)}</div>
      </section>`;
    $("outputs").querySelectorAll("[data-setup]").forEach((b) =>
      b.addEventListener("click", () => openTab(b.dataset.setup)));
  } catch (_) {
    $("outputs").innerHTML = `<span class="err hint">Couldn't read output status.</span>`;
  }
}

async function loadStorage() {
  try {
    const s = await api("/api/storage");
    // Health is a WORD here too, never a colour: the panel has no room for a
    // legend, so the state has to be readable on its own.
    $("storage-info").innerHTML = `
      <div class="kv"><span>Database</span><span class="tech">${esc(s.path)}</span></div>
      <div class="kv"><span>Size</span><span>${esc(fmtMegabytes(s.sizes.db_bytes))}</span></div>
      <div class="kv"><span>Health</span><span>${esc(s.health.status)}</span></div>
      <div class="kv"><span>Backups</span><span>${esc(String(s.sizes.backup_count))}</span></div>`;
  } catch (_) {
    $("storage-info").innerHTML = `<span class="err">Couldn't read storage status.</span>`;
  }
}

// ---- source / add site (first tab, spec 11) ---------------------------------
let lastProbe = null;

// ---- the three source choices -----------------------------------------------
// Each one ends at the same confirm-and-adjust form. The panel never registers
// a site from a guess: it detects, shows what it detected, and waits.

async function loadCurrentPage() {
  const title = $("cur-title"), url = $("cur-url"), use = $("cur-use");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const address = tab?.url || "";
    // chrome:// and extension pages are not sites anyone can crawl, and saying
    // so beats offering a button that would fail at probe time.
    if (!/^https?:\/\//.test(address)) {
      title.textContent = "This tab is not a website";
      url.textContent = address || "";
      use.disabled = true;
      // Reset the label too: it may still read "Open its dataset" from the last
      // tab, promising something this page cannot do.
      use.textContent = "Use this page";
      delete use.dataset.registered;
      out("cur-out", "Open a site in this tab, then come back.", "muted");
      return;
    }
    // The tab HAS been read by this point. Everything below talks to the
    // engine, and an engine failure must not be reported as a browser failure —
    // that sends the owner to fix the wrong thing.
    title.textContent = tab.title || "Untitled page";
    url.textContent = address;
    use.disabled = false;
    use.textContent = "Use this page";
    try {
      const known = await api(`/api/resolve?url=${encodeURIComponent(address)}`);
      if (known.matched) {
        // Do NOT offer to add it again: the only action behind that button is
        // guaranteed to fail with a duplicate-source error.
        out("cur-out", `Already registered as ${esc(known.source_name)}.`, "muted");
        use.textContent = "Open its dataset";
        use.dataset.registered = known.source_key;
      } else {
        out("cur-out", "");
        delete use.dataset.registered;
      }
    } catch (err) {
      out("cur-out", `The engine did not answer, so ScrapeX cannot tell whether `
        + `this site is already registered: ${esc(err.message)}`, "err");
    }
  } catch (_) {
    title.textContent = "Could not read the active tab";
    use.disabled = true;
    out("cur-out", "The browser did not report an active tab.", "err");
  }
}

async function checkPastedUrls() {
  const box = $("urls-box"), results = $("urls-results"), button = $("urls-check");
  const addresses = box.value.split(/\s+/).map((a) => a.trim()).filter(Boolean);
  out("urls-out", "");
  if (!addresses.length) {
    out("urls-out", "Paste at least one address first.", "err");
    return;
  }
  const bad = addresses.filter((a) => !/^https?:\/\/.+\..+/.test(a));
  if (bad.length) {
    out("urls-out", `Not a full address: ${esc(bad[0])}`, "err");
    return;
  }

  button.disabled = true; button.textContent = "Testing…";
  results.classList.remove("hidden");
  results.innerHTML = "";
  let reviewable = 0;
  try {
    // One at a time, deliberately: these are real requests to sites the owner
    // does not control, and the shared fetcher's politeness applies per call.
    for (const [position, address] of addresses.entries()) {
      // entries(), not indexOf: two identical pasted addresses both resolved to
      // the first position, so the counter stalled and then jumped.
      out("urls-out", `Testing ${position + 1} of ${addresses.length}…`, "muted");
      let row;
      try {
        const found = await post("/api/probe", { url: address });
        if (!found.reachable) {
          // A family guessed from an address nobody answered is not a detection.
          row = `<div class="srow"><span class="name">${esc(address)}</span>
            <span class="err hint">Did not respond. Check the address, or the site
            may block automated requests.</span></div>`;
        } else {
          reviewable += 1;
          row = `<div class="srow"><span class="name">${esc(address)}</span>
            <span class="chip ${found.implemented ? "" : "off"}">${
              esc(found.implemented ? found.family : `${found.family} — no connector`)}</span>
            <button class="link" data-pick="${esc(address)}">Review</button></div>`;
        }
      } catch (err) {
        row = `<div class="srow"><span class="name">${esc(address)}</span>
          <span class="err hint">${esc(err.message)}</span></div>`;
      }
      results.insertAdjacentHTML("beforeend", row);
      // Bind as each row lands. Binding after the whole batch meant an early
      // click on a visible button silently did nothing.
      results.querySelectorAll("[data-pick]:not([data-bound])").forEach((link) => {
        link.dataset.bound = "1";
        link.addEventListener("click", () => { showSourceDetail(link.dataset.pick); probe(); });
      });
    }
    out("urls-out", reviewable
      ? "Pick one to review and add."
      : "None of these addresses could be checked.", reviewable ? "muted" : "err");
  } finally {
    button.disabled = false; button.textContent = "Check these sites";
  }
}

const FAMILY_LABELS = {
  "shopify-json": "Shopify (products.json)", "magento-graphql": "Magento (GraphQL)",
  "woocommerce-storeapi": "WooCommerce (Store API)", "salla-html": "Salla (HTML)",
  "zid-html": "Zid (HTML)", "hybris-occ": "SAP Hybris (OCC)",
  "custom-json-api": "Custom JSON API", "static-html-table": "Static HTML table",
  "heidelberg-price-matrix": "Heidelberg (price matrix)",
  "datasheet-enrichment": "Datasheet enrichment", "TBD-probe": "Unknown — needs probing",
};

function fillFamilySelects(selected) {
  const options = Object.entries(FAMILY_LABELS)
    .map(([v, label]) => `<option value="${esc(v)}">${esc(label)}</option>`).join("");
  $("f-family").innerHTML = options;
  $("f-fallback").innerHTML = options;
  if (selected) $("f-family").value = selected;
}

function fieldError(id, message) {
  $(id).textContent = message || "";
  $(id).className = message ? "err hint" : "hint";
}

// The settings form lives inside the Add Site choice, whose panel only opens
// when that radio is checked. Every entry point goes through here, so no future
// one can fill a form the owner cannot see. Add Site is the PRICE TRACKING
// path: the other choices check an address and hand over to it.
function showSourceDetail(url) {
  const choice = $("source-addsite");
  if (choice && !choice.checked) {
    choice.checked = true;
    choice.dispatchEvent(new Event("change", { bubbles: true }));
  }
  $("source-detail").classList.remove("hidden");
  if (url !== undefined) $("url").value = url;
  $("source-detail").scrollIntoView({ block: "nearest" });
}

async function probe() {
  showSourceDetail();
  const url = $("url").value.trim();
  fieldError("err-url", "");
  out("add-out", "");
  if (!/^https?:\/\/.+\..+/.test(url)) {
    fieldError("err-url", "Enter a full URL, for example https://shop.example.com");
    return;
  }
  const btn = $("check"); btn.disabled = true; btn.textContent = "Testing…";
  $("probe-out").className = "hint muted";
  $("probe-out").textContent = "Contacting the site and inspecting what it exposes…";
  try {
    lastProbe = await post("/api/probe", { url });
    const s = lastProbe.suggested;
    const tag = lastProbe.implemented
      ? `<span class="chip">Ready: ${esc(lastProbe.family)}</span>`
      : `<span class="chip off">${esc(lastProbe.family)} — no connector yet</span>`;
    $("probe-out").className = "hint";
    $("probe-out").innerHTML =
      `<div>${tag}</div><div class="muted">${
        esc((lastProbe.evidence || []).join(" · ") || lastProbe.notes || "")}</div>` +
      (lastProbe.reachable ? "" :
        `<div class="err">The site did not respond. Check the URL, or the site may block automated requests.</div>`);

    // Prefill from what was DETECTED, so the user confirms rather than guesses.
    fillFamilySelects(s.family);
    $("f-name").value = s.source_name || "";
    $("f-name-ar").value = s.source_name_ar || "";
    $("f-key").value = s.source_key || "";
    $("f-currency").value = s.currency || "";
    $("f-region").value = s.default_region || "*";
    $("f-vat").value = s.vat_mode || "incl";
    $("f-cadence").value = s.cadence || "daily";
    $("f-kind").value = s.kind || "product_prices";
    $("f-scope").value = s.scope || "census";
    // The probe suggests a price-capture key. Re-spell it for the chosen kind:
    // a lower_snake catalogue would otherwise be handed an UPPER_SNAKE key and
    // reject it at save time, after the form looked filled in correctly.
    applyAddSystem();
    $("f-fetcher").value = s.fetcher || "http";
    $("add-form").classList.remove("hidden");

    const sample = (lastProbe.evidence || [])[0];
    $("sample").classList.toggle("hidden", !sample);
    $("sample-body").textContent = sample || "";
  } catch (e) {
    $("probe-out").className = "err hint";
    $("probe-out").textContent = "Test failed: " + e.message;
  } finally { btn.disabled = false; btn.textContent = "Test site"; }
}

// ---- which kind of capture a new site belongs to ----------------------------
// TWO CAPTURE MODELS, ONE DATABASE. They used to be two databases as well, and
// this comment said so; M5 collapsed the storage and left the models untouched,
// so the sentence had to change and the choice did not.
//
// Price capture understands products, offers, prices and the history of every
// change. Generic extraction has its own catalogue of sites, datasets and
// fields. A site is registered under one of them, and nothing here converts one
// into the other afterwards — so the choice is asked before the form is filled,
// and the form follows the answer. That is unchanged: sharing a file is not
// sharing a shape.
//
// They do not even spell a key the same way: price keys are UPPER_SNAKE
// (manifest.SourceEntry), generic keys are lower_snake (catalog_models
// .KEY_PATTERN). Validating one against the other would reject a correct key
// with a message about the wrong kind.
const SYSTEMS = {
  store: {
    label: "Add site",
    keyPattern: /^[A-Z][A-Z0-9_]{2,63}$/,
    keyHint: "UPPER_SNAKE_CASE, 3–64 characters.",
    keyError: "Use UPPER_SNAKE_CASE, 3–64 characters, starting with a letter.",
    normalizeKey: (v) => v.trim().toUpperCase(),
    note: "Prices, offers and the full history of every change.",
  },
  general: {
    label: "Add to General",
    keyPattern: /^[a-z][a-z0-9_]{1,63}$/,
    keyHint: "lower_snake_case, 2–64 characters.",
    keyError: "Use lower_snake_case, 2–64 characters, starting with a letter.",
    normalizeKey: (v) => v.trim().toLowerCase(),
    note: "Registered in the General catalogue as a draft. Its datasets and " +
          "fields are described after registering, and none of the price " +
          "settings below apply — General does not read prices.",
  },
};

function addSystem() {
  const picked = document.querySelector("input[name='add-system']:checked");
  return SYSTEMS[picked ? picked.value : "store"] ? picked.value : "store";
}

function applyAddSystem() {
  const which = addSystem();
  const spec = SYSTEMS[which];
  const price = which === "store";
  $("add-system-note").textContent = spec.note;
  const intro = $("add-price-intro");
  if (intro) intro.classList.toggle("hidden", !price);
  ["add-price-only", "add-name-ar-row"].forEach((id) => {
    const el = $(id); if (el) el.classList.toggle("hidden", !price);
  });
  $("add-btn").textContent = spec.label;
  $("err-key").textContent = spec.keyHint;
  $("err-key").className = "hint muted";
  // Re-spell a key that was prefilled for the other system rather than leave a
  // value the form is about to reject.
  const key = $("f-key");
  if (key.value.trim()) key.value = spec.normalizeKey(key.value);
}

async function addGeneralSite(key) {
  const payload = {
    site_key: key,
    display_name: $("f-name").value.trim(),
    base_url: $("url").value.trim(),
    lifecycle: "draft",
  };
  const btn = $("add-btn"); btn.disabled = true; btn.textContent = "Adding…";
  try {
    const r = await post("/api/general/catalog/sites", payload);
    out("add-out", `${icon("check", "sm")} Added ${esc(r.site_key)} to General. ` +
      `Describe its datasets in the General workspace — the price list here ` +
      `does not track it.`, "ok icon-label");
    $("url").value = ""; $("add-form").classList.add("hidden");
  } catch (e) {
    out("add-out", `${icon("close", "sm")} ${esc(e.message)}`, "err icon-label");
  } finally { btn.disabled = false; btn.textContent = SYSTEMS[addSystem()].label; }
}

async function addSite() {
  const spec = SYSTEMS[addSystem()];
  const key = spec.normalizeKey($("f-key").value);
  fieldError("err-key", ""); fieldError("err-name", "");
  if (!spec.keyPattern.test(key)) { fieldError("err-key", spec.keyError); return; }
  if (!$("f-name").value.trim()) {
    fieldError("err-name", "An English display name is required."); return;
  }
  if (addSystem() === "general") return addGeneralSite(key);
  const payload = {
    source_key: key, source_name: $("f-name").value.trim(),
    source_name_ar: $("f-name-ar").value.trim(),
    base_url: $("url").value.trim(), family: $("f-family").value,
    fetcher: $("f-fetcher").value, currency: $("f-currency").value.trim(),
    default_region: $("f-region").value.trim() || "*", vat_mode: $("f-vat").value,
    cadence: $("f-cadence").value, kind: $("f-kind").value, scope: $("f-scope").value,
    auth_required: $("f-auth").checked, active: false,
    fallback_families: [...$("f-fallback").selectedOptions].map((o) => o.value),
    identity: {
      primary: $("f-id-primary").value, fallback: $("f-id-fallback").value,
      composite_fields: $("f-id-composite").value.split(",").map((s) => s.trim()).filter(Boolean),
      canonical_url_strip_query: $("f-id-strip").checked,
      on_ambiguous: $("f-id-ambiguous").value,
    },
  };
  const btn = $("add-btn"); btn.disabled = true; btn.textContent = "Adding…";
  try {
    const r = await post("/api/sources", payload);
    await loadSources();
    showView("run");
    out("add-out", `${icon("check", "sm")} Added ${esc(r.source_key)}`, "ok icon-label");
    $("url").value = ""; $("add-form").classList.add("hidden");
  } catch (e) {
    out("add-out", `${icon("close", "sm")} ${esc(e.message)}`, "err icon-label");
  } finally { btn.disabled = false; btn.textContent = SYSTEMS[addSystem()].label; }
}

// ---- current tab ------------------------------------------------------------
async function loadCurrentSite() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const box = $("current");
  const url = tab && tab.url;
  if (!url || !/^https?:/.test(url)) { box.classList.add("hidden"); return; }
  try {
    const r = await api("/api/resolve?url=" + encodeURIComponent(url));
    box.classList.remove("hidden");
    if (r.matched && r.implemented) {
      box.innerHTML = `<div class="row"><span>You're on <b class="name content">${
        esc(r.source_name)}</b></span><button id="sel-cur" class="ghost">Select it</button></div>`;
      $("sel-cur").addEventListener("click", () => {
        state.selected.add(r.source_key); renderSites();
      });
    } else if (r.matched) {
      box.innerHTML = `<span>You're on <b class="name content">${esc(r.source_name)}</b> — <span class="chip off">not supported yet</span></span>`;
    } else {
      box.innerHTML = `<div class="row"><span class="muted">This tab isn't one of your sites.</span>
        <button id="add-cur" class="ghost">Add it</button></div>`;
      $("add-cur").addEventListener("click", () => {
        showView("source"); $("url").value = url; probe();
      });
    }
  } catch (_) { box.classList.add("hidden"); }
}

// ---- starting the engine from the panel -------------------------------------
// The reply can be "started but not yet answering" (a cold interpreter), so the
// button's promise is not the source of truth — the poll below is. The button
// only ever claims what a probe confirmed.
async function startEngineFromPanel() {
  const button = $("engine-start");
  const note = $("engine-note");
  button.disabled = true;
  button.textContent = "Starting…";
  clearRuntimeIssue();
  try {
    await startEngine();
    // Sixty seconds, not fourteen. A cold interpreter opening two databases is
    // slower than the old budget allowed, so the panel used to give up while
    // the engine was still coming up and then blame the installation.
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const engine = await probeEngine();
      if (engine.running) { await render(); return; }
      if (attempt === 8) note.textContent = "Still starting — first run of the day is slower.";
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    note.textContent = "The engine was started and is still not answering. " +
      "Check again in a moment; if it stays quiet, open Logs.";
  } catch (err) {
    // ONE branch used to print "the launcher is not installed" for every
    // failure — including a cold start that simply took longer than five
    // seconds, on a machine where everything was installed and working. Each
    // failure now says what it actually is, and none of them says "terminal":
    // the owner does not use one, so an instruction to open one is not a next
    // step, it is a dead end.
    const kind = err && err.kind;
    setRuntimeIssue(err);
    if (kind === "startup_blocked") {
      note.textContent = "The engine found a setup problem. Fix the issue shown below, then try again.";
    } else if (kind === "database_upgrade_failed") {
      note.textContent = "The database could not be upgraded. The reason is shown below.";
    } else if (kind === "absent") {
      note.textContent = "Chrome cannot find the ScrapeX helper on this machine — " +
        "open Setup below for the one-time install.";
    } else if (kind === "forbidden") {
      // The panel knows its OWN id, and the engine can write it into the
      // helper — so the repair is a request, not a reinstall. It needs the
      // engine reachable over HTTP, which is a different road from the helper
      // and is usually open when this fault happens.
      note.textContent = "The helper does not recognise this extension yet — re-linking…";
      try {
        const backend = await backendBase();
        const r = await fetch(`${backend}/api/native-host/register`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({extension_id: chrome.runtime.id}),
        });
        const body = await r.json();
        note.textContent = r.ok
          ? body.message
          : "Could not re-link automatically — open Setup below for the one-time install.";
      } catch (relinkError) {
        note.textContent = "The helper does not recognise this extension, and the " +
          "engine is not reachable to fix it — open Setup below.";
      }
    } else if (kind === "crashed") {
      note.textContent = "The helper started and stopped. Open Logs to see why — " +
        "nothing is lost, and the engine can still be started from Windows.";
    } else if (kind === "refused") {
      note.textContent = "The helper could not start the engine: " + (err.message || "") +
        " — Check again, or open Logs.";
    } else if (kind === "timeout") {
      note.textContent = "The local helper did not answer. Check Setup below, " +
        "then try again.";
    } else if (!kind) {
      note.textContent = "The engine is taking longer than usual to answer. " +
        "It may still be starting — press Check again in a few seconds.";
    } else {
      note.textContent = "The engine did not start: " + (err.message || kind) +
        " — press Check again, or open Logs.";
    }
  } finally {
    button.disabled = false;
    button.textContent = "Start engine";
  }
}

// The five ways a call to the native host can fail, each said as itself.
// transport.js tags four of them on `err.kind` (absent / forbidden / crashed /
// timeout); the fifth is a host that ANSWERED and refused, which arrives as a
// plain Error carrying the host's own detail and no kind. Collapsing them into
// one sentence is precisely how "the launcher is not installed" got printed on
// a machine where the launcher was installed and answering — see transport.js.
// Callers add their own remedy; this names only the cause, so the two controls
// cannot drift into two different diagnoses of the same failure.
function hostFailureReason(err) {
  const kind = err && err.kind;
  if (kind === "absent") return "Chrome cannot find the ScrapeX helper on this machine";
  if (kind === "forbidden") return "the helper does not recognise this extension yet";
  if (kind === "crashed") return "the helper started and stopped";
  if (kind === "timeout") return "the helper did not answer in time — it may still be starting";
  return (err && err.message) || "the helper refused without saying why";
}

// ---- start with Windows ------------------------------------------------------
// One launcher file on the machine decides it; the native host is the only
// hand that reaches it, so without the host the control honestly says why it
// cannot help instead of pretending a toggle exists.
async function renderAutostart() {
  const state = $("autostart-state");
  const toggle = $("autostart-toggle");
  const offer = $("setup-autostart");
  try {
    const s = await autostartStatus();
    state.textContent = s.installed
      ? "Start with Windows: on — the engine comes up at logon."
      : "Start with Windows: off — after a reboot the engine waits for you.";
    toggle.textContent = s.installed ? "Turn off" : "Turn on";
    toggle.classList.remove("hidden");
    // try/finally with no catch made this the quietest control in the panel:
    // SET_AUTOSTART answering ok:false (Defender blocking the Startup folder,
    // a redirected profile) rejected, the throw unwound past renderAutostart(),
    // and the label went on reading "off". The owner clicked, the button
    // flickered, and nothing happened and nothing was said.
    toggle.onclick = async () => {
      toggle.disabled = true;
      try {
        await setAutostart(!s.installed);
        renderAutostart();
      } catch (err) {
        state.textContent = "Start with Windows: could not be changed — " +
          hostFailureReason(err) + ".";
      } finally {
        toggle.disabled = false;
      }
    };
    if (offer) {
      offer.classList.toggle("hidden", s.installed);
      offer.onclick = async () => {
        offer.disabled = true;
        try {
          await setAutostart(true);
          renderAutostart();
        } catch (err) {
          state.textContent = "Start with Windows: could not be turned on — " +
            hostFailureReason(err) + ".";
        } finally {
          offer.disabled = false;
        }
      };
    }
  } catch (err) {
    // Only `absent` means "not installed". A `forbidden` (the extension was
    // reloaded from another folder, so the helper's allowlist no longer names
    // it) and a `timeout` (a cold start) were both reported here as a missing
    // install, and Setup repairs neither — it sends the owner to fix a
    // component that is working.
    state.textContent = (err && err.kind) === "absent"
      ? "Start with Windows: needs the one-time launcher install (Setup)."
      : "Start with Windows: unavailable — " + hostFailureReason(err) + ".";
    toggle.classList.add("hidden");
    if (offer) offer.classList.add("hidden");
  }
}

let autostartLoaded = false;
let autostartLoadPromise = null;

function maybeRenderAutostart() {
  const setupVisible = currentViewName() === "run" && !$("setup").classList.contains("hidden");
  const settingsVisible = currentViewName() === "settings"
    && !$("s-engine").classList.contains("hidden");
  if ((!setupVisible && !settingsVisible) || autostartLoaded) return autostartLoadPromise;
  if (!autostartLoadPromise) {
    autostartLoadPromise = renderAutostart()
      .catch(() => {})
      .finally(() => {
        autostartLoaded = true;
        autostartLoadPromise = null;
      });
  }
  return autostartLoadPromise;
}

// ---- shell ------------------------------------------------------------------
let runDestinationPromise = null;
let runDestinationLoadedFor = -1;

async function loadRunDestination() {
  if (currentViewName() !== "run" || !state.engineUp) return null;
  if (runDestinationLoadedFor === backendGeneration) return runDestinationPromise;
  if (runDestinationPromise) return runDestinationPromise;
  const generation = backendGeneration;
  runDestinationPromise = Promise.all([
    loadCurrentSite(), loadSources(), loadOutputs(), pollJob(),
  ]).then((result) => {
    if (generation === backendGeneration) runDestinationLoadedFor = generation;
    return result;
  }).catch((error) => {
    if (!panelController.signal.aborted && generation === backendGeneration) {
      const message = $("run-blocked");
      if (message) message.textContent = error && error.message
        || "Run data could not be loaded.";
    }
    return null;
  }).finally(() => {
    runDestinationPromise = null;
  });
  return runDestinationPromise;
}

async function render() {
  // Before anything is loaded or offered: a panel that cannot work half of what
  // it is showing should say so at the top of the screen, not after the click.
  // updateEngineState owns the health check, the version report, and the
  // generation guard around both, so the Engine page's Check again and this
  // whole-panel render cannot disagree about what was asked or answered.
  const engine = await updateEngineState();
  if (engine.cancelled) return engine;
  $("setup").classList.toggle("hidden", engine.running);
  runDestinationLoadedFor = -1;
  if (!engine.running) {
    clearTimeout(pollTimer);
    renderMiniplayer(null);
    $("sites").innerHTML = `<div class="srow"><span class="muted">Start the engine to see your sites.</span></div>`;
  }
  refreshRunButton();
  if (currentViewName() === "run" && engine.running) loadRunDestination();
  maybeRenderAutostart();
  return engine;
}

// ---- runtime repair, in the panel ------------------------------------------
//
// Restart and Upgrade lived only on the web Settings page. The panel is the
// application, so it was sending the owner to another surface to perform the
// most important thing they can do to a stuck engine — and the version notice
// had to name that surface in words, which is how the gap surfaced.
//
// Deliberately plain fetch and no `api()`: these two must work on the day the
// engine is otherwise unhappy, which is the only day they are wanted. api()
// throws on a non-2xx, and a 404 here is not a failure to report but a fact to
// explain — an engine that started before these endpoints existed.
const ENGINE_TOO_OLD =
  "This engine started before these actions existed, so it does not have them " +
  "yet, so it cannot be asked to replace itself from here. ScrapeX does this " +
  "on its own once the updater is installed; that work is under way.";

async function upgradeDatabaseFromPanel() {
  const note = $("runtime-note");
  const upgrade = $("runtime-upgrade");
  const actionButtons = [upgrade, $("runtime-restart"), $("runtime-check-action")]
    .filter(Boolean);
  actionButtons.forEach((button) => { button.disabled = true; });
  note.textContent = "Upgrading the database…";
  try {
    let result;
    let httpAnswered = false;
    try {
      const response = await fetch((await backendBase()) + "/api/databases/upgrade",
                                   {method: "POST"});
      if (response.status !== 404) httpAnswered = true;
      if (response.status === 404) throw Object.assign(new Error("old engine"), {kind: "old_engine"});
      if (!response.ok) {
        let detail = `The upgrade failed (HTTP ${response.status}).`;
        try { detail = (await response.json()).detail || detail; } catch (_) {}
        throw Object.assign(new Error(detail), {kind: "database_upgrade_failed"});
      }
      result = await response.json();
    } catch (httpError) {
      // If the engine is down, the native host is still alive and can perform
      // the same forward-only migration. This is the missing repair path that
      // left the owner staring at a dead Restart button.
      if (httpAnswered) throw httpError;
      result = await upgradeDatabase();
    }
    clearRuntimeIssue();
    note.textContent = result.message || "The database is up to date.";
    const engineNote = $("engine-note");
    if (engineNote) {
      engineNote.textContent = `${note.textContent} Start the engine again.`;
    }
    await render();
  } catch (err) {
    setRuntimeIssue(err);
    note.textContent = "The database was not changed. The reason is shown above.";
    const engineNote = $("engine-note");
    if (engineNote) engineNote.textContent = note.textContent;
  } finally {
    actionButtons.forEach((button) => { button.disabled = false; });
  }
}

function wireRuntimeRepair() {
  const note = $("runtime-note");
  const restart = $("runtime-restart");
  const upgrade = $("runtime-upgrade");
  if (!note || !restart || !upgrade) return;

  upgrade.addEventListener("click", upgradeDatabaseFromPanel);

  restart.addEventListener("click", async () => {
    [restart, upgrade, $("runtime-check-action")].filter(Boolean)
      .forEach((button) => { button.disabled = true; });
    note.textContent = "Restarting — the engine goes quiet for a few seconds.";
    clearRuntimeIssue();
    // Check the CURRENT build's database expectations before asking the old
    // process to leave. Without this gate, a newer process could die during
    // startup and the panel would only be able to say "30 seconds".
    try {
      await checkStartup();
    } catch (startupError) {
      const nativeFailureKinds = ["absent", "forbidden", "crashed", "timeout"];
      if (!nativeFailureKinds.includes(startupError && startupError.kind)) {
        setRuntimeIssue(startupError);
        note.textContent = "Restart was not attempted. Fix the issue shown above first.";
        [restart, upgrade, $("runtime-check-action")].filter(Boolean)
          .forEach((button) => { button.disabled = false; });
        return;
      }
      // The engine is already reachable in this path, so HTTP restart remains
      // useful even when the native helper is unavailable or slow.
      note.textContent = "Native helper unavailable — restarting through the engine.";
    }
    // A thrown fetch is the SUCCESS path — the engine exits mid-answer and the
    // socket dies. An answered fetch that is not ok is the opposite, and the
    // first version of this treated both the same: it looked only for 404 and
    // let every other status fall through to the health poll, which of course
    // succeeded, because the engine had never gone anywhere. The owner pressed
    // the button, read "The engine is back.", and nothing had happened. The
    // engine had in fact answered 500 with a precise reason, and the panel
    // threw it away.
    let refused = null;
    try {
      const asked = await fetch((await backendBase()) + "/api/engine/restart",
                                {method: "POST"});
      if (asked.status === 404) refused = ENGINE_TOO_OLD;
      else if (!asked.ok) {
        let detail = `The engine refused (HTTP ${asked.status}).`;
        try { detail = (await asked.json()).detail || detail; } catch (_) {}
        refused = detail;
      }
    } catch (_) { /* the socket died: it is going down, which is the point */ }
    if (refused) {
      const error = Object.assign(new Error(refused), {kind: "refused"});
      setRuntimeIssue(error);
      note.textContent = "Restart was refused. The reason is shown above.";
      [restart, upgrade, $("runtime-check-action")].filter(Boolean)
        .forEach((button) => { button.disabled = false; });
      return;
    }
    // Poll until it answers again, then re-render so every version and status
    // on this screen comes from the engine that is now running.
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      try {
        const probe = await fetch((await backendBase()) + "/api/engine/health",
                                  {cache: "no-store"});
        if (probe.ok) {
          clearInterval(timer);
          [restart, upgrade, $("runtime-check-action")].filter(Boolean)
            .forEach((button) => { button.disabled = false; });
          note.textContent = "The engine is back.";
          await render();
          return;
        }
      } catch (_) { /* still down, which is expected */ }
      if (attempts >= 30) {
        clearInterval(timer);
        [restart, upgrade, $("runtime-check-action")].filter(Boolean)
          .forEach((button) => { button.disabled = false; });
        // The process may have failed before it could expose /api/health. Ask
        // the native host for the same current-build preflight so a schema
        // error, missing registry, or other startup blocker is not lost.
        try {
          await checkStartup();
          const timeout = Object.assign(
            new Error("The engine did not answer in 30 seconds. It may still be starting."),
            {kind: "timeout"});
          setRuntimeIssue(timeout);
          note.textContent = "The engine has not answered in 30 seconds. Check the reason above.";
        } catch (startupError) {
          setRuntimeIssue(startupError);
          note.textContent = startupError && ["absent", "forbidden", "crashed", "timeout"]
            .includes(startupError.kind)
            ? "The engine did not confirm its restart because the local helper is unavailable."
            : "The engine stopped during startup. The reason is shown above.";
        }
      }
    }, 1000);
  });
}

let startupControlsWired = false;
let deferredControlsWired = false;

function wireStartupShell() {
  if (startupControlsWired) return;
  startupControlsWired = true;
  $("signin").addEventListener("click", async () => {
    const btn = $("signin");
    const status = $("signin-status");
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    status.textContent = "Signing in…";
    status.classList.remove("hidden");
    try {
      await loadAccount({ interactive: true });
      if (state.token) focusAccountSummary();
    } finally {
      btn.disabled = false;
      btn.setAttribute("aria-busy", "false");
      status.classList.add("hidden");
      status.textContent = "";
    }
  });
  $("signout").addEventListener("click", async () => {
    const btn = $("signout");
    btn.disabled = true;
    try {
      // BUMPED BEFORE THE AWAIT, not after. An account check started at open
      // may still be out; without this it comes back after the sign-out and
      // repaints the name and the picture of the account just signed out of.
      accountGeneration += 1;
      // REVOKE, not forget. `forgetToken` alone dropped Chrome's copy and left
      // the grant standing in the owner's Google account, so the next sign-in
      // was instant, silent, and locked to the same account and the same
      // scopes. Signing out has to mean he can come back as someone else.
      const ended = await revokeToken(state.token);
      state.token = "";
      state.account = null;
      state.accountStatus = null;
      // The row STAYS. Signing out ends a session; it does not remove an
      // account, and the person has to be able to come back through the same
      // row rather than typing the address again.
      await endCurrentAccountSession();
      renderAccount(ended.state === "local-only"
        // Said out loud rather than swallowed: this browser has forgotten the
        // account, and Google has not. The difference matters on a shared
        // machine, and the owner can finish the job himself.
        ? { tokenProblem: { state: "signed-out-locally", detail: ended.detail
              + " This browser has forgotten the account, but Google still lists"
              + " ScrapeX under your account's permissions." } }
        : {});
      focusSignin();
    } finally {
      btn.disabled = false;
    }
  });

  // A menu closes the two ways every menu closes. Both are registered once,
  // here, rather than per render: the card is rebuilt on every state change and
  // listeners attached to it would be added again each time.
  //
  // Capture phase, and only while a menu is actually open: Escape already means
  // something to the workspace menu and the rail, and the innermost open thing
  // is the one that should answer it.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    // Innermost first. The dialog is modal, so nothing behind it may answer.
    if (disconnectDialogIsOpen()) {
      event.stopPropagation();
      closeDisconnectDialog();
      return;
    }
    if (!state.openAccountMenu) return;
    event.stopPropagation();
    closeAccountMenu({ restoreFocus: true });
  }, true);
  // No focus restored on an outside click: the person is already pointing at
  // wherever they want to be, and moving focus back would fight them for it.
  document.addEventListener("click", (event) => {
    if (!state.openAccountMenu) return;
    const target = event.target;
    if (target && typeof target.closest === "function"
        && target.closest(".account-menu, .account-menu-button")) return;
    closeAccountMenu();
  });

  // ---- Manage account -----------------------------------------------------
  $("manage-account").addEventListener("click", () => showView("manage-account"));
  $("manage-account-back").addEventListener("click", () => {
    showView("profile");
    focusAccountSummary();
  });
  $("drive-review-permissions").addEventListener("click", () => {
    window.open(GOOGLE_PERMISSIONS_URL, "_blank", "noopener,noreferrer");
  });
  // The shared primitive owns open/close/aria/Escape/outside-click for the menu.
  // Wired once, here, because wire() is once-per-node and a second call on a
  // re-rendered node would leak a document listener.
  window.ScrapeXSplitButton?.wire($("drive-disconnect"), (action) => {
    if (action === "disconnect-drive") openDisconnectDialog();
  });
  $("disconnect-cancel").addEventListener("click", () => closeDisconnectDialog());
  $("disconnect-confirm").addEventListener("click", () => { disconnectDrive(); });
  // The veil itself, not the card: a click that lands on the card must not
  // dismiss the question the card is asking.
  $("disconnect-veil").addEventListener("click", (event) => {
    if (event.target === $("disconnect-veil")) closeDisconnectDialog();
  });
  document.addEventListener("keydown", trapDisconnectFocus, true);

  setGoogleButtonScheme();
  window.addEventListener("scrapexappearancechange", () => {
    setGoogleButtonScheme();
  });

  const tabs = [...document.querySelectorAll("nav.side-rail button[data-view]")];
  tabs.forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $("workspace-toggle").addEventListener("click", () => {
    const open = $("workspace-toggle").getAttribute("aria-expanded") === "true";
    if (open) closeWorkspaceMenu(true);
    else openWorkspaceMenu();
  });
  $("workspace-close").addEventListener("click", () => closeWorkspaceMenu(true));
  $("workspace-backdrop").addEventListener("click", () => closeWorkspaceMenu(true));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeWorkspaceMenu(true);
    }
  });
  document.querySelector("nav.side-rail").addEventListener("keydown", (event) => {
    if (!event.target.matches("button[data-view]")) return;
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const current = tabs.indexOf(document.activeElement);
    let next = current < 0 ? 0 : current;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else next = (current + (event.key === "ArrowDown" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next].focus();
    showView(tabs[next].dataset.view);
  });
  window.addEventListener("resize", () => {
    const active = document.querySelector('nav.side-rail button[aria-current="page"]');
    positionRailIndicator(active, true);
  });
  document.addEventListener("visibilitychange", handlePanelVisibility);

  // The fallback is local and complete, so navigation is usable without an
  // Engine or a network request. The remote contract may refine it after paint.
  renderWorkspaceNavigation(WORKSPACE_NAVIGATION_FALLBACK);
  // The opening view must be ENTERED through showView like every other one.
  // Relying on the markup's initial visibility skipped its loader entirely, so
  // the default screen sat at "Reading the active tab…" until the owner
  // navigated away and back — and the screenshot harness hid it by clicking a
  // nav button before capturing.
  // The panel opens on Welcome. Before we know who is asking there is nothing
  // true to put on a page — no account, no backup, no lease — so the first
  // screen asks that one question and shows nothing else.
  showView("profile", false);
  document.documentElement.dataset.shellInteractive = "true";
  markStartup("shell-interactive");
}

// ---- Google, driven from here -----------------------------------------------
//
// The owner's ruling of 2026-08-11: the engine fetches and saves locally, and
// the extension owns every Google operation. drive.js and sheets.js do the
// talking; this is the part that knows about buttons.
//
// THE TOKEN IS READ PER CLICK, NEVER CAPTURED. state.token is cleared from five
// places — a refused profile read, a 401, sign-out — so a handler that closed
// over it once would keep using a token the owner has already revoked. Reading
// state.token at the moment of use is the same discipline drive.js applies by
// taking it as an argument rather than holding it.

function driveProgress(fraction) {
  const bar = $("drive-progress");
  const fill = $("drive-progress-fill");
  if (!bar || !fill) return;
  if (fraction === null) {
    bar.classList.add("hidden");
    return;
  }
  const percent = Math.max(0, Math.min(100, Math.round(fraction * 100)));
  bar.classList.remove("hidden");
  bar.setAttribute("aria-valuenow", String(percent));
  fill.style.width = percent + "%";
}

/** One shape for all three buttons: disable, run, report, re-enable. */
async function runGoogleAction(button, working, action) {
  if (!state.token) {
    out("drive-msg", "Sign in with Google first — the Account button at the " +
                     "top of the panel.", "err");
    return;
  }
  const buttons = ["drive-backup", "drive-restore", "sheet-create"];
  buttons.forEach((id) => { if ($(id)) $(id).disabled = true; });
  out("drive-msg", esc(working), "");
  try {
    const said = await action(state.token);
    out("drive-msg", esc(said), "ok");
  } catch (error) {
    // The message is the module's own sentence — "Sign in again from the
    // panel", "ScrapeX can only open spreadsheets it created itself" — because
    // those name the next action. Replacing them with a generic failure here
    // would throw away the only part the owner can act on.
    out("drive-msg", esc((error && error.message) || "Something went wrong."), "err");
  } finally {
    driveProgress(null);
    buttons.forEach((id) => { if ($(id)) $(id).disabled = false; });
  }
}

async function backUpToDrive(token) {
  // The engine builds the bundle; the panel uploads it. Neither half sees the
  // other's secret: the engine never gets the token, the panel never opens the
  // database.
  out("drive-msg", "Building the bundle…", "");
  const built = await api("/api/bundle", { method: "POST" });
  const base = await backendBase();
  const archive = await (await fetch(base + "/api/bundle/archive")).blob();
  // The 4 MB a browser can read on its own, carried beside the 36 MB archive
  // only an engine can open. Fetched here rather than inside drive.js: that
  // module talks to Google and nothing else, and giving it a second opinion
  // about the engine's address is how one boundary becomes two.
  const panelPack = built.panel_pack
    ? await (await fetch(base + "/api/bundle/panel-pack")).blob()
    : null;

  const stored = await backUp(token, {
    archive, name: built.name, panelPack,
    manifest: built, bundleFormat: built.bundle_format,
    onProgress: ({sent, total}) => driveProgress(total ? sent / total : 0),
  });
  const pruned = stored.pruned.length
    ? ` ${stored.pruned.length} older backup${stored.pruned.length === 1 ? "" : "s"} removed.`
    : "";
  return `Backed up ${fmtMegabytes(archive.size)} to Drive.${pruned}`;
}

async function fetchFromDrive(token) {
  const {archive, pointer} = await fetchLatest(token, {
    onProgress: ({received, total}) => driveProgress(total ? received / total : 0),
  });
  // DOWNLOADED, NOT RESTORED. Putting this archive over the warehouse is a
  // destructive act on the owner's only copy, and it belongs behind its own
  // confirmed control rather than at the end of a fetch they asked for. What
  // this proves today is that the backup is real, complete and readable.
  return `Fetched ${fmtMegabytes(archive.size)} written ${pointer.created_at || "at an unrecorded time"}` +
         ` by engine ${pointer.engine_version || "unknown"}. It is not installed — this only checks it is there.`;
}

//: Where the chooser lives. It cannot be a page in this extension: Google
//: Picker loads a remote script and MV3 forbids that, so it is served from the
//: owner's own site and answers through background.js's onMessageExternal.
const PICKER_PAGE = "https://muhammadbayoumi.github.io/mbiXsite/scrapex-picker.html";

/**
 * Let the owner point ScrapeX at a spreadsheet it did not create.
 *
 * `drive.file` reaches two kinds of file: ones this app made, and ones the
 * owner hands it through the Picker. This is the second kind, and it is the
 * only way to widen that scope without asking Google for a sensitive one.
 *
 * THE TOKEN GOES IN THE FRAGMENT. Browsers do not send a fragment to the
 * server and do not log it, and the page erases it from the address bar on
 * load. It is used to draw the Picker and for nothing else — what comes back
 * is an id, and the panel opens the file with its own token.
 */
async function pickExistingSpreadsheet() {
  if (!state.token) {
    out("drive-msg", "Sign in with Google first — the Account button at the "
                     + "top of the panel.", "err");
    return;
  }
  await chrome.storage.session.remove("scrapexPickedSpreadsheet");
  const url = `${PICKER_PAGE}#token=${encodeURIComponent(state.token)}`
    + `&ext=${encodeURIComponent(chrome.runtime.id)}`;
  chrome.tabs.create({url});
  out("drive-msg", "Choose a spreadsheet in the tab that just opened, then come "
                   + "back here.", "");

  // POLLED, NOT PUSHED. A side panel can be closed and reopened while the owner
  // is choosing, and a message sent to a panel that is not there is lost —
  // which is why background.js writes the choice to session storage instead of
  // forwarding it. This reads that, and stops after two minutes rather than
  // polling for the life of the browser.
  const deadline = Date.now() + 120000;
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const held = await chrome.storage.session.get("scrapexPickedSpreadsheet");
    const picked = held.scrapexPickedSpreadsheet;
    if (picked) {
      await chrome.storage.session.remove("scrapexPickedSpreadsheet");
      if (!picked.fileId) {
        out("drive-msg", "Nothing was chosen.", "");
        return;
      }
      try {
        const sheet = await openChosen(state.token, picked.fileId);
        const link = $("sheet-link");
        if (link) {
          link.innerHTML = `<a class="link" href="${esc(sheet.url)}" `
            + `target="_blank" rel="noreferrer noopener">${esc(sheet.name)}</a>`;
        }
        out("drive-msg", `ScrapeX can now write to "${esc(sheet.name)}".`, "ok");
      } catch (error) {
        out("drive-msg", esc((error && error.message) || "That file could not be opened."), "err");
      }
      return;
    }
    if (Date.now() > deadline) {
      out("drive-msg", "No spreadsheet was chosen. Press the button again when "
                       + "you are ready.", "");
      return;
    }
  }
}

async function createSpreadsheet(token) {
  const folder = await ensureFolder(token, SHEET_FOLDER);
  const sheet = await ensureSpreadsheet(token, DEFAULT_WORKBOOK, {folder});
  const link = $("sheet-link");
  if (link) {
    link.innerHTML = `<a class="link" href="${esc(sheet.url)}" target="_blank" ` +
                     `rel="noreferrer noopener">${esc(sheet.name)}</a>`;
  }
  return sheet.created
    ? `Created "${sheet.name}" in ${SHEET_FOLDER}.`
    : `"${sheet.name}" already exists — the link is below.`;
}

function wireGoogleControls() {
  const actions = [
    ["drive-backup", "Backing up…", backUpToDrive],
    ["drive-restore", "Looking for the latest backup…", fetchFromDrive],
    ["sheet-create", "Creating the spreadsheet…", createSpreadsheet],
  ];
  // Wired apart from the three above because it does NOT follow their shape:
  // it opens a tab and waits on the owner rather than running a request, so it
  // must not disable the row or claim to be working while nothing is.
  const choose = $("sheet-choose");
  if (choose) choose.addEventListener("click", () => pickExistingSpreadsheet());
  for (const [id, working, action] of actions) {
    const button = $(id);
    if (button) {
      button.addEventListener("click", () =>
        runGoogleAction(button, working, action));
    }
  }
}

function wireDeferredControls() {
  if (deferredControlsWired) return;
  deferredControlsWired = true;
  wireGoogleControls();
  // `[data-sect]` is load-bearing: other buttons borrow the `.sect` LOOK (the
  // Advanced-settings toggle does), and without the attribute filter they get
  // this handler too and blow up on a null target.
  document.querySelectorAll("button.sect[data-sect]").forEach((b) =>
    b.addEventListener("click", () => {
      const body = $(b.dataset.sect);
      const open = body.classList.toggle("hidden");
      b.setAttribute("aria-expanded", String(!open));
      if (!open && b.dataset.sect === "s-engine") maybeRenderAutostart();
    }));

  wireRuntimeRepair();
  wireSourceColumns();
  $("setup-recheck").addEventListener("click", render);
  $("engine-start").addEventListener("click", startEngineFromPanel);
  $("runtime-check-action").addEventListener("click", async () => {
    const button = $("runtime-check-action");
    if (button.dataset.action === "recheck") {
      $("diag-out").textContent = "";
      await render();
      return;
    }
    button.disabled = true;
    $("diag-out").textContent = "Running diagnostics…";
    const engine = await probeEngine();
    setStatus(engine);
    // A protocol mismatch OUTRANKS "reachable": an engine that answers while
    // speaking an older command surface produces 404s and missing fields, and
    // those read as broken features rather than as a stale engine. Say which
    // side is behind — the same sentence the native path has always given.
    $("diag-out").textContent = engine.protocolMismatch
      ? `The panel and the ScrapeX engine speak different protocol versions ` +
        `(panel ${engine.clientProtocol}, engine ${engine.engineProtocol}). ` +
        `Update whichever is older.`
      : engine.running
      ? `Engine reachable at ${await backendBase()} · version ${engine.version || "unknown"}`
      // Not "start it with a command": the owner does not use a terminal, so
      // naming one is a dead end dressed as help. The button above this one
      // starts it, and Windows starts it at logon.
      : `No engine at ${await backendBase()}. Press Start engine above — it also ` +
        `starts by itself when you sign in to Windows.`;
    button.disabled = false;
  });

  $("site-search").addEventListener("input", (e) => {
    state.filter = e.target.value; renderSites();
  });
  $("source-manager-filter").addEventListener("input", (e) => {
    state.sourceFilter = e.target.value;
    renderSourceManager();
  });
  $("source-manager-add").addEventListener("click", () => {
    showView("source");
    const choice = $("source-addsite");
    choice.checked = true;
    choice.dispatchEvent(new Event("change", {bubbles: true}));
    requestAnimationFrame(() => {
      $("source-detail").scrollIntoView({
        behavior: reduceMotion.matches ? "auto" : "smooth", block: "start",
      });
      $("url").focus({preventScroll: true});
    });
  });
  $("source-edit-back").addEventListener("click", () => {
    const sourceKey = state.editingSourceKey;
    showView("sources");
    requestAnimationFrame(() =>
      document.querySelector(`[data-edit-source="${CSS.escape(sourceKey || "")}"]`)
        ?.focus({preventScroll: true}));
  });
  $("source-edit-robots-look").addEventListener("click", lookAtRobots);
  $("source-edit-robots").addEventListener("change", () => {
    const choice = $("source-edit-robots").value;
    $("source-edit-robots-custom").classList.toggle("hidden", choice !== "custom");
    renderRobotsChoice({robots: choice, robots_custom: {
      enforce_disallow: $("source-edit-robots-enforce").checked,
      crawl_delay_s: $("source-edit-robots-delay").value.trim() || null,
    }});
  });
  $("source-edit-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveSourceEditor();
  });
  $("source-edit-rename").addEventListener("click", renameSourceKey);
  $("source-edit-remove").addEventListener("click", stopTrackingSource);
  $("source-edit-wipe").addEventListener("click", wipeSourceData);
  $("select-all").addEventListener("click", () => {
    // What is VISIBLE, not what exists: with a search term typed, taking the
    // whole catalogue left the count contradicting the list on screen.
    visibleSources().filter((s) => s.implemented)
      .forEach((s) => state.selected.add(s.source_key));
    renderSites();
  });
  $("clear-sel").addEventListener("click", () => { state.selected.clear(); renderSites(); });

  $("adv-toggle").addEventListener("click", (e) => {
    const open = $("adv").classList.toggle("hidden");
    e.target.setAttribute("aria-expanded", String(!open));
  });
  $("add-btn").addEventListener("click", addSite);
  document.querySelectorAll("input[name='add-system']").forEach((radio) => {
    radio.addEventListener("change", applyAddSystem);
  });
  applyAddSystem();
  $("check").addEventListener("click", probe);
  $("cur-use").addEventListener("click", () => {
    showSourceDetail($("cur-url").textContent.trim());
    probe();
  });
  $("urls-check").addEventListener("click", checkPastedUrls);
  // Re-read the active tab whenever the owner touches Current Page. `change`
  // alone is unreachable: the radio ships already checked, and a radio only
  // fires change when it BECOMES checked. `click` on the label fires either way.
  document.getElementById("source-current").addEventListener("change", loadCurrentPage);
  document.querySelector('label[for="source-current"]')
    .addEventListener("click", loadCurrentPage);
  $("url").addEventListener("keydown", (e) => { if (e.key === "Enter") probe(); });

  runModeSelectUi = setupRunModeSelect();
  $("run-mode").addEventListener("change", refreshMode);
  $("run").addEventListener("click", startRun);

  // ONE split button (the shared component the dataset Export uses), no more
  // "Pause auto-scroll" — the primary copies what is on screen, the menu
  // downloads the engine's complete record. Same actions from either place.
  window.ScrapeXSplitButton.wire($("activity").querySelector(".split-button"),
    (action) => {
      if (action === "copy") {
        navigator.clipboard.writeText(
          state.logs.map((l) => `${l.logged_at || ""} ${l.level} ${l.message}`).join("\n"));
      } else if (action === "download") {
        // No ?limit: the download is the FULL log, every entry, which is the
        // whole reason it is a separate action from Copy visible.
        if (state.jobRef) openTab(`/api/jobs/${state.jobRef}/logs`);
      }
    });

  $("mini-view").addEventListener("click", () => {
    showView("run"); $("activity").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("mini-pause").addEventListener("click", (e) => controlJob(e.target.dataset.control || "pause"));
  $("mini-cancel").addEventListener("click", () => controlJob("cancel"));

  $("open-workbook").addEventListener("click", () => openTab("/data"));

  $("save").addEventListener("click", async () => {
    await setBackend($("backend").value);
    const moved = activateBackend(await getBackend());
    await Promise.allSettled([
      window.ScrapeXAppearance?.connect(moved),
      window.ScrapeXTime?.connect(moved),
      adoptUiContract(),
    ]);
    await render();
  });
  $("how").addEventListener("click", () =>
    chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html") }));
  $("open-browse").addEventListener("click", () => openTab("/"));
  // The workspace opens with the Storage section already expanded, so the link
  // lands on what it promised rather than on a wall of closed rows.
  $("open-storage").addEventListener("click", () => openTab("/settings#s-storage"));

  // Crawl pace and engine control. Loaded when the section is OPENED rather
  // than at boot: the panel must not spend a request on a page the owner may
  // never expand, and a stale value is worse than a late one.
  $("crawl-save").addEventListener("click", saveCrawlSettings);
  $("engine-restart").addEventListener("click", restartEngineFromPanel);
  $("crawl_honour_delay").addEventListener("change", crawlPaceEffect);
  $("crawl_min_interval_s").addEventListener("input", crawlPaceEffect);
  $("crawl_parallel_sources").addEventListener("input", crawlParallelEffect);
  document.querySelector('[data-sect="s-crawl"]')
    .addEventListener("click", () => {
      if (!$("s-crawl").classList.contains("hidden")) loadCrawlSettings();
    });

  financeCurrencySelectUi = setupFinanceConverterSelect({
    selectId: "finance-converter-currency",
    triggerId: "finance-converter-currency-trigger",
    listId: "finance-converter-currency-list",
    labelPrefix: "Source currency",
  });
  financeTargetSelectUi = setupFinanceConverterSelect({
    selectId: "finance-converter-target",
    triggerId: "finance-converter-target-trigger",
    listId: "finance-converter-target-list",
    labelPrefix: "Target currency",
  });
  $("finance-save").addEventListener("click", saveGoogleFinance);
  $("google_finance_auto_refresh").addEventListener("change", renderFinanceSaveState);
  $("google_finance_refresh_hours").addEventListener("input", renderFinanceSaveState);
  $("finance-refresh").addEventListener("click", refreshGoogleFinance);
  $("finance-converter-amount").addEventListener("input", updateFinanceConverter);
  $("finance-converter-currency").addEventListener("change", updateFinanceConverter);
  $("finance-dataset").addEventListener("click", () => openTab("/data/google-finance"));
  // The formatter has already read the small local preference. The expensive
  // option list is built only when Settings is entered.
  window.ScrapeXTime.subscribe(() => {
    if (timeZoneControlReady) timeZoneEffect();
    if (state.financeStatus) renderGoogleFinanceStatus(state.financeStatus);
  });

  refreshMode();
  // The Engine page's overflow menu. Deferred with the rest: it is a menu on a
  // destination nobody is looking at when the panel opens, and none of the
  // three things it offers exists before the shell is on screen.
  bindEngineOverflowMenu();
}

function scheduleNonCriticalStartup(backendPromise) {
  afterIdle(async () => {
    try {
      const backend = await backendPromise;
      await Promise.allSettled([
        window.ScrapeXAppearance?.connect(backend),
        // The zone travels the same road as appearance, after the locally saved
        // preference has already painted the document.
        window.ScrapeXTime?.connect(backend),
        adoptUiContract(),
      ]);
      // AFTER the shell is settled, never during it. A crawl that was already
      // running has to be found (issue 161), and /api/jobs is destination data
      // that the startup path is forbidden to touch — three tests hold that
      // rule and they are right to. Idle time is where the two fit together.
      await reattachToRunningJob();
    } catch (_) {}
  });
}

async function init() {
  wireStartupShell();
  const paintOpportunity = await afterNextPaint({signal: panelController.signal});
  if (paintOpportunity.source === "cancelled" || panelController.signal.aborted) return;
  // FCP remains the authoritative browser paint measurement. This mark records
  // that startup yielded a bounded renderer opportunity before remote work.
  markStartup("shell-post-opportunity", {
    source: paintOpportunity.source,
    visibilityState: document.visibilityState,
  });

  // These start in the same turn and settle independently. The Engine only
  // waits for its backend address; it never waits for Chrome/Google account work.
  const backendPromise = backendBase().then((backend) => {
    $("backend").value = backend;
    return backend;
  });
  const accountPromise = loadAccount();
  // `render()` is what settles state.engineUp, so the reattach hangs off it
  // rather than racing it. A crawl that was already running is adopted here,
  // on whatever view the panel opened — see reattachToRunningJob (issue 161).
  const enginePromise = backendPromise.then(() => render());
  Promise.allSettled([accountPromise, enginePromise]).then(() => {
    markStartup("fully-settled", {
      account: state.token ? "signed-in" : "signed-out",
      engine: state.engineState,
    });
  });

  wireDeferredControls();
  scheduleNonCriticalStartup(backendPromise);
}

function closePanelWork() {
  accountGeneration += 1;
  engineGeneration += 1;
  clearTimeout(pollTimer);
  pollTimer = null;
  panelController.abort();
  backendController.abort();
}

window.addEventListener("pagehide", closePanelWork, {once: true});
window.addEventListener("beforeunload", closePanelWork, {once: true});
// START NOW IF THE DOCUMENT IS ALREADY PARSED, and only wait if it is not.
//
// This waited unconditionally on DOMContentLoaded, which was right while the
// module was loaded from a <script> tag in the markup. It is not any more:
// boot-app.js appends this module when `load` fires, so DOMContentLoaded is long
// past by the time this line runs and the listener would never be called. The
// panel painted immediately and then did nothing at all -- every button dead,
// no engine check, no account -- which is how the owner found it.
//
// `readyState` is the question that has an answer in both worlds: "loading"
// means the event is still coming, anything else means it has been and gone.
function startPanel() {
  init().catch((error) => {
    markStartup("startup-failed", {message: error && error.message || "unknown"});
    console.error("ScrapeX panel startup failed", error);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startPanel, {once: true});
} else {
  startPanel();
}
