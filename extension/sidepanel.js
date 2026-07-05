// RESOPT side panel — the 3-state UI wired to the LOCAL engine (127.0.0.1).
// Flow: ping engine → (offline = State C) → detect ATS + capture JD → State A →
// optimize via /api/jobs → poll → State B (score, covered, honest gaps, downloads).
// The API key is held in session storage only; the résumé + JD go only to localhost.

const ENGINE = "http://127.0.0.1:47615";
const REMOTE_SELECTORS = "https://raw.githubusercontent.com/praneethgaddam07/resopt/main/selectors.json";
const DL_PAGE = "https://github.com/praneethgaddam07/resopt/releases/latest";

// extension ATS id -> engine portal key (LinkedIn/Indeed are boards, not ATS -> generic)
const PORTAL = { greenhouse: "greenhouse", lever: "lever", workday: "workday", icims: "icims",
  smartrecruiters: "smartrecruiters", ashby: "ashby", bamboohr: "bamboohr",
  linkedin: "generic", indeed: "generic" };

const S = { engineUp: false, ats: null, capture: null, resumes: [], key: "",
  selectors: null, tabId: null, lastResult: null, lastJobId: null };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function show(view) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-" + view).classList.remove("hidden");
}
function setEngine(up) {
  const el = $("engine");
  el.classList.toggle("on", up); el.classList.toggle("off", !up);
  $("engineLabel").textContent = up ? "engine live" : "engine offline";
}

const store = {
  getLocal: async (k, d) => (await chrome.storage.local.get(k))[k] ?? d,
  setLocal: (k, v) => chrome.storage.local.set({ [k]: v }),
  getSession: async (k, d) => (await chrome.storage.session.get(k))[k] ?? d,
  setSession: (k, v) => chrome.storage.session.set({ [k]: v }),
};

function providerHint(k) {
  k = (k || "").trim();
  if (!k) return "";
  if (k.startsWith("sk-ant-")) return "Anthropic (Claude) key";
  if (k.startsWith("sk-")) return "OpenAI key";
  if (k.startsWith("AIza") || k.startsWith("AQ.")) return "Google Gemini key";
  if (k.startsWith("gsk_")) return "Groq key";
  if (k.startsWith("pplx-")) return "Perplexity key";
  return "Unrecognized key format";
}

async function ping() {
  try {
    const r = await fetch(ENGINE + "/api/ping", { signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch (e) { return false; }
}

async function loadSelectors() {
  try {
    const r = await fetch(REMOTE_SELECTORS, { cache: "no-store", signal: AbortSignal.timeout(2500) });
    if (r.ok) { const j = await r.json(); if (j && j.ats) return j; }
  } catch (e) { /* fall back to bundled */ }
  try { return await (await fetch(chrome.runtime.getURL("selectors.json"))).json(); }
  catch (e) { return { ats: {}, fallback: {} }; }
}

const activeTab = async () => (await chrome.tabs.query({ active: true, currentWindow: true }))[0];

async function capture(tabId, atsId) {
  const sel = (S.selectors && S.selectors.ats && S.selectors.ats[atsId]) || {};
  const fallback = (S.selectors && S.selectors.fallback) || {};
  const msg = { type: "resopt:extract", selectors: sel, fallback };
  try {
    return await chrome.tabs.sendMessage(tabId, msg);
  } catch (e) {
    // content script not present yet (timing / non-matched page) — inject then retry
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["detect.js", "content.js"] });
      return await chrome.tabs.sendMessage(tabId, msg);
    } catch (e2) {
      return { error: "Couldn't read this page. Open the job posting directly, then re-scan." };
    }
  }
}

// ---- setup (key + résumés) ----
function renderResumeList() {
  const el = $("resumeList");
  if (!S.resumes.length) { el.innerHTML = '<p class="muted" style="font-size:12px">None yet — add one below.</p>'; return; }
  el.innerHTML = S.resumes.map((r) =>
    `<div class="card" style="display:flex;justify-content:space-between;align-items:center;padding:8px 11px">
       <span>${esc(r.label)}</span>
       <button class="mini" data-del="${esc(r.id)}">remove</button></div>`).join("");
  el.querySelectorAll("[data-del]").forEach((b) =>
    b.addEventListener("click", () => deleteResume(b.getAttribute("data-del"))));
}
async function deleteResume(id) {
  S.resumes = S.resumes.filter((r) => r.id !== id);
  await store.setLocal("resopt_resumes", S.resumes);
  renderResumeList();
}
async function saveResume() {
  const label = $("resumeLabel").value.trim();
  const text = $("resumeText").value.trim();
  if (!label || !text) return;
  S.resumes.push({ id: "r" + Date.now(), label, text });
  await store.setLocal("resopt_resumes", S.resumes);
  $("resumeLabel").value = ""; $("resumeText").value = "";
  renderResumeList();
}
async function uploadResume(file) {
  if (!file) return;
  const btn = $("uploadBtn"), old = btn.textContent;
  btn.textContent = "Reading…"; btn.disabled = true; $("resumeMsg").textContent = "";
  try {
    const fd = new FormData(); fd.append("resume_file", file);
    // Engine extracts text locally (no key, nothing stored) so the file never leaves the machine.
    const r = await fetch(ENGINE + "/api/extract-resume", { method: "POST", body: fd });
    if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail || d; } catch (e) {} throw new Error(d); }
    const { filename, text } = await r.json();
    const label = $("resumeLabel").value.trim() || filename.replace(/\.[^.]+$/, "");
    S.resumes.push({ id: "r" + Date.now(), label, text });
    await store.setLocal("resopt_resumes", S.resumes);
    $("resumeLabel").value = "";
    $("resumeMsg").textContent = `Added “${label}” · ${text.split(/\s+/).filter(Boolean).length} words`;
    renderResumeList();
  } catch (e) {
    $("resumeMsg").textContent = "Couldn't read that file: " + (e.message || e);
  } finally {
    btn.textContent = old; btn.disabled = false; $("resumeFile").value = "";
  }
}
function openSetup() {
  $("keyInput").value = S.key || "";
  $("keyHint").textContent = providerHint(S.key);
  renderResumeList();
  show("setup");
}

