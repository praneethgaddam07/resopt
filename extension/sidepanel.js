// RESOPT side panel.
// Flow: capture the JD from ANY tab → score it (real engine when the RESOPT app is
// running on your machine, quick client-side estimate otherwise) → save to the Hub.
// The Hub tab tracks saved jobs: source link, applied status, and the résumé you
// customized for each one (saved on your own machine).

// Offline fallback ATS list — mirrors the engine's list_portals(); refreshed live
// from /api/ats when the app is running so it never drifts.
const PORTALS_FALLBACK = [
  { key: "workday", name: "Workday" }, { key: "taleo", name: "Oracle Taleo" },
  { key: "adp", name: "ADP Workforce Now" }, { key: "greenhouse", name: "Greenhouse" },
  { key: "lever", name: "Lever" }, { key: "icims", name: "iCIMS" },
  { key: "paycor", name: "Paycor / Paycom" }, { key: "ashby", name: "Ashby" },
  { key: "successfactors", name: "SAP SuccessFactors" }, { key: "smartrecruiters", name: "SmartRecruiters" },
  { key: "bamboohr", name: "BambooHR" }, { key: "generic", name: "Generic / Unknown" },
];
const ENGINE_URL = "http://127.0.0.1:47615";

const S = { ats: null, capture: null, resumes: [], selectors: { ats: {}, fallback: {} },
  skills: [], tabId: null, lastScore: 0, engineOn: false, hubJobs: [], hubFilter: "all", tab: "job" };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const words = (t) => (t || "").split(/\s+/).filter(Boolean).length;

function show(view) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-" + view).classList.remove("hidden");
  // The tab bar only makes sense on the two main surfaces.
  const showTabs = view === "job" || view === "hub";
  $("tabbar").classList.toggle("hidden", !showTabs);
  if (showTabs) {
    $("tabJob").classList.toggle("on", view === "job");
    $("tabHub").classList.toggle("on", view === "hub");
  }
}
const store = {
  getLocal: async (k, d) => (await chrome.storage.local.get(k))[k] ?? d,
  setLocal: (k, v) => chrome.storage.local.set({ [k]: v }),
};
async function getJSON(url) { try { return await (await fetch(url)).json(); } catch (e) { return null; } }

// All engine calls go through the background worker → native messaging host → the
// local RESOPT app (127.0.0.1:47615). The proxy only issues POSTs.
async function nativeFetch(endpoint, payload) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "NATIVE_MESSAGING", payload: { endpoint, payload: payload || {} } },
      (response) => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        if (!response || response.error) return reject(new Error(response?.error || "Unknown error"));
        if (response.data && response.data.error) return reject(new Error(response.data.error));
        resolve(response.data);
      });
  });
}

// ---------- engine status ----------
async function pingEngine() {
  try { const d = await nativeFetch("/api/ping", {}); S.engineOn = !!(d && d.ok); }
  catch (e) { S.engineOn = false; }
  const tag = $("engineTag");
  tag.classList.toggle("on", S.engineOn);
  tag.classList.toggle("off", !S.engineOn);
  $("engineLabel").textContent = S.engineOn ? "on your machine" : "engine off";
  return S.engineOn;
}

async function loadPortals() {
  let list = PORTALS_FALLBACK;
  if (S.engineOn) {
    try { const d = await nativeFetch("/api/ats", {}); if (d && d.portals && d.portals.length) list = d.portals; }
    catch (e) { /* keep fallback */ }
  }
  $("atsOverride").innerHTML = list.map((p) =>
    `<option value="${esc(p.key)}">${esc(p.name)}</option>`).join("");
  $("atsCount").textContent = `· ${list.length} formats`;
}

