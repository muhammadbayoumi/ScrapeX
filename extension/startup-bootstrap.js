(function () {
  "use strict";

  // Earliest extension-owned timestamp. Chrome does not expose the toolbar
  // click that opened a side panel to the document, so this deliberately marks
  // only the start of the document-owned interval.
  try { window.performance.mark("scrapex:document-start"); } catch (_) {}
  document.addEventListener("DOMContentLoaded", () => {
    try { window.performance.mark("scrapex:dom-content-loaded"); } catch (_) {}
  }, {once: true});
})();
