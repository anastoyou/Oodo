from odoo import http
from odoo.http import request


class CustomOperationsUiController(http.Controller):
    """Shop Floor Kiosk (/shopfloor) and Camera + Audio Barcode PWA (/barcode)."""

    @http.route(["/shopfloor"], type="http", auth="user", website=True)
    def shopfloor_kiosk(self, **kwargs):
        workorders = request.env["custom.shopfloor.workorder"].search([("stage", "!=", "done")], limit=50)
        return request.render(
            "custom_operations_ui.shopfloor_kiosk_page",
            {"workorders": workorders},
        )

    @http.route(["/shopfloor/action"], type="http", auth="user", website=True, methods=["POST"])
    def shopfloor_action(self, workorder_id="", op="start", **kwargs):
        if workorder_id:
            wo = request.env["custom.shopfloor.workorder"].browse(int(workorder_id)).exists()
            if wo:
                if op == "start":
                    wo.action_start_timer()
                elif op == "pause":
                    wo.action_pause_timer()
                elif op == "done":
                    wo.action_complete()
        return request.redirect("/shopfloor")

    @http.route(["/barcode"], type="http", auth="user", website=True)
    def barcode_pwa(self, **kwargs):
        return request.render("custom_operations_ui.barcode_pwa_page", {})

    @http.route(["/barcode/lookup"], type="jsonrpc", auth="user", methods=["POST"])
    def barcode_lookup(self, code="", **kwargs):
        code = (code or "").strip()
        if not code:
            return {"found": False, "message": "Empty barcode."}

        product = request.env["product.product"].search(
            ["|", ("barcode", "=", code), ("default_code", "=", code)], limit=1
        )
        if product:
            return {
                "found": True,
                "kind": "product",
                "name": product.display_name,
                "sku": product.default_code or "",
                "barcode": product.barcode or code,
                "qty_available": product.qty_available,
                "price": product.lst_price,
            }

        picking = request.env["stock.picking"].search([("name", "=", code)], limit=1)
        if picking:
            return {
                "found": True,
                "kind": "picking",
                "name": picking.name,
                "state": picking.state,
                "partner": picking.partner_id.name or "",
                "move_count": len(picking.move_ids),
            }

        return {"found": False, "message": f"No product or transfer matched '{code}'."}

