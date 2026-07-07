<p align="center"><img src="app/static/icon.png" width="110" alt="RESOPT"/></p>

<h1 align="center">RESOPT<span>.</span></h1>
<p align="center"><i>The résumé, rewritten for the job you actually want — truthfully.</i></p>

RESOPT tailors your **real** résumé (and a cover letter, if you want one) to a specific
job description so it passes **ATS** screening — and it **never invents experience,
tools, employers, or metrics**. You get an honest fit check, a rewritten résumé with a
live ATS match score, and a clean single-column `.docx`.

- 🔒 **Nothing stored, ever.** Your API key and résumé live in memory for one request,
  then they're scrubbed. No database, no disk, no logs — and the code is open, so you
  can verify that yourself.
- ✅ **Truth-guarded.** A deterministic integrity layer strips any invented metric or
  AI-tell word before the document is built. Genuinely missing skills are flagged to
  you — never faked.
- 🎯 **9 ATS portals** (Workday, Taleo, ADP, Greenhouse, Lever, iCIMS, Paycor,
  SmartRecruiters, BambooHR) with per-portal formatting rules + a pre-submit checklist.

There are two ways to use it — pick one:

---

## 1 · Download the desktop app (easiest)

| Platform | Download |
|----------|----------|
| macOS (Apple Silicon) | [**RESOPT-macOS.zip**](../../releases/latest/download/RESOPT-macOS.zip) |
| Windows | [**RESOPT-Windows.zip**](../../releases/latest/download/RESOPT-Windows.zip) |

**macOS one-liner** (installs to Applications and clears the unsigned-app warning):

```bash
curl -L -o /tmp/RESOPT.zip https://github.com/praneethgaddam07/resopt/releases/latest/download/RESOPT-macOS.zip && unzip -o /tmp/RESOPT.zip -d /Applications && xattr -cr /Applications/RESOPT.app && open /Applications/RESOPT.app
```

Bring your own AI key — **Anthropic, OpenAI, Google Gemini, Groq, or Perplexity** —
pasted in the app, kept for the session only. The app links you to each provider's
key page (Gemini & Groq have free tiers; Perplexity Pro includes monthly API credits).

## 2 · Run the web app from source

```bash
git clone https://github.com/praneethgaddam07/resopt.git
cd resopt
./run_local.sh        # Windows: .\run_local.bat
```

Open <http://localhost:8000>, paste a key, and optimize. `FORCE_MOCK=1` runs the whole
pipeline with placeholder content (no key, no cost) for development. Tests: `pytest`.

---

## 3 · Install & Connect the Chrome Extension

To easily send job descriptions to the app, you need the companion Chrome extension.

1. Install the **RESOPT Chrome Extension** directly from the [Chrome Web Store](https://chromewebstore.google.com/detail/resopt-optimize-your-re/bbgacjcfjkmfcacimbkhelodlnegboej).
2. The extension needs to talk to the local RESOPT app securely using Native Messaging. Run the native messaging script to connect them:
   - **macOS**: Open Terminal and run `./packaging/install_mac.sh`
   - **Windows**: Double-click `install_windows.bat` (if downloaded via release zip) or run `packaging\install_windows.bat`.
   
   *When prompted for your Extension ID, paste:* `bbgacjcfjkmfcacimbkhelodlnegboej`
3. Restart your browser! The extension can now seamlessly talk to the desktop app securely without HTTP.

---

## How it works (short version)

Fit check (honest verdict + which gaps optimization can fix) → tailor (rephrase your
real bullets into the JD's language; a two-tier model router keeps the mechanical
steps on the cheap model) → **integrity guardrail** (deterministic: no unbacked
numbers, no AI-tell words) → per-portal ATS formatting → match-score report. The
fit check's fixable gaps feed straight into the optimizer; borderline tools are only
used after **you** confirm them.

## License

[MIT](LICENSE) — use it, fork it, self-host it.
