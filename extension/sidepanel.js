// RESOPT (extension-only) side panel. Everything runs here — no app, no cloud.
// Flow: capture JD → free deterministic fit (lib/match) → optimize via the user's AI key
// straight from the browser (lib/providers + lib/optimize) → DOCX built in-browser (lib/docx).
const PORTAL = { greenhouse: "greenhouse", lever: "lever", workday: "workday", icims: "icims",
  smartrecruiters: "smartrecruiters", ashby: "ashby", bamboohr: "bamboohr",
  linkedin: "generic", indeed: "generic" };

const S = { ats: null, capture: null, resumes: [], selectors: { ats: {}, fallback: {} },
  skills: [], tabId: null, lastFit: null, lastKw: null, lastData: null };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const words = (t) => (t || "").split(/\s+/).filter(Boolean).length;

function show(view) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-" + view).classList.remove("hidden");
}
const store = {
  getLocal: async (k, d) => (await chrome.storage.local.get(k))[k] ?? d,
  setLocal: (k, v) => chrome.storage.local.set({ [k]: v }),
  getSession: async (k, d) => (await chrome.storage.session.get(k))[k] ?? d,
  setSession: (k, v) => chrome.storage.session.set({ [k]: v }),
};
async function getJSON(url) { try { return await (await fetch(url)).json(); } catch (e) { return null; } }

async function nativeFetch(endpoint, payload) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({
      type: "NATIVE_MESSAGING",
      payload: { endpoint, payload }
    }, (response) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (!response || response.error) return reject(new Error(response?.error || "Unknown error"));
      if (response.data && response.data.error) return reject(new Error(response.data.error));
      resolve(response.data);
    });
  });
}

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
      await new Promise(r => setTimeout(r, 1000));
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
function openSetup() {
  renderResumeList(); show("setup");
}

// ---------- State A: capture + free fit ----------
function fillResumeSelect() {
  $("resumeSelect").innerHTML = S.resumes.map((r) => `<option value="${esc(r.id)}">${esc(r.label)}</option>`).join("");
}
const currentResume = () => S.resumes.find((r) => r.id === $("resumeSelect").value) || S.resumes[0];
function chips(id, arr, cls) {
  $(id).innerHTML = (arr && arr.length)
    ? arr.slice(0, 14).map((k) => `<span class="chip ${cls}">${esc(k)}</span>`).join("")
    : '<span class="muted" style="font-size:12px">—</span>';
}
function verdictClass(pct) { return pct >= 65 ? "v-good" : pct >= 40 ? "v-mid" : "v-low"; }

async function computeFit() {
  const res = currentResume();
  const textForKeywords = (S.capture.jdBullets && S.capture.jdBullets.length > 150) ? S.capture.jdBullets : S.capture.jdText;
  const kw = RESOPT_match.keywords(textForKeywords, S.skills, 16, S.capture.title, S.capture.company);
  const fit = RESOPT_match.fit(res ? res.text : "", kw);
  S.lastFit = fit; S.lastKw = kw;
  
  let pct = fit.pct;
  let verdict = fit.verdict;
  let ai_badge = false;
  
  try {
    const data = await nativeFetch("/api/semantic-match", { resume_text: res ? res.text : "", jd_text: textForKeywords });
    if (data && data.score !== undefined) {
      pct = data.score;
      verdict = data.verdict;
      ai_badge = true;
    }
  } catch (e) {
    // fallback to keywords if desktop app offline
  }
  
  $("fitPct").textContent = pct;
  $("fitBar").style.width = pct + "%";
  const v = $("fitVerdict"); 
  v.innerHTML = verdict + (ai_badge ? ' <span class="badge" style="background:var(--accent);color:#fff;border:none;margin-left:8px;">AI Semantic</span>' : '');
  v.className = "verdict " + verdictClass(pct);
  chips("coverChips", fit.covered, "ok");
  chips("gapChips", fit.missing, "gap");
}
async function renderJob() {
  $("atsChip").textContent = (S.ats && S.ats.name) || "Job";
  $("jobTitle").textContent = S.capture.title || "Job posting";
  $("jobCompany").textContent = S.capture.company || "";
  $("jobMeta").textContent = `Description captured · ${words(S.capture.jdText)} words`;
  if (S.ats && S.ats.id) {
    const opt = $("atsOverride").querySelector(`option[value="${S.ats.id}"]`);
    if (opt) $("atsOverride").value = S.ats.id;
    else $("atsOverride").value = "generic";
  }
  fillResumeSelect();
  await computeFit();
  $("optimizeBtn").disabled = false;
  show("job");
}
function renderNoJob(note) {
  $("atsChip").textContent = "No job";
  $("jobTitle").textContent = "No posting detected here";
  $("jobCompany").textContent = ""; $("jobMeta").textContent = note || "Open a posting on a supported site, then ↻ re-scan.";
  fillResumeSelect(); $("optimizeBtn").disabled = true;
  ["fitPct"].forEach((i) => $(i).textContent = "–"); $("fitBar").style.width = "0%";
  $("fitVerdict").textContent = ""; chips("coverChips", [], "ok"); chips("gapChips", [], "gap");
  show("job");
}
async function scanActiveTab() {
  const tab = await activeTab(); S.tabId = tab && tab.id;
  const ats = tab && tab.url && self.RESOPT_detectATS ? self.RESOPT_detectATS(tab.url) : null;
  S.ats = ats; S.capture = null;
  if (!ats || !tab) return renderNoJob();
  show("loading");
  const cap = await capture(tab.id, ats.id);
  if (!cap || cap.error || !cap.jdText || cap.jdText.length < 60) return renderNoJob(cap && cap.error);
  S.capture = cap; await renderJob();
}