// ---- State A ----
function fillResumeSelect() {
  $("resumeSelect").innerHTML = S.resumes.map((r) =>
    `<option value="${esc(r.id)}">${esc(r.label)}</option>`).join("");
}
function renderJob() {
  $("atsChip").textContent = (S.ats && S.ats.name) || "Job";
  $("jobTitle").textContent = S.capture.title || "Job posting";
  $("jobCompany").textContent = S.capture.company || "";
  const words = (S.capture.jdText || "").split(/\s+/).filter(Boolean).length;
  $("jobMeta").textContent = `Description captured · ${words} words`;
  fillResumeSelect();
  $("optimizeBtn").disabled = false;
  show("job");
}
function renderNoJob(note) {
  $("atsChip").textContent = "No job";
  $("jobTitle").textContent = "No posting detected here";
  $("jobCompany").textContent = "";
  $("jobMeta").textContent = note || "Open a posting on a supported site, then ↻ re-scan.";
  fillResumeSelect();
  $("optimizeBtn").disabled = true;
  show("job");
}
async function scanActiveTab() {
  const tab = await activeTab();
  S.tabId = tab && tab.id;
  const ats = tab && tab.url && self.RESOPT_detectATS ? self.RESOPT_detectATS(tab.url) : null;
  S.ats = ats; S.capture = null;
  if (!ats || !tab) return renderNoJob();
  show("loading");
  const cap = await capture(tab.id, ats.id);
  if (!cap || cap.error || !cap.jdText || cap.jdText.length < 60) return renderNoJob(cap && cap.error);
  S.capture = cap;
  renderJob();
}

