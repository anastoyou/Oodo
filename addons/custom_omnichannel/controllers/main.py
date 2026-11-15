import base64
from datetime import datetime, timedelta

from odoo import fields, http
from odoo.http import request

from odoo.addons.custom_enterprise.controllers.sign import CustomEnterpriseSignController


class CustomOmnichannelController(CustomEnterpriseSignController):
    """Extends /my/sign with drawn signature capture & PDF stamping, plus /shop/rental/book."""

    @http.route(["/my/sign/<string:token>/submit"], type="http", auth="public", website=True, methods=["POST"])
    def portal_sign_submit(self, token, signed_name="", signature_data="", **kwargs):
        res = super().portal_sign_submit(token, signed_name=signed_name, **kwargs)
        signer = request.env["custom.sign.signer"].sudo().search([("access_token", "=", token)], limit=1)
        if signer:
            if signature_data and ";base64," in signature_data:
                clean_b64 = signature_data.split(";base64,", 1)[1].strip()
                if clean_b64:
                    signer.write({"signature_image": clean_b64})
            if signer.request_id.state == "signed":
                signer.request_id.action_generate_signed_pdf()
        return res

    @http.route(["/my/sign/<string:token>/pdf"], type="http", auth="public", website=True)
    def portal_sign_download_pdf(self, token, **kwargs):
        signer = request.env["custom.sign.signer"].sudo().search([("access_token", "=", token)], limit=1)
        if not signer:
            return request.not_found()
        req = signer.request_id
        if req.state == "signed" and not req.signed_pdf:
            req.action_generate_signed_pdf()
        if not req.signed_pdf:
            return request.not_found()
        pdf_bytes = req.signed_pdf.content if hasattr(req.signed_pdf, "content") else base64.b64decode(req.signed_pdf)
        filename = req.signed_pdf_filename or f"{req.name}_signed.pdf"
        return request.make_response(
            pdf_bytes,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", f'attachment; filename="{filename}"'),
            ],
        )

    @http.route(["/shop/rental/book"], type="http", auth="public", website=True, methods=["POST"])
    def shop_rental_book(self, product_id="", pickup_date="", return_date="", quantity="1", **kwargs):
        if not product_id:
            return request.redirect("/shop")
        product = request.env["product.product"].sudo().browse(int(product_id)).exists()
        if not product:
            return request.redirect("/shop")

        order_sudo = request.cart or request.env.website._create_cart()
        qty = max(1, int(float(quantity or 1)))
        cart_res = order_sudo.with_context(skip_cart_verification=True)._cart_add(
            product_id=product.id,
            quantity=qty,
        )
        line = order_sudo.order_line.filtered(lambda l: l.id == cart_res.get("line_id"))
        if line:
            try:
                pickup_dt = datetime.fromisoformat(pickup_date) if pickup_date else fields.Datetime.now()
            except ValueError:
                pickup_dt = fields.Datetime.now()
            try:
                return_dt = (
                    datetime.fromisoformat(return_date)
                    if return_date
                    else pickup_dt + timedelta(days=max(1, product.product_tmpl_id.x_rental_default_days or 3))
                )
            except ValueError:
                return_dt = pickup_dt + timedelta(days=3)
            line.sudo().write({
                "x_rental_pickup_date": fields.Datetime.to_string(pickup_dt),
                "x_rental_return_date": fields.Datetime.to_string(return_dt),
            })
        return request.redirect("/shop/cart")

