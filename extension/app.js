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

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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

function out(id, html, cls) {
  $(id).innerHTML = html ? `<span class="${cls || ""}">${html}</span>` : "";
}
async function openTab(path) { chrome.tabs.create({ url: (await getBackend()) + path }); }

// ---- state ----------------------------------------------------------------
const state = {
  sources: [], selected: new Set(), filter: "",
  job: null, jobRef: null, autoscroll: true, logs: [],
  dataset: null, cursor: 0, records: [], engineUp: false,
};

// ---- views ----------------------------------------------------------------
const VIEWS = ["source", "run", "data", "settings"];

function showView(name) {
  for (const v of VIEWS) $(`view-${v}`).classList.toggle("hidden", v !== name);
  document.querySelectorAll("nav.tabs button").forEach((b) => {
    if (b.dataset.view === name) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  if (name === "data") loadDatasets();
  if (name === "settings") { loadSchedules(); loadStorage(); }
  if (name === "source") loadCurrentPage();
}

// ---- runtime status --------------------------------------------------------
const COMPONENTS = [
  ["Core service", (e) => (e.running ? "Running" : "Stopped")],
  ["Python runtime", (e) => (e.running ? "Ready" : "Unknown")],
  ["HTTP fetcher", (e) => (e.running ? "Ready" : "Unknown")],
  ["Browser automation", () => "Optional"],
];

function renderRuntime(engine) {
  $("components").innerHTML = COMPONENTS.map(([label, fn]) => {
    const value = fn(engine);
    return `<div class="kv"><span>${esc(label)}</span><span class="muted">${esc(value)}</span></div>`;
  }).join("");
}

function setStatus(engine) {
  state.engineUp = engine.running;
  $("dot").className = "dot " + (engine.running ? "on" : "off");
  // The word carries the state; the dot only reinforces it.
  $("estat-text").textContent = engine.running
    ? `Ready${engine.version ? " · v" + engine.version : ""}`
    : "Setup required";
  $("about-version").textContent = engine.version || "—";
  renderRuntime(engine);
}

// ---- sites -----------------------------------------------------------------
function hostOf(url) { try { return new URL(url).host; } catch (_) { return url || ""; } }

function visibleSources() {
  const term = state.filter.trim().toLowerCase();
  return state.sources.filter((s) =>
    !term || s.source_name.toLowerCase().includes(term) ||
    (s.base_url || "").toLowerCase().includes(term));
}

function renderSites() {
  const box = $("sites");
  const shown = visibleSources();

  if (!state.sources.length) {
    box.innerHTML = `<div class="srow"><span class="muted">No sites yet. Open Source to register your first one.</span></div>`;
  } else if (!shown.length) {
    box.innerHTML = `<div class="srow"><span class="muted">No site matches “${esc(state.filter)}”.</span></div>`;
  } else {
    // `host (Display Name)` per spec 10: the host is technical (forced LTR), the
    // display name is data (picks its own direction).
    box.innerHTML = shown.map((s) => {
      const ready = s.implemented;
      const checked = state.selected.has(s.source_key) ? "checked" : "";
      const reason = ready ? "" :
        `<span class="chip off" title="No connector has shipped for this platform yet">Not supported yet</span>`;
      return `<div class="srow ${ready ? "" : "off"}">
        <label>
          <input type="checkbox" data-key="${esc(s.source_key)}" ${checked} ${ready ? "" : "disabled"}>
          <span>
            <span class="tech">${esc(hostOf(s.base_url))}</span>
            <span class="name muted"> (${esc(s.source_name)})</span>
            <span class="n" style="display:block">${Number(s.observations || 0).toLocaleString()} prices${
              s.changes ? " · " + esc(s.changes) : ""}</span>
          </span>
        </label>${reason}
      </div>`;
    }).join("");
    box.querySelectorAll("input[data-key]").forEach((cb) =>
      cb.addEventListener("change", () => {
        cb.checked ? state.selected.add(cb.dataset.key) : state.selected.delete(cb.dataset.key);
        renderSelected();
        refreshRunButton();
      }));
  }
  renderSelected();
  refreshRunButton();
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
    loadChangeSummaries();
  } catch (_) {
    $("sites").innerHTML =
      `<div class="srow"><span class="err">Couldn&#39;t reach the engine.</span></div>`;
  }
}

const CHANGE_LABELS = {
  new: "new", price_increase: "price up", price_decrease: "price down",
  field_updated: "updated", unavailable: "unavailable", returned: "back", removed: "removed",
};

async function loadChangeSummaries() {
  for (const s of state.sources) {
    if (!s.observations) continue;
    try {
      const { summary } = await api("/api/changes?limit=1&source_key=" +
        encodeURIComponent(s.source_key));
      const line = Object.entries(summary || {}).filter(([, n]) => n > 0)
        .map(([k, n]) => `${n} ${CHANGE_LABELS[k] || k}`).join(" · ");
      if (line) { s.changes = line; renderSites(); }
    } catch (_) { /* a missing summary is not worth surfacing */ }
  }
}

// ---- run -------------------------------------------------------------------
const MODES = {
  update: ["Update existing data", "Collect current data and record what changed.", null],
  initial_crawl: ["Initial crawl", "Collect and save these sites for the first time.", null],
  full_rebuild: ["Full rebuild", "Archive the current dataset, then crawl again.",
    "Full rebuild archives the current catalogue and takes a database backup first. Nothing is deleted, and the backup is your rollback."],
};

function refreshMode() {
  const [label, help, warn] = MODES[$("run-mode").value];
  $("mode-help").textContent = help;
  $("mode-warn").className = warn ? "card warn" : "hidden";
  $("mode-warn").innerHTML = warn ? `<span class="muted">${esc(warn)}</span>` : "";
  $("run").textContent = `Start ${label.toLowerCase()}`;
  refreshRunButton();
}

function refreshRunButton() {
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

function fmtElapsed(startedAt) {
  if (!startedAt) return "";
  const secs = Math.max(0, Math.round((Date.now() - Date.parse(startedAt)) / 1000));
  const m = Math.floor(secs / 60);
  return m ? `${m}m ${secs % 60}s` : `${secs}s`;
}

function renderActivity(job) {
  const box = $("activity");
  if (!job) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  $("act-elapsed").textContent = fmtElapsed(job.started_at);
  $("act-state").innerHTML =
    `<span>${esc(job.status.replace(/_/g, " "))}${job.stage ? " · " + esc(job.stage) : ""}</span>` +
    `<span class="content">${esc(job.current_source_key || "—")}</span>`;
  $("act-bar").style.width = job.progress.percent + "%";
  const c = job.counters || {};
  const rows = [
    ["Sites done", `${job.progress.done} / ${job.progress.total}`],
    ["New prices", c.observations || 0],
    ["Unchanged", c.duplicates || 0],
    ["New products", c.products || 0],
    ["Requests", c.requests || 0],
    ["Errors", c.errors || 0],
  ];
  $("act-counters").innerHTML = rows.map(([k, v]) =>
    `<div class="kv"><span>${esc(k)}</span><span class="tech">${esc(v)}</span></div>`).join("");
}

function renderLogs(entries) {
  state.logs = entries;
  $("logbox").innerHTML = entries.map((e) =>
    `<div class="logline"><span class="lvl muted">${esc(e.level)}</span>` +
    `<span class="content">${esc(e.message)}</span></div>`).join("") ||
    `<span class="muted">No log entries yet.</span>`;
  if (state.autoscroll) $("logbox").scrollTop = $("logbox").scrollHeight;
}

function renderMiniplayer(job, queued) {
  const box = $("miniplayer");
  if (!job) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const scope = job.source_keys.length > 1 ? `${job.source_keys.length} sites` : job.source_keys[0];
  $("mini-title").textContent = `${scope} — ${job.status.replace(/_/g, " ")}`;
  $("mini-pct").textContent = `${job.progress.percent}% (${job.progress.done}/${job.progress.total})`;
  $("mini-bar").style.width = job.progress.percent + "%";
  const c = job.counters || {};
  const bits = [];
  if (job.current_source_key) bits.push(`now: ${job.current_source_key}`);
  if (c.observations != null) bits.push(`${c.observations} new prices`);
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
    try { renderLogs((await api(`/api/jobs/${job.job_ref}/logs?limit=200`)).entries); }
    catch (_) {}
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
      renderLogs((await api(`/api/jobs/${state.jobRef}/logs?limit=200`)).entries);
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
      <div class="card">
        <div class="row">
          <span><b class="name content">${esc(s.source_name)}</b>
            <div class="n">${Number(s.observations).toLocaleString()} prices · ${
              Number(s.products || 0).toLocaleString()} products</div>
            <div class="n">${esc(s.changes || "no recorded changes yet")}</div></span>
          <button data-open="${esc(s.source_key)}">Open</button>
        </div>
      </div>`).join("");
    box.querySelectorAll("button[data-open]").forEach((b) =>
      b.addEventListener("click", () => openDataset(b.dataset.open)));
  } catch (_) {
    box.innerHTML = `<div class="card"><span class="err">Couldn't reach the engine.</span></div>`;
  }
}

function openDataset(key) {
  state.dataset = key; state.cursor = 0; state.records = [];
  $("datasets").classList.add("hidden");
  $("dataset-detail").classList.remove("hidden");
  loadRecords(true);
}

async function loadRecords(reset) {
  if (reset) { state.cursor = 0; state.records = []; $("records").innerHTML =
    `<div class="skeleton"></div><div class="skeleton"></div>`; }
  const params = new URLSearchParams({
    source_key: state.dataset, cursor: String(state.cursor), limit: "25",
    q: $("rec-search").value.trim(), availability: $("rec-avail").value,
  });
  try {
    const page = await api("/api/records?" + params);
    state.records = state.records.concat(page.records);
    if (!state.records.length) {
      $("records").innerHTML = `<div class="card"><span class="muted">No records match.</span></div>`;
    } else {
      // Compact cards, a few fields — the panel is not a table (spec 20).
      // Compact cards, a few fields — the panel is not a table (spec 20).
      // Country is shown whenever present: for a commodity source it is the ONLY
      // thing distinguishing one row from the next.
      $("records").innerHTML = state.records.map((r) => `
        <div class="card">
          <div class="name content">${esc(r.name || "—")}</div>
          ${r.region ? `<div class="kv"><span class="muted">Country</span>
            <span>${esc(r.region_name || r.region)} <span class="tech">${esc(r.region)}</span></span></div>` : ""}
          <div class="kv"><span class="muted">Price</span>
            <span class="tech">${esc(r.effective_price)} ${esc(r.currency)}</span></div>
          <div class="kv"><span class="muted">Status</span>
            <span>${esc(String(r.availability).replace(/_/g, " "))}</span></div>
          ${r.sku ? `<div class="kv"><span class="muted">SKU</span><span class="tech">${esc(r.sku)}</span></div>` : ""}
        </div>`).join("");
    }
    state.cursor = page.next_cursor ?? state.cursor;
    $("more-records").classList.toggle("hidden", page.next_cursor === null);
  } catch (e) {
    $("records").innerHTML = `<div class="card"><span class="err">${esc(e.message)}</span></div>`;
  }
}

// ---- settings --------------------------------------------------------------
async function loadSchedules() {
  try {
    const d = await api("/api/schedules");
    $("sched-note").textContent = d.note;
    $("schedules").innerHTML = d.schedules.length
      ? d.schedules.map((s) => `<div class="kv"><span class="content">${esc(s.source_key)}</span>
          <span class="muted">${esc(s.frequency)}${
            s.next_run_at ? " · next " + esc(s.next_run_at) : ""}</span></div>`).join("")
      : `<span class="muted">No schedules yet.</span>`;
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
        <span><b class="name content">${esc(s.source_name)}</b>
          <span class="n" style="display:block">${esc(hostOf(s.base_url))}</span></span>
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
    $("outputs").innerHTML = outputs.map((o) => {
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
          `<span class="hint muted" style="display:block">${esc(o.blocker || o.detail)}</span>`}
          ${setup}</span>
        <span class="chip ${o.ready ? "" : "off"}">${esc(state_)}</span>
      </div>`;
    }).join("");
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
    $("f-key").value = s.source_key || "";
    $("f-currency").value = s.currency || "";
    $("f-region").value = s.default_region || "*";
    $("f-vat").value = s.vat_mode || "incl";
    $("f-cadence").value = s.cadence || "daily";
    $("f-kind").value = s.kind || "product_prices";
    $("f-scope").value = s.scope || "census";
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

async function addSite() {
  const key = $("f-key").value.trim().toUpperCase();
  fieldError("err-key", ""); fieldError("err-name", "");
  if (!/^[A-Z][A-Z0-9_]{2,63}$/.test(key)) {
    fieldError("err-key", "Use UPPER_SNAKE_CASE, 3–64 characters, starting with a letter.");
    return;
  }
  if (!$("f-name").value.trim()) {
    fieldError("err-name", "A display name is required."); return;
  }
  const payload = {
    source_key: key, source_name: $("f-name").value.trim(),
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
    out("cap-out", `✓ Added ${esc(r.source_key)}`, "ok");
    $("url").value = ""; $("add-form").classList.add("hidden");
  } catch (e) {
    out("add-out", "✗ " + esc(e.message), "err");
  } finally { btn.disabled = false; btn.textContent = "Add site"; }
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

// ---- shell ------------------------------------------------------------------
async function render() {
  const engine = await checkEngine();
  setStatus(engine);
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

async function init() {
  $("backend").value = await getBackend();

  document.querySelectorAll("nav.tabs button").forEach((b) =>
    b.addEventListener("click", () => showView(b.dataset.view)));
  // `[data-sect]` is load-bearing: other buttons borrow the `.sect` LOOK (the
  // Advanced-settings toggle does), and without the attribute filter they get
  // this handler too and blow up on a null target.
  document.querySelectorAll("button.sect[data-sect]").forEach((b) =>
    b.addEventListener("click", () => {
      const body = $(b.dataset.sect);
      const open = body.classList.toggle("hidden");
      b.setAttribute("aria-expanded", String(!open));
    }));

  $("estat").addEventListener("click", () => {
    const open = $("runtime-details").classList.toggle("hidden");
    $("estat").setAttribute("aria-expanded", String(!open));
    $("chev").classList.toggle("open", !open);
  });
  $("recheck").addEventListener("click", render);
  $("setup-recheck").addEventListener("click", render);
  $("diagnostics").addEventListener("click", async () => {
    $("diag-out").textContent = "Running diagnostics…";
    const engine = await checkEngine();
    $("diag-out").textContent = engine.running
      ? `Engine reachable at ${await getBackend()} · version ${engine.version || "unknown"}`
      : `No engine at ${await getBackend()}. Start it with: scrapex ui`;
  });

  $("site-search").addEventListener("input", (e) => {
    state.filter = e.target.value; renderSites();
  });
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

  $("run-mode").addEventListener("change", refreshMode);
  $("run").addEventListener("click", startRun);

  $("autoscroll").addEventListener("click", (e) => {
    state.autoscroll = !state.autoscroll;
    e.target.textContent = state.autoscroll ? "Pause auto-scroll" : "Resume auto-scroll";
  });
  $("copy-logs").addEventListener("click", () =>
    navigator.clipboard.writeText(state.logs.map((l) => `${l.logged_at} ${l.level} ${l.message}`).join("\n")));
  $("dl-logs").addEventListener("click", async () =>
    state.jobRef && openTab(`/api/jobs/${state.jobRef}/logs?limit=200`));

  $("mini-view").addEventListener("click", () => {
    showView("run"); $("activity").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("mini-pause").addEventListener("click", (e) => controlJob(e.target.dataset.control || "pause"));
  $("mini-cancel").addEventListener("click", () => controlJob("cancel"));

  $("data-back").addEventListener("click", () => {
    $("dataset-detail").classList.add("hidden"); $("datasets").classList.remove("hidden");
  });
  $("open-workspace").addEventListener("click", () => openTab("/source/" + state.dataset));
  $("more-records").addEventListener("click", () => loadRecords(false));
  let searchTimer = null;
  $("rec-search").addEventListener("input", () => {
    clearTimeout(searchTimer); searchTimer = setTimeout(() => loadRecords(true), 250);
  });
  $("rec-avail").addEventListener("change", () => loadRecords(true));

  $("save").addEventListener("click", async () => { await setBackend($("backend").value); render(); });
  $("how").addEventListener("click", () =>
    chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html") }));
  $("open-browse").addEventListener("click", () => openTab("/"));
  $("open-manage").addEventListener("click", () => openTab("/manage"));
  // The workspace opens with the Storage section already expanded, so the link
  // lands on what it promised rather than on a wall of closed rows.
  $("open-storage").addEventListener("click", () => openTab("/settings#s-storage"));

  refreshMode();
  // The opening view must be ENTERED through showView like every other one.
  // Relying on the markup's initial visibility skipped its loader entirely, so
  // the default screen sat at "Reading the active tab…" until the owner
  // navigated away and back — and the screenshot harness hid it by clicking a
  // nav button before capturing.
  showView("source");
  await render();
}

document.addEventListener("DOMContentLoaded", init);
