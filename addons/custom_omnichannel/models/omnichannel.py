import base64
import io
from datetime import timedelta

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from odoo import Command, _, api, fields, models


class ProductTemplateOmnichannel(models.Model):
    _inherit = "product.template"

    x_is_subscription = fields.Boolean(string="Recurring Subscription Product")
    x_subscription_plan_id = fields.Many2one("custom.subscription.plan", string="Subscription Plan")
    x_is_rental = fields.Boolean(string="Available for Online Rental")
    x_rental_deposit = fields.Float(string="Rental Security Deposit", default=0.0)
    x_rental_default_days = fields.Integer(string="Default Rental Days", default=3)


class SaleOrderLineOmnichannel(models.Model):
    _inherit = "sale.order.line"

    x_rental_pickup_date = fields.Datetime(string="Rental Pickup Date")
    x_rental_return_date = fields.Datetime(string="Rental Return Date")
    x_generated_subscription_id = fields.Many2one(
        "custom.subscription", string="Provisioned Subscription", readonly=True, copy=False
    )
    x_generated_rental_id = fields.Many2one(
        "custom.rental.order", string="Provisioned Rental", readonly=True, copy=False
    )


class SaleOrderOmnichannel(models.Model):
    _inherit = "sale.order"

    x_subscription_count = fields.Integer(compute="_compute_omnichannel_counts")
    x_rental_count = fields.Integer(compute="_compute_omnichannel_counts")

    @api.depends("order_line.x_generated_subscription_id", "order_line.x_generated_rental_id")
    def _compute_omnichannel_counts(self):
        for order in self:
            order.x_subscription_count = len(order.order_line.mapped("x_generated_subscription_id"))
            order.x_rental_count = len(order.order_line.mapped("x_generated_rental_id"))

    def _provision_subscriptions_and_rentals(self):
        Sub = self.env["custom.subscription"]
        Plan = self.env["custom.subscription.plan"]
        Rental = self.env["custom.rental.order"]

        for order in self:
            sub_lines = order.order_line.filtered(
                lambda l: l.product_id.product_tmpl_id.x_is_subscription and not l.x_generated_subscription_id
            )
            for line in sub_lines:
                plan = line.product_id.product_tmpl_id.x_subscription_plan_id or Plan.search([], limit=1)
                if not plan:
                    continue
                sub = Sub.create({
                    "partner_id": order.partner_id.id,
                    "plan_id": plan.id,
                    "line_ids": [
                        Command.create({
                            "product_id": line.product_id.id,
                            "name": line.name or line.product_id.display_name,
                            "quantity": line.product_uom_qty,
                            "price_unit": line.price_unit,
                        })
                    ],
                })
                sub.action_activate()
                line.x_generated_subscription_id = sub.id
                order.message_post(body=_("Provisioned active subscription %s from order line.") % sub.name)

            rental_lines = order.order_line.filtered(
                lambda l: l.product_id.product_tmpl_id.x_is_rental and not l.x_generated_rental_id
            )
            for line in rental_lines:
                tmpl = line.product_id.product_tmpl_id
                pickup = line.x_rental_pickup_date or fields.Datetime.now()
                days = max(1, tmpl.x_rental_default_days or 3)
                ret_due = line.x_rental_return_date or (pickup + timedelta(days=days))
                rental = Rental.create({
                    "partner_id": order.partner_id.id,
                    "pickup_date": pickup,
                    "return_due_date": ret_due,
                    "security_deposit": tmpl.x_rental_deposit or 0.0,
                    "line_ids": [
                        Command.create({
                            "product_id": line.product_id.id,
                            "quantity": line.product_uom_qty,
                            "rental_price": line.price_unit,
                        })
                    ],
                })
                rental.action_reserve()
                line.x_generated_rental_id = rental.id
                order.message_post(body=_("Reserved rental booking %s for %s to %s.") % (rental.name, pickup, ret_due))

    def action_confirm(self):
        res = super().action_confirm()
        self._provision_subscriptions_and_rentals()
        return res

    def action_view_subscriptions(self):
        self.ensure_one()
        subs = self.order_line.mapped("x_generated_subscription_id")
        return {
            "type": "ir.actions.act_window",
            "name": _("Provisioned Subscriptions"),
            "res_model": "custom.subscription",
            "view_mode": "list,form",
            "domain": [("id", "in", subs.ids)],
        }

    def action_view_rentals(self):
        self.ensure_one()
        rentals = self.order_line.mapped("x_generated_rental_id")
        return {
            "type": "ir.actions.act_window",
            "name": _("Provisioned Rentals"),
            "res_model": "custom.rental.order",
            "view_mode": "list,form",
            "domain": [("id", "in", rentals.ids)],
        }


class CustomSignRequestPdf(models.Model):
    _inherit = "custom.sign.request"

    signed_pdf = fields.Binary(string="Signed PDF Certificate", readonly=True, attachment=True)
    signed_pdf_filename = fields.Char(readonly=True)

    def action_generate_signed_pdf(self):
        for req in self:
            cert_buf = io.BytesIO()
            c = pdf_canvas.Canvas(cert_buf, pagesize=A4)
            width, height = A4

            c.setFont("Helvetica-Bold", 16)
            c.drawString(48, height - 56, "Electronic Signature & Audit Certificate")
            c.setFont("Helvetica", 11)
            c.drawString(48, height - 80, f"Reference: {req.name}")
            c.drawString(48, height - 98, f"Document: {req.subject}")
            c.line(48, height - 110, width - 48, height - 110)

            y = height - 140
            for idx, signer in enumerate(req.signer_ids, start=1):
                if y < 140:
                    c.showPage()
                    y = height - 64
                c.setFont("Helvetica-Bold", 11)
                c.drawString(48, y, f"Signer {idx}: {signer.partner_id.name} ({signer.role or 'Signatory'})")
                y -= 16
                c.setFont("Helvetica", 10)
                c.drawString(
                    48,
                    y,
                    f"Status: {signer.state.upper()}  |  Typed Name: {signer.signed_name or '-'}  |  Signed At: {signer.signed_on or '-'}",
                )
                y -= 14
                c.drawString(48, y, f"IP Address: {signer.signed_ip or 'N/A'}")
                y -= 12

                if signer.signature_image:
                    try:
                        img_bytes = (
                            signer.signature_image.content
                            if hasattr(signer.signature_image, "content")
                            else base64.b64decode(signer.signature_image)
                        )
                        img_reader = ImageReader(io.BytesIO(img_bytes))
                        c.drawImage(img_reader, 48, y - 55, width=180, height=50, mask="auto", preserveAspectRatio=True)
                        y -= 68
                    except Exception:
                        y -= 10
                else:
                    y -= 14

            c.save()
            cert_buf.seek(0)

            writer = PdfWriter()
            if req.document_pdf:
                try:
                    doc_bytes = (
                        req.document_pdf.content
                        if hasattr(req.document_pdf, "content")
                        else base64.b64decode(req.document_pdf)
                    )
                    orig_reader = PdfReader(io.BytesIO(doc_bytes))
                    for page in orig_reader.pages:
                        writer.add_page(page)
                except Exception:
                    pass

            cert_reader = PdfReader(cert_buf)
            for page in cert_reader.pages:
                writer.add_page(page)

            out_buf = io.BytesIO()
            writer.write(out_buf)
            req.write({
                "signed_pdf": base64.b64encode(out_buf.getvalue()).decode("ascii"),
                "signed_pdf_filename": f"{req.name}_signed.pdf",
            })

