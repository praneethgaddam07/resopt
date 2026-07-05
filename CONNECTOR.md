# RESOPT — MCP Connector

Runs the RESOPT ATS engine on the user's **own** Claude / ChatGPT / Perplexity subscription.
No API key. Their model does the writing; our deterministic engine does the ATS work
(JD keywords, scoring, truthful tool coverage, integrity checks, the 8-portal `.docx`).

The engine (`app/`) stays private on the server — users add a **URL**, never source.

## What it exposes (MCP tools)

| Tool | Purpose |
|---|---|
| `optimization_guide` | The RESOPT method the host model follows (résumé + cover letter). No fit check. |
| `extract_keywords` / `list_ats_portals` | JD keywords; supported ATS portals |
| `check_tool_coverage` | Truthful tool mapping (surfaces the candidate's own tool, never invents) |
| `score_resume` | ATS match score — called **after** customizing |
| `format_resume` / `format_cover_letter` | Build the ATS-safe `.docx` (integrity folded in) |

Token-frugal by design: brief outputs, one pass, no résumé re-prints — it's the user's own usage.

## Run it

**Local (Claude Desktop)** — saves the `.docx` to `~/Downloads`:
```bash
pip install "mcp[cli]"
python mcp_server.py            # stdio
```
Then add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{ "mcpServers": { "resopt": {
    "command": "/ABS/PATH/.venv/bin/python",
    "args": ["/ABS/PATH/mcp_server.py"] } } }
```

**Remote (hosted)** — returns a download URL instead of writing to disk:
```bash
RESOPT_PUBLIC_URL=https://your-host python mcp_server.py --http
```
- MCP endpoint: `https://your-host/mcp`
- File downloads: `https://your-host/files/{token}` (15-min TTL)
- Health: `https://your-host/health`

## Deploy (Render)

`render.yaml` defines a `resopt-mcp` service. Deploy the Blueprint, then set
`RESOPT_PUBLIC_URL` to the service's own `https://…onrender.com` URL and redeploy.

## Add it to an AI app (users)

- **Claude** (web/Desktop): Settings → Connectors → add custom connector → `https://your-host/mcp`  *(no review gate — fastest)*
- **ChatGPT**: submit as an App (identity verification + review)
- **Perplexity**: add custom connector (Pro/Max/Enterprise)

Then: paste your résumé + the job description → *"optimize my résumé for this job"* (and
*"write a cover letter"* if you want one) → download the `.docx`.

## Next: OAuth
For real users, add auth via FastMCP's `auth_server_provider` / `token_verifier` before
public listing. (Claude custom connectors also support OAuth.)
