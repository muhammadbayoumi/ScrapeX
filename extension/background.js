// Make the toolbar icon open the ScrapeX side panel (the always-available control
// panel). The interface lives in the extension; the engine is the local Python app.
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((e) => console.warn("sidePanel:", e));

// On first install, open the onboarding page so the user immediately learns the
// ScrapeX engine (local Python) must be installed for the tool to work.
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install") {
    chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html") });
  }
});
