"use strict";
// ScrapeX Harvester popup. The extension is only a FACE: it triggers the local
// scrapex backend (which owns harvest.db + the connectors) and links to its
// browse UI. It never parses site data itself. Backend URL is configurable so
// each team member can point at their own local scrapex.

const DEFAULT_BACKEND = "http://127.0.0.1:8000";
const $ = (id) => document.getElementById(id);

async function getBackend() {
  const { backend } = await chrome.storage.local.get("backend");
  return (backend || DEFAULT_BACKEND).replace(/\/+$/, "");
}

async function api(path, options) {
  const backend = await getBackend();
  const res = await fetch(backend + path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function setStatus(ok, text) {
  $("dot").className = "dot " + (ok ? "on" : "off");
  $("status").textContent = text;
}

function showResult(html, cls) {
  $("result").innerHTML = `<span class="${cls || ""}">${html}</span>`;
}

async function activeTabUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab ? tab.url : "";
}

async function capture(sourceKey, btn) {
  const label = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "…جارٍ"; }
  showResult("جارٍ الالتقاط — قد يأخذ لحظات…", "muted");
  try {
    const r = await api("/api/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_key: sourceKey }),
    });
    showResult(
      `✓ ${sourceKey}: ${r.observations} سعر جديد، ${r.duplicates} مكرر، ` +
      `${r.products} منتج جديد (${r.requests} طلب، ${r.errors} خطأ)`, "ok");
    await loadSources();
  } catch (e) {
    showResult("✗ " + e.message, "err");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = label; }
  }
}

async function loadCurrentSite() {
  const url = await activeTabUrl();
  const box = $("current");
  if (!url || !/^https?:/.test(url)) { box.hidden = true; return; }
  try {
    const r = await api("/api/resolve?url=" + encodeURIComponent(url));
    if (!r.matched) {
      box.hidden = false;
      box.className = "card";
      box.innerHTML = `<span class="muted">هذا الموقع ليس مصدرًا معروفًا بعد.</span>`;
      return;
    }
    box.hidden = false;
    box.className = "card hi";
    if (r.implemented) {
      box.innerHTML =
        `<div class="row"><span>أنت على <b>${r.source_name}</b></span>` +
        `<button id="cap-current">التقاط هذا المصدر</button></div>`;
      $("cap-current").addEventListener("click", (e) => capture(r.source_key, e.target));
    } else {
      box.innerHTML =
        `<span>أنت على <b>${r.source_name}</b> — ` +
        `<span class="chip off">connector لسه ما اتبناش</span></span>`;
    }
  } catch (_) { box.hidden = true; }
}

async function loadSources() {
  const list = $("list");
  try {
    const { sources } = await api("/api/sources");
    list.innerHTML = "";
    for (const s of sources) {
      const row = document.createElement("div");
      row.className = "srow";
      const right = s.implemented
        ? `<button data-key="${s.source_key}">التقاط</button>`
        : `<span class="chip off">قريبًا</span>`;
      row.innerHTML =
        `<span>${s.source_name} <span class="n">${s.observations.toLocaleString()} سعر</span></span>` +
        `<span>${right}</span>`;
      list.appendChild(row);
    }
    list.querySelectorAll("button[data-key]").forEach((b) =>
      b.addEventListener("click", () => capture(b.dataset.key, b)));
  } catch (e) {
    list.innerHTML = `<span class="err">تعذّر الاتصال بالخادم. شغّل: <code>scrapex ui</code></span>`;
  }
}

async function refreshHealth() {
  try {
    await api("/api/health");
    setStatus(true, "متصل");
    return true;
  } catch (_) {
    setStatus(false, "غير متصل");
    return false;
  }
}

async function init() {
  $("backend").value = await getBackend();
  $("toggle-settings").addEventListener("click", () => {
    const b = $("settings-body"); b.hidden = !b.hidden;
  });
  $("save").addEventListener("click", async () => {
    await chrome.storage.local.set({ backend: $("backend").value.trim() || DEFAULT_BACKEND });
    location.reload();
  });
  $("browse").addEventListener("click", async () => {
    chrome.tabs.create({ url: await getBackend() });
  });

  const connected = await refreshHealth();
  if (connected) {
    await Promise.all([loadCurrentSite(), loadSources()]);
  } else {
    $("list").innerHTML = `<span class="err">تعذّر الاتصال. شغّل على جهازك: <code>scrapex ui</code></span>`;
  }
}

document.addEventListener("DOMContentLoaded", init);
