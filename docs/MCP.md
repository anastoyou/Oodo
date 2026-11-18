Analyzed __main__.py:L100-153
Searched "Claude Code" web OR "claude.ai" remote MCP server streamable-http custom connector URL
Ran check exact streamable-http path in mcp-server-odoo
Analyzed server.py:L350-405

**Claude Code on the web (`claude.ai/code`)** runs in Anthropic's cloud, so it cannot run local `stdio` (`uvx`) commands—it connects only to a **public HTTPS Streamable HTTP MCP URL** (`https://<your-mcp-host>/mcp`).

Your installed `mcp-server-odoo` already supports `streamable-http`, and your dev `cloudflared` tunnel can expose it securely over HTTPS.

---

### Step 1: Run `mcp-server-odoo` in Streamable HTTP Mode

Start a local HTTP MCP server on port `8000` (with DNS-rebinding allowlist set via `ODOO_MCP_ALLOWED_HOSTS`):

```powershell
$env:ODOO_MCP_ALLOWED_HOSTS = "mcp.locanydm.online,localhost"
uvx --env-file e:\Code\Oodo\.env mcp-server-odoo --transport streamable-http --host 127.0.0.1 --port 8000
```

- It listens on `http://127.0.0.1:8000/mcp`.
- Make sure Odoo is running (`.\.venv\Scripts\python.exe .\odoo\odoo-bin -c .\odoo.conf`).

---

### Step 2: Expose `mcp.locanydm.online` via Cloudflare Tunnel

1. Add a dedicated subdomain ingress rule in [config.yml](file:///e:/Code/Oodo/cloudflared/config.yml) **before** `- service: http_status:404`:
   ```yaml
     - hostname: mcp.locanydm.online
       service: http://host.docker.internal:8000
   ```
2. Restart `cloudflared` and register its Cloudflare DNS CNAME:
   ```powershell
   docker compose restart cloudflared
   docker exec odoo-dev-cloudflared cloudflared tunnel --origincert /etc/cloudflared/cert.pem route dns 581546da-4698-416a-8bef-a5f349941ef0 mcp.locanydm.online
   ```

---

### Step 3: Secure It Before Connecting! *(Important)*

`mcp-server-odoo`'s `streamable-http` mode has **no built-in HTTP authentication** of its own. With `ODOO_YOLO=true` in [.env](file:///e:/Code/Oodo/.env#L21), anyone on the internet who finds `https://mcp.locanydm.online/mcp` could read/write your Odoo data unless you put auth in front of it:

- Recommended: Add a **Cloudflare Access / Zero Trust policy** (or Cloudflare Worker / OAuth proxy) in front of `mcp.locanydm.online`, **or** keep `ODOO_YOLO=read` and use a secret randomized subdomain/path when testing.

---

### Step 4: Connect in Claude Web / Claude Code

1. Open **Claude (`claude.ai`) → Settings → Connectors → Add custom connector** (for `claude.ai` / Claude Code on web).
2. Enter your remote MCP URL:
   ```text
   https://mcp.locanydm.online/mcp
   ```
3. Under **Advanced settings**, add your OAuth / authentication token headers if protected behind Cloudflare Access/proxy, then click **Add**.
4. *(If using Claude Code CLI locally instead of web, local stdio works directly without exposing any port:)*
   ```bash
   claude mcp add --transport http odoo-remote https://mcp.locanydm.online/mcp
   ```

If you want me to add the `mcp.locanydm.online` route to [config.yml](file:///e:/Code/Oodo/cloudflared/config.yml) and register its DNS CNAME now, let me know.