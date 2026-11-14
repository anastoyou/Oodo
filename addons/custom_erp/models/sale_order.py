from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

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
        default="website",
        tracking=True,
    )
    x_payment_mode = fields.Selection(
        selection=[
            ("prepaid", "Prepaid (UPI / Card / Netbanking)"),
            ("cod", "Cash on Delivery (COD)"),
            ("mixed", "Partial / Split"),
        ],
        string="Payment Mode",
        default="prepaid",
        tracking=True,
    )
    x_cod_verification_status = fields.Selection(
        selection=[
            ("not_required", "Not Required"),
            ("pending", "Pending Verification"),
            ("confirmed", "Confirmed by Customer"),
            ("cancelled_rto_risk", "High RTO Risk / Cancelled"),
        ],
        string="COD Verification",
        default="not_required",
        tracking=True,
    )
    x_cod_verified_by_id = fields.Many2one(
        "res.users",
        string="COD Verified By",
        readonly=True,
        copy=False,
    )
    x_cod_verified_date = fields.Datetime(
        string="COD Verified At",
        readonly=True,
        copy=False,
    )
    x_cod_notes = fields.Char(
        string="COD / Support Notes",
        help="Short call or WhatsApp confirmation note recorded by support.",
    )
    x_is_rto = fields.Boolean(
        string="Returned to Origin (RTO)",
        default=False,
        copy=False,
        tracking=True,
    )
    x_rto_reason = fields.Selection(
        selection=[
            ("size_issue", "Size / Fit Issue"),
            ("customer_unavailable", "Customer Unavailable"),
            ("refused_cod", "Refused COD Delivery"),
            ("fake_order", "Unreachable / Invalid Order"),
            ("damaged", "Damaged in Transit"),
            ("other", "Other"),
        ],
        string="RTO Reason",
        copy=False,
    )

    @api.onchange("x_payment_mode")
    def _onchange_x_payment_mode(self):
        for order in self:
            if order.x_payment_mode == "cod" and order.x_cod_verification_status == "not_required":
                order.x_cod_verification_status = "pending"
            elif order.x_payment_mode == "prepaid" and order.x_cod_verification_status == "pending":
                order.x_cod_verification_status = "not_required"

    def _set_cod_status(self, status, note):
        now = fields.Datetime.now()
        user = self.env.user
        for order in self:
            vals = {"x_cod_verification_status": status}
            if status in ("confirmed", "cancelled_rto_risk"):
                vals.update({"x_cod_verified_by_id": user.id, "x_cod_verified_date": now})
            order.write(vals)
            order.message_post(body=note)

    def action_confirm_cod(self):
        """Mark COD order as confirmed by customer support (call/WhatsApp)."""
        self._set_cod_status("confirmed", _("COD order confirmed with customer by %s.", self.env.user.name))

    def action_flag_cod_rto_risk(self):
        """Flag unconfirmed or suspicious COD order as high RTO risk."""
        self._set_cod_status("cancelled_rto_risk", _("COD order flagged as high RTO risk by %s.", self.env.user.name))

    def action_mark_rto(self):
        """Mark dispatched order as Returned to Origin (RTO) for KPI tracking."""
        for order in self:
            order.write({"x_is_rto": True})
            order.message_post(body=_("Order marked as Returned to Origin (RTO)."))

