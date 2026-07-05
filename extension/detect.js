// hostname -> ATS. Shared by the background worker (badge) and the content script
// (which selector set to use). No imports/exports so it works both as a content
// script and via importScripts() in the MV3 service worker. `id` matches a key in
// selectors.json.
(function (root) {
  const ATS = [
    { id: "greenhouse",      name: "Greenhouse",      host: /(^|\.)greenhouse\.io$/ },
    { id: "lever",           name: "Lever",           host: /(^|\.)lever\.co$/ },
    { id: "workday",         name: "Workday",         host: /(^|\.)myworkdayjobs\.com$/ },
    { id: "icims",           name: "iCIMS",           host: /(^|\.)icims\.com$/ },
    { id: "smartrecruiters", name: "SmartRecruiters", host: /(^|\.)smartrecruiters\.com$/ },
    { id: "ashby",           name: "Ashby",           host: /(^|\.)ashbyhq\.com$/ },
    { id: "bamboohr",        name: "BambooHR",        host: /(^|\.)bamboohr\.com$/ },
    { id: "linkedin",        name: "LinkedIn",        host: /(^|\.)linkedin\.com$/, path: /\/jobs\// },
    { id: "indeed",          name: "Indeed",          host: /(^|\.)indeed\.com$/,   path: /(viewjob|\/jobs|\/job\/)/ }
  ];

  function detectATS(urlString) {
    let u;
    try { u = new URL(urlString); } catch (e) { return null; }
    for (const a of ATS) {
      if (a.host.test(u.hostname) && (!a.path || a.path.test(u.pathname + u.search))) {
        return { id: a.id, name: a.name };
      }
    }
    return null;
  }

  root.RESOPT_detectATS = detectATS;
  root.RESOPT_ATS_LIST = ATS;
})(typeof self !== "undefined" ? self : (typeof globalThis !== "undefined" ? globalThis : this));
