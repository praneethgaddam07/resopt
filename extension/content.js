// RESOPT content script — reads the rendered job posting and returns
// { title, company, jdText, url }. Runs in the page's isolated world; READ-ONLY
// (never mutates the page). The side panel resolves which selector set to use
// (bundled vs remote config) and passes it in via a "resopt:extract" message.
(function () {
  function pickText(selectorList) {
    if (!selectorList) return "";
    for (const sel of selectorList.split(",")) {
      try {
        const el = document.querySelector(sel.trim());
        const t = el && (el.innerText || el.textContent || "").trim();
        if (t) return t;
      } catch (e) { /* bad selector — skip */ }
    }
    return "";
  }

  function largestTextBlock(minChars, maxChars) {
    let best = "", bestLen = 0;
    const nodes = document.querySelectorAll("main, article, section, [role='main'], div");
    for (const n of nodes) {
      let t = "";
      try { t = (n.innerText || "").trim(); } catch (e) { continue; }
      if (t.length > bestLen && t.length >= minChars && t.length <= maxChars) {
        bestLen = t.length;
        best = t;
      }
    }
    return best;
  }

  function metaCompany() {
    const og = document.querySelector("meta[property='og:site_name']");
    return (og && og.content && og.content.trim()) || "";
  }

  function titleFromDoc() {
    return (document.title || "").split(/\s[|\-–—]\s/)[0].trim();
  }

  function extract(selectors, fallback) {
    selectors = selectors || {};
    fallback = fallback || { minChars: 300, maxChars: 20000 };
    const title = pickText(selectors.title) || titleFromDoc();
    const company = pickText(selectors.company) || metaCompany();
    let jdText = pickText(selectors.jd);
    if (!jdText || jdText.length < (fallback.minChars || 300)) {
      const block = largestTextBlock(fallback.minChars || 300, fallback.maxChars || 20000);
      if (block.length > jdText.length) jdText = block;
    }
    return { title, company, jdText, url: location.href, capturedAt: Date.now() };
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg && msg.type === "resopt:extract") {
      try { sendResponse(extract(msg.selectors, msg.fallback)); }
      catch (e) { sendResponse({ error: String(e && e.message || e) }); }
    }
    return true; // keep the message channel open for the async response
  });

  // Auto-follow: SPA sites (LinkedIn, Workday…) switch postings without a reload.
  // Poll the URL and tell the side panel to re-capture when the posting changes.
  let lastUrl = location.href;
  function checkNav() {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      try { chrome.runtime.sendMessage({ type: "resopt:navigated" }).catch(() => {}); } catch (e) {}
    }
  }
  setInterval(checkNav, 800);
  window.addEventListener("popstate", checkNav);
})();