// ---------- tabs (native browser tab helpers) ----------
async function activeTab() { return (await chrome.tabs.query({ active: true, currentWindow: true }))[0]; }
async function capture(tabId, atsId, retries = 3) {
  const sel = (S.selectors.ats && S.selectors.ats[atsId]) || {};
  const msg = { type: "resopt:extract", selectors: sel, fallback: S.selectors.fallback || {} };
  const attempt = async () => {
    try { return await chrome.tabs.sendMessage(tabId, msg); }
    catch (e) {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["detect.js", "content.js"] });
      return await chrome.tabs.sendMessage(tabId, msg);
    }
  };
  try {
    let cap = await attempt();
    if ((!cap || !cap.jdText || cap.jdText.length < 60) && retries > 0) {
      await new Promise((r) => setTimeout(r, 1000));
      return capture(tabId, atsId, retries - 1);
    }
    return cap;
  } catch (e2) {
    return { error: "Couldn't read this page. Open the posting directly, then re-scan." };
  }
}

// ---------- setup ----------
function renderResumeList() {
  const el = $("resumeList");
  if (!S.resumes.length) { el.innerHTML = '<p class="muted" style="font-size:12px">None yet — add one below.</p>'; return; }
  el.innerHTML = S.resumes.map((r) =>
    `<div class="card" style="display:flex;justify-content:space-between;align-items:center;padding:8px 11px">
       <span>${esc(r.label)}</span><button class="mini" data-del="${esc(r.id)}">remove</button></div>`).join("");
  el.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => delResume(b.getAttribute("data-del"))));
}
async function delResume(id) {
  S.resumes = S.resumes.filter((r) => r.id !== id);
  await store.setLocal("resopt_resumes", S.resumes); renderResumeList();
}
async function addResume(label, text) {
  if (!text.trim()) return;
  S.resumes.push({ id: "r" + Date.now(), label: label.trim() || "Résumé", text: text.trim() });
  await store.setLocal("resopt_resumes", S.resumes);
  $("resumeLabel").value = ""; $("resumeText").value = "";
  $("resumeMsg").textContent = `Added · ${words(text)} words`;
  renderResumeList();
}
function openSetup() { renderResumeList(); show("setup"); }

// ---------- State A: capture + fit ----------
function fillResumeSelect() {
  $("resumeSelect").innerHTML = S.resumes.map((r) => `<option value="${esc(r.id)}">${esc(r.label)}</option>`).join("");
}
const currentResume = () => S.resumes.find((r) => r.id === $("resumeSelect").value) || S.resumes[0];
function chips(id, arr, cls) {
  $(id).innerHTML = (arr && arr.length)
    ? arr.slice(0, 14).map((k) => `<span class="chip ${cls}">${esc(k)}</span>`).join("")
    : '<span class="muted" style="font-size:12px">—</span>';
}
function verdictColor(pct) { return pct >= 65 ? "var(--green)" : pct >= 40 ? "var(--amber)" : "var(--muted)"; }

async function computeFit() {
  const res = currentResume();
  const jd = (S.capture.jdBullets && S.capture.jdBullets.length > 150) ? S.capture.jdBullets : S.capture.jdText;

  // Baseline: deterministic client-side keywords + fit (always works, even offline).
  let kw = RESOPT_match.keywords(jd, S.skills, 16, S.capture.title, S.capture.company);
  let fit = RESOPT_match.fit(res ? res.text : "", kw);
  let pct = fit.pct, verdict = fit.verdict, engine = false;

  // Upgrade to the real engine when the RESOPT app is running: semantic score +
  // the engine's own keyword extraction (far more accurate than the client stub).
  if (S.engineOn) {
    try {
      const data = await nativeFetch("/api/semantic-match", { resume_text: res ? res.text : "", jd_text: jd });
      if (data && data.score !== undefined) {
        pct = data.score; verdict = data.verdict; engine = true;
        if (data.keywords && data.keywords.length) fit = RESOPT_match.fit(res ? res.text : "", data.keywords);
      }
    } catch (e) { engine = false; }
  }

  S.lastScore = pct;
  $("fitPct").textContent = pct;
  $("fitBar").style.width = pct + "%";
  const v = $("fitVerdict"); v.textContent = verdict || ""; v.style.color = verdictColor(pct);
  const badge = $("scoreBadge");
  badge.textContent = engine ? "scored by engine" : "quick estimate";
  badge.className = "srcbadge " + (engine ? "eng" : "est");
  chips("coverChips", fit.covered, "ok");
  chips("gapChips", fit.missing, "gap");
}

