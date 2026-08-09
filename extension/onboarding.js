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
  // WIRING FIRST, DECORATION SECOND — and the order is a bug fix, not a style.
  //
  // This function used to open by writing a command line into `#cmd-host`. When
  // the steps were rewritten for the downloaded engine that span was deleted
  // from the page and this file was not, so `getElementById` returned null.
  // Inside an async function called from a DOMContentLoaded listener that
  // TypeError surfaces as a silent unhandled rejection: no console error the
  // user would ever see, no visible change, and every statement after it
  // skipped. The page rendered perfectly and Start engine, Check again and Open
  // ScrapeX were all dead — a page one missing element had quietly disarmed.
  //
  // Attaching the listeners before touching any optional element means the
  // worst a missing span can now do is leave a label blank.
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
      // NO STEP NUMBERS AND NO TERMINAL. This used to read "run step 3 first, or
      // start the engine from a terminal (step 4)" — step 3 is now "Come back
      // here", there is no step 4, and the terminal command it pointed at was
      // deleted. Naming a step that does not exist is worse than naming none.
      note.textContent = "Chrome cannot start the engine on its own yet. " +
        "Run scrapex-engine.exe yourself — step 2 above — and leave its " +
        "window open; this page will notice it.";
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

  $("backend-url").textContent = await getBackend();
  await poll();
  // Auto-detect the moment the user starts the engine — no manual refresh.
  timer = setInterval(poll, 3000);
}

document.addEventListener("DOMContentLoaded", init);
