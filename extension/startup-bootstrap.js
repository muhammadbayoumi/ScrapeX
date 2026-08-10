(function () {
  "use strict";

  const STARTUP_EVENT = "scrapex-side-panel-startup-event";

  function epochAt(startTime = window.performance.now()) {
    return window.performance.timeOrigin + startTime;
  }

  function snapshot(extra = {}) {
    let hasFocus = false;
    try { hasFocus = document.hasFocus(); } catch (_) {}
    return {
      visibilityState: document.visibilityState,
      hasFocus,
      ...extra,
    };
  }

  function mark(name, detail) {
    try { window.performance.mark(`scrapex:${name}`, {detail}); }
    catch (_) {
      try { window.performance.mark(`scrapex:${name}`); } catch (_) {}
    }
    try {
      chrome.runtime.sendMessage({
        type: STARTUP_EVENT,
        event: {name, at: epochAt(), detail},
      }).catch(() => {});
    } catch (_) {}
  }

  // Earliest extension-owned timestamp. Chrome does not expose the toolbar
  // click that opened a side panel to the document, so this deliberately marks
  // only the start of the document-owned interval.
  mark("document-start", snapshot());
  document.addEventListener("DOMContentLoaded", () => {
    mark("dom-content-loaded", snapshot());
  }, {once: true});
  window.addEventListener("pageshow", (event) => {
    mark("pageshow", snapshot({persisted: event.persisted}));
  }, {once: true});
  window.addEventListener("focus", () => mark("focus", snapshot()));
  window.addEventListener("blur", () => mark("blur", snapshot()));
  document.addEventListener("visibilitychange", () => {
    mark("visibilitychange", snapshot());
  });

  try {
    const paintObserver = new globalThis.PerformanceObserver((list) => {
      const fcp = list.getEntries().find((entry) =>
        entry.name === "first-contentful-paint");
      if (!fcp) return;
      const detail = snapshot({startTime: fcp.startTime});
      try {
        window.performance.mark("scrapex:first-contentful-paint", {
          startTime: fcp.startTime, detail,
        });
      } catch (_) {}
      try {
        chrome.runtime.sendMessage({
          type: STARTUP_EVENT,
          event: {name: "first-contentful-paint", at: epochAt(fcp.startTime), detail},
        }).catch(() => {});
      } catch (_) {}
      paintObserver.disconnect();
    });
    paintObserver.observe({type: "paint", buffered: true});
  } catch (_) {}
})();
