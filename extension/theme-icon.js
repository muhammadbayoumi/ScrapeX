(function () {
  "use strict";

  const scheme = window.matchMedia("(prefers-color-scheme: dark)");
  const iconPaths = (tone) => ({
    "16": `icons/x-mark-${tone}-16.png`,
    "32": `icons/x-mark-${tone}-32.png`,
  });

  function applyChromeThemeIcon() {
    const tone = scheme.matches ? "white" : "black";
    const favicon = document.getElementById("scrapex-theme-icon");
    if (favicon) favicon.href = iconPaths(tone)["32"];
    if (globalThis.chrome?.action?.setIcon) {
      chrome.action.setIcon({path: iconPaths(tone)}).catch(() => {
        // Chrome still has the matching page favicon when the action is unavailable.
      });
    }
  }

  applyChromeThemeIcon();
  scheme.addEventListener("change", applyChromeThemeIcon);
})();