// ---------- Save to Hub ----------
function fail(msg) { $("errorMsg").textContent = msg || "Something went wrong."; show("error"); }

async function saveToHub() {
  if (!S.capture) return;
  const btn = $("optimizeBtn");
  btn.disabled = true;
  btn.textContent = "Saving...";
  
  const payload = {
    title: S.capture.title || "",
    company: S.capture.company || "",
    url: S.capture.url || "",
    jd_text: S.capture.jdText || "",
    ats_id: $("atsOverride").value || "generic",
    score: S.lastFit ? S.lastFit.pct : 0
  };

  try {
    await nativeFetch("/api/hub/add", payload);
    btn.textContent = "✅ Saved to Hub!";
    btn.style.background = "#10b981"; // green
    btn.style.color = "#fff";
  } catch (e) {
    btn.textContent = "❌ Failed (Is desktop app running?)";
    btn.style.background = "#ef4444";
    setTimeout(() => {
      btn.textContent = "Save Job to Hub";
      btn.style.background = "";
      btn.disabled = false;
    }, 3000);
  }
}

// ---------- download ----------
function triggerDownload(bytes, name) {
  const blob = new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function downloadDocx() {
  if (!S.lastData) return;
  const bytes = RESOPT_docx.build(S.lastData);
  const company = (S.capture && S.capture.company || "Company").replace(/[^A-Za-z0-9]/g, "");
  triggerDownload(bytes, `${S.lastName || "Resume"}_${company || "Company"}.docx`);
}

// ---------- init + wiring ----------
async function init() {
  show("loading");
  S.selectors = (await getJSON(chrome.runtime.getURL("selectors.json"))) || { ats: {}, fallback: {} };
  const sk = await getJSON(chrome.runtime.getURL("skills.json"));
  S.skills = (sk && sk.skills) || [];
  S.resumes = await store.getLocal("resopt_resumes", []);
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
          const b64data = reader.result.split(',')[1];
          const res = await nativeFetch("/api/extract", {
            filename: f.name,
            b64data: b64data
          });
          if (res.error) throw new Error(res.error);
          if (!res.text || res.text.length < 30) throw new Error("No readable text found in that file.");
          await addResume($("resumeLabel").value || f.name.replace(/\.[^.]+$/, ""), res.text);
        } catch (err) {
          $("resumeMsg").textContent = "Couldn't read that file: " + (err.message || err);
        }
      };
      reader.onerror = () => {
        $("resumeMsg").textContent = "Couldn't read that file: FileReader error";
      };
      reader.readAsDataURL(f);
    } catch (err) { $("resumeMsg").textContent = "Couldn't read that file: " + (err.message || err); }
  });
  $("setupDoneBtn").addEventListener("click", async () => {
    if (!S.resumes.length) { $("resumeMsg").textContent = "Add at least one résumé first."; return; }
    await scanActiveTab();
  });
  $("resumeSelect").addEventListener("change", () => { if (S.capture) computeFit(); });
  $("optimizeBtn").addEventListener("click", saveToHub);
  $("openSetupBtn").addEventListener("click", openSetup);
  $("rescanBtn").addEventListener("click", scanActiveTab);
  $("errBackBtn").addEventListener("click", () => (S.capture ? show("job") : openSetup()));
  // auto-follow the posting
  let t = null;
  const auto = () => { if (!S.resumes.length) return;
    clearTimeout(t); t = setTimeout(scanActiveTab, 400); };
  chrome.runtime.onMessage.addListener((m) => { if (m && m.type === "resopt:navigated") auto(); });
  chrome.tabs.onActivated.addListener(auto);
}
wire();
init();
