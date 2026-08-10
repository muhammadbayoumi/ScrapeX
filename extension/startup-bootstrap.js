(function () {
  "use strict";

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
})();
