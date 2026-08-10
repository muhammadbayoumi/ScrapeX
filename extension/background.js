// The manifest preconfigures one global panel at app.html. Keep the runtime
// configuration explicit too, but preserve the action-click user gesture by
// making sidePanel.open() the first Chrome API call in that handler.
const SIDE_PANEL_PATH = "app.html";
const STARTUP_EVENT = "scrapex-side-panel-startup-event";
const STARTUP_TRACE_KEY = "scrapexSidePanelStartupTrace";

let activeStartupTrace = null;
let traceSequence = 0;
const configurationEvents = [];

function epochNow() {
  return globalThis.performance.timeOrigin + globalThis.performance.now();
}

function traceEntry(name, detail = {}, at = epochNow()) {
  return {name, at, detail};
}

function publishTrace() {
  if (!activeStartupTrace) return;
  try {
    chrome.storage.session.set({
      [STARTUP_TRACE_KEY]: structuredClone(activeStartupTrace),
    }).catch((error) => console.warn("sidePanel trace:", error));
  } catch (error) {
    console.warn("sidePanel trace:", error);
  }
}

function recordConfiguration(name, detail = {}) {
  const entry = traceEntry(name, detail);
  configurationEvents.push(entry);
  if (activeStartupTrace) {
    activeStartupTrace.events.push(entry);
    publishTrace();
  }
  console.info("ScrapeX Side Panel startup", entry);
}

function startTrace(name, detail) {
  activeStartupTrace = {
    id: `${Date.now()}-${++traceSequence}`,
    events: [...configurationEvents, traceEntry(name, detail)],
  };
}

function recordStartup(name, detail = {}, at = epochNow(), publish = true) {
  if (!activeStartupTrace) {
    activeStartupTrace = {
      id: `hostless-${Date.now()}-${++traceSequence}`,
      events: [...configurationEvents],
    };
  }
  const entry = traceEntry(name, detail, at);
  activeStartupTrace.events.push(entry);
  if (publish) publishTrace();
  console.info("ScrapeX Side Panel startup", entry);
}

async function configureSidePanel() {
  recordConfiguration("set-panel-behavior-request", {
    openPanelOnActionClick: false,
  });
  try {
    await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: false});
    recordConfiguration("set-panel-behavior-resolved");
  } catch (error) {
    recordConfiguration("set-panel-behavior-failed", {
      message: error?.message || String(error),
    });
  }

  recordConfiguration("set-panel-options-request", {
    enabled: true, path: SIDE_PANEL_PATH,
  });
  try {
    await chrome.sidePanel.setOptions({enabled: true, path: SIDE_PANEL_PATH});
    recordConfiguration("set-panel-options-resolved");
  } catch (error) {
    recordConfiguration("set-panel-options-failed", {
      message: error?.message || String(error),
    });
  }
}

// Start configuration whenever Chrome starts this service worker. The manifest
// already supplies the same global path, so the action handler never waits and
// never loses the user gesture sidePanel.open() requires.
configureSidePanel();

chrome.action.onClicked.addListener((tab) => {
  const windowId = tab?.windowId;
  startTrace("action-click", {tabId: tab?.id ?? null, windowId: windowId ?? null});
  if (!Number.isInteger(windowId)) {
    recordStartup("side-panel-open-failed", {message: "The action has no window."});
    return;
  }

  const options = {windowId};
  recordStartup("side-panel-open-request", options, epochNow(), false);
  try {
    const opening = chrome.sidePanel.open(options);
    // Persist only after open() has consumed the action's user gesture. The
    // timestamps above were captured synchronously without another Chrome API.
    publishTrace();
    opening.then(
      () => recordStartup("side-panel-open-resolved", options),
      (error) => recordStartup("side-panel-open-failed", {
        ...options, message: error?.message || String(error),
      }),
    );
  } catch (error) {
    recordStartup("side-panel-open-failed", {
      ...options, message: error?.message || String(error),
    });
  }
});

// Chrome 141+ exposes the host event. It is additional evidence, not a startup
// dependency, so older supported Chrome versions simply omit this mark.
chrome.sidePanel.onOpened?.addListener((info) => {
  recordStartup("side-panel-on-opened", info);
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== STARTUP_EVENT || !message.event?.name) return;
  recordStartup(message.event.name, {
    ...message.event.detail,
    documentUrl: sender?.url || "",
  }, message.event.at);
});

// On first install, open the onboarding page so the user immediately learns the
// ScrapeX engine (local Python) must be installed for the tool to work.
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    chrome.tabs.create({url: chrome.runtime.getURL("onboarding.html")});
  }
});
