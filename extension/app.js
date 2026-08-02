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
import { autostartStatus, setAutostart, startEngine } from "./transport.js";
import { capabilityProblem, deployedFrom, installedVersion, CAPABILITY_REPORTING_SINCE, isOlder } from "./version.js";

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ICON_SPRITE = "icons/material-icons.svg";
const icon = (name, className = "") =>
  `<svg class="sx-icon ${className}" aria-hidden="true">` +
  `<use href="${ICON_SPRITE}#${name}"></use></svg>`;

async function api(path, options) {
  const res = await fetch((await getBackend()) + path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
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
async function openTab(path) { chrome.tabs.create({ url: (await getBackend()) + path }); }

// ---- state ----------------------------------------------------------------
const state = {
  sources: [], selected: new Set(), filter: "", sourceFilter: "",
  editingSourceKey: null,
  job: null, jobRef: null, logs: [], logSignature: null, logAtBottom: true,
  engineUp: false,
  // The two versions and what the engine says it deploys. `versionReport` is
  // null for an engine too old to publish one, which is NOT the same as an
  // engine that has not been asked yet — every reader of it checks
  // state.engineVersion too, so silence is never read as a refusal.
  installedVersion: "", engineVersion: "", versionReport: null,
};

// ---- views ----------------------------------------------------------------
const VIEWS = [
  "source", "run", "data", "sources", "source-edit", "appearance", "settings",
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

function showView(name, animate = true) {
  const current = VIEWS.find((view) => !$(`view-${view}`).classList.contains("hidden"));
  const navigationName = name === "source-edit" ? "sources" : name;
  runModeSelectUi?.close();
  closeWorkspaceMenu();
  for (const v of VIEWS) $(`view-${v}`).classList.toggle("hidden", v !== name);
  const activeButton = document.querySelector(
    `nav.tabs button[data-view="${navigationName}"]`);
  document.querySelectorAll("nav.tabs button[data-view]").forEach((b) => {
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
  if (name === "settings") { loadSchedules(); loadStorage(); }
  if (name === "source") loadCurrentPage();
}

// ---- runtime status --------------------------------------------------------
const COMPONENTS = [
  ["Core service", (e) => (e.running ? "Running" : "Stopped")],
  ["Python runtime", (e) => (e.running ? "Ready" : "Unknown")],
  ["HTTP fetcher", (e) => (e.running ? "Ready" : "Unknown")],
  // The engine creates and owns both databases; the panel only reports them. A
  // reachable engine sitting on an unusable database read as healthy from here.
  ["Databases", (e) => {
    if (!e.running) return "Unknown";
    if (!e.databases) return "Ready";
    return e.databases.ok ? "Healthy" : `Needs attention — ${e.databases.detail}`;
  }],
  ["Browser automation", () => "Optional"],
];

function renderRuntime(engine) {
  $("components").innerHTML = COMPONENTS.map(([label, fn]) => {
    const value = fn(engine);
    return `<div class="kv"><span>${esc(label)}</span><span class="muted">${esc(value)}</span></div>`;
  }).join("");
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
  state.engineVersion = engine.version || "";
  $("dot").className = "dot " + (engine.running ? "on" : "off");
  // The word carries the state; the dot only reinforces it. "v0.2.0" here is
  // the ENGINE's — said in full in About, where the extension's own version now
  // sits beside it, because one number under no label was the original defect.
  $("estat-text").textContent = engine.running
    ? `Ready${engine.version ? " · engine v" + engine.version : ""}`
    : "Setup required";
  $("about-version").textContent = engine.version || "—";
  renderSchemaLag(engine.schema_lag);
  renderRuntime(engine);
}

// ---- versions ---------------------------------------------------------------
// TWO versions, updated by TWO mechanisms that nothing keeps in step: the engine
// arrives with the repository, the extension only when someone presses Reload in
// chrome://extensions. They drift apart every working day, and until now the
// panel showed one of them and never its own — so a feature the installed
// extension could not reach looked exactly like a feature that was never built.
// That is issue 32 §1.2/§1.3, and it is what cost two sessions.

async function loadVersions(engine) {
  const installed = installedVersion();
  state.installedVersion = installed;
  $("about-extension-version").textContent = installed || "unknown";
  if (!engine.reachable) {
    // Nothing to compare against. The setup card already says the engine is
    // down; inventing a version verdict on top of it would be noise.
    state.versionReport = null;
    renderVersionNotice(engine);
    return;
  }
  const query = installed ? `?extension_version=${encodeURIComponent(installed)}` : "";
  try {
    state.versionReport = await api(`/api/version${query}`);
  } catch (_) {
    // A 404 here is not a broken feature: it is an engine built before version
    // reporting existed. Recorded as null and SAID as such below, never
    // silently treated as "everything is fine".
    state.versionReport = null;
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
    const asked = await fetch((await getBackend()) + "/api/engine/restart",
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
function renderGoogleFinanceStatus(status) {
  const tracked = status.tracked_currencies || [];
  $("finance-currencies").textContent = tracked.length ? tracked.join(", ") : "None yet";
  $("finance-last-check").textContent = status.last_checked || "Never";
  $("finance-latest-market").textContent = status.latest_market_at || "No rates yet";
  $("finance-rows").textContent = `${Number(status.rows || 0).toLocaleString()} rate rows`;
}

async function loadGoogleFinance() {
  try {
    const status = await api("/api/rates/google-finance");
    $("google_finance_auto_refresh").checked = Boolean(status.automatic);
    $("google_finance_refresh_hours").value = String(status.refresh_hours ?? 6);
    renderGoogleFinanceStatus(status);
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
  try {
    await post("/api/settings", {
      google_finance_auto_refresh: $("google_finance_auto_refresh").checked,
      google_finance_refresh_hours: hours,
    });
    await loadGoogleFinance();
  } catch (err) {
    out("finance-msg", "not saved: " + esc(err.message), "err");
    return;
  }
  out("finance-msg", "saved - the new cadence applies immediately", "ok");
}

async function refreshGoogleFinance() {
  const button = $("finance-refresh");
  button.disabled = true;
  const oldLabel = button.textContent;
  button.textContent = "Updating...";
  out("finance-msg", "requesting the latest rates...");
  try {
    const result = await post("/api/rates/google-finance/refresh", {});
    renderGoogleFinanceStatus(result);
    const warning = (result.warnings || []).length
      ? ` ${result.warnings.length} warning(s): ${esc(result.warnings.join("; "))}` : "";
    out("finance-msg", esc(result.detail || "Update complete.") + warning,
        warning ? "" : "ok");
  } catch (err) {
    out("finance-msg", "update failed: " + esc(err.message), "err");
  } finally {
    button.disabled = false;
    button.textContent = oldLabel;
  }
}

// ---- display time zone (spec 33) -------------------------------------------
//
// The panel owns the CONTROL; timezone.js owns the preference, the sharing and
// the one formatter. Everything here is the sentence around the select: what
// the current choice looks like on a real time, and whether it reached the
// engine — because a preference that silently failed to save would come back
// on the next crawl and look like the panel had forgotten it.

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

function renderSourceEditor(source) {
  state.editingSourceKey = source.source_key;
  $("source-edit-identity").innerHTML = sourceIdentity(
    source, false, Number(source.observations || 0).toLocaleString());

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
    };
    const changed = Object.entries(edits).some(
      ([field, value]) => String(source[field] ?? "") !== String(value));
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
  renderWorkspaceNavigation(WORKSPACE_NAVIGATION_FALLBACK);
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

function refreshRunButton() {
  syncModeChoices();
  const n = state.selected.size;
  $("sel-count").textContent = `${n} selected`;
  let blocked = "";
  if (!state.engineUp) blocked = "The engine is not running — start it to run a crawl.";
  else if (!n) blocked = "Select at least one site above.";
  else if (state.job) blocked = "A job is already running. It will queue behind it.";
  $("run").disabled = !state.engineUp || !n;
  $("run-blocked").textContent = blocked;
}

async function startRun() {
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

// ---- ONE formatter each (the DRY the owner asked for) ----------------------
// A count with thousands separators. Every number the panel shows goes through
// here, so 1030 reads as "1,030" everywhere and never as a bare 1030 in one
// place and grouped in another.
function fmtCount(n) {
  return Number(n || 0).toLocaleString();
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

async function pollJob() {
  clearTimeout(pollTimer);
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
    pollTimer = setTimeout(pollJob, POLL_MS);
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
        <span class="dataset-card-open">${icon("chevron-right", "sm")}</span>
        <div><div class="dataset-identity-line">${sourceIdentity(
          s, false, fmtCount(s.observations))}</div>
          <div class="n">${fmtCount(s.products)} products</div>
          <div class="n muted">${freshnessLine(s)}</div></div>
      </article>`).join("");
    box.querySelectorAll("[data-open]").forEach((card) => {
      card.addEventListener("click", () => openDataset(card.dataset.open));
      card.addEventListener("keydown", (event) => {
        if (!["Enter", " "].includes(event.key)) return;
        event.preventDefault();
        openDataset(card.dataset.open);
      });
    });
  } catch (_) {
    box.innerHTML = `<div class="card"><span class="err">Couldn't reach the engine.</span></div>`;
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
    const mb = (n) => `${(Number(n || 0) / 1048576).toFixed(1)} MB`;
    // Health is a WORD here too, never a colour: the panel has no room for a
    // legend, so the state has to be readable on its own.
    $("storage-info").innerHTML = `
      <div class="kv"><span>Database</span><span class="tech">${esc(s.path)}</span></div>
      <div class="kv"><span>Size</span><span>${esc(mb(s.sizes.db_bytes))}</span></div>
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
    // The probe suggests a MarketLens key. Re-spell it for the chosen system:
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

// ---- which system a new site belongs to -------------------------------------
// MarketLens and General are two systems with two databases, not two modes of
// one. MarketLens understands products, offers, prices and the history of every
// change; General is the generic extractor with its own catalogue of sites,
// datasets and fields. A site is registered in one of them, and nothing here
// converts one into the other afterwards — so the choice is asked before the
// form is filled, and the form follows the answer.
//
// They do not even spell a key the same way: MarketLens keys are UPPER_SNAKE
// (manifest.SourceEntry), General keys are lower_snake (catalog_models
// .KEY_PATTERN). Validating one against the other would reject a correct key
// with a message about the wrong system.
const SYSTEMS = {
  store: {
    label: "Add site",
    keyPattern: /^[A-Z][A-Z0-9_]{2,63}$/,
    keyHint: "UPPER_SNAKE_CASE, 3–64 characters.",
    keyError: "Use UPPER_SNAKE_CASE, 3–64 characters, starting with a letter.",
    normalizeKey: (v) => v.trim().toUpperCase(),
    note: "Prices, offers and the full history of every change. Written to the " +
          "MarketLens database.",
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
  try {
    await startEngine();
    // Sixty seconds, not fourteen. A cold interpreter opening two databases is
    // slower than the old budget allowed, so the panel used to give up while
    // the engine was still coming up and then blame the installation.
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const engine = await checkEngine();
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
    if (kind === "absent") {
      note.textContent = "Chrome cannot find the ScrapeX helper on this machine — " +
        "open Setup below for the one-time install.";
    } else if (kind === "forbidden") {
      // The panel knows its OWN id, and the engine can write it into the
      // helper — so the repair is a request, not a reinstall. It needs the
      // engine reachable over HTTP, which is a different road from the helper
      // and is usually open when this fault happens.
      note.textContent = "The helper does not recognise this extension yet — re-linking…";
      try {
        const backend = await getBackend();
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
    } else if (kind === "timeout" || !kind) {
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

// ---- shell ------------------------------------------------------------------
async function render() {
  const engine = await checkEngine();
  setStatus(engine);
  // Before anything is loaded or offered: a panel that cannot work half of what
  // it is showing should say so at the top of the screen, not after the click.
  await loadVersions(engine);
  $("setup").classList.toggle("hidden", engine.running);
  if (engine.running) {
    await Promise.all([loadCurrentSite(), loadSources(), loadOutputs(), pollJob()]);
  } else {
    clearTimeout(pollTimer);
    renderMiniplayer(null);
    $("sites").innerHTML = `<div class="srow"><span class="muted">Start the engine to see your sites.</span></div>`;
  }
  refreshRunButton();
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
  "yet. Start it from the Windows Startup folder (Win+R, shell:startup, " +
  "double-click ScrapeX Engine.vbs), or sign out and in.";

function wireRuntimeRepair() {
  const note = $("runtime-note");
  const restart = $("runtime-restart");
  const upgrade = $("runtime-upgrade");
  if (!note || !restart || !upgrade) return;

  upgrade.addEventListener("click", async () => {
    upgrade.disabled = true;
    note.textContent = "Upgrading the database…";
    try {
      const res = await fetch((await getBackend()) + "/api/databases/upgrade",
                              {method: "POST"});
      if (res.status === 404) { note.textContent = ENGINE_TOO_OLD; return; }
      const body = await res.json();
      note.textContent = res.ok ? body.message
        : (body.detail || "The upgrade did not run.");
    } catch (err) {
      note.textContent = "Could not reach the engine: " + err.message;
    } finally { upgrade.disabled = false; }
  });

  restart.addEventListener("click", async () => {
    restart.disabled = true;
    note.textContent = "Restarting — the engine goes quiet for a few seconds.";
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
      const asked = await fetch((await getBackend()) + "/api/engine/restart",
                                {method: "POST"});
      if (asked.status === 404) refused = ENGINE_TOO_OLD;
      else if (!asked.ok) {
        let detail = `The engine refused (HTTP ${asked.status}).`;
        try { detail = (await asked.json()).detail || detail; } catch (_) {}
        refused = detail;
      }
    } catch (_) { /* the socket died: it is going down, which is the point */ }
    if (refused) { note.textContent = refused; restart.disabled = false; return; }
    // Poll until it answers again, then re-render so every version and status
    // on this screen comes from the engine that is now running.
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      try {
        const probe = await fetch((await getBackend()) + "/api/marketlens/health",
                                  {cache: "no-store"});
        if (probe.ok) {
          clearInterval(timer);
          restart.disabled = false;
          note.textContent = "The engine is back.";
          await render();
          return;
        }
      } catch (_) { /* still down, which is expected */ }
      if (attempts >= 30) {
        clearInterval(timer);
        restart.disabled = false;
        note.textContent = "The engine has not answered in 30 seconds. " +
          "Start it from the Windows Startup folder, or sign out and in.";
      }
    }, 1000);
  });
}

async function init() {
  const backend = await getBackend();
  $("backend").value = backend;
  window.ScrapeXAppearance?.connect(backend);
  // The zone travels the same road as the appearance, so the panel and the
  // workspace can never be showing two different times (§6.9).
  window.ScrapeXTime?.connect(backend);
  renderAutostart();
  adoptUiContract();

  const tabs = [...document.querySelectorAll("nav.tabs button[data-view]")];
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
  document.querySelector("nav.tabs").addEventListener("keydown", (event) => {
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
    const active = document.querySelector('nav.tabs button[aria-current="page"]');
    positionRailIndicator(active, true);
  });
  // `[data-sect]` is load-bearing: other buttons borrow the `.sect` LOOK (the
  // Advanced-settings toggle does), and without the attribute filter they get
  // this handler too and blow up on a null target.
  document.querySelectorAll("button.sect[data-sect]").forEach((b) =>
    b.addEventListener("click", () => {
      const body = $(b.dataset.sect);
      const open = body.classList.toggle("hidden");
      b.setAttribute("aria-expanded", String(!open));
    }));

  wireRuntimeRepair();
  $("recheck").addEventListener("click", render);
  $("setup-recheck").addEventListener("click", render);
  $("engine-start").addEventListener("click", startEngineFromPanel);
  $("diagnostics").addEventListener("click", async () => {
    $("diag-out").textContent = "Running diagnostics…";
    const engine = await checkEngine();
    // A protocol mismatch OUTRANKS "reachable": an engine that answers while
    // speaking an older command surface produces 404s and missing fields, and
    // those read as broken features rather than as a stale engine. Say which
    // side is behind — the same sentence the native path has always given.
    $("diag-out").textContent = engine.protocolMismatch
      ? `The panel and the ScrapeX engine speak different protocol versions ` +
        `(panel ${engine.clientProtocol}, engine ${engine.engineProtocol}). ` +
        `Update whichever is older.`
      : engine.running
      ? `Engine reachable at ${await getBackend()} · version ${engine.version || "unknown"}`
      // Not "start it with a command": the owner does not use a terminal, so
      // naming one is a dead end dressed as help. The button above this one
      // starts it, and Windows starts it at logon.
      : `No engine at ${await getBackend()}. Press Start engine above — it also ` +
        `starts by itself when you sign in to Windows.`;
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
    const moved = await getBackend();
    window.ScrapeXAppearance?.connect(moved);
    window.ScrapeXTime?.connect(moved);
    render();
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

  $("finance-save").addEventListener("click", saveGoogleFinance);
  $("finance-refresh").addEventListener("click", refreshGoogleFinance);
  $("finance-dataset").addEventListener("click", () => openTab("/data/google-finance"));
  document.querySelector('[data-sect="s-finance"]')
    .addEventListener("click", () => {
      if (!$("s-finance").classList.contains("hidden")) loadGoogleFinance();
    });
  // The zone needs no loader: timezone.js has already read the stored
  // preference and filled the select before this runs. Choosing one re-renders
  // every visible time from the data already on screen — nothing is refetched
  // and nothing stored is touched (§6.10) — so all that is left is to keep the
  // example sentence honest and say whether the engine took the choice.
  timeZoneEffect();
  window.ScrapeXTime.subscribe(() => timeZoneEffect());
  $("ui_time_zone").addEventListener("change", () => {
    timeZoneEffect();
    out("timezone-msg", "saving…");
    confirmTimeZoneShared();
  });

  refreshMode();
  // The opening view must be ENTERED through showView like every other one.
  // Relying on the markup's initial visibility skipped its loader entirely, so
  // the default screen sat at "Reading the active tab…" until the owner
  // navigated away and back — and the screenshot harness hid it by clicking a
  // nav button before capturing.
  showView("source", false);
  await render();
}

document.addEventListener("DOMContentLoaded", init);
