import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CustomInstagramController(http.Controller):
    """Handles Instagram Login OAuth callbacks, Meta Webhooks, and Tracked Direct DM Links."""

    @http.route(["/instagram/oauth/callback"], type="http", auth="user", methods=["GET"], website=False)
    def instagram_oauth_callback(self, code="", state="", error="", error_description="", **kwargs):
        account = request.env["custom.instagram.account"]._verify_oauth_state(state)
        if error:
            if account:
                account.sudo().write({"last_error": f"{error}: {error_description}"})
            return request.make_response(
                f"Instagram Login failed: {error} - {error_description}",
                status=400,
                headers=[("Content-Type", "text/plain")],
            )
        if not account or not code:
            return request.make_response(
                "Missing or invalid Instagram OAuth state/code.",
                status=400,
                headers=[("Content-Type", "text/plain")],
            )
        # Strip optional Meta OAuth '#_' suffix from authorization code
        clean_code = code.split("#", 1)[0].strip()
        account.sudo()._exchange_oauth_code(clean_code)
        return request.redirect(f"/odoo/custom.instagram.account/{account.id}")

    @http.route(
        [
            "/instagram/webhook",
            "/instagram/webhook/<int:account_id>",
            "/api/crm/webhooks/instagram",
            "/api/crm/webhooks/instagram/<int:account_id>",
        ],
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=False,
    )
    def instagram_webhook(self, account_id=None, **kwargs):
        Account = request.env["custom.instagram.account"].sudo()
        account = Account.browse(account_id).exists() if account_id else Account.browse()

        if request.httprequest.method == "GET":
            mode = kwargs.get("hub.mode")
            token = (kwargs.get("hub.verify_token") or "").strip()
            challenge = kwargs.get("hub.challenge", "")
            env_token = Account._read_env_setting("INSTAGRAM_WEBHOOK_VERIFY_TOKEN")

            if mode is None and not token:
                active_accs = Account.search([("active", "=", True)])
                return request.make_json_response({
                    "status": "ready",
                    "endpoint": request.httprequest.path,
                    "verify_token_configured": bool(env_token or any(a._effective_verify_token() for a in active_accs)),
                })

            matched = Account.browse()
            if account and token and token == account._effective_verify_token():
                matched = account
            elif not account and token:
                active_accs = Account.search([("active", "=", True)])
                matched = active_accs.filtered(lambda a: a._effective_verify_token() == token)[:1]
                if not matched and env_token and token == env_token:
                    matched = active_accs[:1]
            verified_via_env = bool(not account and env_token and token == env_token)
            if mode == "subscribe" and (matched or verified_via_env):
                request.env["custom.instagram.webhook.log"].sudo().create({
                    "name": "Webhook Subscription Verified",
                    "account_id": matched.id if matched else False,
                    "event_type": "verification",
                    "signature_valid": True,
                    "process_status": "processed",
                    "result_summary": "Meta hub.challenge verified successfully.",
                })
                return request.make_response(challenge, [("Content-Type", "text/plain")])
            return request.make_response("Forbidden", status=403)

        raw_body = request.httprequest.data or b""
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except ValueError:
            payload = {}

        if not account:
            entry_id = str(((payload.get("entry") or [{}])[0]).get("id") or "")
            if entry_id:
                account = Account.search([("active", "=", True), ("ig_user_id", "=", entry_id)], limit=1)
            if not account:
                account = Account.search([("active", "=", True)], limit=1)

        sig_header = request.httprequest.headers.get("X-Hub-Signature-256", "")
        sig_ok = account.verify_webhook_signature(raw_body, sig_header) if account else False

        request.env["custom.instagram.webhook.log"].sudo().ingest_payload(
            account,
            payload,
            signature_valid=sig_ok,
        )
        if account and not sig_ok:
            return request.make_response("Invalid Signature", status=403)
        return request.make_json_response({"status": "ok"})

    @http.route(["/ig/go/<int:sync_id>"], type="http", auth="public", methods=["GET"], website=True)
    def instagram_direct_product_redirect(self, sync_id, instant="0", **kwargs):
        sync = request.env["custom.instagram.product.sync"].sudo().browse(sync_id).exists()
        if not sync:
            return request.redirect("/shop")
        sync.write({"dm_click_count": sync.dm_click_count + 1})

        if str(instant) == "1" and sync.product_tmpl_id.product_variant_id:
            order_sudo = request.cart or request.env.website._create_cart()
            order_sudo.with_context(skip_cart_verification=True)._cart_add(
                product_id=sync.product_tmpl_id.product_variant_id.id,
                quantity=1,
            )
            return request.redirect("/shop/cart")
        target = sync.direct_shop_url or "/shop"
        return request.redirect(target, local=not target.startswith(("http://", "https://")))

