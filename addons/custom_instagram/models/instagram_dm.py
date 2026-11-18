import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


DEFAULT_DM_REPLY = (
    "Hi! Here is the direct buy link for {product_name} ({price}) from {unit_name}:\n"
    "{buy_link}\n"
    "COD & Prepaid available. Tap the link to order in 30 seconds!"
)


class CustomInstagramRule(models.Model):
    _name = "custom.instagram.rule"
    _description = "Meesho-Style Comment-to-DM & Keyword Auto-Link Rule"
    _order = "sequence asc, id asc"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Rule Name", required=True)
    active = fields.Boolean(default=True)
    account_id = fields.Many2one(
        "custom.instagram.account",
        string="Unit Instagram Account",
        required=True,
        ondelete="cascade",
    )
    website_id = fields.Many2one(related="account_id.website_id", string="Business Unit", store=True)
    trigger_on = fields.Selection(
        [("both", "Comments & DMs"), ("comment", "Post / Reel Comments Only"), ("dm", "Direct Messages Only")],
        default="both",
        required=True,
    )
    keywords = fields.Char(
        string="Trigger Keywords (comma-separated)",
        required=True,
        default="LINK, PRICE, PP, BUY",
        help="Case-insensitive keywords (e.g. LINK, PRICE, KURTI). Leave exact product SKU keywords blank here if using Product Sync auto-match.",
    )
    match_mode = fields.Selection(
        [("contains", "Contains Keyword"), ("exact", "Exact Text Match")],
        default="contains",
        required=True,
    )
    product_sync_id = fields.Many2one(
        "custom.instagram.product.sync",
        string="Specific Product Direct Link",
        domain="[('account_id', '=', account_id)]",
        help="Optional: pin this rule to one product. Leave empty to automatically match a synced unit product by text/SKU or fall back to the latest synced product.",
    )
    use_generic_card = fields.Boolean(
        string="Send Interactive Product Card in DM",
        default=True,
        help="Uses Meta Generic Template card with product image and 'Buy Now' button in active DM conversations (text link used automatically for comment private replies).",
    )
    reply_template = fields.Text(
        string="DM Message Template",
        default=DEFAULT_DM_REPLY,
        required=True,
        help="Available placeholders: {product_name}, {price}, {buy_link}, {unit_name}, {keyword}",
    )
    auto_create_lead = fields.Boolean(string="Create CRM Lead", default=True)
    trigger_count = fields.Integer(string="Times Triggered", default=0, readonly=True)

    def _matches_text(self, text, event_kind):
        self.ensure_one()
        if self.trigger_on == "comment" and event_kind != "comment":
            return False
        if self.trigger_on == "dm" and event_kind != "dm":
            return False
        cleaned = (text or "").strip().lower()
        if not cleaned:
            return False
        tokens = [k.strip().lower() for k in (self.keywords or "").split(",") if k.strip()]
        if self.match_mode == "exact":
            return cleaned in tokens
        return any(tok in cleaned for tok in tokens)

    def _resolve_sync_product(self, incoming_text):
        self.ensure_one()
        if self.product_sync_id:
            return self.product_sync_id
        return self.env["custom.instagram.webhook.log"]._match_sync_product_from_text(self.account_id, incoming_text)

    def _render_reply(self, sync_rec):
        self.ensure_one()
        tmpl_text = self.reply_template or DEFAULT_DM_REPLY
        if not sync_rec:
            unit_name = self.website_id.name or self.account_id.name
            unit_url = f"{self.account_id._unit_base_url()}/shop"
            fallback = self.account_id.fallback_dm_text or "Browse {unit_name}: {unit_url}"
            return fallback.format(unit_name=unit_name, unit_url=unit_url)

        use_instant = self.account_id.use_cart_instant_checkout
        link = f"{sync_rec.tracked_dm_url}?instant=1" if use_instant else sync_rec.tracked_dm_url
        symbol = sync_rec.currency_id.symbol or "₹"
        return tmpl_text.format(
            product_name=sync_rec.name or sync_rec.product_tmpl_id.name,
            price=f"{symbol}{sync_rec.list_price:,.0f}",
            buy_link=link,
            unit_name=self.website_id.name or self.account_id.name,
            keyword=sync_rec.keyword_code or "",
        )


