<p align="center"><img src="icon.png" width="110" alt="RESOPT"/></p>

<h1 align="center">RESOPT</h1>
<p align="center"><i>The résumé, rewritten for the job you actually want — truthfully.</i></p>

## Install

**macOS (Apple Silicon)** — paste into Terminal to download, install, and launch:

```bash
curl -L -o /tmp/RESOPT.zip https://github.com/praneethgaddam07/resopt/releases/latest/download/RESOPT-macOS.zip && unzip -o /tmp/RESOPT.zip -d /Applications && xattr -dr com.apple.quarantine /Applications/RESOPT.app && open /Applications/RESOPT.app
```

**Windows** — [download **RESOPT.exe**](../../releases/latest/download/RESOPT.exe) and run it.

Prefer clicking? Grab the [latest release](../../releases/latest) directly. If macOS
blocks it as from an *unidentified developer*, right-click **RESOPT** in Applications →
**Open** → **Open** (once). The Terminal command above already handles this for you.

## What it does

RESOPT tailors your **real** résumé (and a cover letter, if you want one) to a specific
job description so it passes **ATS** screening — and it **never invents experience,
tools, employers, or metrics**. You get an honest fit check, a rewritten résumé with a
live ATS match score, and a clean single-column `.docx` or `.pdf`.

- 🔒 **Nothing stored, ever.** Bring your own AI key — it lives in memory for the
  session and is never saved or sent anywhere else.
- ✅ **Truth-guarded.** Invented metrics and AI-tell words are stripped before the
  document is built; genuinely missing skills are flagged to you — never faked.
- 🎯 **11 ATS portals** (Workday, Taleo, ADP, Greenhouse, Lever, iCIMS, Paycor,
  Ashby, SAP SuccessFactors, SmartRecruiters, BambooHR) with per-portal formatting rules.

## Your AI key

Works with **Anthropic, OpenAI, Google Gemini, Groq, or Perplexity** — the app links
you to each provider's key page. Gemini & Groq have free tiers; Perplexity Pro
includes monthly API credits. Free-tier keys automatically fall back to the best
model your tier serves.

## Privacy

Your key and résumé are processed in memory for the request and scrubbed — no
database, no disk, no logs. The key is session-only: cleared when you close the app.
