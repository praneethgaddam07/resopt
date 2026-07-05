# Deploy RESOPT (one time, free)

Hosts RESOPT so friends can use it. **Free:** the AI runs on each friend's own
Claude / ChatGPT / Perplexity, and Render's free tier hosts our (deterministic) engine at $0.
No database, nothing stored.

## One-click deploy
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/praneethgaddam07/resume-optimizer)

1. Click the button → **sign in to Render** (free; use "Sign in with GitHub" — no credit card).
2. **Authorize Render** to read the `resume-optimizer` repo. Render reads `render.yaml` and
   sets up the **`resopt-mcp`** connector service (the website is not deployed by this blueprint).
3. Click **Apply** and wait until **`resopt-mcp`** shows **Live**.
4. Copy its URL, e.g. `https://resopt-mcp-xxxx.onrender.com`.
5. Open **`resopt-mcp` → Environment** → set **`RESOPT_PUBLIC_URL`** to that exact URL → **Save**
   (it redeploys once, ~1 min).

**Your shareable connector URL:** `https://resopt-mcp-xxxx.onrender.com/mcp`

Send that URL back and it goes into the README + the friend PDF.

## How friends add it
- **Claude** (Pro) / **Perplexity** (Pro): Settings → Connectors → *Add custom connector* → paste the URL.
- **ChatGPT**: via the App Directory after submission (see CONNECTOR.md).

## Good to know
- Free tier **sleeps after ~15 min idle**; the first request then takes ~1 min to wake. Fine for testing.
- **No database** in RESOPT, so Render's "free DB expires in 30 days" warning does **not** apply.
- Want to remove the cold-start later? Render Starter is ~**$7/mo**. Not needed now.