async function renderJob() {
  $("atsChip").textContent = (S.ats && S.ats.name) || "Job";
  $("jobTitle").textContent = S.capture.title || "Job posting";
  $("jobCompany").textContent = S.capture.company || "";
  $("jobMeta").textContent = `Description captured · ${words(S.capture.jdText)} words`;
  const link = $("jobLink");
  if (S.capture.url) { link.href = S.capture.url; link.style.visibility = "visible"; }
  else { link.style.visibility = "hidden"; }
  const want = (S.ats && S.ats.id) || "generic";
  if ($("atsOverride").querySelector(`option[value="${want}"]`)) $("atsOverride").value = want;
  else $("atsOverride").value = "generic";
  fillResumeSelect();
  await computeFit();
  $("optimizeBtn").disabled = false;
  $("optimizeBtn").textContent = "Save Job to Hub";
  $("optimizeBtn").className = "cta";
  show("job");
}
function renderNoJob(note) {
  $("atsChip").textContent = "No job";
  $("jobTitle").textContent = "No posting detected here";
  $("jobCompany").textContent = "";
  $("jobMeta").textContent = note || "Open a job posting in any tab, then ↻ re-scan.";
  $("jobLink").style.visibility = "hidden";
  fillResumeSelect(); $("optimizeBtn").disabled = true;
  $("fitPct").textContent = "–"; $("fitBar").style.width = "0%";
  $("fitVerdict").textContent = ""; chips("coverChips", [], "ok"); chips("gapChips", [], "gap");
  $("scoreBadge").textContent = S.engineOn ? "scored by engine" : "quick estimate";
  $("scoreBadge").className = "srcbadge " + (S.engineOn ? "eng" : "est");
  show("job");
}
async function scanActiveTab() {
  if (S.tab !== "job") return;  // don't yank the panel off the Hub
  const tab = await activeTab(); S.tabId = tab && tab.id;
  const isWeb = tab && tab.url && /^https?:\/\//i.test(tab.url);
  if (!isWeb) { S.capture = null; return renderNoJob("Open a job posting in a browser tab, then ↻ re-scan."); }
  // Any tab: use the tuned selectors when we recognize the ATS, otherwise the
  // generic largest-text-block extractor in content.js handles the page.
  const ats = self.RESOPT_detectATS ? self.RESOPT_detectATS(tab.url) : null;
  S.ats = ats || { id: "generic", name: "Job" };
  S.capture = null;
  show("loading");
  const cap = await capture(tab.id, S.ats.id);
  if (!cap || cap.error || !cap.jdText || cap.jdText.length < 60) return renderNoJob(cap && cap.error);
  S.capture = cap; await renderJob();
}

// ---------- Save to Hub ----------
function fail(msg) { $("errorMsg").textContent = msg || "Something went wrong."; show("error"); }
async function saveToHub() {
  if (!S.capture) return;
  const btn = $("optimizeBtn");
  btn.disabled = true; btn.textContent = "Saving…";
  const payload = {
    title: S.capture.title || "", company: S.capture.company || "",
    url: S.capture.url || "", jd_text: S.capture.jdText || "",
    ats_id: $("atsOverride").value || "generic", score: S.lastScore || 0,
  };
  try {
    await nativeFetch("/api/hub/add", payload);
    btn.textContent = "✓ Saved to Hub"; btn.className = "cta ok";
    refreshHubCount();
    setTimeout(() => { btn.textContent = "Save Job to Hub"; btn.className = "cta"; btn.disabled = false; }, 2200);
  } catch (e) {
    btn.textContent = "Start the RESOPT app to save"; btn.className = "cta";
    setTimeout(() => { btn.textContent = "Save Job to Hub"; btn.disabled = false; }, 3000);
  }
}

