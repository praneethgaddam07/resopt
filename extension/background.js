// MV3 service worker: badge the toolbar icon on recognized job postings and open
// the side panel when the icon is clicked. Kept deliberately thin — all optimization
// logic lives in the side panel + the local engine.
importScripts("detect.js");

const BADGE_COLOR = "#E4572E"; // RESOPT vermilion

function openPanelOnClick() {
  // Clicking the toolbar icon opens the side panel (no popup).
  if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
  }
}
chrome.runtime.onInstalled.addListener(openPanelOnClick);
chrome.runtime.onStartup.addListener(openPanelOnClick);
openPanelOnClick();

async function badge(tabId, url) {
  const hit = self.RESOPT_detectATS ? self.RESOPT_detectATS(url || "") : null;
  try {
    await chrome.action.setBadgeText({ tabId, text: hit ? "JD" : "" });
    if (hit) {
      await chrome.action.setBadgeBackgroundColor({ tabId, color: BADGE_COLOR });
      await chrome.action.setTitle({ tabId, title: `RESOPT — ${hit.name} job detected` });
    } else {
      await chrome.action.setTitle({ tabId, title: "RESOPT" });
    }
  } catch (e) { /* tab gone */ }
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (tab && tab.url && (info.status === "complete" || info.url)) badge(tabId, tab.url);
});
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try { const t = await chrome.tabs.get(tabId); badge(tabId, t.url); } catch (e) {}
});
