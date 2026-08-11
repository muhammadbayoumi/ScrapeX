importScripts("startup-trace.js");

// OPENING THE SIDE PANEL, AND THE COMPETING WRITE THAT WAS REMOVED.
//
// The rejected build called, at service-worker startup and without awaiting it:
//
//     await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: false});
//     await chrome.sidePanel.setOptions({enabled: true, path: "app.html"});
//
// On a COLD click there is no service worker yet, so Chrome starts one to
// deliver action.onClicked. Top-level code runs first, the two configuration
// calls go out, and the click handler's sidePanel.open() runs while the second
// one is still in flight — because setOptions sits behind an await. setOptions
// carries a `path`, and setting a path is what tells Chrome which document the
// panel shows. It therefore lands AFTER the panel has already been opened, on a
// panel that is already showing that same document.
//
// Neither call was needed. `side_panel.default_path` in the manifest already
// registers the global path, before any click, for every window. So the two
// calls added nothing and raced the one call that mattered.
//
// What is left is the rule: the manifest registers, the click opens, and
// sidePanel.open() is the FIRST and ONLY Chrome API call in the handler so no
// awaited work can spend the user gesture it requires.

const SIDE_PANEL_PATH = "app.html";

// WHICH OPENING STRATEGY THIS BUILD USES. Tested one at a time, never combined:
// combining them is what produced a build where nobody could say which
// mechanism actually opened the panel.
//
//   "explicit"  - Strategy B. No setPanelBehavior, no setOptions. Exactly one
//                 action.onClicked listener whose first Chrome call is
//                 sidePanel.open({windowId}). This is the shipping default.
//   "behavior"  - Strategy A. Chrome opens the panel itself from the action
//                 click via setPanelBehavior({openPanelOnActionClick: true}).
//                 The click listener then opens nothing at all.
//   "diagnostic"- Strategy B, but pointed at tests/diagnostic-panel.html: a
//                 static page with no CSS, no modules and no requests. Never
//                 reaches a package; see the note on DIAGNOSTIC_PANEL_PATH.
//
// Changed here, in source, rather than read from storage: MV3 requires event
// listeners to be registered synchronously at the top level, and a strategy
// that depends on an awaited storage read cannot honour that.
const OPENING_STRATEGY = "explicit";

// The diagnostic page lives under extension/tests/ because the release workflow
// deletes that directory from the package and then FAILS the build if it is
// still present. The page therefore cannot ship, and that is enforced by the
// existing gate rather than by remembering to remove it.
const DIAGNOSTIC_PANEL_PATH = "tests/diagnostic-panel.html";

const trace = globalThis.ScrapeXStartupTrace.createTrace(
  globalThis.ScrapeXStartupTrace.HOST_KEY,
);

function lastError() {
  try { return chrome.runtime.lastError?.message || null; } catch (_) { return null; }
}

trace.mark("service-worker-start", {
  strategy: OPENING_STRATEGY,
  path: OPENING_STRATEGY === "diagnostic" ? DIAGNOSTIC_PANEL_PATH : SIDE_PANEL_PATH,
});

// STRATEGY A ONLY. Chrome performs the opening itself, so there is nothing for
// the click handler to do and no gesture to preserve. This is the one strategy
// where a configuration call is legitimate, because it must be in place BEFORE
// the click rather than racing it.
if (OPENING_STRATEGY === "behavior") {
  chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).then(
    () => trace.mark("set-panel-behavior-resolved", {openPanelOnActionClick: true}),
    (error) => trace.mark("set-panel-behavior-failed", {
      message: error?.message || String(error),
    }),
  );
}

// STRATEGY "diagnostic" ONLY. Registered once, at worker start, long before any
// click — the ordering the production path deliberately no longer needs.
//
// RELOAD THE EXTENSION BEFORE THE FIRST DIAGNOSTIC CLICK. Pressing reload on
// chrome://extensions starts the worker immediately, so this setOptions has
// resolved long before any toolbar click. Clicking the icon on a cold worker
// instead would recreate the very race this branch removed from production, and
// the diagnostic would be measuring that race rather than the panel.
if (OPENING_STRATEGY === "diagnostic") {
  chrome.sidePanel.setOptions({enabled: true, path: DIAGNOSTIC_PANEL_PATH}).then(
    () => trace.mark("set-panel-options-resolved", {path: DIAGNOSTIC_PANEL_PATH}),
    (error) => trace.mark("set-panel-options-failed", {
      message: error?.message || String(error),
    }),
  );
}

// EXACTLY ONE action.onClicked listener in the whole extension.
chrome.action.onClicked.addListener((tab) => {
  const windowId = tab?.windowId;
  trace.mark("action-click", {
    tabId: tab?.id ?? null,
    windowId: windowId ?? null,
    strategy: OPENING_STRATEGY,
  });

  // Strategy A: Chrome already opened the panel. Opening it again here would be
  // the second open attempt this investigation exists to rule out.
  if (OPENING_STRATEGY === "behavior") {
    trace.mark("side-panel-open-skipped", {reason: "chrome-opens-on-action-click"});
    return;
  }

  if (!Number.isInteger(windowId)) {
    trace.mark("side-panel-open-failed", {message: "The action has no window."});
    return;
  }

  const options = {windowId};
  try {
    // FIRST Chrome API call in this handler, synchronously, on every path. The
    // mark above touched only startup-trace's in-memory array; its storage
    // write is asynchronous and cannot land before this line.
    const opening = chrome.sidePanel.open(options);
    trace.mark("side-panel-open-request", {...options, lastError: lastError()});
    opening.then(
      () => trace.mark("side-panel-open-resolved", options),
      (error) => trace.mark("side-panel-open-failed", {
        ...options,
        message: error?.message || String(error),
        lastError: lastError(),
      }),
    );
  } catch (error) {
    trace.mark("side-panel-open-failed", {
      ...options,
      message: error?.message || String(error),
      lastError: lastError(),
    });
  }
});

// Chrome 141+ exposes the host's own opening event. It is evidence, never a
// startup dependency, so older supported Chrome versions simply omit this mark.
chrome.sidePanel.onOpened?.addListener((info) => {
  trace.mark("side-panel-on-opened", info);
});

// RETRIEVING THE TRACE. Run scrapexTrace() in the service worker's console
// (chrome://extensions -> ScrapeX -> "service worker"). The two contexts write
// to separate keys, so this is where they are merged back onto one clock — the
// host's opening interval and the document's startup in a single ordered list.
globalThis.scrapexTrace = async function scrapexTrace() {
  const keys = [
    globalThis.ScrapeXStartupTrace.HOST_KEY,
    globalThis.ScrapeXStartupTrace.DOCUMENT_KEY,
  ];
  const stored = await chrome.storage.session.get(keys);
  const rows = [];
  for (const key of keys) {
    const where = key.endsWith("Host") ? "worker" : "document";
    for (const event of stored[key]?.events || []) rows.push({...event, where});
  }
  rows.sort((left, right) => left.epochMs - right.epochMs);
  const first = rows.length ? rows[0].epochMs : 0;
  return rows.map((row) => ({
    "+ms": Math.round((row.epochMs - first) * 10) / 10,
    where: row.where,
    event: row.name,
    detail: row.detail,
  }));
};

// On first install, open the onboarding page so the user immediately learns the
// ScrapeX engine (local Python) must be installed for the tool to work.
chrome.runtime.onInstalled.addListener((details) => {
  trace.mark("runtime-on-installed", {reason: details.reason});
  if (details.reason === "install") {
    chrome.tabs.create({url: chrome.runtime.getURL("onboarding.html")});
  }
});
