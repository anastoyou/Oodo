import re
import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _normalize_indian_phone(raw_phone):
    digits = re.sub(r"\D+", "", raw_phone or "")
    if len(digits) == 10:
        return f"91{digits}"
    return digits


class CustomWhatsappConfig(models.Model):
    _name = "custom.whatsapp.config"
    _description = "WhatsApp Business Cloud API Configuration"

    name = fields.Char(required=True, default="Primary WhatsApp Business")
    active = fields.Boolean(default=True)
    phone_number_id = fields.Char(string="Meta Phone Number ID")
    business_account_id = fields.Char(string="WABA ID")
    access_token = fields.Char(string="Permanent Access Token")
    verify_token = fields.Char(string="Webhook Verify Token", default="zoee_wa_verify_2026")
    sandbox_mode = fields.Boolean(
        string="Local Simulation Mode (No API Call)",
        default=True,
        help="When enabled or when credentials are empty, messages are logged cleanly in Odoo without calling Meta servers.",
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)


class CustomWhatsappTemplate(models.Model):
    _name = "custom.whatsapp.template"
    _description = "WhatsApp Approved Message Template"
    _order = "name"

    name = fields.Char(required=True)
    template_code = fields.Char(string="Meta Template Name", required=True)
    language_code = fields.Char(default="en")
    body_preview = fields.Text(string="Message Body", required=True)
    category = fields.Selection(
        [("utility", "Utility (Order / COD / Tracking)"), ("marketing", "Marketing"), ("support", "Support / Exchange")],
        default="utility",
        required=True,
    )


class CustomWhatsappMessage(models.Model):
    _name = "custom.whatsapp.message"
    _description = "WhatsApp Message Log"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="Reference", readonly=True, default="New")
    direction = fields.Selection([("outbound", "Outbound"), ("inbound", "Inbound")], default="outbound", required=True)
    partner_id = fields.Many2one("res.partner", string="Contact")
    mobile_number = fields.Char(string="WhatsApp Number", required=True)
    template_id = fields.Many2one("custom.whatsapp.template", string="Template")
    body = fields.Text(string="Message Text", required=True)
    sale_order_id = fields.Many2one("sale.order", string="Sales Order")
    ticket_id = fields.Many2one("custom.support.ticket", string="Support Ticket")
    state = fields.Selection(
        [("draft", "Queued"), ("sent", "Sent / Simulated"), ("received", "Received"), ("failed", "Failed")],
        default="draft",
        tracking=True,
    )
    external_message_id = fields.Char(readonly=True)
    error_message = fields.Char(readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for msg in self:
            if msg.partner_id and not msg.mobile_number:
                msg.mobile_number = msg.partner_id.phone or ""

    @api.onchange("template_id")
    def _onchange_template_id(self):
        for msg in self:
            if msg.template_id and not msg.body:
                msg.body = msg.template_id.body_preview

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                vals["name"] = seq.next_by_code("custom.whatsapp.message") or "WA"
        return super().create(vals_list)

    def action_send_whatsapp(self):
        config = self.env["custom.whatsapp.config"].search([("active", "=", True)], limit=1)
        for msg in self:
            phone = _normalize_indian_phone(msg.mobile_number)
            if not phone:
                raise UserError(_("Enter a valid WhatsApp phone number before sending."))

            if not config or config.sandbox_mode or not (config.phone_number_id and config.access_token):
                msg.write({
                    "state": "sent",
                    "external_message_id": f"sim-{msg.id}",
                    "error_message": False,
                })
                msg._post_to_linked_chatter()
                continue

            url = f"https://graph.facebook.com/v19.0/{config.phone_number_id}/messages"
            headers = {"Authorization": f"Bearer {config.access_token}", "Content-Type": "application/json"}
            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "text",
                "text": {"body": msg.body},
            }
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                data = resp.json() if resp.content else {}
                if resp.ok:
                    wa_id = (data.get("messages") or [{}])[0].get("id", "")
                    msg.write({"state": "sent", "external_message_id": wa_id, "error_message": False})
                    msg._post_to_linked_chatter()
                else:
                    msg.write({"state": "failed", "error_message": str(data)[:240]})
            except requests.RequestException as exc:
                msg.write({"state": "failed", "error_message": str(exc)[:240]})

    def _post_to_linked_chatter(self):
        self.ensure_one()
        note = _("WhatsApp (%s) sent to %s: %s") % (self.name, self.mobile_number, self.body)
        if self.sale_order_id:
            self.sale_order_id.message_post(body=note)
        if self.ticket_id:
            self.ticket_id.message_post(body=note)