class CustomInstagramMessage(models.Model):
    _name = "custom.instagram.message"
    _description = "Instagram DM & Comment Private Reply Log"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="Reference", readonly=True, default="New")
    direction = fields.Selection(
        [("inbound", "Inbound"), ("outbound", "Outbound")],
        default="outbound",
        required=True,
    )
    channel_event = fields.Selection(
        [
            ("dm", "Direct Message"),
            ("comment_reply", "Comment Private Reply -> DM"),
            ("comment", "Inbound Post/Reel Comment"),
            ("postback", "DM Button Postback"),
        ],
        default="dm",
        required=True,
    )
    account_id = fields.Many2one(
        "custom.instagram.account",
        string="Unit Instagram Account",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env["custom.instagram.account"].search([("active", "=", True)], limit=1),
    )
    website_id = fields.Many2one(related="account_id.website_id", string="Business Unit", store=True)
    sender_ig_id = fields.Char(string="Customer IG User ID (IGSID)")
    sender_username = fields.Char(string="Customer @Handle")
    comment_id = fields.Char(string="IG Comment ID", index=True)
    media_id = fields.Char(string="IG Media ID")
    is_echo = fields.Boolean(string="From IG Echo", default=False, readonly=True)

    partner_id = fields.Many2one("res.partner", string="CRM Contact")
    lead_id = fields.Many2one("crm.lead", string="Linked CRM Lead")
    product_sync_id = fields.Many2one(
        "custom.instagram.product.sync",
        string="Synced Product",
        domain="[('account_id', '=', account_id)]",
    )
    rule_id = fields.Many2one("custom.instagram.rule", string="Matched Automation Rule")

    body = fields.Text(string="Message Text", required=True)
    direct_link_url = fields.Char(string="Direct Checkout Link Sent")
    use_generic_card = fields.Boolean(string="Send Product Card (DM)", default=True)
    state = fields.Selection(
        [("draft", "Draft"), ("sent", "Sent / Simulated"), ("received", "Received"), ("failed", "Failed")],
        default="draft",
        tracking=True,
    )
    external_message_id = fields.Char(string="Meta Message ID (MID)", readonly=True, index=True)
    error_message = fields.Char(string="Error", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.instagram.message") or "IG"
        return super().create(vals_list)

    def _build_dm_payload(self):
        self.ensure_one()
        link = self.direct_link_url
        if not link and self.product_sync_id:
            link = (
                f"{self.product_sync_id.tracked_dm_url}?instant=1"
                if self.account_id.use_cart_instant_checkout
                else self.product_sync_id.tracked_dm_url
            )
        text = self.body or ""
        if link and link not in text:
            text = f"{text}\n{link}".strip()

        # Comment Private Reply MUST use recipient.comment_id + text message (Meta Graph spec)
        if self.comment_id and self.channel_event == "comment_reply":
            return {
                "recipient": {"comment_id": self.comment_id},
                "message": {"text": text},
            }

        recipient = {"id": self.sender_ig_id} if self.sender_ig_id else {"comment_id": self.comment_id}
        if self.use_generic_card and self.product_sync_id and link and not self.comment_id:
            sync = self.product_sync_id
            symbol = sync.currency_id.symbol or "₹"
            element = {
                "title": f"{sync.name} — {symbol}{sync.list_price:,.0f}"[:80],
                "subtitle": f"{self.website_id.name or self.account_id.name} • Instant Direct Checkout"[:80],
                "default_action": {"type": "web_url", "url": link},
                "buttons": [
                    {"type": "web_url", "url": link, "title": "Buy Now (Direct Link)"},
                ],
            }
            if sync.public_image_url and sync.public_image_url.startswith("https://") and "localhost" not in sync.public_image_url:
                element["image_url"] = sync.public_image_url
            return {
                "recipient": recipient,
                "message": {
                    "attachment": {
                        "type": "template",
                        "payload": {
                            "template_type": "generic",
                            "elements": [element],
                        },
                    }
                },
            }

        return {
            "recipient": recipient,
            "message": {"text": text},
        }

    def action_send_dm(self):
        for msg in self:
            acc = msg.account_id
            if not acc:
                raise UserError(_("Select a Unit Instagram Account before sending."))
            if not (msg.sender_ig_id or msg.comment_id):
                raise UserError(_("Specify either Customer IG User ID or Comment ID before sending."))

            payload = msg._build_dm_payload()
            if acc.sandbox_mode or not (acc.access_token and acc.ig_user_id):
                msg.write({
                    "state": "sent",
                    "external_message_id": f"sim_ig_{msg.id}",
                    "error_message": False,
                })
                if msg.product_sync_id:
                    msg.product_sync_id.sudo().write({"dm_sent_count": msg.product_sync_id.dm_sent_count + 1})
                if msg.lead_id:
                    msg.lead_id.message_post(body=_("Instagram Direct Link DM sent (simulated): %s") % msg.body)
                continue

            ok, data = acc._graph_request(
                "POST",
                f"{acc.ig_user_id}/messages",
                json_body=payload,
                use_bearer=True,
            )
            if ok:
                msg.write({
                    "state": "sent",
                    "external_message_id": data.get("message_id") or data.get("id") or "",
                    "error_message": False,
                })
                if msg.product_sync_id:
                    msg.product_sync_id.sudo().write({"dm_sent_count": msg.product_sync_id.dm_sent_count + 1})
                if msg.lead_id:
                    msg.lead_id.message_post(body=_("Instagram Direct Link DM sent: %s") % msg.body)
            else:
                err = (data.get("error") or {}).get("message") or str(data)
                msg.write({"state": "failed", "error_message": err[:250]})
        return True


class CustomInstagramWebhookLog(models.Model):
    _name = "custom.instagram.webhook.log"
    _description = "Instagram Webhook Event Log & Dispatcher"
    _order = "id desc"

    name = fields.Char(string="Event Summary", readonly=True)
    received_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    account_id = fields.Many2one("custom.instagram.account", string="Unit Instagram Account", ondelete="set null")
    website_id = fields.Many2one(related="account_id.website_id", string="Business Unit", store=True)
    event_type = fields.Selection(
        [
            ("messages", "DM Message"),
            ("comments", "Post / Reel Comment"),
            ("messaging_postbacks", "DM Postback"),
            ("verification", "Webhook Verification"),
            ("unknown", "Other"),
        ],
        default="unknown",
        required=True,
    )
    is_simulated = fields.Boolean(string="Simulated", default=False)
    signature_valid = fields.Boolean(string="HMAC Signature Valid", default=True)
    sender_ig_id = fields.Char(string="Sender IGSID")
    sender_username = fields.Char(string="Sender @Handle")
    comment_id = fields.Char(string="Comment ID")
    incoming_text = fields.Char(string="Incoming Text")
    raw_payload = fields.Text(string="Raw JSON Payload")
    process_status = fields.Selection(
        [("received", "Received"), ("processed", "Auto-Replied / Processed"), ("ignored", "Ignored"), ("error", "Error")],
        default="received",
        required=True,
    )
    result_summary = fields.Text(string="Processing Result", readonly=True)
    inbound_message_id = fields.Many2one("custom.instagram.message", string="Inbound Message", readonly=True)
    reply_message_id = fields.Many2one("custom.instagram.message", string="Auto-Reply DM", readonly=True)

    @api.model
    def _match_sync_product_from_text(self, account, text):
        Sync = self.env["custom.instagram.product.sync"].sudo()
        cleaned = (text or "").strip().lower()
        syncs = Sync.search([("account_id", "=", account.id)], order="id desc", limit=200)
        if not syncs:
            return Sync
        if cleaned:
            for rec in syncs:
                kw = (rec.keyword_code or "").strip().lower()
                sku = (rec.product_tmpl_id.default_code or "").strip().lower()
                if (kw and kw in cleaned) or (sku and sku in cleaned):
                    return rec
            for rec in syncs:
                pname = (rec.product_tmpl_id.name or "").strip().lower()
                words = [w for w in pname.split() if len(w) >= 4]
                if pname and (pname in cleaned or any(w in cleaned for w in words)):
                    return rec
        return syncs[:1]

    @api.model
    def _find_or_create_partner_and_lead(self, account, sender_ig_id, sender_username, text, sync_rec, create_lead=True):
        Partner = self.env["res.partner"].sudo()
        handle = f"@{sender_username.lstrip('@')}" if sender_username else (sender_ig_id or "ig_user")
        partner = False
        if sender_username:
            partner = Partner.search([("comment", "ilike", f"ig:{sender_username}")], limit=1)
        if not partner and sender_ig_id:
            partner = Partner.search([("comment", "ilike", f"igsid:{sender_ig_id}")], limit=1)
        if not partner:
            partner = Partner.create({
                "name": f"Instagram {handle}",
                "customer_rank": 1,
                "comment": f"ig:{sender_username or ''} igsid:{sender_ig_id or ''}",
            })

        lead = False
        if create_lead and account.auto_create_crm_lead:
            Lead = self.env["crm.lead"].sudo()
            lead = Lead.search([
                ("partner_id", "=", partner.id),
                ("x_inquiry_channel", "=", "instagram"),
                ("type", "=", "opportunity"),
            ], limit=1)
            if not lead:
                prod_hint = f" ({sync_rec.name})" if sync_rec else ""
                lead = Lead.create({
                    "name": f"[{account.website_id.name or account.name}] IG Inquiry {handle}{prod_hint}",
                    "partner_id": partner.id,
                    "type": "opportunity",
                    "x_inquiry_channel": "instagram",
                    "company_id": account.company_id.id,
                    "expected_revenue": sync_rec.list_price if sync_rec else 0.0,
                    "description": f"Unit: {account.website_id.name}\nInstagram Text: {text}",
                })
        return partner, lead

    @api.model
    def ingest_payload(self, account, payload, event_type=None, is_simulated=False, signature_valid=True):
        raw_str = json.dumps(payload, indent=2, ensure_ascii=False)
        events = self._extract_events(payload)
        parsed = events[0] if events else self._empty_event()
        detected_type = event_type or parsed["event_type"]
        sender_id = parsed["sender_id"]
        sender_user = parsed["sender_username"]
        comment_id = parsed["comment_id"]
        text = parsed["text"]

        log = self.sudo().create({
            "name": f"{detected_type}: {sender_user or sender_id or 'webhook'}",
            "account_id": account.id if account else False,
            "event_type": detected_type,
            "is_simulated": is_simulated,
            "signature_valid": signature_valid,
            "sender_ig_id": sender_id,
            "sender_username": sender_user,
            "comment_id": comment_id,
            "incoming_text": (text or "")[:200],
            "raw_payload": raw_str,
            "process_status": "received",
        })
        if not account or not signature_valid or not events:
            log.write({
                "process_status": "ignored",
                "result_summary": "Invalid signature, missing account, or empty webhook event.",
            })
            return log

        for ev in events:
            ev_type = event_type or ev["event_type"]
            if not (ev["text"] or ev["is_postback"] or ev["has_attachment"]):
                continue
            log._process_extracted_event(
                account,
                ev_type,
                ev["sender_id"],
                ev["sender_username"],
                ev["comment_id"],
                ev["media_id"],
                ev["text"] or "[Attachment]",
                mid=ev["mid"],
                recipient_id=ev["recipient_id"],
                is_echo=ev["is_echo"],
            )
        if log.process_status == "received":
            log.write({
                "process_status": "ignored",
                "result_summary": "No processable text, attachment, or postback in payload.",
            })
        return log

    def action_reprocess(self):
        for log in self:
            payload = json.loads(log.raw_payload or "{}")
            events = log._extract_events(payload)
            if log.account_id and events:
                for ev in events:
                    if not (ev["text"] or ev["is_postback"] or ev["has_attachment"]):
                        continue
                    log._process_extracted_event(
                        log.account_id,
                        ev["event_type"],
                        ev["sender_id"],
                        ev["sender_username"],
                        ev["comment_id"],
                        ev["media_id"],
                        ev["text"] or "[Attachment]",
                        mid=ev["mid"],
                        recipient_id=ev["recipient_id"],
                        is_echo=ev["is_echo"],
                    )
        return True

    def _find_duplicate_message(self, account, direction, mid=None, comment_id=None):
        Msg = self.env["custom.instagram.message"].sudo()
        if mid:
            dup = Msg.search([
                ("account_id", "=", account.id),
                ("direction", "=", direction),
                ("external_message_id", "=", mid),
            ], limit=1)
            if dup:
                return dup
        if comment_id:
            dup = Msg.search([
                ("account_id", "=", account.id),
                ("direction", "=", direction),
                ("comment_id", "=", comment_id),
            ], limit=1)
            if dup:
                return dup
        return Msg

    def _process_extracted_event(
        self,
        account,
        event_type,
        sender_id,
        sender_user,
        comment_id,
        media_id,
        text,
        mid="",
        recipient_id="",
        is_echo=False,
    ):
        self.ensure_one()
        ev_kind = "comment" if event_type == "comments" else "dm"
        is_outbound_echo = bool(
            is_echo
            or (sender_id and account.ig_user_id and sender_id == account.ig_user_id)
            or (sender_user and account.ig_username and sender_user.strip("@").lower() == account.ig_username.strip("@").lower())
        )
        customer_ig_id = recipient_id if is_outbound_echo else sender_id
        Msg = self.env["custom.instagram.message"].sudo()

        # 1. Manage Echoes (messages sent from Odoo already stored, or manual replies sent via Instagram App)
        if is_outbound_echo:
            existing_out = self._find_duplicate_message(account, "outbound", mid=mid, comment_id=comment_id)
            if existing_out:
                if not existing_out.is_echo:
                    existing_out.write({"is_echo": True})
                self.write({
                    "process_status": "processed",
                    "reply_message_id": existing_out.id,
                    "result_summary": _("Outbound echo matched existing message %s (deduplicated; no duplicate stored).") % existing_out.name,
                })
                return

            sync_rec = self._match_sync_product_from_text(account, text)
            partner = False
            lead = False
            if customer_ig_id:
                partner, lead = self._find_or_create_partner_and_lead(
                    account, customer_ig_id, "", text, sync_rec, create_lead=False
                )
            echo_msg = Msg.create({
                "direction": "outbound",
                "channel_event": "comment_reply" if ev_kind == "comment" else "dm",
                "account_id": account.id,
                "sender_ig_id": customer_ig_id,
                "comment_id": comment_id or False,
                "media_id": media_id or False,
                "partner_id": partner.id if partner else False,
                "lead_id": lead.id if lead else False,
                "body": text,
                "state": "sent",
                "is_echo": True,
                "external_message_id": mid or False,
            })
            self.write({
                "process_status": "processed",
                "reply_message_id": echo_msg.id,
                "result_summary": _("Stored outbound echo %s (sent from external Instagram app/suite; no auto-reply triggered).") % echo_msg.name,
            })
            return

        # 2. Deduplicate Inbound Webhook Retries by Meta MID / Comment ID
        existing_in = self._find_duplicate_message(account, "inbound", mid=mid, comment_id=comment_id)
        if existing_in:
            self.write({
                "process_status": "ignored",
                "inbound_message_id": existing_in.id,
                "result_summary": _("Duplicate inbound event skipped (already stored as %s).") % existing_in.name,
            })
            return

        rules = self.env["custom.instagram.rule"].sudo().search(
            [("account_id", "=", account.id), ("active", "=", True)],
            order="sequence asc, id asc",
        )
        matched_rule = False
        for rule in rules:
            if rule._matches_text(text, ev_kind):
                matched_rule = rule
                break

        sync_rec = (
            matched_rule._resolve_sync_product(text)
            if matched_rule
            else self._match_sync_product_from_text(account, text)
        )
        create_lead = matched_rule.auto_create_lead if matched_rule else account.auto_create_crm_lead
        partner, lead = self._find_or_create_partner_and_lead(account, sender_id, sender_user, text, sync_rec, create_lead=create_lead)

        inbound = Msg.create({
            "direction": "inbound",
            "channel_event": "comment" if ev_kind == "comment" else ("postback" if event_type == "messaging_postbacks" else "dm"),
            "account_id": account.id,
            "sender_ig_id": sender_id,
            "sender_username": sender_user,
            "comment_id": comment_id,
            "media_id": media_id,
            "partner_id": partner.id if partner else False,
            "lead_id": lead.id if lead else False,
            "product_sync_id": sync_rec.id if sync_rec else False,
            "rule_id": matched_rule.id if matched_rule else False,
            "body": text or "[Postback]",
            "state": "received",
            "external_message_id": mid or False,
        })

        # Send Meesho-style direct link reply if rule matched, DM received, or comment matched a product keyword/SKU
        cleaned_text = (text or "").strip().lower()
        exact_kw_match = bool(
            sync_rec
            and cleaned_text
            and any(
                code and code.strip().lower() in cleaned_text
                for code in (sync_rec.keyword_code, sync_rec.product_tmpl_id.default_code)
            )
        )
        reply_msg = False
        if matched_rule or (sync_rec and (ev_kind == "dm" or exact_kw_match)):
            if matched_rule:
                reply_text = matched_rule._render_reply(sync_rec)
                use_card = matched_rule.use_generic_card
                matched_rule.write({"trigger_count": matched_rule.trigger_count + 1})
            else:
                link = f"{sync_rec.tracked_dm_url}?instant=1" if account.use_cart_instant_checkout else sync_rec.tracked_dm_url
                symbol = sync_rec.currency_id.symbol or "₹"
                reply_text = DEFAULT_DM_REPLY.format(
                    product_name=sync_rec.name,
                    price=f"{symbol}{sync_rec.list_price:,.0f}",
                    buy_link=link,
                    unit_name=account.website_id.name or account.name,
                    keyword=sync_rec.keyword_code or "",
                )
                use_card = True

            link_url = (
                (f"{sync_rec.tracked_dm_url}?instant=1" if account.use_cart_instant_checkout else sync_rec.tracked_dm_url)
                if sync_rec
                else False
            )
            reply_msg = self.env["custom.instagram.message"].sudo().create({
                "direction": "outbound",
                "channel_event": "comment_reply" if ev_kind == "comment" else "dm",
                "account_id": account.id,
                "sender_ig_id": sender_id,
                "sender_username": sender_user,
                "comment_id": comment_id if ev_kind == "comment" else False,
                "partner_id": partner.id if partner else False,
                "lead_id": lead.id if lead else False,
                "product_sync_id": sync_rec.id if sync_rec else False,
                "rule_id": matched_rule.id if matched_rule else False,
                "body": reply_text,
                "direct_link_url": link_url,
                "use_generic_card": False if ev_kind == "comment" else use_card,
            })
            reply_msg.action_send_dm()
            summary = _(
                "Inbound recorded (%(inb)s). Sent Direct Link DM (%(rep)s) for %(prod)s via %(rule)s."
            ) % {
                "inb": inbound.name,
                "rep": reply_msg.name,
                "prod": sync_rec.name if sync_rec else "Store Catalog",
                "rule": matched_rule.name if matched_rule else "Unit Auto-Match",
            }
        else:
            summary = _("Inbound message recorded (%s); no keyword rule matched for auto-reply.") % inbound.name

        self.write({
            "process_status": "processed",
            "inbound_message_id": inbound.id,
            "reply_message_id": reply_msg.id if reply_msg else False,
            "result_summary": summary,
        })

    @staticmethod
    def _empty_event():
        return {
            "event_type": "unknown",
            "mid": "",
            "sender_id": "",
            "recipient_id": "",
            "sender_username": "",
            "comment_id": "",
            "media_id": "",
            "text": "",
            "is_echo": False,
            "is_postback": False,
            "has_attachment": False,
        }

    @classmethod
    def _extract_events(cls, payload):
        events = []
        for entry in payload.get("entry") or []:
            for ev in entry.get("messaging") or []:
                msg = ev.get("message") or {}
                postback = ev.get("postback") or {}
                item = cls._empty_event()
                item["sender_id"] = str((ev.get("sender") or {}).get("id") or "")
                item["recipient_id"] = str((ev.get("recipient") or {}).get("id") or "")
                item["mid"] = str(msg.get("mid") or "")
                item["is_echo"] = bool(msg.get("is_echo"))
                item["has_attachment"] = bool(msg.get("attachments"))
                if postback:
                    item["event_type"] = "messaging_postbacks"
                    item["text"] = postback.get("title") or postback.get("payload") or ""
                    item["is_postback"] = True
                else:
                    item["event_type"] = "messages"
                    item["text"] = msg.get("text") or ""
                events.append(item)

            for ch in entry.get("changes") or []:
                field = ch.get("field") or "unknown"
                val = ch.get("value") or {}
                item = cls._empty_event()
                item["event_type"] = "comments" if "comment" in field else "unknown"
                item["comment_id"] = str(val.get("id") or "")
                item["media_id"] = str((val.get("media") or {}).get("id") or "")
                frm = val.get("from") or {}
                item["sender_id"] = str(frm.get("id") or "")
                item["sender_username"] = frm.get("username") or ""
                item["text"] = val.get("text") or ""
                events.append(item)
        return events

    @classmethod
    def _extract_first_event(cls, payload):
        events = cls._extract_events(payload)
        return events[0] if events else cls._empty_event()


class CustomInstagramSendLinkWizard(models.TransientModel):
    _name = "custom.instagram.send.link.wizard"
    _description = "Send Direct Product Checkout Link via Instagram DM"

    account_id = fields.Many2one(
        "custom.instagram.account",
        string="Unit Instagram Account",
        required=True,
        default=lambda self: self.env["custom.instagram.account"].search([("active", "=", True)], limit=1),
    )
    product_sync_id = fields.Many2one(
        "custom.instagram.product.sync",
        string="Unit Synced Product",
        required=True,
        domain="[('account_id', '=', account_id)]",
    )
    def _default_recipient_ig_id(self):
        msg = self.env["custom.instagram.message"].search(
            [("direction", "=", "inbound"), ("sender_ig_id", "!=", False)],
            limit=1,
        )
        return msg.sender_ig_id if msg else False

    recipient_ig_id = fields.Char(
        string="Recipient IG User ID (IGSID)",
        required=True,
        default=_default_recipient_ig_id,
    )
    recipient_username = fields.Char(string="Recipient @Handle")
    comment_id = fields.Char(string="Reply to Comment ID (Optional)")
    use_generic_card = fields.Boolean(string="Send Clickable Product Card (Generic Template)", default=True)
    message_text = fields.Text(string="DM Message", required=True)
    direct_link_preview = fields.Char(string="Direct Checkout Link", compute="_compute_preview")

    @api.depends("product_sync_id", "account_id.use_cart_instant_checkout")
    def _compute_preview(self):
        for wiz in self:
            if wiz.product_sync_id:
                wiz.direct_link_preview = (
                    f"{wiz.product_sync_id.tracked_dm_url}?instant=1"
                    if wiz.account_id.use_cart_instant_checkout
                    else wiz.product_sync_id.tracked_dm_url
                )
            else:
                wiz.direct_link_preview = False

    @api.onchange("account_id", "product_sync_id")
    def _onchange_product_sync(self):
        for wiz in self:
            if wiz.product_sync_id and wiz.account_id:
                link = (
                    f"{wiz.product_sync_id.tracked_dm_url}?instant=1"
                    if wiz.account_id.use_cart_instant_checkout
                    else wiz.product_sync_id.tracked_dm_url
                )
                symbol = wiz.product_sync_id.currency_id.symbol or "₹"
                wiz.message_text = DEFAULT_DM_REPLY.format(
                    product_name=wiz.product_sync_id.name,
                    price=f"{symbol}{wiz.product_sync_id.list_price:,.0f}",
                    buy_link=link,
                    unit_name=wiz.account_id.website_id.name or wiz.account_id.name,
                    keyword=wiz.product_sync_id.keyword_code or "",
                )

    def action_send_now(self):
        self.ensure_one()
        is_comment_reply = bool(self.comment_id)
        msg = self.env["custom.instagram.message"].create({
            "direction": "outbound",
            "channel_event": "comment_reply" if is_comment_reply else "dm",
            "account_id": self.account_id.id,
            "sender_ig_id": self.recipient_ig_id,
            "sender_username": self.recipient_username,
            "comment_id": self.comment_id or False,
            "product_sync_id": self.product_sync_id.id,
            "body": self.message_text,
            "direct_link_url": self.direct_link_preview,
            "use_generic_card": False if is_comment_reply else self.use_generic_card,
        })
        msg.action_send_dm()
        return {
            "type": "ir.actions.act_window",
            "name": _("Sent Instagram Direct Link DM"),
            "res_model": "custom.instagram.message",
            "view_mode": "form",
            "res_id": msg.id,
        }
