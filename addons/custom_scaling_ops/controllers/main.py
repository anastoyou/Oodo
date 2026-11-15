import json

from odoo import Command, http
from odoo.http import request


class CustomScalingOpsController(http.Controller):
    """Courier tracking webhook (/courier/webhook) & Camera Scan-to-Session Push (/barcode/push)."""

    @http.route(["/courier/webhook"], type="http", auth="public", methods=["POST"], csrf=False)
    def courier_webhook(self, **kwargs):
        try:
            payload = json.loads(request.httprequest.data.decode("utf-8") or "{}")
        except ValueError:
            return request.make_json_response({"status": "error", "message": "invalid json"}, status=400)

        awb = str(payload.get("awb") or payload.get("awb_code") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        if not awb:
            return request.make_json_response({"status": "ignored"})

        picking = request.env["stock.picking"].sudo().search([("x_awb_number", "=", awb)], limit=1)
        if not picking:
            return request.make_json_response({"status": "not_found"})

        mapping = {
            "in_transit": ("in_transit", "handed_to_courier"),
            "out_for_delivery": ("out_for_delivery", "handed_to_courier"),
            "delivered": ("delivered", "handed_to_courier"),
            "rto_initiated": ("rto_initiated", "rto_received"),
            "rto_delivered": ("rto_delivered", "rto_received"),
        }
        courier_state, pack_state = mapping.get(status, ("in_transit", picking.x_packing_status))
        picking.write({"x_courier_status": courier_state, "x_packing_status": pack_state})
        picking.message_post(body=f"Courier webhook update for AWB {awb}: {status}")
        return request.make_json_response({"status": "ok", "picking": picking.name})

    @http.route(["/barcode/push"], type="jsonrpc", auth="user", methods=["POST"])
    def barcode_push_to_session(self, code="", **kwargs):
        clean = (code or "").strip()
        if not clean:
            return {"ok": False, "message": "Empty barcode."}
        product = request.env["product.product"].search(
            ["|", ("barcode", "=", clean), ("default_code", "=", clean)], limit=1
        )
        if not product:
            return {"ok": False, "message": f"No product found for '{clean}'."}

        Session = request.env["custom.barcode.session"]
        session = Session.search([("state", "=", "draft")], order="id desc", limit=1)
        if not session:
            session = Session.create({"operation_mode": "picking"})

        existing = session.line_ids.filtered(lambda l: l.product_id == product)[:1]
        if existing:
            existing.scanned_qty += 1.0
        else:
            session.line_ids = [
                Command.create({
                    "product_id": product.id,
                    "scanned_code": clean,
                    "scanned_qty": 1.0,
                })
            ]
        return {
            "ok": True,
            "session": session.name,
            "product": product.display_name,
            "qty": existing.scanned_qty if existing else 1.0,
        }

