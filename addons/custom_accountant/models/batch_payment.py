from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPaymentBatchLink(models.Model):
    _inherit = "account.payment"

    batch_payment_id = fields.Many2one(
        "custom.batch.payment",
        string="Batch Payment",
        copy=False,
        ondelete="set null",
    )

    def action_print_payment_voucher(self):
        self.ensure_one()
        return self.env.ref("custom_accountant.action_report_payment_voucher").report_action(self)


class CustomBatchPayment(models.Model):
    _name = "custom.batch.payment"
    _description = "Batch Payment / Bank Deposit"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Reference", required=True, copy=False, readonly=True, default="New")
    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    batch_type = fields.Selection(
        [("inbound", "Inbound (Customer Batch Deposit)"), ("outbound", "Outbound (Vendor Batch Payment)")],
        required=True,
        default="inbound",
        tracking=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank Journal",
        required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        tracking=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [("draft", "New"), ("sent", "Sent / Deposited"), ("reconciled", "Reconciled")],
        default="draft",
        required=True,
        tracking=True,
    )
    payment_ids = fields.One2many(
        "account.payment",
        "batch_payment_id",
        string="Payments",
        domain="[('journal_id', '=', journal_id), ('payment_type', '=', batch_type), ('state', 'in', ('paid', 'reconciled'))]",
    )
    amount = fields.Monetary(string="Total Amount", compute="_compute_amount", store=True, currency_field="currency_id")
    payment_count = fields.Integer(compute="_compute_amount", store=True)
    note = fields.Text(string="Bank Remittance Notes")

    @api.depends("journal_id.currency_id", "company_id.currency_id")
    def _compute_currency_id(self):
        for batch in self:
            batch.currency_id = batch.journal_id.currency_id or batch.company_id.currency_id

    @api.depends("payment_ids.amount", "payment_ids.state")
    def _compute_amount(self):
        for batch in self:
            valid = batch.payment_ids.filtered(lambda p: p.state in ("paid", "reconciled"))
            batch.amount = sum(valid.mapped("amount"))
            batch.payment_count = len(valid)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                code = "custom.batch.payment.in" if vals.get("batch_type", "inbound") == "inbound" else "custom.batch.payment.out"
                vals["name"] = seq.next_by_code(code) or "BATCH/0001"
        return super().create(vals_list)

    def action_validate_batch(self):
        for batch in self:
            if not batch.payment_ids:
                raise UserError(_("Add at least one payment before validating batch %s.") % batch.name)
            batch.payment_ids.write({"is_sent": True})
            batch.state = "sent"

    def action_mark_reconciled(self):
        self.write({"state": "reconciled"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_print_batch_slip(self):
        self.ensure_one()
        return self.env.ref("custom_accountant.action_report_batch_payment").report_action(self)
