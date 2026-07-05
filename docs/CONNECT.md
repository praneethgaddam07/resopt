# Use RESOPT with the AI you already have (free — no API key)

RESOPT tailors your **real** résumé to any job so it passes ATS screening — it never
invents experience, and it shows you your ATS match score. It runs inside your own
Claude or Perplexity subscription.

**Your connector URL:**

> ### `https://resopt-mcp.onrender.com/mcp`

## Claude (Pro/Max — web or desktop app)

1. Go to **claude.ai** → click your initials (bottom-left) → **Settings** → **Connectors**.
2. Click **Add custom connector**.
3. Name: `RESOPT` · URL: `https://resopt-mcp.onrender.com/mcp` → **Add** (no login needed).
4. Open a **new chat** → click the **search & tools** (sliders) icon → toggle **RESOPT** on.

## Perplexity (Pro/Max)

1. **Settings** → **Connectors** → **Add connector**.
2. Pick the custom/advanced option, name it `RESOPT`, paste the same URL → **Save**.
3. Enable RESOPT as a source/tool in your thread.

## Then use it (both apps)

Paste your **résumé text** and the **job description** into the chat and say:

> *“Use RESOPT to optimize my résumé for this job. Target portal: Workday.”*

(or Greenhouse, iCIMS, SmartRecruiters… — ask it to `list_ats_portals` if unsure.
Add *“and write a cover letter”* if you want one.)

Approve the RESOPT tool calls when your AI asks permission. You'll get an **ATS match
score**, honest gap notes, and a **.docx download link**.

⏱ **Download links expire after ~15 minutes** — if you miss one, just ask your AI to
run `format_resume` again.

## Good to know

- **Privacy:** your résumé is processed by *your own* AI subscription. RESOPT's server
  only runs deterministic checks (ATS scoring, truthful tool mapping, formatting) and
  stores **nothing** — generated files auto-delete after 15 minutes. Don't want to
  trust our server at all? The code is open (MIT) — **self-host the connector**:
  see [CONNECTOR.md](../CONNECTOR.md), or run it locally inside Claude Desktop:

  ```jsonc
  // claude_desktop_config.json  (first: pip install -r requirements-mcp.txt)
  { "mcpServers": { "resopt": {
      "command": "python", "args": ["/path/to/resume-optimizer/mcp_server.py"] } } }
  ```

- **It will never fabricate.** Genuinely missing skills are flagged to *you* — never
  faked on paper.
- **ChatGPT:** not yet — coming via the app directory.
- **No Claude/Perplexity Pro?** Use the free **desktop app** instead (bring your own
  API key — Gemini and Groq have free tiers): see the
  [main README](../README.md#1--download-the-desktop-app-easiest).
