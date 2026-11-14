from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    x_sales_channel = fields.Selection(
        selection=[
            ("website", "Website (D2C)"),
            ("whatsapp", "WhatsApp Business"),
            ("instagram", "Instagram / Social"),
            ("marketplace_myntra", "Myntra"),
            ("marketplace_ajio", "Ajio"),
            ("marketplace_amazon", "Amazon"),
            ("marketplace_flipkart", "Flipkart"),
            ("marketplace_meesho", "Meesho"),
            ("store_pos", "Retail Store"),
            ("b2b_wholesale", "B2B Wholesale"),
        ],
        string="Sales Channel",
        compute="_compute_x_sale_channel_info",
        store=True,
        readonly=True,
    )
    x_payment_mode = fields.Selection(
        selection=[
            ("prepaid", "Prepaid (UPI / Card / Netbanking)"),
            ("cod", "Cash on Delivery (COD)"),
            ("mixed", "Partial / Split"),
        ],
        string="Payment Mode",
        compute="_compute_x_sale_channel_info",
        store=True,
        readonly=True,
    )

    @api.depends(
        "move_type",
        "invoice_line_ids.sale_line_ids.order_id.x_sales_channel",
        "invoice_line_ids.sale_line_ids.order_id.x_payment_mode",
    )
    def _compute_x_sale_channel_info(self):
        for move in self:
            if move.move_type not in ("out_invoice", "out_refund", "out_receipt"):
                move.x_sales_channel = False
                move.x_payment_mode = False
                continue
            orders = move.invoice_line_ids.sale_line_ids.order_id
            primary = orders[:1]
            move.x_sales_channel = primary.x_sales_channel if primary else False
            move.x_payment_mode = primary.x_payment_mode if primary else False

