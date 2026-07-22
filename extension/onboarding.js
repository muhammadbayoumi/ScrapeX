import { checkEngine, getBackend } from "./engine.js";
import { startEngine } from "./transport.js";

const $ = (id) => document.getElementById(id);
let timer = null;

function render(state) {
  const box = $("status");
  const text = $("status-text");
  const sub = $("status-sub");
  if (state.running) {
    box.className = "status up";
    text.textContent = "ScrapeX engine detected";
    sub.textContent = "";
    document.body.classList.add("connected");
    $("ver").textContent = state.version ? `v${state.version}` : "";
    if (timer) { clearInterval(timer); timer = null; }
  } else {
    box.className = "status down";
    text.textContent = "ScrapeX engine not installed / not running";
    sub.textContent = "Follow the steps below";
    document.body.classList.remove("connected");
  }
}

async function poll() {
  render(await checkEngine());
}

async function init() {
  $("backend-url").textContent = await getBackend();
  // The register-the-launcher command must name THIS extension's id — Chrome
  // only lets a native host talk to the ids its manifest lists, and an id
  // the user has to go hunting for is an id that gets typed wrong.
  $("cmd-host").textContent =
    `python -m scrapex.cli install-native-host --extension-id ${chrome.runtime.id}`;
  await poll();
  // Auto-detect the moment the user starts the engine — no manual refresh.
  timer = setInterval(poll, 3000);

  $("check").addEventListener("click", poll);
  $("start-engine").addEventListener("click", async () => {
    const button = $("start-engine");
    const note = $("start-note");
    button.disabled = true;
    note.textContent = "Starting…";
    try {
      await startEngine();
      // The poll above flips the page to "connected" the moment the engine
      // answers; this note only covers the gap until it does.
      note.textContent = "Engine starting — this page will notice it by itself.";
    } catch (err) {
      note.textContent = "The launcher is not registered yet — run step 3 first, " +
        "or start the engine from a terminal (step 4).";
    } finally {
      button.disabled = false;
    }
  });
  $("open-app").addEventListener("click", async () => {
    try {
      const win = await chrome.windows.getCurrent();
      await chrome.sidePanel.open({ windowId: win.id }); // the panel is the control UI
    } catch (_) {
      chrome.tabs.create({ url: chrome.runtime.getURL("app.html") });
    }
  });
  document.querySelectorAll("[data-copy]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await navigator.clipboard.writeText($(btn.dataset.copy).textContent.trim());
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = "Copy"), 1200);
    })
  );
}

document.addEventListener("DOMContentLoaded", init);
