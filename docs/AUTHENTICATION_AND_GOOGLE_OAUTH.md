# Adding Google Sign-In & Custom Authentication

---

## 1. Current Authentication Setup in This Project

* **Already installed in `zoeemasterdb`:** `auth_signup` (`auth_signup.invitation_scope = b2c` — customer self-signup enabled), `auth_passkey` + `auth_passkey_portal` (Passkeys), and `auth_totp` + `auth_totp_portal` (2FA).
* **Already styled in `addons/custom_store/`:** [`views/portal_templates.xml`](../addons/custom_store/views/portal_templates.xml) customizes `/web/login` and `/web/signup` via `website.login_layout`, `web.login`, and `auth_signup.signup`.
* **Built-in OAuth2 ready on disk:** `odoo/addons/auth_oauth/` (currently `uninstalled`), which already ships pre-configured provider records in [`auth_oauth_data.xml`](../odoo/addons/auth_oauth/data/auth_oauth_data.xml) for **Google OAuth2** (`auth_oauth.provider_google`) and **Facebook Graph** (`auth_oauth.provider_facebook`).

---

## 2. Option A: Enable Google Authentication (No Custom Python Needed)

1. **Install `auth_oauth`:**
   * Add `"auth_oauth"` to `depends` in [`addons/custom_store/__manifest__.py`](../addons/custom_store/__manifest__.py) (recommended so production installs it automatically) and run:
     ```bat
     .\upgrade.bat --skip-pull
     .\start.bat
     ```
   * *(Or install once via `.\upgrade.bat --skip-pull --install --modules auth_oauth`, or tick **Settings → General Settings → Integrations → OAuth Authentication**).*
2. **Create a Google OAuth 2.0 Client ID (Google Cloud Console):**
   * Choose **Web application**.
   * Add **Authorized JavaScript origins** (e.g. `http://localhost:8069` in dev, `https://yourbrand.in` in production).
   * Add **Authorized redirect URIs** matching Odoo's OAuth callback route ([`auth_oauth/controllers/main.py`](../odoo/addons/auth_oauth/controllers/main.py)):
     * Local: `http://localhost:8069/auth_oauth/signin`
     * Production: `https://yourbrand.in/auth_oauth/signin`
3. **Configure Google Sign-In in Odoo:**
   * Open **Settings → General Settings → Integrations**, enable **Google Authentication** (`auth_oauth_google_enabled`), paste the **Client ID** (`auth_oauth_google_client_id`), and click **Save**.
   * `auth_oauth` automatically adds enabled provider buttons into `web.login_oauth` on `/web/login` and `/web/signup`.
   * **Important URL note:** Odoo computes `redirect_uri` from the active request host (`request.httprequest.url_root + 'auth_oauth/signin'`). Keep Google's Authorized Redirect URI aligned with the domain/URL you browse from (note that temporary `trycloudflare.com` quick tunnels change hostnames on restart; also check `web.base.url` under System Parameters in production).

---

## 3. Option B: Add Other Implicit OAuth2 Providers (Zero Code)

With `auth_oauth` installed and Developer Mode active, go to **Settings → Users & Companies → OAuth Providers** (`auth.oauth.provider`) or load `<record model="auth.oauth.provider">` XML inside `addons/custom_store/` (or a custom `addons/custom_auth/` module):

* Set `client_id`, `auth_endpoint`, `scope`, `validation_endpoint`, optional `data_endpoint`, button label (`body`), and `css_class`.
* If a provider expects `Authorization: Bearer <token>` instead of `?access_token=...` on `validation_endpoint` / `data_endpoint`, set System Parameter `auth_oauth.authorization_header = True` (supported in `odoo/addons/auth_oauth/models/res_users.py`).

---

## 4. Option C: Custom Authentication in `addons/` (WhatsApp/SMS OTP, Code-Flow OAuth, Custom SSO)

For **mobile/WhatsApp OTP login**, **OAuth2 Authorization Code Flow (`response_type=code` + `client_secret`)**, or custom SSO, implement a module in `addons/` (for example `addons/custom_auth/` or inside `addons/custom_store/`) using these 3 Odoo `20.0` hooks:

1. **Login / Signup UI (`views/*.xml`):**
   * Inherit `web.login` or `web.login_oauth` to add your OTP field, custom login tab, or redirect button (matching `addons/custom_store/views/portal_templates.xml`).
2. **Credential Verification (`models/res_users.py`):**
   * Inherit `res.users` and override `_check_credentials(self, credential, env)` ([`base/models/res_users.py`](../odoo/odoo/addons/base/models/res_users.py#L313), [`auth_oauth/models/res_users.py`](../odoo/addons/auth_oauth/models/res_users.py#L152)):
     ```python
     from odoo import models
     from odoo.exceptions import AccessDenied

     class ResUsers(models.Model):
         _inherit = "res.users"

         def _check_credentials(self, credential, env):
             try:
                 return super()._check_credentials(credential, env)
             except AccessDenied:
                 if credential.get("type") != "custom_otp":
                     raise
                 # Verify token / OTP stored for self.env.user
                 if self._verify_custom_otp(credential.get("token")):
                     return {"uid": self.env.user.id, "auth_method": "custom_otp", "mfa": "default"}
                 raise
     ```
3. **HTTP Auth Routes & Session Sign-In (`controllers/*.py`):**
   * Expose public HTTP routes (e.g. `/auth/otp/request`, `/auth/otp/verify`, or `/auth/oidc/callback` to exchange a `code` with a server-side `client_secret`), resolve or create the portal `res.users` record when self-signup is allowed (`auth_signup`), then sign into the session via `odoo.http.session.authenticate(request.session, request.env, credential)` and redirect with `_get_login_redirect_url(...)` (same pattern as [`auth_oauth/controllers/main.py`](../odoo/addons/auth_oauth/controllers/main.py#L125-L133)).
   * **Security checklist:** Keep `client_secret` and OTP provider keys in `.env` or System Parameters (never committed to Git), enforce HTTPS behind Nginx ([`deploy/nginx.conf`](../deploy/nginx.conf)) in production, and rate-limit / expire OTP tokens.

