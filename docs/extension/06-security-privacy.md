# 06 — Security & privacy

Privacy isn't a feature bolt-on here — it's the architecture. This doc states the threat model,
justifies every permission, and defines data handling.

## Data-flow privacy claim
- The extension transmits **nothing** to any RESOPT-controlled server. There is no such server in
  the path.
- The JD is read from the page the user is already viewing. The résumé lives in the user's browser
  storage. Optimization happens on the user's own machine (`127.0.0.1`). Files download locally.
- Therefore "your résumé and the job description never leave your machine" is literally true and
  independently verifiable (open devtools → network → only `localhost` calls).

## Threat model

| Threat | Vector | Mitigation |
|---|---|---|
| Extension exfiltrates résumé/JD | malicious/compromised extension code | No network origins except `localhost` + current page; no analytics endpoints; MV3 bans remote code; open to inspection |
| A web page reads the localhost engine | any site fetching `127.0.0.1:47615` | Engine CORS allows only `chrome-extension://<id>`; `/api/*` rejects other origins; PNA preflight enforced |
| Malicious page feeds a poisoned "JD" | crafted DOM to manipulate output | JD is treated as untrusted text; engine already sanitizes and never executes input; validators strip fabricated metrics |
| Selector config tampering | MITM on remote config fetch | Fetch over HTTPS from the repo; config is data only (never `eval`'d); schema-validate before use; ship a safe bundled default |
| Résumé leaks via storage | another extension / local malware | `chrome.storage` is extension-scoped; AI key kept session-only, never persisted; nothing written to disk by us |
| Over-broad host access | `<all_urls>` scope creep | Explicit ATS domain allowlist + `activeTab`; no wildcard-all |
| App-launch abuse | `resopt://` scheme hijack | Scheme only launches the local app; passes no sensitive payload; degrade to plain download link |

## Permission justifications (for the store listing)
- **`sidePanel`** — the product surface; the optimization UI lives in the side panel.
- **`activeTab`** — read the JD from the tab the user explicitly invokes the extension on.
- **`storage`** — save the user's résumés and the selector-config cache locally.
- **`scripting`** — inject the content script that extracts the JD from supported postings.
- **`host_permissions`: ATS domains** — detect the ATS and read the JD on those postings only.
- **`host_permissions`: `http://127.0.0.1/*`** — talk to the user's own local RESOPT engine.

Each maps to a single, explainable purpose — no permission exists "just in case."

## Data handling rules (non-negotiable, inherited from the app)
- **Zero server retention.** We run no server, so we store nothing. Do not add analytics that phone
  home; if we ever want metrics, they must be local and opt-in.
- **Session-only secrets.** Any AI key is held in memory for the session, never in `chrome.storage`,
  never logged.
- **No PII in logs.** The content script and panel must not `console.log` résumé/JD content in
  release builds.
- **Least privilege.** New ATS support = add its domain to the allowlist, nothing broader.

## Compliance notes
- MV3's remote-code ban is satisfied: the only remote fetch is JSON selector *data*.
- Privacy policy for the listing writes itself: local processing, no collection, no transmission to
  us. This is a marketing asset, not a liability.