// ---------- Hub tab ----------
async function refreshHubCount() {
  if (!S.engineOn) { $("hubCount").style.display = "none"; return; }
  try {
    const jobs = await nativeFetch("/api/hub/jobs", {});
    S.hubJobs = Array.isArray(jobs) ? jobs : [];
    const c = $("hubCount");
    if (S.hubJobs.length) { c.textContent = S.hubJobs.length; c.style.display = ""; }
    else c.style.display = "none";
  } catch (e) { /* app offline */ }
}
async function loadHub() {
  const el = $("hubList");
  if (!S.engineOn) {
    el.innerHTML = '<p class="empty">Start the RESOPT app on your machine to open your Hub.</p>';
    return;
  }
  el.innerHTML = '<div class="spin"></div>';
  try {
    const jobs = await nativeFetch("/api/hub/jobs", {});
    S.hubJobs = Array.isArray(jobs) ? jobs : [];
  } catch (e) { S.hubJobs = []; }
  renderHub();
}
function renderHub() {
  const el = $("hubList");
  let jobs = S.hubJobs;
  if (S.hubFilter === "applied") jobs = jobs.filter((j) => j.applied);
  else if (S.hubFilter === "saved") jobs = jobs.filter((j) => !j.applied);
  if (!jobs.length) { el.innerHTML = '<p class="empty">No jobs here yet. Save one from the “This job” tab.</p>'; return; }

  el.innerHTML = jobs.map((j) => {
    const applied = !!j.applied;
    const link = j.url ? `<a class="linkic" href="${esc(j.url)}" target="_blank" title="Open the posting" aria-label="Open the posting">↗</a>` : "";
    const resume = j.resume_path
      ? `<button class="save" data-open="${j.id}"><span>📄</span>${esc(j.resume_label || "résumé")} · on your Mac</button>`
      : `<button class="hubopt" data-opt="${j.id}">Optimize in app</button>`;
    return `<div class="jrow">
      <div style="display:flex;align-items:flex-start">
        <div><p class="jt">${esc(j.title || "Job")}</p><p class="jc">${esc(j.company || "")}</p></div>
        <span style="margin-left:auto;display:flex;align-items:center;gap:8px">${link}
          <button class="trash" data-del="${j.id}" title="Remove" aria-label="Remove">✕</button></span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;margin-top:9px">
        <span class="pill">${esc(atsName(j.ats_id))}</span>
        <div class="seg" style="margin-left:auto">
          <button class="${applied ? "a" : ""}" data-app="${j.id}" data-v="1">Applied</button>
          <button class="${applied ? "" : "n"}" data-app="${j.id}" data-v="0">Not applied</button>
        </div>
      </div>
      <div style="margin-top:8px">${resume}</div>
    </div>`;
  }).join("");

  el.querySelectorAll("[data-app]").forEach((b) => b.addEventListener("click", () =>
    setApplied(+b.getAttribute("data-app"), b.getAttribute("data-v") === "1")));
  el.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () =>
    deleteHubJob(+b.getAttribute("data-del"))));
  el.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () =>
    openResume(+b.getAttribute("data-open"))));
  el.querySelectorAll("[data-opt]").forEach((b) => b.addEventListener("click", () =>
    optimizeInApp(+b.getAttribute("data-opt"))));
}
function atsName(key) {
  const p = PORTALS_FALLBACK.find((x) => x.key === key);
  return p ? p.name : (key || "Job");
}
async function setApplied(id, applied) {
  const job = S.hubJobs.find((j) => j.id === id); if (job) { job.applied = applied ? 1 : 0; renderHub(); }
  try { await nativeFetch("/api/hub/applied/" + id, { applied }); } catch (e) {}
  refreshHubCount();
}
async function deleteHubJob(id) {
  S.hubJobs = S.hubJobs.filter((j) => j.id !== id); renderHub(); refreshHubCount();
  try { await nativeFetch("/api/hub/delete/" + id, {}); } catch (e) {}
}
async function openResume(id) {
  try { await nativeFetch("/api/hub/open-resume/" + id, {}); } catch (e) {}
}
function optimizeInApp(id) {
  // Hand the job to the desktop app UI, which runs the full optimize with the user's
  // key and can save the customized résumé back to the Hub folder.
  chrome.tabs.create({ url: `${ENGINE_URL}/?hub_job=${id}` });
}

