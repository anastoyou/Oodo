import json

from odoo import fields, http
from odoo.http import request


class CustomCommsController(http.Controller):
    """WhatsApp Cloud webhook receiver and Frontdesk Reception Kiosk (/frontdesk)."""

    @http.route(["/whatsapp/webhook"], type="http", auth="public", methods=["GET", "POST"], csrf=False)
    def whatsapp_webhook(self, **kwargs):
        if request.httprequest.method == "GET":
            mode = kwargs.get("hub.mode")
            token = kwargs.get("hub.verify_token")
            challenge = kwargs.get("hub.challenge", "")
            cfg = request.env["custom.whatsapp.config"].sudo().search([("active", "=", True)], limit=1)
            if mode == "subscribe" and cfg and token == cfg.verify_token:
                return request.make_response(challenge, [("Content-Type", "text/plain")])
            return request.make_response("Forbidden", status=403)

        payload = {}
        try:
            payload = json.loads(request.httprequest.data.decode("utf-8") or "{}")
        except ValueError:
            payload = {}

        entries = payload.get("entry") or []
        WaMsg = request.env["custom.whatsapp.message"].sudo()
        for entry in entries:
            for change in entry.get("changes") or []:
                val = change.get("value") or {}
                for msg in val.get("messages") or []:
                    from_num = msg.get("from", "")
                    text_body = (msg.get("text") or {}).get("body", "[Media/Interactive Message]")
                    partner = request.env["res.partner"].sudo().search([("phone", "ilike", from_num[-10:])], limit=1)
                    WaMsg.create({
                        "direction": "inbound",
                        "partner_id": partner.id if partner else False,
                        "mobile_number": from_num,
                        "body": text_body,
                        "state": "received",
                        "external_message_id": msg.get("id", ""),
                    })
        return request.make_json_response({"status": "ok"})

    @http.route(["/frontdesk"], type="http", auth="public", website=True)
    def frontdesk_kiosk(self, checked_in=None, **kwargs):
        employees = request.env["hr.employee"].sudo().search([], limit=50)
        return request.render(
            "custom_comms.frontdesk_kiosk_page",
            {"employees": employees, "checked_in": checked_in},
        )

    @http.route(["/frontdesk/checkin"], type="http", auth="public", website=True, methods=["POST"])
    def frontdesk_checkin_submit(self, name="", phone="", company_name="", purpose="meeting", host_employee_id="", notes="", **kwargs):
        if name.strip():
            visitor = request.env["custom.frontdesk.visitor"].sudo().create({
                "name": name.strip(),
                "phone": phone.strip(),
                "company_name": company_name.strip(),
                "purpose": purpose,
                "host_employee_id": int(host_employee_id) if host_employee_id else False,
                "check_in": fields.Datetime.now(),
                "notes": notes.strip(),
            })
            if visitor.host_employee_id and visitor.host_employee_id.user_id:
                visitor.activity_schedule(
                    summary=f"Visitor arrived: {visitor.name}",
                    user_id=visitor.host_employee_id.user_id.id,
                )
            return request.redirect("/frontdesk?checked_in=1")
        return request.redirect("/frontdesk")