class CustomVoipCall(models.Model):
    _name = "custom.voip.call"
    _description = "VoIP Call Log & COD Phone Verification"
    _inherit = ["mail.thread"]
    _order = "call_datetime desc, id desc"

    name = fields.Char(string="Call Summary", required=True)
    direction = fields.Selection([("outbound", "Outbound Call"), ("inbound", "Inbound Call")], default="outbound", required=True)
    partner_id = fields.Many2one("res.partner", string="Customer / Contact")
    phone_number = fields.Char(required=True)
    user_id = fields.Many2one("res.users", string="Agent", default=lambda self: self.env.user, required=True)
    call_datetime = fields.Datetime(default=fields.Datetime.now, required=True)
    duration_seconds = fields.Integer(string="Duration (Seconds)", default=0)
    disposition = fields.Selection(
        [
            ("connected", "Connected"),
            ("cod_confirmed", "COD Confirmed"),
            ("no_answer", "No Answer / Busy"),
            ("callback", "Callback Requested"),
            ("wrong_number", "Invalid / Unreachable"),
        ],
        default="connected",
        required=True,
    )
    sale_order_id = fields.Many2one("sale.order", string="Related Order")
    crm_lead_id = fields.Many2one("crm.lead", string="Related Lead")
    notes = fields.Text()
    recording_url = fields.Char(string="Recording URL")

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for call in self:
            if call.partner_id and not call.phone_number:
                call.phone_number = call.partner_id.phone or ""

    @api.model_create_multi
    def create(self, vals_list):
        calls = super().create(vals_list)
        for call in calls:
            note = _("VoIP %s (%s, %ss) by %s: %s") % (
                call.direction, call.disposition, call.duration_seconds, call.user_id.name, call.notes or call.name
            )
            if call.sale_order_id:
                call.sale_order_id.message_post(body=note)
                if call.disposition == "cod_confirmed" and call.sale_order_id.x_payment_mode == "cod":
                    call.sale_order_id.action_confirm_cod()
            if call.crm_lead_id:
                call.crm_lead_id.message_post(body=note)
        return calls


class CustomFrontdeskVisitor(models.Model):
    _name = "custom.frontdesk.visitor"
    _description = "Frontdesk / Reception Visitor Kiosk"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "check_in desc, id desc"

    name = fields.Char(string="Visitor Name", required=True)
    phone = fields.Char(string="Phone / Mobile")
    company_name = fields.Char(string="Organization / Courier")
    purpose = fields.Selection(
        [
            ("tailoring_fitting", "Custom Tailoring / Fitting"),
            ("vendor_sample", "Vendor / Fabric Sample"),
            ("pickup_delivery", "Order Pickup / Return"),
            ("interview", "Job Interview"),
            ("meeting", "Partner / Business Meeting"),
        ],
        default="meeting",
        required=True,
    )
    host_employee_id = fields.Many2one("hr.employee", string="Host Employee")
    check_in = fields.Datetime(default=fields.Datetime.now, required=True)
    check_out = fields.Datetime()
    state = fields.Selection([("checked_in", "Checked In"), ("checked_out", "Checked Out")], default="checked_in", tracking=True)
    notes = fields.Char()

    def action_check_out(self):
        self.write({"state": "checked_out", "check_out": fields.Datetime.now()})


class SaleOrderComms(models.Model):
    _inherit = "sale.order"

    def action_open_whatsapp_composer(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Send WhatsApp"),
            "res_model": "custom.whatsapp.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_mobile_number": self.partner_id.phone or "",
                "default_sale_order_id": self.id,
                "default_body": _("Hi %s, update regarding your order %s (Total: %s).") % (
                    self.partner_id.name, self.name, self.amount_total
                ),
            },
        }

    def action_log_voip_call(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Log VoIP / COD Call"),
            "res_model": "custom.voip.call",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_name": f"Call for {self.name}",
                "default_partner_id": self.partner_id.id,
                "default_phone_number": self.partner_id.phone or "",
                "default_sale_order_id": self.id,
            },
        }
