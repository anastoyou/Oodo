import hashlib
import hmac
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


DEFAULT_IG_SCOPES = (
    "instagram_business_basic,"
    "instagram_business_manage_messages,"
    "instagram_business_manage_comments,"
    "instagram_business_content_publish"
)


class CustomInstagramAccount(models.Model):
    _name = "custom.instagram.account"
    _description = "Unit Instagram Business Account (Instagram Login API)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "website_id asc, id asc"

    name = fields.Char(string="Unit / Account Label", required=True, tracking=True)
    active = fields.Boolean(default=True)
    website_id = fields.Many2one(
        "website",
        string="Business Unit (Website)",
        required=True,
        default=lambda self: self.env["website"].search([], limit=1),
        tracking=True,
        help="Each Website / Business Unit connects its own Instagram Business account and credentials.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    # Instagram Business identity (populated via Instagram Login OAuth / /me)
    ig_user_id = fields.Char(string="Instagram User ID (IGID)", tracking=True)
    ig_username = fields.Char(string="Instagram @Username", tracking=True)
    account_type = fields.Char(string="Account Type", readonly=True)

    # Instagram App with Instagram Login credentials (fallback cleanly to .env App settings)
    app_id = fields.Char(
        string="Instagram App ID",
        help="Optional per-unit override; defaults to INSTAGRAM_APP_ID from .env.",
    )
    app_secret = fields.Char(
        string="Instagram App Secret",
        groups="base.group_system",
        help="Optional per-unit override; defaults to INSTAGRAM_APP_SECRET from .env.",
    )
    api_version = fields.Char(string="Graph API Version", default="v22.0", required=True)
    oauth_scopes = fields.Char(string="OAuth Scopes", default=DEFAULT_IG_SCOPES, required=True)
    redirect_uri = fields.Char(
        string="OAuth Redirect URI",
        compute="_compute_endpoint_urls",
        help="Register this exact URL under Valid OAuth Redirect URIs in Meta App Dashboard.",
    )

    # Latest Long-Lived Token Lifecycle (60-day rolling refresh)
    access_token = fields.Char(string="Long-Lived Access Token", groups="base.group_system")
    token_type = fields.Selection(
        [("short_lived", "Short-Lived (1h)"), ("long_lived", "Long-Lived (60 Days)")],
        default="long_lived",
        readonly=True,
    )
    token_obtained_at = fields.Datetime(string="Token Obtained At", readonly=True)
    token_expires_at = fields.Datetime(string="Token Expires At", readonly=True, tracking=True)
    last_refreshed_at = fields.Datetime(string="Last Token Refresh", readonly=True)
    days_until_expiry = fields.Integer(string="Days Until Expiry", compute="_compute_token_status")
    connection_state = fields.Selection(
        [
            ("disconnected", "Disconnected"),
            ("connected", "Connected"),
            ("expiring_soon", "Expiring Soon (<15d)"),
            ("error", "Error / Expired"),
        ],
        string="Status",
        compute="_compute_token_status",
    )
    last_error = fields.Text(string="Last API Error", readonly=True)

    # Webhook Management
    public_base_url = fields.Char(
        string="Public Webhook / Tunnel URL",
        help="Optional public HTTPS origin (e.g. https://localapi.locanydm.online) for Meta Webhook & OAuth callbacks.",
    )
    webhook_url = fields.Char(
        string="Webhook Callback URL",
        compute="_compute_endpoint_urls",
        help="Paste into Meta App Dashboard -> Webhooks -> Instagram Callback URL.",
    )
    webhook_verify_token = fields.Char(
        string="Webhook Verify Token",
        help="Optional per-unit override; defaults to INSTAGRAM_WEBHOOK_VERIFY_TOKEN from .env.",
    )
    verify_signature = fields.Boolean(
        string="Verify X-Hub-Signature-256",
        default=True,
        help="Validates incoming Meta webhook POST payloads with App Secret HMAC-SHA256.",
    )
    subscribe_messages = fields.Boolean(string="Subscribe: DMs (messages)", default=True)
    subscribe_comments = fields.Boolean(string="Subscribe: Comments", default=True)
    subscribe_postbacks = fields.Boolean(string="Subscribe: Postbacks", default=True)
    webhook_subscribed_at = fields.Datetime(string="Webhooks Subscribed At", readonly=True)

    # Unit Automation & Sync Settings
    sandbox_mode = fields.Boolean(
        string="Local Simulation Mode",
        default=True,
        help="Simulates Instagram Graph API calls locally until live Meta credentials are configured.",
    )
    auto_sync_new_products = fields.Boolean(
        string="Auto-Sync New Unit Products",
        default=True,
        help="Automatically creates a tracked unit DM direct-link sync entry whenever a product is added to this unit.",
    )
    auto_publish_to_feed = fields.Boolean(
        string="Auto-Publish Feed Post on Sync",
        default=False,
        help="When enabled in live mode with a public HTTPS product image URL, also publishes an Instagram feed post via /{ig_user_id}/media.",
    )
    sync_shared_products = fields.Boolean(
        string="Include Shared Catalog Products",
        default=True,
        help="Sync products whose Website field is empty (shared across all units) into this unit's Instagram sync list.",
    )
    sync_service_products = fields.Boolean(
        string="Auto-Sync Service Products",
        default=False,
        help="Include Service products (e.g. Digital Services) during auto-sync; keeps internal POS/Gift Card/Down Payment utilities excluded when unchecked.",
    )
    use_cart_instant_checkout = fields.Boolean(
        string="Direct Buy Link Prefills Cart",
        default=False,
        help="When enabled, DM direct links use the tracked /ig/go/<sync_id>?instant=1 URL; otherwise opens the clean /shop/<product> page.",
    )
    auto_create_crm_lead = fields.Boolean(
        string="Auto-Create CRM Lead on Inbound DM",
        default=True,
    )
    default_utm_campaign = fields.Char(string="Default UTM Campaign", default="ig_dm_link")
    fallback_dm_text = fields.Text(
        string="Default Catalog DM Reply",
        default="Thanks for messaging {unit_name}! Browse all latest styles directly on our store: {unit_url}",
    )

    product_sync_count = fields.Integer(compute="_compute_counts")
    rule_count = fields.Integer(compute="_compute_counts")
    message_count = fields.Integer(compute="_compute_counts")
    webhook_log_count = fields.Integer(compute="_compute_counts")

    def _global_base_url(self):
        return (self.env["ir.config_parameter"].sudo().get_str("web.base.url") or "http://localhost:8069").rstrip("/")

    def _compute_endpoint_urls(self):
        global_base = self._global_base_url()
        for rec in self:
            base = (rec.public_base_url or global_base).strip().rstrip("/")
            rec.redirect_uri = f"{base}/instagram/oauth/callback"
            if rec.public_base_url:
                rec.webhook_url = f"{base}/api/crm/webhooks/instagram"
            else:
                rec.webhook_url = f"{base}/instagram/webhook/{rec.id}" if rec.id else f"{base}/instagram/webhook"

    @api.depends("access_token", "token_expires_at", "last_error", "sandbox_mode")
    def _compute_token_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.last_error:
                rec.connection_state = "error"
                rec.days_until_expiry = 0
                continue
            if not rec.access_token:
                rec.connection_state = "connected" if rec.sandbox_mode else "disconnected"
                rec.days_until_expiry = 60 if rec.sandbox_mode else 0
                continue
            if rec.token_expires_at:
                delta = (rec.token_expires_at - now).days
                rec.days_until_expiry = max(0, delta)
                if rec.token_expires_at <= now:
                    rec.connection_state = "error"
                elif delta <= 15:
                    rec.connection_state = "expiring_soon"
                else:
                    rec.connection_state = "connected"
            else:
                rec.days_until_expiry = 60
                rec.connection_state = "connected"

    def _compute_counts(self):
        Sync = self.env["custom.instagram.product.sync"]
        Rule = self.env["custom.instagram.rule"]
        Msg = self.env["custom.instagram.message"]
        Log = self.env["custom.instagram.webhook.log"]
        for rec in self:
            rec.product_sync_count = Sync.search_count([("account_id", "=", rec.id)])
            rec.rule_count = Rule.search_count([("account_id", "=", rec.id)])
            rec.message_count = Msg.search_count([("account_id", "=", rec.id)])
            rec.webhook_log_count = Log.search_count([("account_id", "=", rec.id)])

    def _unit_base_url(self):
        self.ensure_one()
        domain = (self.website_id.domain or "").strip() if self.website_id else ""
        if domain:
            if not domain.startswith(("http://", "https://")):
                domain = f"https://{domain}"
            return domain.rstrip("/")
        return self._global_base_url()

    def _sign_oauth_state(self):
        self.ensure_one()
        secret = self.env["ir.config_parameter"].sudo().get_str("database.secret") or "odoo-ig-secret"
        payload = str(self.id)
        sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        return f"{payload}:{sig}"

    @api.model
    def _verify_oauth_state(self, state):
        if not state or ":" not in state:
            return self.browse()
        raw_id, sig = state.split(":", 1)
        if not raw_id.isdigit():
            return self.browse()
        rec = self.sudo().browse(int(raw_id)).exists()
        if not rec:
            return self.browse()
        expected = rec._sign_oauth_state().split(":", 1)[1]
        return rec if hmac.compare_digest(sig, expected) else self.browse()

    @api.model
    def _read_env_setting(self, key, default=""):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
        env_path = Path(__file__).resolve().parents[3] / ".env"
        if env_path.is_file():
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
        return default

    def _effective_app_id(self):
        self.ensure_one()
        return (self.app_id or self._read_env_setting("INSTAGRAM_APP_ID")).strip()

    def _effective_app_secret(self):
        self.ensure_one()
        return (self.app_secret or self._read_env_setting("INSTAGRAM_APP_SECRET")).strip()

    def _effective_verify_token(self):
        self.ensure_one()
        return (self.webhook_verify_token or self._read_env_setting("INSTAGRAM_WEBHOOK_VERIFY_TOKEN")).strip()

    def verify_webhook_signature(self, raw_body, signature_header):
        self.ensure_one()
        app_secret = self._effective_app_secret()
        if not self.verify_signature or not app_secret:
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        received_sig = signature_header.split("=", 1)[1].strip()
        expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received_sig, expected)

    def _graph_request(self, method, path, params=None, json_body=None, use_bearer=False):
        self.ensure_one()
        version = (self.api_version or "v22.0").strip("/")
        clean_path = path.lstrip("/")
        url = f"https://graph.instagram.com/{version}/{clean_path}" if version else f"https://graph.instagram.com/{clean_path}"
        req_params = dict(params or {})
        headers = {}
        if use_bearer:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif "access_token" not in req_params:
            req_params["access_token"] = self.access_token

        try:
            resp = requests.request(method, url, params=req_params, json=json_body, headers=headers, timeout=15)
            data = resp.json() if resp.content else {}
        except requests.RequestException as exc:
            self.write({"last_error": str(exc)})
            return False, {"error": {"message": str(exc)}}

        if not resp.ok or "error" in data:
            err_msg = (data.get("error") or {}).get("message") or resp.text or f"HTTP {resp.status_code}"
            self.write({"last_error": err_msg})
            return False, data

        if self.last_error:
            self.write({"last_error": False})
        return True, data

    def action_open_oauth_login(self):
        self.ensure_one()
        app_id = self._effective_app_id()
        if not app_id:
            raise UserError(_("Enter your Instagram App ID (or set INSTAGRAM_APP_ID in .env) before connecting."))
        query = urlencode({
            "force_authentication": "1",
            "client_id": app_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.oauth_scopes or DEFAULT_IG_SCOPES,
            "state": self._sign_oauth_state(),
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"https://www.instagram.com/oauth/authorize?{query}",
            "target": "new",
        }

    def _exchange_oauth_code(self, code):
        self.ensure_one()
        app_id = self._effective_app_id()
        app_secret = self._effective_app_secret()
        if not (app_id and app_secret):
            raise UserError(_("Instagram App ID and App Secret (in record or .env) are required to exchange the OAuth code."))

        # Step 1: Exchange authorization code for short-lived token (Instagram Login API)
        resp = requests.post(
            "https://api.instagram.com/oauth/access_token",
            data={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code": code,
            },
            timeout=15,
        )
        short_data = resp.json() if resp.content else {}
        short_token = short_data.get("access_token")
        if not resp.ok or not short_token:
            err = short_data.get("error_message") or str(short_data)
            self.write({"last_error": err})
            raise UserError(_("Instagram OAuth code exchange failed: %s") % err)

        ig_user_id = str(short_data.get("user_id") or "")
        final_token = short_token
        token_type = "short_lived"
        expires_in = 3600

        # Step 2: Upgrade short-lived token to 60-day long-lived token via graph.instagram.com
        ll_resp = requests.get(
            "https://graph.instagram.com/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": app_secret,
                "access_token": short_token,
            },
            timeout=15,
        )
        ll_data = ll_resp.json() if ll_resp.content else {}
        if ll_resp.ok and ll_data.get("access_token"):
            final_token = ll_data["access_token"]
            token_type = "long_lived"
            expires_in = int(ll_data.get("expires_in") or 5183944)

        now = fields.Datetime.now()
        self.write({
            "access_token": final_token,
            "ig_user_id": ig_user_id or self.ig_user_id,
            "token_type": token_type,
            "token_obtained_at": now,
            "last_refreshed_at": now,
            "token_expires_at": now + timedelta(seconds=expires_in),
            "sandbox_mode": False,
            "last_error": False,
        })
        self.action_test_connection()
        self.message_post(body=_("Connected Instagram Business account via Instagram Login (%s).") % (self.ig_username or self.ig_user_id))
        return True

    def action_refresh_access_token(self):
        for rec in self:
            if rec.sandbox_mode and not rec.access_token:
                now = fields.Datetime.now()
                rec.write({
                    "token_type": "long_lived",
                    "token_obtained_at": rec.token_obtained_at or now,
                    "last_refreshed_at": now,
                    "token_expires_at": now + timedelta(days=60),
                    "last_error": False,
                })
                continue
            if not rec.access_token:
                raise UserError(_("Connect with Instagram Login or enter an access token before refreshing."))
            try:
                resp = requests.get(
                    "https://graph.instagram.com/refresh_access_token",
                    params={"grant_type": "ig_refresh_token", "access_token": rec.access_token},
                    timeout=15,
                )
                data = resp.json() if resp.content else {}
            except requests.RequestException as exc:
                rec.write({"last_error": str(exc)})
                raise UserError(_("Token refresh network error: %s") % exc) from exc

            if not resp.ok or not data.get("access_token"):
                err = (data.get("error") or {}).get("message") or str(data)
                rec.write({"last_error": err})
                raise UserError(_("Instagram token refresh failed: %s") % err)

            now = fields.Datetime.now()
            expires_in = int(data.get("expires_in") or 5183944)
            rec.write({
                "access_token": data["access_token"],
                "token_type": "long_lived",
                "last_refreshed_at": now,
                "token_expires_at": now + timedelta(seconds=expires_in),
                "last_error": False,
            })
            rec.message_post(body=_("Refreshed 60-day Instagram Login access token (expires %s).") % rec.token_expires_at)
        return True

    def action_test_connection(self):
        for rec in self:
            if rec.sandbox_mode or not rec.access_token:
                now = fields.Datetime.now()
                rec.write({
                    "ig_user_id": rec.ig_user_id or f"178414000{rec.id:05d}",
                    "ig_username": rec.ig_username or f"{(rec.website_id.name or 'unit').lower().replace(' ', '_')}_official",
                    "account_type": "BUSINESS",
                    "token_obtained_at": rec.token_obtained_at or now,
                    "token_expires_at": rec.token_expires_at or (now + timedelta(days=60)),
                    "last_error": False,
                })
                continue
            ok, data = rec._graph_request(
                "GET",
                "me",
                params={"fields": "user_id,username,name,account_type"},
            )
            if not ok:
                raise UserError(_("Profile check failed: %s") % (data.get("error", {}).get("message") or data))
            rec.write({
                "ig_user_id": str(data.get("user_id") or data.get("id") or rec.ig_user_id or ""),
                "ig_username": data.get("username") or rec.ig_username,
                "account_type": data.get("account_type") or rec.account_type,
                "last_error": False,
            })
        return True

    def action_subscribe_webhooks(self):
        for rec in self:
            fields_list = []
            if rec.subscribe_messages:
                fields_list.append("messages")
            if rec.subscribe_comments:
                fields_list.append("comments")
            if rec.subscribe_postbacks:
                fields_list.append("messaging_postbacks")
            if not fields_list:
                raise UserError(_("Select at least one webhook subscription field."))

            if rec.sandbox_mode or not (rec.access_token and rec.ig_user_id):
                rec.write({"webhook_subscribed_at": fields.Datetime.now(), "last_error": False})
                rec.message_post(body=_("Simulated webhook subscription for fields: %s") % ", ".join(fields_list))
                continue

            ok, data = rec._graph_request(
                "POST",
                f"{rec.ig_user_id}/subscribed_apps",
                params={"subscribed_fields": ",".join(fields_list)},
            )
            if not ok:
                raise UserError(_("Webhook subscription failed: %s") % (data.get("error", {}).get("message") or data))
            rec.write({"webhook_subscribed_at": fields.Datetime.now(), "last_error": False})
            rec.message_post(body=_("Subscribed Instagram webhooks on Meta: %s") % ", ".join(fields_list))
        return True

    def action_sync_all_unit_products(self):
        Sync = self.env["custom.instagram.product.sync"]
        Product = self.env["product.template"]
        for rec in self:
            domain = [
                ("sale_ok", "=", True),
                ("website_id", "in", [rec.website_id.id, False] if rec.sync_shared_products else [rec.website_id.id]),
            ]
            if not rec.sync_service_products:
                domain.append(("type", "!=", "service"))
            products = Product.search(domain)
            Sync.sync_products_for_account(rec, products)
        return True

    def action_simulate_test_webhook(self):
        self.ensure_one()
        sample_rule = self.env["custom.instagram.rule"].search(
            [("account_id", "=", self.id), ("active", "=", True)],
            limit=1,
        )
        keyword = (sample_rule.keywords or "LINK").split(",")[0].strip() if sample_rule else "LINK"
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": self.ig_user_id or f"178414000{self.id:05d}",
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": f"sim_cmt_{self.id}_{int(fields.Datetime.now().timestamp())}",
                                "text": f"Hi please share {keyword}",
                                "from": {"id": "17899000112233", "username": "demo_shopper_in"},
                            },
                        }
                    ],
                }
            ],
        }
        log = self.env["custom.instagram.webhook.log"].ingest_payload(self, payload, event_type="comments", is_simulated=True)
        return {
            "type": "ir.actions.act_window",
            "name": _("Webhook Event & Auto-DM Result"),
            "res_model": "custom.instagram.webhook.log",
            "view_mode": "form",
            "res_id": log.id,
        }

    def action_view_product_syncs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Unit Product Syncs"),
            "res_model": "custom.instagram.product.sync",
            "view_mode": "list,form",
            "domain": [("account_id", "=", self.id)],
            "context": {"default_account_id": self.id},
        }

    def action_view_rules(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Direct-Link DM Rules"),
            "res_model": "custom.instagram.rule",
            "view_mode": "list,form",
            "domain": [("account_id", "=", self.id)],
            "context": {"default_account_id": self.id},
        }

    def action_view_messages(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Instagram DM & Comment Inbox"),
            "res_model": "custom.instagram.message",
            "view_mode": "list,form",
            "domain": [("account_id", "=", self.id)],
            "context": {"default_account_id": self.id},
        }

    def action_view_webhook_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Webhook Event Logs"),
            "res_model": "custom.instagram.webhook.log",
            "view_mode": "list,form",
            "domain": [("account_id", "=", self.id)],
            "context": {"default_account_id": self.id},
        }

    @api.model
    def cron_refresh_instagram_tokens(self):
        now = fields.Datetime.now()
        cutoff_expiry = now + timedelta(days=15)
        cutoff_age = now - timedelta(hours=24)
        accounts = self.search([
            ("active", "=", True),
            ("sandbox_mode", "=", False),
            ("access_token", "!=", False),
            ("token_expires_at", "<=", cutoff_expiry),
        ])
        for acc in accounts:
            if acc.last_refreshed_at and acc.last_refreshed_at > cutoff_age:
                continue
            try:
                acc.action_refresh_access_token()
            except Exception:
                continue
