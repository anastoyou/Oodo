from odoo import fields, http
from odoo.http import request


class CustomEnterpriseSignController(http.Controller):
    """Public token-based e-Signature portal and Helpdesk CSAT rating endpoints."""

    @http.route(["/my/sign/<string:token>"], type="http", auth="public", website=True)
    def portal_sign_document(self, token, **kwargs):
        signer = request.env["custom.sign.signer"].sudo().search([("access_token", "=", token)], limit=1)
        if not signer:
            return request.not_found()
        return request.render(
            "custom_enterprise.portal_sign_page",
            {"signer": signer, "sign_request": signer.request_id},
        )

    @http.route(["/my/sign/<string:token>/submit"], type="http", auth="public", website=True, methods=["POST"])
    def portal_sign_submit(self, token, signed_name="", **kwargs):
        signer = request.env["custom.sign.signer"].sudo().search([("access_token", "=", token)], limit=1)
        if not signer:
            return request.not_found()
        cleaned_name = (signed_name or "").strip()
        if cleaned_name and signer.state != "signed":
            signer.write({
                "signed_name": cleaned_name,
                "signed_on": fields.Datetime.now(),
                "signed_ip": request.httprequest.remote_addr or "",
                "state": "signed",
            })
            req = signer.request_id
            req.message_post(body=f"Signed electronically by {cleaned_name} ({signer.partner_id.name}).")
            if all(s.state == "signed" for s in req.signer_ids):
                req.state = "signed"
        return request.redirect(f"/my/sign/{token}")

    @http.route(["/my/tickets/<int:ticket_id>/rate"], type="http", auth="user", website=True, methods=["POST"])
    def portal_ticket_rate(self, ticket_id, rating_score="5", rating_comment="", **kwargs):
        ticket = request.env["custom.support.ticket"].search([("id", "=", ticket_id)], limit=1)
        if ticket and rating_score in {"1", "2", "3", "4", "5"}:
            ticket.write({
                "rating_score": rating_score,
                "rating_comment": (rating_comment or "").strip(),
                "rating_date": fields.Datetime.now(),
            })
        return request.redirect(f"/my/tickets/{ticket_id}")

    @http.route(["/appointments"], type="http", auth="public", website=True)
    def public_appointments(self, booked=None, **kwargs):
        types = request.env["custom.appointment.type"].sudo().search([("active", "=", True)])
        return request.render(
            "custom_enterprise.portal_appointments_page",
            {"appointment_types": types, "booked": booked},
        )

    @http.route(["/appointments/book"], type="http", auth="public", website=True, methods=["POST"])
    def public_appointments_book(self, appointment_type_id="", customer_name="", customer_phone="", customer_email="", start_datetime="", notes="", **kwargs):
        if appointment_type_id and customer_name.strip():
            dt_val = start_datetime.replace("T", " ") + ":00" if "T" in start_datetime else fields.Datetime.now()
            request.env["custom.appointment.booking"].sudo().create({
                "appointment_type_id": int(appointment_type_id),
                "customer_name": customer_name.strip(),
                "customer_phone": customer_phone.strip(),
                "customer_email": customer_email.strip(),
                "start_datetime": dt_val,
                "notes": notes.strip(),
            })
            return request.redirect("/appointments?booked=1")
        return request.redirect("/appointments")