// ---------- init + wiring ----------
async function switchTab(name) {
  S.tab = name;
  if (name === "hub") { show("hub"); await loadHub(); }
  else { show("job"); if (!S.capture) await scanActiveTab(); }
}

async function init() {
  show("loading");
  S.selectors = (await getJSON(chrome.runtime.getURL("selectors.json"))) || { ats: {}, fallback: {} };
  const sk = await getJSON(chrome.runtime.getURL("skills.json"));
  S.skills = (sk && sk.skills) || [];
  S.resumes = await store.getLocal("resopt_resumes", []);
  await pingEngine();
  await loadPortals();
  refreshHubCount();
  if (!S.resumes.length) return openSetup();
  await scanActiveTab();
}
function wire() {
  $("saveResumeBtn").addEventListener("click", () => addResume($("resumeLabel").value, $("resumeText").value));
  $("uploadBtn").addEventListener("click", () => $("resumeFile").click());
  $("resumeFile").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    e.target.value = "";
    $("resumeMsg").textContent = "Reading " + f.name + "…";
    try {
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const b64data = reader.result.split(",")[1];
          const res = await nativeFetch("/api/extract", { filename: f.name, b64data });
          if (res.error) throw new Error(res.error);
          if (!res.text || res.text.length < 30) throw new Error("No readable text found in that file.");
          await addResume($("resumeLabel").value || f.name.replace(/\.[^.]+$/, ""), res.text);
        } catch (err) { $("resumeMsg").textContent = "Couldn't read that file: " + (err.message || err); }
      };
      reader.onerror = () => { $("resumeMsg").textContent = "Couldn't read that file (start the RESOPT app to read PDFs)."; };
      reader.readAsDataURL(f);
    } catch (err) { $("resumeMsg").textContent = "Couldn't read that file: " + (err.message || err); }
  });
  $("setupDoneBtn").addEventListener("click", async () => {
    if (!S.resumes.length) { $("resumeMsg").textContent = "Add at least one résumé first."; return; }
    S.tab = "job"; await scanActiveTab();
  });
  $("resumeSelect").addEventListener("change", () => { if (S.capture) computeFit(); });
  $("optimizeBtn").addEventListener("click", saveToHub);
  $("openSetupBtn").addEventListener("click", openSetup);
  $("rescanBtn").addEventListener("click", scanActiveTab);
  $("errBackBtn").addEventListener("click", () => (S.capture ? show("job") : openSetup()));

  $("tabJob").addEventListener("click", () => switchTab("job"));
  $("tabHub").addEventListener("click", () => switchTab("hub"));
  $("hubRefresh").addEventListener("click", loadHub);
  document.querySelectorAll(".fseg button").forEach((b) => b.addEventListener("click", () => {
    S.hubFilter = b.getAttribute("data-filter");
    document.querySelectorAll(".fseg button").forEach((x) => x.classList.toggle("on", x === b));
    renderHub();
  }));

  // Auto-follow the posting (SPA sites swap jobs without a reload) — only on the job tab.
  let t = null;
  const auto = () => { if (!S.resumes.length || S.tab !== "job") return; clearTimeout(t); t = setTimeout(scanActiveTab, 400); };
  chrome.runtime.onMessage.addListener((m) => { if (m && m.type === "resopt:navigated") auto(); });
  chrome.tabs.onActivated.addListener(auto);
}
wire();
init();