// ---- optimize + poll ----
function guessLastName(text) {
  const first = (text || "").split("\n").map((s) => s.trim()).find(Boolean) || "";
  const words = first.split(/\s+/).filter((w) => /^[A-Za-z][A-Za-z'-]+$/.test(w));
  return words.length ? words[words.length - 1] : "Resume";
}
function fail(msg) { $("errorMsg").textContent = msg || "Optimization failed."; show("error"); }

async function optimize() {
  const resume = S.resumes.find((r) => r.id === $("resumeSelect").value) || S.resumes[0];
  if (!resume) return openSetup();
  if (!S.key) return openSetup();
  S.currentLastName = guessLastName(resume.text);
  const fd = new FormData();
  fd.append("jd", S.capture.jdText);
  fd.append("api_key", S.key);
  fd.append("resume", resume.text);
  fd.append("ats", (S.ats && PORTAL[S.ats.id]) || "generic");
  fd.append("company", (S.capture.company || "Company").slice(0, 60));
  fd.append("lastname", S.currentLastName);
  fd.append("target_title", S.capture.title || "");
  $("busyBar").style.width = "8%"; $("busyLabel").textContent = "Optimizing…"; show("busy");
  let res;
  try { res = await fetch(ENGINE + "/api/jobs", { method: "POST", body: fd }); }
  catch (e) { return fail("Lost the engine — is the RESOPT app still running?"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    return fail(detail);
  }
  const { id } = await res.json();
  const done = await poll(id);
  if (!done || done.status !== "done") return fail((done && done.error) || "Optimization failed.");
  renderResult(id, done.result);
}
async function poll(id) {
  for (let i = 0; i < 150; i++) {
    let j;
    try { j = await (await fetch(`${ENGINE}/api/jobs/${id}`)).json(); }
    catch (e) { return { status: "error", error: "Lost connection to the engine." }; }
    if (j.status === "done" || j.status === "error") return j;
    if (j.progress) {
      $("busyBar").style.width = Math.max(8, j.progress.percent || 8) + "%";
      if (j.progress.label) $("busyLabel").textContent = j.progress.label + "…";
    }
    await new Promise((r) => setTimeout(r, 1200));
  }
  return { status: "error", error: "Timed out. Try again." };
}

// ---- State B ----
function chips(id, arr, cls) {
  $(id).innerHTML = (arr && arr.length)
    ? arr.map((k) => `<span class="chip ${cls}">${esc(k)}</span>`).join("")
    : '<span class="muted" style="font-size:12px">—</span>';
}
function renderResult(id, result) {
  S.lastResult = result; S.lastJobId = id;
  const rep = result.report || {};
  const score = Math.round(rep.ats_score || 0);
  $("scoreNum").textContent = score;
  $("scoreBar").style.width = Math.max(0, Math.min(100, score)) + "%";
  $("scorePass").textContent = rep.passes_threshold ? "✓ passes ATS target" : "below target — see gaps";
  chips("matchedChips", (rep.matched_keywords || []).slice(0, 12), "ok");
  const miss = (rep.missing_keywords || []).slice(0, 12);
  if (miss.length) chips("missingChips", miss, "gap");
  else $("missingChips").innerHTML = '<span class="muted" style="font-size:12px">Nothing material left uncovered.</span>';
  $("checklistLine").textContent = `ATS checklist: ${rep.checklist_passed || 0}/${rep.checklist_total || 0} passed`;
  show("result");
}

// ---- downloads ----
function triggerDownload(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
const fname = (ext) => `${S.currentLastName || "Resume"}_${(S.capture && S.capture.company) || "Company"}.${ext}`
  .replace(/[^A-Za-z0-9_.-]/g, "");
async function downloadDocx() {
  try {
    const r = await fetch(`${ENGINE}/api/jobs/${S.lastJobId}/download`);
    if (!r.ok) throw new Error();
    triggerDownload(await r.blob(), fname("docx"));
  } catch (e) { fail("This result expired. Re-optimize to download again."); }
}
async function downloadPdf() {
  const res = S.lastResult; if (!res) return;
  const data = { job_title: res.job_title, summary: res.summary, skills: res.skills,
    experiences: res.experiences, projects: res.projects };
  const contact = Object.assign({}, res.contact,
    { education: res.education, certifications: res.certifications });
  const body = { data, contact, ats: (S.ats && PORTAL[S.ats.id]) || "generic",
    section_order: res.section_order, fmt: "pdf",
    lastname: S.currentLastName, company: (S.capture && S.capture.company) || "Company" };
  try {
    const r = await fetch(`${ENGINE}/api/render`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error();
    triggerDownload(await r.blob(), fname("pdf"));
  } catch (e) { fail("Couldn't build the PDF. Try DOCX, or re-optimize."); }
}

// ---- init + wiring ----
async function init() {
  show("loading");
  S.engineUp = await ping();
  setEngine(S.engineUp);
  if (!S.engineUp) return show("offline");
  S.selectors = await loadSelectors();
  S.key = await store.getSession("resopt_key", "");
  S.resumes = await store.getLocal("resopt_resumes", []);
  if (!S.key || !S.resumes.length) return openSetup();
  await scanActiveTab();
}

function wire() {
  $("dlLink").href = DL_PAGE;
  $("retryBtn").addEventListener("click", init);
  $("errRetryBtn").addEventListener("click", init);
  $("keyInput").addEventListener("input", () => { $("keyHint").textContent = providerHint($("keyInput").value); });
  $("saveResumeBtn").addEventListener("click", saveResume);
  $("uploadBtn").addEventListener("click", () => $("resumeFile").click());
  $("resumeFile").addEventListener("change", (e) => uploadResume(e.target.files[0]));
  // Auto-follow the posting: re-capture when the page navigates (SPA job switches)
  // or the user switches tabs — no manual Re-scan needed.
  let rescanT = null;
  const autoRescan = () => {
    if (!S.engineUp || !S.key || !S.resumes.length) return;   // not past setup yet
    if (!$("view-busy").classList.contains("hidden")) return;  // don't interrupt an optimize
    clearTimeout(rescanT); rescanT = setTimeout(scanActiveTab, 400);
  };
  chrome.runtime.onMessage.addListener((m) => { if (m && m.type === "resopt:navigated") autoRescan(); });
  chrome.tabs.onActivated.addListener(autoRescan);
  $("setupDoneBtn").addEventListener("click", async () => {
    S.key = $("keyInput").value.trim();
    await store.setSession("resopt_key", S.key);
    if (!S.key) { $("keyHint").textContent = "Enter your key to continue."; return; }
    if (!S.resumes.length) { $("keyHint").textContent = "Add at least one résumé above."; return; }
    await scanActiveTab();
  });
  $("openSetupBtn").addEventListener("click", openSetup);
  $("rescanBtn").addEventListener("click", scanActiveTab);
  $("optimizeBtn").addEventListener("click", optimize);
  $("dlDocx").addEventListener("click", downloadDocx);
  $("dlPdf").addEventListener("click", downloadPdf);
  $("reoptBtn").addEventListener("click", () => show("job"));
}

wire();
init();
