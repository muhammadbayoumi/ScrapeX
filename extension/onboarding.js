import { checkEngine, getBackend } from "./engine.js";

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
  await poll();
  // Auto-detect the moment the user starts the engine — no manual refresh.
  timer = setInterval(poll, 3000);

  $("check").addEventListener("click", poll);
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
